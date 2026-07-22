# BARRACKS LED Sign

<!-- TODO: Add hero photo of the completed sign -->
![BARRACKS Sign](placeholder-photo.jpg)

A WiFi-controlled LED sign spelling **BARRACKS** using 498 individually addressable WS2812B NeoPixels, 3D printed letter housings, and a microcontroller running 14 animated lighting effects -- all controllable from any device on the network via a simple HTTP API.

> **Why "BARRACKS"?** That's the name of our college house. Every house needs a sign, and every sign needs 498 LEDs and a rainbow scroll effect. We don't make the rules.

## Features

- 498 WS2812B LEDs across 8 individually wired letters
- 14 animation effects (rainbow, fire, matrix rain, comet, heartbeat, and more)
- WiFi HTTP API for controlling effects, brightness, speed, and power from any browser or script
- Over-the-air code upload (MicroPython version) -- push new code without plugging in USB
- Automatic crash recovery with rollback to last known-good code
- Persistent settings survive power cycles
- Fully 3D printed letter frames, diffuser inserts, backings, and inter-letter stands

## Demo

<!-- TODO: Add GIF or video link showing effects -->

## Hardware

### Bill of Materials

| Component                                 | Quantity    | Notes                                    |
| ----------------------------------------- | ----------- | ---------------------------------------- |
| WS2812B LED strip (60 LEDs/m)             | ~8.3m total | Cut to per-letter lengths                |
| Raspberry Pi Pico W or ESP32-C3 SuperMini | 1           | Either works with MicroPython            |
| 5V power supply                           | 1           | Sized for ~500 LEDs (10A recommended)    |
| 3-pin JST connectors                      | 8 pairs     | Data + power connections between letters |
| 22 AWG silicone wire                      | As needed   | Power distribution and data lines        |


### LED Layout

Each letter is wired independently and daisy-chained via data line in order: 
**B - A - R - R - A - C - K - S**

| Letter | LEDs | Letter | LEDs |
|--------|------|--------|------|
| B | 74 | A | 58 |
| R | 67 | C | 53 |
| K | 57 | S | 64 |

Total: **498 LEDs** on GPIO 2.

### Wiring Diagram

The data line runs through all 8 letters in series. Each letter has its own power tap from a shared 5V bus to avoid voltage drop across the full strip length.

```
5V PSU ──┬── B ── A ── R ── R ── A ── C ── K ── S
         │   │    │    │    │    │    │    │    │
GND ─────┴───┴────┴────┴────┴────┴────┴────┴────┘
              │
GPIO 2 ──────┘ (data in)
```

## 3D Printing

Every letter is made up of four 3D printed components. All STL files are in the `3D MODELS/` directory.

### Components Per Letter

| Component | Description | Material Recommendation |
|-----------|-------------|------------------------|
| **Frame** | Outer shell of the letter shape | PLA/PETG, opaque color |
| **Insert** | Diffuser that sits inside the frame, spreads LED light evenly | White PLA or translucent PETG |
| **Backing** | Rear plate that holds the LED strip in place | PLA, any color |
| **Stand** | Connects adjacent letters for freestanding display | PLA, any color |

<!-- TODO: Add photo of exploded view or printed parts -->
![3D Printed Parts](placeholder-3d-parts.jpg)

### Print Files

```
3D MODELS/
  frames/          # Outer letter shells (B, A, R x2, C, K, S)
  inserts/         # Light diffuser inserts (v1 and v2 revisions)
  backings/        # Rear plates for LED mounting
  stands/          # Individual letter stands (v1)
  v2 stands/       # Inter-letter bridge stands (BA, AR, RR, RA, AC, CK, KS)
  electronics case/  # Enclosure for the microcontroller + wiring
```

### Print Settings

Recommended settings (adjust to your printer):

- **Frames**: 0.2mm layer height, 3 perimeters, 15% infill
- **Inserts**: 0.2mm layer height, 2 perimeters, 10% infill. Print in white or translucent material for best light diffusion
- **Backings**: 0.2mm layer height, 3 perimeters, 20% infill
- **Stands**: 0.3mm layer height, 3 perimeters, 20% infill (structural)

### Assembly

1. Print all components for each letter
2. Adhere WS2812B strip to the inside channel of each **backing**, following the letter shape
3. Solder data and power connections between letters using JST connectors
4. Press-fit each **insert** (diffuser) into its **frame** (superglue might be required depending on print quality)
5. Attach the **backing** with LEDs to the frame assembly with super glue
6. Glue **stands** together use super glue.
7. Mount the microcontroller in the **electronics case** and connect to the first letter (B)
8. Connect remaining letters in sequence using JST connectors 

## Software

Two firmware options are available. Both provide the same 14 effects and HTTP API.

### Option 1: MicroPython (Recommended)

Best for active development. Supports OTA code upload so you can push changes over WiFi.

**Supported boards:** Raspberry Pi Pico W, ESP32-C3 SuperMini

