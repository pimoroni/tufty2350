// fatlfs.c - FAT16 <-> LittleFS translation shim. See fatlfs.h for the model.
//
// Outward: a synthesized FAT16 volume (512-byte sectors). Inward: individual
// files in an lfs2 volume. Host writes are staged in RAM and committed to
// LittleFS at flush barriers. Files are identified across flushes by their FAT
// first-cluster, so rename/move preserve data instead of copying it. Sub-cluster
// (partial) writes are handled by read-modify-write into the staging buffer.
// Files larger than the RAM budget spill their tail clusters to per-chain temp
// LittleFS files during the write burst and are claimed at the flush barrier.
//
// FAT16 structure notes: the root directory is a FIXED linear region between
// the FATs and the data area (root_bytes, authoritative, no staging), not a
// cluster chain - cluster numbering still starts at 2 but cluster 2 is plain
// data. The in-RAM FAT keeps 28-bit FAT32-style values; serve/apply translate
// to/from 16-bit on-disk entries so all chain-walking code stays unchanged.

#include "fatlfs.h"
#include "fat_defs.h"
#include <stdlib.h>
#include <stdio.h>
#include <ctype.h>
#include "fatlfs_port.h"

#define FATLFS_PATH_MAX 512
#define FATLFS_LFN_MAX  255
#define SPILL_PREFIX    ".fatlfs_spill_"
#define MV_PREFIX       ".fatlfs_mv_"
#define RECOVER_PREFIX  "RECOVERED_"

// Max UTF-16 units a host-written LFN chain can address: ord sequence 1..20,
// 13 units each. Buffers must be sized for THIS, not FATLFS_LFN_MAX (255) -
// a max-length chain writes 260 units.
#define LFN_MAX_UNITS   (20 * LFN_CHARS_PER_ENTRY)
// Per-directory 8.3 short-name uniqueness table entries (encoder).
#define SHORT_TABLE_MAX 256

// ---------------------------------------------------------------------------
// Instance state
// ---------------------------------------------------------------------------

typedef struct {
    char     path[FATLFS_PATH_MAX];  // lfs path, no leading slash ("" = root)
    uint32_t first_cluster;          // FAT chain head (0 for empty file)
    uint32_t size;                   // bytes (0 for dirs)
    uint8_t  is_dir;
} fatlfs_node_t;

typedef struct { int32_t node; uint32_t idx; } owner_t;  // node into fs->committed

struct fatlfs {
    lfs2_t  *lfs;
    uint32_t cluster_size;
    uint32_t spc;            // sectors per cluster (cluster_size/512)
    uint32_t cluster_count;  // usable data clusters
    uint32_t cc2;            // cluster_count + 2 (entries 0,1 reserved)
    uint32_t staging_max;

    // Region geometry, in 512-byte sectors:
    // [0, reserved) boot | [reserved, root_start) FATs | [root_start,
    // data_start) fixed root directory | [data_start, total) data clusters.
    uint32_t reserved_sectors;
    uint32_t fat_sectors;    // sectors per FAT copy
    uint32_t root_start;     // first root-directory sector
    uint32_t root_sectors;   // fixed root region size
    uint32_t root_entries;   // root capacity in 32-byte entries
    uint32_t data_start;     // first data sector
    uint64_t total_sectors;

    uint8_t *root_bytes;     // authoritative root-directory contents
    int      root_dirty;     // host wrote the root region since last commit

    uint32_t *fat;           // [cc2] authoritative next-cluster table
    uint8_t **staging;       // [cc2] host-written, not-yet-committed cluster data
    uint8_t **dir_bytes;     // [cc2] persistent directory-cluster contents
    owner_t  *owner;         // [cc2] file-data cluster -> (committed node, logical idx)
                             //       node==-2 means the cluster was spilled (see below)
    uint32_t *spillhead;     // [cc2] for spilled clusters: chain head keying the temp file
    uint32_t *prev;          // [cc2] reverse-FAT scratch for spill (persistent: rebuilt
                             //       each spill but never re-allocated, so spilling can't
                             //       fail on a tight arena mid-copy)

    uint32_t staged_bytes;
    uint32_t alloc_hint;     // free-cluster scan hint (encoder)

    fatlfs_node_t *committed;   // last-flush snapshot (files + dirs, excl. root)
    int            committed_n;

    uint8_t boot[FAT_SECTOR_SIZE];
    uint8_t *clusbuf;        // cluster_size scratch (single-threaded use)

    uint32_t volume_id;
    char     volume_label[12];
    int      keep_trash;     // if 0, drop OS turd files instead of storing them

    // one cached open spill file for the current large write burst
    int         spill_open;
    uint32_t    spill_head;
    lfs2_file_t spill_file;

    int         no_inline_spill;  // embedded: don't spill from the write path (flash
                                  // masks IRQs in the USB callback); drive it from a task

    // Per-handle file caches. LittleFS may be built with LFS2_NO_MALLOC (as in the
    // MicroPython firmware), so every open must supply its own cache buffer via
    // lfs2_file_opencfg. Three are needed because the reconcile write handle and a
    // source read handle (and a kept-open spill handle) can be open at once.
    struct lfs2_file_config fc_wr, fc_rd, fc_spill;
    uint8_t    *cache_wr, *cache_rd, *cache_spill;

    // Kept-open spill READ handle. Committing a large spilled file reads thousands
    // of clusters back from one temp file; re-opening it per cluster is O(n) littlefs
    // metadata walks and, on flash, turns eject into a multi-minute "hang". Hold the
    // handle open across a file's sequential cluster reads instead.
    int         spill_rd_open;
    uint32_t    spill_rd_head;
    lfs2_file_t spill_rd_file;
    struct lfs2_file_config fc_spill_rd;
    uint8_t    *cache_spill_rd;
};

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

static inline uint32_t fat_get(fatlfs_t *fs, uint32_t c) {
    return (c < fs->cc2) ? (fs->fat[c] & FAT_ENTRY_MASK) : 0;
}
static inline void fat_set(fatlfs_t *fs, uint32_t c, uint32_t v) {
    if (c < fs->cc2) fs->fat[c] = v & FAT_ENTRY_MASK;
}

static int path_depth(const char *p) {
    int d = 0; for (; *p; p++) if (*p == '/') d++; return d;
}

// Bounded join with explicit truncation at FATLFS_PATH_MAX-1 (snprintf here
// trips -Werror=format-truncation on the firmware build).
static void path_join(char *out, const char *prefix, const char *name) {
    size_t n = 0;
    if (prefix[0]) {
        for (size_t i = 0; prefix[i] && n < FATLFS_PATH_MAX - 1; i++) out[n++] = prefix[i];
        if (n < FATLFS_PATH_MAX - 1) out[n++] = '/';
    }
    for (size_t i = 0; name[i] && n < FATLFS_PATH_MAX - 1; i++) out[n++] = name[i];
    out[n] = 0;
}

// UTF-16 (single BMP unit) -> UTF-8, appended at *pp (assumes room).
static void put_utf8(char **pp, uint16_t u) {
    char *p = *pp;
    if (u == 0) { *pp = p; return; }
    if (u < 0x80) { *p++ = (char)u; }
    else if (u < 0x800) { *p++ = (char)(0xC0 | (u >> 6)); *p++ = (char)(0x80 | (u & 0x3F)); }
    else if (u >= 0xD800 && u <= 0xDFFF) { /* surrogate: skip */ }
    else { *p++ = (char)(0xE0 | (u >> 12)); *p++ = (char)(0x80 | ((u >> 6) & 0x3F));
           *p++ = (char)(0x80 | (u & 0x3F)); }
    *pp = p;
}

// UTF-8 -> next BMP code unit; advances *pp. Returns 0 at end.
static uint16_t next_utf16(const char **pp) {
    const unsigned char *p = (const unsigned char *)*pp;
    uint32_t u;
    if (*p == 0) return 0;
    if (*p < 0x80) { u = *p; p += 1; }
    else if ((*p & 0xE0) == 0xC0) { u = ((uint32_t)(p[0] & 0x1F) << 6) | (p[1] & 0x3F); p += 2; }
    else if ((*p & 0xF0) == 0xE0) { u = ((uint32_t)(p[0] & 0x0F) << 12) | ((uint32_t)(p[1] & 0x3F) << 6) | (p[2] & 0x3F); p += 3; }
    else { u = '_'; p += 4; }  // non-BMP: placeholder
    *pp = (const char *)p;
    return (uint16_t)u;
}

// ---------------------------------------------------------------------------
// Boot sector synthesis (FAT16 BPB; no FSInfo / backup boot on FAT16)
// ---------------------------------------------------------------------------

