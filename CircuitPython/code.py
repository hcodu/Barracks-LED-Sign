import board
import neopixel
import time
import math
import random
import analogio
import wifi
import socketpool
import microcontroller
from rainbowio import colorwheel as _cw
from adafruit_httpserver import Server, Request, Response

# --- Watchdog (auto-reboot on hang) ---
try:
    from watchdog import WatchDogTimer, WatchDogMode
    wdt = WatchDogTimer(timeout=16, mode=WatchDogMode.RESET)
except Exception:
    wdt = None

# --- Pre-compute colorwheel LUT ---
def _cw_tuple(pos):
    c = _cw(pos)
    if isinstance(c, int):
        return ((c >> 16) & 255, (c >> 8) & 255, c & 255)
    return c

CW_LUT = [_cw_tuple(i) for i in range(256)]
del _cw_tuple

# --- Persistent state via NVM ---
# NVM layout: byte 0 = magic (0xBA), byte 1 = effect, bytes 2-3 = speed_pct, byte 4 = brightness (0-100)
nvm = microcontroller.nvm

def load_state():
    if nvm[0] == 0xBA:
        effect = nvm[1]
        speed = (nvm[2] << 8) | nvm[3]
        bright = nvm[4]
        if not (1 <= effect <= 14):
            effect = 1
        if not (10 <= speed <= 1000):
            speed = 100
        if not (0 <= bright <= 100):
            bright = 20
        return effect, speed, bright
    return 1, 100, 20

def _write_nvm(effect, speed_pct, brightness_pct):
    nvm[0] = 0xBA
    nvm[1] = effect
    nvm[2] = (speed_pct >> 8) & 0xFF
    nvm[3] = speed_pct & 0xFF
    nvm[4] = brightness_pct

# Rate-limited NVM save: mark dirty, write every ~30s
_nvm_dirty = False
_nvm_last_write = 0

def save_state(effect, speed_pct, brightness_pct):
    global _nvm_dirty
    _nvm_dirty = True

def flush_nvm_if_needed():
    global _nvm_dirty, _nvm_last_write
    now = time.monotonic()
    if _nvm_dirty and now - _nvm_last_write >= 30:
        _write_nvm(current_effect, speed_pct, brightness_pct)
        _nvm_dirty = False
        _nvm_last_write = now

def flush_nvm_now():
    global _nvm_dirty, _nvm_last_write
    if _nvm_dirty:
        _write_nvm(current_effect, speed_pct, brightness_pct)
        _nvm_dirty = False
        _nvm_last_write = time.monotonic()

# --- Microphone (MAX4466 on GP26/ADC0) ---
mic = analogio.AnalogIn(board.GP26)

# --- LED Setup (early init for status indicator) ---
pixel_pin = board.GP2

