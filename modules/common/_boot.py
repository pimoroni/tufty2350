import rp2
import vfs
import machine  # noqa: F401


# fatlfs build: one unified littlefs over the WHOLE user-flash region, mounted
# at "/". The badge OS/apps live under "/system" (a subdirectory); the rest of "/"
# is user-writable space. This replaces the old split of a read-only FAT at
# "/system" plus a small 1 MB littlefs at "/". The host-facing editable drive is
# synthesised on demand from this littlefs by the fatlfs module.
bdev = rp2.Flash()
try:
    fs = vfs.VfsLfs2(bdev, progsize=256)
    vfs.mount(fs, "/")
except:  # noqa: E722
    vfs.VfsLfs2.mkfs(bdev, progsize=256)
    fs = vfs.VfsLfs2(bdev, progsize=256)
    vfs.mount(fs, "/")

del vfs, bdev, fs
