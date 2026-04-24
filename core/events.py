#!/usr/bin/env python3
# core/events.py — EventBus y tipos de evento

from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class EventType(Enum):
    # ── Entrada de asientos ──────────────────────────────────
    SEAT_SELECTED       = auto()   # payload: name, camera, seat_number

    # ── Movimiento de cámara ─────────────────────────────────
    CAMERA_MOVE         = auto()   # payload: camera, pan_speed, tilt_speed
    CAMERA_STOP         = auto()   # payload: camera
    CAMERA_ZOOM         = auto()   # payload: camera, speed

    # ── Presets ──────────────────────────────────────────────
    CHAIRMAN_ASSIGNED   = auto()   # payload: name
    PRESET_SAVE_REQUESTED = auto() # payload: camera, name
    PRESET_SAVED        = auto()   # payload: camera, name, slot

    # ── Sesión ───────────────────────────────────────────────
    SESSION_START       = auto()
    SESSION_END         = auto()

    # ── Conexión ─────────────────────────────────────────────
    CONNECTION_CHANGED  = auto()   # payload: camera, connected


@dataclass
class Event:
    type: EventType
    payload: Dict[str, Any]


class EventBus:
    """Synchronous event bus (legacy). Prefer AsyncEventBus for new code."""

    def __init__(self) -> None:
        self._subscribers: Dict[EventType, List[Callable[[Event], None]]] = {}

    def subscribe(self, event_type: EventType,
                  handler: Callable[[Event], None]) -> None:
        self._subscribers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: EventType,
                    handler: Callable[[Event], None]) -> None:
        handlers = self._subscribers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    def emit(self, event_type: EventType, **payload: Any) -> None:
        event = Event(type=event_type, payload=payload)
        for handler in list(self._subscribers.get(event_type, [])):
            handler(event)


class _QtDispatchProxy:
    """
    Routes a handler call onto the Qt main thread using a queued signal.

    The QObject must be created on the main thread (i.e., during subscribe_qt,
    which is always called from main-thread widget constructors). Qt's queued
    connection then delivers the signal — and therefore the handler call — back
    to the main thread regardless of which thread calls dispatch().
    """

    def __init__(self, handler: Callable[[Event], None]) -> None:
        from PyQt5.QtCore import QObject, pyqtSignal, Qt

        class _Emitter(QObject):
            fired: Any = pyqtSignal(object)

            def __init__(self) -> None:
                super().__init__()
                self.fired.connect(handler, Qt.QueuedConnection)

        self._emitter = _Emitter()
        self._original = handler

    def dispatch(self, event: Event) -> None:
        self._emitter.fired.emit(event)


class AsyncEventBus:
    """
    Thread-safe asynchronous event bus.

    emit() enqueues the event and returns immediately (non-blocking for UI).
    A single daemon worker thread dequeues events and dispatches handlers.

    Lifecycle:
        bus = AsyncEventBus()
        bus.start()          # launch worker thread
        ...
        bus.stop()           # drain queue and join worker

    Subscribing Qt-touching handlers:
        bus.subscribe_qt(EventType.PRESET_SAVED, self._on_saved)
        # handler is invoked on the Qt main thread via a queued signal
    """

    def __init__(self) -> None:
        self._queue: queue.Queue[Optional[Event]] = queue.Queue()
        self._subscribers: Dict[EventType, List[Callable[[Event], None]]] = {}
        self._lock = threading.RLock()
        self._worker: Optional[threading.Thread] = None

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._worker = threading.Thread(
            target=self._run,
            name="AsyncEventBus-worker",
            daemon=True,
        )
        self._worker.start()

    def stop(self) -> None:
        self._queue.put(None)  # sentinel signals worker to exit
        if self._worker:
            self._worker.join(timeout=2.0)
            self._worker = None

    # ── Subscription ─────────────────────────────────────────────────────────

    def subscribe(self, event_type: EventType,
                  handler: Callable[[Event], None]) -> None:
        with self._lock:
            self._subscribers.setdefault(event_type, []).append(handler)

    def subscribe_qt(self, event_type: EventType,
                     handler: Callable[[Event], None]) -> None:
        """Register handler to be invoked on the Qt main thread."""
        proxy = _QtDispatchProxy(handler)

        def _dispatch(event: Event) -> None:
            proxy.dispatch(event)

        _dispatch._original = handler  # type: ignore[attr-defined]
        self.subscribe(event_type, _dispatch)

    def unsubscribe(self, event_type: EventType,
                    handler: Callable[[Event], None]) -> None:
        with self._lock:
            handlers = self._subscribers.get(event_type, [])
            to_remove = [
                h for h in handlers
                if h is handler or getattr(h, '_original', None) is handler
            ]
            for h in to_remove:
                handlers.remove(h)

    # ── Publishing ───────────────────────────────────────────────────────────

    def emit(self, event_type: EventType, **payload: Any) -> None:
        self._queue.put(Event(type=event_type, payload=payload))

    # ── Worker ───────────────────────────────────────────────────────────────

    def _run(self) -> None:
        while True:
            event = self._queue.get()
            if event is None:
                break
            with self._lock:
                handlers = list(self._subscribers.get(event.type, []))
            for handler in handlers:
                try:
                    handler(event)
                except Exception:
                    logger.exception(
                        "Unhandled exception in handler %r for %s",
                        handler, event.type,
                    )
