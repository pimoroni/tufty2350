// fatlfs.h - FAT16 <-> LittleFS translation shim (public API).
//
// Presents a FAT16 block device outward (512-byte LBA sectors) while storing
// every file as an individual file inside a LittleFS (lfs2) volume. FAT metadata
// (boot sector, FATs, directory entries) is synthesized on read and interpreted
// on write; file data is streamed to/from LittleFS. Host writes are deferred and
// committed to LittleFS at flush barriers (SCSI SYNCHRONIZE CACHE / NBD FLUSH /
// unmount), which is where the host guarantees on-disk coherence.
//
// FAT16 (not 32) so the advertised volume can match the real LittleFS capacity:
// FAT32's 65525-cluster minimum would force a >=32 MB volume at 512 B clusters,
// overcommitting a small flash and turning oversized copies into silent late
// failures. FAT16 allows ~2-32 MB honest volumes, so a too-big copy fails
// upfront in the host's UI. The one structural FAT16 quirk is the fixed-size
// root directory region (root_entries below); subdirectories are unlimited.
//
// Portable C: depends only on the lfs2 API + <string.h>/<stdlib.h>. The same
// core runs on the host (behind nbdkit) and on an RP2 (behind TinyUSB MSC or an
// on-device FAT driver). All dynamic memory is malloc/free; a fixed-arena
// allocator can be substituted on embedded targets.
#ifndef FATLFS_H
#define FATLFS_H

#include <stdint.h>
#include <stddef.h>
#include "lfs2.h"

#ifdef __cplusplus
extern "C" {
#endif

// Return codes: 0 on success, negative lfs2 error code, or one of these.
#define FATLFS_OK        0
#define FATLFS_ERR_INVAL -22
#define FATLFS_ERR_NOMEM -12
#define FATLFS_ERR_IO    -5

typedef struct fatlfs_config {
    lfs2_t *lfs;              // an already-mounted lfs2 instance (caller owns)

    uint32_t cluster_size;   // FAT cluster size in bytes; multiple of 512.
                             // 512 keeps small volumes inside the FAT16 window.
    uint32_t cluster_count;  // usable data clusters, clamped into FAT16's
                             // [4085, 65524] window. Advertised volume size =
                             // cluster_count*cluster_size; size it to the real
                             // lfs capacity so hosts see honest free space.

    uint32_t root_entries;   // fixed FAT16 root directory capacity in 32-byte
                             // entries (LFNs consume several per file). Rounded
                             // up to a sector multiple. 0 => 1024.

    uint32_t staging_max_bytes; // soft cap on RAM held for not-yet-flushed file
                                // data clusters; exceeding it triggers a flush.

    uint32_t volume_id;      // FAT volume serial (0 => derived default)
    char volume_label[12];   // 11 chars + NUL; "" => "FATLFS     "

    // OS "trash" files (macOS ._AppleDouble, .DS_Store, .Spotlight-V100,
    // .Trashes, .fseventsd, __MACOSX; Windows Thumbs.db, $RECYCLE.BIN, ...) are
    // quietly dropped rather than written to LittleFS. Set to 1 to keep them.
    int keep_os_trash;
} fatlfs_config_t;

typedef struct fatlfs fatlfs_t;

// Create/attach the shim over a mounted lfs2 volume. Scans the existing LittleFS
// content and presents it as a populated FAT tree (two-way bridge / persistence).
// Returns a heap-allocated instance in *out, or a negative error.
int fatlfs_mount(const fatlfs_config_t *cfg, fatlfs_t **out);

// Flush any pending writes to LittleFS and free the instance. Does not unmount
// the underlying lfs2 (caller owns it).
int fatlfs_unmount(fatlfs_t *fs);

// Outward FAT16 block device geometry.
uint32_t fatlfs_block_size(const fatlfs_t *fs);   // always 512
uint64_t fatlfs_block_count(const fatlfs_t *fs);  // total 512-byte sectors

// True if anything host-written awaits commit (staged file/dir clusters OR a
// modified root directory region - the latter has no staging bytes, so callers
// gating flushes on staged_bytes alone would miss root-only renames/deletes).
int fatlfs_dirty(const fatlfs_t *fs);

// Read/write `count` 512-byte sectors starting at LBA `lba` (0-based).
// Return FATLFS_OK or negative error. Writes are staged, not yet in LittleFS.
int fatlfs_read(fatlfs_t *fs, uint64_t lba, uint32_t count, void *buf);
int fatlfs_write(fatlfs_t *fs, uint64_t lba, uint32_t count, const void *buf);

// Commit all staged writes into LittleFS (create/write/rename/delete files and
// dirs) and sync. Call on every host flush barrier and before unmount.
int fatlfs_flush(fatlfs_t *fs);

// Embedded port: keep flash writes out of the USB callback. Enable deferred
// spill, then drive spill/flush from the main loop.
void     fatlfs_defer_spill(fatlfs_t *fs, int on);
void     fatlfs_spill(fatlfs_t *fs, uint32_t max_clusters);  // 0 = unlimited
uint32_t fatlfs_staged_bytes(const fatlfs_t *fs);
uint32_t fatlfs_staging_max(const fatlfs_t *fs);

#ifdef __cplusplus
}
#endif

#endif // FATLFS_H
