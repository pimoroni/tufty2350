// fatbridge.h - synthesised FAT16 volume backed by an arbitrary file store.
//
// Presents a read/write FAT16 disk to a USB-MSC host (or any block consumer)
// without materialising a FAT image: reads are synthesised on the fly from the
// backend's file list, and writes are interpreted back into file operations.
// The backend is a small vtable so the same core runs over littlefs on the
// rp2 port and over anything (POSIX dir, real littlefs) in host tests.
//
// Phase 1 (this file): full read synthesis + a write interpreter for the
// common host patterns (create/append/overwrite/delete with 8.3 names).
// Long-file-name (LFN) support and large data-before-dir spill are TODO.

#ifndef FATBRIDGE_H
#define FATBRIDGE_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

#define FATBRIDGE_SECTOR_SIZE 512u

// Max cluster slots in the sparse write cache (effective count is bounded by
// wbuf_len / cluster_bytes). 512 slots = up to 1 MB of in-flight writes at 2 KB
// clusters; struct cost is 2 KB. With async back-pressure the host paces itself
// to our commit rate, so this is the working-set headroom, not the total copy.
#define FATBRIDGE_CACHE_SLOTS 4096

// Backend: how the core sees the underlying file store. All calls are by a
// stable integer index into a snapshot taken at fatbridge_begin(). Names are short
// 8.3-style for now (caller may pass long names; core will 8.3-mangle).
// Path-based backend (supports a directory tree). Paths are full, "/"-separated,
// with no leading slash ("" or "/" means the root); the core uses the same form
// it gets back from list().
typedef struct fatbridge_backend {
    void *ctx;
    // List child #idx of directory `dir` ("" == root). Fills name, size (files),
    // is_dir. Returns 0 on success, <0 when idx is past the last child.
    int (*list)(void *ctx, const char *dir, int idx, char *name, size_t name_cap, uint32_t *size, int *is_dir);
    // Read len bytes at off from file `path`. Returns bytes read or <0.
    int (*read)(void *ctx, const char *path, uint32_t off, void *buf, uint32_t len);
    // Create/replace file `path` (off==0 => truncate-create). Returns 0 or <0.
    int (*write)(void *ctx, const char *path, uint32_t off, const void *buf, uint32_t len);
    // Set final size (commit) of file `path`. Returns 0 or <0.
    int (*commit)(void *ctx, const char *path, uint32_t size);
    // Delete file or (empty) dir `path`. Returns 0 or <0.
    int (*remove)(void *ctx, const char *path);
    // Rename oldpath -> newpath. Returns 0 or <0.
    int (*rename)(void *ctx, const char *oldpath, const char *newpath);
    // Create directory `path`. Returns 0 or <0.
    int (*mkdir)(void *ctx, const char *path);
    // Optional (may be NULL): report the backing store's total and used bytes so
    // the synthesised volume can present an accurate size and free space. Returns
    // 0 on success, <0 if unavailable.
    int (*fs_usage)(void *ctx, uint64_t *total_bytes, uint64_t *used_bytes);
} fatbridge_backend_t;

// One synthesised tree node (file or directory).
typedef struct {
    char name[64];          // leaf name, ASCII, truncated to 63
    char name83[11];        // packed 8.3 alias, space-padded, upper-case
    uint8_t nt_flags;       // VFAT NT-byte: 0x08 lower base, 0x10 lower ext
    bool needs_lfn;         // name not representable as plain/lower 8.3
    bool is_dir;            // directory (entry-table) vs regular file
    int parent;             // index of parent dir node, -1 == root
    uint32_t size;          // files only
    uint32_t first_cluster; // file data, or dir entry-table; 0 if none
    uint32_t n_clusters;
    bool dirty;             // host wrote file data this session
    bool present;           // false once host deletes it
    bool pending_remove;    // host deleted it; backend remove deferred to flush
    bool pending_rename;    // host renamed it; backend rename deferred to flush
    bool pending_mkdir;     // host created this dir; backend mkdir deferred
    uint16_t commit_done;   // clusters of this file already committed (bounded flush)
    uint32_t commit_cl;     // physical cluster of cluster #commit_done (FAT-chain cursor)
    char old_name[64];      // old leaf name, for the deferred rename
} fatbridge_file_t;

