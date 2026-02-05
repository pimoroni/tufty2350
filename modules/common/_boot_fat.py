import os
import rp2
import vfs
import machine  # noqa: F401


# Try to mount the filesystem, and format the flash if it doesn't exist.

USER_FLASH_SIZE = rp2.Flash().ioctl(4, 0) * rp2.Flash().ioctl(5, 0)
LFS_SIZE = 1024 * 1024  # 1MB root filesystem
FS_LABEL = os.uname().machine.split(" ")[1]


bdev_lfs = rp2.Flash(start=USER_FLASH_SIZE - LFS_SIZE, len=LFS_SIZE)
try:
    lfs = os.VfsLfs2(bdev_lfs, progsize=256)
    vfs.mount(lfs, "/")
    os.listdir("/") # might fail with UnicodeError on corrupt FAT
except:  # noqa: E722
    os.VfsLfs2.mkfs(bdev_lfs, progsize=256)
    lfs = os.VfsLfs2(bdev_lfs, progsize=256)
    vfs.mount(lfs, "/")

bdev = rp2.Flash(start=0, len=USER_FLASH_SIZE - LFS_SIZE)
try:
    fat = vfs.VfsFat(bdev)
    vfs.mount(fat, "/system", readonly=True)
    os.listdir("/system") # might fail with UnicodeError on corrupt FAT

except:  # noqa: E722
    from badgeware import fatal_error

    fatal_error("System Error!", "Unable to mount filesystem. This may be a temporary error, reset your board again.")


del os, vfs, bdev, bdev_lfs, fat, lfs
