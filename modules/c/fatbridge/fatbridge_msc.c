// fatbridge: expose the badge's littlefs storage to a USB host as a (synthesised)
// FAT16 drive, so files can be copied/edited over USB while the on-device
// filesystem stays littlefs (resilient, single unified partition).
//
// This file is the MicroPython glue + the C API that ports/rp2/msc_disk.c calls
// to serve the live USB-MSC drive. The FAT<->backend translation core is in
// fatbridge.c. The drive is presented on demand by fatbridge.msc_mode(), which
// blocks servicing USB until the host ejects/unmounts, then reboots to normal.
#include <string.h>
#include "py/runtime.h"
#include "py/mphal.h"
#include "extmod/vfs.h"
#include "lib/littlefs/lfs2.h"
#include "fatbridge.h"

// FAT volume label the host shows for the badge drive. Configurable per board
// (TUFTY / BLINKY / BADGER ...); set in mpconfigboard.h.
#ifndef MICROPY_HW_FATBRIDGE_LABEL
#define MICROPY_HW_FATBRIDGE_LABEL "BADGE"
#endif

// TinyUSB / rp2 USB glue, forward-declared (tusb.h isn't on the qstr-scan path).
extern void mp_usbd_task(void);
extern bool tud_mounted(void);
extern bool rp2_tud_set_msc_ready(void);            // present the MSC LUN media
extern void watchdog_reboot(uint32_t pc, uint32_t sp, uint32_t delay_ms);

// The mounted VfsLfs2 object layout (mirrors extmod/vfs_lfs.c's
// mp_obj_vfs_lfs2_t) so we can reach the live lfs2_t of the flash filesystem.
extern const mp_obj_type_t mp_type_vfs_lfs2;
typedef struct {
    mp_obj_base_t base;
    mp_vfs_blockdev_t blockdev;
    bool enable_mtime;
    vstr_t cur_dir;
    struct lfs2_config config;
    lfs2_t lfs;
} fatbridge_lfs2_vfs_t;

// --- path-based backend over the mounted littlefs ---
typedef struct { lfs2_t *lfs; const struct lfs2_file_config *fcfg; } be_ctx_t;
static lfs2_t *real_lfs;
static struct lfs2_file_config real_fcfg;  // commit (write) file cache
static struct lfs2_file_config read_fcfg;  // reads use their own cache so they can
                                           // run while the commit file is open
static be_ctx_t real_ctx;
static bool readonly_mode = true;

// The file currently being committed is kept OPEN across its per-cluster writes
// and closed once (be_commit) - one littlefs metadata commit per file instead of
// one per 2 KB cluster (which is O(n^2) and unusably slow on a 1 MB+ file).
static lfs2_file_t cm_file;
static bool cm_open;
static char cm_path[160];

