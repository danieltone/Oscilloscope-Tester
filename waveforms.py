"""
waveforms.py — Waveform generation engine for Oscilloscope Tester
Raspberry Pi Pico (RP2040) / MicroPython

Square and PWM waveforms use the hardware PWM peripheral directly.
Analog waveforms (sine, triangle, sawtooth) use PWM-based Direct Digital
Synthesis (DDS): the PWM duty cycle is updated at a fixed sample rate to
approximate the target waveform. Connect an RC low-pass filter to the pin
output to recover a clean analog signal (see README.md for filter values).

All public waveform methods block until the user presses any key to stop.
"""

import math
import time
import select
import sys
from machine import Pin, PWM

# ---------------------------------------------------------------------------
# DDS configuration
# ---------------------------------------------------------------------------

# Carrier frequency for DDS analog waveforms.
# Must be >> max waveform frequency. 62.5 kHz works well for waveforms up to
# ~1 kHz and is within the RP2040 PWM hardware range.
PWM_CARRIER_HZ = 62_500

# Mapping of (max waveform Hz → lookup-table sample count).
# More samples = smoother waveform but lower attainable frequency.
_FREQ_TO_SAMPLES = [
    (10,          256),
    (100,          64),
    (1_000,        16),
    (float('inf'),  8),
]


def _sample_count(freq_hz):
    for threshold, n in _FREQ_TO_SAMPLES:
        if freq_hz <= threshold:
            return n
    return 8


# ---------------------------------------------------------------------------
# Lookup-table builders
# ---------------------------------------------------------------------------

def _make_sine(n):
    return [int(32767 + 32767 * math.sin(2 * math.pi * i / n)) for i in range(n)]


