// fatlfs: expose the badge's littlefs storage to a USB host as a FAT16 drive so
// files can be copied/edited over USB while the on-device filesystem stays
// littlefs (one resilient, unified partition). FAT16 so the advertised volume
// matches the real ~13 MB partition (FAT32's cluster minimum would force
// >=32 MB) - an oversized copy fails upfront in the host's UI.
//
// This is the MicroPython glue + the C API that ports/rp2/msc_disk.c calls to
// serve the live USB-MSC drive. The FAT16<->littlefs translation core is in
// fatlfs.c; the embedded PSRAM allocator is in fatlfs_arena.c.
//
// Model (vs the old fatbridge): host writes are STAGED in RAM (never flash)
// inside the USB callback. They commit to littlefs at flush barriers - the host's
// SYNCHRONIZE CACHE, write-idle pauses, and eject - in one reconcile pass that
// creates/updates every file atomically. This avoids the O(n^2) per-file
// re-commit that a synthesise-on-read design forced, and it gets multi-cluster
// directories, AppleDouble sidecars and >cache single files right (proven on host).
#include <string.h>
#include "py/runtime.h"
#include "py/mphal.h"
#include "extmod/vfs.h"
#include "lib/littlefs/lfs2.h"
#include "fatlfs.h"
#include "fatlfs_arena.h"

// FAT volume label shown for the badge drive; set per board in mpconfigboard.h.
// (Kept on the old macro name so board configs don't need touching.)
#ifndef MICROPY_HW_FATLFS_LABEL
#define MICROPY_HW_FATLFS_LABEL "BADGE"
#endif

// PSRAM arena for all of fatlfs's allocations: the FAT-mirror arrays sized by
// cluster count (~750 KB since FAT16), per-file caches, the committed snapshot,
// reconcile scratch, AND the staging buffer. So the staging cap is well under
// the arena size. The badge has an 8 MB GC heap (framebuffer lives in SRAM), so
// we can afford a big arena; a 5 MB cap lets a typical few-MB file stay wholly
// in RAM and skip the slower spill-to-flash path entirely.
#define FATLFS_ARENA_BYTES   (7u * 1024 * 1024)
#define FATLFS_STAGING_MAX   (5u * 1024 * 1024)   // 5 MB in-RAM before spill

// TinyUSB / rp2 glue, forward-declared (tusb.h isn't on the qstr-scan path).
extern void mp_usbd_task(void);
extern bool tud_mounted(void);
extern bool rp2_tud_set_msc_ready(void);
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
} fatlfs_lfs2_vfs_t;

static fatlfs_t *v;                 // the mounted shim (in the arena)
static lfs2_t   *real_lfs;          // the badge's littlefs (for disk_usage)
static bool      setup_done;
static bool      readonly_mode = true;
static volatile bool host_ejected;
static volatile uint32_t last_read_ms;   // last host READ10 (browsing/copy-from)
static volatile uint32_t last_write_ms;  // last host WRITE10 (copy-to/edit)
static volatile bool flush_requested;    // host issued SYNCHRONIZE CACHE
static uint32_t  last_flush_ms;          // last incremental commit (paces long copies)
static bool      spilled_session;        // a large file spilled: defer all commits to eject
static bool      commit_seen;            // eject noticed; "saving" screen drawn
static uint32_t  done_at_ms;             // when the flush finished (hold before reboot)
static bool      flush_failed;           // an incremental commit failed; stop retry churn
static bool      write_since_flush;      // host wrote since the last commit attempt
static int       final_rc;               // result of the eject flush (drives DONE vs ERROR)

// service() status codes (mirrored in modules/python/_msc.py)
#define ST_IDLE       0
#define ST_READING    1
#define ST_WRITING    2
#define ST_COMMITTING 3   // host ejected; flushing staged writes to littlefs
#define ST_DONE       4   // flushed; about to reboot to normal mode
#define ST_ERROR      5   // eject flush FAILED (badge disk full?); rebooting anyway
#define ST_ACTIVE_MS  250 // how long after an op to still call it "active"

// Incremental commit pacing. macOS bulk copies can stream with no gaps and never
// send SYNCHRONIZE CACHE, so idle/barrier flushing alone leaves everything for one
// long freeze at eject. So we also flush periodically during an active copy. This
// is safe because reconcile preserves in-flight orphan data (a file whose data is
// written but whose directory entry isn't yet) - completed files commit, the file
// being written stays staged until a later flush. FLUSH_IDLE_MS is the quiet-gap
// trigger; FLUSH_PERIOD_MS caps how long staged writes sit during a gapless copy.
#define FLUSH_IDLE_MS   300
#define FLUSH_PERIOD_MS 750