// Core paths are "" (root) or "a/b/c"; lfs2 wants a leading slash.
static void lfspath(char *out, size_t cap, const char *rel) {
    out[0] = '/';
    if (rel[0] == 0) {
        out[1] = 0;
    } else {
        strncpy(out + 1, rel, cap - 2);
        out[cap - 1] = 0;
    }
}
static bool is_dot(const char *n) {
    return n[0] == '.' && (n[1] == 0 || (n[1] == '.' && n[2] == 0));
}
static int be_list(void *c, const char *dir, int idx, char *name, size_t cap, uint32_t *size, int *is_dir) {
    be_ctx_t *bc = c;
    char p[160];
    lfspath(p, sizeof(p), dir);
    lfs2_dir_t d;
    if (lfs2_dir_open(bc->lfs, &d, p) < 0) {
        return -1;
    }
    struct lfs2_info info;
    int n = 0, rc = -1;
    while (lfs2_dir_read(bc->lfs, &d, &info) > 0) {
        if (info.type == LFS2_TYPE_DIR && is_dot(info.name)) {
            continue;
        }
        if (n == idx) {
            strncpy(name, info.name, cap - 1);
            name[cap - 1] = 0;
            *size = info.size;
            *is_dir = (info.type == LFS2_TYPE_DIR);
            rc = 0;
            break;
        }
        n++;
    }
    lfs2_dir_close(bc->lfs, &d);
    return rc;
}
static int be_read(void *c, const char *path, uint32_t off, void *buf, uint32_t len) {
    be_ctx_t *bc = c;
    char p[160];
    lfspath(p, sizeof(p), path);
    lfs2_file_t f;
    if (lfs2_file_opencfg(bc->lfs, &f, p, LFS2_O_RDONLY, &read_fcfg) < 0) {
        return -1;
    }
    lfs2_file_seek(bc->lfs, &f, off, LFS2_SEEK_SET);
    int r = lfs2_file_read(bc->lfs, &f, buf, len);
    lfs2_file_close(bc->lfs, &f);
    return r;
}
// Stream a cluster into the kept-open commit file (opened on cluster 0, truncating;
// closed once by be_commit). Writes are sequential (logical offsets) regardless of
// how the host fragmented the data - commit_one_cluster picks the right cache slot.
static int be_write(void *c, const char *path, uint32_t off, const void *buf, uint32_t len) {
    if (readonly_mode) {
        return -1;
    }
    be_ctx_t *bc = c;
    char p[160];
    lfspath(p, sizeof(p), path);
    if (cm_open && (off == 0 || strcmp(cm_path, p) != 0)) {
        lfs2_file_close(bc->lfs, &cm_file); // restart / different file -> close prev
        cm_open = false;
    }
    if (!cm_open) {
        int fl = LFS2_O_WRONLY | LFS2_O_CREAT | (off == 0 ? LFS2_O_TRUNC : 0);
        if (lfs2_file_opencfg(bc->lfs, &cm_file, p, fl, &real_fcfg) < 0) {
            return -1;
        }
        strncpy(cm_path, p, sizeof(cm_path) - 1);
        cm_path[sizeof(cm_path) - 1] = 0;
        cm_open = true;
    }
    lfs2_file_seek(bc->lfs, &cm_file, off, LFS2_SEEK_SET);
    int r = lfs2_file_write(bc->lfs, &cm_file, buf, len);
    return r < 0 ? r : 0;
}
static int be_commit(void *c, const char *path, uint32_t size) {
    (void)path; (void)size;
    be_ctx_t *bc = c;
    if (cm_open) {
        int r = lfs2_file_close(bc->lfs, &cm_file); // the single metadata commit
        cm_open = false;
        return r < 0 ? -1 : 0;
    }
    return 0;
}
static int be_remove(void *c, const char *path) {
    if (readonly_mode) {
        return -1;
    }
    be_ctx_t *bc = c;
    char p[160];
    lfspath(p, sizeof(p), path);
    return lfs2_remove(bc->lfs, p) < 0 ? -1 : 0;
}
static int be_rename(void *c, const char *oldp, const char *newp) {
    if (readonly_mode) {
        return -1;
    }
    be_ctx_t *bc = c;
    char a[160], b[160];
    lfspath(a, sizeof(a), oldp);
    lfspath(b, sizeof(b), newp);
    return lfs2_rename(bc->lfs, a, b) < 0 ? -1 : 0;
}
static int be_mkdir(void *c, const char *path) {
    if (readonly_mode) {
        return -1;
    }
    be_ctx_t *bc = c;
    char p[160];
    lfspath(p, sizeof(p), path);
    int r = lfs2_mkdir(bc->lfs, p);
    return (r < 0 && r != LFS2_ERR_EXIST) ? -1 : 0;
}
static int be_fs_usage(void *c, uint64_t *total, uint64_t *used) {
    be_ctx_t *bc = c;
    const struct lfs2_config *cfg = bc->lfs->cfg;
    if (!cfg || cfg->block_count == 0 || cfg->block_size == 0) {
        return -1;
    }
    lfs2_ssize_t u = lfs2_fs_size(bc->lfs); // used blocks (incl. metadata)
    if (u < 0) {
        return -1;
    }
    *total = (uint64_t)cfg->block_count * cfg->block_size;
    *used = (uint64_t)u * cfg->block_size;
    return 0;
}
static const fatbridge_backend_t real_backend = {
    .ctx = &real_ctx, .list = be_list, .read = be_read, .write = be_write,
    .commit = be_commit, .remove = be_remove, .rename = be_rename, .mkdir = be_mkdir,
    .fs_usage = be_fs_usage,
};