**Architecture:**
- `main.py` -- Thin bootloader that handles WiFi, OTA uploads, and crash recovery
- `app.py` -- All LED effects and the HTTP control server

**Setup:**
1. Flash MicroPython firmware from `MicroPython/Firmware/` onto your board
2. Copy `main.py`, `app.py`, and `config.json` to the device
3. Edit `config.json` with your WiFi credentials:
   ```json
   {
       "wifi_ssid": "YourNetwork",
       "wifi_password": "YourPassword"
   }
   ```
4. Power cycle the device. It will connect to WiFi and print its IP address

**OTA Upload:**

After initial setup, push code changes over WiFi without USB:

```bash
curl -X PUT --data-binary "@app.py" http://<device-ip>/upload
```

Or double-click `upload.bat` (edit the IP address inside first).

The device automatically backs up the previous `app.py` before overwriting. If a bad upload crashes on boot, the bootloader rolls back to the backup and enters recovery mode (red blinking LEDs) where you can upload a fix.

### Option 2: CircuitPython

The original firmware. Simpler single-file setup but no OTA upload -- you need USB access to change code.

**Supported boards:** Raspberry Pi Pico W only

**Setup:**
1. Flash CircuitPython 8.0.0-beta.1 UF2 for Pico W
2. Install the 8.x CircuitPython bundle (early 2023 release -- newer versions require `ssl` which isn't supported)
3. Copy `code.py` and `settings.toml` to the CIRCUITPY drive
4. Edit `settings.toml`:
   ```toml
   CIRCUITPY_WIFI_SSID = "YourNetwork"
   CIRCUITPY_WIFI_PASSWORD = "YourPassword"
   ```

**Extras over MicroPython:**
- Smooth crossfade transitions between effects
- Watchdog timer for auto-reboot on hang

## API

Once running, control the sign from any device on the same network:

```bash
# Switch to fire effect
curl http://<device-ip>/effect/7

# Set brightness to 50%
curl http://<device-ip>/brightness/50

# Turn off
curl http://<device-ip>/power/off

# Check current state
curl http://<device-ip>/status
```

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/effect/<1-14>` | GET | Set active effect |
| `/brightness/<0-100>` | GET | Set brightness percentage |
| `/speed/up` | GET | Increase animation speed (1.5x) |
| `/speed/down` | GET | Decrease animation speed (0.5x) |
| `/speed/reset` | GET | Reset speed to 100% |
| `/power/on` | GET | Turn on |
| `/power/off` | GET | Turn off |
| `/status` | GET | Get current state |
| `/upload` | PUT | Push new app.py (MicroPython only) |

### Effects List

| #   | Effect          | Description                                         |
| --- | --------------- | --------------------------------------------------- |
| 1   | Rainbow Sweep   | Smooth rainbow shifts left to right across the sign |
| 2   | Breathing Pulse | Entire sign fades in and out with shifting colors   |
| 3   | Letter Chase    | Letters illuminate one at a time in sequence        |
| 4   | Sparkle         | Random bright pixels flash on a warm background     |
| 5   | Color Wave      | An orange wave sweeps across the sign               |
| 6   | Ping Pong       | Each letter oscillates between two colors           |
| 7   | Fire            | Realistic flame simulation with heat-mapped flicker |
| 8   | Matrix Rain     | Green trails cycle through each letter's LEDs       |
| 9   | Solid Cycle     | Entire sign slowly rotates through the color wheel  |
| 10  | Comet           | A 60-pixel rainbow tail streaks across the sign     |
| 11  | Raindrop Ripple | Random concentric light ripples expand outward      |
| 12  | Heartbeat       | Red double-pulse beats from the center              |
| 13  | Marquee         | A warm spotlight sweeps back and forth              |
| 14  | Matrix Rain 2   | Rain falls down vertical strokes only               |

## Tools

### LED Mapper

`led_mapper.html` is a browser-based tool for mapping physical LED positions. Open it locally, click to place LEDs on a reference image of each letter, and export coordinates to `led_positions.json`. These coordinates drive position-aware effects like rainbow sweep, color wave, and comet.

## Project Structure

```
.
├── CircuitPython/
│   ├── code.py                    # Main application (656 lines)
│   ├── settings.toml              # WiFi + API config
│   └── Firmware/
├── MicroPython/
│   ├── main.py                    # Bootloader with OTA + recovery (190 lines)
│   ├── app.py                     # LED application (632 lines)
│   ├── config.json                # WiFi credentials
│   ├── upload.bat                 # One-click OTA deploy
│   └── Firmware/
├── 3D MODELS/
│   ├── frames/                    # Letter outer shells
│   ├── inserts/                   # Light diffuser inserts
│   ├── backings/                  # LED mounting plates
│   ├── stands/                    # Individual letter stands
│   ├── v2 stands/                 # Bridge stands (letter pairs)
│   └── electronics case/          # Controller enclosure
├── led_mapper.html                # Interactive LED position tool
├── led_positions.json             # LED X/Y coordinate data
└── README.md
```

## License

This project is open source. Feel free to build your own.
