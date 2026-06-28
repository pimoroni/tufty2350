// fatbridge.c - see fatbridge.h. Synthesised FAT16 over a file-store backend.
#include "fatbridge.h"
#include <string.h>

#define SS FATBRIDGE_SECTOR_SIZE

// ---- little-endian writers ----
static inline void put16(uint8_t *p, uint16_t v) {
    p[0] = v & 0xff;
    p[1] = v >> 8;
}
static inline void put32(uint8_t *p, uint32_t v) {
    p[0] = v & 0xff;
    p[1] = (v >> 8) & 0xff;
    p[2] = (v >> 16) & 0xff;
    p[3] = (v >> 24) & 0xff;
}
static inline uint16_t get16(const uint8_t *p) {
    return (uint16_t)p[0] | ((uint16_t)p[1] << 8);
}
static inline uint32_t get32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static uint32_t cluster_bytes(const fatbridge_t *v) {
    return (uint32_t)v->sectors_per_cluster * SS;
}

static char up(char c) {
    return (c >= 'a' && c <= 'z') ? (char)(c - 32) : c;
}
static char lo(char c) {
    return (c >= 'A' && c <= 'Z') ? (char)(c + 32) : c;
}
static bool valid83(char c) {
    return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9')
           || c == '_' || c == '-' || c == '~' || c == '!' || c == '#' || c == '$'
           || c == '%' || c == '&' || c == '(' || c == ')' || c == '@' || c == '^';
}

// LFN checksum over an 11-byte 8.3 name.
static uint8_t name_checksum(const char n[11]) {
    uint8_t s = 0;
    for (int i = 0; i < 11; i++) {
        s = (uint8_t)(((s & 1) ? 0x80 : 0) + (s >> 1) + (uint8_t)n[i]);
    }
    return s;
}

// Classify a name. Fills out83 (space-padded, upper) and nt_flags. Returns
// false if it fits 8.3 (plain or all-lower via NT byte), true if it needs LFN.
static bool classify_name(const char *name, char out83[11], uint8_t *nt_flags) {
    *nt_flags = 0;
    memset(out83, ' ', 11);
    if (name[0] == '.') {
        return true; // dotfiles -> LFN
    }
    const char *dot = NULL;
    for (const char *p = name; *p; p++) {
        if (*p == '.') {
            dot = p;
        }
    }
    size_t blen = dot ? (size_t)(dot - name) : strlen(name);
    size_t elen = dot ? strlen(dot + 1) : 0;
    if (blen == 0 || blen > 8 || elen > 3) {
        return true;
    }
    int bl = 0, bu = 0, el = 0, eu = 0;
    for (size_t i = 0; i < blen; i++) {
        char c = name[i];
        if (!valid83(c)) {
            return true;
        }
        if (c >= 'a' && c <= 'z') {
            bl = 1;
        } else if (c >= 'A' && c <= 'Z') {
            bu = 1;
        }
        out83[i] = up(c);
    }
    for (size_t i = 0; i < elen; i++) {
        char c = dot[1 + i];
        if (!valid83(c)) {
            return true;
        }
        if (c >= 'a' && c <= 'z') {
            el = 1;
        } else if (c >= 'A' && c <= 'Z') {
            eu = 1;
        }
        out83[8 + i] = up(c);
    }
    if ((bl && bu) || (el && eu)) {
        return true; // mixed case can't use the NT-byte trick
    }
    if (bl) {
        *nt_flags |= 0x08;
    }
    if (el) {
        *nt_flags |= 0x10;
    }
    return false;
}

// Does `name` need LFN entries to round-trip (i.e. it isn't representable as a
// plain/lower-case 8.3 name)? Used on the host-write path, where the host gives
// us the 8.3 alias but not this flag - without it a host-written long name is
// synthesised back to the host as its bare 8.3 alias only. Discards the 8.3/NT
// outputs (we keep the host-supplied name83/nt byte).
static bool name_needs_lfn(const char *name) {
    char throwaway83[11];
    uint8_t throwaway_nt;
    return classify_name(name, throwaway83, &throwaway_nt);
}

// Build a unique "BASE~N.EXT" 8.3 alias for a long name (n = 1-based attempt).
static void gen_alias(const char *name, int n, char out83[11]) {
    memset(out83, ' ', 11);
    char base[8];
    int bi = 0;
    for (const char *p = name; *p && *p != '.' && bi < 6; p++) {
        if (valid83(*p)) {
            base[bi++] = up(*p);
        }
    }
    if (bi == 0) {
        base[bi++] = '_';
    }
    char suf[6];
    int sl = 0;
    suf[sl++] = '~';
    char num[4];
    int nl = 0;
    if (n == 0) {
        n = 1;
    }
    while (n > 0 && nl < 3) {
        num[nl++] = '0' + (n % 10);
        n /= 10;
    }
    for (int i = nl - 1; i >= 0; i--) {
        suf[sl++] = num[i];
    }
    int trunc = bi;
    if (trunc + sl > 8) {
        trunc = 8 - sl;
    }
    int o = 0;
    for (int i = 0; i < trunc; i++) {
        out83[o++] = base[i];
    }
    for (int i = 0; i < sl; i++) {
        out83[o++] = suf[i];
    }
    const char *dot = NULL;
    for (const char *p = name; *p; p++) {
        if (*p == '.') {
            dot = p;
        }
    }
    if (dot) {
        for (int i = 0; i < 3 && dot[1 + i]; i++) {
            if (valid83(dot[1 + i])) {
                out83[8 + i] = up(dot[1 + i]);
            }
        }
    }
}

// "MAIN    PY " + nt_flags -> "main.py" into out (>=13 bytes).
static void unmangle_83(const char in[11], uint8_t nt, char *out) {
    int o = 0;
    for (int i = 0; i < 8 && in[i] != ' '; i++) {
        out[o++] = (nt & 0x08) ? lo(in[i]) : in[i];
    }
    if (in[8] != ' ') {
        out[o++] = '.';
        for (int i = 8; i < 11 && in[i] != ' '; i++) {
            out[o++] = (nt & 0x10) ? lo(in[i]) : in[i];
        }
    }
    out[o] = 0;
}

