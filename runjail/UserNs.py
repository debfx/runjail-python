# Copyright (C) 2017 Felix Geyer <debfx@fobos.de>
# Copyright (C) 2013 The Chromium OS Authors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 or (at your option)
# version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import errno
import os
import signal
import sys
import time

from runjail.Libc import Libc


class PipeLock:
    """A simple one-way lock based on pipe().
    This is used when code is calling os.fork() directly and needs to synchronize
    behavior between the two.  The same process should not try to use Wait/Post
    as it will just see its own results.  If you need bidirection locks, you'll
    need to create two yourself.
    Be sure to delete the lock when you're done to prevent fd leakage.
    """
    def __init__(self):
        self.read_fd, self.write_fd = os.pipe2(os.O_CLOEXEC)

    def Wait(self, size=1):
        """Read |size| bytes from the pipe.
        Args:
        size: How many bytes to read.  It must match the length of |data| passed
            by the other end during its call to Post.
        Returns:
        The data read back.
        """
        return os.read(self.read_fd, size)

    def Post(self, data=b"!"):
        """Write |data| to the pipe.
        Args:
        data: The data to send to the other side calling Wait.  It must be of the
            exact length that is passed to Wait.
        """
        os.write(self.write_fd, data)

    def __del__(self):
        os.close(self.read_fd)
        os.close(self.write_fd)


