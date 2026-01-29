#include "mp_helpers.hpp"
#include "picovector.hpp"

extern "C" {

  #include "py/stream.h"
  #include "py/reader.h"
  #include "py/runtime.h"
  #include "extmod/vfs.h"

  #ifndef NO_QSTR
    #include "PNGdec.h"
  #endif

  void *pngdec_open_callback(const char *filename, int32_t *size) {
    mp_obj_t fn = mp_obj_new_str(filename, (mp_uint_t)strlen(filename));

    mp_obj_t args[2] = {
        fn,
        MP_ROM_QSTR(MP_QSTR_r),
    };

    // Stat the file to get its size
    // example tuple response: (32768, 0, 0, 0, 0, 0, 5153, 1654709815, 1654709815, 1654709815)
    mp_obj_t stat = mp_vfs_stat(fn);
    mp_obj_tuple_t *tuple = (mp_obj_tuple_t*)MP_OBJ_TO_PTR(stat);
    *size = mp_obj_get_int(tuple->items[6]);

    png_handle_t *png_handle = (png_handle_t *)m_tracked_calloc(1, sizeof(png_handle_t));
    png_handle->fhandle = mp_vfs_open(MP_ARRAY_SIZE(args), &args[0], (mp_map_t *)&mp_const_empty_map);

    return (void *)png_handle;
  }

  void pngdec_close_callback(void *handle) {
    png_handle_t *png_handle = (png_handle_t *)(handle);
    mp_stream_close(png_handle->fhandle);
    m_tracked_free(handle);
  }

  int32_t pngdec_read_callback(PNGFILE *png, uint8_t *p, int32_t c) {
    png_handle_t *png_handle = (png_handle_t *)(png->fHandle);
    int error;
    return mp_stream_read_exactly(png_handle->fhandle, p, c, &error);
  }

  // Re-implementation of stream.c/static mp_obj_t stream_seek(size_t n_args, const mp_obj_t *args)
  int32_t pngdec_seek_callback(PNGFILE *png, int32_t p) {
    png_handle_t *png_handle = (png_handle_t *)(png->fHandle);
    struct mp_stream_seek_t seek_s;
    seek_s.offset = p;
    seek_s.whence = SEEK_SET;

    const mp_stream_p_t *stream_p = mp_get_stream(png_handle->fhandle);

    int error;
    mp_uint_t res = stream_p->ioctl(png_handle->fhandle, MP_STREAM_SEEK, (mp_uint_t)(uintptr_t)&seek_s, &error);
    if (res == MP_STREAM_ERROR) {
        mp_raise_msg_varg(&mp_type_OSError, MP_ERROR_TEXT("PNG: seek failed with %d"), error);
    }

    return seek_s.offset;
  }

  void pngdec_decode_callback(PNGDRAW *pDraw) {
    image_t *target = (image_t *)pDraw->pUser;

    uint8_t *psrc = (uint8_t *)pDraw->pPixels;
    int w = pDraw->iWidth;

    switch(pDraw->iPixelType) {
      case PNG_PIXEL_TRUECOLOR: {
        uint32_t *pdst = (uint32_t *)target->ptr(0, pDraw->y);
        while(w--) {
          rgb_color_t c(psrc[0], psrc[1], psrc[2], 255);
          *pdst = c._p;
          psrc += 3;
          pdst++;
        }
      } break;

      case PNG_PIXEL_TRUECOLOR_ALPHA: {
        uint32_t *pdst = (uint32_t *)target->ptr(0, pDraw->y);
        while(w--) {
          rgb_color_t c(psrc[0], psrc[1], psrc[2], psrc[3]);
          *pdst = c._p;
          psrc += 4;
          pdst++;
        }
      } break;

      case PNG_PIXEL_INDEXED: {
        if(target->has_palette()) {
          for(int i = 0; i < 256; i++) {
            rgb_color_t c(
              pDraw->pPalette[i * 3 + 0],
              pDraw->pPalette[i * 3 + 1],
              pDraw->pPalette[i * 3 + 2],
              pDraw->iHasAlpha ? pDraw->pPalette[768 + i] : 255
            );
            target->palette(i, c._p);
          }

          uint8_t *pdst = (uint8_t *)target->ptr(0, pDraw->y);
          while(w--) {
            *pdst = *psrc;
            pdst++;
            psrc++;
          }
        } else {
          uint32_t *pdst = (uint32_t *)target->ptr(0, pDraw->y);
          while(w--) {
            *pdst = rgb_color_t(
              pDraw->pPalette[*psrc * 3 + 0],
              pDraw->pPalette[*psrc * 3 + 1],
              pDraw->pPalette[*psrc * 3 + 2],
              pDraw->iHasAlpha ? pDraw->pPalette[768 + *psrc] : 255
            )._p;
            psrc++;
            pdst++;
          }
        }
      } break;
      case PNG_PIXEL_GRAYSCALE: {
        uint32_t *pdst = (uint32_t *)target->ptr(0, pDraw->y);
        while(w--) {
          uint8_t src = *psrc;
          // do something with index here

          switch(pDraw->iBpp) {
            case 8: {
              *pdst = rgb_color_t(src, src, src, 255)._p;
              pdst++;
            } break;

            case 4: {
              int src1 = (src & 0xf0) | ((src & 0xf0) >> 4);
              int src2 = (src & 0x0f) | ((src & 0x0f) << 4);
              *pdst = rgb_color_t(src1, src1, src1, 255)._p;
              pdst++;
              *pdst = rgb_color_t(src2, src2, src2, 255)._p;
              pdst++;
            } break;

            case 1: {
              for(int i = 0; i < 8; i++) {
                int v = src & 0b10000000 ? 255 : 0;
                *pdst = rgb_color_t(v, v, v, 255)._p;
                pdst++;
                src <<= 1;
              }
            } break;
          }

          psrc++;
        }
      } break;

      default: {
        // TODO: raise file not supported error
      } break;
    }

//     } else if (pDraw->iPixelType == PNG_PIXEL_INDEXED) {
//         for(int x = 0; x < pDraw->iWidth; x++) {
//             uint8_t i = 0;
//             if(pDraw->iBpp == 8) {  // 8bpp
//                 i = *pixel++;
//             } else if (pDraw->iBpp == 4) {  // 4bpp
//                 i = *pixel;
//                 i >>= (x & 0b1) ? 0 : 4;
//                 i &= 0xf;
//                 if (x & 1) pixel++;
//             } else if (pDraw->iBpp == 2) {  // 2bpp
//                 i = *pixel;
//                 i >>= 6 - ((x & 0b11) << 1);
//                 i &= 0x3;
//                 if ((x & 0b11) == 0b11) pixel++;
//             } else {  // 1bpp
//                 i = *pixel;
//                 i >>= 7 - (x & 0b111);
//                 i &= 0b1;
//                 if ((x & 0b111) == 0b111) pixel++;
//             }
//             if(x < target->source.x || x >= target->source.x + target->source.w) continue;
//             // grab the colour from the palette
//             uint8_t r = pDraw->pPalette[(i * 3) + 0];
//             uint8_t g = pDraw->pPalette[(i * 3) + 1];
//             uint8_t b = pDraw->pPalette[(i * 3) + 2];
//             uint8_t a = pDraw->iHasAlpha ? pDraw->pPalette[768 + i] : 1;
//             if (a) {
//                 if (current_graphics->pen_type == PicoGraphics::PEN_RGB332) {
//                     if (current_mode == MODE_POSTERIZE || current_mode == MODE_COPY) {
//                         // Posterized output to RGB332
//                         current_graphics->set_pen(RGB(r, g, b).to_rgb332());
//                         current_graphics->rectangle({current_position.x, current_position.y, scale.x, scale.y});
//                     } else {
//                         // Dithered output to RGB332
//                         for(auto px = 0; px < scale.x; px++) {
//                             for(auto py = 0; py < scale.y; py++) {
//                                 current_graphics->set_pixel_dither(current_position + Point{px, py}, {r, g, b});
//                             }
//                         }
//                     }
//                 } else if(current_graphics->pen_type == PicoGraphics::PEN_P8
//                     || current_graphics->pen_type == PicoGraphics::PEN_P4
//                     || current_graphics->pen_type == PicoGraphics::PEN_3BIT
//                     || current_graphics->pen_type == PicoGraphics::PEN_INKY7) {

//                         // Copy raw palette indexes over
//                         if(current_mode == MODE_COPY) {
//                             if(current_palette_offset > 0) {
//                                 i = ((int16_t)(i) + current_palette_offset) & 0xff;
//                             }
//                             current_graphics->set_pen(i);
//                             current_graphics->rectangle({current_position.x, current_position.y, scale.x, scale.y});
//                         // Posterized output to the available palete
//                         } else if(current_mode == MODE_POSTERIZE) {
//                             int closest = RGB(r, g, b).closest(current_graphics->get_palette(), current_graphics->get_palette_size());
//                             if (closest == -1) {
//                                 closest = 0;
//                             }
//                             current_graphics->set_pen(closest);
//                             current_graphics->rectangle({current_position.x, current_position.y, scale.x, scale.y});
//                         } else {
//                             for(auto px = 0; px < scale.x; px++) {
//                                 for(auto py = 0; py < scale.y; py++) {
//                                     current_graphics->set_pixel_dither(current_position + Point{px, py}, {r, g, b});
//                                 }
//                             }
//                         }
//                 } else {
//                     current_graphics->set_pen(r, g, b);
//                     current_graphics->rectangle({current_position.x, current_position.y, scale.x, scale.y});
//                 }
//             }
//             current_position += step;
//         }
//     }

    // samples of other pixel formats at end of file...
  }
}























