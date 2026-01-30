#include "st7789.hpp"


namespace pimoroni {

  uint32_t __attribute__((section(".uninitialized_data"))) __attribute__ ((aligned (4))) framebuffer[320 * 240];
  uint16_t __attribute__((section(".uninitialized_data"))) __attribute__ ((aligned (4))) linebuffer[240 * 4];

  // If we configure MicroPython's main.c to skip the first 320 * 240 * sizeof(uint32_t)
  // bytes we can steal this as a backbuffer.
  // auto backbuffer = new((uintptr_t *)XIP_PSRAM_CACHED) uint32_t[320 * 240];
  // auto backbuffer_nocache = new((uintptr_t *)XIP_PSRAM_NOCACHE) uint32_t[320 * 240];

  enum MADCTL : uint8_t {
    ROW_ORDER   = 0b10000000,
    COL_ORDER   = 0b01000000,
    SWAP_XY     = 0b00100000,  // AKA "MV"
    SCAN_ORDER  = 0b00010000,
    RGB_BGR     = 0b00001000,
    HORIZ_ORDER = 0b00000100
  };

  enum reg {
    SWRESET   = 0x01,
    TEOFF     = 0x34,
    TEON      = 0x35,
    STE       = 0x44,
    MADCTL    = 0x36,
    COLMOD    = 0x3A,
    RAMCTRL   = 0xB0,
    RGBCTRL   = 0xB1,
    GCTRL     = 0xB7,
    VCOMS     = 0xBB,
    LCMCTRL   = 0xC0,
    VDVVRHEN  = 0xC2,
    VRHS      = 0xC3,
    VDVS      = 0xC4,
    FRCTRL2   = 0xC6,
    PWCTRL1   = 0xD0,
    GATESEL   = 0xD6,
    PORCTRL   = 0xB2,
    GMCTRP1   = 0xE0,
    GMCTRN1   = 0xE1,
    INVOFF    = 0x20,
    SLPIN     = 0x10,
    SLPOUT    = 0x11,
    DISPON    = 0x29,
    GAMSET    = 0x26,
    DISPOFF   = 0x28,
    RAMWR     = 0x2C,
    INVON     = 0x21,
    CASET     = 0x2A,
    RASET     = 0x2B,
    PWMFRSEL  = 0xCC
  };

