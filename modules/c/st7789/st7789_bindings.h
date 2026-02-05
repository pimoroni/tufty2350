#include "py/runtime.h"
#include "py/objstr.h"

extern const mp_obj_type_t ST7789_type;

// Declare the functions we'll make available in Python
extern mp_obj_t st7789_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw, const mp_obj_t *all_args);
extern mp_obj_t st7789___del__(mp_obj_t self_in);
extern mp_obj_t st7789_update(mp_obj_t self_in);
extern mp_int_t st7789_get_framebuffer(mp_obj_t self_in, mp_buffer_info_t *bufinfo, mp_uint_t flags);
extern mp_obj_t st7789_set_backlight(mp_obj_t self_in, mp_obj_t value_in);
extern mp_obj_t st7789_set_mode(mp_obj_t self_in, mp_obj_t value_in);
extern mp_obj_t st7789_command(mp_obj_t self_in, mp_obj_t reg_in, mp_obj_t data_in);
extern mp_obj_t st7789_set_max_pio_clock(mp_obj_t self_in, mp_obj_t value_in);
extern mp_obj_t st7789_set_vsync(mp_obj_t self_in, mp_obj_t sync_in);
extern void st7789_attr(mp_obj_t self_in, qstr attr, mp_obj_t *dest);