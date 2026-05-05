# Milestones

This document defines the planned GitHub milestones for making the project installable, scalable and commercially supportable.

Roadmap index: #239

---

## M1 - Architecture & Config

**Goal:** make the codebase safe to grow before adding installer, editor, licensing or advanced integrations.

**Issues:**

- #242 Document architecture rules and forbidden imports
- #247 Add architecture import boundary tests
- #241 Create AppContext and bootstrap.py
- #243 Add typed Settings model and config.yaml loader
- #244 Add default config.yaml templates for Starter and Standard installs
- #245 Add CameraRegistry for camera lookup by id and role
- #248 Add startup smoke test without real hardware

**Exit criteria:**

- App still starts.
- Architecture rules are documented.
- Tests prevent obvious layer violations.
- Settings can load validated YAML config.
- Starter and Standard config templates validate.
- Cameras can be resolved by id and role.

---

## M2 - Installable Raspberry Pi Runtime

**Goal:** make the app installable, runnable and diagnosable on Raspberry Pi.

**Issues:**

- #250 Add macd CLI skeleton with status and version commands
- #251 Add Raspberry Pi systemd service template
- #252 Add first Raspberry Pi install.sh skeleton
- #254 Add DiagnosticsService and macd doctor basic checks
- #249 Add GitHub Actions CI for pytest

**Exit criteria:**

- `macd version` and `macd status` exist.
- systemd service template exists.
- first install script skeleton exists.
- `macd doctor` gives basic useful output.
- CI runs pytest without real cameras or ATEM.

---

## M3 - Safe Data, Backup & Layout Foundation

**Goal:** make customer data safe before adding the visual editor.

**Issues:**

- #218 Add persistent room_layout.json and LayoutService
- #226 Add layout schema versioning, migration and safe recovery
- #219 Decouple seat_id, visible label and VISCA preset
- #246 Add legacy .txt to config.yaml migration path
- #255 Add BackupService with manifest-based ZIP backup
- #256 Add safe restore workflow with pre-restore backup

**Exit criteria:**

- Layout data is no longer only hardcoded in Python.
- Layout can recover from missing/corrupt files.
- Seat identity, label and VISCA preset are separate.
- Legacy config migration path exists.
- Full customer backup can be created.
- Restore validates manifest and creates a pre-restore backup.

---

## M4 - Customer Layout Editor

**Goal:** let installers configure customer rooms without editing Python.

**Issues:**

- #227 Define preset ownership, camera routing and conflict rules for layouts
- #223 Include room layouts in backup, import and export workflows
- #220 Add admin-only EDIT_LAYOUT mode with drag-to-move seats
- #221 Add seat properties panel with layout validation

**Exit criteria:**

- Seat recall uses explicit camera role and preset.
- Layout import/export is safe.
- Admin can move seats visually.
- Admin can edit label, preset, visibility and lock state safely.
- Validation prevents broken layouts and warns on risky layouts.

---

## M5 - Commercial Readiness

**Goal:** prepare the product for demos, installations, support packages and commercial plans.

**Issues:**

- #236 Safe simulation and demo mode for sales, testing and training
- #237 ATEM integration scope, service layer and diagnostics
- #234 Licensing and commercial plan enforcement
- #225 Add guided seat preset calibration workflow
- #222 Add room layout generator, templates and preview workflow
- #228 Support multiple room profiles per client installation

**Exit criteria:**

- Demo mode does not overwrite production config.
- ATEM scope is clear and diagnosable.
- Offline license model exists.
- Plans can limit features and camera counts.
- Seat calibration workflow is available.
- Templates/generator help faster installs.
- Multi-room is planned or implemented if needed.

---

# Recommended milestone order

1. M1 - Architecture & Config
2. M2 - Installable Raspberry Pi Runtime
3. M3 - Safe Data, Backup & Layout Foundation
4. M4 - Customer Layout Editor
5. M5 - Commercial Readiness

---

# Rule

Do not start a later milestone if the previous one is still unstable, unless the issue is explicitly independent and does not touch shared architecture, config, installer, data or layout foundations.
