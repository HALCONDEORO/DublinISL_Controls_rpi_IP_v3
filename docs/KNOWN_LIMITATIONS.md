# Known Limitations

This document lists current product and code limitations. It should be updated when the related issues are resolved.

## Architecture

- The codebase is still in a hybrid architecture. The newer `core/`, `application/`, `domain/` and `adapters/` layers exist, but some workflows still go through legacy Qt controllers and direct UI callbacks.
- The architecture migration is tracked across issues [#35](https://github.com/HALCONDEORO/DublinISL_Controls_rpi_IP_v3/issues/35) through [#44](https://github.com/HALCONDEORO/DublinISL_Controls_rpi_IP_v3/issues/44).

## ATEM Integration

- ATEM support is optional and partial. The app can monitor program changes, but full ATEM automation/control is not complete.
- ATEM behaviour still needs stronger safety modes, diagnostics, fake hardware tests and configurable input mapping before it should be treated as a complete customer automation feature.

## Simulation Mode

- Simulation mode covers VISCA camera behaviour. It is not a full standalone ATEM network simulator.
- Simulated/demo behaviour must remain clearly visible to operators so it is not confused with real hardware operation.

## VISCA And Camera Behaviour

- Some combined or unusual VISCA hardware responses may not be parsed correctly until [#8](https://github.com/HALCONDEORO/DublinISL_Controls_rpi_IP_v3/issues/8) is resolved.
- Camera command queuing, cancellation, STOP priority and latency handling still have open hardening work.

## Deployment And Operations

- Raspberry Pi installation, systemd setup, update/rollback and support runbook workflows are still being documented and scripted.
- Runtime/customer data separation is improved, but the broader deployment model still has open hardening work.

## Testing

- Existing tests are useful for core logic, but hardware-free smoke tests, ATEM fake tests, worker shutdown tests and backup/restore safety tests still need more coverage.
- Real camera and ATEM behaviour must still be validated on target hardware before production deployment.