// ---- C API consumed by ports/rp2/msc_disk.c (the live USB-MSC callbacks) ----
bool fatlfs_active(void) {
    return setup_done && !host_ejected;
}
bool fatlfs_readonly(void) {
    return readonly_mode;
}
void fatlfs_msc_capacity(uint32_t *block_count, uint16_t *block_size) {
    if (setup_done) {
        *block_count = (uint32_t)fatlfs_block_count(v);
        *block_size = (uint16_t)fatlfs_block_size(v);
    } else {
        *block_count = 0;
        *block_size = 512;
    }
}
int32_t fatlfs_msc_read(uint32_t lba, uint32_t off, void *buf, uint32_t len) {
    if (!setup_done) return -1;
    last_read_ms = mp_hal_ticks_ms();
    uint32_t sec = lba + off / 512;         // off is a byte offset within the xfer
    uint32_t n = len / 512;
    if (fatlfs_read(v, sec, n, buf) != FATLFS_OK) return -1;
    return (int32_t)(n * 512);
}
// Stage only - the MSC callback must NOT touch flash. An lfs2 commit is many
// flash ops with IRQs masked; over a bulk burst that starves the USB task and
// overflows its event queue. Commit happens from the msc loop at eject.
int32_t fatlfs_msc_write(uint32_t lba, uint32_t off, uint8_t *buf, uint32_t len) {
    if (!setup_done) return -1;
    last_write_ms = mp_hal_ticks_ms();
    write_since_flush = true;
    uint32_t sec = lba + off / 512;
    uint32_t n = len / 512;
    if (fatlfs_write(v, sec, n, buf) != FATLFS_OK) return -1;
    return (int32_t)(n * 512);
}
// Host issued START STOP UNIT (eject). Do NOT reboot here (staged writes aren't
// committed yet); the msc loop notices, flushes to flash, then reboots.
void fatlfs_msc_eject(void) {
    host_ejected = true;
}
// Host issued SYNCHRONIZE CACHE - a consistency barrier where staged writes are
// safe to commit. Record it; the service loop does the flash-touching flush.
void fatlfs_msc_sync(void) {
    flush_requested = true;
}

// ---- set up the FAT16 view over the mounted flash littlefs ----
static void expose_real(bool rw) {
    // A stale v from a previous expose must not be reachable from the MSC
    // callbacks while we re-init the arena underneath it.
    setup_done = false;
    readonly_mode = !rw;
    host_ejected = false;
    commit_seen = false;
    done_at_ms = 0;
    real_lfs = NULL;
    for (mp_vfs_mount_t *m = MP_STATE_VM(vfs_mount_table); m != NULL; m = m->next) {
        if (mp_obj_get_type(m->obj) == &mp_type_vfs_lfs2) {
            fatlfs_lfs2_vfs_t *vp = MP_OBJ_TO_PTR(m->obj);
            real_lfs = &vp->lfs;
            break;
        }
    }
    if (real_lfs == NULL) {
        mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT("no littlefs mounted"));
    }

    // One big PSRAM buffer, kept alive by a GC root, carved up by the arena
    // allocator that fatlfs.c's malloc/free/calloc/realloc route to.
    uint8_t *arena = MP_STATE_PORT(fatlfs_arena_buf);
    if (arena == NULL) {
        arena = m_new(uint8_t, FATLFS_ARENA_BYTES);
        MP_STATE_PORT(fatlfs_arena_buf) = arena;
    }
    fatlfs_arena_init(arena, FATLFS_ARENA_BYTES);
    v = NULL;

    // Honest volume sizing: advertise the real littlefs partition capacity so a
    // too-big copy fails upfront in the host's UI instead of silently at eject.
    // littlefs metadata/block-rounding overhead means true free space is a bit
    // less than advertised; the ST_ERROR eject path is the backstop for that.
    uint32_t part_bytes = 0;
    if (real_lfs->cfg && real_lfs->cfg->block_count) {
        part_bytes = real_lfs->cfg->block_count * real_lfs->cfg->block_size;
    }

    fatlfs_config_t cfg = {
        .lfs = real_lfs,
        // 512 B clusters: the badge holds many small files (4 KB clusters wasted
        // ~0.5 MB of staging to rounding), and they keep the honest cluster count
        // inside FAT16's [4085, 65524] window - 4 KB clusters would push a 13 MB
        // volume below the FAT12 boundary.
        .cluster_size = 512,
        .cluster_count = part_bytes / 512,   // ~real capacity; mount clamps to FAT16 window
        .staging_max_bytes = FATLFS_STAGING_MAX,
        // Unique serial per expose so the host doesn't serve a stale cached mount.
        .volume_id = 0x1337c0deu ^ mp_hal_ticks_ms(),
        .keep_os_trash = 0,            // drop ._ / .DS_Store instead of storing them
    };
    memset(cfg.volume_label, ' ', sizeof(cfg.volume_label));
    const char *lbl = MICROPY_HW_FATLFS_LABEL;
    for (int i = 0; i < 11 && lbl[i]; i++) cfg.volume_label[i] = lbl[i];

    int rc = fatlfs_mount(&cfg, &v);
    if (rc != FATLFS_OK || v == NULL) {
        mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT("fatlfs mount failed"));
    }
    fatlfs_defer_spill(v, 1);          // never spill (flash) from the USB callback

    last_read_ms = last_write_ms = 0;
    last_flush_ms = mp_hal_ticks_ms();
    spilled_session = false;
    flush_failed = false;
    write_since_flush = false;
    final_rc = FATLFS_OK;
    setup_done = true;
}

