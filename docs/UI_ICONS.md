# UI Icons: migrate emojis to SVG/PNG assets

## Decision

Do not rely on emoji characters for production UI controls on Raspberry Pi.

Use project-controlled icon assets instead:

- Keep the editable source icons as SVG files.
- Generate PNG variants for sizes that the UI needs.
- Load the PNG assets from the application code where direct SVG rendering is not reliable or unnecessarily complex.
- Keep text labels beside important icons so operators are not forced to guess what a button does.

This is especially relevant for controls such as settings, camera, network, save, delete, warning, lock and refresh.

---

## Why this is needed

Emoji rendering is not reliable enough for customer deployments on Raspberry Pi.

Common failure cases:

- Missing emoji fonts on Raspberry Pi OS.
- Different rendering between Raspberry Pi OS, Debian, Ubuntu and desktop development machines.
- Emoji variation selectors such as `⚙️` forcing colour emoji rendering instead of a plain symbol.
- Font fallback differences between terminal, Qt and other UI layers.
- Icons appearing as empty squares, missing glyphs or visually inconsistent symbols.

For a commercial installation, a broken settings icon looks like a software fault even if the underlying feature still works.

---

## Recommended asset structure

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

The SVG files are the source of truth. The PNG files are generated assets used by the UI where needed.

---

## Initial icon set

| UI function | Avoid | Asset name |
|---|---:|---|
| Settings | `⚙️` | `settings.svg` |
| Camera | `📷` | `camera.svg` |
| Preset | emoji/symbol | `preset.svg` |
| Network | `🌐` | `network.svg` |
| Save | `💾` | `save.svg` |
| Delete | `🗑️` | `delete.svg` |
| Warning | `⚠️` | `warning.svg` |
| Lock/licence | `🔒` | `lock.svg` |
| Unlock | `🔓` | `unlock.svg` |
| Refresh/update | `🔄` | `refresh.svg` |
| Home | `🏠` | `home.svg` |
| Back | `⬅️` | `back.svg` |
| Fullscreen | emoji/symbol | `fullscreen.svg` |
| Exit | `❌` | `exit.svg` |

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

## Colour and branding guidance

Use project colours instead of platform emoji colours.

Recommended style:

- Lavender / purple for secondary controls.
- Cyan / blue accent for active or selected controls.
- White or light grey for dark backgrounds.
- Dark grey for light backgrounds.
- Red or amber only for destructive or warning states.

Avoid mixing multiple icon packs because it makes the UI look unfinished.

---

## Implementation approach

### Phase 1: remove emoji dependency

Search for emoji characters in the codebase:

```bash
grep -R "⚙\|📷\|🔧\|🛠\|💾\|🗑\|⚠\|🔒\|🔓\|🔄\|🏠\|❌" .
```

Replace emoji-only labels with either:

- text-only labels, or
- icon plus text labels.

For example:

```text
Settings
Camera 1
Save Preset
Delete
```

This gives an immediate fallback even before all icon assets are added.

---

### Phase 2: add asset folders

Create:

```text
assets/icons/svg/
assets/icons/png/
```

Commit the SVG source files and the generated PNG files.

For production Raspberry Pi deployments, do not depend on generating icons at runtime. Generate PNGs during development or during the build process and ship them with the application.

---

### Phase 3: centralise icon loading

Use one icon loader instead of loading image files directly from many UI files.

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

Then use the loader from UI code:

```python
settings_button.setIcon(get_icon("settings", 32))
settings_button.setText("Settings")
```

This makes missing assets obvious during testing and avoids scattered hard-coded paths.

---

### Phase 4: optional SVG-to-PNG build script

If PNGs are generated automatically, keep the generation script outside the runtime path.

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

For the deployed app, the simpler and safer route is to commit generated PNGs and avoid requiring `cairosvg` on the customer device.

---

## UI rule for production

Do not use icon-only buttons for critical actions.

Use icon plus text for actions such as:

- Settings
- Save Preset
- Delete
- Start Session
- End Session
- Camera 1 / Camera 2
- Import / Export Backup

Icon-only buttons are acceptable only for secondary controls where the meaning is obvious and a tooltip is present.

---

## Acceptance checklist

Before considering this done:

- [ ] No production UI button depends on emoji rendering.
- [ ] `assets/icons/svg/` exists and contains the source icons.
- [ ] `assets/icons/png/` exists and contains generated sizes used by the UI.
- [ ] Icon loading is centralised.
- [ ] Important buttons still show readable text.
- [ ] Missing icon files fail loudly during development/testing.
- [ ] The UI has been tested on the target Raspberry Pi image.
- [ ] The UI has been checked on the production screen resolution.

---

## Practical recommendation

For this project, the best route is:

1. Replace emoji labels with text labels immediately.
2. Add Lucide-style SVGs under `assets/icons/svg/`.
3. Generate and commit PNGs at 24, 32 and 48 px.
4. Load icons through a single helper module.
5. Keep text labels beside important controls.

This gives a more stable, professional and portable interface for customer deployments.