// macOS/Windows metadata noise we never persist to the backing store.
static bool is_host_metadata(const char *name) {
    if (name[0] == '.' && name[1] == '_') {
        return true; // AppleDouble ._*
    }
    static const char *const junk[] = {
        ".DS_Store", ".Spotlight-V100", ".fseventsd", ".Trashes",
        ".TemporaryItems", ".apdisk", "System Volume Information",
        "desktop.ini", "Thumbs.db", "$RECYCLE.BIN",
        ".metadata_never_index", // we synthesise this one (see fatbridge_begin)
        0
    };
    for (int i = 0; junk[i]; i++) {
        if (strcmp(name, junk[i]) == 0) {
            return true;
        }
    }
    return false;
}

int fatbridge_init(fatbridge_t *v, const fatbridge_backend_t *be,
    uint32_t total_bytes, uint8_t spc,
    fatbridge_file_t *files, int max_files,
    uint8_t *wbuf, size_t wbuf_len,
    uint16_t *fat, uint32_t fat_cap) {
    memset(v, 0, sizeof(*v));
    v->be = be;
    v->fat = fat;
    v->fat_cap = fat_cap;
    if (fat && fat_cap) {
        memset(fat, 0, (size_t)fat_cap * sizeof(uint16_t));
    }
    v->sectors_per_cluster = spc;
    v->reserved_sectors = 1;
    v->num_fats = 1;            // 1 FAT: legal, accepted by win/mac/linux, halves FAT region
    v->root_entries = 512;
    v->files = files;
    v->max_files = max_files;
    v->wbuf = wbuf;
    v->wbuf_len = wbuf_len;
    v->vol_id = 0x1337c0de;
    memcpy(v->vol_label, "BADGE      ", 11); // default; caller may override

    v->total_sectors = total_bytes / SS;
    v->root_dir_sectors = (v->root_entries * 32u + SS - 1) / SS;

    // FAT16 size calculation (fatgen-style, single pass).
    uint32_t tmp1 = v->total_sectors - (v->reserved_sectors + v->root_dir_sectors);
    uint32_t tmp2 = (256u * spc) + v->num_fats; // 256 = SS/2 entries per FAT sector
    v->fat_sectors = (tmp1 + (tmp2 - 1)) / tmp2;

    v->fat_start = v->reserved_sectors;
    v->root_start = v->fat_start + (uint32_t)v->num_fats * v->fat_sectors;
    v->data_start = v->root_start + v->root_dir_sectors;
    uint32_t data_sectors = v->total_sectors - v->data_start;
    v->total_clusters = data_sectors / spc;

    if (v->total_clusters < 4085 || v->total_clusters > 65524) {
        return -1; // not a valid FAT16 cluster count
    }
    return fatbridge_begin(v);
}

// Ensure the 8.3 alias in f is unique among files[0..upto).
static bool cluster_cached(const fatbridge_t *v, uint32_t c);
static int cache_find(const fatbridge_t *v, uint32_t cl);

static int lfn_count_of(const fatbridge_file_t *f) {
    return f->needs_lfn ? ((int)strlen(f->name) + 12) / 13 : 0;
}
static int child_entries(const fatbridge_file_t *f) {
    return lfn_count_of(f) + 1; // LFN entries + the 8.3 entry
}

// Build the full "/"-separated path of node idx into buf ("" for root).
static void node_path(fatbridge_t *v, int idx, char *buf, size_t cap) {
    if (idx < 0) {
        if (cap) {
            buf[0] = 0;
        }
        return;
    }
    node_path(v, v->files[idx].parent, buf, cap);
    size_t len = strlen(buf);
    if (len && len + 1 < cap) {
        buf[len++] = '/';
        buf[len] = 0;
    }
    strncat(buf, v->files[idx].name, cap - strlen(buf) - 1);
}

// Make f's 8.3 alias unique among its siblings (children of `parent`).
static void ensure_unique_alias(fatbridge_t *v, int upto, int parent, fatbridge_file_t *f, const char *name) {
    for (int attempt = 1; attempt < 1000; attempt++) {
        gen_alias(name, attempt, f->name83);
        bool clash = false;
        for (int j = 0; j < upto; j++) {
            if (v->files[j].parent == parent && memcmp(v->files[j].name83, f->name83, 11) == 0) {
                clash = true;
                break;
            }
        }
        if (!clash) {
            return;
        }
    }
}

// Recursively snapshot the backend tree into v->files[].
static void fatbridge_enumerate(fatbridge_t *v, int dir_idx, const char *dirpath, int depth) {
    if (depth > 8) {
        return; // bound recursion on the MCU
    }
    char name[64];
    uint32_t size;
    int is_dir;
    for (int i = 0; v->be->list(v->be->ctx, dirpath, i, name, sizeof(name), &size, &is_dir) == 0; i++) {
        if (is_host_metadata(name) || v->n_files >= v->max_files) {
            continue;
        }
        int idx = v->n_files++;
        fatbridge_file_t *f = &v->files[idx];
        memset(f, 0, sizeof(*f));
        strncpy(f->name, name, sizeof(f->name) - 1);
        f->needs_lfn = classify_name(name, f->name83, &f->nt_flags);
        if (f->needs_lfn) {
            ensure_unique_alias(v, idx, dir_idx, f, name);
        }
        f->is_dir = is_dir != 0;
        f->parent = dir_idx;
        f->present = true;
        f->size = f->is_dir ? 0 : size;
        if (f->is_dir) {
            char sub[FATBRIDGE_PATH_MAX];
            node_path(v, idx, sub, sizeof(sub));
            fatbridge_enumerate(v, idx, sub, depth + 1);
        }
    }
}