//     } else if (pDraw->iPixelType == PNG_PIXEL_GRAYSCALE) {
//         for(int x = 0; x < pDraw->iWidth; x++) {
//             uint8_t i = 0;
//             if(pDraw->iBpp == 8) {  // 8bpp
//                 i = *pixel++; // Already 8bpc
//             } else if (pDraw->iBpp == 4) {  // 4bpp
//                 i = *pixel;
//                 i >>= (x & 0b1) ? 0 : 4;
//                 i &= 0xf;
//                 if (x & 1) pixel++;
//                 // Just copy the colour into the upper and lower nibble
//                 if(current_mode != MODE_COPY) {
//                     i = (i << 4) | i;
//                 }
//             } else if (pDraw->iBpp == 2) {  // 2bpp
//                 i = *pixel;
//                 i >>= 6 - ((x & 0b11) << 1);
//                 i &= 0x3;
//                 if ((x & 0b11) == 0b11) pixel++;
//                 // Evenly spaced 4-colour palette
//                 if(current_mode != MODE_COPY) {
//                     i = (0xFFB86800 >> (i * 8)) & 0xFF;
//                 }
//             } else {  // 1bpp
//                 i = *pixel;
//                 i >>= 7 - (x & 0b111);
//                 i &= 0b1;
//                 if ((x & 0b111) == 0b111) pixel++;
//                 if(current_mode != MODE_COPY) {
//                     i = i ? 255 : 0;
//                 }
//             }
//             if(x < target->source.x || x >= target->source.x + target->source.w) continue;