// fatlfs.expose(): present the badge littlefs as a USB drive, non-blocking.
// Pair with service() driven from the app's update() loop (keeps the UI alive).
static mp_obj_t fl_expose(void) {
    expose_real(true);
    rp2_tud_set_msc_ready();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(fl_expose_obj, fl_expose);

// fatlfs.service(): drive USB + relieve RAM pressure. Call every frame from the
// app's update() loop. Returns a status code for the UI:
//   0 IDLE, 1 READING, 2 WRITING, 3 COMMITTING (ejected, flushing to flash),
//   4 DONE (flushed, about to reboot), 5 ERROR (flush failed - badge disk
//   full?; rebooting anyway). On eject it draws COMMITTING for one frame (so
// the UI can show "Saving"), then flushes and reboots.
static mp_obj_t fl_service(void) {
    if (!setup_done) {
        return MP_OBJ_NEW_SMALL_INT(ST_IDLE);
    }
    // Pump USB (stage host writes) and relieve RAM pressure. A file larger than
    // the staging cap must spill to flash; each spilled cluster masks IRQs, so we
    // bound the spill per pump. While over the cap we also pump USB fewer times, so
    // the host's writes NAK and throttle back - natural backpressure that lets the
    // spill keep up instead of the buffer ballooning and the UI freezing.
    // Relieve RAM pressure for a file larger than the staging cap. Spilling rebuilds
    // a reverse-FAT table, so it runs at most once per frame (not once per pump - that
    // starved USB into a stall). Over the cap we drain FIRST, then accept only a
    // couple of writes, so spill always outpaces intake and staging can't balloon to
    // an out-of-arena write failure (which the host retries forever = stuck copy).
    // Under the cap we pump freely but stop the instant we cross it, bounding overshoot.
    if (fatlfs_staged_bytes(v) > fatlfs_staging_max(v)) {
        fatlfs_spill(v, 64);         // drain ~32 KB to flash
        mp_usbd_task();              // then accept a little (throttled -> backpressure)
        mp_usbd_task();
        spilled_session = true;
    } else {
        for (int i = 0; i < 64; i++) {
            mp_usbd_task();
            if (fatlfs_staged_bytes(v) > fatlfs_staging_max(v)) break;
        }
    }

    // Incremental commit for the common case (small files): flush at a SYNCHRONIZE
    // CACHE barrier, a write-idle pause, or periodically through a gapless copy
    // (see the FLUSH_* notes). Keeps the eject flush short and gives cavalier-unplug
    // users their files; just a brief frame hitch while it commits. But once
    // anything has SPILLED we stop: reconciling a large file that's still being
    // written churns its spill temp, and a write-idle pause can't be told apart
    // from a mid-file gap (a big image copy stalls on source reads). So a spilled
    // session commits only at eject - the one barrier where the file is provably
    // complete. Small copies never spill, so they keep realtime saves.
    // idle/periodic re-arm only on NEW writes (write_since_flush): a failed or
    // orphan-retaining flush leaves staged bytes behind, and without the gate we'd
    // rerun the full reconcile every frame until the next write. A failed commit
    // (flush_failed) also stops incremental retries - the eject flush is the one
    // retry that matters, and its result is surfaced as ST_ERROR.
    uint32_t now = mp_hal_ticks_ms();
    bool idle = write_since_flush && last_write_ms && (uint32_t)(now - last_write_ms) > FLUSH_IDLE_MS;
    bool periodic = write_since_flush && last_flush_ms && (uint32_t)(now - last_flush_ms) > FLUSH_PERIOD_MS;
    if (!host_ejected && !spilled_session && !flush_failed && fatlfs_dirty(v) &&
        (flush_requested || idle || periodic)) {
        flush_requested = false;
        write_since_flush = false;
        if (fatlfs_flush(v) != FATLFS_OK) flush_failed = true;
        last_flush_ms = mp_hal_ticks_ms();
    } else if (flush_requested) {
        flush_requested = false;   // nothing staged; barrier already satisfied
    }

    if (host_ejected) {
        if (!commit_seen) {
            // First frame after eject: let the caller paint "Saving" before we
            // block in the (single, atomic) reconcile pass.
            commit_seen = true;
            return MP_OBJ_NEW_SMALL_INT(ST_COMMITTING);
        }
        if (done_at_ms == 0) {
            final_rc = fatlfs_flush(v);   // commit every staged write to littlefs
            done_at_ms = mp_hal_ticks_ms();
        }
        // Hold the "saved" screen briefly - or the error screen long enough to be
        // read. Reboot regardless: the staged RAM is lost either way and the badge
        // must come back in a usable state.
        uint32_t hold_ms = (final_rc == FATLFS_OK) ? 1200 : 8000;
        if ((uint32_t)(mp_hal_ticks_ms() - done_at_ms) < hold_ms) {
            return MP_OBJ_NEW_SMALL_INT(final_rc == FATLFS_OK ? ST_DONE : ST_ERROR);
        }
        uint32_t t = mp_hal_ticks_ms();             // let host finish its unmount
        while ((uint32_t)(mp_hal_ticks_ms() - t) < 200) {
            mp_usbd_task();
        }
        watchdog_reboot(0, 0, 0);   // clean reboot -> normal mode
        for (;;) {
        }
    }
    now = mp_hal_ticks_ms();
    if (last_write_ms && (uint32_t)(now - last_write_ms) < ST_ACTIVE_MS) {
        return MP_OBJ_NEW_SMALL_INT(ST_WRITING);
    }
    if (last_read_ms && (uint32_t)(now - last_read_ms) < ST_ACTIVE_MS) {
        return MP_OBJ_NEW_SMALL_INT(ST_READING);
    }
    return MP_OBJ_NEW_SMALL_INT(ST_IDLE);
}
static MP_DEFINE_CONST_FUN_OBJ_0(fl_service_obj, fl_service);

// fatlfs.mem_usage(): (staged_bytes, staging_max) for a RAM-pressure bar. Staged
// bytes rise as the host copies, and fall to ~0 once flushed at eject.
static mp_obj_t fl_mem_usage(void) {
    uint32_t staged = 0, cap = 0;
    if (setup_done) {
        staged = fatlfs_staged_bytes(v);
        cap = fatlfs_staging_max(v);
    }
    mp_obj_t t[2] = { mp_obj_new_int_from_uint(staged), mp_obj_new_int_from_uint(cap) };
    return mp_obj_new_tuple(2, t);
}
static MP_DEFINE_CONST_FUN_OBJ_0(fl_mem_usage_obj, fl_mem_usage);

// fatlfs.disk_usage(): (used, total) bytes of the REAL littlefs storage - how
// full the badge actually is, distinct from the transient staging cache.
static mp_obj_t fl_disk_usage(void) {
    uint64_t total = 0, used = 0;
    if (setup_done && real_lfs && real_lfs->cfg) {
        const struct lfs2_config *c = real_lfs->cfg;
        lfs2_ssize_t u = lfs2_fs_size(real_lfs);
        if (u >= 0 && c->block_count && c->block_size) {
            total = (uint64_t)c->block_count * c->block_size;
            used = (uint64_t)u * c->block_size;
        }
    }
    mp_obj_t t[2] = { mp_obj_new_int_from_ull(used), mp_obj_new_int_from_ull(total) };
    return mp_obj_new_tuple(2, t);
}
static MP_DEFINE_CONST_FUN_OBJ_0(fl_disk_usage_obj, fl_disk_usage);

static const mp_rom_map_elem_t fatlfs_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_fatlfs) },
    { MP_ROM_QSTR(MP_QSTR_expose), MP_ROM_PTR(&fl_expose_obj) },
    { MP_ROM_QSTR(MP_QSTR_service), MP_ROM_PTR(&fl_service_obj) },
    { MP_ROM_QSTR(MP_QSTR_mem_usage), MP_ROM_PTR(&fl_mem_usage_obj) },
    { MP_ROM_QSTR(MP_QSTR_disk_usage), MP_ROM_PTR(&fl_disk_usage_obj) },
};
static MP_DEFINE_CONST_DICT(fatlfs_globals, fatlfs_globals_table);

const mp_obj_module_t fatlfs_module = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&fatlfs_globals,
};
MP_REGISTER_MODULE(MP_QSTR_fatlfs, fatlfs_module);
MP_REGISTER_ROOT_POINTER(void *fatlfs_arena_buf);
