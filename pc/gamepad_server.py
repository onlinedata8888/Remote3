#!/usr/bin/env python3
"""
Remote Gamepad - PC receiver (WiFi)
Phone app (Game pad -> WiFi mode) connects here over WebSocket and this script turns the phone into a
virtual Xbox 360 controller on your PC (works with PS1 emulators, racing games, anything that takes XInput).

  Windows : pip install vgamepad          (installs the ViGEmBus driver on first use; reboot if asked)
  Linux   : needs /dev/uinput access      (sudo python3 gamepad_server.py   or add a udev rule)
  Test    : python3 gamepad_server.py --dry-run     (prints what the phone sends, no controller created)

Run:  python gamepad_server.py            then type the shown IP into the app.
Opt:  --port 8765   --pin 1234 (app must send the same PIN)
Each phone that connects becomes its own controller (player 1, 2, ...).
"""
import argparse, base64, hashlib, os, socket, struct, sys, threading, time
from urllib.parse import urlparse, parse_qs

GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

# ----------------------------------------------------------------------------- phone -> pad state
# phone bit numbers (same as the app's BTNS table)
BIT_A, BIT_B, BIT_X, BIT_Y = 0, 1, 3, 4
BIT_L1, BIT_R1, BIT_L2, BIT_R2 = 6, 7, 8, 9
BIT_SELECT, BIT_START, BIT_HOME, BIT_L3, BIT_R3 = 10, 11, 12, 13, 14
# hat 0 = centre, 1=N 2=NE 3=E 4=SE 5=S 6=SW 7=W 8=NW
HAT_XY = {0: (0, 0), 1: (0, -1), 2: (1, -1), 3: (1, 0), 4: (1, 1), 5: (0, 1), 6: (-1, 1), 7: (-1, 0), 8: (-1, -1)}


def parse_state(line):
    """'P btn hat lx ly rx ry' -> (btn, hat, lx, ly, rx, ry) or None"""
    p = line.split()
    if len(p) != 7 or p[0] != "P":
        return None
    try:
        v = [int(x) for x in p[1:]]
    except ValueError:
        return None
    btn, hat = v[0] & 0xFFFF, v[1]
    if hat < 0 or hat > 8:
        hat = 0
    ax = [max(-127, min(127, a)) for a in v[2:]]
    return (btn, hat, ax[0], ax[1], ax[2], ax[3])


def axis16(a):          # -127..127 -> -32767..32767
    return int(max(-127, min(127, a)) * 32767 / 127)


# ----------------------------------------------------------------------------- backends
class DryPad:
    def __init__(self, n): self.n = n; print("[pad %d] created (dry-run)" % n)
    def update(self, s): print("[pad %d] btn=%s hat=%d L=(%d,%d) R=(%d,%d)" % ((self.n, format(s[0], '016b')) + s[1:]))
    def close(self): print("[pad %d] closed" % self.n)


class WinPad:
    """Virtual Xbox 360 pad through ViGEmBus (vgamepad)."""
    def __init__(self, n):
        import vgamepad as vg
        self.vg = vg
        self.pad = vg.VX360Gamepad()
        B = vg.XUSB_BUTTON
        self.map = {BIT_A: B.XUSB_GAMEPAD_A, BIT_B: B.XUSB_GAMEPAD_B, BIT_X: B.XUSB_GAMEPAD_X, BIT_Y: B.XUSB_GAMEPAD_Y,
                    BIT_L1: B.XUSB_GAMEPAD_LEFT_SHOULDER, BIT_R1: B.XUSB_GAMEPAD_RIGHT_SHOULDER,
                    BIT_SELECT: B.XUSB_GAMEPAD_BACK, BIT_START: B.XUSB_GAMEPAD_START, BIT_HOME: B.XUSB_GAMEPAD_GUIDE,
                    BIT_L3: B.XUSB_GAMEPAD_LEFT_THUMB, BIT_R3: B.XUSB_GAMEPAD_RIGHT_THUMB}
        self.dp = {(0, -1): B.XUSB_GAMEPAD_DPAD_UP, (0, 1): B.XUSB_GAMEPAD_DPAD_DOWN,
                   (-1, 0): B.XUSB_GAMEPAD_DPAD_LEFT, (1, 0): B.XUSB_GAMEPAD_DPAD_RIGHT}
        self.held = set()
        print("[pad %d] virtual Xbox 360 controller ready" % n)

    def update(self, s):
        btn, hat, lx, ly, rx, ry = s
        want = set(code for bit, code in self.map.items() if btn >> bit & 1)
        hx, hy = HAT_XY[hat]
        if hy < 0: want.add(self.dp[(0, -1)])
        if hy > 0: want.add(self.dp[(0, 1)])
        if hx < 0: want.add(self.dp[(-1, 0)])
        if hx > 0: want.add(self.dp[(1, 0)])
        for b in self.held - want: self.pad.release_button(button=b)
        for b in want - self.held: self.pad.press_button(button=b)
        self.held = want
        self.pad.left_trigger(value=255 if btn >> BIT_L2 & 1 else 0)
        self.pad.right_trigger(value=255 if btn >> BIT_R2 & 1 else 0)
        # phone: up = negative Y.  XInput: up = positive Y
        self.pad.left_joystick(x_value=axis16(lx), y_value=-axis16(ly))
        self.pad.right_joystick(x_value=axis16(rx), y_value=-axis16(ry))
        self.pad.update()

    def close(self):
        try: self.pad.reset(); self.pad.update()
        except Exception: pass
        del self.pad


