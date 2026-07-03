// fat_defs.h - FAT on-disk structure constants and little-endian helpers.
//
// Portable, no dependencies beyond <stdint.h>/<string.h>. All multi-byte fields
// in FAT are little-endian; we access raw byte buffers via the rd/wr helpers
// below rather than packed structs, so this is alignment- and endian-safe on
// any target (including the RP2).
#ifndef FATLFS_FAT_DEFS_H
#define FATLFS_FAT_DEFS_H

#include <stdint.h>
#include <string.h>

// ---- Fixed geometry ----
#define FAT_SECTOR_SIZE      512u
#define FAT_DIRENT_SIZE      32u      // bytes per directory entry
#define FAT_RESERVED_SECTORS 1u       // FAT12/16 convention: boot sector only
#define FAT_NUM_FATS         2u
#define FAT_FIRST_DATA_CLUSTER 2u     // cluster numbering starts at 2
#define FAT_MEDIA_FIXED      0xF8u

// FAT16 cluster-count window: below the minimum, hosts treat the volume as
// FAT12; above the maximum, as FAT32. Geometry is clamped into this range.
// At 512 B clusters this allows honest volume sizes from ~2 MB to ~32 MB.
#define FAT16_MIN_CLUSTERS   4085u
#define FAT16_MAX_CLUSTERS   65524u

// ---- On-disk FAT16 entry values ----
#define FAT16_EOC            0xFFFFu   // end-of-chain marker we write
#define FAT16_BAD            0xFFF7u

// ---- Internal cluster-chain semantics ----
// The in-RAM FAT keeps a 28-bit FAT32-style representation regardless of the
// on-disk format; serve/apply translate to/from 16-bit entries at the sector
// boundary. This keeps every chain walk format-agnostic.
#define FAT_ENTRY_MASK       0x0FFFFFFFu
#define FAT_FREE             0x00000000u
#define FAT_EOC              0x0FFFFFFFu   // end-of-chain marker we write
#define FAT_BAD              0x0FFFFFF7u
#define FAT_IS_EOC(v)        (((v) & FAT_ENTRY_MASK) >= 0x0FFFFFF8u)

// ---- Directory entry attribute bits ----
#define ATTR_READ_ONLY 0x01u
#define ATTR_HIDDEN    0x02u
#define ATTR_SYSTEM    0x04u
#define ATTR_VOLUME_ID 0x08u
#define ATTR_DIRECTORY 0x10u
#define ATTR_ARCHIVE   0x20u
#define ATTR_LONG_NAME 0x0Fu   // RO|HIDDEN|SYSTEM|VOLUME_ID
#define ATTR_LONG_MASK 0x3Fu

// ---- Directory entry field offsets (within a 32-byte entry) ----
#define DIR_Name       0
#define DIR_Attr       11
#define DIR_NTRes      12
#define DIR_CrtTimeTh  13
#define DIR_CrtTime    14
#define DIR_CrtDate    16
#define DIR_LstAccDate 18
#define DIR_FstClusHI  20
#define DIR_WrtTime    22
#define DIR_WrtDate    24
#define DIR_FstClusLO  26
#define DIR_FileSize   28

// ---- Long-file-name entry field offsets ----
#define LDIR_Ord       0
#define LDIR_Name1     1     // 5 UTF-16 chars
#define LDIR_Attr      11    // == ATTR_LONG_NAME
#define LDIR_Type      12
#define LDIR_Chksum    13
#define LDIR_Name2     14    // 6 UTF-16 chars
#define LDIR_FstClusLO 26    // always 0
#define LDIR_Name3     28    // 2 UTF-16 chars
#define LDIR_LAST_MASK 0x40  // OR'd into ord of the last (highest) LFN entry
#define LFN_CHARS_PER_ENTRY 13

// Special first-byte markers in DIR_Name[0].
#define DIRENT_FREE       0xE5u  // deleted / free-but-more-follow
#define DIRENT_END        0x00u  // free and no further used entries
#define DIRENT_KANJI_E5   0x05u  // real 0xE5 first char escaped as 0x05

// ---- Little-endian accessors on raw byte buffers ----
static inline uint16_t fat_rd16(const uint8_t *p) {
    return (uint16_t)(p[0] | ((uint16_t)p[1] << 8));
}
static inline uint32_t fat_rd32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static inline void fat_wr16(uint8_t *p, uint16_t v) {
    p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8);
}
static inline void fat_wr32(uint8_t *p, uint32_t v) {
    p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);
}

// LFN checksum computed over the 11-byte 8.3 short name.
static inline uint8_t fat_lfn_checksum(const uint8_t *short_name11) {
    uint8_t sum = 0;
    for (int i = 0; i < 11; i++) {
        sum = (uint8_t)(((sum & 1) ? 0x80 : 0) + (sum >> 1) + short_name11[i]);
    }
    return sum;
}

// Read/write the 28-bit cluster pointer stored in a directory entry.
static inline uint32_t fat_dirent_cluster(const uint8_t *e) {
    return ((uint32_t)fat_rd16(e + DIR_FstClusHI) << 16) | fat_rd16(e + DIR_FstClusLO);
}
static inline void fat_dirent_set_cluster(uint8_t *e, uint32_t clus) {
    fat_wr16(e + DIR_FstClusHI, (uint16_t)(clus >> 16));
    fat_wr16(e + DIR_FstClusLO, (uint16_t)(clus & 0xFFFF));
}

#endif // FATLFS_FAT_DEFS_H