static fatbridge_t v;
static bool setup_done;
static volatile bool host_ejected;
static volatile uint32_t last_read_ms;   // last host READ10 (browsing/copy-from)
static volatile uint32_t last_write_ms;  // last host WRITE10 (copy-to/edit)
static uint32_t commit_total;            // pending file clusters captured at eject (for %)
static uint32_t done_at_ms;              // when the commit drained (hold 100% before reboot)

// All of fatbridge's heap-allocated working buffers, kept alive by ONE GC root
// (the struct below) instead of one root pointer each. The GC traces this block,
// finds the pointers, and keeps the buffers - so adding more tracked RAM just
// means another field here, not another MP_REGISTER_ROOT_POINTER.
typedef struct {
    void *files;     // node table (fatbridge_file_t[])
    void *wbuf;      // write-back cluster cache
    void *fat;       // host-FAT chain mirror
    void *filebuf;   // littlefs commit-file cache
    void *filebuf_r; // littlefs read cache (separate from the open commit file)
} fatbridge_bufs_t;

// service() status codes (also documented in modules/python/_msc.py)
#define FB_IDLE       0
#define FB_READING    1
#define FB_WRITING    2
#define FB_COMMITTING 3   // host ejected; draining cache to flash (use commit_progress())
#define FB_DONE       4   // drained; about to reboot to normal mode
#define FB_ACTIVE_MS  250 // how long after an op to still call it "active"

// ---- C API consumed by ports/rp2/msc_disk.c (the live USB-MSC callbacks) ----
bool fatbridge_active(void) {
    return setup_done && !host_ejected;
}
bool fatbridge_readonly(void) {
    return readonly_mode;
}
void fatbridge_msc_capacity(uint32_t *block_count, uint16_t *block_size) {
    if (setup_done) {
        fatbridge_capacity(&v, block_count, block_size);
    } else {
        *block_count = 0;
        *block_size = 512;
    }
}
int32_t fatbridge_msc_read(uint32_t lba, uint32_t off, void *buf, uint32_t len) {
    last_read_ms = mp_hal_ticks_ms();
    return setup_done ? fatbridge_read(&v, lba, off, buf, len) : -1;
}
// Cache-only: the MSC callback must NOT touch flash (an lfs2 commit is many
// flash ops with IRQs masked; over a bulk burst that starves the USB task and
// overflows its event queue). Flash commits are driven by the msc_mode() loop.
int32_t fatbridge_msc_write(uint32_t lba, uint32_t off, uint8_t *buf, uint32_t len) {
    last_write_ms = mp_hal_ticks_ms();
    return setup_done ? fatbridge_write(&v, lba, off, buf, len) : -1;
}
// Host issued START STOP UNIT (load_eject, stop) - i.e. the user ejected. We
// must NOT reboot here (the write cache may still hold uncommitted data); the
// msc_mode() loop notices, drains to flash, then reboots.
void fatbridge_msc_eject(void) {
    host_ejected = true;
}