static void build_boot(fatlfs_t *fs) {
    uint8_t *b = fs->boot;
    memset(b, 0, FAT_SECTOR_SIZE);
    b[0] = 0xEB; b[1] = 0x3C; b[2] = 0x90;              // jmp
    memcpy(b + 3, "MSDOS5.0", 8);                        // OEM
    fat_wr16(b + 11, FAT_SECTOR_SIZE);                   // bytes/sector
    b[13] = (uint8_t)fs->spc;                            // sectors/cluster
    fat_wr16(b + 14, (uint16_t)fs->reserved_sectors);
    b[16] = FAT_NUM_FATS;
    fat_wr16(b + 17, (uint16_t)fs->root_entries);        // fixed root capacity
    if (fs->total_sectors < 0x10000) {
        fat_wr16(b + 19, (uint16_t)fs->total_sectors);   // total sectors 16
    }
    b[21] = FAT_MEDIA_FIXED;
    fat_wr16(b + 22, (uint16_t)fs->fat_sectors);         // FAT size 16
    fat_wr16(b + 24, 63);                                // sectors/track
    fat_wr16(b + 26, 255);                               // heads
    fat_wr32(b + 28, 0);                                 // hidden
    if (fs->total_sectors >= 0x10000) {
        fat_wr32(b + 32, (uint32_t)fs->total_sectors);   // total sectors 32
    }
    b[36] = 0x80;                                        // drive number
    b[38] = 0x29;                                        // ext boot signature
    fat_wr32(b + 39, fs->volume_id);
    memcpy(b + 43, fs->volume_label, 11);
    memcpy(b + 54, "FAT16   ", 8);
    b[510] = 0x55; b[511] = 0xAA;
}

static void spill_name(char *out, uint32_t head);  // fwd decl (defined below)

// ---------------------------------------------------------------------------
// Cluster read paths (precedence: staging > dir_bytes > owner(lfs) > zero)
// ---------------------------------------------------------------------------

// Content excluding staging (used for RMW init and as fallback).
static void read_cluster_base(fatlfs_t *fs, uint32_t c, uint8_t *buf) {
    if (c < fs->cc2 && fs->dir_bytes[c]) {
        memcpy(buf, fs->dir_bytes[c], fs->cluster_size);
        return;
    }
    if (c < fs->cc2 && fs->owner[c].node == -2) {
        // Cluster was spilled to a per-chain temp file during a large write; read
        // it back from there so mid-session reads (e.g. a copy) see real data. Keep
        // the temp file open across a chain's clusters (spill_rd_head) - see the note
        // on the struct fields - so committing a large file isn't O(n) opens.
        uint32_t off = fs->owner[c].idx * fs->cluster_size;
        memset(buf, 0, fs->cluster_size);
        if (!fs->spill_rd_open || fs->spill_rd_head != fs->spillhead[c]) {
            if (fs->spill_rd_open) { lfs2_file_close(fs->lfs, &fs->spill_rd_file); fs->spill_rd_open = 0; }
            char sp[FATLFS_PATH_MAX]; spill_name(sp, fs->spillhead[c]);
            if (lfs2_file_opencfg(fs->lfs, &fs->spill_rd_file, sp, LFS2_O_RDONLY, &fs->fc_spill_rd) >= 0) {
                fs->spill_rd_open = 1; fs->spill_rd_head = fs->spillhead[c];
            } else {
                return;  // temp missing -> zeros
            }
        }
        if (lfs2_file_seek(fs->lfs, &fs->spill_rd_file, off, LFS2_SEEK_SET) >= 0)
            lfs2_file_read(fs->lfs, &fs->spill_rd_file, buf, fs->cluster_size);
        return;
    }
    if (c < fs->cc2 && fs->owner[c].node >= 0) {
        fatlfs_node_t *n = &fs->committed[fs->owner[c].node];
        uint32_t off = fs->owner[c].idx * fs->cluster_size;
        memset(buf, 0, fs->cluster_size);
        lfs2_file_t fp;
        if (lfs2_file_opencfg(fs->lfs, &fp, n->path, LFS2_O_RDONLY, &fs->fc_rd) >= 0) {
            if (lfs2_file_seek(fs->lfs, &fp, off, LFS2_SEEK_SET) >= 0) {
                uint32_t want = fs->cluster_size;
                if (off < n->size && n->size - off < want) want = n->size - off;
                lfs2_file_read(fs->lfs, &fp, buf, want);
            }
            lfs2_file_close(fs->lfs, &fp);
        }
        return;
    }
    memset(buf, 0, fs->cluster_size);
}

static void read_cluster(fatlfs_t *fs, uint32_t c, uint8_t *buf) {
    if (c < fs->cc2 && fs->staging[c]) { memcpy(buf, fs->staging[c], fs->cluster_size); return; }
    read_cluster_base(fs, c, buf);
}

static uint8_t *stage_get_or_init(fatlfs_t *fs, uint32_t c) {
    if (c >= fs->cc2) return NULL;
    if (fs->staging[c]) return fs->staging[c];
    uint8_t *p = malloc(fs->cluster_size);
    if (!p) return NULL;
    read_cluster_base(fs, c, p);
    fs->staging[c] = p;
    fs->staged_bytes += fs->cluster_size;
    return p;
}

// ---------------------------------------------------------------------------
// FAT-region sector serve/apply: translate between the internal 28-bit chain
// representation and 16-bit on-disk FAT16 entries.
// ---------------------------------------------------------------------------

#define FAT_ENTRIES_PER_SEC (FAT_SECTOR_SIZE / 2)

static void serve_fat_sector(fatlfs_t *fs, uint32_t fatsec, uint8_t *buf) {
    uint32_t base = fatsec * FAT_ENTRIES_PER_SEC;
    for (uint32_t i = 0; i < FAT_ENTRIES_PER_SEC; i++) {
        uint32_t e = base + i;
        uint16_t v;
        if (e == 0) v = 0xFF00 | FAT_MEDIA_FIXED;        // 0xFFF8
        else if (e == 1) v = FAT16_EOC;                  // EOC / clean bits
        else if (e >= fs->cc2) v = 0;
        else {
            uint32_t iv = fs->fat[e] & FAT_ENTRY_MASK;
            if (iv == 0) v = 0;
            else if (iv == FAT_BAD) v = FAT16_BAD;
            else if (FAT_IS_EOC(iv) || iv >= fs->cc2) v = FAT16_EOC;
            else v = (uint16_t)iv;
        }
        fat_wr16(buf + i * 2, v);
    }
}

static void apply_fat_sector(fatlfs_t *fs, uint32_t fatsec, const uint8_t *buf) {
    uint32_t base = fatsec * FAT_ENTRIES_PER_SEC;
    for (uint32_t i = 0; i < FAT_ENTRIES_PER_SEC; i++) {
        uint32_t e = base + i;
        if (e < 2 || e >= fs->cc2) continue;
        uint16_t v = fat_rd16(buf + i * 2);
        uint32_t iv;
        if (v == 0) iv = FAT_FREE;
        else if (v == FAT16_BAD) iv = FAT_BAD;
        else if (v >= 0xFFF8) iv = FAT_EOC;
        else iv = v;   // out-of-range cluster numbers end chains in the walks
        fs->fat[e] = iv;
    }
}

// ---------------------------------------------------------------------------
// Large-file spill (bound RAM to staging_max)
// ---------------------------------------------------------------------------

static void spill_name(char *out, uint32_t head) { snprintf(out, FATLFS_PATH_MAX, SPILL_PREFIX "%u", (unsigned)head); }

static void spill_close(fatlfs_t *fs) {
    if (fs->spill_open) { lfs2_file_close(fs->lfs, &fs->spill_file); fs->spill_open = 0; }
}

static void spill_rd_close(fatlfs_t *fs) {
    if (fs->spill_rd_open) { lfs2_file_close(fs->lfs, &fs->spill_rd_file); fs->spill_rd_open = 0; }
}

// True if any cluster still marks this chain head's temp file as its only data
// source (an in-flight spilled file the host hasn't linked into the directory
// yet). Such temps must survive reconcile's cleanup pass.
static int spill_head_live(fatlfs_t *fs, uint32_t head) {
    for (uint32_t c = 2; c < fs->cc2; c++)
        if (fs->owner[c].node == -2 && fs->spillhead[c] == head) return 1;
    return 0;
}

// Reverse-walk FAT to find a cluster's chain head and logical index.
static uint32_t chain_head_of(fatlfs_t *fs, uint32_t c, uint32_t *idx_out, uint32_t *prev) {
    uint32_t head = c, idx = 0;
    uint32_t guard = fs->cc2 + 1;
    while (prev[head] != 0 && guard--) { head = prev[head]; idx++; }
    *idx_out = idx;
    return head;
}