class LinuxPad:
    """Virtual Xbox 360 pad through /dev/uinput (no extra packages)."""
    EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
    UI_SET_EVBIT, UI_SET_KEYBIT, UI_SET_ABSBIT = 0x40045564, 0x40045565, 0x40045567
    UI_DEV_CREATE, UI_DEV_DESTROY = 0x5501, 0x5502
    BTN = {BIT_A: 0x130, BIT_B: 0x131, BIT_X: 0x133, BIT_Y: 0x134, BIT_L1: 0x136, BIT_R1: 0x137,
           BIT_SELECT: 0x13a, BIT_START: 0x13b, BIT_HOME: 0x13c, BIT_L3: 0x13d, BIT_R3: 0x13e}
    ABS_X, ABS_Y, ABS_Z, ABS_RX, ABS_RY, ABS_RZ, ABS_HAT0X, ABS_HAT0Y = 0, 1, 2, 3, 4, 5, 16, 17

    def __init__(self, n):
        import fcntl
        self.fcntl = fcntl
        self.fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        f = self.fcntl.ioctl
        f(self.fd, self.UI_SET_EVBIT, self.EV_KEY); f(self.fd, self.UI_SET_EVBIT, self.EV_ABS); f(self.fd, self.UI_SET_EVBIT, self.EV_SYN)
        for code in self.BTN.values(): f(self.fd, self.UI_SET_KEYBIT, code)
        absinfo = {self.ABS_X: (-32768, 32767), self.ABS_Y: (-32768, 32767), self.ABS_RX: (-32768, 32767), self.ABS_RY: (-32768, 32767),
                   self.ABS_Z: (0, 255), self.ABS_RZ: (0, 255), self.ABS_HAT0X: (-1, 1), self.ABS_HAT0Y: (-1, 1)}
        amin, amax = [0] * 64, [0] * 64
        for a, (lo, hi) in absinfo.items():
            f(self.fd, self.UI_SET_ABSBIT, a); amin[a], amax[a] = lo, hi
        name = ("Xbox 360 Remote Gamepad %d" % n).encode()[:79].ljust(80, b"\0")
        # struct uinput_user_dev: name[80], input_id{bustype,vendor,product,version}, ff_effects_max, absmax[64], absmin[64], absfuzz[64], absflat[64]
        dev = name + struct.pack("<HHHHi", 0x03, 0x045e, 0x028e, 0x0110, 0)
        dev += struct.pack("<64i", *amax) + struct.pack("<64i", *amin) + struct.pack("<64i", *([0] * 64)) + struct.pack("<64i", *([0] * 64))
        os.write(self.fd, dev)
        f(self.fd, self.UI_DEV_CREATE)
        self.last = {}
        print("[pad %d] virtual Xbox 360 controller ready (uinput)" % n)

    def _ev(self, t, c, v):
        os.write(self.fd, struct.pack("llHHi", int(time.time()), 0, t, c, v))

    def _set(self, t, c, v):
        if self.last.get((t, c)) != v:
            self.last[(t, c)] = v
            self._ev(t, c, v)

    def update(self, s):
        btn, hat, lx, ly, rx, ry = s
        for bit, code in self.BTN.items(): self._set(self.EV_KEY, code, btn >> bit & 1)
        hx, hy = HAT_XY[hat]
        self._set(self.EV_ABS, self.ABS_HAT0X, hx); self._set(self.EV_ABS, self.ABS_HAT0Y, hy)
        self._set(self.EV_ABS, self.ABS_Z, 255 if btn >> BIT_L2 & 1 else 0)
        self._set(self.EV_ABS, self.ABS_RZ, 255 if btn >> BIT_R2 & 1 else 0)
        self._set(self.EV_ABS, self.ABS_X, axis16(lx)); self._set(self.EV_ABS, self.ABS_Y, axis16(ly))     # evdev: up = negative, same as phone
        self._set(self.EV_ABS, self.ABS_RX, axis16(rx)); self._set(self.EV_ABS, self.ABS_RY, axis16(ry))
        self._ev(self.EV_SYN, 0, 0)

    def close(self):
        try: self.fcntl.ioctl(self.fd, self.UI_DEV_DESTROY); os.close(self.fd)
        except Exception: pass


