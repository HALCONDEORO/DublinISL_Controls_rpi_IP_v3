#!/usr/bin/env python3
# camera_worker.py — Worker de envío de comandos VISCA
#
# Responsabilidad única: mantener una conexión TCP persistente con una cámara
# y despachar comandos desde una cola en un thread dedicado.
#
# CAMBIOS RESPECTO A VERSIÓN ANTERIOR:
#   - FIX DEADLOCK: recv() ya no se ejecuta dentro de self._lock.
#     Antes: `with self._lock: sock.send(raw); sock.recv(1024)`
#     Si la cámara no respondía, el lock quedaba bloqueado indefinidamente.
#     Ahora: se copia la referencia del socket con el lock, se libera,
#     y se hace send/recv sin tenerlo. Si el socket se cierra entre medias
#     (por _close_socket desde otro hilo), la excepción se captura normalmente.
#
#   - FIX PYTHON 3.9: `socket.socket | None` es sintaxis 3.10+.
#     Aunque `from __future__ import annotations` la acepta como string en
#     anotaciones, usar Optional[socket.socket] es explícito y compatible
#     con cualquier herramienta de análisis estático sobre Python 3.9.
#
#   - CLARIDAD: se separa la adquisición del socket de su uso en _run(),
#     haciendo el flujo más fácil de leer y de auditar.

from __future__ import annotations  # type hints modernos sin romper Python 3.9 en runtime

import logging
import queue
import select
import socket
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional  # reemplaza `socket.socket | None` (sintaxis 3.10+)

from PyQt5.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)

from config import SOCKET_TIMEOUT, VISCA_PORT, CAMERA_QUEUE_MAXSIZE, HEARTBEAT_TIMEOUT


@dataclass
class ViscaCommand:
    """
    Representa un comando VISCA listo para ejecutar.

    camera:     1 = CAM1 (Platform), 2 = CAM2 (Comments). Usado por ViscaController
                para enrutar al worker correcto antes de encolar.
    payload:    bytes completos del frame VISCA (cam_id + cuerpo del comando).
    priority:   si True, vacía la cola antes de encolar. Usar exclusivamente en STOP.
    on_success: callback invocado desde el thread del worker tras envío exitoso.
    on_failure: callback invocado desde el thread del worker tras todos los reintentos fallidos.

    IMPORTANTE: los callbacks se ejecutan en el thread del worker, no en el hilo Qt.
    Para actualizar widgets desde ellos usa QTimer.singleShot(0, fn) o el helper
    ViscaController._ui(fn).
    """
    camera:     int
    payload:    bytes
    priority:   bool                          = False
    on_success: Optional[Callable[[], None]] = None
    on_failure: Optional[Callable[[], None]] = None


class CameraWorkerSignals(QObject):
    """Señales Qt para CameraWorker (QObject requerido para pyqtSignal)."""
    connection_changed = pyqtSignal(bool)  # True = conectado, False = desconectado


