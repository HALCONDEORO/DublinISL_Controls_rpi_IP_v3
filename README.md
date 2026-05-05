# DublinISL Controls — PTZ Camera Control System

DublinISL Controls is a Raspberry Pi touchscreen application for controlling VISCA-over-IP PTZ cameras from a visual seating layout.

The current system lets an operator select a platform position or audience seat and recall the matching camera preset. The project is now being evolved into an installable and scalable product under the MACD Adaptive roadmap.

---

## Current status

This repository is functional, but still in transition from a fixed-site application into a configurable commercial product.

### Works today

- VISCA-over-IP PTZ camera control over TCP port `5678`.
- Current two-camera model:
  - **Camera 1 / Platform** — chairman, left and right platform presets.
  - **Camera 2 / Comments** — audience / seating presets.
- Pan, tilt, zoom, focus, backlight and exposure controls.
- 1920×1080 touchscreen PyQt interface.
- Visual seating layout with seat buttons.
- CALL mode for live preset recall.
- SET mode for assigning speaker names to seats.
- Chairman personal preset allocation.
- Session start/end flow for camera power-on and standby.
- Optional Blackmagic ATEM monitoring through `PyATEMMax`.
- VISCA camera simulation mode.
- Persistent runtime data in `~/.config/dublinisl/` by default.
- Atomic JSON writes with backup files.
- Existing pytest coverage for several core behaviours.

### Still in progress

- Architecture is still hybrid: newer `core/`, `application/` and `domain/` layers exist, but legacy Qt controllers are still used.
- Seat positions are still based on the legacy fixed layout and are being migrated toward editable customer layouts.
- Configuration still uses legacy `.txt` files; planned direction is validated `config.yaml`.
- There is no packaged production installer yet.
- ATEM support is monitoring/automation-oriented, not full switcher control.
- Simulation mode is useful, but is being redesigned to avoid touching production configuration.
- Licensing, commercial plans and online support workflows are planned, not complete.

See also:

- [Known limitations](docs/KNOWN_LIMITATIONS.md)
- [Privacy notes](docs/PRIVACY_NOTES.md)
- Roadmap issue: #239

---

## Hardware requirements

| Component | Current expectation |
|---|---|
| Computer | Raspberry Pi 4 recommended |
| Cameras | VISCA-over-IP PTZ cameras using TCP port `5678` |
| Display | 1920×1080 touchscreen recommended |
| Network | Raspberry Pi and cameras on the same reachable LAN |
| ATEM | Optional Blackmagic ATEM switcher for monitoring/automation |

Static IPs are strongly recommended for cameras and ATEM devices.

---

## Software requirements

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

On Raspberry Pi OS, prefer system packages for PyQt5 and QtSvg:

```bash
sudo apt update
sudo apt install -y git python3-pyqt5 python3-pyqt5.qtsvg
```

---

## Quick start

### 1. Clone

```bash
git clone https://github.com/HALCONDEORO/DublinISL_Controls_rpi_IP_v3.git
cd DublinISL_Controls_rpi_IP_v3
```

### 2. Install dependencies

For Raspberry Pi:

```bash
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

### 3. Configure camera IPs

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

Planned direction: replace these legacy files with validated `config.yaml` as tracked in #230, #243, #244, #245 and #246.

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

## Tests

Run tests:

```bash
pytest
```

On Windows, the helper script is:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

The roadmap includes extra test hardening for architecture boundaries, startup smoke tests and CI: #238, #247, #248 and #249.

---

## Simulation mode

Enable:

```bash
python3 sim_mode.py on
python3 main.py
```

Disable:

```bash
python3 sim_mode.py off
```

Show state:

```bash
python3 sim_mode.py show
```

Current behaviour:

- Starts simulated VISCA camera servers.
- Temporarily rewrites camera IP files and stores a backup in `sim_ip_backup.json`.
- Uses internal ATEM event simulation when simulation is active.

Important: simulation currently touches legacy config files. A safer profile-based demo/simulation system is planned in #236.

---

## Raspberry Pi auto-start

The recommended production direction is `systemd`.

Manual example:

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

Enable manually:

```bash
sudo systemctl daemon-reload
sudo systemctl enable dublinisl.service
sudo systemctl start dublinisl.service
journalctl -u dublinisl.service -f
```

Planned direction:

- `macd` CLI command
- `macd-control.service`
- `install.sh`
- `macd doctor`
- backup before update
- safe restore workflow

Tracked in #231, #250, #251, #252, #232, #254, #233, #255 and #256.

---

## Persistent data and backup

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

The project already has JSON safety helpers and backup/import support for current data. A fuller manifest-based customer backup/restore workflow is planned in #233, #255 and #256.

---

## Main operation concepts

### CALL mode

Live operation mode. Pressing a seat/platform button recalls its configured camera preset.

### SET mode

Setup mode. Used for assigning speaker names to seats and chairman positions.

### Session control

The session button powers cameras on, waits for motor initialisation, recalls initial positions and later sends cameras to standby. There is also an inactivity timer that can power down cameras after long inactivity.

### Chairman presets

Chairman personal presets are managed by `PresetService` and stored in `chairman_presets.json`.

Current personal preset range:

- First personal slot: `10`
- Last personal slot: `89`
- Generic fallback preset: `1`

### ATEM monitoring

ATEM support is optional. If `PyATEMMax` is unavailable or the ATEM cannot be reached, the app should continue running. Current behaviour is limited; the future ATEM scope is tracked in #237.

---

## Architecture

The target architecture is layered:

```text
domain/          Pure domain models and constants
application/     Product/application services
core/            Event bus, controller, state, supervisor
adapters/        Hardware/storage/simulation adapters
ptz/visca/       VISCA protocol, commands, parser, manager and worker
ui/              PyQt interface, planned separation
runtime/         Planned CLI, installer, systemd and diagnostics
```

Current status:

- Some newer layers already exist and are used.
- `MainWindow` still performs too much wiring.
- Legacy Qt controllers are still active during migration.
- New business logic should move into application services, not legacy UI controllers.

Architecture cleanup is tracked in #229, #241, #242 and #247.

---

## Product roadmap

The active roadmap is tracked in #239.

Execution order:

1. Architecture and configuration foundation.
2. Release safety and smoke tests.
3. Raspberry Pi installer/runtime.
4. Diagnostics and backup/restore.
5. Persistent editable room layout.
6. Safe demo/simulation mode.
7. ATEM integration scope.
8. Offline licensing and commercial plan enforcement.

Important product decisions:

- Config and room layout are separate.
- Do not create another camera controller.
- Do not start the visual layout editor before `LayoutService`, schema migration and seat ID/preset separation are safe.
- JSON remains the first storage target; SQLite is not required for the MVP.
- Online licensing and cloud dashboard are not first-release requirements.

---

## Known gaps before commercial deployment

These are implementation gaps, not promises:

1. Packaged installer and `systemd` workflow.
2. Validated `config.yaml` configuration.
3. Architecture migration away from legacy UI controllers.
4. Editable/persistent room layout.
5. Safer demo/simulation profile that does not rewrite production config.
6. Full customer backup and safe restore workflow.
7. Clear ATEM commercial scope.
8. Offline license validation and feature gating.
9. More hardware-free smoke tests and CI.

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