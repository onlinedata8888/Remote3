# Remote Gamepad - PC receiver (WiFi)

Phone = Xbox 360 controller on your PC. PS1 emulators (DuckStation, ePSXe...), racing games, anything that takes XInput.

## Windows
1. Python 3 install karo (python.org), "Add to PATH" tick karo.
2. `run_windows.bat` double-click. Pehli baar `vgamepad` + ViGEmBus driver install hoga (agar kahe to reboot).
3. Console jo IP dikhaye (jaise 192.168.1.20) woh phone me daalo.

## Linux
`./run_linux.sh` (uinput ke liye sudo chahiye).

## Phone
Game pad kholo -> upar chip `BT` dabao jab tak `WiFi` na dikhe -> neeche status par tap -> PC IP daalo -> Connect.
Phone + PC same WiFi par. Windows Firewall puche to **Private network: Allow**.
Do phone connect karo to Player 1 / Player 2 alag controller banenge.

## Options
`python gamepad_server.py --port 8765 --pin 1234` (PIN lagao to app me bhi wahi PIN daalo)
`python gamepad_server.py --dry-run` (bina controller banaye sirf check: phone kya bhej raha hai)

## Mapping
A/B/X/Y, L1/R1, L2/R2 (trigger full), Select=Back, Start, Home=Guide, L3/R3, d-pad, left + right stick.
