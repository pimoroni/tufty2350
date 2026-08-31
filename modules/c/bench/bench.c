#include "py/runtime.h"

// Implemented in bench.cpp
extern mp_obj_t bench_noargs(void);
extern mp_obj_t bench_arg1(mp_obj_t a);
extern mp_obj_t bench_arg2(mp_obj_t a, mp_obj_t b);
extern mp_obj_t bench_arg3(mp_obj_t a, mp_obj_t b, mp_obj_t c);
extern mp_obj_t bench_arg4(size_t n, const mp_obj_t *args);
extern mp_obj_t bench_arg8(size_t n, const mp_obj_t *args);
extern mp_obj_t bench_argkw(size_t n_args, const mp_obj_t *args, mp_map_t *kw_args);
extern mp_obj_t bench_take_ptr(mp_obj_t a, mp_obj_t b, mp_obj_t c);
extern mp_obj_t bench_take_int(mp_obj_t a, mp_obj_t b, mp_obj_t c);
extern mp_obj_t bench_take_float(mp_obj_t a, mp_obj_t b, mp_obj_t c);
extern mp_obj_t bench_ret_none(void);
extern mp_obj_t bench_ret_int(void);
extern mp_obj_t bench_ret_float(void);
extern mp_obj_t bench_ret_bool(void);
extern mp_obj_t bench_ret_tuple2(void);
extern mp_obj_t bench_ret_tuple8(void);
extern mp_obj_t bench_ret_list(mp_obj_t n_in);
extern mp_obj_t bench_ret_bytes(mp_obj_t n_in);
extern mp_obj_t bench_cyc_init(void);
extern mp_obj_t bench_cyc(void);
extern mp_obj_t bench_set_skip(mp_obj_t on);
// keyword parsing + method dispatch (bodies in bench.cpp)
extern mp_obj_t bench_argparse(size_t n_args, const mp_obj_t *pos, mp_map_t *kw);
extern mp_obj_t bench_thing_m0(mp_obj_t self_in);
extern mp_obj_t bench_thing_m1(mp_obj_t self_in, mp_obj_t a);
extern mp_obj_t bench_thing_m3(size_t n, const mp_obj_t *args);
extern mp_obj_t bench_thing_s0(void);
extern mp_obj_t bench_thing_mkw(size_t n_args, const mp_obj_t *pos, mp_map_t *kw);
extern mp_obj_t bench_thing_make(mp_obj_t self_in);
extern mp_obj_t bench_thing_make_plain(mp_obj_t self_in);
extern mp_obj_t bench_thing_del(mp_obj_t self_in);
extern mp_obj_t bench_thing_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw, const mp_obj_t *args);

// dispatch / arity
static MP_DEFINE_CONST_FUN_OBJ_0(bench_noargs_obj, bench_noargs);
static MP_DEFINE_CONST_FUN_OBJ_1(bench_arg1_obj, bench_arg1);
static MP_DEFINE_CONST_FUN_OBJ_2(bench_arg2_obj, bench_arg2);
static MP_DEFINE_CONST_FUN_OBJ_3(bench_arg3_obj, bench_arg3);
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(bench_arg4_obj, 4, 4, bench_arg4);
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(bench_arg8_obj, 8, 8, bench_arg8);
static MP_DEFINE_CONST_FUN_OBJ_KW(bench_argkw_obj, 0, bench_argkw);

// extraction
static MP_DEFINE_CONST_FUN_OBJ_3(bench_take_ptr_obj, bench_take_ptr);
static MP_DEFINE_CONST_FUN_OBJ_3(bench_take_int_obj, bench_take_int);
static MP_DEFINE_CONST_FUN_OBJ_3(bench_take_float_obj, bench_take_float);

// return construction
static MP_DEFINE_CONST_FUN_OBJ_0(bench_ret_none_obj, bench_ret_none);
static MP_DEFINE_CONST_FUN_OBJ_0(bench_ret_int_obj, bench_ret_int);
static MP_DEFINE_CONST_FUN_OBJ_0(bench_ret_float_obj, bench_ret_float);
static MP_DEFINE_CONST_FUN_OBJ_0(bench_ret_bool_obj, bench_ret_bool);
static MP_DEFINE_CONST_FUN_OBJ_0(bench_ret_tuple2_obj, bench_ret_tuple2);
static MP_DEFINE_CONST_FUN_OBJ_0(bench_ret_tuple8_obj, bench_ret_tuple8);
static MP_DEFINE_CONST_FUN_OBJ_1(bench_ret_list_obj, bench_ret_list);
static MP_DEFINE_CONST_FUN_OBJ_1(bench_ret_bytes_obj, bench_ret_bytes);

// cycle counter
static MP_DEFINE_CONST_FUN_OBJ_0(bench_cyc_init_obj, bench_cyc_init);
static MP_DEFINE_CONST_FUN_OBJ_0(bench_cyc_obj, bench_cyc);
static MP_DEFINE_CONST_FUN_OBJ_1(bench_set_skip_obj, bench_set_skip);

// keyword parsing
static MP_DEFINE_CONST_FUN_OBJ_KW(bench_argparse_obj, 0, bench_argparse);

