import machine
import neopixel
import time
import math
import random
import network
import socket
import json

# --- Load config ---
try:
    with open("config.json", "r") as f:
        config = json.load(f)
except (OSError, ValueError):
    config = {}

WIFI_SSID = config.get("wifi_ssid", "codu")
WIFI_PASS = config.get("wifi_password", "psolutions1234")

# --- Pre-compute colorwheel LUT ---
def _colorwheel(pos):
    pos = pos % 256
    if pos < 85:
        return (255 - pos * 3, pos * 3, 0)
    elif pos < 170:
        pos -= 85
        return (0, 255 - pos * 3, pos * 3)
    else:
        pos -= 170
        return (pos * 3, 0, 255 - pos * 3)

CW_LUT = [_colorwheel(i) for i in range(256)]

# --- Persistent state via JSON ---
STATE_FILE = "state.json"

def load_state():
    try:
        with open(STATE_FILE, "r") as f:
            s = json.load(f)
        effect = s.get("effect", 1)
        speed = s.get("speed", 100)
        bright = s.get("brightness", 20)
        if not (1 <= effect <= 14):
            effect = 1
        if not (10 <= speed <= 1000):
            speed = 100
        if not (0 <= bright <= 100):
            bright = 20
        return effect, speed, bright
    except (OSError, ValueError):
        return 1, 100, 20

def _write_state(effect, speed_pct, brightness_pct):
    with open(STATE_FILE, "w") as f:
        json.dump({"effect": effect, "speed": speed_pct, "brightness": brightness_pct}, f)

# Rate-limited state save
_state_dirty = False
_state_last_write = 0

def save_state(effect, speed_pct, brightness_pct):
    global _state_dirty
    _state_dirty = True

def flush_state_if_needed():
    global _state_dirty, _state_last_write
    now = time.ticks_ms()
    if _state_dirty and time.ticks_diff(now, _state_last_write) >= 30000:
        _write_state(current_effect, speed_pct, brightness_pct)
        _state_dirty = False
        _state_last_write = now

def flush_state_now():
    global _state_dirty, _state_last_write
    if _state_dirty:
        _write_state(current_effect, speed_pct, brightness_pct)
        _state_dirty = False
        _state_last_write = time.ticks_ms()

# --- LED Setup ---
pixel_pin = machine.Pin(2)

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
pixels = neopixel.NeoPixel(pixel_pin, num_pixels)

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

VERT_SEGS = []
for _li in range(8):
    _s = LETTER_STARTS[_li]
    _sz = LETTER_SIZES[_li]
    _lx = ALL_X[_s:_s + _sz]
    _cx = (min(_lx) + max(_lx)) / 2
    _rs = 0
    for _i in range(1, _sz):
        if abs(_lx[_i] - _lx[_i - 1]) > 10:
            if _i - _rs >= 4:
                _seg = list(range(_s + _rs, _s + _i))
                if sum(_lx[_rs:_i]) / (_i - _rs) > _cx:
                    _seg.reverse()
                VERT_SEGS.append(_seg)
            _rs = _i
    if _sz - _rs >= 4:
        _seg = list(range(_s + _rs, _s + _sz))
        if sum(_lx[_rs:_sz]) / (_sz - _rs) > _cx:
            _seg.reverse()
        VERT_SEGS.append(_seg)

del ALL_X, B_X, A_X, R_X, C_X, K_X, S_X

# --- WiFi ---
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    time.sleep(1)
    if not wlan.isconnected():
        print(f"Connecting to {WIFI_SSID}...")
        wlan.connect(WIFI_SSID, WIFI_PASS)
        timeout = 20
        while not wlan.isconnected() and timeout > 0:
            time.sleep(0.5)
            timeout -= 1
    if wlan.isconnected():
        print("Connected:", wlan.ifconfig()[0])
        return wlan
    else:
        print("WiFi failed")
        return None

# Red while connecting
for i in range(num_pixels):
    pixels[i] = (50, 0, 0)
pixels.write()
time.sleep(2)

wlan = connect_wifi()

