# UI Icons: migrate emojis to SVG/PNG assets

## Decision

Production UI controls must not depend on emoji rendering.

Use project-controlled icon assets instead:

- SVG files as editable source assets.
- Generated PNG files for runtime use where this is simpler and more reliable.
- A central icon loader instead of scattered hard-coded image paths.
- Text labels beside all important action buttons.

This mainly affects controls such as settings, camera, presets, network, save, delete, warning, lock/licence, refresh, home and exit.

---

## Why this matters

Emoji rendering is not reliable enough for customer deployments on Raspberry Pi.

Common failure cases:

- Missing emoji fonts on Raspberry Pi OS.
- Different rendering between Raspberry Pi OS, Debian, Ubuntu and desktop development machines.
- Emoji variation selectors such as `⚙️` forcing colour emoji rendering instead of plain symbol rendering.
- Font fallback differences between terminal, Qt and other UI layers.
- Icons appearing as empty squares, missing glyphs or visually inconsistent symbols.

For a commercial installation, a broken settings icon looks like a software fault even if the feature still works.

---

## Recommended labels for GitHub work

Use these labels consistently when creating issues or PRs for this work.

| Label | Meaning |
|---|---|
| `ui` | Visual interface work |
| `assets` | Icons, images or static resources |
| `raspberry-pi` | Raspberry Pi-specific reliability issue |
| `production-hardening` | Needed before customer deployment |
| `documentation` | Docs-only change |
| `tests` | Automated test coverage |
| `priority: high` | Should be completed before customer deployment |
| `priority: medium` | Important, but not blocking the first deployment |
| `priority: low` | Useful polish or future cleanup |

If priority labels do not exist in the repository, use title prefixes until the labels are created:

```text
[P1] Replace emoji-only production buttons
[P2] Add icon asset registry and tests
[P3] Add optional Qt resource packaging
```

---

## Consolidated implementation plan

### P1 — Remove emoji dependency from production UI

**Suggested labels:** `ui`, `raspberry-pi`, `production-hardening`, `priority: high`

Goal: no critical UI control should rely on emoji rendering.

Actions:

- Search for emoji characters in the codebase.
- Replace emoji-only controls with readable text.
- Where useful, replace them with icon plus text.
- Keep text visible for critical actions.

Search command:

```bash
grep -R "⚙\|📷\|🔧\|🛠\|💾\|🗑\|⚠\|🔒\|🔓\|🔄\|🏠\|❌\|⬅" .
```

Preferred button style:

```text
[icon] Settings
[icon] Camera 1
[icon] Save Preset
[icon] Delete
```

Fallback rule:

> The app must remain usable with text labels even if icons are missing or disabled.

---

### P1 — Add official icon asset structure

**Suggested labels:** `ui`, `assets`, `production-hardening`, `priority: high`

Recommended structure:

```text
assets/
  icons/
    svg/
      settings.svg
      camera.svg
      preset.svg
      save.svg
      delete.svg
      edit.svg
      network.svg
      warning.svg
      lock.svg
      unlock.svg
      refresh.svg
      home.svg
      back.svg
      fullscreen.svg
      exit.svg
    png/
      settings_24.png
      settings_32.png
      settings_48.png
      camera_24.png
      camera_32.png
      camera_48.png
```

Rules:

- SVG files are the source of truth.
- PNG files are generated runtime assets.
- Commit both SVG and generated PNG files.
- Do not generate icons at runtime on customer Raspberry Pis.

---

### P1 — Define the first icon set

**Suggested labels:** `ui`, `assets`, `priority: high`

