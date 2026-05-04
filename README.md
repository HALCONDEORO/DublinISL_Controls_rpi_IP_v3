# DublinISL Controls — PTZ Camera Control System

> Version 3.0 — current README aligned with the implementation in `main`.

DublinISL Controls is a Raspberry Pi application for operating two VISCA-over-IP PTZ cameras from a touchscreen interface. It is designed around a visual seating layout: the operator clicks a seat or platform position and the matching camera preset is recalled.

The current implementation is for a two-camera setup:

- **Camera 1 / Platform** — platform, chairman, left and right stage positions.
- **Camera 2 / Comments** — audience / seating area positions.

Audio and microphones are not part of this application.

---

## Current Implementation Status

### Implemented

- Two VISCA-over-IP camera control over TCP port `5678`.
- Pan, tilt, zoom, focus, backlight and exposure controls.
- Visual auditorium layout with seat buttons from `4` to `131` plus platform controls for presets `1`, `2` and `3`.
- Drag-and-drop speaker assignment to seats.
- Chairman personal preset allocation using reserved VISCA slots `10` to `89`.
- Session button for camera power-on, delayed initialisation and standby.
- Optional ATEM monitoring through `PyATEMMax`.
- Simulation mode for VISCA cameras.
- Persistent data stored outside the app folder in `~/.config/dublinisl/` by default.
- Backup export/import for JSON data files and plain-text config files.
- `AsyncEventBus`, `SystemState`, application services and domain modules exist and are used for part of the app.
- Worker supervisor monitors camera workers and the ATEM monitor thread.

### Partially Implemented / Important Limitations

See [Known Limitations](docs/KNOWN_LIMITATIONS.md) for the maintained list of current caveats and open hardening work.

- The architecture is currently **hybrid**. The newer `core/`, `application/`, `domain/` and `adapters/` layers exist, but `MainWindow` still uses legacy Qt controllers such as `ViscaController`, `SessionController`, `DialogsController` and `SeatNamesController`.
- ATEM support currently monitors program changes. It does **not** fully control or switch the ATEM. The implemented behaviour is: when ATEM program changes from input `3` to input `2`, the Comments camera is sent Home.
- Simulation mode starts virtual VISCA camera servers. ATEM simulation is internal/event-based, not a full standalone ATEM network simulator.
- Login audit code exists, but audit logging is currently commented out in `login_screen.py`. `audit_log.json` is not written during normal login flow unless that code is re-enabled.
- `password.enc` is encrypted using PBKDF2-derived key material. If `password.enc` is missing or cannot be decrypted, login is blocked until `python3 setup_password.py` creates a valid password file.
- JSON writes are atomic through `json_io.py`. Every runtime save also creates a `.bak` of the previous file before replacing it.
- Dependency files now exist, but there is still no packaged installer, `pyproject.toml` or pinned lock file.

---

## Hardware Requirements

| Component | Current expectation |
|-----------|---------------------|
| Computer | Raspberry Pi 4 recommended |
| Cameras | 2 × VISCA-over-IP PTZ cameras using TCP port `5678` |
| Video switcher | Blackmagic ATEM, optional, monitored via `PyATEMMax` |
| Display | 1920×1080 touchscreen recommended |
| Network | Raspberry Pi, cameras and ATEM on reachable LAN addresses |

Static IPs are strongly recommended for the two cameras and the ATEM.

---

## Software Requirements

| Software | Notes |
|----------|-------|
| Python | Python 3.8+ intended; test on the target Raspberry Pi image before production use |
| PyQt5 | Required for the GUI |
| PyQt5 QtSvg support | Required because the UI renders SVG icons |
| PyATEMMax | Optional; required only for real ATEM monitoring |
| git | Required for clone/update workflow |

Dependency files are split by purpose:

| File | Purpose |
|------|---------|
| `requirements.txt` | Core runtime dependencies for non-Raspberry Pi or generic pip installs |
| `requirements-dev.txt` | Development and test dependencies; includes `pytest` |
| `requirements-rpi.txt` | Raspberry Pi pip dependencies only; PyQt5/QtSvg should be installed with `apt` |
| `requirements-atem.txt` | Optional Blackmagic ATEM monitoring dependency (`PyATEMMax`) |