  void ST7789::init() {
    gpio_set_function(dc, GPIO_FUNC_SIO);
    gpio_set_dir(dc, GPIO_OUT);

    gpio_set_function(cs, GPIO_FUNC_SIO);
    gpio_set_dir(cs, GPIO_OUT);

    gpio_init(vsync);

    // if a backlight pin is provided then set it up for
    // pwm control
    pwm_config cfg = pwm_get_default_config();
    pwm_set_wrap(pwm_gpio_to_slice_num(bl), 65535);
    pwm_init(pwm_gpio_to_slice_num(bl), &cfg, true);
    gpio_set_function(bl, GPIO_FUNC_PWM);
    set_backlight(0); // Turn backlight off initially to avoid nasty surprises

    command(reg::SWRESET);

    sleep_ms(150);

    // Common init
    command(reg::COLMOD,    1, "\x05");  // 16 bits per pixel

    // both started as 0x0c 0x0c
    command(reg::PORCTRL, 5, "\x0c\x0c\x00\x33\x33");
    //command(reg::RGBCTRL, 3, "\x40\x02\x14");
    command(reg::LCMCTRL, 1, "\x2c");
    command(reg::VDVVRHEN, 1, "\x01");
    command(reg::VRHS, 1, "\x0f");
    command(reg::VDVS, 1, "\x20");
    command(reg::PWCTRL1, 2, "\xa4\xa1");
    command(reg::FRCTRL2, 1, "\x0f");

    // As noted in https://github.com/pimoroni/pimoroni-pico/issues/1040
    // this is required to avoid a weird light grey banding issue with low brightness green.
    // The banding is not visible without tweaking gamma settings (GMCTRP1 & GMCTRN1) but
    // it makes sense to fix it anyway.
    command(reg::RAMCTRL, 2, "\x00\xc0");

    // 320 x 240
    command(reg::GCTRL, 1, "\x35");
    command(reg::VCOMS, 1, "\x1b");
    command(reg::GMCTRP1, 14, "\xF0\x00\x06\x04\x05\x05\x31\x44\x48\x36\x12\x12\x2B\x34");
    command(reg::GMCTRN1, 14, "\xF0\x0B\x0F\x0F\x0D\x26\x31\x43\x47\x38\x14\x14\x2C\x32");

    command(reg::INVON);   // set inversion mode
    command(reg::SLPOUT);  // leave sleep mode

    sleep_ms(100);

    uint8_t madctl = MADCTL::ROW_ORDER | MADCTL::SCAN_ORDER; //MADCTL::ROW_ORDER | MADCTL::SWAP_XY | MADCTL::SCAN_ORDER;
    uint16_t caset[2] = {0, 239};
    uint16_t raset[2] = {0, 319};

    // Byte swap the 16bit rows/cols values
    caset[0] = __builtin_bswap16(caset[0]);
    caset[1] = __builtin_bswap16(caset[1]);
    raset[0] = __builtin_bswap16(raset[0]);
    raset[1] = __builtin_bswap16(raset[1]);

    command(reg::CASET,  4, (char *)caset);
    command(reg::RASET,  4, (char *)raset);
    command(reg::MADCTL, 1, (char *)&madctl);

    // Set up the screen for a display update
    uint8_t cmd = reg::RAMWR;
    gpio_put(dc, 0); // command mode
    gpio_put(cs, 0);
    write_blocking(&cmd, 1);
    gpio_put(dc, 1); // data mode

    // Temporarily reconfigure the DMA with no read increment so we can
    // clock out just one zero (no need to memset) to clear the whole display.
    linebuffer[0] = 0;
    configure_dma(false);
    write_blocking((uint8_t *)linebuffer, fullres_width * fullres_height * sizeof(uint16_t)); // Clear display to black
    configure_dma(true);

    command(reg::TEON, 1, "\x00");  // enable frame sync signal
    command(reg::STE, 2, "\x00\x00");
    command(reg::DISPON);  // turn display on
    set_backlight(230); // Turn backlight on now surprises have passed, 180 = about half perceptual brightness
  }

  uint32_t *ST7789::get_framebuffer() {
    return framebuffer;
  }

  static inline volatile void pio_sm_block_until_stalled(PIO pio, uint sm) {
    uint32_t sm_stall_mask = 1u << (sm + PIO_FDEBUG_TXSTALL_LSB);
    pio->fdebug = sm_stall_mask;
    while (!(pio->fdebug & sm_stall_mask))
        ;
  }

  inline void ST7789::wait_for_dma(void) {
    dma_channel_wait_for_finish_blocking(st_dma);

    // Prevent a race between PIO and chip-select or data/command
    // What's up with pio_sm_is_exec_stalled?
    pio_sm_block_until_stalled(parallel_pio, parallel_sm);
  }

  void ST7789::write_blocking(const uint8_t *src, size_t len) {
    dma_channel_set_trans_count(st_dma, len, false);
    dma_channel_set_read_addr(st_dma, src, true);
    wait_for_dma();
  }

  void ST7789::start_dma(const uint8_t *src, size_t len) {
    dma_channel_set_trans_count(st_dma, len, false);
    dma_channel_set_read_addr(st_dma, src, true);
  }

  void ST7789::command(uint8_t command, size_t len, const char *data) {
    wait_for_dma();

    gpio_put(dc, 0); // command mode

    gpio_put(cs, 0);

    write_blocking(&command, 1);
    if(data) {
      gpio_put(dc, 1); // data mode
      write_blocking((const uint8_t*)data, len);
    }

    gpio_put(cs, 1);
  }

