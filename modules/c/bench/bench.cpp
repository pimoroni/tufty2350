// Do-nothing native functions for benchmarking the MicroPython -> C++ call
// boundary. Bodies are deliberately empty (or do only the marshalling under
// test) so the harness measures dispatch / extraction / construction cost and
// nothing else.

extern "C" {
  #include "py/runtime.h"
  #include "py/objlist.h"

  // Volatile sinks stop the compiler eliding the argument extraction we want
  // to measure.
  static volatile mp_int_t   g_int_sink;
  static volatile mp_float_t g_float_sink;
  static volatile const void *g_ptr_sink;

  // A fixed source buffer so ret_bytes() can build a bytes object of arbitrary
  // length without a per-call malloc of its own.
  static const uint8_t g_zeros[256] = {0};

  // ---- cycle counter (Cortex-M33 DWT) -------------------------------------
  // Cortex-M debug registers. CYCCNT increments once per CPU cycle, giving
  // true single-cycle resolution (time.ticks_cpu() on this port is only us).
  #define BENCH_DEMCR     (*(volatile uint32_t *)0xE000EDFC)
  #define BENCH_DWT_CTRL  (*(volatile uint32_t *)0xE0001000)
  #define BENCH_DWT_CYCCNT (*(volatile uint32_t *)0xE0001004)

  mp_obj_t bench_cyc_init(void) {
    BENCH_DEMCR |= (1u << 24);      // TRCENA: enable DWT/ITM
    BENCH_DWT_CYCCNT = 0;
    BENCH_DWT_CTRL |= 1u;           // CYCCNTENA
    return mp_const_none;
  }

  mp_obj_t bench_cyc(void) {
    return mp_obj_new_int_from_uint(BENCH_DWT_CYCCNT);
  }

  // Runtime toggle read by picovector's blit_vspan binding, so we can measure
  // the binding/decode cost with the pixel render skipped, without a rebuild.
  volatile bool bench_skip_blit = false;
  mp_obj_t bench_set_skip(mp_obj_t on) {
    bench_skip_blit = mp_obj_is_true(on);
    return mp_const_none;
  }

  // ---- dispatch / arity ---------------------------------------------------
  // Fixed arity 0..3 take the fast switch in mp_call_function_n_kw; 4+ forces
  // the variadic (args-array) path; KW adds keyword-map handling.

  mp_obj_t bench_noargs(void) { return mp_const_none; }
  mp_obj_t bench_arg1(mp_obj_t a) { (void)a; return mp_const_none; }
  mp_obj_t bench_arg2(mp_obj_t a, mp_obj_t b) { (void)a; (void)b; return mp_const_none; }
  mp_obj_t bench_arg3(mp_obj_t a, mp_obj_t b, mp_obj_t c) { (void)a; (void)b; (void)c; return mp_const_none; }

  mp_obj_t bench_arg4(size_t n, const mp_obj_t *args) { (void)n; (void)args; return mp_const_none; }
  mp_obj_t bench_arg8(size_t n, const mp_obj_t *args) { (void)n; (void)args; return mp_const_none; }

  mp_obj_t bench_argkw(size_t n_args, const mp_obj_t *args, mp_map_t *kw_args) {
    (void)n_args; (void)args; (void)kw_args;
    return mp_const_none;
  }

  // ---- argument extraction ------------------------------------------------
  // All take three args and return None; only the unpack differs.

  mp_obj_t bench_take_ptr(mp_obj_t a, mp_obj_t b, mp_obj_t c) {
    g_ptr_sink = a; g_ptr_sink = b; g_ptr_sink = c;
    return mp_const_none;
  }
  mp_obj_t bench_take_int(mp_obj_t a, mp_obj_t b, mp_obj_t c) {
    g_int_sink = mp_obj_get_int(a) + mp_obj_get_int(b) + mp_obj_get_int(c);
    return mp_const_none;
  }
  mp_obj_t bench_take_float(mp_obj_t a, mp_obj_t b, mp_obj_t c) {
    g_float_sink = mp_obj_get_float(a) + mp_obj_get_float(b) + mp_obj_get_float(c);
    return mp_const_none;
  }

  // ---- return construction ------------------------------------------------
  // Fixed (zero/one) args, vary only what we hand back.

  mp_obj_t bench_ret_none(void) { return mp_const_none; }
  mp_obj_t bench_ret_int(void) { return MP_OBJ_NEW_SMALL_INT(42); }
  mp_obj_t bench_ret_float(void) { return mp_obj_new_float((mp_float_t)1.5); }  // inline under OBJ_REPR_C
  mp_obj_t bench_ret_bool(void) { return mp_const_true; }

  mp_obj_t bench_ret_tuple2(void) {
    mp_obj_t items[2] = { MP_OBJ_NEW_SMALL_INT(1), MP_OBJ_NEW_SMALL_INT(2) };
    return mp_obj_new_tuple(2, items);
  }
  mp_obj_t bench_ret_tuple8(void) {
    mp_obj_t items[8];
    for (int i = 0; i < 8; i++) items[i] = MP_OBJ_NEW_SMALL_INT(i);
    return mp_obj_new_tuple(8, items);
  }

  // list of n small ints; pre-sized then filled directly to avoid append/grow.
  mp_obj_t bench_ret_list(mp_obj_t n_in) {
    mp_int_t n = mp_obj_get_int(n_in);
    mp_obj_list_t *list = (mp_obj_list_t *)MP_OBJ_TO_PTR(mp_obj_new_list(n, NULL));
    for (mp_int_t i = 0; i < n; i++) list->items[i] = MP_OBJ_NEW_SMALL_INT(i);
    return MP_OBJ_FROM_PTR(list);
  }

  // bytes of n zeros (clamped to source buffer).
  mp_obj_t bench_ret_bytes(mp_obj_t n_in) {
    mp_int_t n = mp_obj_get_int(n_in);
    if (n < 0) n = 0;
    if (n > (mp_int_t)sizeof(g_zeros)) n = sizeof(g_zeros);
    return mp_obj_new_bytes(g_zeros, n);
  }

  // ---- keyword-argument parsing -------------------------------------------
  // Module-level function using the full mp_arg_parse_all machinery (allowed
  // table + defaults), the heavy path vs raw positional extraction.
  mp_obj_t bench_argparse(size_t n_args, const mp_obj_t *pos, mp_map_t *kw) {
    static const mp_arg_t allowed[] = {
      { MP_QSTR_bka, MP_ARG_INT, {0} },
      { MP_QSTR_bkb, MP_ARG_INT, {0} },
      { MP_QSTR_bkc, MP_ARG_INT, {0} },
    };
    mp_arg_val_t vals[3];
    mp_arg_parse_all(n_args, pos, kw, 3, allowed, vals);
    g_int_sink = vals[0].u_int + vals[1].u_int + vals[2].u_int;
    return mp_const_none;
  }

  // ---- method dispatch: a minimal type with methods -----------------------
  // Calls look like obj.method(...): attribute lookup in the type locals_dict,
  // method dispatch, and self unpacking - the real picovector path.
  typedef struct _bench_thing_obj_t {
    mp_obj_base_t base;
    int32_t v;
  } bench_thing_obj_t;

  extern const mp_obj_type_t bench_type_thing;   // defined in bench.c

  mp_obj_t bench_thing_m0(mp_obj_t self_in) { (void)self_in; return mp_const_none; }
  mp_obj_t bench_thing_m1(mp_obj_t self_in, mp_obj_t a) { (void)self_in; (void)a; return mp_const_none; }
  // self + 3 args via the VAR path (args[0] is self), as picovector methods do.
  mp_obj_t bench_thing_m3(size_t n, const mp_obj_t *args) { (void)n; (void)args; return mp_const_none; }

  // static method: no self, called as Thing.s0().
  mp_obj_t bench_thing_s0(void) { return mp_const_none; }

  // method taking keyword args, parsed with mp_arg_parse_all (skips self).
  mp_obj_t bench_thing_mkw(size_t n_args, const mp_obj_t *pos, mp_map_t *kw) {
    static const mp_arg_t allowed[] = {
      { MP_QSTR_bka, MP_ARG_INT, {0} },
      { MP_QSTR_bkb, MP_ARG_INT, {0} },
      { MP_QSTR_bkc, MP_ARG_INT, {0} },
    };
    mp_arg_val_t vals[3];
    mp_arg_parse_all(n_args - 1, pos + 1, kw, 3, allowed, vals);
    g_int_sink = vals[0].u_int + vals[1].u_int + vals[2].u_int;
    return mp_const_none;
  }

  // factory method: allocate a GC object *with a finaliser* (mirrors the
  // picovector mp_obj_malloc_with_finaliser factories) - suspected 25us source.
  mp_obj_t bench_thing_make(mp_obj_t self_in) {
    (void)self_in;
    bench_thing_obj_t *o = mp_obj_malloc_with_finaliser(bench_thing_obj_t, &bench_type_thing);
    o->v = 0;
    return MP_OBJ_FROM_PTR(o);
  }

  // plain GC object *without* a finaliser, to isolate the finaliser cost.
  mp_obj_t bench_thing_make_plain(mp_obj_t self_in) {
    (void)self_in;
    bench_thing_obj_t *o = mp_obj_malloc(bench_thing_obj_t, &bench_type_thing);
    o->v = 0;
    return MP_OBJ_FROM_PTR(o);
  }

  mp_obj_t bench_thing_del(mp_obj_t self_in) { (void)self_in; return mp_const_none; }

  // constructor: Thing()
  mp_obj_t bench_thing_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw, const mp_obj_t *args) {
    (void)type; (void)n_args; (void)n_kw; (void)args;
    bench_thing_obj_t *o = mp_obj_malloc_with_finaliser(bench_thing_obj_t, &bench_type_thing);
    o->v = 0;
    return MP_OBJ_FROM_PTR(o);
  }
}
