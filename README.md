# remote_r — Google TV / Android TV remote (real protocol)

Aapki `remote_r.apk` ka UI **bilkul same** hai (HTML markup + CSS byte-for-byte unchanged). Sirf peeche ka connection ab
asli **Android TV Remote Protocol v2** hai (wahi jo Google TV app use karti hai).

## Kya real hai
- TV discovery (3 tarike ek saath): Android NSD mDNS + apna raw mDNS query + Wi-Fi subnet scan (port 6466)
- **TV na mile to**: dropdown kholo -> upar ki "Searching for TVs…" line par tap -> TV ka IP daalo (10 sec me kuch na mile to ye dialog apne aap aata hai)
- Pairing: TLS port **6467**, 6-character code, SHA-256 secret (self-signed RSA-2048 client certificate)
- Remote: TLS port **6466**, protobuf messages, ping/keepalive, auto-reconnect
- D-pad / OK / Back / Home / Recent / Power / Mute / Volume / Channel / numbers / colour keys / media keys
- Touchpad (tap = OK, drag = arrows), scroll wheels = arrows, volume wheel + slider = volume keys
- On-screen keyboard (and phone keyboard) types into the TV (IME text; key-code fallback)
- App row launches apps by link (`APP_LINKS` in `app/assets/remote.html`)
- Speed: persistent TLS connection, TCP_NODELAY, key **down on touch / up on release**, batched volume steps

## Pehli baar use
1. Purani `remote_r` app **uninstall** karo (signing key alag hai), phir `dist/remote_r_googletv.apk` install karo.
2. Phone aur TV **same Wi-Fi** par. App khulte hi TV list me aa jayega (dropdown me select karo).
3. TV par 6-character code aayega -> app ka **keyboard** khulega -> code type karke **Done**.
4. Status dot green = connected. Dot par tap = reconnect / dobara pair.

## Jo nahi ho sakta (protocol limit)
- `Cast`, `Mirror` buttons: is protocol me nahi hain (toast dikhta hai).
- `P.Mode`, `S.Mode`, `Wi-Fi`, `Bluetooth`: TV ki **Settings** kholte hain (vendor-specific keys nahi hote).
- Mic button: TV par Search kholta hai; phone se voice streaming implement nahi hai.
- TV deep standby me ho to power-on ke liye TV ka network-standby/Wake-on-LAN on hona chahiye.

## Build
```
./build_apk.sh      # Linux/macOS/WSL, Java 17+, python3
```
Output: `dist/remote_r_googletv.apk`

### GitHub Actions (auto-build)
Push this repo to GitHub and `.github/workflows/build.yml` builds the APK for you on every push
(and on demand via the "Run workflow" button under the Actions tab). The finished
`remote_r_googletv.apk` shows up as a downloadable artifact on the workflow run — no local
Android setup needed. Push a tag like `v1.1` and it's also attached to a GitHub Release automatically.

## Recent fixes (this build)
- **Mic / voice command capturing nothing**: recording used to start (`AudioRecord.startRecording()`)
  *before* the app had even heard back from the TV. While waiting up to ~2.5 s for the TV's reply,
  the phone's mic buffer (only ~2 s deep) filled up and overflowed with silence/handshake noise —
  and that stale audio is what got sent first once streaming actually began, so the TV opened its
  mic UI but never heard real speech. Fixed: the mic now only starts capturing *after* the TV has
  confirmed it is listening, so the first byte sent is genuinely live audio from when you start
  talking. The "TV ne voice session nahi kholi" timeout was also extended (2.5s → 4s) since some
  TVs are slower to respond over Wi-Fi than the fake test TV.
- **Quick Settings (the 3-line button, top-left)**: already wired to long-press Home (which is how
  Google TV opens the settings panel that slides in from the right edge), but the hold was only
  650ms — extended to 900ms, comfortably above the ~500ms long-press threshold most TVs use, so it
  registers reliably instead of sometimes being read as a normal Home tap.

## Mouse page (new)
Touchpad ke **upar-beech me cursor icon** hai. Us par tap karo -> naya full-screen **Mouse page** khulta hai (Back arrow se wapas).

Purani RemoteNOW app ka `MousePanel` gesture engine port kiya gaya hai (constants original APK se: 4dp movement threshold,
click < 150 ms, hold > 500 ms, right edge = vertical scroll bar, bottom edge = horizontal scroll bar):

| Gesture | Kya hota hai |
|---|---|
| 1 ungli move | D-pad arrows (tez ungli = zyada steps, mouse acceleration jaisa) |
| Tap | OK |
| Ungli rok kar 0.5 s hold + move | Drag (OK dabaa reh kar arrows) |
| 2 ungli swipe | Scroll up / down / left / right |
| Pinch out / in | Volume up / down |
| Right edge par drag | Up / Down scroll |
| Bottom edge par drag | Left / Right scroll |
| Neeche ki row | Back, Home, Play/Pause, Vol -, Vol + |