//             //mp_printf(&mp_plat_print, "Drawing pixel at %dx%d, %dbpp, value %d\n", current_position.x, current_position.y, pDraw->iBpp, i);
//             if (current_mode != MODE_PEN) {
//                 // Allow greyscale PNGs to be copied just like an indexed PNG
//                 // since we might want to offset and recolour them.
//                 if(current_mode == MODE_COPY
//                     && (current_graphics->pen_type == PicoGraphics::PEN_P8
//                     || current_graphics->pen_type == PicoGraphics::PEN_P4
//                     || current_graphics->pen_type == PicoGraphics::PEN_3BIT
//                     || current_graphics->pen_type == PicoGraphics::PEN_INKY7)) {
//                     if(current_palette_offset > 0) {
//                         i = ((int16_t)(i) + current_palette_offset) & 0xff;
//                     }
//                     current_graphics->set_pen(i);
//                 } else {
//                     current_graphics->set_pen(i, i, i);
//                 }
//             }
//             if (current_mode != MODE_PEN || i == 0) {
//                 current_graphics->rectangle({current_position.x, current_position.y, scale.x, scale.y});
//             }

//             current_position += step;
//         }
//     } else if (pDraw->iPixelType == PNG_PIXEL_INDEXED) {
//         for(int x = 0; x < pDraw->iWidth; x++) {
//             uint8_t i = 0;
//             if(pDraw->iBpp == 8) {  // 8bpp
//                 i = *pixel++;
//             } else if (pDraw->iBpp == 4) {  // 4bpp
//                 i = *pixel;
//                 i >>= (x & 0b1) ? 0 : 4;
//                 i &= 0xf;
//                 if (x & 1) pixel++;
//             } else if (pDraw->iBpp == 2) {  // 2bpp
//                 i = *pixel;
//                 i >>= 6 - ((x & 0b11) << 1);
//                 i &= 0x3;
//                 if ((x & 0b11) == 0b11) pixel++;
//             } else {  // 1bpp
//                 i = *pixel;
//                 i >>= 7 - (x & 0b111);
//                 i &= 0b1;
//                 if ((x & 0b111) == 0b111) pixel++;
//             }
//             if(x < target->source.x || x >= target->source.x + target->source.w) continue;
//             // grab the colour from the palette
//             uint8_t r = pDraw->pPalette[(i * 3) + 0];
//             uint8_t g = pDraw->pPalette[(i * 3) + 1];
//             uint8_t b = pDraw->pPalette[(i * 3) + 2];
//             uint8_t a = pDraw->iHasAlpha ? pDraw->pPalette[768 + i] : 1;
//             if (a) {
//                 if (current_graphics->pen_type == PicoGraphics::PEN_RGB332) {
//                     if (current_mode == MODE_POSTERIZE || current_mode == MODE_COPY) {
//                         // Posterized output to RGB332
//                         current_graphics->set_pen(RGB(r, g, b).to_rgb332());
//                         current_graphics->rectangle({current_position.x, current_position.y, scale.x, scale.y});
//                     } else {
//                         // Dithered output to RGB332
//                         for(auto px = 0; px < scale.x; px++) {
//                             for(auto py = 0; py < scale.y; py++) {
//                                 current_graphics->set_pixel_dither(current_position + Point{px, py}, {r, g, b});
//                             }
//                         }
//                     }
//                 } else if(current_graphics->pen_type == PicoGraphics::PEN_P8
//                     || current_graphics->pen_type == PicoGraphics::PEN_P4
//                     || current_graphics->pen_type == PicoGraphics::PEN_3BIT
//                     || current_graphics->pen_type == PicoGraphics::PEN_INKY7) {

