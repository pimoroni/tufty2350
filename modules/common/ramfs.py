import vfs

@micropython.viper
def viper_memcpy(dest: ptr8, src: ptr8, num: int) -> int:
    for i in range(num):
        dest[i] = src[i]
    return num


class RAMFS:
    RAMFS_BASE = 0x11700000
    RAMFS_SIZE = 0x00100000

    def __init__(self, size=0x100000, offset=0, blocksize=256, debug=False):
        self.debug = debug
        self.blocks, remainder = divmod(size, blocksize)

        if remainder:
            raise ValueError("Size should be a multiple of {blocksize:0,d}")

        self.blocksize = blocksize

        if size + offset > self.RAMFS_SIZE:
            raise ValueError("Size requested is larger than reserved RAM")

        self.address = self.RAMFS_BASE + offset
        self.length = size

    def readblocks(self, block_num, buf, offset=0):
        if self.debug:
            print(f"PSRAM: readblocks: {block_num} {len(buf)}, {offset}")
        viper_memcpy(buf, self.address + (block_num * self.blocksize) + offset, len(buf))

    def writeblocks(self, block_num, buf, offset=0):
        if self.debug:
            print(f"PSRAM: writeblocks: {block_num} {len(buf)}, {offset}")
        viper_memcpy(self.address + (block_num * self.blocksize) + offset, buf, len(buf))

    def ioctl(self, op, arg):
        if self.debug:
            print(f"PSRAM: ioctl: {op} {arg}")
        if op == 3:  # Sync
            return 0
        if op == 4:  # Block Count
            return self.blocks
        if op == 5:  # Block Size
            return self.blocksize
        if op == 6:  # Erase
            # We don't need to erase blocks ever,
            # but it might be worth implementing?
            return 0
        return None

    def __str__(self):
        return f"RAMFS: length: {self.length}, address: {self.address}"

def mkramfs(size=1024 * 1024, mount_point="/tmp", debug=False):
    psram = RAMFS(size, debug=debug)

    try:
        fs = vfs.VfsLfs2(psram, progsize=256)
    except OSError:
        vfs.VfsLfs2.mkfs(psram, progsize=256)
        fs = vfs.VfsLfs2(psram, progsize=256)

    vfs.mount(fs, mount_point)