// Snapshot the backend tree and lay out clusters: files get data clusters,
// each subdirectory gets entry-table cluster(s); the root lives in the fixed
// root-dir region.
// Append a synthetic 0-byte root file (not backed by the store): inert in flush
// (size 0, never dirty) and read as empty. Used for the Spotlight marker.
static void add_marker(fatbridge_t *v, const char *name) {
    if (v->n_files >= v->max_files) {
        return;
    }
    int idx = v->n_files++;
    fatbridge_file_t *f = &v->files[idx];
    memset(f, 0, sizeof(*f));
    strncpy(f->name, name, sizeof(f->name) - 1);
    f->needs_lfn = classify_name(name, f->name83, &f->nt_flags);
    if (f->needs_lfn) {
        ensure_unique_alias(v, idx, -1, f, name);
    }
    f->parent = -1; // root
    f->present = true;
}

int fatbridge_begin(fatbridge_t *v) {
    v->n_files = 0;
    fatbridge_enumerate(v, -1, "", 0);
    // Tell macOS Spotlight not to index this volume (cuts the .Spotlight-V100 /
    // .fseventsd churn). A 0-byte ".metadata_never_index" at the root is the
    // documented marker; synthesised, never written to the backing store.
    add_marker(v, ".metadata_never_index");

    uint32_t cb = cluster_bytes(v);
    uint32_t next = 2;
    for (int i = 0; i < v->n_files; i++) {
        fatbridge_file_t *f = &v->files[i];
        if (f->is_dir) {
            int entries = 2; // "." and ".."
            for (int j = 0; j < v->n_files; j++) {
                if (v->files[j].parent == i && v->files[j].present) {
                    entries += child_entries(&v->files[j]);
                }
            }
            uint32_t tc = ((uint32_t)entries * 32 + cb - 1) / cb;
            if (tc == 0) {
                tc = 1;
            }
            f->first_cluster = next;
            f->n_clusters = tc;
            next += tc;
        } else {
            f->n_clusters = f->size ? (f->size + cb - 1) / cb : 0;
            f->first_cluster = f->n_clusters ? next : 0;
            next += f->n_clusters;
        }
    }
    // Reserve top-of-disk clusters so the host's free-space count matches the
    // backend's REAL free space: presented-used (file/dir clusters + reserved)
    // should equal the backend's used bytes (which include its metadata overhead
    // and any capacity we haven't laid out as files).
    v->reserved_clusters = 0;
    if (v->be->fs_usage) {
        uint64_t total_b = 0, used_b = 0;
        if (v->be->fs_usage(v->be->ctx, &total_b, &used_b) == 0) {
            uint32_t used_cl = (uint32_t)((used_b + cb - 1) / cb);
            uint32_t assigned = next - 2;
            uint32_t avail = v->total_clusters > assigned ? v->total_clusters - assigned : 0;
            uint32_t want = used_cl > assigned ? used_cl - assigned : 0;
            v->reserved_clusters = want > avail ? avail : want;
        }
    }
    memset(v->cache_cl, 0, sizeof(v->cache_cl)); // clear the write cache
    v->lfn_active = false;
    // Reset the hot-path hints (the file table just changed underneath them).
    v->last_owner = -1;
    v->alloc_cursor = 0;
    v->dir_hint_idx = FATBRIDGE_NO_DIR_HINT;
    return 0;
}

void fatbridge_capacity(const fatbridge_t *v, uint32_t *block_count, uint16_t *block_size) {
    *block_size = SS;
    *block_count = v->total_sectors;
}

// Find the file owning data cluster c (>=2); return index or -1, set *is_last.
// Reads are sequential, so most lookups land in the same file as the previous
// one: try the cached owner before the O(n_files) table scan.
static int cluster_owner(fatbridge_t *v, uint32_t c, bool *is_last) {
    int h = v->last_owner;
    if (h >= 0 && h < v->n_files) {
        const fatbridge_file_t *f = &v->files[h];
        if (f->present && f->n_clusters &&
            c >= f->first_cluster && c < f->first_cluster + f->n_clusters) {
            if (is_last) {
                *is_last = (c == f->first_cluster + f->n_clusters - 1);
            }
            return h;
        }
    }
    for (int i = 0; i < v->n_files; i++) {
        const fatbridge_file_t *f = &v->files[i];
        if (!f->present || f->n_clusters == 0) {
            continue;
        }
        if (c >= f->first_cluster && c < f->first_cluster + f->n_clusters) {
            if (is_last) {
                *is_last = (c == f->first_cluster + f->n_clusters - 1);
            }
            v->last_owner = i;
            return i;
        }
    }
    return -1;
}

// ---- read synthesis ----
static void synth_boot(const fatbridge_t *v, uint8_t *s) {
    memset(s, 0, SS);
    s[0] = 0xEB;
    s[1] = 0x3C;
    s[2] = 0x90;             // jmp
    memcpy(s + 3, "MSDOS5.0", 8);
    put16(s + 11, SS);                       // bytes/sector
    s[13] = v->sectors_per_cluster;
    put16(s + 14, v->reserved_sectors);
    s[16] = v->num_fats;
    put16(s + 17, v->root_entries);
    put16(s + 19, v->total_sectors < 0x10000 ? v->total_sectors : 0);
    s[21] = 0xF8;                            // media
    put16(s + 22, v->fat_sectors);
    put16(s + 24, 63);                       // sectors/track
    put16(s + 26, 255);                      // heads
    put32(s + 28, 0);                        // hidden
    put32(s + 32, v->total_sectors < 0x10000 ? 0 : v->total_sectors);
    s[36] = 0x80;                            // drive num
    s[38] = 0x29;                            // ext boot sig
    put32(s + 39, v->vol_id);
    memcpy(s + 43, v->vol_label, 11);        // volume label
    memcpy(s + 54, "FAT16   ", 8);
    s[510] = 0x55;
    s[511] = 0xAA;
}