# Pulse green twice
for _ in range(2):
    for i in range(64):
        pixels.fill((0, i // 3, 0))
        pixels.write()
        time.sleep_us(50)

# --- Brightness-scaled LUTs ---
brightness_scale = 20

def _scale(r, g, b, s):
    return (r * s // 100, g * s // 100, b * s // 100)

def rebuild_brightness_luts():
    global CW_LUT_B, fire_lut_b, wave_lut_b, wave_bg_b, trail_colors_b, trail_tip_b
    s = brightness_scale
    CW_LUT_B = [_scale(r, g, b, s) for r, g, b in CW_LUT]
    fire_lut_b = [_scale(r, g, b, s) for r, g, b in fire_lut]
    wave_lut_b = [_scale(r, g, b, s) for r, g, b in wave_lut]
    wave_bg_b = _scale(*wave_bg, s)
    trail_colors_b = [_scale(r, g, b, s) for r, g, b in trail_colors]
    trail_tip_b = _scale(*trail_tip, s)

# --- HTTP Server ---
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_socket.bind(("0.0.0.0", 80))
server_socket.listen(5)
server_socket.setblocking(False)

def parse_request(client):
    try:
        client.settimeout(1.0)
        data = client.recv(1024)
        if not data:
            return None, None
        request_line = data.decode("utf-8").split("\r\n")[0]
        parts = request_line.split(" ")
        if len(parts) >= 2:
            return parts[0], parts[1]
        return None, None
    except Exception:
        return None, None

def send_response(client, status, body):
    response = f"HTTP/1.1 {status}\r\nContent-Type: text/plain\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n{body}"
    client.send(response.encode("utf-8"))
    client.close()

def handle_request(method, path):
    global current_effect, speed_pct, brightness_pct, brightness_scale, power_on

    if path.startswith("/effect/"):
        try:
            n = int(path.split("/effect/")[1])
            if 1 <= n <= 14:
                start_transition()
                current_effect = n
                reset_state()
                save_state(current_effect, speed_pct, brightness_pct)
                return "200 OK", f"Effect set to {n}"
        except ValueError:
            pass
        return "400 Bad Request", "Invalid effect (1-14)"

    elif path.startswith("/power/"):
        cmd = path.split("/power/")[1]
        if cmd == "on":
            power_on = True
            reset_state()
            return "200 OK", "Power ON"
        elif cmd == "off":
            power_on = False
            pixels.fill((0, 0, 0))
            pixels.write()
            flush_state_now()
            return "200 OK", "Power OFF"
        return "400 Bad Request", "Invalid (on/off)"

    elif path == "/speed/up":
        speed_pct = min(speed_pct * 3 // 2, 800)
        save_state(current_effect, speed_pct, brightness_pct)
        return "200 OK", f"Speed: {speed_pct}%"

    elif path == "/speed/down":
        speed_pct = max(speed_pct // 2, 12)
        save_state(current_effect, speed_pct, brightness_pct)
        return "200 OK", f"Speed: {speed_pct}%"

    elif path == "/speed/reset":
        speed_pct = 100
        save_state(current_effect, speed_pct, brightness_pct)
        return "200 OK", "Speed: 100%"

    elif path.startswith("/brightness/"):
        try:
            v = int(path.split("/brightness/")[1])
            if 0 <= v <= 100:
                brightness_pct = v
                brightness_scale = v
                rebuild_brightness_luts()
                save_state(current_effect, speed_pct, brightness_pct)
                return "200 OK", f"Brightness: {brightness_pct}%"
        except ValueError:
            pass
        return "400 Bad Request", "Invalid brightness (0-100)"

    elif path == "/status":
        return "200 OK", f"power={'on' if power_on else 'off'} effect={current_effect} speed={speed_pct}% brightness={brightness_pct}%"

    return "404 Not Found", "Not found"

def poll_server():
    try:
        client, addr = server_socket.accept()
        method, path = parse_request(client)
        if method and path:
            status, body = handle_request(method, path)
            send_response(client, status, body)
        else:
            client.close()
    except OSError:
        pass

# --- Shared lookup tables ---
SIN_LUT = [int((math.sin(i * 6.283 / 256) + 1.0) * 127.5) for i in range(256)]

# --- State class ---
class State:
    __slots__ = ('offset', 't', 'hue', 'pos', 'chase_phase', 'chase_letter',
                 'chase_step', 'chase_wait', 'drops', 'ripples', 'hb_t', 'drops2')

state = State()

# --- State ---
current_effect, speed_pct, brightness_pct = load_state()
brightness_scale = brightness_pct
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
    state.drops2 = [random.randint(-len(VERT_SEGS[i]), len(VERT_SEGS[i]) - 1) for i in range(len(VERT_SEGS))]
    state.ripples = []
    state.hb_t = 0

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

# Heartbeat rhythm
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

# Build brightness-scaled LUTs
rebuild_brightness_luts()

# --- Effect frame functions ---

def frame_rainbow_sweep():
    off = state.offset
    for i in range(num_pixels):
        pixels[i] = CW_LUT_B[(HUES[i] - off) % 256]
    state.offset = (off + 2) % 256

def frame_breathing_pulse():
    t = state.t
    hue = state.hue
    b = SIN_LUT[t]
    r, g, bl = CW_LUT_B[hue]
    pixels.fill((r * b >> 8, g * b >> 8, bl * b >> 8))
    state.t = (t + 1) % 256
    state.hue = (hue + 1) % 256

def frame_letter_chase():
    phase = state.chase_phase
    if phase == 0:
        li = state.chase_letter
        start = LETTER_STARTS[li]
        size = LETTER_SIZES[li]
        color = CW_LUT_B[(li * 32) % 256]
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
            r, g, b = CW_LUT_B[(li * 32) % 256]
            color = (r * step // 20, g * step // 20, b * step // 20)
            for j in range(start, start + size):
                pixels[j] = color
        state.chase_step = step - 1
        if step - 1 <= 0:
            state.chase_phase = 0
            state.chase_letter = 0
            state.chase_wait = 15

def frame_sparkle():
    s = brightness_scale
    pixels.fill((15 * s // 100, 10 * s // 100, 5 * s // 100))
    spark = (255 * s // 100, 220 * s // 100, 180 * s // 100)
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
            pixels[i] = wave_lut_b[dist]
        else:
            pixels[i] = wave_bg_b
    state.pos = (pos + 3) % 256

def frame_ping_pong():
    t = state.t
    s = brightness_scale
    for li in range(8):
        start = LETTER_STARTS[li]
        size = LETTER_SIZES[li]
        blend = SIN_LUT[(t + li * 33) % 256]
        inv = 255 - blend
        color = (blend * s // 100, inv * 50 * s // 25500, inv * s // 100)
        for j in range(start, start + size):
            pixels[j] = color
    state.t = (t + 2) % 256

def frame_fire():
    for i in range(num_pixels):
        heat = base_heat[i] - (getrandbits(7) % 81)
        if heat < 0:
            heat = 0
        pixels[i] = fire_lut_b[heat]

def frame_matrix_rain():
    pixels.fill((0, 0, 0))
    drops = state.drops
    for li in range(8):
        start = LETTER_STARTS[li]
        size = LETTER_SIZES[li]
        head = drops[li]
        for t in range(trail_len):
            pixels[start + (head - t) % size] = trail_colors_b[t]
        pixels[start + head] = trail_tip_b
        drops[li] = (drops[li] + 1) % size

def frame_matrix_rain_2():
    pixels.fill((0, 0, 0))
    drops = state.drops2
    for si in range(len(VERT_SEGS)):
        seg = VERT_SEGS[si]
        seg_len = len(seg)
        head = drops[si]
        for t in range(trail_len):
            idx = head - t
            if 0 <= idx < seg_len:
                pixels[seg[idx]] = trail_colors_b[t]
        if 0 <= head < seg_len:
            pixels[seg[head]] = trail_tip_b
        drops[si] += 1
        if drops[si] >= seg_len + trail_len:
            drops[si] = -random.randint(0, seg_len)

def frame_solid_cycle():
    hue = state.hue
    pixels.fill(CW_LUT_B[hue])
    state.hue = (hue + 1) % 256

def frame_comet():
    pos = state.pos
    pixels.fill((0, 0, 0))
    for t in range(comet_tail):
        idx = pos - t
        if 0 <= idx < num_pixels:
            f = comet_fade[t]
            r, g, b = CW_LUT_B[(pos + t * 3) % 256]
            pixels[idx] = (r * f >> 8, g * f >> 8, b * f >> 8)
    if 0 <= pos < num_pixels:
        s = brightness_scale
        pixels[pos] = (255 * s // 100, 255 * s // 100, 255 * s // 100)
    state.pos = pos + 2
    if pos + 2 >= num_pixels + comet_tail:
        state.pos = 0

def frame_raindrop_ripple():
    ripples = state.ripples
    s = brightness_scale
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
                val = bright * fade * s // 25500
                r0, g0, b0 = pixels[i]
                if val > r0:
                    pixels[i] = (val, val, val)
        rip[1] += 3
    state.ripples = [r for r in ripples if r[1] < 85]

def frame_heartbeat():
    t = state.hb_t
    beat = hb_lut[t]
    s = brightness_scale
    for i in range(num_pixels):
        dist = HUES[i] - 128
        if dist < 0:
            dist = -dist
        falloff = 255 - dist
        if falloff < 0:
            falloff = 0
        bright = beat * falloff * s // 25500
        pixels[i] = (bright, 0, bright >> 3)
    state.hb_t = (t + 3) % 256

def frame_marquee():
    pos = state.pos
    s = brightness_scale
    dim = (8 * s // 100, 6 * s // 100, 2 * s // 100)
    for i in range(num_pixels):
        dist = HUES[i] - pos
        if dist < 0:
            dist = -dist
        if dist > 128:
            dist = 256 - dist
        if dist < marquee_width:
            bright = (marquee_width - dist) * 255 // marquee_width
            pixels[i] = (bright * s // 100, bright * 200 * s // 25500, bright * 80 * s // 25500)
        else:
            pixels[i] = dim
    state.pos = (pos + 2) % 256

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
    14: (frame_matrix_rain_2, 0.05),
}

# --- Transition helper ---
def start_transition():
    global transition_remaining
    for i in range(num_pixels):
        old_frame[i] = pixels[i]
    transition_remaining = TRANSITION_FRAMES

# --- Start server ---
if wlan and wlan.isconnected():
    print(f"Server running on {wlan.ifconfig()[0]} | Effect: {current_effect} | Speed: {speed_pct}% | Brightness: {brightness_pct}%")
else:
    print("Running without WiFi")

# --- Main loop ---
while True:
    # WiFi auto-reconnect
    wifi_check_counter += 1
    if wifi_check_counter >= 500:
        wifi_check_counter = 0
        if wlan and not wlan.isconnected():
            print("WiFi lost, reconnecting...")
            wlan = connect_wifi()

    # Poll HTTP server
    poll_server()

    # Rate-limited state flush
    flush_state_if_needed()

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

        pixels.write()
        time.sleep(base_delay * 100 / speed_pct)
    else:
        time.sleep(0.1)
