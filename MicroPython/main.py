import machine
import network
import socket
import json
import time
import gc
import os

try:
    with open("config.json", "r") as f:
        config = json.load(f)
except (OSError, ValueError):
    config = {}

WIFI_SSID = config.get("wifi_ssid", "codu")
WIFI_PASS = config.get("wifi_password", "")

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    time.sleep(2)
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

wlan = connect_wifi()

def receive_upload(client, initial_data):
    try:
        client.settimeout(10.0)
        buf = initial_data
        while b"\r\n\r\n" not in buf:
            chunk = client.recv(256)
            if not chunk:
                return False
            buf += chunk
            if len(buf) > 2048:
                return False

        header_end = buf.index(b"\r\n\r\n") + 4
        body_start = buf[header_end:]
        headers = buf[:header_end].decode("utf-8")

        content_length = 0
        for line in headers.split("\r\n"):
            if line.lower().startswith("content-length:"):
                content_length = int(line.split(":")[1].strip())
                break

        if content_length == 0 or content_length > 40960:
            return False

        bytes_written = 0
        with open("_app_tmp.py", "w") as f:
            if body_start:
                f.write(body_start.decode("utf-8"))
                bytes_written += len(body_start)
            while bytes_written < content_length:
                to_read = min(512, content_length - bytes_written)
                chunk = client.recv(to_read)
                if not chunk:
                    break
                f.write(chunk.decode("utf-8"))
                bytes_written += len(chunk)

        if bytes_written < content_length:
            try:
                os.remove("_app_tmp.py")
            except OSError:
                pass
            return False

        try:
            os.remove("app_prev.py")
        except OSError:
            pass
        try:
            os.rename("app.py", "app_prev.py")
        except OSError:
            pass
        os.rename("_app_tmp.py", "app.py")
        return True
    except Exception as e:
        print("Upload error:", e)
        try:
            os.remove("_app_tmp.py")
        except OSError:
            pass
        return False

def _recovery_mode():
    print("RECOVERY MODE - app.py failed")
    import neopixel
    leds = neopixel.NeoPixel(machine.Pin(2), 10)

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", 80))
    srv.listen(5)
    srv.settimeout(1.0)

    blink = 0
    while True:
        blink += 1
        if blink % 2 == 0:
            leds.fill((50, 0, 0))
        else:
            leds.fill((0, 0, 0))
        leds.write()

        try:
            client, addr = srv.accept()
            client.settimeout(5.0)
            data = client.recv(512)
            if not data:
                client.close()
                continue
            line = data.decode("utf-8").split("\r\n")[0]
            parts = line.split(" ")
            method = parts[0] if len(parts) >= 2 else ""
            path = parts[1] if len(parts) >= 2 else ""

            if method == "PUT" and path == "/upload":
                if receive_upload(client, data):
                    resp = "HTTP/1.1 200 OK\r\nContent-Length: 22\r\nConnection: close\r\n\r\nUpload OK, rebooting..."
                    client.send(resp.encode("utf-8"))
                    client.close()
                    time.sleep(0.5)
                    machine.soft_reset()
                else:
                    resp = "HTTP/1.1 500 Error\r\nContent-Length: 13\r\nConnection: close\r\n\r\nUpload failed"
                    client.send(resp.encode("utf-8"))
                    client.close()
            elif path == "/status":
                ip = wlan.ifconfig()[0] if wlan and wlan.isconnected() else "none"
                body = f"RECOVERY MODE ip={ip}"
                resp = f"HTTP/1.1 200 OK\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n{body}"
                client.send(resp.encode("utf-8"))
                client.close()
            else:
                resp = "HTTP/1.1 404 Not Found\r\nContent-Length: 9\r\nConnection: close\r\n\r\nNot found"
                client.send(resp.encode("utf-8"))
                client.close()
        except OSError:
            pass
        time.sleep(0.5)

def boot_app():
    try:
        os.stat("_booting")
        print("Previous app.py crashed on boot, rolling back...")
        os.remove("_booting")
        try:
            os.remove("app.py")
            os.rename("app_prev.py", "app.py")
            print("Rolled back to app_prev.py")
        except OSError:
            print("No backup available")
            return False
    except OSError:
        pass

    with open("_booting", "w") as f:
        f.write("1")

    try:
        gc.collect()
        f = open("app.py")
        code = f.read()
        f.close()
        gc.collect()
        exec(code)
    except Exception as e:
        print("app.py error:", e)
        return False
    return True

print("Booting app.py...")
if not boot_app():
    _recovery_mode()