There is currently no pinned dependency lock file. Install dependencies explicitly on the target system and test before production use.

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/HALCONDEORO/DublinISL_Controls_rpi_IP_v3.git
cd DublinISL_Controls_rpi_IP_v3
```

### 2. Install dependencies

On Raspberry Pi OS, prefer system packages for PyQt5 and QtSvg:

```bash
sudo apt update
sudo apt install -y git python3-pyqt5 python3-pyqt5.qtsvg
pip3 install -r requirements-rpi.txt
```

For a non-Raspberry Pi development/runtime install:

```bash
pip3 install -r requirements.txt
```

For development and tests:

```bash
pip3 install -r requirements-dev.txt
pytest
```

On Windows, the repeatable verification command is:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

Use it after each change before shipping or committing. It runs the full pytest
suite with Qt in offscreen mode and test data isolated from the real
`~/.config/dublinisl/` directory. Add `-InstallDeps` the first time on a fresh
environment.

If using a real Blackmagic ATEM switcher:

```bash
pip3 install -r requirements-atem.txt
```

### 3. Create configuration files

The app reads these plain-text files from the project folder:

| File | Purpose | Example |
|------|---------|---------|
| `PTZ1IP.txt` | Platform camera IP | `172.16.1.11` |
| `PTZ2IP.txt` | Comments/audience camera IP | `172.16.1.12` |
| `Cam1ID.txt` | VISCA device ID for camera 1 | `81` |
| `Cam2ID.txt` | VISCA device ID for camera 2 | `82` |
| `ATEMIP.txt` | ATEM IP address | `192.168.1.240` |
| `Contact.txt` | Text shown on the Help button | `IT Support` |

Quick setup example:

```bash
echo "172.16.1.11"   > PTZ1IP.txt
echo "172.16.1.12"   > PTZ2IP.txt
echo "81"            > Cam1ID.txt
echo "82"            > Cam2ID.txt
echo "192.168.1.240" > ATEMIP.txt
echo "IT Support"    > Contact.txt
```

If a file is missing, `config.py` uses built-in fallback values. Check the files explicitly before production use instead of relying on defaults.

### 4. Set or change the login password

```bash
python3 setup_password.py
```

Current behaviour:

- If `password.txt` exists and `password.enc` does not exist, the script migrates `password.txt` into `password.enc` and deletes `password.txt`.
- If `password.enc` already exists, the current password is required before setting a new one.
- If `password.enc` is missing or unreadable during app login, access is blocked and the operator must run `python3 setup_password.py`.

For production, create or change the password before delivery and verify that `password.enc` exists.

### 5. Run the application

```bash
python3 main.py
```

Runtime window behaviour:

- Normal mode: opens full-screen.
- Simulation mode: opens as a normal window.

---

## Auto-start on Raspberry Pi

Recommended approach: use `systemd`.

Create a service file:

```bash
sudo nano /etc/systemd/system/dublinisl.service
```

Example:

```ini
[Unit]
Description=DublinISL Controls
After=graphical.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/DublinISL_Controls_rpi_IP_v3
ExecStart=/usr/bin/python3 /home/pi/DublinISL_Controls_rpi_IP_v3/main.py
Restart=on-failure
Environment=DISPLAY=:0

[Install]
WantedBy=graphical.target
```

Enable it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable dublinisl.service
sudo systemctl start dublinisl.service
```

Check logs:

```bash
journalctl -u dublinisl.service -f
```

`rc.local` can still be used on older systems, but `systemd` is clearer and easier to support.

---

## Usage Guide

### Login Screen

| Element | Current behaviour |
|---------|-------------------|
| Password field | Hidden text input |
| ACCESS | Checks the typed password |
| Enter key | Same as ACCESS |
| ? Help | Shows the contents of `Contact.txt` |
| Status message | Shows success, warning or lockout state |

Lockout schedule after failed attempts:

| Failed attempt | Lockout |
|----------------|---------|
| 1st | none |
| 2nd | none |
| 3rd | 10 seconds |
| 4th | 10 seconds |
| 5th | 30 seconds |
| 6th | 30 seconds |
| 7th | 60 seconds |
| 8th | 60 seconds |
| 9th+ | 3600 seconds |

Schedule bypass:

- If the weekly schedule says the current time is allowed, login is bypassed automatically.
- The schedule is stored in `schedule.json` under the persistent data directory.

Audit note:

- `LoginAudit` exists in code.
- Login audit calls are currently commented out, so normal login attempts are not written to `audit_log.json`.

---

### Splash Screen

After successful login, the splash screen runs startup checks and then opens the main interface. The app continues even if optional components are unavailable.

---

### Main Window

The main window is designed for 1920×1080.

| Area | Purpose |
|------|---------|
| Auditorium layout | Seat buttons and platform buttons |
| Right panel | Camera selection, joystick, zoom, focus, exposure and ATEM status |
| Names panel | Speaker list and seat assignment, visible in SET mode |

Platform controls:

| Control | Preset |
|---------|--------|
| Chairman | `1` |
| Left | `2` |
| Right | `3` |

Seat controls:

- Seats `4` to `131` are mapped to saved camera presets.
- Platform presets `1` to `3` always use Camera 1.
- Seat presets normally use Camera 2.

---

### CALL Mode and SET Mode

| Mode | Purpose |
|------|---------|
| CALL | Live operation. Clicking a button recalls its preset. |
| SET | Setup. Speaker names can be assigned to seats and chairman positions can be configured. |