def _make_triangle(n):
    half = n // 2
    out = []
    for i in range(n):
        if i <= half:
            out.append(65535 * i // half)
        else:
            out.append(65535 * (n - i) // half)
    return out


def _make_sawtooth(n):
    # Avoid division by zero for n=1 (never used, but defensive)
    d = max(1, n - 1)
    return [65535 * i // d for i in range(n)]


def _make_rev_sawtooth(n):
    d = max(1, n - 1)
    return [65535 * (n - 1 - i) // d for i in range(n)]


# Pre-compute lookup tables for every used sample size at import time so
# there is no runtime delay when a waveform is first selected.
_TABLES = {}
for _n in (8, 16, 64, 256):
    _TABLES[_n] = {
        'sine':         _make_sine(_n),
        'triangle':     _make_triangle(_n),
        'sawtooth':     _make_sawtooth(_n),
        'rev_sawtooth': _make_rev_sawtooth(_n),
    }


# ---------------------------------------------------------------------------
# Serial-input helpers
# ---------------------------------------------------------------------------

def _stdin_ready():
    """Return True if at least one byte is waiting on stdin (non-blocking)."""
    p = select.poll()
    p.register(sys.stdin, select.POLLIN)
    return bool(p.poll(0))


def _drain_stdin():
    """Consume all pending stdin bytes."""
    while _stdin_ready():
        sys.stdin.read(1)


def _wait_for_keypress(check_ms=100):
    """Block until the user presses any key, polling every check_ms ms."""
    while True:
        time.sleep_ms(check_ms)
        if _stdin_ready():
            _drain_stdin()
            return


# ---------------------------------------------------------------------------
# Waveform generator
# ---------------------------------------------------------------------------

class WaveformGenerator:
    """
    Generates test waveforms on a single GPIO pin.

    Parameters
    ----------
    pin_num : int
        GPIO pin number (default 0 = GP0, physical pin 1 on Pico).
    """

    def __init__(self, pin_num=0):
        self.pin_num = pin_num
        self._pwm = None   # active PWM object, or None
        self._gpio = None  # active GPIO Pin object, or None

    # ------------------------------------------------------------------
    # Private setup / teardown
    # ------------------------------------------------------------------

    def _setup_pwm(self, freq_hz):
        self._teardown()
        self._pwm = PWM(Pin(self.pin_num))
        self._pwm.freq(max(8, freq_hz))
        self._pwm.duty_u16(0)

    def _setup_gpio(self):
        self._teardown()
        self._gpio = Pin(self.pin_num, Pin.OUT)
        self._gpio.value(0)

    def _teardown(self):
        if self._pwm is not None:
            try:
                self._pwm.duty_u16(0)
                self._pwm.deinit()
            except Exception:
                pass
            self._pwm = None
        if self._gpio is not None:
            try:
                self._gpio.value(0)
            except Exception:
                pass
            self._gpio = None

    # ------------------------------------------------------------------
    # DDS engine
    # ------------------------------------------------------------------

    def _run_dds(self, table, wave_hz):
        """
        Core DDS loop: update PWM duty cycle from `table` at the correct
        sample rate to produce `wave_hz` Hz on the output pin.

        Uses a busy-wait timing loop for sample-accurate output.
        Stops when the user presses any key.
        """
        n = len(table)
        interval_us = max(1, 1_000_000 // (wave_hz * n))

        self._setup_pwm(PWM_CARRIER_HZ)
        pwm = self._pwm

        tus   = time.ticks_us
        tdiff = time.ticks_diff
        tadd  = time.ticks_add

        # Poll for user stop input at most once per second of output.
        cycles_per_check = max(1, wave_hz)
        cycles = 0
        next_t = tus()

        while True:
            for sample in table:
                pwm.duty_u16(sample)
                next_t = tadd(next_t, interval_us)
                # Busy-wait until it is time for the next sample.
                while tdiff(tus(), next_t) < 0:
                    pass

            cycles += 1
            if cycles >= cycles_per_check:
                cycles = 0
                if _stdin_ready():
                    _drain_stdin()
                    break

        self._teardown()

    # ------------------------------------------------------------------
    # Public API — Square / PWM
    # ------------------------------------------------------------------

    def stop(self):
        """Immediately silence output and set the pin low."""
        self._teardown()

    def square_wave(self, freq_hz):
        """
        Hardware PWM square wave at 50 % duty cycle.
        No external filter needed — probe directly on the pin.
        Frequency range: 8 Hz to ~62.5 MHz.
        """
        self._setup_pwm(freq_hz)
        self._pwm.duty_u16(32768)          # 50 % duty cycle
        _wait_for_keypress()
        self._teardown()

    def pwm_wave(self, freq_hz, duty_pct):
        """
        Hardware PWM at given frequency and duty cycle.

        Parameters
        ----------
        freq_hz  : int   carrier frequency in Hz
        duty_pct : float duty cycle 0–100 %
        """
        self._setup_pwm(freq_hz)
        self._pwm.duty_u16(int(duty_pct / 100.0 * 65535))
        _wait_for_keypress()
        self._teardown()

    # ------------------------------------------------------------------
    # Public API — Analog waveforms (RC filter recommended)
    # ------------------------------------------------------------------

    def sine_wave(self, freq_hz):
        """Sine wave approximation via PWM DDS (RC filter recommended)."""
        n = _sample_count(freq_hz)
        self._run_dds(_TABLES[n]['sine'], freq_hz)

    def triangle_wave(self, freq_hz):
        """Triangle wave via PWM DDS (RC filter recommended)."""
        n = _sample_count(freq_hz)
        self._run_dds(_TABLES[n]['triangle'], freq_hz)

    def sawtooth_wave(self, freq_hz):
        """Rising sawtooth wave via PWM DDS (RC filter recommended)."""
        n = _sample_count(freq_hz)
        self._run_dds(_TABLES[n]['sawtooth'], freq_hz)

    def rev_sawtooth_wave(self, freq_hz):
        """Falling (reverse) sawtooth wave via PWM DDS (RC filter recommended)."""
        n = _sample_count(freq_hz)
        self._run_dds(_TABLES[n]['rev_sawtooth'], freq_hz)

    def dc_level(self, pct):
        """
        DC-like output via high-frequency PWM.
        pct : float  0–100, maps to approx 0–3.3 V after RC filtering.
        Without a filter the scope shows a 62.5 kHz square wave at that
        duty cycle — the DC level is visible as the time-averaged voltage.
        """
        self._setup_pwm(PWM_CARRIER_HZ)
        self._pwm.duty_u16(int(pct / 100.0 * 65535))
        _wait_for_keypress()
        self._teardown()

    # ------------------------------------------------------------------
    # Public API — Special tests
    # ------------------------------------------------------------------

    def burst_wave(self, carrier_hz, on_cycles=10, off_cycles=10):
        """
        Burst mode: `on_cycles` square-wave cycles at `carrier_hz` Hz,
        followed by `off_cycles` worth of silence, repeating indefinitely.

        Uses software GPIO toggling with busy-wait for accurate timing.
        Stops when the user presses any key.
        """
        half_us = max(1, 500_000 // carrier_hz)
        off_us  = off_cycles * 2 * half_us

        self._setup_gpio()
        pin   = self._gpio
        tus   = time.ticks_us
        tdiff = time.ticks_diff
        tadd  = time.ticks_add

        while True:
            # --- ON burst: on_cycles complete square-wave cycles ---
            state = 1
            t = tus()
            for _ in range(on_cycles * 2):   # 2 half-periods per cycle
                pin.value(state)
                state ^= 1
                t = tadd(t, half_us)
                while tdiff(tus(), t) < 0:
                    pass
            pin.value(0)

            # --- OFF silence ---
            t = tadd(tus(), off_us)
            while tdiff(tus(), t) < 0:
                pass

            if _stdin_ready():
                _drain_stdin()
                break

        self._teardown()

    def frequency_sweep(self, start_hz=1, end_hz=1_000_000,
                        steps_per_decade=3, dwell_sec=2):
        """
        Square-wave frequency sweep on a logarithmic scale.

        Parameters
        ----------
        start_hz        : int   starting frequency in Hz
        end_hz          : int   ending frequency in Hz
        steps_per_decade: int   frequency steps per decade (3 = octave steps)
        dwell_sec       : int   seconds to hold each frequency
        """
        factor = 10 ** (1.0 / steps_per_decade)
        freqs  = []
        f      = float(start_hz)
        while f <= end_hz * 1.001:
            freqs.append(max(8, int(round(f))))
            f *= factor

        total = len(freqs)
        print("  Sweep: {} steps, {} s each (~{} s total)".format(
            total, dwell_sec, total * dwell_sec))

        for idx, freq in enumerate(freqs, 1):
            if freq >= 1_000_000:
                label = "{:.3f} MHz".format(freq / 1_000_000)
            elif freq >= 1_000:
                label = "{:.3f} kHz".format(freq / 1_000)
            else:
                label = "{} Hz".format(freq)
            print("  [{}/{}] {}        ".format(idx, total, label), end="\r")

            self._setup_pwm(freq)
            self._pwm.duty_u16(32768)

            deadline = time.ticks_add(time.ticks_ms(), dwell_sec * 1000)
            while time.ticks_diff(time.ticks_ms(), deadline) < 0:
                time.sleep_ms(50)
                if _stdin_ready():
                    _drain_stdin()
                    self._teardown()
                    print("\n  Sweep stopped.")
                    return

        self._teardown()
        print("\n  Sweep complete.")