| UI function | Avoid | Asset name | Notes |
|---|---:|---|---|
| Settings | `⚙️` | `settings.svg` | Critical |
| Camera | `📷` | `camera.svg` | Critical |
| Preset | emoji/symbol | `preset.svg` | Critical |
| Save | `💾` | `save.svg` | Critical |
| Delete | `🗑️` | `delete.svg` | Critical; keep text |
| Warning | `⚠️` | `warning.svg` | Critical; never icon-only |
| Lock/licence | `🔒` | `lock.svg` | Important for future licensing |
| Unlock | `🔓` | `unlock.svg` | Important |
| Refresh/update | `🔄` | `refresh.svg` | Important |
| Home | `🏠` | `home.svg` | Useful |
| Back | `⬅️` | `back.svg` | Useful |
| Network | `🌐` | `network.svg` | Useful, but text should clarify |
| Fullscreen | emoji/symbol | `fullscreen.svg` | Optional |
| Exit | `❌` | `exit.svg` | Use with text |

---

### P1 — Centralise icon loading

**Suggested labels:** `ui`, `assets`, `production-hardening`, `priority: high`

Use one icon loader instead of loading image files directly from multiple UI files.

Example pattern:

```python
from pathlib import Path
from PyQt5.QtGui import QIcon

ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons" / "png"


def get_icon(name: str, size: int = 32) -> QIcon:
    path = ICON_DIR / f"{name}_{size}.png"
    if not path.exists():
        raise FileNotFoundError(f"Missing UI icon: {path}")
    return QIcon(str(path))
```

Usage:

```python
settings_button.setIcon(get_icon("settings", 32))
settings_button.setText("Settings")
```

Reason:

- One source for paths and sizes.
- Missing assets fail clearly during testing.
- Future changes to asset location do not require editing many UI files.

---

### P2 — Add an icon registry

**Suggested labels:** `ui`, `assets`, `priority: medium`

Avoid string literals spread across the UI.

Example:

```python
ICON_SETTINGS = "settings"
ICON_CAMERA = "camera"
ICON_SAVE = "save"
ICON_DELETE = "delete"
ICON_WARNING = "warning"
ICON_REFRESH = "refresh"
```

This reduces typo risk and makes refactors safer.

---

### P2 — Add automated asset tests

**Suggested labels:** `tests`, `assets`, `priority: medium`

Add a test that checks required icons exist in the sizes used by the UI.

Example:

```python
from pathlib import Path

ICON_DIR = Path("assets/icons/png")
REQUIRED_ICONS = [
    "settings",
    "camera",
    "preset",
    "save",
    "delete",
    "warning",
    "lock",
    "refresh",
]
REQUIRED_SIZES = [24, 32, 48]


def test_required_ui_icons_exist():
    missing = []
    for icon in REQUIRED_ICONS:
        for size in REQUIRED_SIZES:
            path = ICON_DIR / f"{icon}_{size}.png"
            if not path.exists():
                missing.append(str(path))

    assert not missing, "Missing UI icons: " + ", ".join(missing)
```

This prevents code from referencing assets that were not committed.

---

### P2 — Add a diagnostic no-icons mode

**Suggested labels:** `ui`, `raspberry-pi`, `production-hardening`, `priority: medium`

Add an environment flag for support diagnostics:

```bash
DUBLINISL_DISABLE_ICONS=1 python3 main.py
```

Expected behaviour:

- App loads without icon images.
- All important buttons still show readable text.
- Useful when diagnosing customer Raspberry Pi display or asset path issues.

---

### P2 — Add state-specific icons

**Suggested labels:** `ui`, `assets`, `priority: medium`

Useful states:

```text
camera_connected.svg
camera_disconnected.svg
camera_active.svg
camera_warning.svg
atem_connected.svg
atem_disconnected.svg
session_active.svg
session_inactive.svg
licence_valid.svg
licence_expired.svg
simulation_active.svg
```

This improves operator feedback, especially for cameras, ATEM, session status, simulation mode and future licensing.

Text must still be present for warnings and destructive states.

---

### P3 — Consider Qt resource packaging

**Suggested labels:** `ui`, `assets`, `packaging`, `priority: low`

Qt `.qrc` resources can package icons into application resources.

Potential benefits:

- Fewer file path errors.
- Cleaner packaging later.
- More predictable deployment if an installer is added.

This is useful, but not required for the first icon migration.

Priority: low until the project has a proper installer/package flow.

---

## Icon source recommendation

