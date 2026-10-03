# Remote2 39

(38 ke saare changes included.)

## Naya: Game pad WiFi se bhi
- Game pad me upar chip ab 3 mode cycle karta hai: **BT -> WiFi (PC) -> TV keys**.
- **WiFi (PC)**: phone -> PC par `pc/gamepad_server.py` (WebSocket). PC par virtual Xbox 360 controller banta hai
  (Windows: vgamepad/ViGEmBus, Linux: uinput). Auto-reconnect, keep-alive, optional PIN, do phone = Player 1/2.
- Manifest me `usesCleartextTraffic="true"` (WebView ko ws:// ke liye chahiye).
- WiFi se TV: TV par receiver nahi hota, isliye TV ke liye BT (asli pad) ya TV keys (Google TV remote, WiFi par) hi options hain.

## Files
app/assets/remote.html, patch/patch_apk.py, pc/*, patch/v39_*.py, tests/test_v39_wifi_gamepad.py
## Note
dist APK alag key se sign hai -> purani app uninstall karke install karo.