The visual border and button styling change with the selected mode.

---

### Camera Control

| Control | Current behaviour |
|---------|-------------------|
| Platform / Comments selector | Chooses the active camera for manual control |
| Joystick | Sends pan/tilt commands while held; sends stop on release |
| Zoom slider | Sends absolute zoom percentage |
| Auto Focus | Enables continuous autofocus |
| One Push AF | Triggers one-shot autofocus |
| Manual Focus | Switches to manual focus |
| Darker / Brighter | Adjusts brightness or exposure compensation depending on AE mode |
| Backlight | Toggles backlight compensation state tracked per camera |

The app uses a camera worker thread and command queue for frequent VISCA commands.

---

### Session Control

The session button controls camera power state.

Start session:

1. Marks the session active.
2. Resets activity and VISCA speed watchdog state.
3. Sends Power ON to both cameras.
4. Waits 8 seconds for motor initialisation.
5. Sends Camera 1 to chairman preset `1`.
6. Sends Camera 2 Home.
7. Marks the UI as ON.

End session:

1. Asks for confirmation.
2. Cancels active preset polling.
3. Sends Standby to both cameras.
4. Marks the UI as OFF.

There is also an inactivity timer. If a session is active and there is no recorded camera/seat/zoom activity for 2 hours, both cameras are sent to standby.

---

### Chairman Personal Presets

Chairman personal presets are managed by `PresetService` and persisted in `chairman_presets.json`.

Current slot range:

- First personal chairman slot: `10`
- Last personal chairman slot: `89`
- Generic chairman fallback preset: `1`

If a speaker has no personal preset, the generic chairman preset is used.

---

### ATEM Monitoring

ATEM support is optional.

Current real-hardware behaviour:

- `ATEMMonitor` imports `PyATEMMax` only when needed.
- If `PyATEMMax` is missing, ATEM monitoring is disabled and the app continues.
- If the ATEM cannot be reached, the app continues.
- When program input changes from `3` to `2`, the app sends the Comments camera to Home.

Current limitation:

- The app monitors ATEM program state; it does not currently perform general ATEM switching control.

---

### Weekly Schedule

The weekly schedule controls password bypass.

Stored file:

```text
~/.config/dublinisl/schedule.json
```

Each day has:

- `enabled`: true/false
- `start`: `HH:MM`
- `end`: `HH:MM`

Overnight windows are supported. Example: `22:00` to `06:00`.

---

## Simulation Mode

Enable:

```bash
python3 sim_mode.py on
python3 main.py
```

Disable:

```bash
python3 sim_mode.py off
```

Show current state:

```bash
python3 sim_mode.py show
```

Current simulation behaviour:

- Creates `sim_ip_backup.json` in the app directory.
- Saves original values from `PTZ1IP.txt`, `PTZ2IP.txt` and `ATEMIP.txt`.
- Rewrites:
  - `PTZ1IP.txt` → `127.0.0.1`
  - `PTZ2IP.txt` → `127.0.0.2`
- Starts virtual VISCA servers for the two cameras.
- ATEM simulation uses `hardware_simulator.atem_event_queue` when `sim_ip_backup.json` exists.

Important:

- Simulation mode changes the `.txt` config files and restores them when turned off.
- If `sim_ip_backup.json` is deleted manually, restore the real IP files yourself.

---

## Backup and Data Storage

### Persistent data directory

Default:

```text
~/.config/dublinisl/
```

Override:

```bash
DUBLINISL_DATA_DIR=/mnt/usb/dublinisl python3 main.py
```

Data files:

| File | Purpose |
|------|---------|
| `seat_names.json` | Speaker names and seat assignments |
| `chairman_presets.json` | Chairman personal preset map |
| `schedule.json` | Weekly login bypass schedule |

On startup, legacy JSON files from the app directory are migrated into the persistent data directory if needed.

### App-directory config files

| File | Purpose |
|------|---------|
| `PTZ1IP.txt` | Camera 1 IP |
| `PTZ2IP.txt` | Camera 2 IP |
| `Cam1ID.txt` | Camera 1 VISCA ID |
| `Cam2ID.txt` | Camera 2 VISCA ID |
| `ATEMIP.txt` | ATEM IP |
| `Contact.txt` | Help/contact text |
| `password.enc` | Login password storage |
| `sim_ip_backup.json` | Simulation mode backup flag and original IP values |

### ZIP export/import

The backup system in `data_paths.py` supports:

- Exporting JSON data files from the persistent data directory.
- Exporting config `.txt` files from the app directory.
- Importing both groups back to their correct locations.
- Creating `.bak` files during import when replacing existing files.
- Creating `.bak` files on every normal runtime save (via `json_io.save_json`).

---

## Updating

Typical update workflow:

```bash
cd /home/pi/DublinISL_Controls_rpi_IP_v3
git pull origin main
python3 main.py
```

Persistent data in `~/.config/dublinisl/` should survive a `git pull`.

Before updating a production installation:

1. Export a ZIP backup from the app.
2. Copy the app directory `.txt` files.
3. Check whether new Python dependencies were added.
4. Test simulation mode before using live hardware.

---

## Network Behaviour

Production mode:

```text
Raspberry Pi  ->  PTZ Camera 1  TCP 5678
Raspberry Pi  ->  PTZ Camera 2  TCP 5678
Raspberry Pi  ->  ATEM          via PyATEMMax, optional
```

The production app normally makes outbound TCP connections to cameras and ATEM.

Simulation mode:

- The app starts local VISCA server sockets for simulated cameras.
- This is different from production mode and is intended for development/testing.

---

## Architecture

The target architecture is layered, but the current implementation is still mixed.

### Existing newer layers

```text
domain/          Data constants and domain models
core/            Event bus, state, controller, supervisor
application/     Camera, preset and session services
adapters/        Input adapters
ptz/visca/       VISCA commands, parser, manager, worker and protocol
```

### Existing legacy/Qt controllers still in use

```text
main_window.py
ptz/visca/controller.py
session_mixin.py
dialogs_mixin.py
seat_names_mixin.py
```

### Key modules

| Module | Current role |
|--------|--------------|
| `main.py` | App entry point; creates `QApplication`, virtual keyboard and `MainWindow` |
| `main_window.py` | Main UI composition and hybrid wiring |
| `ptz/visca/commands.py` | Pure VISCA command builders |
| `ptz/visca/parser.py` | Pure VISCA response parsers |
| `ptz/visca/worker.py` | Persistent TCP worker and command queue per camera |
| `ptz/visca/manager.py` | Camera workers and per-camera state/cache |
| `ptz/visca/protocol.py` | VISCA logic separated from direct Qt widget calls through callbacks |
| `ptz/visca/controller.py` | Qt-facing VISCA controller used by `MainWindow` |
| `atem_monitor.py` | ATEM monitor thread; optional PyATEMMax integration |
| `secret_manager.py` | Password encryption/decryption helper |
| `setup_password.py` | Password setup/change utility |
| `json_io.py` | Atomic JSON load/save helper |
| `data_paths.py` | Persistent data paths and ZIP backup/import |
| `hardware_simulator.py` | VISCA camera simulation and ATEM event queue |
| `sim_mode.py` | Toggles simulation mode by rewriting camera IP files |

---

## Known Technical Gaps Before Customer Deployment

These are current implementation gaps, not feature promises:

1. Enable audit logging safely, without storing attempted passwords.
2. Add a pinned dependency lock file or packaged installer for repeatable deployments.
3. Finish the architecture migration or document the legacy controllers as permanent.
4. Expand tests around real VISCA response formats, especially ACK + Completion in the same TCP packet.
5. Decide whether ATEM control is monitoring-only or should become full switcher control.
6. Add a tested installer/systemd setup script for Raspberry Pi deployments.

---

## Troubleshooting

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| App crashes at startup | Missing PyQt5 or QtSvg support | Install `python3-pyqt5 python3-pyqt5.qtsvg` |
| Camera indicator red | Camera unreachable or wrong IP | Check `PTZ1IP.txt` / `PTZ2IP.txt`, power and network |
| Joystick does nothing | Camera unreachable or session/camera state issue | Start session, check camera indicator, check logs |
| ATEM shows disconnected | PyATEMMax missing, wrong IP or ATEM offline | Install `pip3 install -r requirements-atem.txt`, check `ATEMIP.txt`, verify network |
| Login is blocked with password setup warning | `password.enc` missing/unreadable | Run `python3 setup_password.py` |
| Schedule bypass logs in automatically | Current time is inside enabled schedule | Edit weekly schedule or disable the day |
| Simulation still active | `sim_ip_backup.json` exists | Run `python3 sim_mode.py off` |
| Real camera IPs lost after simulation | Backup file removed or restore failed | Recreate `PTZ1IP.txt` and `PTZ2IP.txt` manually |
| Seat/chairman data missing | Wrong `DUBLINISL_DATA_DIR` or missing JSON | Check `~/.config/dublinisl/` and restore from ZIP backup |

---

## License

Copyright (c) 2026 Marco Antonio Tevar Asensio. Todos los derechos reservados.

Este software es propietario y de uso privado exclusivo. Queda prohibida su copia, distribución, modificación o uso sin autorización expresa y por escrito del autor. Consulta el fichero [LICENSE](LICENSE) para el texto completo.

---

## Contact

For technical support or installation assistance:

**Marco Tevar** — +353 085 236 8581  
**Carol Torres** — +353 89 975 2890