// Spill non-head data clusters to per-chain temp lfs files to free RAM. Each
// spilled cluster is a flash write; on an IRQ-masking target a big overflow spilled
// in one go starves USB and freezes the UI. `budget` (0 = unlimited) caps how many
// clusters move per call so the caller can interleave USB servicing.
static void spill_pressure(fatlfs_t *fs, uint32_t budget) {
    uint32_t *prev = fs->prev;   // persistent scratch (see struct) - never fails here
    memset(prev, 0, fs->cc2 * sizeof(uint32_t));
    for (uint32_t x = 2; x < fs->cc2; x++) {
        uint32_t nx = fat_get(fs, x);
        if (nx >= 2 && nx < fs->cc2 && !FAT_IS_EOC(nx)) prev[nx] = x;
    }
    uint32_t moved = 0;
    for (uint32_t c = 2; c < fs->cc2 && fs->staged_bytes > fs->staging_max; c++) {
        if (!fs->staging[c]) continue;
        if (fs->dir_bytes[c]) continue;                           // never spill known dirs
        uint32_t idx, head = chain_head_of(fs, c, &idx, prev);
        if (idx == 0) continue;                                   // keep chain heads in RAM
        if (!fs->spill_open || fs->spill_head != head) {
            spill_close(fs);
            char sp[FATLFS_PATH_MAX]; spill_name(sp, head);
            if (lfs2_file_opencfg(fs->lfs, &fs->spill_file, sp, LFS2_O_WRONLY | LFS2_O_CREAT, &fs->fc_spill) < 0) continue;
            fs->spill_open = 1; fs->spill_head = head;
        }
        int wrote = 0;
        if (lfs2_file_seek(fs->lfs, &fs->spill_file, idx * fs->cluster_size, LFS2_SEEK_SET) >= 0) {
            lfs2_ssize_t w = lfs2_file_write(fs->lfs, &fs->spill_file, fs->staging[c], fs->cluster_size);
            wrote = (w == (lfs2_ssize_t)fs->cluster_size);
        }
        if (!wrote) break;   // lfs full / IO error: the staged copy is the ONLY copy -
                             // keep it, and stop (further spills will fail the same way)
        free(fs->staging[c]); fs->staging[c] = NULL;
        fs->staged_bytes -= fs->cluster_size;
        fs->owner[c].node = -2; fs->owner[c].idx = idx; fs->spillhead[c] = head; // spilled
        // (spill_close() below closes+syncs the temp file, so it is readable
        //  before control returns to the host / any subsequent read request)
        if (budget && ++moved >= budget) break;
    }
    spill_close(fs);
}

// ---------------------------------------------------------------------------
// Per-sector read / write dispatch
// ---------------------------------------------------------------------------

static void read_sector(fatlfs_t *fs, uint64_t lba, uint8_t *buf) {
    if (lba < fs->reserved_sectors) {
        if (lba == 0) memcpy(buf, fs->boot, FAT_SECTOR_SIZE);
        else memset(buf, 0, FAT_SECTOR_SIZE);
        return;
    }
    if (lba < fs->root_start) {
        uint32_t rel = (uint32_t)(lba - fs->reserved_sectors);
        serve_fat_sector(fs, rel % fs->fat_sectors, buf);
        return;
    }
    if (lba < fs->data_start) {   // fixed root directory region
        memcpy(buf, fs->root_bytes + (size_t)(lba - fs->root_start) * FAT_SECTOR_SIZE, FAT_SECTOR_SIZE);
        return;
    }
    uint32_t rel = (uint32_t)(lba - fs->data_start);
    uint32_t cluster = FAT_FIRST_DATA_CLUSTER + rel / fs->spc;
    uint32_t secoff = (rel % fs->spc) * FAT_SECTOR_SIZE;
    if (cluster >= fs->cc2) { memset(buf, 0, FAT_SECTOR_SIZE); return; }
    read_cluster(fs, cluster, fs->clusbuf);
    memcpy(buf, fs->clusbuf + secoff, FAT_SECTOR_SIZE);
}

static int write_sector(fatlfs_t *fs, uint64_t lba, const uint8_t *buf) {
    if (lba < fs->reserved_sectors) return FATLFS_OK;     // boot sector: accept, ignore
    if (lba < fs->root_start) {
        uint32_t rel = (uint32_t)(lba - fs->reserved_sectors);
        apply_fat_sector(fs, rel % fs->fat_sectors, buf);
        return FATLFS_OK;
    }
    if (lba < fs->data_start) {   // root region: authoritative, no staging
        memcpy(fs->root_bytes + (size_t)(lba - fs->root_start) * FAT_SECTOR_SIZE, buf, FAT_SECTOR_SIZE);
        fs->root_dirty = 1;
        return FATLFS_OK;
    }
    uint32_t rel = (uint32_t)(lba - fs->data_start);
    uint32_t cluster = FAT_FIRST_DATA_CLUSTER + rel / fs->spc;
    uint32_t secoff = (rel % fs->spc) * FAT_SECTOR_SIZE;
    if (cluster >= fs->cc2) return FATLFS_OK;
    uint8_t *st = stage_get_or_init(fs, cluster);
    if (!st) return FATLFS_ERR_NOMEM;
    memcpy(st + secoff, buf, FAT_SECTOR_SIZE);
    if (!fs->no_inline_spill && fs->staged_bytes > fs->staging_max) spill_pressure(fs, 0);
    return FATLFS_OK;
}

// ---------------------------------------------------------------------------
// Directory-entry name decode (8.3 + LFN)
// ---------------------------------------------------------------------------

static void decode_short(const uint8_t *e, char *out) {
    char base[9], ext[4];
    int bn = 0, en = 0;
    for (int i = 0; i < 8; i++) if (e[i] != ' ') base[bn++] = e[i]; else break;
    base[bn] = 0;
    for (int i = 8; i < 11; i++) if (e[i] != ' ') ext[en++] = e[i]; else break;
    ext[en] = 0;
    if (bn && (uint8_t)base[0] == DIRENT_KANJI_E5) base[0] = (char)0xE5;
    if (e[DIR_NTRes] & 0x08) for (int i = 0; i < bn; i++) base[i] = (char)tolower((unsigned char)base[i]);
    if (e[DIR_NTRes] & 0x10) for (int i = 0; i < en; i++) ext[i] = (char)tolower((unsigned char)ext[i]);
    if (en) snprintf(out, FATLFS_LFN_MAX + 1, "%s.%s", base, ext);
    else    snprintf(out, FATLFS_LFN_MAX + 1, "%s", base);
}

// ---------------------------------------------------------------------------
// Parse the FAT directory tree from dir clusters into a node vector.
// ---------------------------------------------------------------------------

typedef struct { fatlfs_node_t *v; int n, cap; } nodevec;

static int nv_push(nodevec *nv, const fatlfs_node_t *node) {
    if (nv->n == nv->cap) {
        int nc = nv->cap ? nv->cap * 2 : 16;
        fatlfs_node_t *nv2 = realloc(nv->v, nc * sizeof(fatlfs_node_t));
        if (!nv2) return FATLFS_ERR_NOMEM;
        nv->v = nv2; nv->cap = nc;
    }
    nv->v[nv->n++] = *node;
    return 0;
}

// Per-level parse state, heap-allocated: parse_dir recurses to directory depth
// and the RP2 main stack is only 8 KB total. lfn is sized for the maximum a
// 20-entry LFN chain can address (260 units, > FATLFS_LFN_MAX) and name for
// full 3-byte UTF-8 expansion of every unit; both were previously stack arrays
// that a long or non-ASCII filename overflowed. The cluster buffer follows the
// struct (it can't share fs->clusbuf - recursion would clobber the parent's
// cluster data).
typedef struct {
    uint16_t lfn[LFN_MAX_UNITS];
    char     name[LFN_MAX_UNITS * 3 + 1];
    fatlfs_node_t node;
} parse_scratch_t;

static int parse_dir(fatlfs_t *fs, uint32_t start, const char *prefix,
                     nodevec *nv, uint8_t *visited, uint8_t *dircls);

// Directory-entry scan state, shared between the fixed root region (one flat
// buffer) and cluster chains (16 entries per 512 B cluster, LFN runs spanning
// cluster boundaries).
typedef struct {
    parse_scratch_t *s;
    const char *prefix;
    nodevec *nv;
    uint8_t *visited, *dircls;
    int have_lfn, lfn_len;
    uint8_t lfn_csum;
    int done;              // hit DIRENT_END: no further entries in this directory
} dirscan_t;

// Process nents 32-byte entries from buf; recurses into subdirectories.
static int scan_dir_entries(fatlfs_t *fs, dirscan_t *sc, const uint8_t *buf, uint32_t nents) {
    parse_scratch_t *s = sc->s;
    for (uint32_t i = 0; i < nents; i++) {
        const uint8_t *e = buf + i * FAT_DIRENT_SIZE;
        uint8_t b0 = e[0];
        if (b0 == DIRENT_END) { sc->done = 1; return 0; }
        if (b0 == DIRENT_FREE) { sc->have_lfn = 0; continue; }
        uint8_t attr = e[DIR_Attr];
        if ((attr & ATTR_LONG_MASK) == ATTR_LONG_NAME) {
            uint8_t ord = e[LDIR_Ord];
            int last = (ord & LDIR_LAST_MASK) != 0;
            int seq = ord & 0x1F;
            if (seq < 1 || seq > 20) { sc->have_lfn = 0; continue; }
            if (last) { sc->have_lfn = 1; sc->lfn_csum = e[LDIR_Chksum]; sc->lfn_len = seq * LFN_CHARS_PER_ENTRY; }
            if (!sc->have_lfn) continue;
            uint16_t *dst = &s->lfn[(seq - 1) * LFN_CHARS_PER_ENTRY];
            static const int offs[13] = {1,3,5,7,9, 14,16,18,20,22,24, 28,30};
            for (int k = 0; k < 13; k++) dst[k] = fat_rd16(e + offs[k]);
            continue;
        }
        if (attr & ATTR_VOLUME_ID) { sc->have_lfn = 0; continue; }  // volume label

        uint8_t shortname[11]; memcpy(shortname, e, 11);
        if (sc->have_lfn && sc->lfn_csum == fat_lfn_checksum(shortname)) {
            char *p = s->name;
            for (int k = 0; k < sc->lfn_len; k++) { if (s->lfn[k] == 0) break; put_utf8(&p, s->lfn[k]); }
            *p = 0;
        } else {
            decode_short(e, s->name);
        }
        sc->have_lfn = 0;

        if (s->name[0] == '.' && (s->name[1] == 0 || (s->name[1] == '.' && s->name[2] == 0))) continue;

        memset(&s->node, 0, sizeof s->node);
        path_join(s->node.path, sc->prefix, s->name);
        s->node.first_cluster = fat_dirent_cluster(e);
        s->node.is_dir = (attr & ATTR_DIRECTORY) ? 1 : 0;
        if (s->node.is_dir) {
            int r = nv_push(sc->nv, &s->node); if (r) return r;
            // Recurse only into real chains: first_cluster 0 would otherwise be
            // taken for the root region and loop forever.
            if (s->node.first_cluster >= 2) {
                r = parse_dir(fs, s->node.first_cluster, s->node.path, sc->nv, sc->visited, sc->dircls);
                if (r) return r;
            }
        } else {
            s->node.size = fat_rd32(e + DIR_FileSize);
            int r = nv_push(sc->nv, &s->node); if (r) return r;
        }
    }
    return 0;
}