**Limit (honest):** purani app **Hisense VIDAA** protocol (`REL_xxxx_yyyy` pointer packets) use karti thi, jisme TV par asli cursor
chalta tha. Google TV Remote v2 protocol me pointer message hota hi nahi (sirf key events), isliye yahan mouse movement
D-pad steps me convert hoti hai. TV par floating cursor tab tak nahi aa sakta jab tak TV khud koi mouse-toggle/pointer feature na de.

Files: `app/assets/remote.html` (UI + gestures), `patch/add_mouse_page.py` (ye patch dobara apply karne ke liye),
`tests/test_mouse_page.py` (Playwright gesture test, 30 checks).

## Structure
- `app/java/.../TvBridge.java` — JS<->native bridge, connection state machine, pairing flow
- `PairingSession.java`, `RemoteSession.java`, `Msgs.java`, `Pb.java`, `CertStore.java`, `Tls.java`, `Discovery.java`
- `app/assets/remote.html` — aapka UI (sirf `<script>` me TVNative wiring; `patch/patch_html.py` diff banata hai)
- `patch/patch_apk.py` — MainActivity hook + Wi-Fi permissions
- `tests/` — `faketv.py` (reference library ke protobuf schema par bana fake TV) + `TestMain.java`

## Testing status (honest)
Real Google TV par abhi test **nahi** hua. Protocol ko fake TV ke against verify kiya gaya
(reference `androidtvremote2` ke schema/algorithm se): pairing hash, handshake, ping, key down/up, volume, IME text, app launch.
Real TV par kuch button galat behave kare to `K` / `PAGE_KEYS` / `APP_LINKS` (remote.html ke top par) badalna kaafi hai.


## Remote 13 change log
- Preserved the original Cast gallery, Mirroring button, page-2 controls, mouse/remote page and all existing remote functionality.
- Added Settings button beside Power.
- Added Dark/Off-White theme selection with persistence.
- Added Default Remote Page: 1st Page (first install default) or 2nd Page.
- Build uses unique Android package ID `com.remote13.mirroring` so it installs separately from the old app.

## v11.18 — Bluetooth HID mouse (PC mode)
Touchpad ke cursor icon par tap -> Mouse page **PC mode** me khulta hai (top-right `PC | TV` switch se TV mode par ja sakte ho).
Phone khud ek Bluetooth mouse ban jata hai (`HidMouse.java`, Android 9+ `BluetoothHidDevice`), PC ka asli cursor chalta hai.

**Pehli baar pairing:** Mouse page -> `Devices` -> `Phone discoverable karo` -> PC ki Bluetooth settings me phone ko Add/Pair karo -> app me list se PC select karo.
Uske baad app next time last PC se auto-connect karti hai.

| Gesture (PC mode) | Kya hota hai |
|---|---|
| 1 ungli move | PC cursor (speed ke saath acceleration) |
| Tap / 2 ungli tap | Left click / Right click |
| Ungli rok kar hold + move | Drag (left button held) |
| 2 ungli swipe, right edge, bottom edge | Scroll (vertical / horizontal) |
| LEFT / MIDDLE / RIGHT buttons | Held while touched |

Files: `app/java/.../HidMouse.java`, `TvBridge.java` (`HidNative` bridge), `patch/patch_apk.py` (Bluetooth permissions), `tests/test_hid_pc_mode.py`.

## v11.20 — Mouse page ab sirf PC mode
TV option hata diya (TV ka touchpad 1st page par pehle se hai). Neeche ki row: Back, Home, Play/Pause, **Recent** (1st page Recent ka duplicate) aur **Remote icon** (tap = wapas 1st page). Vol -/Vol + hata diye.

## v11.23 — Mouse icon: 1 click = PC mouse pad, 2 clicks = Mouse page
Touchpad ke top-centre wale mouse icon par:
- **1 click** -> 1st page ka apna touchpad **PC mouse pad** ban jata hai (icon arrow se asli mouse me badal jata hai, pad par teal border). Phir se 1 click -> wapas normal TV touchpad.
  Pad par: 1 ungli = PC cursor, tap = left click, 2 ungli tap = right click, hold+move = drag, 2 ungli swipe = scroll.
  Pad ke dono grey wheels (left / bottom) PC mode me bhi normal trackpad wala TV scroll hi karte hain (v30). **Baaki sare 1st-page buttons** (arrows, OK, media, apps, volume slider, red volume wheel) pehle jaise TV keys hi bhejte hain.
- **2 clicks (jaldi-jaldi)** -> purana full-screen **Mouse page** (PC mode + Devices) khulta hai.
Test: `tests/test_pad_pc_mode.py`.

## YouTube panel (30_19)
Double-tap the YouTube shortcut on page 1 to open the YouTube control panel (single tap still launches YouTube). Buttons send real TV keys (play/pause, prev/next, -10s/+10s, CC, search, menu, d-pad, volume synced with the TV). Live timeline and tap-to-seek are NOT included: the Android TV Remote protocol does not report playback position.
\n## Keyboard v40 fix\nThe keyboard now uses whole-field TV IME synchronization for edits, has a working symbols page, hold-to-repeat backspace, explicit phone-keyboard Backspace/Enter handling, and preserves pairing-code input.\n