//                         // Copy raw palette indexes over
//                         if(current_mode == MODE_COPY) {
//                             if(current_palette_offset > 0) {
//                                 i = ((int16_t)(i) + current_palette_offset) & 0xff;
//                             }
//                             current_graphics->set_pen(i);
//                             current_graphics->rectangle({current_position.x, current_position.y, scale.x, scale.y});
//                         // Posterized output to the available palete
//                         } else if(current_mode == MODE_POSTERIZE) {
//                             int closest = RGB(r, g, b).closest(current_graphics->get_palette(), current_graphics->get_palette_size());
//                             if (closest == -1) {
//                                 closest = 0;
//                             }
//                             current_graphics->set_pen(closest);
//                             current_graphics->rectangle({current_position.x, current_position.y, scale.x, scale.y});
//                         } else {
//                             for(auto px = 0; px < scale.x; px++) {
//                                 for(auto py = 0; py < scale.y; py++) {
//                                     current_graphics->set_pixel_dither(current_position + Point{px, py}, {r, g, b});
//                                 }
//                             }
//                         }
//                 } else {
//                     current_graphics->set_pen(r, g, b);
//                     current_graphics->rectangle({current_position.x, current_position.y, scale.x, scale.y});
//                 }
//             }
//             current_position += step;
//         }
//     }
