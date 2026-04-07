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
#   - CLARIDAD: se separa la adquisición del socket de su uso en _run(),
#     haciendo el flujo más fácil de leer y de auditar.

from __future__ import annotations  # type hints modernos en Python <3.10

import queue
import socket
import binascii
import threading

from config import SOCKET_TIMEOUT, VISCA_PORT


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

    _QUEUE_MAXSIZE = 20  # Límite de cola: descarta comandos nuevos si se llena

    def __init__(self, ip: str, port: int = VISCA_PORT):
        self.ip   = ip
        self.port = port

        # Cola con límite: put_nowait() lanza queue.Full si está llena
        self._queue = queue.Queue(maxsize=self._QUEUE_MAXSIZE)
        self._sock  = None
        self._lock  = threading.Lock()  # Protege acceso a self._sock entre hilos

        # Thread daemon: muere cuando el proceso principal termina.
        # No hace falta llamar a stop() explícitamente al cerrar la app.
        self._thread = threading.Thread(
            target=self._run, daemon=True, name=f"CamWorker-{ip}")
        self._thread.start()

    def send(self, hex_cmd: str) -> bool:
        """
        Encola un comando VISCA en formato hex string (ej. "81010604FF").
        Devuelve True si se encoló, False si la cola estaba llena.

        MOTIVO: nunca bloquear el hilo de la UI. Si la cámara no responde
        y la cola se llena, se descartan nuevos comandos en lugar de
        congelar la interfaz.
        """
        try:
            self._queue.put_nowait(hex_cmd)
            return True
        except queue.Full:
            print(f"[WARNING] CameraWorker {self.ip}: cola llena, comando descartado: {hex_cmd}")
            return False

    def _connect(self) -> socket.socket | None:
        """
        Intenta abrir una conexión TCP nueva con la cámara.
        Devuelve el socket si tiene éxito, None si falla.

        IMPORTANTE: si connect() lanza excepción, el socket se cierra
        explícitamente para evitar file descriptor leak.
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.settimeout(SOCKET_TIMEOUT)
            s.connect((self.ip, self.port))
            print(f"[INFO] CameraWorker: conectado a {self.ip}:{self.port}")
            return s
        except (socket.timeout, socket.error, OSError) as exc:
            print(f"[WARNING] CameraWorker: no se pudo conectar a {self.ip}: {exc}")
            s.close()  # Cierre explícito: evita leak de file descriptors
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
            cmd = self._queue.get()  # Bloquea hasta que haya algo en la cola

            # Intentar hasta 2 veces: 1ª con socket existente, 2ª tras reconectar
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
                    raw = binascii.unhexlify(cmd)
                    sock_ref.send(raw)
                    sock_ref.recv(1024)  # Leer ACK de la cámara (sin lock)
                    break  # Éxito: salir del bucle de reintentos

                except (socket.timeout, socket.error, OSError, binascii.Error) as exc:
                    print(f"[WARNING] CameraWorker {self.ip} intento {attempt + 1}: {exc}")
                    self._close_socket()
                    # Si era el primer intento → el bucle reconecta y reintenta.
                    # Si era el segundo → el comando se descarta silenciosamente.