// --- Thing type: method dispatch ---
static MP_DEFINE_CONST_FUN_OBJ_1(bench_thing_m0_obj, bench_thing_m0);
static MP_DEFINE_CONST_FUN_OBJ_2(bench_thing_m1_obj, bench_thing_m1);
static MP_DEFINE_CONST_FUN_OBJ_VAR(bench_thing_m3_obj, 1, bench_thing_m3);
static MP_DEFINE_CONST_FUN_OBJ_0(bench_thing_s0_fun_obj, bench_thing_s0);
static MP_DEFINE_CONST_STATICMETHOD_OBJ(bench_thing_s0_obj, MP_ROM_PTR(&bench_thing_s0_fun_obj));
static MP_DEFINE_CONST_FUN_OBJ_KW(bench_thing_mkw_obj, 1, bench_thing_mkw);
static MP_DEFINE_CONST_FUN_OBJ_1(bench_thing_make_obj, bench_thing_make);
static MP_DEFINE_CONST_FUN_OBJ_1(bench_thing_make_plain_obj, bench_thing_make_plain);
static MP_DEFINE_CONST_FUN_OBJ_1(bench_thing_del_obj, bench_thing_del);

static const mp_rom_map_elem_t bench_thing_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR_m0), MP_ROM_PTR(&bench_thing_m0_obj) },
    { MP_ROM_QSTR(MP_QSTR_m1), MP_ROM_PTR(&bench_thing_m1_obj) },
    { MP_ROM_QSTR(MP_QSTR_m3), MP_ROM_PTR(&bench_thing_m3_obj) },
    { MP_ROM_QSTR(MP_QSTR_s0), MP_ROM_PTR(&bench_thing_s0_obj) },
    { MP_ROM_QSTR(MP_QSTR_mkw), MP_ROM_PTR(&bench_thing_mkw_obj) },
    { MP_ROM_QSTR(MP_QSTR_make), MP_ROM_PTR(&bench_thing_make_obj) },
    { MP_ROM_QSTR(MP_QSTR_make_plain), MP_ROM_PTR(&bench_thing_make_plain_obj) },
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&bench_thing_del_obj) },
};
static MP_DEFINE_CONST_DICT(bench_thing_locals_dict, bench_thing_locals_dict_table);

MP_DEFINE_CONST_OBJ_TYPE(
    bench_type_thing,
    MP_QSTR_Thing,
    MP_TYPE_FLAG_NONE,
    make_new, bench_thing_make_new,
    locals_dict, &bench_thing_locals_dict
);

static const mp_rom_map_elem_t bench_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_bench) },
    // dispatch / arity
    { MP_ROM_QSTR(MP_QSTR_noargs), MP_ROM_PTR(&bench_noargs_obj) },
    { MP_ROM_QSTR(MP_QSTR_arg1), MP_ROM_PTR(&bench_arg1_obj) },
    { MP_ROM_QSTR(MP_QSTR_arg2), MP_ROM_PTR(&bench_arg2_obj) },
    { MP_ROM_QSTR(MP_QSTR_arg3), MP_ROM_PTR(&bench_arg3_obj) },
    { MP_ROM_QSTR(MP_QSTR_arg4), MP_ROM_PTR(&bench_arg4_obj) },
    { MP_ROM_QSTR(MP_QSTR_arg8), MP_ROM_PTR(&bench_arg8_obj) },
    { MP_ROM_QSTR(MP_QSTR_argkw), MP_ROM_PTR(&bench_argkw_obj) },
    // extraction
    { MP_ROM_QSTR(MP_QSTR_take_ptr), MP_ROM_PTR(&bench_take_ptr_obj) },
    { MP_ROM_QSTR(MP_QSTR_take_int), MP_ROM_PTR(&bench_take_int_obj) },
    { MP_ROM_QSTR(MP_QSTR_take_float), MP_ROM_PTR(&bench_take_float_obj) },
    // return construction
    { MP_ROM_QSTR(MP_QSTR_ret_none), MP_ROM_PTR(&bench_ret_none_obj) },
    { MP_ROM_QSTR(MP_QSTR_ret_int), MP_ROM_PTR(&bench_ret_int_obj) },
    { MP_ROM_QSTR(MP_QSTR_ret_float), MP_ROM_PTR(&bench_ret_float_obj) },
    { MP_ROM_QSTR(MP_QSTR_ret_bool), MP_ROM_PTR(&bench_ret_bool_obj) },
    { MP_ROM_QSTR(MP_QSTR_ret_tuple2), MP_ROM_PTR(&bench_ret_tuple2_obj) },
    { MP_ROM_QSTR(MP_QSTR_ret_tuple8), MP_ROM_PTR(&bench_ret_tuple8_obj) },
    { MP_ROM_QSTR(MP_QSTR_ret_list), MP_ROM_PTR(&bench_ret_list_obj) },
    { MP_ROM_QSTR(MP_QSTR_ret_bytes), MP_ROM_PTR(&bench_ret_bytes_obj) },
    // cycle counter
    { MP_ROM_QSTR(MP_QSTR_cyc_init), MP_ROM_PTR(&bench_cyc_init_obj) },
    { MP_ROM_QSTR(MP_QSTR_cyc), MP_ROM_PTR(&bench_cyc_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_skip), MP_ROM_PTR(&bench_set_skip_obj) },
    // keyword parsing + method dispatch
    { MP_ROM_QSTR(MP_QSTR_argparse), MP_ROM_PTR(&bench_argparse_obj) },
    { MP_ROM_QSTR(MP_QSTR_Thing), MP_ROM_PTR(&bench_type_thing) },
};
static MP_DEFINE_CONST_DICT(bench_globals, bench_globals_table);

const mp_obj_module_t mod_bench = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&bench_globals,
};

MP_REGISTER_MODULE(MP_QSTR_bench, mod_bench);