// ---- set up the synthesised volume over the mounted flash littlefs ----
static void expose_real(bool rw) {
    readonly_mode = !rw;
    host_ejected = false;
    real_lfs = NULL;
    struct lfs2_config *cfg = NULL;
    for (mp_vfs_mount_t *m = MP_STATE_VM(vfs_mount_table); m != NULL; m = m->next) {
        if (mp_obj_get_type(m->obj) == &mp_type_vfs_lfs2) {
            fatbridge_lfs2_vfs_t *vp = MP_OBJ_TO_PTR(m->obj);
            real_lfs = &vp->lfs;
            cfg = &vp->config;
            break;
        }
    }
    if (real_lfs == NULL) {
        mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT("no littlefs mounted"));
    }
    real_ctx.lfs = real_lfs;
    real_ctx.fcfg = &real_fcfg;
    // Present the REAL littlefs size (block_count*block_size) with accurate free
    // space (see fs_usage). 2 KB clusters keep the cache space-efficient.
    uint32_t total_bytes = (uint32_t)((uint64_t)cfg->block_count * cfg->block_size);
    if (total_bytes < 1u * 1024 * 1024) {
        total_bytes = 13u * 1024 * 1024; // fallback if the config lacks a count
    }
    int max_files = 1024;                  // every file/subdir/._ sidecar takes a node
    size_t wlen = 6u * 1024 * 1024;        // PSRAM write-back cache (FB is in SRAM)
    uint32_t fat_cap = total_bytes / 2048u + 16; // entries >= total_clusters + 2

    // One GC root for all working buffers (see fatbridge_bufs_t).
    fatbridge_bufs_t *b = m_new(fatbridge_bufs_t, 1);
    MP_STATE_PORT(fatbridge_bufs) = b;
    b->filebuf = m_new(uint8_t, cfg->cache_size);
    b->filebuf_r = m_new(uint8_t, cfg->cache_size);
    b->files = m_new(uint8_t, max_files * sizeof(fatbridge_file_t));
    b->wbuf = m_new(uint8_t, wlen);
    b->fat = m_new(uint16_t, fat_cap);
    real_fcfg.buffer = b->filebuf;
    read_fcfg.buffer = b->filebuf_r;
    cm_open = false;

    int rc = fatbridge_init(&v, &real_backend, total_bytes, 4,
        (fatbridge_file_t *)b->files, max_files,
        b->wbuf, wlen,
        (uint16_t *)b->fat, fat_cap);
    if (rc < 0) {
        mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("bad FAT geometry"));
    }
    // Unique volume serial per expose so the host doesn't serve a stale cached
    // mount across reboots.
    v.vol_id = 0x1337c0deu ^ mp_hal_ticks_ms();
    // Volume label (space-padded to 11, per the board config).
    memset(v.vol_label, ' ', sizeof(v.vol_label));
    const char *lbl = MICROPY_HW_FATBRIDGE_LABEL;
    for (int i = 0; i < (int)sizeof(v.vol_label) && lbl[i]; i++) {
        v.vol_label[i] = lbl[i];
    }
    last_read_ms = last_write_ms = 0;
    commit_total = 0;
    done_at_ms = 0;
    setup_done = true;
}

// fatbridge.msc_mode(): present the badge littlefs as a USB drive and service it
// until the host unmounts/ejects (or the cable is pulled, or Ctrl-C), committing
// continuously; then drain the last writes and reboot back to normal mode.
// Never returns. For boards without a reset button: call this from a menu/app.
static mp_obj_t fb_msc_mode(void) {
    expose_real(true);              // set up the synthesised volume over littlefs
    rp2_tud_set_msc_ready();        // make the MSC LUN media "ready" -> host mounts
    bool seen = false;
    for (;;) {
        mp_usbd_task();             // service USB (caches host writes)
        if (setup_done) {
            fatbridge_flush_step(&v); // commit at most one cluster
        }
        mp_handle_pending(true);    // Ctrl-C -> exit to normal mode
        if (tud_mounted()) {
            seen = true;
        }
        if (host_ejected || (seen && !tud_mounted())) {
            break;                  // host done -> drain + reboot
        }
    }
    while (setup_done && fatbridge_flush_step(&v)) {   // finish committing
        mp_usbd_task();
    }
    uint32_t t = mp_hal_ticks_ms();
    while ((uint32_t)(mp_hal_ticks_ms() - t) < 400) {  // let host finish unmount
        mp_usbd_task();
    }
    watchdog_reboot(0, 0, 0);       // clean reboot -> normal mode
    for (;;) {
    }
    return mp_const_none;           // unreachable
}
static MP_DEFINE_CONST_FUN_OBJ_0(fb_msc_mode_obj, fb_msc_mode);