static uint16_t fat_entry(fatbridge_t *v, uint32_t c) {
    if (c == 0) {
        return 0xFFF8;      // media descriptor
    }
    if (c == 1) {
        return 0xFFFF;
    }
    bool last = false;
    int owner = cluster_owner(v, c, &last);
    if (owner < 0) {
        // Top-of-disk clusters reserved to make free space match the backend:
        // marked end-of-chain (allocated) so the host counts them used, not free,
        // and never tries to write there (beyond real capacity).
        if (v->reserved_clusters &&
            c >= 2 + v->total_clusters - v->reserved_clusters &&
            c < 2 + v->total_clusters) {
            return 0xFFFF;
        }
        return 0x0000;      // free
    }
    return last ? 0xFFFF : (uint16_t)(c + 1);
}

static void synth_fat_sector(fatbridge_t *v, uint32_t idx_in_fat, uint8_t *s) {
    memset(s, 0, SS);
    uint32_t first = idx_in_fat * (SS / 2);   // 256 entries per sector
    for (uint32_t i = 0; i < SS / 2; i++) {
        put16(s + i * 2, fat_entry(v, first + i));
    }
}

static void synth_dir_entry(const fatbridge_file_t *f, uint8_t *e) {
    memset(e, 0, 32);
    memcpy(e, f->name83, 11);
    e[11] = f->is_dir ? 0x10 : 0x20; // directory or archive
    e[12] = f->nt_flags;          // VFAT NT byte: lower-case base/ext
    put16(e + 20, 0);             // first cluster high (FAT16: 0)
    put16(e + 22, 0x4800);        // write time (arbitrary)
    put16(e + 24, 0x5821);        // write date (2024-01-01-ish)
    put16(e + 26, (uint16_t)f->first_cluster);
    put32(e + 28, f->is_dir ? 0 : f->size); // dirs report size 0
}

// Emit one LFN entry for sequence seq (1-based), is_last marks the highest seq
// (which is stored physically first and carries the 0x40 flag).
static void synth_lfn_entry(const fatbridge_file_t *f, int seq, bool is_last, uint8_t cksum, uint8_t *e) {
    memset(e, 0, 32);
    e[0] = (uint8_t)(seq | (is_last ? 0x40 : 0));
    e[11] = 0x0F;                 // LFN attribute
    e[13] = cksum;
    int start = (seq - 1) * 13;
    size_t nlen = strlen(f->name);
    static const int pos[13] = { 1, 3, 5, 7, 9, 14, 16, 18, 20, 22, 24, 28, 30 };
    for (int j = 0; j < 13; j++) {
        int ci = start + j;
        uint16_t ch;
        if ((size_t)ci < nlen) {
            ch = (uint8_t)f->name[ci];
        } else if ((size_t)ci == nlen) {
            ch = 0x0000;          // NUL terminator
        } else {
            ch = 0xFFFF;          // padding
        }
        e[pos[j]] = ch & 0xff;
        e[pos[j] + 1] = ch >> 8;
    }
}

// Emit logical entry `e` of directory dir_idx's table (-1 == root) into out.
// Entry stream: [vol-label | "." ".."] then each child's LFN entries + 8.3.
static void emit_dir_entry(fatbridge_t *v, int dir_idx, uint32_t e, uint8_t *out) {
    memset(out, 0, 32);
    uint32_t pos;
    if (dir_idx < 0) {
        if (e == 0) {
            memcpy(out, v->vol_label, 11);
            out[11] = 0x08;       // volume label
            return;
        }
        pos = 1;
    } else {
        if (e == 0 || e == 1) {   // "." and ".."
            memset(out, ' ', 11);
            out[0] = '.';
            if (e == 1) {
                out[1] = '.';
            }
            out[11] = 0x10;
            uint32_t cl = (e == 0) ? v->files[dir_idx].first_cluster
                : (v->files[dir_idx].parent < 0 ? 0 : v->files[v->files[dir_idx].parent].first_cluster);
            put16(out + 26, (uint16_t)cl);
            return;
        }
        pos = 2;
    }
    // The host reads a directory table sector-by-sector, so successive entries
    // scan the same child list. Resume from the cached boundary (the start of
    // the child covering a not-larger entry) instead of restarting from the
    // first node every call - that restart is what makes a table O(children^2).
    int j = 0;
    if (v->dir_hint_idx == dir_idx && v->dir_hint_pos <= e) {
        j = v->dir_hint_j;
        pos = v->dir_hint_pos;
    }
    for (; j < v->n_files; j++) {
        fatbridge_file_t *c = &v->files[j];
        if (c->parent != dir_idx || !c->present) {
            continue;
        }
        int lfn = lfn_count_of(c);
        // Record this child's boundary so the next (>=) entry resumes here.
        v->dir_hint_idx = dir_idx;
        v->dir_hint_j = j;
        v->dir_hint_pos = pos;
        if (e < pos + (uint32_t)lfn) {
            int part = (int)(e - pos);
            synth_lfn_entry(c, lfn - part, part == 0, name_checksum(c->name83), out);
            return;
        }
        if (e == pos + (uint32_t)lfn) {
            synth_dir_entry(c, out);
            return;
        }
        pos += lfn + 1;
    }
    // beyond the last child -> leave zero (end-of-directory)
}

static void synth_dir_table_sector(fatbridge_t *v, int dir_idx, uint32_t sector_in_table, uint8_t *s) {
    memset(s, 0, SS);
    uint32_t base = sector_in_table * (SS / 32); // 16 entries per sector
    for (uint32_t i = 0; i < SS / 32; i++) {
        emit_dir_entry(v, dir_idx, base + i, s + i * 32);
    }
}