class CameraWorker:
    """
    Gestiona la conexión TCP con una cámara VISCA y despacha comandos
    de forma asíncrona desde una cola interna.

    DISEÑO:
    - Un único thread de fondo consume la cola y envía comandos.
    - Si el socket falla, intenta reconectar una vez antes de descartar
      el comando, evitando bloquear la UI indefinidamente.
    - La cola tiene un límite de 20 comandos para evitar acumulación
      si la cámara no responde (p.ej. apagada). Los comandos más nuevos
      se descartan cuando la cola está llena.
    """

    def __init__(self, ip: str, port: int = VISCA_PORT):
        self.ip   = ip
        self.port = port

        self.signals = CameraWorkerSignals()  # señales Qt para la UI
        self._is_connected = False            # estado actual de conexión

        # Cola con límite: put_nowait() lanza queue.Full si está llena
        self._queue: queue.Queue = queue.Queue(maxsize=CAMERA_QUEUE_MAXSIZE)

        # CAMBIADO: anotación de tipo usa Optional en lugar de `socket.socket | None`
        # MOTIVO: `|` para tipos es sintaxis Python 3.10+; Optional es compatible con 3.9
        self._sock: Optional[socket.socket] = None
        self._lock = threading.Lock()  # Protege acceso a self._sock entre hilos

        # Timestamp actualizado en cada iteración de _run(); el supervisor
        # lo usa para detectar hilos vivos pero congelados.
        self._last_heartbeat: float = time.monotonic()

        # Thread daemon: muere cuando el proceso principal termina.
        # No hace falta llamar a stop() explícitamente al cerrar la app.
        self._thread = threading.Thread(
            target=self._run, daemon=True, name=f"CamWorker-{ip}")
        self._thread.start()

    def send(self, cmd: ViscaCommand) -> bool:
        """
        Encola un ViscaCommand para ejecución asíncrona.
        Devuelve True si se encoló, False si la cola estaba llena.

        MOTIVO: nunca bloquear el hilo de la UI. Si la cámara no responde
        y la cola se llena, se descartan nuevos comandos en lugar de
        congelar la interfaz.
        """
        try:
            self._queue.put_nowait(cmd)
            return True
        except queue.Full:
            logger.warning("CameraWorker %s: cola llena, descartado: %s",
                           self.ip, cmd.payload.hex())
            return False

    def send_priority(self, cmd: ViscaCommand):
        """
        Vacía la cola de comandos pendientes y coloca cmd en primer lugar.

        Usar para comandos críticos de parada: garantiza que el STOP se
        ejecute inmediatamente sin esperar a comandos de movimiento acumulados.
        Los comandos ya en vuelo (siendo enviados por el worker) no se ven afectados.
        """
        # Drenar la cola sin bloquear
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        # Insertar el comando prioritario
        try:
            self._queue.put_nowait(cmd)
        except queue.Full:
            pass

    def heartbeat_age(self) -> float:
        """Seconds since the worker loop last ran. Used by the supervisor."""
        return time.monotonic() - self._last_heartbeat

    def restart(self) -> None:
        """Re-spawn the worker thread if it has stopped unexpectedly."""
        if not self._thread.is_alive():
            self._close_socket()
            self._last_heartbeat = time.monotonic()
            self._thread = threading.Thread(
                target=self._run, daemon=True, name=f"CamWorker-{self.ip}")
            self._thread.start()
            logger.info("CameraWorker %s: thread restarted by supervisor", self.ip)

    def _set_connected(self, connected: bool):
        """Actualiza el estado de conexión y emite señal si cambia."""
        if connected != self._is_connected:
            self._is_connected = connected
            self.signals.connection_changed.emit(connected)

    def _ping(self):
        """Heartbeat periódico: verifica/restaura la conexión cuando la cola está inactiva."""
        with self._lock:
            sock_ref = self._sock

        if sock_ref is not None:
            if self._socket_alive(sock_ref):
                self._set_connected(True)
            else:
                # Socket muerto (cámara apagada / cable desconectado)
                self._close_socket()
                with self._lock:
                    self._sock = self._connect()
                    sock_ref = self._sock
                self._set_connected(sock_ref is not None)
        else:
            # Sin socket → intentar reconectar
            with self._lock:
                if self._sock is None:
                    self._sock = self._connect()
                sock_ref = self._sock
            self._set_connected(sock_ref is not None)

    @staticmethod
    def _socket_alive(sock: socket.socket) -> bool:
        """
        Comprueba si un socket TCP sigue activo sin enviar datos de aplicación.

        Usa select() con timeout cero para ver si el descriptor tiene datos
        listos para leer. En TCP, readable sin haber enviado nada significa
        que el par envió EOF (FIN) o RST, es decir, la conexión está cerrada.
        Si no hay nada legible, intenta send(b"") — una escritura vacía no
        transmite bytes pero sí detecta si el descriptor local es válido.
        """
        try:
            readable, _, _ = select.select([sock], [], [], 0)
            if readable:
                # Hay datos listos: en un protocolo petición/respuesta como VISCA
                # no deberían llegar datos espontáneos; si los hay, o el par cerró
                # la conexión (recv devuelve b"") o llegó basura → desconectado.
                data = sock.recv(1)
                return len(data) > 0
            # Sin datos pendientes → verificar que el descriptor local sigue abierto
            sock.send(b"")
            return True
        except (OSError, socket.error):
            return False

    def _connect(self) -> Optional[socket.socket]:
        """
        Intenta abrir una conexión TCP nueva con la cámara.
        Devuelve el socket si tiene éxito, None si falla.

        CAMBIADO: anotación de retorno usa Optional[socket.socket]
        MOTIVO: `socket.socket | None` requiere Python 3.10+; esta forma
        es equivalente y compatible con Python 3.9 en producción (RPi).

        IMPORTANTE: si connect() lanza excepción, el socket se cierra
        explícitamente para evitar file descriptor leak.
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.settimeout(SOCKET_TIMEOUT)
            s.connect((self.ip, self.port))
            logger.info("CameraWorker: conectado a %s:%s", self.ip, self.port)
            self._set_connected(True)
            return s
        except (socket.timeout, socket.error, OSError) as exc:
            # [WARN] y no [ERROR]: fallo de conexión en arranque es esperado
            # si las cámaras aún no están encendidas o alcanzables en desarrollo.
            logger.warning("CameraWorker: no se pudo conectar a %s: %s", self.ip, exc)
            s.close()  # Cierre explícito: evita leak de file descriptors
            self._set_connected(False)
            return None

    def _close_socket(self):
        """Cierra el socket actual de forma segura, ignorando errores."""
        with self._lock:
            if self._sock is not None:
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None
        self._set_connected(False)

    def _run(self):
        """
        Bucle principal del worker (corre en thread de fondo).

        FIX DEADLOCK:
        Antes, send() y recv() se ejecutaban dentro de `with self._lock`.
        Si recv() bloqueaba (cámara sin respuesta), el lock quedaba tomado
        indefinidamente, impidiendo que _close_socket() pudiera ejecutarse.

        Ahora el flujo es:
          1. Adquirir lock → copiar referencia del socket → liberar lock.
          2. Hacer send/recv SIN el lock.
          3. Si falla → _close_socket() puede adquirir el lock normalmente.

        Si el socket se cierra entre step 1 y step 2 (por _close_socket
        llamado desde otro contexto), la excepción de send/recv se captura
        y el worker reintenta reconectando.
        """
        while True:
            self._last_heartbeat = time.monotonic()
            # Espera hasta HEARTBEAT_TIMEOUT s; si no hay comando, ejecuta heartbeat y vuelve a esperar
            try:
                cmd = self._queue.get(timeout=HEARTBEAT_TIMEOUT)
            except queue.Empty:
                self._ping()
                continue

            # Intentar hasta 2 veces: 1ª con socket existente, 2ª tras reconectar
            _succeeded = False
            for attempt in range(2):

                # --- Fase 1: obtener referencia del socket (con lock breve) ---
                with self._lock:
                    if self._sock is None:
                        self._sock = self._connect()
                    sock_ref = self._sock  # copia local: lock se libera aquí

                if sock_ref is None:
                    break  # Sin conexión disponible: descartar comando

                # --- Fase 2: enviar y leer ACK SIN el lock ---
                # MOTIVO: recv() puede tardar hasta SOCKET_TIMEOUT segundos.
                # Hacerlo sin lock permite que _close_socket() funcione
                # mientras tanto sin quedarse esperando.
                try:
                    sock_ref.send(cmd.payload)
                    sock_ref.recv(1024)  # Leer ACK de la cámara (sin lock)
                    self._set_connected(True)
                    _succeeded = True
                    break  # Éxito: salir del bucle de reintentos

                except (socket.timeout, socket.error, OSError) as exc:
                    logger.warning("CameraWorker %s intento %d: %s", self.ip, attempt + 1, exc)
                    self._close_socket()
                    # Si era el primer intento → el bucle reconecta y reintenta.
                    # Si era el segundo → el comando se descarta e invoca on_failure.

            if _succeeded:
                if cmd.on_success:
                    cmd.on_success()
            else:
                if cmd.on_failure:
                    cmd.on_failure()