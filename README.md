# MACD Adaptive Control

Formerly: **DublinISL Controls**

MACD Adaptive Control is a Raspberry Pi touchscreen application for controlling VISCA-over-IP PTZ cameras from a visual seating layout.

The app works today as a fixed-site control system. The next goal is to make it easier to install, configure, support and sell as a MACD Adaptive product.

> **Status:** working application, productisation in progress. Production installer is not complete yet; current setup is manual.

**First production target:** an offline-first Raspberry Pi installation with local touchscreen control, customer-specific configuration, backup/restore, diagnostics and optional support tooling.

---

## At a glance

| Item | Current status |
|---|---|
| Platform | Raspberry Pi touchscreen app |
| Camera protocol | VISCA-over-IP |
| Current camera model | 2 PTZ cameras |
| Interface | PyQt touchscreen UI |
| Configuration | Legacy `.txt` files |
| Installation | Manual clone/run today; installer planned |
| Diagnostics | Basic logs/checks today; `macd doctor` planned |
| Commercial status | Productisation in progress |
| Main roadmap | #239 |

---

## Quick start

### 1. Clone

```bash
git clone https://github.com/HALCONDEORO/DublinISL_Controls_rpi_IP_v3.git
cd DublinISL_Controls_rpi_IP_v3
```

### 2. Install dependencies

On Raspberry Pi OS, install PyQt5/QtSvg with `apt`:

```bash
sudo apt update
sudo apt install -y git python3-pyqt5 python3-pyqt5.qtsvg
pip3 install -r requirements-rpi.txt
```

For generic development:

```bash
pip3 install -r requirements.txt
pip3 install -r requirements-dev.txt
```

Optional ATEM support:

```bash
pip3 install -r requirements-atem.txt
```

### 3. Configure cameras

Current production configuration uses legacy text files in the project folder:

| File | Purpose | Example |
|---|---|---|
| `PTZ1IP.txt` | Platform camera IP | `172.16.1.11` |
| `PTZ2IP.txt` | Comments camera IP | `172.16.1.12` |
| `Cam1ID.txt` | VISCA ID for camera 1 | `81` |
| `Cam2ID.txt` | VISCA ID for camera 2 | `82` |
| `ATEMIP.txt` | ATEM IP, optional | `192.168.1.240` |
| `Contact.txt` | Help/contact text | `IT Support` |

Example:

```bash
echo "172.16.1.11"   > PTZ1IP.txt
echo "172.16.1.12"   > PTZ2IP.txt
echo "81"            > Cam1ID.txt
echo "82"            > Cam2ID.txt
echo "192.168.1.240" > ATEMIP.txt
echo "IT Support"    > Contact.txt
```

`config.yaml` is planned, but legacy `.txt` files are still the current production configuration path.

### 4. Set login password

```bash
python3 setup_password.py
```

If `password.enc` is missing or invalid, login is blocked until a valid password file is created.

### 5. Run

```bash
python3 main.py
```

Normal mode opens full-screen. Simulation mode opens as a normal window.

---

## Intended use

Designed for venues that need simple local PTZ camera control from known room positions:

- community halls
- meeting rooms
- council chambers
- conference rooms
- training/demo environments
- venues with fixed seating and repeatable camera presets

```text
Operator touchscreen
        ↓
Raspberry Pi
        ↓
VISCA-over-IP PTZ cameras
        ↓
Optional ATEM monitoring / automation
```

---

## Scope

| Included today | Not included today |
|---|---|
| VISCA-over-IP PTZ control | Audio mixing |
| Two-camera workflow | Microphone control |
| PyQt touchscreen UI | Automatic speaker tracking |
| Seat/platform preset recall | Public SaaS access |
| CALL and SET modes | Cloud dashboard |
| Chairman personal presets | Online licensing |
| Session power-on/standby flow | Full ATEM switcher control |
| Optional ATEM monitoring | Production multi-room management |
| VISCA camera simulation |  |
| Persistent JSON runtime data |  |
| Atomic JSON writes with backups |  |
| Existing pytest coverage |  |

---

## Current vs planned

This repository is functional, but still transitioning into a configurable commercial product.

| Area | Current | Planned direction | Tracking |
|---|---|---|---|
| Product name | DublinISL Controls | MACD Adaptive Control | README |
| Architecture | Hybrid app + legacy Qt controllers | Cleaner services/layers | #229, #241, #242, #247 |
| Configuration | Legacy `.txt` files | Validated `config.yaml` | #230, #243, #244, #245, #246 |
| Cameras | Fixed two-camera model | Camera registry by id/role | #245 |
| Seating layout | Legacy fixed layout | Editable persistent room layout | #217, #218, #226, #219 |
| Installation | Manual clone/run | Installer + systemd + CLI | #231, #250, #251, #252 |
| Diagnostics | Partial logs/checks | `macd doctor` + support bundle | #232, #254 |
| Backup | Current JSON/config export | Manifest backup/restore | #233, #255, #256 |
| Simulation | Rewrites legacy config files | Safe demo profile | #236 |
| ATEM | Optional monitoring/automation | Defined service layer/scope | #237 |
| Licensing | Not implemented | Offline license + feature limits | #234 |
| Storage | JSON files | JSON first; SQLite only if needed | #239 |

Related docs:

- [Known limitations](docs/KNOWN_LIMITATIONS.md)
- [Privacy notes](docs/PRIVACY_NOTES.md)

---

## Requirements

### Hardware

| Component | Current expectation |
|---|---|
| Computer | Raspberry Pi 4 recommended |
| Cameras | VISCA-over-IP PTZ cameras using TCP port `5678` |
| Display | 1920×1080 touchscreen recommended |
| Network | Raspberry Pi and cameras on the same reachable LAN |
| ATEM | Optional Blackmagic ATEM switcher for monitoring/automation |

