# DublinISL Controls — PTZ Camera Control System

> Version 3.0 — Tested on Raspberry Pi OS

A professional PTZ (Pan-Tilt-Zoom) camera control application built for a
131-seat parliamentary chamber. Designed to run on a Raspberry Pi 4, it
controls two IP PTZ cameras via VISCA over TCP/IP and integrates with a
BlackMagic ATEM video switcher for automated speaker tracking during live
sessions.

---

## Table of Contents

1. [Features](#features)
2. [Hardware Requirements](#hardware-requirements)
3. [Software Requirements](#software-requirements)
4. [Installation](#installation)
5. [Usage Guide](#usage-guide)
6. [Backup](#backup)
7. [Updating](#updating)
8. [Network Architecture](#network-architecture)
9. [File Reference](#file-reference)
10. [Security](#security)
11. [Troubleshooting](#troubleshooting)
12. [Contributing](#contributing)
13. [Project Structure](#project-structure)
14. [Architecture](#architecture)
15. [License](#license)
16. [Contact](#contact)

---

## Features

- **Dual PTZ camera control** — Pan, tilt, zoom, focus, and exposure via VISCA over TCP/IP (port 5678)
- **131-seat auditorium layout** — Visual seat grid with a per-seat saved camera preset
- **Speaker management** — Drag-and-drop name assignment to seats; chairman gets individual saved positions
- **ATEM switcher integration** — Monitors program output and auto-switches between camera inputs
- **Session management** — Coordinated camera power-on/off with motor initialisation sequence
- **Simulation mode** — In-process virtual VISCA servers and ATEM for development without hardware
- **Network discovery** — TCP/ARP scan to auto-detect camera IPs on the LAN
- **Operating schedule** — Per-weekday enable/disable with configurable start and end times
- **Touchscreen interface** — Optimised for 1920x1080 with virtual keyboard support
- **Machine-locked login** — PBKDF2-HMAC-SHA256 password encryption; audit log of all login attempts
- **Persistent data outside the app** — JSON data files stored in `~/.config/dublinisl/`; survive reinstalls and `git pull`
- **Automatic `.bak` copies** — Every save writes a `.bak` alongside the JSON for instant single-step rollback
- **ZIP export / import** — One-click full backup and restore (data + config `.txt` files) via Settings
- **Duplicate preset detection** — Warns before overwriting a chairman preset that is already assigned to another name
- **Atomic JSON writes** — All JSON saves use a temp-file + rename to prevent corruption on power loss

> Screenshots of the interface will be added in a future release.

---

## Hardware Requirements

| Component | Details |
|-----------|---------|
| **Computer** | Raspberry Pi 4 (4 GB RAM recommended) |
| **PTZ Cameras** | 2 x VISCA-over-IP cameras, TCP port **5678** |
| **Video Switcher** | BlackMagic ATEM (optional), TCP port **9910** |
| **Display** | 1920x1080 touchscreen (recommended); mouse + keyboard also supported |
| **Network** | All devices on the same LAN; static IPs strongly recommended |

> The application has been developed and tested on **Raspberry Pi OS**. It may
> work on other Linux distributions or Windows, but these are not officially
> supported.

---

## Software Requirements

| Software | Version | Notes |
|----------|---------|-------|
| Python | 3.8 or newer | Pre-installed on Raspberry Pi OS |
| PyQt5 | Latest | GUI framework |
| PyATEMMax | Latest | Optional — only needed for ATEM integration |

---

## Installation

### 1. Clone the repository

Open a terminal on your Raspberry Pi and run:

```bash
git clone https://github.com/halcondeoro/dublinisl_controls_rpi_ip_v3.git
cd dublinisl_controls_rpi_ip_v3
```

> If git is not installed: `sudo apt-get install git`

---

### 2. Install Python dependencies

```bash
pip3 install PyQt5
```

If you are using a BlackMagic ATEM switcher, also install:

```bash
pip3 install PyATEMMax
```

---

### 3. Create configuration files

Create the following plain-text files in the project folder with your actual
network values:

| File | Contents | Example |
|------|----------|---------|
| `PTZ1IP.txt` | IP address of the Platform camera | `172.16.1.11` |
| `PTZ2IP.txt` | IP address of the Comments camera | `172.16.1.12` |
| `Cam1ID.txt` | VISCA device ID for Camera 1 (hex) | `81` |
| `Cam2ID.txt` | VISCA device ID for Camera 2 (hex) | `82` |
| `ATEMIP.txt` | IP address of the BlackMagic ATEM | `192.168.1.240` |
| `Contact.txt` | Support contact shown on the Help screen | `IT Support: ext. 123` |

Quick creation:

```bash
echo "172.16.1.11"   > PTZ1IP.txt
echo "172.16.1.12"   > PTZ2IP.txt
echo "81"            > Cam1ID.txt
echo "82"            > Cam2ID.txt
echo "192.168.1.240" > ATEMIP.txt
echo "IT Support"    > Contact.txt
```

> All values can also be edited from inside the app via **Settings -> Camera Configuration**.

---

### 4. Set the login password

```bash
python3 setup_password.py
```

Enter and confirm your new password. The file `password.enc` is written and
locked to this machine.

> **Default password (first run):** `dublin2024` — change it immediately.

---

### 5. Run the application

```bash
python3 main.py
```

**Auto-start on boot (Raspberry Pi):**

Add to `/etc/rc.local` before `exit 0`:

```bash
su pi -c "cd /home/pi/dublinisl_controls_rpi_ip_v3 && python3 main.py &"
```

---

## Usage Guide

### Login Screen

```
+----------------------------------------+
|          DublinISL Controls            |
|           Restricted Access            |
|                                        |
|  Password: [________________________]  |
|           [    ACCESS    ]             |
|                                        |
|  Enter password                [? Help]|
+----------------------------------------+
```

| Element | Description |
|---------|-------------|
| **Password field** | Type the login password (input is hidden) |
| **ACCESS** | Submit — or press **Enter** |
| **? Help** | Displays the support contact from `Contact.txt` |
| **Status message** | Green on success; amber/red on failure |

Failed login lockout:

| Attempt | Lockout |
|---------|---------|
| 1st | No lockout |
| 2nd | 10 seconds |
| 3rd | 30 seconds |
| 4th | 60 seconds |
| 5th+ | 1 hour |

All attempts are recorded in `audit_log.json` with timestamps.

---

### Splash Screen — System Check

After login, 12 automated checks run before the main window opens:

```
+----------------------------------------+
|  [OK  12ms] Operating System           |
|  [OK  34ms] Camera 1 (Platform)        |
|  [OK  41ms] Camera 2 (Audience)        |
|  [--      ] ATEM Switcher              |
|  ...                                   |
|  [######################    ]  75%     |
|  Status: 9/12 tests passed             |
+----------------------------------------+
```

- **OK** — component reachable
- **--** — unavailable (app continues anyway)
- Press **Ctrl+D** for diagnostic detail

---

### Main Window Overview

```
+------------------------------+----------------------+
|                              |                      |
|   AUDITORIUM SEAT GRID       |   RIGHT CONTROL      |
|   (seats 1-131)              |   PANEL              |
|                              |                      |
|  [Left] [Chairman] [Right]   |  [SET]  [CALL]       |
|                              |  [Platform][Comments]|
|  [ 2][ 3][ 4][ 5][ 6]       |                      |
|  [ 7][ 8][ 9][10][11]        |  [  JOYSTICK  ] [Z]  |
|  ...                         |                      |
|                              |  [Auto Focus]        |
|  [Attendees]  (SET mode)     |  [Backlight OFF]     |
|                              |  [Settings]          |
+------------------------------+----------------------+
```

| Area | Description |
|------|-------------|
| **Seat grid** | One button per seat; click to recall that seat's camera preset |
| **Platform buttons** | Fixed positions: Left, Chairman, Right |
| **Attendees panel** | Floating panel (SET mode only) to manage speaker names |
| **Right panel** | Camera controls: mode toggle, camera select, joystick, zoom, focus, exposure |

---

### CALL Mode vs SET Mode

```
+----------+----------+
|   SET    |   CALL   |
+----------+----------+
 (green)    (red)
```

| Mode | Purpose |
|------|---------|
| **CALL** (red) | Live operation — click a seat to recall its preset and switch the ATEM input |
| **SET** (green) | Setup — drag speaker names to seats, save chairman positions |

> Use **SET mode** before the session to assign attendees. Switch to **CALL mode** for the live session.

---

### Controlling a Camera

**Select camera:** Use the Platform / Comments toggle buttons. A green LED
means reachable; red means offline.

**Joystick — pan and tilt:**
- Click and drag the knob toward any of 8 directions
- Camera moves while the knob is held; release to stop
- Glows teal in SET mode, burgundy in CALL mode

**Zoom:** Vertical slider to the right of the joystick.
- Drag up to zoom in, drag down to zoom out
- Current percentage shown below the slider

**Focus:**

| Button | Action |
|--------|--------|
| Auto Focus | Continuous auto-focus (default) |
| One Push AF | Single trigger, then holds |
| Manual Focus | Disables auto-focus |

**Exposure:**

| Button | Action |
|--------|--------|
| Darker | Decreases exposure (shows offset) |
| Backlight | Toggles backlight compensation (glows orange when ON) |
| Brighter | Increases exposure (shows offset) |

---

### Assigning Speakers to Seats

Done in **SET mode** before the session.

1. Click the **Attendees** button (person icon, top-right area)
2. In the floating panel, click and hold a name
3. Drag it onto the desired seat button
4. The button updates to show the speaker's first name

**Remove an assignment:**
- Drag the seat back to the Attendees panel, or
- Double-tap the seat and confirm the dialog

**Attendees panel buttons:**

| Button | Action |
|--------|--------|
| Pencil | Rename the speaker |
| Bin | Delete the speaker permanently |
| + Add | Add a new speaker |
| Bring All Back | Clear all seat assignments at once |

---

### Chairman Presets

Saves a personalised camera position per speaker for the chairman seat.

**Save:**
1. Drag a speaker's name onto the Chairman button
2. Position the camera with the joystick and zoom
3. Click **Save position** (green button below Chairman)

**Recall:** Click Chairman in CALL mode — camera moves to that speaker's saved
position automatically.

**Edit:** Click **Edit** (blue), re-position, then save again.

---

### Platform Buttons

| Button | Description |
|--------|-------------|
| **Left** | Left side of the stage (preset 2) |
| **Chairman** | Chairman desk — per-speaker presets (preset 1) |
| **Right** | Right side / comments area (preset 3) |

---

### Configuration Dialog

Open via **Settings** at the bottom of the right panel.

| Section | Description |
|---------|-------------|
| **Session** | Start or end the camera session (powers cameras on/off) |
| **Camera** | Edit IP / VISCA ID; green = reachable, red = offline |
| **Camera Discovery** | LAN scan — assign found IPs directly |
| **Access** | Change the login password |
| **Schedule** | Open the weekly schedule editor |
| **Simulation Mode** | Toggle real hardware vs virtual cameras |
| **Close Program** | Shut down the application |

---

### Weekly Schedule

Open via **Settings -> Weekly Schedule**.

- Check a day to enable it; set start and end times
- During scheduled hours the login screen requires no password
- Saved to `schedule.json`

---

### Simulation Mode

Runs the full application without physical hardware.

```bash
python3 sim_mode.py on
python3 main.py
```

Or from inside the app: **Settings -> Enable Simulation Mode**.

To restore real hardware:

```bash
python3 sim_mode.py off
```

Real IPs are backed up to `sim_ip_backup.json` while simulation is active.

---

## Backup

### Data files (survive reinstalls — stored in `~/.config/dublinisl/`)

| File | Contents |
|------|----------|
| `~/.config/dublinisl/seat_names.json` | Speaker names and seat assignments |
| `~/.config/dublinisl/chairman_presets.json` | Per-speaker camera presets |
| `~/.config/dublinisl/schedule.json` | Weekly operating schedule |

Alongside each JSON the app automatically keeps a `.bak` copy (e.g.
`chairman_presets.json.bak`). If a JSON file becomes corrupt, rename the
`.bak` to restore the previous save.

### Configuration files (in the app directory)

| File | Contents |
|------|----------|
| `PTZ1IP.txt`, `PTZ2IP.txt` | Camera IP addresses |
| `Cam1ID.txt`, `Cam2ID.txt` | VISCA device IDs |
| `ATEMIP.txt` | ATEM IP address |
| `Contact.txt` | Support contact shown in Help |

> `password.enc` is machine-locked and does not need to be backed up — it
> cannot be used on a different machine.

> The data directory can be overridden with the `DUBLINISL_DATA_DIR` environment
> variable, e.g. `DUBLINISL_DATA_DIR=/mnt/usb python3 main.py`.

### ZIP export / import (built-in)

The Settings dialog now includes **Export Backup** and **Import Backup** buttons.

- **Export Backup** — creates a single `.zip` that contains all three JSON data
  files *and* all six `.txt` configuration files. Save it to a USB drive or
  cloud storage.
- **Import Backup** — restores both groups from a previously exported `.zip` to
  their correct locations automatically.

This is the recommended way to migrate the application to a new Raspberry Pi.

### Recommended: automatic daily backup to USB drive

Create the script `/home/pi/backup_dublinisl.sh`:

```bash
#!/bin/bash
DEST="/media/pi/BACKUP/dublinisl_$(date +%Y%m%d)"
DATA_DIR="$HOME/.config/dublinisl"
APP_DIR="/home/pi/dublinisl_controls_rpi_ip_v3"
mkdir -p "$DEST"
cp "$DATA_DIR"/*.json "$DEST"/
cp "$APP_DIR"/*.txt   "$DEST"/
echo "Backup completed: $DEST"
```

Make it executable and schedule it daily at 02:00:

```bash
chmod +x /home/pi/backup_dublinisl.sh
crontab -e
# Add this line:
0 2 * * * /home/pi/backup_dublinisl.sh
```

---

## Updating

Updating pulls new code. Data files (`seat_names.json`, `chairman_presets.json`,
`schedule.json`) live in `~/.config/dublinisl/` and are never touched by git.
Configuration `.txt` files in the app directory are also not tracked by git.

```bash
cd /home/pi/dublinisl_controls_rpi_ip_v3
git pull origin main
```

If new Python dependencies were added:

```bash
pip3 install PyQt5
pip3 install PyATEMMax   # only if using ATEM
```

Then restart the application:

```bash
python3 main.py
```

> Always check the release notes before updating on a production system.

---

## Network Architecture

```
                        LAN
  +---------------+   TCP:5678   +----------+
  | Raspberry Pi  | -----------> | PTZ Cam1 |
  | (this app)    | -----------> | PTZ Cam2 |
  |               |   TCP:9910   +----------+
  |               | -----------> |   ATEM   |
  +---------------+              +----------+
```

- All connections are **outbound TCP** from the Raspberry Pi
- No incoming connections required — no firewall rules needed on the Pi
- Static IPs are strongly recommended for all devices

---

## File Reference

### Configuration files (plain text, created manually)

| File | Description |
|------|-------------|
| `PTZ1IP.txt` | Platform camera IP address |
| `PTZ2IP.txt` | Comments camera IP address |
| `Cam1ID.txt` | Camera 1 VISCA device ID (hex) |
| `Cam2ID.txt` | Camera 2 VISCA device ID (hex) |
| `ATEMIP.txt` | BlackMagic ATEM IP address |
| `Contact.txt` | Support contact shown in Help |

### Data files (JSON, auto-managed by the app)

Persistent data lives in `~/.config/dublinisl/` (overridable via `DUBLINISL_DATA_DIR`):

| File | Description |
|------|-------------|
| `~/.config/dublinisl/seat_names.json` | Speaker names and seat assignments |
| `~/.config/dublinisl/chairman_presets.json` | Per-speaker camera presets for the chairman seat |
| `~/.config/dublinisl/schedule.json` | Weekly operating schedule |

Each JSON file has an automatic `.bak` sibling (e.g. `seat_names.json.bak`).

Files in the app directory:

| File | Description |
|------|-------------|
| `password.enc` | Machine-locked encrypted login password |
| `audit_log.json` | Timestamped log of all login attempts |
| `sim_ip_backup.json` | Backup of real IPs while simulation mode is active |

---

## Security

- **Machine-locked encryption:** `password.enc` is encrypted with a key derived
  from the host machine's hardware identifier. It cannot be used on any other
  machine.
- **PBKDF2-HMAC-SHA256:** 200,000 iterations with a 16-byte random salt —
  resistant to brute-force attacks.
- **Progressive lockout:** Delays of 10s, 30s, 60s, and 1 hour after repeated
  failed login attempts.
- **Audit logging:** Every login attempt recorded in `audit_log.json` with
  timestamp and outcome.
- **No network listener:** The application makes only outbound TCP connections
  and does not open any listening port.

---

## Troubleshooting

| Symptom | Likely cause | Solution |
|---------|-------------|----------|
| Camera LED shows red | Camera unreachable | Check IP in `PTZ1IP.txt` / `PTZ2IP.txt`; verify camera is powered and on the same LAN |
| Wrong password on first run | Default password not yet set | Run `python3 setup_password.py` |
| `password.enc` rejected after moving to new Pi | Machine-lock mismatch | Run `python3 setup_password.py` on the new machine |
| ATEM shows "--" in splash | ATEM offline or wrong IP | Check `ATEMIP.txt`; the app works without ATEM |
| Joystick has no effect | Session not started | Settings -> **Start Session** |
| App crashes at startup | PyQt5 not installed | Run `pip3 install PyQt5` |
| Seat assignments lost after reboot | `seat_names.json` missing | Check `~/.config/dublinisl/`; rename `.bak` to `.json` or restore from ZIP backup |
| Chairman preset slot collision warning | Two speakers share a slot | Click OK to reassign automatically; or clear the old entry first in SET mode |
| JSON file corrupt / empty after power cut | Incomplete write | Rename `<file>.json.bak` → `<file>.json` in `~/.config/dublinisl/` |

---

## Contributing

This project does not have a formal contribution workflow, but suggestions and
ideas are welcome. If you find a bug or have an improvement in mind, open an
issue on GitHub:

**https://github.com/halcondeoro/dublinisl_controls_rpi_ip_v3/issues**

Please include:
- A clear description of the problem or idea
- Steps to reproduce (if reporting a bug)
- Your Raspberry Pi OS version and Python version

---

## Project Structure

The codebase follows a layered architecture. Each layer only depends on layers below it.

```
dublinisl_controls_rpi_ip_v3/
│
├── domain/                        # Pure data models — no Qt, no I/O
│   ├── camera.py                  # Camera dataclass (index, ip, cam_id, label)
│   ├── preset.py                  # Preset slot constants and platform preset IDs
│   └── seat.py                    # Seat dataclass (number, x, y, name)
│
├── core/                          # Framework-agnostic logic — no Qt, no I/O
│   ├── controller.py              # Central coordinator wiring services together
│   ├── events.py                  # EventBus + EventType enum (synchronous, thread-safe)
│   └── state.py                   # SystemState — single source of truth for runtime state
│
├── application/                   # Business logic services — no Qt
│   ├── camera_service.py          # Translates business intents into VISCA commands
│   ├── preset_service.py          # Owns the name→slot map for chairman personal presets
│   └── session_service.py         # Session lifecycle state (start/end, chairman tracking)
│
├── adapters/input/                # Qt input adapters — bridge UI events to EventBus
│   ├── joystick_adapter.py        # Converts joystick drag signals to CAMERA_MOVE events
│   └── seat_adapter.py            # Converts seat button clicks to SEAT_SELECTED events
│
├── devices/                       # Re-exports for hardware drivers (migration shim)
│   └── __init__.py                # Exports CameraWorker, CameraManager, ViscaProtocol
│
├── simulation/                    # Hardware simulation (no physical devices needed)
│   └── sim_worker.py              # Virtual VISCA + ATEM worker thread
│
├── tests/                         # Test package
│   └── __init__.py
│
├── main.py                        # Application entry point
├── main_window.py                 # Main window — composes all panels and controllers
├── config.py                      # IP/ID config loader; VISCA preset map (131 seats)
├── data_paths.py                  # Persistent data directory + ZIP export/import
├── json_io.py                     # Atomic JSON read/write with .bak copies
├── visca_protocol.py              # Pure VISCA command logic (no Qt dependency)
├── visca_mixin.py                 # Qt adapter layer for VISCA
├── camera_worker.py               # Daemon thread per camera; persistent TCP socket
├── camera_manager.py              # Centralised camera state (zoom, focus, backlight)
├── atem_monitor.py                # Background thread monitoring ATEM program output
├── right_panel.py                 # Right control panel (joystick, zoom, focus, exposure)
├── joystick.py                    # DigitalJoystick widget
├── names_panel.py                 # Attendees floating panel
├── widgets.py                     # GoButton, DragDropButton, SpecialDragButton
├── chairman_button.py             # ChairmanButton with per-speaker preset UI
├── chairman_presets.py            # Per-speaker preset storage (reads via data_paths)
├── seat_names_mixin.py            # Controller — speaker names and seat assignments
├── session_mixin.py               # Controller — camera power on/off sequence
├── login_screen.py                # Login UI with lockout
├── splash_screen.py               # Startup system-check screen
├── secret_manager.py              # PBKDF2 + machine-locked password encryption
├── setup_password.py              # CLI utility to set/reset the login password
├── config_dialog.py               # Settings modal dialog (includes ZIP export/import)
├── schedule_dialog.py             # Weekly schedule editor dialog
├── schedule_config.py             # Schedule read/write logic
├── camera_discovery.py            # TCP + ARP network scan for camera auto-detection
├── hardware_simulator.py          # Virtual VISCA servers + ATEM (simulation mode)
├── sim_mode.py                    # CLI to enable/disable simulation mode
├── virtual_keyboard.py            # Touchscreen virtual keyboard
└── test_persistence.py            # Comprehensive persistence and data-integrity tests
```

---

## Architecture

The application is structured in four layers. Each layer only imports from layers below it; no circular dependencies are permitted.

```
┌──────────────────────────────────────────┐
│  UI Layer (Qt)                           │
│  main_window, right_panel, login_screen, │
│  splash_screen, config_dialog, …         │
├──────────────────────────────────────────┤
│  Adapters  (adapters/input/)             │
│  joystick_adapter, seat_adapter          │
├──────────────────────────────────────────┤
│  Application  (application/)             │
│  CameraService, PresetService,           │
│  SessionService                          │
├──────────────────────────────────────────┤
│  Core  (core/)                           │
│  EventBus, SystemState, Controller       │
├──────────────────────────────────────────┤
│  Domain  (domain/)                       │
│  Camera, Preset, Seat  (data only)       │
└──────────────────────────────────────────┘
```

| Layer | Qt? | I/O? | Responsibility |
|-------|-----|------|----------------|
| **Domain** | No | No | Data shapes and constants |
| **Core** | No | No | State, events, orchestration |
| **Application** | No | JSON / TCP | Business logic services |
| **Adapters** | Yes | No | Bridge Qt signals → EventBus |
| **UI** | Yes | No | Render state, capture user input |

Hardware drivers (`camera_worker`, `camera_manager`, `visca_protocol`) are
re-exported via the `devices/` package during the ongoing migration.

---

## License

This project is licensed under the **GNU General Public License v3.0 (GPL-3.0)**.

You are free to use, study, modify, and distribute this software, provided that
any derivative work is also distributed under the same GPL-3.0 licence.

See the [LICENSE](LICENSE) file for the full licence text.

---

## Contact

For technical support or installation assistance:

**Marco Tevar** — +353 085 236 8581
**Carol Torres** — +353 89 975 2890
