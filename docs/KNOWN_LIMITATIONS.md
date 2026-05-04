# Known Limitations

This document lists current product and code limitations. It will be updated as issues are resolved.

## Authentication

- Login audit logging is present in the code but not yet enabled safely in production.

## ATEM Integration

- ATEM support is monitoring-only (input switching detection). Full two-way control is not implemented.

## Simulation Mode

- Simulation mode covers VISCA camera behaviour only. ATEM simulation is not supported.

## JSON Backup Behaviour

- `.bak` file rotation for JSON config files is inconsistent until [#13](../../../issues/13) is resolved.

## Architecture

- The codebase is in a hybrid state during the migration from the legacy Qt-callback architecture to
  the new `AsyncEventBus` / service-layer architecture. Issues [#35–#44](../../../issues/35) track
  the remaining migration work.

## VISCA Parser

- Edge-case hardware responses from certain VISCA cameras may not be parsed correctly until
  [#8](../../../issues/8) is resolved.
