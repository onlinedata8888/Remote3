#!/bin/bash
cd "$(dirname "$0")"
sudo modprobe uinput 2>/dev/null
sudo python3 gamepad_server.py "$@"