static int synth_data_sector(fatbridge_t *v, uint32_t sector, uint8_t *s) {
    memset(s, 0, SS);
    uint32_t rel = sector - v->data_start;
    uint32_t cluster = 2 + rel / v->sectors_per_cluster;
    uint32_t sec_in_clus = rel % v->sectors_per_cluster;
    bool last;
    int owner = cluster_owner(v, cluster, &last);
    if (owner < 0) {
        return 0; // free space reads as zeros
    }
    fatbridge_file_t *f = &v->files[owner];
    if (f->is_dir) {
        // this cluster holds the directory's entry table
        uint32_t tsec = (cluster - f->first_cluster) * v->sectors_per_cluster + sec_in_clus;
        synth_dir_table_sector(v, owner, tsec, s);
        return 0;
    }
    uint32_t file_off = (cluster - f->first_cluster) * cluster_bytes(v) + sec_in_clus * SS;
    if (file_off >= f->size) {
        return 0;
    }
    uint32_t n = f->size - file_off;
    if (n > SS) {
        n = SS;
    }
    if (f->dirty) {
        // served from the sparse write cache (host-modified this session)
        int slot = cache_find(v, cluster);
        if (slot >= 0) {
            memcpy(s, v->wbuf + (uint32_t)slot * cluster_bytes(v) + sec_in_clus * SS, n);
            return 0;
        }
    }
    char path[FATBRIDGE_PATH_MAX];
    node_path(v, owner, path, sizeof(path));
    v->be->read(v->be->ctx, path, file_off, s, n);
    return 0;
}

static int read_sector(fatbridge_t *v, uint32_t sector, uint8_t *s) {
    if (sector == 0) {
        synth_boot(v, s);
    } else if (sector < v->fat_start) {
        memset(s, 0, SS);                       // reserved
    } else if (sector < v->root_start) {
        uint32_t in_fat = (sector - v->fat_start) % v->fat_sectors;
        synth_fat_sector(v, in_fat, s);
    } else if (sector < v->data_start) {
        synth_dir_table_sector(v, -1, sector - v->root_start, s);
    } else {
        synth_data_sector(v, sector, s);
    }
    return 0;
}

int32_t fatbridge_read(fatbridge_t *v, uint32_t lba, uint32_t offset, void *buf, uint32_t bufsize) {
    uint8_t sec[SS];
    uint8_t *out = buf;
    uint32_t produced = 0;
    uint64_t abs = (uint64_t)lba * SS + offset;
    while (produced < bufsize) {
        uint32_t sector = (uint32_t)(abs / SS);
        uint32_t soff = (uint32_t)(abs % SS);
        read_sector(v, sector, sec);
        uint32_t n = SS - soff;
        if (n > bufsize - produced) {
            n = bufsize - produced;
        }
        memcpy(out + produced, sec + soff, n);
        produced += n;
        abs += n;
    }
    return (int32_t)produced;
}

// ---- write interpretation (phase 1: contiguous small-file create/delete) ----
// Strategy: cache data-region writes contiguously in wbuf; parse root-dir
// writes to learn file name/size/first_cluster, then commit the assembled
// bytes to the backend. Handles data-before-dir and dir-before-data for files
// allocated contiguously from a single cluster run (the common case on a fresh
// volume). Fragmented allocation / LFN / >wbuf files are TODO.

// ---- sparse write cache (cluster -> wbuf slot) ----
static uint32_t cache_capacity(const fatbridge_t *v) {
    uint32_t n = v->wbuf_len / cluster_bytes(v);
    return n > FATBRIDGE_CACHE_SLOTS ? FATBRIDGE_CACHE_SLOTS : n;
}
static int cache_find(const fatbridge_t *v, uint32_t cl) {
    uint32_t n = cache_capacity(v);
    for (uint32_t i = 0; i < n; i++) {
        if (v->cache_cl[i] == cl) {
            return (int)i;
        }
    }
    return -1;
}
static int cache_alloc(fatbridge_t *v, uint32_t cl) {
    uint32_t n = cache_capacity(v);
    if (n == 0) {
        return -1;
    }
    // Scan from a rolling cursor (not always slot 0) so a bulk copy that fills
    // the cache front-to-back is amortised O(1) per alloc, not O(slots).
    if (v->alloc_cursor >= n) {
        v->alloc_cursor = 0;
    }
    for (uint32_t k = 0; k < n; k++) {
        uint32_t i = v->alloc_cursor + k;
        if (i >= n) {
            i -= n;
        }
        if (v->cache_cl[i] == 0) {
            v->cache_cl[i] = cl;
            v->cache_clean[i] = 0;
            v->alloc_cursor = (i + 1 >= n) ? 0 : i + 1;
            return (int)i;
        }
    }
    // No empty slot: evict a committed (clean) cluster - its data is safe in the
    // backend. Dirty (uncommitted) clusters must never be dropped.
    for (uint32_t k = 0; k < n; k++) {
        uint32_t i = v->alloc_cursor + k;
        if (i >= n) {
            i -= n;
        }
        if (v->cache_clean[i]) {
            v->cache_cl[i] = cl;
            v->cache_clean[i] = 0;
            v->alloc_cursor = (i + 1 >= n) ? 0 : i + 1;
            return (int)i;
        }
    }
    return -1; // genuinely full (all clusters dirty/in-flight)
}

// Was data for cluster c written into the cache this session?
static bool cluster_cached(const fatbridge_t *v, uint32_t c) {
    return cache_find(v, c) >= 0;
}

static int find_child_by_83(fatbridge_t *v, int parent, const uint8_t name83[11]) {
    for (int i = 0; i < v->n_files; i++) {
        if (v->files[i].parent == parent && memcmp(v->files[i].name83, name83, 11) == 0) {
            return i;
        }
    }
    return -1;
}

// Returns false if the cache is full (data would be dropped) so the caller can
// fail the host write instead of silently losing it.
static bool cache_data_sector(fatbridge_t *v, uint32_t sector, const uint8_t *s) {
    uint32_t rel = sector - v->data_start;
    uint32_t cluster = 2 + rel / v->sectors_per_cluster;
    uint32_t sec_in_clus = rel % v->sectors_per_cluster;
    int slot = cache_find(v, cluster);
    if (slot < 0) {
        slot = cache_alloc(v, cluster);
    }
    if (slot < 0) {
        v->overflow = true; // cache full of uncommitted data -> can't accept more
        return false;
    }
    memcpy(v->wbuf + (uint32_t)slot * cluster_bytes(v) + sec_in_clus * SS, s, SS);
    v->cache_clean[slot] = 0; // freshly written -> uncommitted
    return true;
}

