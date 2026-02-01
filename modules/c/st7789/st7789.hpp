#pragma once

#include <cstdlib>
#include <math.h>
#include <string.h>

#include "hardware/spi.h"
#include "hardware/dma.h"
#include "hardware/gpio.h"
#include "hardware/pio.h"
#include "hardware/pwm.h"
#include "hardware/clocks.h"
#include "pico/stdlib.h"

#ifndef NO_QSTR
#include "st7789_parallel.pio.h"
#endif

#include <algorithm>

#define XIP_PSRAM_CACHED  _u(0x11000000)
#define XIP_PSRAM_NOCACHE _u(0x15000000)


namespace pimoroni {
  class ST7789 {
  private:
    int width = 160;
    int height = 120;
    int fullres_width = 320;
    int fullres_height = 240;

    // interface pins
    uint cs = 27;
    uint dc = 28;
    uint wr_sck = 30;
    uint rd_sck = 31;
    uint d0 = 32;
    uint bl = 26;
    uint vsync = 21;

    // pio stuff
    PIO parallel_pio = pio1;
    uint32_t startup_hz = 0;
    uint32_t max_pio_clk = 44 * MHZ;

    // Regular commands
    uint parallel_sm;
    int parallel_offset;
    uint st_dma;

    // Whether to vsync
    bool use_vsync = true;

  public:
    // Parallel init
    ST7789() {
      pio_set_gpio_base(parallel_pio, d0 + 8 >= 32 ? 16 : 0);

      parallel_sm = pio_claim_unused_sm(parallel_pio, true);
      parallel_offset = pio_add_program(parallel_pio, &st7789_parallel_program);
      if(parallel_offset == -1) {
        panic("Could not add parallel PIO program.");
      }

      pio_gpio_init(parallel_pio, wr_sck);

      gpio_set_function(rd_sck,  GPIO_FUNC_SIO);
      gpio_set_dir(rd_sck, GPIO_OUT);

      for(auto i = 0u; i < 8; i++) {
        pio_gpio_init(parallel_pio, d0 + i);
      }

      pio_sm_set_consecutive_pindirs(parallel_pio, parallel_sm, d0, 8, true);
      pio_sm_set_consecutive_pindirs(parallel_pio, parallel_sm, wr_sck, 1, true);

      pio_sm_config c = st7789_parallel_program_get_default_config(parallel_offset);
      sm_config_set_out_pins(&c, d0, 8);
      sm_config_set_sideset_pins(&c, wr_sck);
      sm_config_set_fifo_join(&c, PIO_FIFO_JOIN_TX);
      sm_config_set_out_shift(&c, false, true, 8);

      // Determine clock divider
      startup_hz = clock_get_hz(clk_sys);
      sm_config_set_clkdiv(&c, ceil(2.f * fmax(1.0f, float(startup_hz) / max_pio_clk)) * 0.5f);

      pio_sm_init(parallel_pio, parallel_sm, parallel_offset, &c);
      pio_sm_set_enabled(parallel_pio, parallel_sm, true);

      st_dma = dma_claim_unused_channel(true);
      configure_dma(true);

      gpio_put(rd_sck, 1);

      init();
    }

    ~ST7789() {
      if(dma_channel_is_claimed(st_dma)) {
        dma_channel_abort(st_dma);
        dma_channel_unclaim(st_dma);
      }

      if(pio_sm_is_claimed(parallel_pio, parallel_sm)) {
        pio_sm_set_enabled(parallel_pio, parallel_sm, false);
        pio_sm_drain_tx_fifo(parallel_pio, parallel_sm);
        //pio_sm_unclaim(parallel_pio, parallel_sm);
        pio_remove_program_and_unclaim_sm(&st7789_parallel_program, parallel_pio, parallel_sm, parallel_offset);
      }
    }

    void update(bool fullres);
    void set_backlight(uint8_t brightness);
    uint32_t *get_framebuffer();
    void command(uint8_t command, size_t len = 0, const char *data = NULL);
    void set_max_pio_clock(uint32_t hz);
    void set_vsync(bool sync);

  private:
    void init();
    void configure_dma(bool enable_read_increment = true);
    inline void wait_for_dma(void);
    void write_blocking(const uint8_t *src, size_t len);
    void start_dma(const uint8_t *src, size_t len);
  };

}