// fatbridge.expose(): present the badge littlefs as a USB drive, non-blocking.
// Pair with service() driven from the app's update() loop (keeps the UI alive).
static mp_obj_t fb_expose(void) {
    expose_real(true);
    rp2_tud_set_msc_ready();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(fb_expose_obj, fb_expose);

// fatbridge.service(): drive USB + commit a bounded chunk to flash. Call every
// frame from the app's update() loop. Returns a status code for the UI:
//   0 IDLE, 1 READING (host browsing/copy-from), 2 WRITING (copy-to/edit),
//   3 COMMITTING (host ejected, draining cache - see commit_progress()),
//   4 DONE (drained, about to reboot to normal mode).
// On eject it keeps the UI alive (returns 3 with progress, then 4) and reboots
// itself once the "done" screen has been shown briefly.
static mp_obj_t fb_service(void) {
    if (!setup_done) {
        return MP_OBJ_NEW_SMALL_INT(FB_IDLE);
    }
    // Snapshot the pending commit work the moment we notice the eject (before we
    // drain any of it), for the progress denominator.
    if (host_ejected && commit_total == 0) {
        commit_total = fatbridge_pending_clusters(&v);
        if (commit_total == 0) {
            commit_total = 1;
        }
    }
    bool work = false;
    for (int i = 0; i < 64; i++) {       // service USB + commit a bounded chunk
        mp_usbd_task();
        if (fatbridge_flush_step(&v)) {  // true while there's real commit work left
            work = true;
        }
    }
    if (host_ejected) {
        // flush_step reporting no work is the authoritative "done" signal -
        // leftover cached dir-table/free clusters are NOT pending work.
        if (work) {
            done_at_ms = 0;
            return MP_OBJ_NEW_SMALL_INT(FB_COMMITTING);
        }
        // Drained: hold the "100% / saved" screen briefly so it's clearly seen.
        if (done_at_ms == 0) {
            done_at_ms = mp_hal_ticks_ms();
        }
        if ((uint32_t)(mp_hal_ticks_ms() - done_at_ms) < 1200) {
            return MP_OBJ_NEW_SMALL_INT(FB_DONE);
        }
        uint32_t t = mp_hal_ticks_ms();  // let the host finish its unmount handshake
        while ((uint32_t)(mp_hal_ticks_ms() - t) < 200) {
            mp_usbd_task();
        }
        watchdog_reboot(0, 0, 0);        // clean reboot -> normal mode
        for (;;) {
        }
    }
    uint32_t now = mp_hal_ticks_ms();
    if (last_write_ms && (uint32_t)(now - last_write_ms) < FB_ACTIVE_MS) {
        return MP_OBJ_NEW_SMALL_INT(FB_WRITING);
    }
    if (last_read_ms && (uint32_t)(now - last_read_ms) < FB_ACTIVE_MS) {
        return MP_OBJ_NEW_SMALL_INT(FB_READING);
    }
    return MP_OBJ_NEW_SMALL_INT(FB_IDLE);
}
static MP_DEFINE_CONST_FUN_OBJ_0(fb_service_obj, fb_service);

// fatbridge.commit_progress(): 0.0..1.0 fraction of the post-eject commit done.
// Only meaningful while service() reports COMMITTING/DONE.
static mp_obj_t fb_commit_progress(void) {
    if (!setup_done || commit_total == 0) {
        return mp_obj_new_float(0.0f);
    }
    uint32_t left = fatbridge_pending_clusters(&v);
    float p = 1.0f - (float)left / (float)commit_total;
    if (p < 0.0f) {
        p = 0.0f;
    }
    if (p > 1.0f) {
        p = 1.0f;
    }
    return mp_obj_new_float(p);
}
static MP_DEFINE_CONST_FUN_OBJ_0(fb_commit_progress_obj, fb_commit_progress);

// fatbridge.overflow(): True if any host write was dropped this session (a copy
// larger than the cache could hold before it could be committed). For UI warnings.
static mp_obj_t fb_overflow(void) {
    return mp_obj_new_bool(setup_done && v.overflow);
}
static MP_DEFINE_CONST_FUN_OBJ_0(fb_overflow_obj, fb_overflow);

static const mp_rom_map_elem_t fatbridge_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_fatbridge) },
    { MP_ROM_QSTR(MP_QSTR_msc_mode), MP_ROM_PTR(&fb_msc_mode_obj) },
    { MP_ROM_QSTR(MP_QSTR_expose), MP_ROM_PTR(&fb_expose_obj) },
    { MP_ROM_QSTR(MP_QSTR_service), MP_ROM_PTR(&fb_service_obj) },
    { MP_ROM_QSTR(MP_QSTR_commit_progress), MP_ROM_PTR(&fb_commit_progress_obj) },
    { MP_ROM_QSTR(MP_QSTR_overflow), MP_ROM_PTR(&fb_overflow_obj) },
};
static MP_DEFINE_CONST_DICT(fatbridge_globals, fatbridge_globals_table);

const mp_obj_module_t fatbridge_module = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&fatbridge_globals,
};
MP_REGISTER_MODULE(MP_QSTR_fatbridge, fatbridge_module);
MP_REGISTER_ROOT_POINTER(void *fatbridge_bufs);
