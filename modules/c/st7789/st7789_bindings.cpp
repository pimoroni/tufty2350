#include <cstdio>
#include "hardware/spi.h"
#include "hardware/sync.h"
#include "pico/binary_info.h"
#include "pico/stdlib.h"
#include <new>  // for placement new

#include "st7789.hpp"

using namespace pimoroni;

static ST7789 *display = nullptr;
static uint32_t display_refcount = 0;

#define MP_OBJ_TO_PTR2(o, t) ((t *)(uintptr_t)(o))
#define m_new_class(cls, ...) new(m_new(cls, 1)) cls(__VA_ARGS__)
#define m_del_class(cls, ptr) ptr->~cls();m_del(cls, ptr, 1)

extern "C" {
#include "st7789_bindings.h"
#include "py/builtin.h"

typedef struct _ST7789_obj_t {
    mp_obj_base_t base;
    ST7789 *display;
} ST7789_obj_t;


mp_obj_t st7789_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw, const mp_obj_t *all_args) {
    _ST7789_obj_t *self = mp_obj_malloc_with_finaliser(ST7789_obj_t, &ST7789_type);
    if(!display) {
        display = m_new_class(ST7789);
    }
    self->display = display;
    display_refcount++;
    return MP_OBJ_FROM_PTR(self);
}

mp_obj_t st7789___del__(mp_obj_t self_in) {
    display_refcount--;
    if(display_refcount == 0) {
        m_del_class(ST7789, display);
        display = nullptr;
    }
    return mp_const_none;
}

mp_obj_t st7789_update(mp_obj_t self_in) {
    (void)self_in;
    display->update();
    return mp_const_none;
}

mp_obj_t st7789_command(mp_obj_t self_in, mp_obj_t reg_in, mp_obj_t data_in) {
    (void)self_in;
    uint8_t reg = mp_obj_get_int(reg_in);

    if(mp_obj_is_type(data_in, &mp_type_tuple)) {
        mp_obj_tuple_t *tuple = (mp_obj_tuple_t *)MP_OBJ_TO_PTR(data_in);
        uint8_t data[tuple->len] = {0};
        for(unsigned i = 0u; i < tuple->len; i++) {
            data[i] = mp_obj_get_int(tuple->items[i]);
        }
        display->command(reg, tuple->len, (const char *)data);
        return mp_const_none;
    }

    display->command(reg, 0, NULL);
    return mp_const_none;
}

mp_obj_t st7789_set_backlight(mp_obj_t self_in, mp_obj_t value_in) {
    (void)self_in;
    display->set_backlight((uint8_t)(mp_obj_get_float(value_in) * 255));
    return mp_const_none;
}

mp_obj_t st7789_set_max_pio_clock(mp_obj_t self_in, mp_obj_t value_in) {
    (void)self_in;
    display->set_max_pio_clock(mp_obj_get_uint(value_in));
    return mp_const_none;
}

mp_obj_t st7789_set_mode(mp_obj_t self_in, mp_obj_t mode_in) {
    (void)self_in;
    display->set_mode(mp_obj_is_true(mode_in));
    return mp_const_none;
}

mp_obj_t st7789_set_vsync(mp_obj_t self_in, mp_obj_t sync_in) {
    (void)self_in;
    display->set_vsync(mp_obj_is_true(sync_in));
    return mp_const_none;
}


mp_int_t st7789_get_framebuffer(mp_obj_t self_in, mp_buffer_info_t *bufinfo, mp_uint_t flags) {
    (void)self_in;
    (void)flags;
    bufinfo->buf = display->get_framebuffer();
    bufinfo->len = 320 * 240 * 4;
    bufinfo->typecode = 'B';
    return 0;
}

void st7789_attr(mp_obj_t self_in, qstr attr, mp_obj_t *dest) {
    if(attr == MP_QSTR_WIDTH && dest[0] == MP_OBJ_NULL) {
        dest[0] = mp_obj_new_int(display->get_mode() ? 320 : 160);
        return;
    }

    if(attr == MP_QSTR_HEIGHT && dest[0] == MP_OBJ_NULL) {
        dest[0] = mp_obj_new_int(display->get_mode() ? 240 : 120);
        return;
    }

    dest[1] = MP_OBJ_SENTINEL;
}

}