// Parse a directory into the node vector. start == 0 parses the fixed FAT16
// root region; otherwise the cluster chain starting at `start`.
// dircls: set to 1 for every cluster that belongs to a directory chain.
static int parse_dir(fatlfs_t *fs, uint32_t start, const char *prefix,
                     nodevec *nv, uint8_t *visited, uint8_t *dircls) {
    parse_scratch_t *s = malloc(sizeof *s + fs->cluster_size);
    if (!s) return FATLFS_ERR_NOMEM;
    dirscan_t sc = { .s = s, .prefix = prefix, .nv = nv, .visited = visited, .dircls = dircls };
    int r = 0;
    if (start == 0) {
        r = scan_dir_entries(fs, &sc, fs->root_bytes, fs->root_entries);
    } else {
        uint8_t *cbuf = (uint8_t *)(s + 1);
        uint32_t c = start;
        uint32_t guard = fs->cc2 + 1;
        while (c >= 2 && c < fs->cc2 && guard--) {
            if (visited[c]) break;
            visited[c] = 1; dircls[c] = 1;
            read_cluster(fs, c, cbuf);
            r = scan_dir_entries(fs, &sc, cbuf, fs->cluster_size / FAT_DIRENT_SIZE);
            if (r || sc.done) break;
            uint32_t nxt = fat_get(fs, c);
            if (nxt < 2 || nxt >= fs->cc2 || FAT_IS_EOC(nxt)) break;
            c = nxt;
        }
    }
    free(s);
    return r;
}

// ---------------------------------------------------------------------------
// Reconciliation helpers
// ---------------------------------------------------------------------------

// Match a new node to a committed node: same type and (fc identity, else path).
static int find_prev(fatlfs_t *fs, const fatlfs_node_t *nn) {
    for (int i = 0; i < fs->committed_n; i++) {
        fatlfs_node_t *p = &fs->committed[i];
        if (p->is_dir != nn->is_dir) continue;
        if (nn->first_cluster != 0 && p->first_cluster == nn->first_cluster) return i;
    }
    if (nn->first_cluster == 0 && !nn->is_dir) {
        for (int i = 0; i < fs->committed_n; i++) {
            fatlfs_node_t *p = &fs->committed[i];
            if (!p->is_dir && p->first_cluster == 0 && strcmp(p->path, nn->path) == 0) return i;
        }
    }
    return -1;
}

// Length of a FAT chain (number of clusters) starting at `first`.
static uint32_t chain_len(fatlfs_t *fs, uint32_t first) {
    uint32_t n = 0, c = first, guard = fs->cc2 + 1;
    while (c >= 2 && c < fs->cc2 && guard--) {
        n++;
        uint32_t nxt = fat_get(fs, c);
        if (nxt < 2 || nxt >= fs->cc2 || FAT_IS_EOC(nxt)) break;
        c = nxt;
    }
    return n;
}

// Commit a file's data into its lfs file, reconstructing every cluster from its
// true current source (staging > spill > existing-lfs). This is safe to run at a
// NON-barrier point: if the directory-entry size and the FAT chain disagree
// (a write in progress), we keep the larger FAT-chain extent so no tail data is
// lost; a later, coherent reconcile trims it to the exact size.
static int flush_file_data(fatlfs_t *fs, const fatlfs_node_t *f) {
    uint32_t nclus = chain_len(fs, f->first_cluster);
    uint32_t ceil_clus = (f->size + fs->cluster_size - 1) / fs->cluster_size;
    int coherent = (nclus == ceil_clus);
    uint64_t eff = coherent ? f->size : (uint64_t)nclus * fs->cluster_size;

    lfs2_file_t fp;
    int r = lfs2_file_opencfg(fs->lfs, &fp, f->path, LFS2_O_RDWR | LFS2_O_CREAT, &fs->fc_wr);
    if (r < 0) return r;
    uint8_t *buf = malloc(fs->cluster_size);
    if (!buf) { lfs2_file_close(fs->lfs, &fp); return FATLFS_ERR_NOMEM; }

    uint32_t idx = 0, c = f->first_cluster, guard = fs->cc2 + 1;
    while (c >= 2 && c < fs->cc2 && guard--) {
        uint64_t off = (uint64_t)idx * fs->cluster_size;
        if (off >= eff) break;
        uint32_t n = fs->cluster_size;
        if (eff - off < n) n = (uint32_t)(eff - off);
        // Fast path: this cluster is already the same file's data at the same
        // offset in lfs (identity preserved across a rename/move) -> leave it.
        int already = !fs->staging[c] && fs->owner[c].node >= 0
                      && fs->committed[fs->owner[c].node].first_cluster == f->first_cluster
                      && fs->owner[c].idx == idx;
        if (!already) {
            read_cluster(fs, c, buf);   // staging > dir > spill(node==-2) > lfs > zero
            if (lfs2_file_seek(fs->lfs, &fp, off, LFS2_SEEK_SET) < 0 ||
                lfs2_file_write(fs->lfs, &fp, buf, n) < 0) {
                free(buf); lfs2_file_close(fs->lfs, &fp); return FATLFS_ERR_IO;
            }
        }
        idx++;
        uint32_t nxt = fat_get(fs, c);
        if (nxt < 2 || nxt >= fs->cc2 || FAT_IS_EOC(nxt)) break;
        c = nxt;
    }
    free(buf);
    r = lfs2_file_truncate(fs->lfs, &fp, (lfs2_off_t)eff);
    int rc = lfs2_file_close(fs->lfs, &fp);
    // The spill temp (if any) for this chain is now fully absorbed into the file.
    // Close the kept-open spill reader first so the temp isn't removed out from under it.
    if (f->first_cluster) {
        spill_rd_close(fs);
        char sp[FATLFS_PATH_MAX]; spill_name(sp, f->first_cluster); lfs2_remove(fs->lfs, sp);
    }
    return (r < 0) ? r : rc;
}

// depth-sort index arrays
static nodevec *g_sort_src; // for qsort comparators (single-threaded)
static int cmp_deep(const void *a, const void *b) {
    int ia = *(const int *)a, ib = *(const int *)b;
    return path_depth(g_sort_src->v[ib].path) - path_depth(g_sort_src->v[ia].path);
}
static int cmp_shallow(const void *a, const void *b) {
    int ia = *(const int *)a, ib = *(const int *)b;
    return path_depth(g_sort_src->v[ia].path) - path_depth(g_sort_src->v[ib].path);
}

// ---------------------------------------------------------------------------
// OS "trash" filtering (macOS Finder / Windows sidecar files)
// ---------------------------------------------------------------------------

static int name_is_trash(const char *name) {
    if (name[0] == '.' && name[1] == '_') return 1;   // ._* AppleDouble sidecars
    static const char *const trash[] = {
        ".DS_Store", ".Spotlight-V100", ".Trashes", ".fseventsd",
        ".TemporaryItems", ".DocumentRevisions-V100", ".apdisk",
        ".VolumeIcon.icns", ".AppleDouble", ".AppleDB", ".AppleDesktop",
        "__MACOSX", "Thumbs.db", "desktop.ini", "$RECYCLE.BIN",
        "System Volume Information", ".Trash-1000", NULL,
    };
    for (int i = 0; trash[i]; i++) if (strcmp(name, trash[i]) == 0) return 1;
    return 0;
}

// True if any component of the path is a trash name (so a trash *directory*
// drops its whole subtree, not just the directory entry).
static int path_is_trash(const char *path) {
    const char *seg = path;
    for (;;) {
        const char *slash = strchr(seg, '/');
        size_t len = slash ? (size_t)(slash - seg) : strlen(seg);
        char comp[64];
        if (len >= sizeof comp) len = sizeof comp - 1;
        memcpy(comp, seg, len); comp[len] = 0;
        if (name_is_trash(comp)) return 1;
        if (!slash) return 0;
        seg = slash + 1;
    }
}