typedef struct fatbridge {
    const fatbridge_backend_t *be;

    // geometry (sectors)
    uint8_t  sectors_per_cluster;
    uint16_t reserved_sectors;
    uint8_t  num_fats;
    uint16_t root_entries;
    uint32_t total_sectors;
    uint32_t fat_sectors;       // per FAT
    uint32_t root_dir_sectors;
    uint32_t total_clusters;    // count of data clusters (+2 offset applies)
    uint32_t reserved_clusters; // top-of-disk clusters marked unavailable so the
                                // host's free-space count matches the backend's
                                // real free space (accounts for backend metadata
                                // overhead + capacity beyond our file data)
    uint32_t fat_start;         // first FAT sector
    uint32_t root_start;        // first root-dir sector
    uint32_t data_start;        // first data sector (== cluster 2)
    uint32_t vol_id;
    char     vol_label[11];     // FAT volume label (space-padded, not NUL-terminated)

    // file table (caller-provided storage)
    fatbridge_file_t *files;
    int n_files;
    int max_files;

    // write staging: a single in-RAM cluster-keyed dirty cache (phase 1 keeps
    // it simple: the caller hands us a buffer; we map host data writes by
    // cluster into it and flush per-file on dir-entry/commit).
    // Sparse write cache: wbuf is divided into fixed cluster-sized slots; each
    // slot holds one arbitrary cluster (cache_cl[i], 0 == empty). Any clusters
    // can be cached regardless of address; committing a file frees its slots,
    // so multiple/interleaved file writes in one session work.
    uint8_t *wbuf;
    size_t   wbuf_len;
    uint32_t cache_cl[FATBRIDGE_CACHE_SLOTS];   // cluster number in each slot, 0=empty
    uint8_t  cache_clean[FATBRIDGE_CACHE_SLOTS]; // 1 = committed (data safe in backend,
                                            // evictable under pressure); 0 = dirty.
                                            // Write-back: committed clusters stay
                                            // cached so a later size catch-up can
                                            // re-commit from the latest data.

    // Host FAT mirror: the cluster-chain table exactly as the host writes it.
    // Lets us follow a directory's entry-table chain when the host extends a
    // busy directory past one cluster (otherwise those overflow entries get
    // mis-cached as file data and the files are silently lost). Caller-provided,
    // sized >= total_clusters + 2. NULL disables (contiguous-only fallback).
    uint16_t *fat;
    uint32_t  fat_cap;      // entries available in fat[]

    // LFN accumulation while interpreting host root-dir writes
    char    lfn_acc[256];
    uint8_t lfn_checksum;
    bool    lfn_active;

    // Deferred-commit: the MSC write callback only caches data and sets this;
    // the actual backend (flash) writes happen in fatbridge_flush() from a safe
    // (non-USB-callback) context. Critical on RP2: flash_range_program cannot
    // run from the TinyUSB callback (XIP/multicore-lockout) without faulting.
    bool    pending;
    bool    dirty_dirs; // new data-region sectors arrived; subdir tables need a
                        // (re)parse pass before the next commit (see flush_step)
    bool    overflow;   // set if a data sector was dropped (cache full) - must
                        // stay false: with async back-pressure the host is paced
                        // so this never trips for a correctly-sized cache.
} fatbridge_t;

// Initialise the synthesised volume. total_bytes is the disk size presented to
// the host; sectors_per_cluster sets cluster size. files[]/max_files store the
// snapshot; wbuf/wbuf_len is scratch for write staging (from the MP heap).
// Returns 0 on success, <0 on error (bad geometry / too many files).
int fatbridge_init(fatbridge_t *v, const fatbridge_backend_t *be,
    uint32_t total_bytes, uint8_t sectors_per_cluster,
    fatbridge_file_t *files, int max_files,
    uint8_t *wbuf, size_t wbuf_len,
    uint16_t *fat, uint32_t fat_cap);

// (Re)snapshot the backend's files and assign clusters. Call after init and
// whenever the underlying store changed outside a host session.
int fatbridge_begin(fatbridge_t *v);

void fatbridge_capacity(const fatbridge_t *v, uint32_t *block_count, uint16_t *block_size);

// Count file-data clusters still pending commit (commit-progress denominator).
uint32_t fatbridge_pending_clusters(const fatbridge_t *v);

// Serve a host READ of bufsize bytes starting at sector lba (+byte offset).
// Returns bytes produced (== bufsize) or <0.
int32_t fatbridge_read(fatbridge_t *v, uint32_t lba, uint32_t offset, void *buf, uint32_t bufsize);

// Interpret a host WRITE. Returns bytes consumed (== bufsize) or <0. Backend
// mutations are deferred (only cached/marked); call fatbridge_flush() afterwards.
int32_t fatbridge_write(fatbridge_t *v, uint32_t lba, uint32_t offset, const void *buf, uint32_t bufsize);

// Apply ALL deferred backend writes/removes (loops fatbridge_flush_step). Fine for
// host tests / small edits; for a live USB-MSC session use fatbridge_flush_step in a
// loop interleaved with tud_task() so flash never starves the USB task.
void fatbridge_flush(fatbridge_t *v);

// Do at most ONE bounded unit of deferred work (one mkdir/rename/remove, or one
// cluster of a file commit). Returns true if it did something (more may remain),
// false when nothing is pending. Keeps each flash burst short.
bool fatbridge_flush_step(fatbridge_t *v);

#endif // FATBRIDGE_H