B_X = [
    8.9, 24.2, 42.9, 60.9, 78.9, 88.2, 94.9, 102.9, 109.6, 112.2,
    112.2, 111.6, 113.6, 108.2, 108.2, 113.6, 112.9, 114.2, 112.2, 108.2,
    96.9, 81.6, 67.6, 54.9, 45.6, 32.9, 14.9, 2.9, 2.2, 8.9,
    27.6, 44.2, 58.2, 72.9, 81.6, 80.9, 81.6, 81.6, 74.9, 66.9,
    56.9, 42.2, 35.6, 34.9, 34.9, 22.9, 7.6, 4.2, 4.2, 4.2,
    4.9, 5.6, 17.6, 30.9, 46.2, 61.6, 73.6, 81.6, 81.6, 82.9,
    82.9, 78.9, 68.9, 56.2, 46.9, 31.6, 33.6, 32.9, 33.6, 20.2,
    8.9, 6.9, 4.9, 4.2,
]
A_X = [
    135.4, 149.7, 161.1, 165.4, 176.1, 187.5, 199.7, 210.4, 221.1, 226.1,
    233.2, 246.8, 249.7, 246.8, 242.5, 239.7, 236.8, 232.5, 228.2, 225.4,
    222.5, 218.2, 216.1, 211.8, 204.0, 196.8, 196.8, 199.0, 201.8, 202.5,
    205.4, 206.8, 208.2, 209.7, 201.8, 193.2, 183.2, 179.7, 181.1, 184.0,
    185.4, 188.2, 189.7, 188.2, 189.7, 181.8, 174.0, 169.7, 165.4, 162.5,
    159.0, 156.8, 153.2, 150.4, 146.8, 144.0, 141.1, 138.2,
]
R_X = [
    284.7, 295.4, 306.8, 307.5, 308.2, 308.2, 309.0, 319.0, 329.7, 341.1,
    355.4, 359.0, 359.7, 361.1, 360.4, 359.7, 374.0, 387.5, 389.0, 386.8,
    386.8, 386.1, 386.8, 383.2, 383.2, 388.2, 388.2, 386.8, 387.5, 370.4,
    379.7, 358.2, 346.1, 333.2, 321.1, 304.7, 289.0, 281.1, 282.5, 295.4,
    309.7, 322.5, 338.2, 349.7, 359.7, 361.1, 360.4, 359.7, 350.4, 341.8,
    331.1, 319.7, 308.2, 308.2, 308.2, 308.2, 295.4, 282.5, 283.2, 282.5,
    282.5, 282.5, 282.5, 282.5, 282.5, 283.2, 283.2,
]
C_X = [
    722.1, 735.9, 749.0, 762.9, 778.3, 788.3, 795.9, 795.9, 772.9, 785.2,
    767.5, 768.3, 759.8, 749.8, 739.0, 729.0, 715.9, 717.5, 717.5, 717.5,
    717.5, 718.3, 718.3, 718.3, 717.5, 725.9, 735.2, 745.2, 755.9, 766.7,
    768.3, 782.1, 795.2, 795.9, 789.0, 778.3, 766.7, 755.2, 745.2, 734.4,
    719.0, 708.3, 694.4, 688.3, 688.3, 688.3, 689.0, 688.3, 689.0, 689.8,
    689.0, 689.0, 695.9,
]
K_X = [
    824.7, 842.9, 847.4, 848.3, 848.3, 848.3, 849.2, 861.0, 865.6, 871.9,
    877.4, 885.6, 891.9, 901.9, 912.9, 926.5, 922.9, 917.4, 909.2, 903.8,
    897.4, 887.4, 881.0, 882.9, 887.4, 894.7, 901.0, 908.3, 915.6, 922.9,
    911.9, 900.1, 894.7, 885.6, 880.1, 872.9, 865.6, 859.2, 850.1, 850.1,
    850.1, 850.1, 849.2, 848.3, 833.8, 822.9, 822.9, 822.9, 821.9, 821.9,
    823.8, 824.7, 824.7, 823.8, 824.7, 823.8, 823.8,
]
S_X = [
    975.4, 988.7, 1004.3, 1019.8, 1028.7, 1037.6, 1048.7, 1049.8, 1051.0, 1049.8,
    1048.7, 1038.7, 1026.5, 1012.1, 1003.2, 989.8, 977.6, 975.4, 973.2, 975.4,
    984.3, 994.3, 1005.4, 1016.5, 1024.3, 1024.3, 1035.4, 1047.6, 1052.1, 1051.0,
    1039.8, 1027.6, 1011.0, 997.6, 986.5, 973.2, 962.1, 953.2, 946.5, 945.4,
    944.3, 945.4, 952.1, 959.8, 968.7, 981.0, 995.4, 1011.0, 1019.8, 1024.3,
    1026.5, 1024.3, 1018.7, 1007.6, 997.6, 983.2, 973.2, 971.0, 957.6, 946.5,
    945.4, 945.4, 955.4, 963.2,
]

R2_SHIFT = 134
A2_SHIFT = 414

ALL_X = B_X + A_X + R_X + [x + R2_SHIFT for x in R_X] + [x + A2_SHIFT for x in A_X] + C_X + K_X + S_X

num_pixels = len(ALL_X)
pixels = neopixel.NeoPixel(pixel_pin, num_pixels, auto_write=False, brightness=0.2)

x_min = min(ALL_X)
x_max = max(ALL_X)
x_range = x_max - x_min
HUES = [int((x - x_min) / x_range * 255) for x in ALL_X]

