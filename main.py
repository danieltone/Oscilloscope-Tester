"""
main.py — Oscilloscope Tester for Raspberry Pi Pico
MicroPython interactive menu over USB serial

Upload this file AND waveforms.py to the Pico.
It runs automatically on power-up (MicroPython executes main.py at boot).

Connect via any serial terminal at 115200 baud, e.g.:
  mpremote connect /dev/ttyACM0
  screen /dev/ttyACM0 115200
  minicom -b 115200 -D /dev/ttyACM0
"""

import sys
import time
import select
from machine import Pin
import waveforms

# ---------------------------------------------------------------------------
# Hardware assignments
# ---------------------------------------------------------------------------
MAIN_PIN = 0    # GP0 — main waveform output  (physical pin 1)
LED_PIN  = 25   # Onboard LED (shows the app is running)

# ---------------------------------------------------------------------------
# Menu strings
# ---------------------------------------------------------------------------
HEADER = """\r
+------------------------------------------------------+
|       OSCILLOSCOPE TESTER  --  Raspberry Pi Pico     |
|   Probe: GP0 (pin 1)   GND: any GND pin              |
+------------------------------------------------------+"""

MENU = """\r
 -- SQUARE WAVES  (hardware PWM, probe directly) -------
  [1]   1 Hz        [2]   10 Hz       [3]  100 Hz
  [4]   1 kHz       [5]  10 kHz       [6] 100 kHz
  [7]   1 MHz

 -- DUTY CYCLE / PWM  (1 kHz carrier) ------------------
  [8]  10 %        [9]  25 %        [10]  50 %
 [11]  75 %       [12]  90 %

 -- ANALOG WAVEFORMS  (RC filter recommended *) --------
 [13]  Sine      1 Hz   [14]  Sine     10 Hz
 [15]  Sine    100 Hz   [16]  Triangle 10 Hz
 [17]  Triangle 100 Hz  [18]  Sawtooth 10 Hz
 [19]  Sawtooth 100 Hz  [20]  Rev-sawtooth 10 Hz

 -- DC LEVELS  (RC filter recommended *) ---------------
 [21]   0 V (GND)       [22] ~0.83 V (25 %)
 [23] ~1.65 V (50 %)    [24] ~2.48 V (75 %)
 [25]  3.3 V (100 %)

 -- SPECIAL --------------------------------------------
 [26]  Burst  1 kHz  (10 ON / 10 OFF cycles)
 [27]  Burst 10 kHz  (10 ON / 10 OFF cycles)
 [28]  Frequency sweep  1 Hz -> 1 MHz  (2 s per step)

  [0]  Stop / back to menu

 * RC filter: 10 kohm series resistor + 10 nF to GND
   (gives ~1.6 kHz cutoff, removes 62.5 kHz PWM carrier)
   Without filter the scope still shows the PWM envelope.
-------------------------------------------------------
Press Enter after typing your choice to stop a waveform.
Choice: """


def _prompt():
    sys.stdout.write(HEADER + MENU)


def _drain():
    """Consume any pending serial input before showing the prompt."""
    p = select.poll()
    p.register(sys.stdin, select.POLLIN)
    while p.poll(20):
        sys.stdin.read(1)