def make_backend(dry):
    if dry: return DryPad
    if sys.platform.startswith("win"):
        try:
            import vgamepad  # noqa
            return WinPad
        except ImportError:
            sys.exit("vgamepad nahi mila.  Pehle chalao:  pip install vgamepad   (phir ye script dobara)")
    if sys.platform.startswith("linux"):
        if not os.path.exists("/dev/uinput"):
            sys.exit("/dev/uinput nahi mila.  sudo modprobe uinput   phir sudo python3 gamepad_server.py")
        return LinuxPad
    sys.exit("Is OS par virtual controller support nahi hai (Windows ya Linux chahiye). --dry-run se sirf test ho sakta hai.")


# ----------------------------------------------------------------------------- tiny WebSocket server (stdlib)
def recv_exact(conn, n):
    b = b""
    while len(b) < n:
        c = conn.recv(n - len(b))
        if not c: raise ConnectionError("closed")
        b += c
    return b


def read_frame(conn):
    h = recv_exact(conn, 2)
    op, masked, ln = h[0] & 0x0F, h[1] & 0x80, h[1] & 0x7F
    if ln == 126: ln = struct.unpack(">H", recv_exact(conn, 2))[0]
    elif ln == 127: ln = struct.unpack(">Q", recv_exact(conn, 8))[0]
    if ln > 65536: raise ConnectionError("frame too big")
    mask = recv_exact(conn, 4) if masked else b""
    data = recv_exact(conn, ln) if ln else b""
    if masked: data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    return op, data


def send_frame(conn, op, data=b""):
    conn.sendall(bytes([0x80 | op, len(data)]) + data if len(data) < 126 else bytes([0x80 | op, 126]) + struct.pack(">H", len(data)) + data)


def handshake(conn, pin):
    buf = b""
    while b"\r\n\r\n" not in buf:
        c = conn.recv(4096)
        if not c or len(buf) > 16384: return False
        buf += c
    head = buf.split(b"\r\n\r\n")[0].decode("latin1").split("\r\n")
    parts = head[0].split()
    hdr = {}
    for l in head[1:]:
        if ":" in l: k, v = l.split(":", 1); hdr[k.strip().lower()] = v.strip()
    if len(parts) < 2 or "sec-websocket-key" not in hdr or "websocket" not in hdr.get("upgrade", "").lower():
        body = b"Remote Gamepad server is running. Use the phone app (Game pad -> WiFi).\n"
        conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % len(body) + body)
        return False
    q = parse_qs(urlparse(parts[1]).query)
    if pin and q.get("pin", [""])[0] != pin:
        conn.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        return False
    acc = base64.b64encode(hashlib.sha1(hdr["sec-websocket-key"].encode() + GUID).digest()).decode()
    conn.sendall(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: %s\r\n\r\n" % acc).encode())
    return True


class Server:
    def __init__(self, backend, pin):
        self.backend, self.pin = backend, pin
        self.slots, self.lock = set(), threading.Lock()

    def client(self, conn, addr):
        pad, n = None, 0
        try:
            conn.settimeout(15)
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            if not handshake(conn, self.pin): return
            with self.lock:
                n = next(i for i in range(1, 100) if i not in self.slots); self.slots.add(n)
            print("phone connected: %s  -> player %d" % (addr[0], n))
            pad = self.backend(n)
            send_frame(conn, 1, ("OK %d" % n).encode())
            while True:
                op, data = read_frame(conn)
                if op == 8: break
                if op == 9: send_frame(conn, 10, data); continue
                if op in (1, 2):
                    s = parse_state(data.decode("ascii", "ignore"))
                    if s: pad.update(s)
        except (ConnectionError, socket.timeout, OSError):
            pass
        except Exception as e:
            print("error:", e)
        finally:
            if pad: pad.close()
            if n:
                with self.lock: self.slots.discard(n)
                print("phone disconnected: %s (player %d)" % (addr[0], n))
            try: conn.close()
            except Exception: pass

    def serve(self, port):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", port)); s.listen(8)
        while True:
            c, a = s.accept()
            threading.Thread(target=self.client, args=(c, a), daemon=True).start()


def lan_ips():
    ips = set()
    try:
        t = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); t.connect(("10.255.255.255", 1)); ips.add(t.getsockname()[0]); t.close()
    except Exception: pass
    try:
        for i in socket.gethostbyname_ex(socket.gethostname())[2]: ips.add(i)
    except Exception: pass
    return sorted(i for i in ips if not i.startswith("127."))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--pin", default="")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    be = make_backend(a.dry_run)
    print("=" * 56)
    print(" Remote Gamepad PC receiver")
    for ip in lan_ips(): print("   App me ye IP daalo:  %s   (port %d)" % (ip, a.port))
    if a.pin: print("   PIN:", a.pin)
    print(" Phone aur PC ek hi WiFi par hone chahiye. Band karne ke liye Ctrl+C.")
    print("=" * 56)
    try: Server(be, a.pin).serve(a.port)
    except KeyboardInterrupt: print("bye")


if __name__ == "__main__":
    main()