// ---------------------------------------------------------------------------
// The flush barrier: commit staged state into LittleFS.
// ---------------------------------------------------------------------------

static int reconcile(fatlfs_t *fs) {
    int rc = 0;
    nodevec nv = {0};
    uint8_t *visited = calloc(fs->cc2, 1);
    uint8_t *dircls  = calloc(fs->cc2, 1);
    uint8_t *datacls = calloc(fs->cc2, 1);   // file-data clusters reachable from the dir tree
    if (!visited || !dircls || !datacls) { rc = FATLFS_ERR_NOMEM; goto done; }

    rc = parse_dir(fs, 0, "", &nv, visited, dircls);   // 0 = fixed root region
    if (rc) goto done;

    // Mark every file-data cluster reachable from a directory entry (committed
    // files AND to-be-dropped trash - anything the host has linked into the tree).
    // What's left with staging but unmarked is an in-flight orphan: a new file
    // whose data + FAT chain exist but whose directory entry doesn't point at them
    // yet (first_cluster still 0). We must NOT drop those on an incremental flush;
    // the host will write the entry and a later flush commits it. Walk before the
    // trash drop below so trash clusters are counted (and thus reclaimed).
    for (int i = 0; i < nv.n; i++) {
        if (nv.v[i].is_dir) continue;
        uint32_t c = nv.v[i].first_cluster, g = fs->cc2 + 1;
        while (c >= 2 && c < fs->cc2 && g--) {
            datacls[c] = 1;
            uint32_t nx = fat_get(fs, c);
            if (nx < 2 || nx >= fs->cc2 || FAT_IS_EOC(nx)) break;
            c = nx;
        }
    }

    // Quietly drop OS turd files: never store them in LittleFS. They remain
    // visible in the transient FAT view (the host just wrote them) until the
    // next power-cycle, exactly as on a real removable drive.
    if (!fs->keep_trash) {
        int w = 0;
        for (int i = 0; i < nv.n; i++)
            if (!path_is_trash(nv.v[i].path)) nv.v[w++] = nv.v[i];
        nv.n = w;
    }


    // Map each new node to a prev node (-1 = new). Mark matched prevs.
    int *match = malloc((nv.n ? nv.n : 1) * sizeof(int));
    uint8_t *prev_used = calloc(fs->committed_n ? fs->committed_n : 1, 1);
    if (!match || !prev_used) { rc = FATLFS_ERR_NOMEM; free(match); free(prev_used); goto done; }
    for (int i = 0; i < nv.n; i++) {
        match[i] = find_prev(fs, &nv.v[i]);
        if (match[i] >= 0) prev_used[match[i]] = 1;
    }

    // (a) detach relocated survivors to temp names (deepest-first). Temp names are
    // keyed by the node's chain head - deterministic - so a retry after a pass that
    // failed part-way can recognise an already-detached node instead of wedging on
    // ENOENT and stranding its data under a hidden temp name forever.
    g_sort_src = &nv;
    int *order = malloc((nv.n ? nv.n : 1) * sizeof(int));
    char **tmpname = calloc(nv.n ? nv.n : 1, sizeof(char *)); // temp name per new-node index (or NULL)
    if (!order || !tmpname) { rc = FATLFS_ERR_NOMEM; goto done2; }
    for (int i = 0; i < nv.n; i++) order[i] = i;
    qsort(order, nv.n, sizeof(int), cmp_deep);
    for (int oi = 0; oi < nv.n; oi++) {
        int i = order[oi];
        if (match[i] < 0) continue;
        const char *oldp = fs->committed[match[i]].path;
        if (strcmp(oldp, nv.v[i].path) == 0) continue;   // unchanged path
        char tmp[40];
        snprintf(tmp, sizeof tmp, MV_PREFIX "%u", (unsigned)nv.v[i].first_cluster);
        int r = lfs2_rename(fs->lfs, oldp, tmp);
        if (r == LFS2_ERR_NOENT) {
            // Source gone: an earlier pass that failed later on either already
            // detached it (temp exists) or fully landed it (final path exists).
            struct lfs2_info st;
            if (lfs2_stat(fs->lfs, tmp, &st) >= 0) r = 0;
            else if (lfs2_stat(fs->lfs, nv.v[i].path, &st) >= 0) { r = 0; tmp[0] = 0; }
        }
        if (r < 0) { rc = r; goto done2; }
        if (tmp[0]) {
            tmpname[i] = malloc(strlen(tmp) + 1);
            if (!tmpname[i]) { rc = FATLFS_ERR_NOMEM; goto done2; }
            strcpy(tmpname[i], tmp);
        }
    }

    // (b) delete prev nodes absent from new (deepest-first).
    {
        int *dord = malloc((fs->committed_n ? fs->committed_n : 1) * sizeof(int));
        nodevec cv = { fs->committed, fs->committed_n, fs->committed_n };
        g_sort_src = &cv;
        for (int i = 0; i < fs->committed_n; i++) dord[i] = i;
        qsort(dord, fs->committed_n, sizeof(int), cmp_deep);
        for (int oi = 0; oi < fs->committed_n; oi++) {
            int i = dord[oi];
            if (prev_used[i]) continue;
            // Same-path same-type replacement by a brand-new node (the host's
            // delete+recreate save pattern): do NOT delete first. flush_file_data
            // overwrites the file in place and littlefs commits that copy-on-write
            // at close, so either the old or the new content is always on flash;
            // deleting here would open a power-loss window with neither. (mkdir
            // below treats an existing dir as success, covering the dir case.
            // Relocated nodes - match[j] >= 0 - land by rename, which replaces the
            // old occupant atomically, so those still delete early as before.)
            int reused = 0;
            for (int j = 0; j < nv.n; j++) {
                if (match[j] < 0 && nv.v[j].is_dir == fs->committed[i].is_dir &&
                    strcmp(nv.v[j].path, fs->committed[i].path) == 0) { reused = 1; break; }
            }
            if (reused) continue;
            lfs2_remove(fs->lfs, fs->committed[i].path);   // ok if already gone
        }
        free(dord);
        g_sort_src = &nv;
    }

    // (c) create brand-new directories (shallowest-first).
    qsort(order, nv.n, sizeof(int), cmp_shallow);
    for (int oi = 0; oi < nv.n; oi++) {
        int i = order[oi];
        if (match[i] >= 0 || !nv.v[i].is_dir) continue;
        int r = lfs2_mkdir(fs->lfs, nv.v[i].path);
        if (r < 0 && r != LFS2_ERR_EXIST) { rc = r; goto done2; }
    }

    // (d) re-attach temps to final paths (shallowest-first).
    for (int oi = 0; oi < nv.n; oi++) {
        int i = order[oi];
        if (!tmpname[i]) continue;
        int r = lfs2_rename(fs->lfs, tmpname[i], nv.v[i].path);
        if (r < 0) { rc = r; goto done2; }
    }

    // (e) create new empty files (parents now exist), then (f) flush file data.
    for (int oi = 0; oi < nv.n; oi++) {
        int i = order[oi];
        if (nv.v[i].is_dir) continue;
        int r = flush_file_data(fs, &nv.v[i]);
        if (r < 0) { rc = r; goto done2; }
    }

    // Commit snapshot: replace committed with new nodes.
    free(fs->committed);
    fs->committed = malloc((nv.n ? nv.n : 1) * sizeof(fatlfs_node_t));
    if (!fs->committed) { rc = FATLFS_ERR_NOMEM; fs->committed_n = 0; goto done2; }
    memcpy(fs->committed, nv.v, nv.n * sizeof(fatlfs_node_t));
    fs->committed_n = nv.n;

    // Rebuild owner index from committed file chains. Preserve spilled clusters
    // (node == -2): those belong to an in-flight file not yet in the directory, and
    // their data lives only in a temp lfs file keyed by spillhead. Wiping the marker
    // here would orphan that data and lose a large file mid-copy. The committed-chain
    // loop below overrides -2 for any cluster that has now been committed.
    for (uint32_t c = 0; c < fs->cc2; c++) {
        if (fs->owner[c].node == -2) continue;
        fs->owner[c].node = -1; fs->owner[c].idx = 0; fs->spillhead[c] = 0;
    }
    for (int i = 0; i < fs->committed_n; i++) {
        if (fs->committed[i].is_dir) continue;
        uint32_t idx = 0, c = fs->committed[i].first_cluster, guard = fs->cc2 + 1;
        while (c >= 2 && c < fs->cc2 && guard--) {
            fs->owner[c].node = i; fs->owner[c].idx = idx++;
            uint32_t nxt = fat_get(fs, c);
            if (nxt < 2 || nxt >= fs->cc2 || FAT_IS_EOC(nxt)) break;
            c = nxt;
        }
    }

    // Clean unclaimed spill temps (aborted writes). Runs AFTER the owner rebuild
    // so owner==-2 markers are exact: a temp still referenced by one holds the
    // ONLY copy of an in-flight orphan's data and must survive. Names we generate
    // are short (prefix + u32); anything longer merely matches the prefix and is
    // left alone rather than truncated into deleting the wrong path.
    {
        lfs2_dir_t d;
        if (lfs2_dir_open(fs->lfs, &d, "/") >= 0) {
            struct lfs2_info inf;
            char victims[16][40]; int nvic = 0;
            while (lfs2_dir_read(fs->lfs, &d, &inf) > 0 && nvic < 16) {
                if (strncmp(inf.name, SPILL_PREFIX, strlen(SPILL_PREFIX)) != 0) continue;
                size_t len = strlen(inf.name);
                if (len >= sizeof victims[0]) continue;
                uint32_t head = (uint32_t)strtoul(inf.name + strlen(SPILL_PREFIX), NULL, 10);
                if (spill_head_live(fs, head)) continue;
                memcpy(victims[nvic++], inf.name, len + 1);
            }
            lfs2_dir_close(fs->lfs, &d);
            for (int i = 0; i < nvic; i++) lfs2_remove(fs->lfs, victims[i]);
        }
    }

    // Persist current directory-cluster contents; drop clusters no longer dirs.
    for (uint32_t c = 2; c < fs->cc2; c++) {
        if (dircls[c]) {
            if (!fs->dir_bytes[c]) fs->dir_bytes[c] = malloc(fs->cluster_size);
            if (fs->dir_bytes[c]) read_cluster(fs, c, fs->dir_bytes[c]);
        } else if (fs->dir_bytes[c]) {
            free(fs->dir_bytes[c]); fs->dir_bytes[c] = NULL;
        }
    }

done2:
    if (tmpname) for (int i = 0; i < nv.n; i++) free(tmpname[i]);
    free(match); free(prev_used); free(order); free(tmpname);
done:
    // Reclaim staging only after a SUCCESSFUL commit: durable file data and
    // captured directory clusters (held in dir_bytes) can go; in-flight orphans -
    // file data the host wrote but hasn't linked into the directory yet - stay
    // staged so an incremental flush doesn't lose the file being written.
    // On FAILURE everything stays staged and dir_bytes stays untouched: the
    // host's view of the volume must not change because our lfs writes failed,
    // and a later flush retries the whole commit from the same staged state.
    if (rc == 0) {
        fs->staged_bytes = 0;
        fs->root_dirty = 0;   // root region changes are committed too
        for (uint32_t c = 0; c < fs->cc2; c++) {
            if (!fs->staging[c]) continue;
            if (datacls[c] || dircls[c]) {
                free(fs->staging[c]); fs->staging[c] = NULL;
            } else {
                fs->staged_bytes += fs->cluster_size;   // orphan: retain for next flush
            }
        }
    }
    free(nv.v); free(visited); free(dircls); free(datacls);
    return rc;
}