def _label(freq_hz):
    if freq_hz >= 1_000_000:
        return "{} MHz".format(freq_hz // 1_000_000)
    if freq_hz >= 1_000:
        return "{} kHz".format(freq_hz // 1_000)
    return "{} Hz".format(freq_hz)


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

def _dispatch(choice, gen):
    """Execute the selected test. Returns False to exit, True to continue."""
    if choice == 0:
        gen.stop()
        print("\r  Output stopped.")
        return True

    # --- Square waves ---
    if choice in (1, 2, 3, 4, 5, 6, 7):
        freqs = {1: 1, 2: 10, 3: 100, 4: 1_000, 5: 10_000, 6: 100_000, 7: 1_000_000}
        f = freqs[choice]
        print("\r  Square wave {}  ->  GP0.  Press any key to stop.".format(_label(f)))
        gen.square_wave(f)

    # --- PWM duty cycle ---
    elif choice in (8, 9, 10, 11, 12):
        duties = {8: 10, 9: 25, 10: 50, 11: 75, 12: 90}
        d = duties[choice]
        print("\r  PWM 1 kHz  {}%  ->  GP0.  Press any key to stop.".format(d))
        gen.pwm_wave(1_000, d)

    # --- Analog waveforms ---
    elif choice == 13:
        print("\r  Sine 1 Hz  (RC filter recommended)  Press any key to stop.")
        gen.sine_wave(1)
    elif choice == 14:
        print("\r  Sine 10 Hz  (RC filter recommended)  Press any key to stop.")
        gen.sine_wave(10)
    elif choice == 15:
        print("\r  Sine 100 Hz  (RC filter recommended)  Press any key to stop.")
        gen.sine_wave(100)
    elif choice == 16:
        print("\r  Triangle 10 Hz  (RC filter recommended)  Press any key to stop.")
        gen.triangle_wave(10)
    elif choice == 17:
        print("\r  Triangle 100 Hz  (RC filter recommended)  Press any key to stop.")
        gen.triangle_wave(100)
    elif choice == 18:
        print("\r  Sawtooth 10 Hz  (RC filter recommended)  Press any key to stop.")
        gen.sawtooth_wave(10)
    elif choice == 19:
        print("\r  Sawtooth 100 Hz  (RC filter recommended)  Press any key to stop.")
        gen.sawtooth_wave(100)
    elif choice == 20:
        print("\r  Reverse-sawtooth 10 Hz  (RC filter recommended)  Press any key to stop.")
        gen.rev_sawtooth_wave(10)

    # --- DC levels ---
    elif choice == 21:
        print("\r  DC 0 V (output low)  ->  GP0.  Press any key to stop.")
        gen.dc_level(0)
    elif choice == 22:
        print("\r  DC ~0.83 V (25%)  ->  GP0.  RC filter recommended.  Press any key to stop.")
        gen.dc_level(25)
    elif choice == 23:
        print("\r  DC ~1.65 V (50%)  ->  GP0.  RC filter recommended.  Press any key to stop.")
        gen.dc_level(50)
    elif choice == 24:
        print("\r  DC ~2.48 V (75%)  ->  GP0.  RC filter recommended.  Press any key to stop.")
        gen.dc_level(75)
    elif choice == 25:
        print("\r  DC 3.3 V (100%)  ->  GP0.  Press any key to stop.")
        gen.dc_level(100)

    # --- Special ---
    elif choice == 26:
        print("\r  Burst 1 kHz  10 ON / 10 OFF  ->  GP0.  Press any key to stop.")
        gen.burst_wave(1_000, on_cycles=10, off_cycles=10)
    elif choice == 27:
        print("\r  Burst 10 kHz  10 ON / 10 OFF  ->  GP0.  Press any key to stop.")
        gen.burst_wave(10_000, on_cycles=10, off_cycles=10)
    elif choice == 28:
        print("\r  Frequency sweep 1 Hz -> 1 MHz  (press any key to stop early)")
        gen.frequency_sweep(start_hz=1, end_hz=1_000_000, steps_per_decade=3, dwell_sec=2)

    else:
        print("\r  Unknown choice: {}".format(choice))

    return True


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run():
    led = Pin(LED_PIN, Pin.OUT)
    led.value(1)

    gen = waveforms.WaveformGenerator(pin_num=MAIN_PIN)

    # Give the USB serial connection a moment to settle, then clear any
    # garbage that arrived while the Pico was booting.
    time.sleep_ms(500)
    _drain()

    _prompt()

    while True:
        try:
            line = sys.stdin.readline().strip()
        except KeyboardInterrupt:
            gen.stop()
            print("\r\nCtrl-C received — output stopped. Reset the Pico to restart.")
            break

        if not line:
            _prompt()
            continue

        try:
            choice = int(line)
        except ValueError:
            print("\r  Invalid input '{}' — enter a number from the menu.".format(line))
            _prompt()
            continue

        _dispatch(choice, gen)
        _prompt()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    run()