// Commit ONE cluster of dirty file idx (the next un-committed one), if all its
// data is cached. Writes piece-by-piece across calls so each flash burst is one
// cluster; on the last cluster, commits the size and evicts the file's slots.
// Returns true if it did a unit of work. Data clusters may sit in scattered
// cache slots; a file whose data the host hasn't fully written stays pending.
// The physical cluster after c, following the host's FAT chain (handles a file
// the host allocated NON-contiguously - common once the volume has data). Falls
// back to c+1 only if the chain entry isn't mirrored yet.
static uint32_t file_next_cluster(const fatbridge_t *v, uint32_t c) {
    if (v->fat && c >= 2 && c < v->fat_cap) {
        uint32_t nxt = v->fat[c];
        if (nxt >= 2 && nxt < 0xFFF0u) {
            return nxt;
        }
    }
    return c + 1;
}

static bool commit_one_cluster(fatbridge_t *v, int idx) {
    fatbridge_file_t *f = &v->files[idx];
    if (!f->present || f->is_dir || f->size == 0 || !f->dirty) {
        return false;
    }
    uint32_t cb = cluster_bytes(v);
    uint32_t need = (f->size + cb - 1) / cb;
    char path[FATBRIDGE_PATH_MAX];
    node_path(v, idx, path, sizeof(path));
    // Every cluster must be available before we rewrite the file. A cluster is
    // either cached (host wrote it this session) or - for a partial edit/append -
    // still present unchanged in the backend file, which we pull in here BEFORE
    // any write (the first write truncates). If a cluster is in neither, the data
    // hasn't fully arrived (new file mid-transfer) so we wait. Walk the file's
    // FAT chain (physical clusters), not first_cluster+i, so fragmented files work.
    // This whole-chain scan only has to pass ONCE per (re)dirtied file: once every
    // cluster is confirmed present, commit_ready latches so the remaining
    // per-cluster commit calls don't re-walk the chain (that re-walk made commit
    // O(need^2) in cache scans, dominating large-file commit time).
    if (!f->commit_ready) {
        uint32_t c = f->first_cluster;
        for (uint32_t i = 0; i < need; i++) {
            if (cache_find(v, c) < 0) {
                int fslot = cache_alloc(v, c);
                if (fslot < 0) {
                    return false; // cache full; retry after an eviction
                }
                uint32_t off = i * cb;
                uint32_t want = (i + 1 == need) ? (f->size - off) : cb;
                int got = v->be->read(v->be->ctx, path, off, v->wbuf + (uint32_t)fslot * cb, want);
                if (got < (int)want) {
                    v->cache_cl[fslot] = 0; // not in backend either -> wait
                    return false;
                }
            }
            c = file_next_cluster(v, c);
        }
        f->commit_ready = true; // all clusters cached/pulled; uncommitted ones stay
                                // dirty (never evicted) so they remain available
    }
    uint32_t k = f->commit_done;
    if (k == 0) {
        f->commit_cl = f->first_cluster; // start of the chain
    }
    int slot = cache_find(v, f->commit_cl);
    uint32_t chunk = (k + 1 == need) ? (f->size - k * cb) : cb;
    // Backend write/commit can fail when the real flash is full (LFS_ERR_NOSPC).
    if (slot < 0 || v->be->write(v->be->ctx, path, k * cb, v->wbuf + (uint32_t)slot * cb, chunk) < 0) {
        v->overflow = true;
        f->dirty = false;
        f->commit_done = 0;
        f->commit_ready = false;
        return true;
    }
    if (slot >= 0) {
        v->cache_clean[slot] = 1; // committed -> clean (kept, evictable under pressure)
    }
    f->commit_cl = file_next_cluster(v, f->commit_cl);
    f->commit_done++;
    if (f->commit_done >= need) {
        if (v->be->commit(v->be->ctx, path, f->size) < 0) {
            v->overflow = true;
        }
        f->dirty = false;       // re-commits if the host edits it again
        f->commit_done = 0;
    }
    return true;
}

// Pull the 13 UCS-2 chars of an LFN entry into the accumulator at its position.
static void lfn_accumulate(fatbridge_t *v, const uint8_t *e) {
    int seq = e[0] & 0x1F;
    if (seq < 1 || seq > 19) {
        return;
    }
    if (e[0] & 0x40) {           // last logical entry (physically first): restart
        memset(v->lfn_acc, 0, sizeof(v->lfn_acc));
        v->lfn_checksum = e[13];
        v->lfn_active = true;
    }
    static const int pos[13] = { 1, 3, 5, 7, 9, 14, 16, 18, 20, 22, 24, 28, 30 };
    int start = (seq - 1) * 13;
    for (int j = 0; j < 13; j++) {
        int ci = start + j;
        if (ci < (int)sizeof(v->lfn_acc) - 1) {
            uint16_t ch = (uint16_t)e[pos[j]] | ((uint16_t)e[pos[j] + 1] << 8);
            v->lfn_acc[ci] = (ch == 0 || ch == 0xFFFF) ? 0 : (char)(ch & 0xff);
        }
    }
}