// Rebuild committed snapshot + owner index + persistent dir_bytes from the
// current in-RAM FAT/dir state (used after the encoder builds an initial view).
static int build_snapshot(fatlfs_t *fs) {
    nodevec nv = {0};
    uint8_t *visited = calloc(fs->cc2, 1);
    uint8_t *dircls  = calloc(fs->cc2, 1);
    if (!visited || !dircls) { free(visited); free(dircls); return FATLFS_ERR_NOMEM; }
    int rc = parse_dir(fs, 0, "", &nv, visited, dircls);   // 0 = fixed root region
    if (rc) { free(nv.v); free(visited); free(dircls); return rc; }
    free(fs->committed);
    fs->committed = malloc((nv.n ? nv.n : 1) * sizeof(fatlfs_node_t));
    if (!fs->committed) { free(nv.v); free(visited); free(dircls); return FATLFS_ERR_NOMEM; }
    memcpy(fs->committed, nv.v, nv.n * sizeof(fatlfs_node_t));
    fs->committed_n = nv.n;
    for (uint32_t c = 0; c < fs->cc2; c++) { fs->owner[c].node = -1; fs->owner[c].idx = 0; fs->spillhead[c] = 0; }
    for (int i = 0; i < fs->committed_n; i++) {
        if (fs->committed[i].is_dir) continue;
        uint32_t idx = 0, c = fs->committed[i].first_cluster, guard = fs->cc2 + 1;
        while (c >= 2 && c < fs->cc2 && guard--) {
            fs->owner[c].node = i; fs->owner[c].idx = idx++;
            uint32_t nxt = fat_get(fs, c);
            if (nxt < 2 || nxt >= fs->cc2 || FAT_IS_EOC(nxt)) break;
            c = nxt;
        }
    }
    free(nv.v); free(visited); free(dircls);
    return 0;
}

// ---------------------------------------------------------------------------
// LittleFS -> FAT encoder (present existing lfs content as a populated volume)
// ---------------------------------------------------------------------------

static uint32_t alloc_cluster(fatlfs_t *fs) {
    for (uint32_t c = fs->alloc_hint; c < fs->cc2; c++) {
        if (fs->fat[c] == FAT_FREE) { fs->fat[c] = FAT_EOC; fs->alloc_hint = c + 1; return c; }
    }
    for (uint32_t c = 2; c < fs->alloc_hint && c < fs->cc2; c++) {
        if (fs->fat[c] == FAT_FREE) { fs->fat[c] = FAT_EOC; return c; }
    }
    return 0;  // full
}

// first == 0 writes the fixed FAT16 root region; otherwise a cluster chain.
typedef struct { fatlfs_t *fs; uint32_t first, cur, off; int root; } dirwriter;

static int dw_start(dirwriter *dw, fatlfs_t *fs, uint32_t fixed_first) {
    dw->fs = fs;
    dw->off = 0;
    dw->root = (fixed_first == 0);
    if (dw->root) {
        dw->first = dw->cur = 0;
        memset(fs->root_bytes, 0, (size_t)fs->root_sectors * FAT_SECTOR_SIZE);
        return 0;
    }
    dw->first = dw->cur = fixed_first;
    fs->fat[dw->cur] = FAT_EOC;
    if (!fs->dir_bytes[dw->cur]) fs->dir_bytes[dw->cur] = calloc(1, fs->cluster_size);
    else memset(fs->dir_bytes[dw->cur], 0, fs->cluster_size);
    return fs->dir_bytes[dw->cur] ? 0 : FATLFS_ERR_NOMEM;
}

static int dw_put(dirwriter *dw, const uint8_t *ent) {
    fatlfs_t *fs = dw->fs;
    if (dw->root) {
        // The FAT16 root cannot grow: fail loudly when its fixed capacity is
        // exhausted (raise cfg.root_entries if a tree legitimately needs more).
        if (dw->off + FAT_DIRENT_SIZE > fs->root_entries * FAT_DIRENT_SIZE) return FATLFS_ERR_NOMEM;
        memcpy(fs->root_bytes + dw->off, ent, FAT_DIRENT_SIZE);
        dw->off += FAT_DIRENT_SIZE;
        return 0;
    }
    if (dw->off + FAT_DIRENT_SIZE > fs->cluster_size) {
        uint32_t nc = alloc_cluster(fs);
        if (!nc) return FATLFS_ERR_NOMEM;
        fs->fat[dw->cur] = nc; fs->fat[nc] = FAT_EOC;
        if (!fs->dir_bytes[nc]) fs->dir_bytes[nc] = calloc(1, fs->cluster_size);
        else memset(fs->dir_bytes[nc], 0, fs->cluster_size);
        if (!fs->dir_bytes[nc]) return FATLFS_ERR_NOMEM;
        dw->cur = nc; dw->off = 0;
    }
    memcpy(fs->dir_bytes[dw->cur] + dw->off, ent, FAT_DIRENT_SIZE);
    dw->off += FAT_DIRENT_SIZE;
    return 0;
}

static int short_valid(int c) {
    return isalnum(c) || strchr("$%'-_@~`!(){}^#&", c) != NULL;
}

static void gen_short(const char *name, uint8_t out[11], char used[][11], int *nused) {
    const char *dot = strrchr(name, '.');
    char base[64], ext[8]; int bn = 0, en = 0;
    for (const char *p = name; *p && (dot ? p < dot : 1) && bn < 63; p++) {
        if (*p == ' ' || *p == '.') continue;
        base[bn++] = short_valid((unsigned char)*p) ? (char)toupper((unsigned char)*p) : '_';
    }
    if (dot) for (const char *p = dot + 1; *p && en < 3; p++)
        ext[en++] = short_valid((unsigned char)*p) ? (char)toupper((unsigned char)*p) : '_';
    base[bn] = 0; ext[en] = 0;
    if (bn == 0) { base[0] = '_'; bn = 1; base[1] = 0; }

    for (int n = 1; n < 1000000; n++) {
        char num[8]; int nl = snprintf(num, sizeof num, "~%d", n);
        int keep = 8 - nl; if (keep > bn) keep = bn;
        memset(out, ' ', 11);
        memcpy(out, base, keep);
        memcpy(out + keep, num, nl);
        memcpy(out + 8, ext, en);
        int clash = 0;
        for (int i = 0; i < *nused; i++) if (memcmp(used[i], out, 11) == 0) { clash = 1; break; }
        if (!clash) {
            // Table full (>SHORT_TABLE_MAX entries in one dir): stop recording rather
            // than write past it. Later names risk duplicate 8.3 aliases, but hosts
            // resolve by LFN.
            if (*nused < SHORT_TABLE_MAX) { memcpy(used[*nused], out, 11); (*nused)++; }
            return;
        }
    }
}

