#!/usr/bin/env python3
# core/supervisor.py — Worker supervisor: detect and restart failed background threads

from __future__ import annotations

import logging
import threading
from typing import Callable

logger = logging.getLogger(__name__)

# How often the supervisor checks each worker (seconds).
_POLL_INTERVAL = 10.0


class Supervisor:
    """
    Polls registered workers and restarts them when they become unhealthy.

    Each worker is described by three arguments to register():
      name      — label used in log messages
      is_alive  — () -> bool: return True if the worker is healthy
      restart   — () -> None: recreate/restart the worker; must be idempotent

    Both callables are invoked from the supervisor's own daemon thread.
    If a restart touches Qt objects, wrap it with QTimer.singleShot(0, fn)
    so the actual work runs in the Qt main thread.
    """

    def __init__(self, poll_interval: float = _POLL_INTERVAL) -> None:
        self._poll_interval = poll_interval
        self._workers: list[tuple[str, Callable[[], bool], Callable[[], None]]] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="Supervisor")

    def register(
        self,
        name: str,
        is_alive: Callable[[], bool],
        restart: Callable[[], None],
    ) -> None:
        self._workers.append((name, is_alive, restart))

    def start(self) -> None:
        self._thread.start()
        logger.info("Supervisor started — monitoring %d worker(s)", len(self._workers))

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=self._poll_interval + 2)

    def _loop(self) -> None:
        while not self._stop.wait(self._poll_interval):
            for name, is_alive, restart in self._workers:
                try:
                    if not is_alive():
                        logger.warning("Supervisor: %s is down — restarting", name)
                        restart()
                        logger.info("Supervisor: %s restarted", name)
                except Exception:
                    logger.exception("Supervisor: unhandled error handling %s", name)