// Interpret a 512-byte directory-table sector belonging to directory dir_idx
// (-1 == root). Children are created/edited/deleted/renamed within that dir;
// a 0x10 entry is a subdirectory (mkdir).
static void parse_dir_sector(fatbridge_t *v, int dir_idx, const uint8_t *s) {
    for (uint32_t i = 0; i < SS / 32; i++) {
        const uint8_t *e = s + i * 32;
        uint8_t first = e[0];
        uint8_t attr = e[11];
        if (first == 0x00) {
            continue;          // free/never-used slot
        }
        if (attr == 0x0F) {    // LFN component
            if (first != 0xE5) {
                lfn_accumulate(v, e);
            }
            continue;
        }
        if (attr == 0x08) {    // volume label
            v->lfn_active = false;
            continue;
        }
        if (e[0] == '.') {     // "." / ".." self/parent links
            v->lfn_active = false;
            continue;
        }
        if (first == 0xE5) {   // deleted short entry
            // byte 0 is wiped but bytes 1..10 of the 8.3 name survive; match a
            // child of this directory on those and remove it.
            for (int k = 0; k < v->n_files; k++) {
                fatbridge_file_t *f = &v->files[k];
                if (f->present && f->parent == dir_idx && memcmp(f->name83 + 1, e + 1, 10) == 0) {
                    f->present = false;
                    f->pending_remove = true; // deferred to fatbridge_flush()
                    v->pending = true;
                    break;
                }
            }
            v->lfn_active = false;
            continue;
        }
        uint8_t name83[11];
        memcpy(name83, e, 11);
        // resolve the real name: assembled LFN (if checksum matches) else 8.3.
        char name[64];
        if (v->lfn_active && name_checksum((char *)name83) == v->lfn_checksum && v->lfn_acc[0]) {
            strncpy(name, v->lfn_acc, sizeof(name) - 1);
            name[sizeof(name) - 1] = 0;
        } else {
            unmangle_83((char *)name83, e[12], name);
        }
        v->lfn_active = false;

        if (is_host_metadata(name)) {
            // Never persist host metadata. A prior transient parse may have seen
            // this entry's 8.3 record before its LFN prefix was cached and created
            // a node under the 8.3 alias (e.g. "._tumblr.png" -> "_TUMB~40.PNG").
            // Now that we recognise the real name, drop that stale alias node
            // (matched by the identical 8.3 bytes), removing it from the backend
            // too if it was already committed.
            int dup = find_child_by_83(v, dir_idx, name83);
            if (dup >= 0 && v->files[dup].present) {
                v->files[dup].present = false;
                v->files[dup].pending_remove = true;
                v->pending = true;
            }
            continue;
        }
        bool is_dir = (attr & 0x10) != 0;
        uint32_t size = get32(e + 28);
        uint32_t fc = get16(e + 26);
        int fi = find_child_by_83(v, dir_idx, name83);

        // Rename detection (same directory): a new name whose cluster matches an
        // existing child of the SAME type. For files we also require that no data
        // was written for that cluster (else it's a delete+recreate with new
        // content, not a rename). For directories that guard does NOT apply: macOS
        // rewrites a renamed directory's entry-table cluster (so it IS cached),
        // and a new dir entry can only share an existing dir's first_cluster when
        // it's a rename - littlefs rename then moves the whole subtree.
        if (fi < 0 && fc != 0 && (is_dir || !cluster_cached(v, fc))) {
            for (int k = 0; k < v->n_files; k++) {
                fatbridge_file_t *g = &v->files[k];
                if (g->parent == dir_idx && g->is_dir == is_dir && (g->present || g->pending_remove)
                    && g->first_cluster == fc) {
                    if (!g->pending_rename) {
                        strncpy(g->old_name, g->name, sizeof(g->old_name) - 1);
                        g->old_name[sizeof(g->old_name) - 1] = 0;
                    }
                    g->pending_rename = true;
                    g->present = true;
                    g->pending_remove = false;
                    memcpy(g->name83, name83, 11);
                    strncpy(g->name, name, sizeof(g->name) - 1);
                    g->name[sizeof(g->name) - 1] = 0;
                    g->needs_lfn = name_needs_lfn(g->name); // new name may need LFN
                    g->size = size;
                    v->pending = true;
                    fi = k;
                    break;
                }
            }
            if (fi >= 0) {
                continue; // rename handled
            }
        }

        if (fi < 0) {
            if (v->n_files >= v->max_files) {
                continue;
            }
            fi = v->n_files++;
            fatbridge_file_t *f = &v->files[fi];
            memset(f, 0, sizeof(*f));
            memcpy(f->name83, name83, 11);
            f->parent = dir_idx;
            f->present = true;
            f->is_dir = is_dir;
            if (is_dir) {
                f->first_cluster = fc;
                f->n_clusters = 1; // host allocates one cluster for a new dir table
                f->pending_mkdir = true;
            }
        }
        fatbridge_file_t *f = &v->files[fi];
        strncpy(f->name, name, sizeof(f->name) - 1);
        f->name[sizeof(f->name) - 1] = 0;
        f->nt_flags = e[12];
        f->needs_lfn = name_needs_lfn(f->name); // synthesise LFN back this session
        if (!f->is_dir) {
            // Only (re)mark dirty when the data actually changed. Directory
            // tables are re-parsed idempotently; without this guard a re-parse
            // would re-dirty an already-committed file whose cache slots have
            // been evicted, committing garbage over good data.
            bool changed = (f->first_cluster != fc) || (f->size != size);
            f->size = size;
            f->first_cluster = fc;
            f->n_clusters = size ? (size + cluster_bytes(v) - 1) / cluster_bytes(v) : 0;
            if (changed) {
                f->dirty = true;
                f->commit_done = 0;
                f->commit_ready = false; // data changed -> re-scan availability
            }
        }
        v->pending = true; // commit deferred to fatbridge_flush()
    }
}

// Parse one subdirectory's ENTIRE entry table - every cluster of its host-FAT
// chain, in order, from the cache - with fresh LFN state. Parsing the whole
// chain as a single ordered stream is what makes long names whose LFN sets
// straddle a sector/cluster boundary come out intact. Idempotent (re-parsing
// updates existing nodes; the change-guard in parse_dir_sector stops it from
// re-dirtying already-committed files). Dir-table clusters are left cached so
// later passes see newly-appended entries.
static void parse_one_dir(fatbridge_t *v, int dir_idx) {
    uint32_t cb = cluster_bytes(v);
    uint32_t spc = v->sectors_per_cluster;
    v->lfn_active = false; // a directory table is a fresh entry stream
    uint32_t c = v->files[dir_idx].first_cluster;
    int guard = 0;
    while (c >= 2 && c < 0xFFF0u && c < v->fat_cap && guard++ < 100000) {
        int slot = cache_find(v, c);
        if (slot >= 0) {
            uint8_t *cbase = v->wbuf + (uint32_t)slot * cb;
            for (uint32_t s = 0; s < spc; s++) {
                parse_dir_sector(v, dir_idx, cbase + s * SS);
            }
        }
        uint32_t nxt = v->fat ? v->fat[c] : 0;
        if (nxt == 0 || nxt == c) {
            break;
        }
        c = nxt;
    }
    v->lfn_active = false;
}