static int emit_entry(dirwriter *dw, const char *name, int is_dir,
                      uint32_t first_cluster, uint32_t size,
                      char used[][11], int *nused) {
    uint8_t sh[11];
    gen_short(name, sh, used, nused);
    uint8_t csum = fat_lfn_checksum(sh);

    // UTF-16 name, NUL-terminated then 0xFFFF padded to a 13-multiple.
    uint16_t u16[FATLFS_LFN_MAX + 16]; int ulen = 0;
    const char *p = name;
    while (ulen < FATLFS_LFN_MAX) { uint16_t u = next_utf16(&p); u16[ulen++] = u; if (u == 0) break; }
    if (ulen == 0 || u16[ulen - 1] != 0) u16[ulen++] = 0;
    int nlfn = (ulen + 12) / 13;
    for (int t = ulen; t < nlfn * 13; t++) u16[t] = 0xFFFF;

    const int offs[13] = {1,3,5,7,9, 14,16,18,20,22,24, 28,30};
    for (int seq = nlfn; seq >= 1; seq--) {
        uint8_t e[FAT_DIRENT_SIZE]; memset(e, 0, sizeof e);
        e[LDIR_Ord] = (uint8_t)(seq | (seq == nlfn ? LDIR_LAST_MASK : 0));
        e[LDIR_Attr] = ATTR_LONG_NAME; e[LDIR_Chksum] = csum;
        const uint16_t *chunk = &u16[(seq - 1) * 13];
        for (int k = 0; k < 13; k++) fat_wr16(e + offs[k], chunk[k]);
        int r = dw_put(dw, e); if (r) return r;
    }
    uint8_t e[FAT_DIRENT_SIZE]; memset(e, 0, sizeof e);
    memcpy(e, sh, 11);
    e[DIR_Attr] = is_dir ? ATTR_DIRECTORY : ATTR_ARCHIVE;
    fat_dirent_set_cluster(e, first_cluster);
    fat_wr32(e + DIR_FileSize, is_dir ? 0 : size);
    return dw_put(dw, e);
}

// Per-level encode state, heap-allocated: encode_dir recurses to directory depth
// and its old stack frame (8.3 uniqueness table + two path buffers + lfs2_info)
// was ~4 KB per level - two nested directories overran the RP2's 8 KB stack.
typedef struct {
    char used[SHORT_TABLE_MAX][11];
    char op[FATLFS_PATH_MAX];
    char childpath[FATLFS_PATH_MAX];
    struct lfs2_info info;
} encode_scratch_t;

