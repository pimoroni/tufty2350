import vfs
import machine  # noqa: F401
import rp2


# Try to mount the filesystem, and format the flash if it doesn't exist.
# Note: the flash requires the programming size to be aligned to 256 bytes.
bdev = rp2.Flash()
try:
    fs = vfs.VfsLfs2(bdev, progsize=256)
except:  # noqa: E722
    vfs.VfsLfs2.mkfs(bdev, progsize=256)
    fs = vfs.VfsLfs2(bdev, progsize=256)
vfs.mount(fs, "/")

del vfs, bdev, fs