// Parse all subdirectory tables from the cache. Iterates to a fixpoint because
// parsing one directory can reveal deeper subdirectories whose tables are also
// cached and waiting. (The fixed root region is parsed live in fatbridge_write.)
static void parse_dir_tables(fatbridge_t *v) {
    if (!v->fat) {
        return;
    }
    for (int pass = 0; pass < 32; pass++) {
        int before = v->n_files;
        for (int i = 0; i < v->n_files; i++) {
            fatbridge_file_t *f = &v->files[i];
            if (f->present && f->is_dir && f->first_cluster) {
                parse_one_dir(v, i);
            }
        }
        if (v->n_files == before) {
            break;
        }
    }
}

int32_t fatbridge_write(fatbridge_t *v, uint32_t lba, uint32_t offset, const void *buf, uint32_t bufsize) {
    const uint8_t *in = buf;
    uint32_t consumed = 0;
    uint64_t abs = (uint64_t)lba * SS + offset;
    uint8_t sec[SS];
    bool dropped = false;
    // A write may add/remove/rename children, invalidating the dir-entry resume
    // hint built during the last read pass.
    v->dir_hint_idx = FATBRIDGE_NO_DIR_HINT;
    while (consumed < bufsize) {
        uint32_t sector = (uint32_t)(abs / SS);
        uint32_t soff = (uint32_t)(abs % SS);
        uint32_t n = SS - soff;
        if (n > bufsize - consumed) {
            n = bufsize - consumed;
        }
        // assemble a full sector image (read-modify-write for partial)
        if (n != SS) {
            read_sector(v, sector, sec);
        }
        memcpy(sec + soff, in + consumed, n);

        if (sector >= v->data_start) {
            // Cache ALL data-region writes - both file data AND subdirectory
            // entry tables. Subdir tables are parsed wholesale (whole host-FAT
            // chain, in order, fresh LFN state) by parse_dir_tables() at flush
            // time; parsing them incrementally here would corrupt long names
            // whose LFN sets straddle a sector/cluster boundary.
            if (!cache_data_sector(v, sector, sec)) {
                dropped = true;    // cache full of uncommitted data
            }
            v->pending = true;     // a late data write may complete a file; defer
            v->dirty_dirs = true;  // a cached cluster may be a subdir table
        } else if (sector >= v->root_start && sector < v->data_start) {
            parse_dir_sector(v, -1, sec); // fixed root directory region
        } else if (v->fat && sector >= v->fat_start && sector < v->root_start) {
            // Mirror the host FAT so we can follow directory entry-table chains.
            uint32_t in_fat = (sector - v->fat_start) % v->fat_sectors;
            uint32_t base = in_fat * (SS / 2u); // 256 cluster entries per sector
            for (uint32_t k = 0; k < SS / 2u; k++) {
                uint32_t c = base + k;
                if (c < v->fat_cap) {
                    v->fat[c] = get16(sec + k * 2);
                }
            }
            v->pending = true;
        }

        consumed += n;
        abs += n;
    }
    // If the cache couldn't hold this write, fail it so the host reports an error
    // (e.g. "disk full") instead of believing a silently-dropped write succeeded.
    if (dropped) {
        return -1;
    }
    return (int32_t)consumed;
}

// Do one bounded unit of deferred backend work (see header). Call repeatedly,
// interleaved with tud_task(), so flash never starves the USB task.
bool fatbridge_flush_step(fatbridge_t *v) {
    char path[FATBRIDGE_PATH_MAX], opath[FATBRIDGE_PATH_MAX];
    // (Re)parse subdirectory tables from the cache whenever new data-region
    // sectors have arrived, so every file in every directory is tracked before
    // we commit. Gated so it doesn't re-scan the whole tree on every call.
    if (v->dirty_dirs) {
        parse_dir_tables(v);
        v->dirty_dirs = false;
    }
    for (int i = 0; i < v->n_files; i++) {
        fatbridge_file_t *f = &v->files[i];
        if (f->pending_mkdir) {
            node_path(v, i, path, sizeof(path));
            v->be->mkdir(v->be->ctx, path);
            f->pending_mkdir = false;
            return true;
        }
        if (f->pending_rename) {
            node_path(v, i, path, sizeof(path));        // new path
            node_path(v, f->parent, opath, sizeof(opath));
            size_t l = strlen(opath);
            if (l && l + 1 < sizeof(opath)) {
                opath[l++] = '/';
                opath[l] = 0;
            }
            strncat(opath, f->old_name, sizeof(opath) - strlen(opath) - 1);
            v->be->rename(v->be->ctx, opath, path);
            f->pending_rename = false;
            f->dirty = false; // rename carries no new data
            return true;
        }
        if (f->pending_remove) {
            node_path(v, i, path, sizeof(path));
            v->be->remove(v->be->ctx, path);
            f->pending_remove = false;
            return true;
        }
        if (commit_one_cluster(v, i)) {
            return true;
        }
    }
    v->pending = false;
    return false;
}

// Apply ALL deferred work (host tests / small edits).
void fatbridge_flush(fatbridge_t *v) {
    while (fatbridge_flush_step(v)) {
    }
}

// Clusters of file data still waiting to be committed to the backend (i.e. real
// pending commit work, NOT cached dir-table/free clusters which are never written
// out). Used for the post-eject commit progress bar. Reaches 0 when done.
uint32_t fatbridge_pending_clusters(const fatbridge_t *v) {
    uint32_t total = 0;
    for (int i = 0; i < v->n_files; i++) {
        const fatbridge_file_t *f = &v->files[i];
        if (f->present && !f->is_dir && f->dirty && f->n_clusters > f->commit_done) {
            total += f->n_clusters - f->commit_done;
        }
    }
    return total;
}