class UserNs:
    def __init__(self, chroot_dir):
        self._chroot_dir = chroot_dir
        self._libc = Libc()
        # remember original uid, changes when transitioning to new user ns
        self._uid = os.getuid()

    def safeTcSetPgrp(self, fd, pgrp):
        """Set |pgrp| as the controller of the tty |fd|."""
        try:
            curr_pgrp = os.tcgetpgrp(fd)
        except OSError as e:
            # This can come up when the fd is not connected to a terminal.
            if e.errno == errno.ENOTTY:
                return
            raise
        # We can change the owner only if currently own it.  Otherwise we'll get
        # stopped by the kernel with SIGTTOU and that'll hit the whole group.
        if curr_pgrp == os.getpgrp():
            os.tcsetpgrp(fd, pgrp)

    def reapChildren(self, pid):
        """Reap all children that get reparented to us until we see |pid| exit.
        Args:
            pid: The main child to watch for.
        Returns:
            The wait status of the |pid| child.
        """
        pid_status = 0
        while True:
            try:
                (wpid, status) = os.wait()
                if pid == wpid:
                    # Save the status of our main child so we can exit with it below.
                    pid_status = status
            except OSError as e:
                if e.errno == errno.ECHILD:
                    break
                elif e.errno != errno.EINTR:
                    raise
        return pid_status

    def exitAsStatus(self, status):
        """Exit the same way as |status|.
        If the status field says it was killed by a signal, then we'll do that to
        ourselves.  Otherwise we'll exit with the exit code.
        See http://www.cons.org/cracauer/sigint.html for more details.
        Args:
            status: A status as returned by os.wait type funcs.
        """
        if os.WIFSIGNALED(status):
            # Kill ourselves with the same signal.
            sig_status = os.WTERMSIG(status)
            pid = os.getpid()
            os.kill(pid, sig_status)
            time.sleep(0.1)
            # Still here?  Maybe the signal was masked.
            try:
                signal.signal(sig_status, signal.SIG_DFL)
            except RuntimeError as e:
                if e.args[0] != errno.EINVAL:
                    raise
            os.kill(pid, sig_status)
            time.sleep(0.1)
            # Still here?  Just exit.
            exit_status = 128 + sig_status
        else:
            exit_status = os.WEXITSTATUS(status)
        # Exit with the code we want.
        sys.exit(exit_status)

    def create(self, new_net=False):
        unshare_flags = Libc.CLONE_NEWUSER | Libc.CLONE_NEWNS | Libc.CLONE_NEWPID | Libc.CLONE_NEWIPC
        if new_net:
            unshare_flags |= Libc.CLONE_NEWNET

        self._libc.unshare(unshare_flags)

        # Used to make sure process groups are in the right state before we try to
        # forward the controlling terminal.
        lock = PipeLock()

        # Now that we're in the new pid namespace, fork.  The parent is the master
        # of it in the original namespace, so it only monitors the child inside it.
        # It is only allowed to fork once too.
        pid = os.fork()
        if pid != 0:
            # Mask SIGINT with the assumption that the child will catch & process it.
            # We'll pass that back up below.
            signal.signal(signal.SIGINT, signal.SIG_IGN)

            # Forward the control of the terminal to the child so it can manage input.
            self.safeTcSetPgrp(sys.stdin.fileno(), pid)

            # Signal our child it can move forward.
            lock.Post()
            del lock

            status = self.reapChildren(pid)

            # Cleanup
            self.umount(self._chroot_dir, Libc.MNT_DETACH)
            os.rmdir(self._chroot_dir)

            self.exitAsStatus(status)

        self.setup_user_mapping()
        self.mount_private_propagation("/")

        if new_net:
            self.set_iface_lo_up()

        # Wait for our parent to finish initialization.
        lock.Wait()
        del lock

        # Resetup the locks for the next phase.
        lock = PipeLock()

        pid = os.fork()
        if pid != 0:
            # Mask SIGINT with the assumption that the child will catch & process it.
            # We'll pass that back up below.
            signal.signal(signal.SIGINT, signal.SIG_IGN)

            # Now that we're in a new pid namespace, start a new process group so that
            # children have something valid to use.  Otherwise getpgrp/etc... will get
            # back 0 which tends to confuse -- you can't setpgrp(0) for example.
            os.setpgrp()

            # Forward the control of the terminal to the child so it can manage input.
            self.safeTcSetPgrp(sys.stdin.fileno(), pid)

            # Signal our child it can move forward.
            lock.Post()
            del lock

            # Watch all of the children.  We need to act as the master inside the
            # namespace and reap old processes.
            self.exitAsStatus(self.reapChildren(pid))

        # Wait for our parent to finish initialization.
        lock.Wait()
        del lock

        # Create a process group for the grandchild so it can manage things
        # independent of the init process.
        os.setpgrp()

    def run(self, command, cwd=os.getcwd()):
        self._libc.chroot(self._chroot_dir)

        # move cwd to new mounts
        try:
            os.chdir(cwd)
        except FileNotFoundError:
            print("The current working directory '{}' doesn't exist in the new namespace.\n"
                  "Resetting to '/'.".format(cwd),
                  file=sys.stderr)
            os.chdir("/")

        # reset signal handlers
        for sig_nr in range(1, signal.NSIG):
            if signal.getsignal(sig_nr) == signal.SIG_IGN:
                signal.signal(sig_nr, signal.SIG_DFL)

        # drops all capabilities (if uid != 0)
        os.execvp(command[0], command)

    def mount_private_propagation(self, mountpoint):
        self._libc.mount("none", mountpoint, None, Libc.MS_REC | Libc.MS_PRIVATE)

    def mount_proc(self, path):
        self._libc.mount("proc",
                         path,
                         "proc",
                         Libc.MS_NOSUID | Libc.MS_NODEV | Libc.MS_NOEXEC)

    def remount_ro(self, path, existing_flags):
        self._libc.mount(path,
                         path,
                         None,
                         existing_flags | Libc.MS_REC | Libc.MS_BIND | Libc.MS_REMOUNT | Libc.MS_RDONLY)

    def mount_inaccessible(self, path):
        self._libc.mount("tmpfs", path, "tmpfs", Libc.MS_REC, "mode=000")
        self.remount_ro(path, existing_flags=0)

    def mount_bind(self, source, target):
        self._libc.mount(source, target, None, Libc.MS_REC | Libc.MS_BIND)

    def mount_tmpfs(self, path, mode):
        self._libc.mount("tmpfs",
                         path,
                         "tmpfs",
                         Libc.MS_REC | Libc.MS_NOSUID | Libc.MS_NOATIME,
                         "mode=" + mode)

    def umount(self, path, flags=0):
        self._libc.umount2(path, flags)

    def setup_user_mapping(self):
        """Map the uid/gid in the parent namespace to the same inside the new namespace."""

        with open("/proc/self/uid_map", "w") as f:
            f.write("{} {} 1\n".format(self._uid, self._uid))

        # set setgroups to "deny" so we are allowed to write to gid_map
        try:
            with open("/proc/self/setgroups", "w") as f:
                f.write("deny")
        except FileNotFoundError:
            # pre 3.19 kernels don't have this restriction, ignore
            pass

        with open("/proc/self/gid_map", "w") as f:
            f.write("{} {} 1\n".format(self._uid, self._uid))

    def set_no_new_privs(self):
        self._libc.prctl(Libc.PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)

    def set_iface_lo_up(self):
        try:
            import pyroute2
        except ImportError:
            print("Couldn't bring up the loopback interface for network. "
                  "Install the pyroute2 python library.", file=sys.stderr)
            return

        ipr = pyroute2.IPRoute()
        dev = ipr.link_lookup(ifname="lo")[0]
        # Linux automatically adds the IP addresses
        ipr.link("set", index=dev, state="up")