# Crossfade buffer
old_frame = [(0, 0, 0)] * num_pixels
transition_remaining = 0
TRANSITION_FRAMES = 15

LETTER_STARTS = [0, 74, 132, 199, 266, 324, 377, 434]
LETTER_SIZES = [74, 58, 67, 67, 58, 53, 57, 64]

del ALL_X, B_X, A_X, R_X, C_X, K_X, S_X

# --- WiFi with status LEDs ---
import os
WIFI_SSID = os.getenv("CIRCUITPY_WIFI_SSID") or "codu"
WIFI_PASS = os.getenv("CIRCUITPY_WIFI_PASSWORD") or "psolutions1234"

print(WIFI_SSID)

def connect_wifi():
    try:
        wifi.radio.connect(WIFI_SSID, WIFI_PASS)
        print("Connected:", wifi.radio.ipv4_address)
        return True
    except Exception as e:
        print("WiFi failed:", e)
        return False

# Red while connecting
pixels.fill((50, 0, 0))
pixels.show()
time.sleep(2)

connect_wifi()

# Pulse green twice
for _ in range(2):
    for i in range(64):
        pixels.fill((0, i // 3, 0))
        pixels.show()
        time.sleep(0.00005)

pool = socketpool.SocketPool(wifi.radio)
server = Server(pool)

# --- Shared lookup tables ---
SIN_LUT = [int((math.sin(i * 6.283 / 256) + 1.0) * 127.5) for i in range(256)]

# --- State class (attribute access is faster than dict lookups) ---
class State:
    __slots__ = ('offset', 't', 'hue', 'pos', 'chase_phase', 'chase_letter',
                 'chase_step', 'chase_wait', 'drops', 'ripples', 'hb_t',
                 'sound_level', 'sound_peak', 'sound_hue')

state = State()

# --- State ---
current_effect, speed_pct, brightness_pct = load_state()
pixels.brightness = brightness_pct / 100
power_on = True
wifi_check_counter = 0

def reset_state():
    state.offset = 0
    state.t = 0
    state.hue = 0
    state.pos = 0
    state.chase_phase = 0
    state.chase_letter = 0
    state.chase_step = 0
    state.chase_wait = 0
    state.drops = [random.randint(0, LETTER_SIZES[li] - 1) for li in range(8)]
    state.ripples = []
    state.hb_t = 0
    state.sound_level = 0
    state.sound_peak = 1000
    state.sound_hue = 0

reset_state()

# --- Pre-computed tables for specific effects ---
# Fire
fire_lut = []
for h in range(256):
    if h < 85:
        fire_lut.append((h * 3, 0, 0))
    elif h < 170:
        fire_lut.append((255, (h - 85) * 3, 0))
    else:
        fire_lut.append((255, 255, (h - 170) * 3))
base_heat = [180 + (HUES[i] >> 2) for i in range(num_pixels)]

# Color wave
wave_width = 90
wave_lut = []
for d in range(wave_width):
    b = (wave_width - d) * 255 // wave_width
    wave_lut.append((b, b * 80 // 255, 0))
wave_bg = (0, 0, 40)

# Matrix rain
trail_len = 8
trail_colors = [(0, 255 * (trail_len - t) // trail_len, 0) for t in range(trail_len)]
trail_tip = (180, 255, 180)

# Comet
comet_tail = 60
comet_fade = [((comet_tail - t) * (comet_tail - t) * 255) // (comet_tail * comet_tail) for t in range(comet_tail)]

getrandbits = random.getrandbits

# Heartbeat rhythm: two bumps then a pause (mapped over 256 steps)
hb_lut = []
for i in range(256):
    if i < 40:
        hb_lut.append(SIN_LUT[i * 128 // 40])
    elif i < 60:
        hb_lut.append(0)
    elif i < 100:
        hb_lut.append(SIN_LUT[(i - 60) * 128 // 40])
    else:
        hb_lut.append(0)

# Marquee
marquee_width = 40

# --- Effect frame functions (one frame each, no loops) ---

def frame_rainbow_sweep():
    off = state.offset
    for i in range(num_pixels):
        pixels[i] = CW_LUT[(HUES[i] - off) % 256]
    state.offset = (off + 2) % 256

def frame_breathing_pulse():
    t = state.t
    hue = state.hue
    b = SIN_LUT[t]
    r, g, bl = CW_LUT[hue]
    pixels.fill((r * b >> 8, g * b >> 8, bl * b >> 8))
    state.t = (t + 1) % 256
    state.hue = (hue + 1) % 256

def frame_letter_chase():
    phase = state.chase_phase
    if phase == 0:
        li = state.chase_letter
        start = LETTER_STARTS[li]
        size = LETTER_SIZES[li]
        color = CW_LUT[(li * 32) % 256]
        for j in range(start, start + size):
            pixels[j] = color
        state.chase_letter = li + 1
        if li + 1 >= 8:
            state.chase_phase = 1
            state.chase_wait = 25
    elif phase == 1:
        state.chase_wait -= 1
        if state.chase_wait <= 0:
            state.chase_phase = 2
            state.chase_step = 20
    elif phase == 2:
        step = state.chase_step
        for li in range(8):
            start = LETTER_STARTS[li]
            size = LETTER_SIZES[li]
            r, g, b = CW_LUT[(li * 32) % 256]
            color = (r * step // 20, g * step // 20, b * step // 20)
            for j in range(start, start + size):
                pixels[j] = color
        state.chase_step = step - 1
        if step - 1 <= 0:
            state.chase_phase = 0
            state.chase_letter = 0
            state.chase_wait = 15

def frame_sparkle():
    pixels.fill((15, 10, 5))
    spark = (255, 220, 180)
    for _ in range(25):
        pixels[random.randint(0, num_pixels - 1)] = spark

def frame_color_wave():
    pos = state.pos
    for i in range(num_pixels):
        dist = HUES[i] - pos
        if dist < 0:
            dist = -dist
        if dist > 128:
            dist = 256 - dist
        if dist < wave_width:
            pixels[i] = wave_lut[dist]
        else:
            pixels[i] = wave_bg
    state.pos = (pos + 3) % 256

def frame_ping_pong():
    t = state.t
    for li in range(8):
        start = LETTER_STARTS[li]
        size = LETTER_SIZES[li]
        blend = SIN_LUT[(t + li * 33) % 256]
        inv = 255 - blend
        color = (blend, inv * 50 // 255, inv)
        for j in range(start, start + size):
            pixels[j] = color
    state.t = (t + 2) % 256

def frame_fire():
    for i in range(num_pixels):
        heat = base_heat[i] - (getrandbits(7) % 81)
        if heat < 0:
            heat = 0
        pixels[i] = fire_lut[heat]

def frame_matrix_rain():
    pixels.fill((0, 0, 0))
    drops = state.drops
    for li in range(8):
        start = LETTER_STARTS[li]
        size = LETTER_SIZES[li]
        head = drops[li]
        for t in range(trail_len):
            pixels[start + (head - t) % size] = trail_colors[t]
        pixels[start + head] = trail_tip
        drops[li] = (drops[li] + 1) % size

def frame_solid_cycle():
    hue = state.hue
    pixels.fill(CW_LUT[hue])
    state.hue = (hue + 1) % 256

def frame_comet():
    pos = state.pos
    pixels.fill((0, 0, 0))
    for t in range(comet_tail):
        idx = pos - t
        if 0 <= idx < num_pixels:
            f = comet_fade[t]
            r, g, b = CW_LUT[(pos + t * 3) % 256]
            pixels[idx] = (r * f >> 8, g * f >> 8, b * f >> 8)
    if 0 <= pos < num_pixels:
        pixels[pos] = (255, 255, 255)
    state.pos = pos + 2
    if pos + 2 >= num_pixels + comet_tail:
        state.pos = 0

def frame_raindrop_ripple():
    ripples = state.ripples
    if random.randint(0, 5) == 0:
        origin = random.randint(0, 255)
        ripples.append([origin, 0])
    pixels.fill((0, 0, 0))
    for rip in ripples:
        center, radius = rip
        for i in range(num_pixels):
            dist = HUES[i] - center
            if dist < 0:
                dist = -dist
            if dist > 128:
                dist = 256 - dist
            ring_dist = dist - radius
            if ring_dist < 0:
                ring_dist = -ring_dist
            if ring_dist < 8:
                bright = (8 - ring_dist) * 255 // 8
                fade = 255 - radius * 3
                if fade < 0:
                    fade = 0
                val = bright * fade >> 8
                r0, g0, b0 = pixels[i]
                if val > r0:
                    pixels[i] = (val, val, val)
        rip[1] += 3
    state.ripples = [r for r in ripples if r[1] < 85]

def frame_heartbeat():
    t = state.hb_t
    beat = hb_lut[t]
    for i in range(num_pixels):
        dist = HUES[i] - 128
        if dist < 0:
            dist = -dist
        falloff = 255 - dist
        if falloff < 0:
            falloff = 0
        bright = beat * falloff >> 8
        pixels[i] = (bright, 0, bright >> 3)
    state.hb_t = (t + 3) % 256

def frame_marquee():
    pos = state.pos
    for i in range(num_pixels):
        dist = HUES[i] - pos
        if dist < 0:
            dist = -dist
        if dist > 128:
            dist = 256 - dist
        if dist < marquee_width:
            bright = (marquee_width - dist) * 255 // marquee_width
            pixels[i] = (bright, bright * 200 // 255, bright * 80 // 255)
        else:
            pixels[i] = (8, 6, 2)
    state.pos = (pos + 2) % 256

def read_mic():
    lo = 65535
    hi = 0
    for _ in range(80):
        v = mic.value
        if v < lo:
            lo = v
        if v > hi:
            hi = v
    return hi - lo

NOISE_FLOOR = 300

_mic_print_counter = 0

def frame_sound_reactive():
    global _mic_print_counter
    raw_amp = read_mic()
    _mic_print_counter += 1
    if _mic_print_counter >= 30:
        print("mic raw:", raw_amp)
        _mic_print_counter = 0
    amp = raw_amp
    # Cut anything below noise floor
    if amp < NOISE_FLOOR:
        amp = 0
    else:
        amp = amp - NOISE_FLOOR
    # Auto-calibrate: track peak with slow decay
    if amp > state.sound_peak:
        state.sound_peak = amp
    else:
        state.sound_peak = state.sound_peak - (state.sound_peak >> 7) - 1
        if state.sound_peak < 500:
            state.sound_peak = 500
    # Normalize 0-255
    level = amp * 255 // state.sound_peak
    if level > 255:
        level = 255
    # Smooth with previous frame
    state.sound_level = (state.sound_level + level) >> 1
    sl = state.sound_level
    # Color shifts with volume
    state.sound_hue = (state.sound_hue + 1 + (sl >> 5)) % 256
    # Light up letters left-to-right based on volume
    # At low volume only B lights, at max all 8 letters light
    letters_lit = 1 + sl * 7 // 255
    for li in range(8):
        start = LETTER_STARTS[li]
        size = LETTER_SIZES[li]
        if li < letters_lit:
            frac = sl if li < letters_lit - 1 else (sl * 8 - li * 255) % 256
            if frac > 255:
                frac = 255
            r, g, b = CW_LUT[(state.sound_hue + li * 32) % 256]
            color = (r * frac >> 8, g * frac >> 8, b * frac >> 8)
            for j in range(start, start + size):
                pixels[j] = color
        else:
            for j in range(start, start + size):
                pixels[j] = (0, 0, 0)

# Effect lookup and base frame delays
EFFECTS = {
    1: (frame_rainbow_sweep, 0.02),
    2: (frame_breathing_pulse, 0.02),
    3: (frame_letter_chase, 0.04),
    4: (frame_sparkle, 0.1),
    5: (frame_color_wave, 0.02),
    6: (frame_ping_pong, 0.02),
    7: (frame_fire, 0.04),
    8: (frame_matrix_rain, 0.05),
    9: (frame_solid_cycle, 0.03),
    10: (frame_comet, 0.015),
    11: (frame_raindrop_ripple, 0.03),
    12: (frame_heartbeat, 0.02),
    13: (frame_marquee, 0.02),
    14: (frame_sound_reactive, 0.005),
}

# --- HTTP Routes ---

def start_transition():
    global old_frame, transition_remaining
    old_frame = [pixels[i] for i in range(num_pixels)]
    transition_remaining = TRANSITION_FRAMES

@server.route("/effect/<num>")
def route_effect(request: Request, num: str):
    global current_effect
    try:
        n = int(num)
        if 1 <= n <= 14:
            start_transition()
            current_effect = n
            reset_state()
            save_state(current_effect, speed_pct, brightness_pct)
            return Response(request, f"Effect set to {n}")
    except ValueError:
        pass
    return Response(request, "Invalid effect (1-14)", status=(400, "Bad Request"))

@server.route("/power/<cmd>")
def route_power(request: Request, cmd: str):
    global power_on
    if cmd == "on":
        power_on = True
        reset_state()
        return Response(request, "Power ON")
    elif cmd == "off":
        power_on = False
        pixels.fill((0, 0, 0))
        pixels.show()
        flush_nvm_now()
        return Response(request, "Power OFF")
    return Response(request, "Invalid (on/off)", status=(400, "Bad Request"))

@server.route("/speed/up")
def route_speed_up(request: Request):
    global speed_pct
    speed_pct = min(speed_pct * 3 // 2, 800)
    save_state(current_effect, speed_pct, brightness_pct)
    return Response(request, f"Speed: {speed_pct}%")

@server.route("/speed/down")
def route_speed_down(request: Request):
    global speed_pct
    speed_pct = max(speed_pct // 2, 12)
    save_state(current_effect, speed_pct, brightness_pct)
    return Response(request, f"Speed: {speed_pct}%")

@server.route("/speed/reset")
def route_speed_reset(request: Request):
    global speed_pct
    speed_pct = 100
    save_state(current_effect, speed_pct, brightness_pct)
    return Response(request, "Speed: 100%")

@server.route("/brightness/<val>")
def route_brightness(request: Request, val: str):
    global brightness_pct
    try:
        v = int(val)
        if 0 <= v <= 100:
            brightness_pct = v
            pixels.brightness = brightness_pct / 100
            save_state(current_effect, speed_pct, brightness_pct)
            return Response(request, f"Brightness: {brightness_pct}%")
    except ValueError:
        pass
    return Response(request, "Invalid brightness (0-100)", status=(400, "Bad Request"))

@server.route("/status")
def route_status(request: Request):
    return Response(request, f"power={'on' if power_on else 'off'} effect={current_effect} speed={speed_pct}% brightness={brightness_pct}%")

# --- Start server ---
server.start(str(wifi.radio.ipv4_address), port=80)
print(f"Server running on {wifi.radio.ipv4_address} | Effect: {current_effect} | Speed: {speed_pct}% | Brightness: {brightness_pct}%")

# --- Main loop ---
while True:
    # Feed watchdog
    if wdt:
        wdt.feed()

    # WiFi auto-reconnect (check every ~500 frames)
    wifi_check_counter += 1
    if wifi_check_counter >= 500:
        wifi_check_counter = 0
        if wifi.radio.ipv4_address is None:
            print("WiFi lost, reconnecting...")
            connect_wifi()

    # Poll HTTP server
    try:
        server.poll()
    except Exception as e:
        print("Server error:", e)

    # Rate-limited NVM flush
    flush_nvm_if_needed()

    if power_on and current_effect in EFFECTS:
        func, base_delay = EFFECTS[current_effect]
        func()

        if transition_remaining > 0:
            blend_new = (TRANSITION_FRAMES - transition_remaining + 1) * 255 // TRANSITION_FRAMES
            blend_old = 255 - blend_new
            for i in range(num_pixels):
                or0, og, ob = old_frame[i]
                nr, ng, nb = pixels[i]
                pixels[i] = (
                    (or0 * blend_old + nr * blend_new) >> 8,
                    (og * blend_old + ng * blend_new) >> 8,
                    (ob * blend_old + nb * blend_new) >> 8,
                )
            transition_remaining -= 1

        pixels.show()
        time.sleep(base_delay * 100 / speed_pct)
    else:
        time.sleep(0.1)