Static IPs are strongly recommended for cameras and ATEM devices.

### Software

| Software | Notes |
|---|---|
| Python | Python 3.8+ intended; test on target Raspberry Pi image before deployment |
| PyQt5 | Required for the GUI |
| PyQt5 QtSvg | Required for SVG icons |
| PyATEMMax | Optional; only needed for real ATEM monitoring |
| git | Required for clone/update workflow |

Dependency files:

| File | Purpose |
|---|---|
| `requirements.txt` | Generic runtime dependencies |
| `requirements-rpi.txt` | Raspberry Pi pip dependencies |
| `requirements-atem.txt` | Optional ATEM dependency |
| `requirements-dev.txt` | Development/test dependencies |

---

## Tests

```bash
pytest
```

On Windows:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

Planned hardening: architecture boundary tests, startup smoke tests and CI (#238, #247, #248, #249).

---

## Simulation mode

```bash
python3 sim_mode.py on
python3 main.py
python3 sim_mode.py off
python3 sim_mode.py show
```

Current simulation mode:

- starts simulated VISCA camera servers
- temporarily rewrites camera IP files
- stores backup state in `sim_ip_backup.json`
- uses internal ATEM event simulation when active

Important: simulation currently touches legacy config files. A safer profile-based demo mode is planned in #236.

---

## Raspberry Pi auto-start

The current recommended production direction is `systemd`.

Manual service example:

```ini
[Unit]
Description=MACD Adaptive Control
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

Manual commands:

```bash
sudo systemctl daemon-reload
sudo systemctl enable dublinisl.service
sudo systemctl start dublinisl.service
journalctl -u dublinisl.service -f
```

Planned production runtime: `macd` CLI, `macd-control.service`, `install.sh`, `macd doctor`, backup-before-update and safe restore.

---

## Data and backup

Default runtime data directory:

```text
~/.config/dublinisl/
```

Override:

```bash
DUBLINISL_DATA_DIR=/mnt/usb/dublinisl python3 main.py
```

Common runtime files:

| File | Purpose |
|---|---|
| `seat_names.json` | Speaker names and seat assignments |
| `chairman_presets.json` | Chairman personal preset map |
| `schedule.json` | Weekly login bypass schedule |

The project already has JSON safety helpers and backup/import support for current data. A fuller manifest-based backup/restore workflow is planned in #233, #255 and #256.

---

## Main operation concepts

| Concept | Meaning |
|---|---|
| CALL mode | Live mode. Pressing a seat/platform button recalls its preset. |
| SET mode | Setup mode for assigning speaker names to seats and chairman positions. |
| Session control | Powers cameras on/off and recalls initial positions. |
| Chairman presets | Personal chairman presets stored in `chairman_presets.json`. |
| ATEM monitoring | Optional ATEM state monitoring; full switcher control is not currently implemented. |

Chairman personal preset range:

- first personal slot: `10`
- last personal slot: `89`
- generic fallback preset: `1`

---

## Architecture

Target direction:

```text
domain/          Pure domain models and constants
application/     Product/application services
core/            Event bus, controller, state, supervisor
adapters/        Hardware/storage/simulation adapters
ptz/visca/       VISCA protocol, commands, parser, manager and worker
ui/              PyQt interface, planned separation
runtime/         Planned CLI, installer, systemd and diagnostics
```

Current reality:

- newer layers already exist and are partly used
- `MainWindow` still performs too much wiring
- legacy Qt controllers are still active
- new business logic should move into application services, not legacy UI controllers

Architecture cleanup is tracked in #229, #241, #242 and #247.

---

## Development workflow

1. Create a focused `feature/*` branch.
2. Keep the change small enough to review.
3. Run `pytest` before committing.
4. Test simulation mode if the change touches startup, config, cameras or UI.
5. Open a pull request before merging to `main`.
6. Do not add new business logic to legacy Qt controllers.

Branch policy:

```text
main       = stable / deployable work
feature/*  = focused feature or refactor work
```

Recommended next development steps: #242, #247, #241 and #243.

---

## Security notes

- Do not commit customer passwords.
- Do not commit private license keys.
- Do not commit real customer secrets or private network details unless intentionally required and sanitised.
- Do not expose a customer Raspberry Pi directly to the public internet.
- Use VPN or controlled remote-support tooling for remote access.
- Back up customer config and data before updates.
- Treat logs and backup ZIPs as customer-sensitive data.

---

## Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| App crashes at startup | Missing PyQt5/QtSvg | Install `python3-pyqt5 python3-pyqt5.qtsvg` |
| Camera indicator red | Wrong IP, camera offline or network issue | Check `PTZ1IP.txt`, `PTZ2IP.txt`, power and LAN |
| Joystick does nothing | Camera/session state or connectivity issue | Start session and check camera indicator/logs |
| ATEM disconnected | PyATEMMax missing, wrong IP or ATEM offline | Install optional dependency and check `ATEMIP.txt` |
| Login blocked | Missing/invalid `password.enc` | Run `python3 setup_password.py` |
| Simulation still active | `sim_ip_backup.json` exists | Run `python3 sim_mode.py off` |
| Seat data missing | Wrong data directory or missing JSON | Check `~/.config/dublinisl/` or restore backup |

---

## License

Copyright (c) 2026 Marco Antonio Tevar Asensio. All rights reserved.

This is proprietary software. Copying, distribution, modification or use requires explicit written permission from the owner. See [LICENSE](LICENSE).

---

## Contact

Commercial support and installation details should be provided directly to authorised customers.