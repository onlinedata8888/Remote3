# Remote2 37 - Customizable Game Pad

(36 ka multi-device fix isme included hai.)

## Game pad kyun nahi chal raha tha
1. Host (TV / PC) pairing ke time phone ka HID descriptor yaad rakh leta hai. Gamepad hissa baad me add hua tha, isliye purani
   pairing wale TV/PC ko gamepad dikhta hi nahi tha. Fix: dono taraf Forget karke dobara pair karna padta hai.
2. Ek hi descriptor me mouse + keyboard + gamepad tha, host (khaas kar Android TV) use keyboard/mouse samajh leta hai.
   Fix: naya "Pad only" profile (sirf game controller, gamepad subclass).
3. App me koi guide nahi tha ki pairing kaise karni hai. Fix: BT status par tap -> Profile, Forget, Discoverable, steps.

## Naya
- Pad only / Mouse+Keyboard+Pad profile (HidMouse.setProfile), pehle se paired device Forget (HidMouse.forget).
- Hat switch ko proper degrees (physical min/max) mile, L3/R3 buttons add.
- Customizable game pad: edit (pencil) -> button drag, corner handle se resize, size slider, label/bind change,
  delete, + Add (round/pill/d-pad/left stick/right stick), Presets (Xbox, Retro, Minimal), Reset. Layout save hota hai
  (landscape aur portrait alag).
- D-pad ab 8 direction, ungli slide karke direction badal sakte ho. Multi-touch (A+B ek saath) chalta hai.
- "TV keys" mode: Bluetooth ke bina, Google TV se jude remote connection se BUTTON_A/B/X/Y/L1/R1... aur d-pad keys bhejta hai
  (experimental: kuch TV/games in keys ko ignore karte hain; analog stick yahan d-pad ban jata hai).

## Files
HidMouse.java, app/assets/remote.html, tests/test_gamepad_custom.py (33 checks)