  void ST7789::update(bool fullres) {
    // Determine clock divider
    const uint32_t sys_clk_hz = clock_get_hz(clk_sys);

    if (sys_clk_hz != startup_hz) {
      startup_hz = sys_clk_hz;
      pio_sm_set_clkdiv(parallel_pio, parallel_sm, fmax(1.0f, float(sys_clk_hz) / max_pio_clk));
    }

    wait_for_dma();

    // Wait for vsync
    while (gpio_get(vsync) == 0);

    uint8_t cmd = reg::RAMWR;
    gpio_put(dc, 0); // command mode
    gpio_put(cs, 0);
    write_blocking(&cmd, 1);
    gpio_put(dc, 1); // data mode

    // Take an "a" and a "b" pointer into the linebuffer, we will swap between
    // these, converting pixels into one while the other is DMA'd to the screen.
    uint16_t *buf_a = linebuffer;
    uint16_t *buf_b = linebuffer + 240 * 2;

    // The copy from framebuffer to linebuffer also serves to rotate the image
    // 90 degrees to match the scan orientation and prevent diagonal tearing.
    if(fullres) {
      for(int x = 0; x < fullres_width; x++) {
        for(int y = 0; y < fullres_height; y++) {
          uint32_t src = framebuffer[y * fullres_width + x];
          buf_a[y] = __builtin_bswap16(((src & 0xf8) << 8) | ((src & 0xfc00) >> 5) | ((src & 0xf80000) >> 19));
        }
        // Transfer a single full res (full 240 pixel height) column
        // In full-res we can "chase the beam" as it were, replacing pixels
        // behind the outgoing DMA transfer.
        wait_for_dma();
        start_dma((uint8_t *)buf_a, fullres_height * 2);
        std::swap(buf_a, buf_b);
      }
    } else {
      for(int x = 0; x < width; x++) {
        for(int y = 0; y < height; y++) {
          uint32_t src = framebuffer[y * width + x];
          uint16_t pixel = __builtin_bswap16(((src & 0xf8) << 8) | ((src & 0xfc00) >> 5) | ((src & 0xf80000) >> 19));
          buf_a[y * 2] = pixel;
          buf_a[y * 2 + 1] = pixel;
          // It's slightly faster to prepare to rows, rather than prepare
          // a single row and copy it twice.
          buf_a[(height + y) * 2] = pixel;
          buf_a[(height + y) * 2 + 1] = pixel;
        }
        wait_for_dma();
        start_dma((uint8_t *)buf_a, fullres_height * 2 * 2);
        std::swap(buf_a, buf_b);
      }
    }

    // Yeet the last column into the abyss and save a little time
    // wait_for_dma();
    // gpio_put(cs, 1);
  }

  void ST7789::set_backlight(uint8_t brightness) {
    // gamma correct the provided 0-255 brightness value onto a
    // 0-65535 range for the pwm counter
    float gamma = 2.8;
    uint16_t value = (uint16_t)(pow((float)(brightness) / 255.0f, gamma) * 65535.0f + 0.5f);
    pwm_set_gpio_level(bl, value);
  }

  void ST7789::configure_dma(bool enable_read_increment) {
    dma_channel_config config = dma_channel_get_default_config(st_dma);
    channel_config_set_read_increment(&config, enable_read_increment);
    channel_config_set_transfer_data_size(&config, DMA_SIZE_8);
    channel_config_set_bswap(&config, false);
    channel_config_set_dreq(&config, pio_get_dreq(parallel_pio, parallel_sm, true));
    dma_channel_configure(st_dma, &config, &parallel_pio->txf[parallel_sm], NULL, 0, false);
  }

  void ST7789::set_max_pio_clock(uint32_t hz) {
    max_pio_clk = hz;
    startup_hz = 0;
  }
}
