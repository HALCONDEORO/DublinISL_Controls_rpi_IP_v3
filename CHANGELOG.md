# Changelog

All notable changes to this project should be documented in this file.

This project uses a simple versioning approach while it is still in early product development:

- Patch version: documentation, tests, install scripts, small fixes.
- Minor version: new features or significant refactors.
- Major version: breaking changes for installation, configuration or customer deployments.

## 3.0.3

### Changed

- Standardised copyright headers across all 82 Python source files: replaced verbose Spanish-language "uso privado exclusivo" notices with a concise two-line English header (closes #25).

## 3.0.2

### Added

- Added `docs/LEGAL_CHECKLIST.md` for pre-customer deployment legal review (closes #26).

## 3.0.1

### Added

- Added `requirements.txt`, `requirements-dev.txt` and `requirements-rpi.txt`.
- Added `requirements-atem.txt` for optional Blackmagic ATEM monitoring dependencies.
- Added README documentation aligned with the current implementation.
- Added Raspberry Pi dependency guidance.
- Added this changelog.
- Added `VERSION` file.
- Added example configuration files under `config.example/`.
- Added pytest configuration.
- Added GitHub Actions test workflow.

### Changed

- Kept `requirements.txt` focused on core runtime dependencies.
- Removed optional ATEM dependency from default runtime/dev install path so CI and tests do not depend on `PyATEMMax`.
- Kept `requirements-rpi.txt` minimal; install `requirements-atem.txt` separately only on systems using a real ATEM.

### Notes

- The current implementation is still hybrid: new `core/`, `application/` and `domain/` layers exist, but legacy Qt controllers are still used by `main_window.py`.
- Login fallback behaviour still needs hardening before wider customer deployment.
- Audit logging code exists but is currently disabled in normal login flow.

## 3.0.0

### Current baseline

- Two-camera VISCA-over-IP PTZ control.
- Touchscreen-oriented PyQt5 interface.
- Seat preset recall and speaker assignment.
- Chairman personal preset allocation.
- Optional ATEM monitoring.
- Simulation mode for VISCA cameras.
- Persistent data directory under `~/.config/dublinisl/` by default.