Use one clean open icon family and keep the style consistent.

Recommended options:

- Lucide Icons
- Feather Icons
- Heroicons
- Material Symbols

Preferred choice for this project: **Lucide Icons**.

Reason: they are simple, technical, readable on small screens and easy to recolour to match the MACD Adaptive visual style.

Before adding third-party icons, confirm the licence terms and keep attribution if required.

---

## Third-party asset documentation

Add a file when third-party icons are committed:

```text
docs/THIRD_PARTY_ASSETS.md
```

Suggested content:

```text
Icon pack: Lucide Icons
Usage: UI icons
Licence: ISC
Source: lucide.dev
Notes: SVG icons adapted only for size/colour consistency.
```

This keeps commercial usage cleaner and avoids future uncertainty about asset rights.

---

## Colour and branding guidance

Use project colours instead of platform emoji colours.

Recommended style:

- Lavender / purple for secondary controls.
- Cyan / blue accent for active or selected controls.
- White or light grey for dark backgrounds.
- Dark grey for light backgrounds.
- Red or amber only for destructive or warning states.

Avoid mixing icon packs. It makes the UI look unfinished.

---

## Official icon sizes

Use a small set of standard sizes.

| Size | Usage |
|---:|---|
| 24 px | Small inline controls |
| 32 px | Normal buttons |
| 48 px | Main controls / touchscreen-friendly buttons |
| 64 px | Large touch controls only if needed |

For the current Raspberry Pi touchscreen UI, prefer 32 px for normal buttons and 48 px for important touch controls.

---

## Optional SVG-to-PNG build script

If PNGs are generated automatically, keep generation outside the runtime path.

Example:

```python
from pathlib import Path
import cairosvg

SVG_DIR = Path("assets/icons/svg")
PNG_DIR = Path("assets/icons/png")
SIZES = [24, 32, 48, 64]

PNG_DIR.mkdir(parents=True, exist_ok=True)

for svg_file in SVG_DIR.glob("*.svg"):
    for size in SIZES:
        output = PNG_DIR / f"{svg_file.stem}_{size}.png"
        cairosvg.svg2png(
            url=str(svg_file),
            write_to=str(output),
            output_width=size,
            output_height=size,
        )
        print(f"Generated {output}")
```

Development dependency:

```bash
pip install cairosvg
```

On Raspberry Pi, Cairo may require system packages:

```bash
sudo apt install -y libcairo2
```

For deployed apps, commit generated PNGs and avoid requiring `cairosvg` on the customer device.

---

## Production UI rules

1. No production button should depend only on emoji rendering.
2. No critical action should be icon-only.
3. Text must remain visible for settings, save, delete, session control, camera selection, backup import/export and warnings.
4. Warning/error states must not rely only on colour.
5. Missing icons should fail clearly in development and degrade safely in production.
6. Use one icon family and one consistent visual style.

---

## Acceptance checklist

Before considering this work done:

- [ ] No production UI button depends on emoji rendering.
- [ ] `assets/icons/svg/` exists and contains the source icons.
- [ ] `assets/icons/png/` exists and contains generated sizes used by the UI.
- [ ] Icon loading is centralised.
- [ ] Important buttons still show readable text.
- [ ] A required-icons test exists.
- [ ] A third-party asset note exists if external icons are committed.
- [ ] Missing icons fail loudly during development/testing.
- [ ] The UI has been tested on the target Raspberry Pi image.
- [ ] The UI has been checked on the production screen resolution.

---

## Recommended execution order

1. **P1:** Replace emoji-only labels with text labels.
2. **P1:** Add `assets/icons/svg/` and `assets/icons/png/`.
3. **P1:** Add the first 8-10 production icons.
4. **P1:** Add a central icon loader.
5. **P2:** Add icon registry constants.
6. **P2:** Add tests for required icon assets.
7. **P2:** Add diagnostic no-icons mode.
8. **P2:** Add state-specific icons.
9. **P3:** Consider Qt `.qrc` packaging when installer work starts.

This keeps the migration small, testable and safer for customer deployments.
