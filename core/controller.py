#!/usr/bin/env python3
# core/controller.py — Orquestador central
#
# El Controller es el único componente que:
#   - Suscribe eventos del bus
#   - Llama a los servicios de aplicación
#   - Actualiza SystemState
#
# Ni la UI ni los dispositivos llaman entre sí: todo pasa por aquí.
# Sin Qt. Sin I/O directa.

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.events import AsyncEventBus, EventType, Event
from core.state import SystemState

if TYPE_CHECKING:
    from application.preset_service import PresetService
    from application.camera_service import CameraService
    from application.session_service import SessionService

logger = logging.getLogger(__name__)


class Controller:

    def __init__(
        self,
        state: SystemState,
        bus: AsyncEventBus,
        camera_svc: 'CameraService',
        preset_svc: 'PresetService',
        session_svc: 'SessionService',
    ) -> None:
        self._state   = state
        self._bus     = bus
        self._camera  = camera_svc
        self._presets = preset_svc
        self._session = session_svc
        self._register()

    def _register(self) -> None:
        self._bus.subscribe(EventType.SEAT_SELECTED,        self._on_seat_selected)
        self._bus.subscribe(EventType.CAMERA_MOVE,          self._on_camera_move)
        self._bus.subscribe(EventType.CAMERA_STOP,          self._on_camera_stop)
        self._bus.subscribe(EventType.CAMERA_ZOOM,          self._on_camera_zoom)
        self._bus.subscribe(EventType.CHAIRMAN_ASSIGNED,    self._on_chairman_assigned)
        self._bus.subscribe(EventType.PRESET_SAVE_REQUESTED, self._on_preset_save_requested)
        self._bus.subscribe(EventType.SESSION_START,        self._on_session_start)
        self._bus.subscribe(EventType.SESSION_END,          self._on_session_end)

    # ─────────────────────────────────────────────────────────────────────
    #  Handlers
    # ─────────────────────────────────────────────────────────────────────

    def _on_seat_selected(self, event: Event) -> None:
        name: str = event.payload.get("name", "")
        cam:  int = event.payload.get("camera", self._state.active_camera)
        seat: int = event.payload.get("seat_number", 0)

        preset = self._presets.get_preset_for_name(name) if name else seat

        if not preset:  # seat==0 o slot inválido
            logger.warning("seat_selected: preset inválido (seat=%d, name=%r)", seat, name)
            return

        ok = self._camera.recall_preset(cam, preset)
        if ok:
            self._state.camera(cam).active_preset = preset
            self._camera.invalidate_zoom(cam)

    def _on_camera_move(self, event: Event) -> None:
        cam  = event.payload["camera"]
        pan  = event.payload["pan_speed"]
        tilt = event.payload["tilt_speed"]
        self._camera.move(cam, pan, tilt)
        cam_state = self._state.camera(cam)
        cam_state.pan_speed  = pan
        cam_state.tilt_speed = tilt

    def _on_camera_stop(self, event: Event) -> None:
        cam = event.payload["camera"]
        self._camera.stop(cam)
        cam_state = self._state.camera(cam)
        cam_state.pan_speed  = 0
        cam_state.tilt_speed = 0

    def _on_camera_zoom(self, event: Event) -> None:
        cam   = event.payload["camera"]
        speed = event.payload["speed"]
        self._camera.zoom(cam, speed)

    def _on_chairman_assigned(self, event: Event) -> None:
        name: str = event.payload["name"]
        self._state.session.chairman_name = name
        self._session.set_chairman(name)

        preset = self._presets.get_preset_for_name(name)
        cam = 1  # Chairman siempre controla Cam1 (Platform)
        ok = self._camera.recall_preset(cam, preset)
        if ok:
            self._state.camera(cam).active_preset = preset
            self._camera.invalidate_zoom(cam)
        else:
            logger.warning("chairman_assigned: fallo al hacer recall preset %d", preset)

    def _on_preset_save_requested(self, event: Event) -> None:
        cam:  int = event.payload.get("camera", 1)
        name: str = event.payload["name"]

        slot, is_new = self._presets.assign_slot(name)
        if slot is None:
            logger.error("preset_save: rango de presets agotado para '%s'", name)
            return

        ok = self._camera.save_preset(cam, slot)
        if ok:
            logger.info("Preset %d guardado para '%s' en Cam%d", slot, name, cam)
            self._bus.emit(EventType.PRESET_SAVED, camera=cam, name=name, slot=slot)
        else:
            if is_new:
                self._presets.release_slot(name)
            logger.error("preset_save: fallo VISCA para '%s' slot=%d — %s",
                         name, slot, "slot liberado" if is_new else "slot existente conservado")

    def _on_session_start(self, event: Event) -> None:
        self._state.session.active = True
        self._session.start()

    def _on_session_end(self, event: Event) -> None:
        self._state.session.active = False
        self._session.end()