// Recursively encode an lfs directory (lpath, no trailing slash; "" = root).
static int encode_dir(fatlfs_t *fs, const char *lpath, uint32_t this_cluster, uint32_t parent_cluster) {
    dirwriter dw;
    int r = dw_start(&dw, fs, this_cluster);
    if (r) return r;
    encode_scratch_t *s = malloc(sizeof *s);
    // Two passes so we can recurse without keeping many lfs dir handles open.
    // Collect children first.
    struct { char name[FATLFS_LFN_MAX + 1]; uint32_t size; uint8_t is_dir; } *kids = NULL;
    int nused = 0, nk = 0, capk = 0;
    if (!s) return FATLFS_ERR_NOMEM;

    if (this_cluster != 0) {   // the fixed root region carries no "."/".."
        uint8_t e[FAT_DIRENT_SIZE];
        // "." -> this directory
        memset(e, 0, sizeof e); memset(e, ' ', 11); e[0] = '.';
        e[DIR_Attr] = ATTR_DIRECTORY; fat_dirent_set_cluster(e, dw.first);
        if ((r = dw_put(&dw, e))) goto out;
        // ".." -> parent (0 when the parent is the root)
        memset(e, 0, sizeof e); memset(e, ' ', 11); e[0] = '.'; e[1] = '.';
        e[DIR_Attr] = ATTR_DIRECTORY;
        fat_dirent_set_cluster(e, parent_cluster);
        if ((r = dw_put(&dw, e))) goto out;
    } else {   // fixed root: emit the volume-label entry so hosts show the drive
        // name. Windows Explorer reads the label from this ATTR_VOLUME_ID entry,
        // not from BS_VolLab in the boot sector; without it the drive shows as a
        // generic "USB Drive". scan_dir_entries skips it, so it never round-trips
        // back into lfs as a file.
        uint8_t e[FAT_DIRENT_SIZE];
        memset(e, 0, sizeof e);
        memcpy(e, fs->volume_label, 11);   // 11 bytes, space-padded; cluster/size stay 0
        e[DIR_Attr] = ATTR_VOLUME_ID;
        if ((r = dw_put(&dw, e))) goto out;
    }

    {
        lfs2_dir_t d;
        snprintf(s->op, sizeof s->op, "%s", lpath[0] ? lpath : "/");
        r = lfs2_dir_open(fs->lfs, &d, s->op);
        if (r < 0) goto out;
        while (lfs2_dir_read(fs->lfs, &d, &s->info) > 0) {
            const char *nm = s->info.name;
            if (nm[0] == '.' && (nm[1] == 0 || (nm[1] == '.' && nm[2] == 0))) continue;
            if (strncmp(nm, SPILL_PREFIX, strlen(SPILL_PREFIX)) == 0) continue;
            if (strncmp(nm, MV_PREFIX, strlen(MV_PREFIX)) == 0) continue;
            if (nk == capk) {
                int nc = capk ? capk * 2 : 16;
                void *k2 = realloc(kids, nc * sizeof *kids);
                if (!k2) { lfs2_dir_close(fs->lfs, &d); r = FATLFS_ERR_NOMEM; goto out; }
                kids = k2; capk = nc;
            }
            snprintf(kids[nk].name, sizeof kids[nk].name, "%s", nm);
            kids[nk].size = s->info.size; kids[nk].is_dir = (s->info.type == LFS2_TYPE_DIR);
            nk++;
        }
        lfs2_dir_close(fs->lfs, &d);
        r = 0;
    }

    for (int i = 0; i < nk; i++) {
        if (lpath[0]) snprintf(s->childpath, sizeof s->childpath, "%s/%s", lpath, kids[i].name);
        else snprintf(s->childpath, sizeof s->childpath, "%s", kids[i].name);
        if (kids[i].is_dir) {
            uint32_t sub = alloc_cluster(fs);
            if (!sub) { r = FATLFS_ERR_NOMEM; goto out; }
            if ((r = emit_entry(&dw, kids[i].name, 1, sub, 0, s->used, &nused))) goto out;
            if ((r = encode_dir(fs, s->childpath, sub, dw.first))) goto out;
        } else {
            uint32_t first = 0;
            if (kids[i].size > 0) {
                uint32_t nclus = (kids[i].size + fs->cluster_size - 1) / fs->cluster_size;
                uint32_t prev = 0;
                for (uint32_t j = 0; j < nclus; j++) {
                    uint32_t c = alloc_cluster(fs);
                    if (!c) { r = FATLFS_ERR_NOMEM; goto out; }
                    if (prev) fs->fat[prev] = c; else first = c;
                    fs->fat[c] = FAT_EOC; prev = c;
                }
            }
            if ((r = emit_entry(&dw, kids[i].name, 0, first, kids[i].size, s->used, &nused))) goto out;
        }
    }
out:
    free(kids);
    free(s);
    return r;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

// Recover leftovers from an interrupted previous session, BEFORE encoding the
// FAT view. Stale spill temps are partial data with no owner: delete. Mv temps
// are complete files/dirs that were caught mid-rename by a power cut or crash:
// surface them as RECOVERED_<n> so the data reappears instead of being hidden
// (encode_dir skips our temp prefixes) and silently lost forever.
static void recover_temps(fatlfs_t *fs) {
    for (int pass = 0; pass < 64; pass++) {
        lfs2_dir_t d;
        if (lfs2_dir_open(fs->lfs, &d, "/") < 0) return;
        struct lfs2_info inf;
        char victims[8][64]; uint8_t is_mv[8]; int nvic = 0;
        while (lfs2_dir_read(fs->lfs, &d, &inf) > 0 && nvic < 8) {
            int mv = strncmp(inf.name, MV_PREFIX, strlen(MV_PREFIX)) == 0;
            int sp = strncmp(inf.name, SPILL_PREFIX, strlen(SPILL_PREFIX)) == 0;
            if (!mv && !sp) continue;
            size_t len = strlen(inf.name);
            if (len >= sizeof victims[0]) continue;  // not a name we generate
            memcpy(victims[nvic], inf.name, len + 1);
            is_mv[nvic++] = (uint8_t)mv;
        }
        lfs2_dir_close(fs->lfs, &d);
        if (nvic == 0) return;
        for (int i = 0; i < nvic; i++) {
            if (!is_mv[i]) { lfs2_remove(fs->lfs, victims[i]); continue; }
            char dst[32]; struct lfs2_info st; int n;
            for (n = 0; n < 1000; n++) {
                snprintf(dst, sizeof dst, RECOVER_PREFIX "%d", n);
                if (lfs2_stat(fs->lfs, dst, &st) < 0) break;
            }
            if (n >= 1000 || lfs2_rename(fs->lfs, victims[i], dst) < 0) return;
        }
    }
}

int fatlfs_mount(const fatlfs_config_t *cfg, fatlfs_t **out) {
    if (!cfg || !cfg->lfs || !out) return FATLFS_ERR_INVAL;

    fatlfs_t *fs = calloc(1, sizeof *fs);
    if (!fs) return FATLFS_ERR_NOMEM;
    fs->lfs = cfg->lfs;
    fs->cluster_size = cfg->cluster_size ? cfg->cluster_size : 4096;
    if (fs->cluster_size % FAT_SECTOR_SIZE) { free(fs); return FATLFS_ERR_INVAL; }
    fs->spc = fs->cluster_size / FAT_SECTOR_SIZE;
    fs->cluster_count = cfg->cluster_count ? cfg->cluster_count : FAT16_MAX_CLUSTERS;
    if (fs->cluster_count < FAT16_MIN_CLUSTERS) fs->cluster_count = FAT16_MIN_CLUSTERS;
    if (fs->cluster_count > FAT16_MAX_CLUSTERS) fs->cluster_count = FAT16_MAX_CLUSTERS;
    fs->cc2 = fs->cluster_count + 2;
    fs->root_entries = cfg->root_entries ? cfg->root_entries : 1024;
    fs->root_entries = (fs->root_entries + 15) & ~15u;   // whole 512 B sectors
    fs->root_sectors = fs->root_entries * FAT_DIRENT_SIZE / FAT_SECTOR_SIZE;
    fs->staging_max = cfg->staging_max_bytes ? cfg->staging_max_bytes : (4u * 1024 * 1024);
    fs->volume_id = cfg->volume_id ? cfg->volume_id : 0x4641544Cu; // "FATL"
    if (cfg->volume_label[0]) { memcpy(fs->volume_label, cfg->volume_label, 11); }
    else memcpy(fs->volume_label, "FATLFS     ", 11);
    fs->keep_trash = cfg->keep_os_trash;

    // Geometry.
    fs->reserved_sectors = FAT_RESERVED_SECTORS;
    uint32_t fat_bytes = fs->cc2 * 2;   // 16-bit on-disk entries
    fs->fat_sectors = (fat_bytes + FAT_SECTOR_SIZE - 1) / FAT_SECTOR_SIZE;
    fs->root_start = fs->reserved_sectors + FAT_NUM_FATS * fs->fat_sectors;
    fs->data_start = fs->root_start + fs->root_sectors;
    fs->total_sectors = (uint64_t)fs->data_start + (uint64_t)fs->cluster_count * fs->spc;

    fs->fat       = calloc(fs->cc2, sizeof(uint32_t));
    fs->staging   = calloc(fs->cc2, sizeof(uint8_t *));
    fs->dir_bytes = calloc(fs->cc2, sizeof(uint8_t *));
    fs->owner     = malloc(fs->cc2 * sizeof(owner_t));
    fs->spillhead = calloc(fs->cc2, sizeof(uint32_t));
    fs->prev      = malloc(fs->cc2 * sizeof(uint32_t));   // spill scratch, rebuilt per use
    fs->clusbuf   = malloc(fs->cluster_size);
    fs->root_bytes = calloc(fs->root_sectors, FAT_SECTOR_SIZE);
    // Per-handle file caches for lfs2_file_opencfg (LFS2_NO_MALLOC-safe).
    uint32_t csz  = fs->lfs->cfg ? fs->lfs->cfg->cache_size : 512;
    fs->cache_wr       = malloc(csz);
    fs->cache_rd       = malloc(csz);
    fs->cache_spill    = malloc(csz);
    fs->cache_spill_rd = malloc(csz);
    if (!fs->fat || !fs->staging || !fs->dir_bytes || !fs->owner || !fs->spillhead ||
        !fs->prev || !fs->clusbuf || !fs->root_bytes ||
        !fs->cache_wr || !fs->cache_rd || !fs->cache_spill || !fs->cache_spill_rd) {
        fatlfs_unmount(fs); return FATLFS_ERR_NOMEM;
    }
    fs->fc_wr.buffer       = fs->cache_wr;       fs->fc_wr.attrs       = NULL; fs->fc_wr.attr_count       = 0;
    fs->fc_rd.buffer       = fs->cache_rd;       fs->fc_rd.attrs       = NULL; fs->fc_rd.attr_count       = 0;
    fs->fc_spill.buffer    = fs->cache_spill;    fs->fc_spill.attrs    = NULL; fs->fc_spill.attr_count    = 0;
    fs->fc_spill_rd.buffer = fs->cache_spill_rd; fs->fc_spill_rd.attrs = NULL; fs->fc_spill_rd.attr_count = 0;
    for (uint32_t c = 0; c < fs->cc2; c++) { fs->owner[c].node = -1; fs->owner[c].idx = 0; fs->spillhead[c] = 0; }

    fs->fat[0] = 0x0FFFFFF8;      // media descriptor (served as 0xFFF8)
    fs->fat[1] = 0x0FFFFFFF;      // EOC / clean bits (served as 0xFFFF)
    fs->alloc_hint = FAT_FIRST_DATA_CLUSTER;
    build_boot(fs);
    recover_temps(fs);

    // Encode any existing LittleFS content as a populated FAT tree; if the root
    // is empty this simply leaves an empty root directory (region already zeroed).
    int r = encode_dir(fs, "", 0, 0);   // 0 = fixed root region
    if (r) { fatlfs_unmount(fs); return r; }
    r = build_snapshot(fs);
    if (r) { fatlfs_unmount(fs); return r; }

    *out = fs;
    return FATLFS_OK;
}

int fatlfs_unmount(fatlfs_t *fs) {
    if (!fs) return FATLFS_OK;
    int rc = FATLFS_OK;
    if (fs->lfs && fs->fat) rc = fatlfs_flush(fs);
    spill_close(fs);
    spill_rd_close(fs);
    if (fs->staging)   for (uint32_t c = 0; c < fs->cc2; c++) free(fs->staging[c]);
    if (fs->dir_bytes) for (uint32_t c = 0; c < fs->cc2; c++) free(fs->dir_bytes[c]);
    free(fs->fat); free(fs->staging); free(fs->dir_bytes); free(fs->owner);
    free(fs->spillhead); free(fs->prev); free(fs->clusbuf); free(fs->root_bytes);
    free(fs->committed);
    free(fs->cache_wr); free(fs->cache_rd); free(fs->cache_spill); free(fs->cache_spill_rd);
    free(fs);
    return rc;
}

uint32_t fatlfs_block_size(const fatlfs_t *fs)  { (void)fs; return FAT_SECTOR_SIZE; }
uint64_t fatlfs_block_count(const fatlfs_t *fs) { return fs->total_sectors; }

int fatlfs_read(fatlfs_t *fs, uint64_t lba, uint32_t count, void *buf) {
    uint8_t *p = buf;
    for (uint32_t i = 0; i < count; i++) read_sector(fs, lba + i, p + i * FAT_SECTOR_SIZE);
    return FATLFS_OK;
}

int fatlfs_write(fatlfs_t *fs, uint64_t lba, uint32_t count, const void *buf) {
    const uint8_t *p = buf;
    for (uint32_t i = 0; i < count; i++) {
        int r = write_sector(fs, lba + i, p + i * FAT_SECTOR_SIZE);
        if (r) return r;
    }
    return FATLFS_OK;
}

int fatlfs_flush(fatlfs_t *fs) {
    spill_close(fs);
    int rc = reconcile(fs);
    spill_rd_close(fs);   // release the kept-open spill reader after the commit pass
    return rc;
}

// --- embedded helpers ------------------------------------------------------
// On RP2 a flash write masks IRQs for tens of ms; doing that inside the TinyUSB
// MSC write callback starves the bus. So the port stages writes only (no flash)
// and drives spill/flush from the main loop instead.
void fatlfs_defer_spill(fatlfs_t *fs, int on) { fs->no_inline_spill = on ? 1 : 0; }

// Relieve RAM pressure by spilling excess staged clusters to a temp lfs file.
// `max_clusters` (0 = unlimited) caps the flash writes per call so the caller can
// interleave USB servicing and keep the UI alive. Safe to call from the main loop,
// never from a USB callback.
void fatlfs_spill(fatlfs_t *fs, uint32_t max_clusters) {
    if (fs->staged_bytes > fs->staging_max) spill_pressure(fs, max_clusters);
}

uint32_t fatlfs_staged_bytes(const fatlfs_t *fs) { return fs->staged_bytes; }
uint32_t fatlfs_staging_max(const fatlfs_t *fs)  { return fs->staging_max; }

// Root-region writes carry no staging bytes, so "anything to commit?" must
// consider both (a root-only rename/delete would otherwise never flush).
int fatlfs_dirty(const fatlfs_t *fs) { return fs->staged_bytes > 0 || fs->root_dirty; }
