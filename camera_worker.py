#!/usr/bin/env python3
# camera_worker.py — Worker de envío de comandos VISCA
#
# Responsabilidad única: mantener una conexión TCP persistente con una cámara
# y despachar comandos desde una cola en un thread dedicado.
#
# MOTIVO DE SEPARACIÓN: la lógica de red (reconexión, gestión de socket,
# cola) no tiene nada que ver con la UI.  Separarlo hace ambas partes
# más fáciles de testear y de depurar.

from __future__ import annotations  # Permite type hints modernos (X | Y, list[...]) en Python <3.10

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
      si la cámara no responde (p.ej. apagada). Los comandos más antiguos
      se descartan cuando la cola está llena.
    """

    _QUEUE_MAXSIZE = 20  # Límite de cola: evita acumular comandos obsoletos

    def __init__(self, ip: str, port: int = VISCA_PORT):
        self.ip   = ip
        self.port = port

        # Cola con límite: si se llena, los comandos nuevos son descartados
        # en send() para no bloquear el hilo de la UI.
        self._queue  = queue.Queue(maxsize=self._QUEUE_MAXSIZE)
        self._sock   = None
        self._lock   = threading.Lock()  # Protege acceso a self._sock

        # Thread daemon: muere automáticamente cuando el proceso principal termina.
        # No hace falta llamar a stop() explícitamente al cerrar la app.
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"CamWorker-{ip}")
        self._thread.start()

    def send(self, hex_cmd: str) -> bool:
        """
        Encola un comando VISCA en formato hex string (ej. "81010604FF").
        Devuelve True si se encoló, False si la cola estaba llena y se descartó.

        MOTIVO: no bloquear nunca el hilo de la UI. Si la cámara no responde
        y la cola se llena, simplemente se ignoran nuevos comandos en lugar
        de congelar la interfaz.
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
        No lanza excepción — los errores se gestionan silenciosamente
        para que el worker siga vivo aunque la cámara esté apagada.

        IMPORTANTE: si connect() lanza excepción, el socket se cierra
        explícitamente para evitar file descriptor leak — los sockets no
        liberados se acumulan si la cámara no está disponible y el worker
        reintenta continuamente.
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.settimeout(SOCKET_TIMEOUT)
            s.connect((self.ip, self.port))
            print(f"[INFO] CameraWorker: conectado a {self.ip}:{self.port}")
            return s
        except (socket.timeout, socket.error, OSError) as exc:
            print(f"[WARNING] CameraWorker: no se pudo conectar a {self.ip}: {exc}")
            s.close()  # Cerrar explícitamente: evita leak de file descriptors
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
        Extrae comandos de la cola y los envía.
        Si el envío falla, cierra el socket y reintenta UNA vez
        (reconectando antes del segundo intento).
        Si el segundo intento también falla, el comando se descarta
        y el worker continúa con el siguiente.
        """
        while True:
            cmd = self._queue.get()  # Bloquea hasta que haya algo en la cola

            # Intentar hasta 2 veces: 1ª con socket existente, 2ª tras reconectar
            for attempt in range(2):
                with self._lock:
                    if self._sock is None:
                        self._sock = self._connect()
                    if self._sock is None:
                        break  # Sin socket: descartar comando

                try:
                    raw = binascii.unhexlify(cmd)
                    with self._lock:
                        self._sock.send(raw)
                        self._sock.recv(1024)  # Leer ACK/respuesta de la cámara
                    break  # Éxito: salir del bucle de reintentos

                except (socket.timeout, socket.error, OSError, binascii.Error) as exc:
                    print(f"[WARNING] CameraWorker {self.ip} intento {attempt+1}: {exc}")
                    self._close_socket()
                    # Si era el primer intento, el bucle volverá a intentarlo reconectando.
                    # Si era el segundo, el comando se descarta y continuamos.
