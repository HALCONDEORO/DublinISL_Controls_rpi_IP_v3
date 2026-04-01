#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────────
#
#  Name:    LBD - Sign Language Camera Controls - IP RPI Version
#  Author:  Isaac Urwin  -  IP & ISL revision by Simon Laban
#  Date:    November 2025 / Updated March 2026
#
#  Purpose:
#    PyQt5 GUI that controls two PTZ cameras over VISCA-over-IP (TCP port 5678).
#    Camera 1 faces the platform (speaker); Camera 2 faces the audience.
#    Operators click seat buttons (numbered 4-128) to call presets, or use
#    the arrow/zoom controls for manual framing.
#
#  Protocol overview (for new readers):
#    VISCA is a serial/TCP camera control protocol.  Every command is a short
#    hex byte string: <device_id> <command_bytes> FF.  This app sends those
#    strings over a plain TCP socket to port 5678 on the camera's IP address.
#    Example: "81 01 04 07 22 FF" tells Camera 1 (id=81) to zoom in slowly.
#
#  Session lifecycle:
#    1. Operator presses ⏻  →  Power ON sent to both cameras
#    2. App waits 8 seconds (cameras need time to boot their motors)
#    3. Both cameras move to their Home position automatically
#    4. Operator clicks seats to recall preset positions
#    5. Pressing ⏻ again asks for confirmation, then sends Standby to both
#
#  UI layout (1920 × 1080 px):
#    Left area  (x 0-1460)  : Seating-plan image + numbered seat buttons
#    Right panel (x 1500+)  : Camera selection, speed, preset mode,
#                             PTZ arrows, zoom, focus/exposure, config
#
#  Config files (plain text, one value per file, created in working directory):
#    PTZ1IP.txt   IP address of the Platform camera  (default 172.16.1.11)
#    PTZ2IP.txt   IP address of the Comments camera  (default 172.16.1.12)
#    Cam1ID.txt   VISCA hex device ID for Camera 1   (default "81")
#    Cam2ID.txt   VISCA hex device ID for Camera 2   (default "82")
#    Contact.txt  Support contact shown in the Help dialog
#    If any file is missing the app continues with the default shown above.
#
# ─────────────────────────────────────────────────────────────────────────────

import os
import re
import sys
import queue
import socket
import binascii
import threading

from PyQt5 import QtGui, QtWidgets, QtCore
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QToolButton,
    QLabel, QMessageBox, QButtonGroup, QInputDialog, QSlider
)
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt


# ─────────────────────────────────────────────────────────────────────────────
#  Speed slider constants
# ─────────────────────────────────────────────────────────────────────────────
SPEED_MIN     = 1   # Slowest pan/tilt speed (VISCA minimum is 1)
SPEED_MAX     = 18  # Fastest safe pan/tilt speed (ceiling for both axes)
SPEED_DEFAULT = 8   # Slider starts here; roughly medium pace


# ─────────────────────────────────────────────────────────────────────────────
#  Shared network constant
# ─────────────────────────────────────────────────────────────────────────────
SOCKET_TIMEOUT = 1  # Seconds used for every TCP connect / send / recv call


# ─────────────────────────────────────────────────────────────────────────────
#  Config helpers
# ─────────────────────────────────────────────────────────────────────────────

def _read_config(filename, default):
    """
    Read a single-line text config file; return its stripped contents.
    If the file is missing or unreadable, log a warning and return `default`.
    """
    try:
        with open(filename, 'r') as f:
            return f.read().strip()
    except (FileNotFoundError, IOError) as exc:
        print(f"[WARNING] Could not read '{filename}': {exc}  -> using default '{default}'")
        return default


IPAddress  = _read_config('PTZ1IP.txt',  '172.16.1.11')   # Platform camera IP
IPAddress2 = _read_config('PTZ2IP.txt',  '172.16.1.12')   # Comments camera IP
Cam1ID     = _read_config('Cam1ID.txt',  '81')             # VISCA device ID hex string
Cam2ID     = _read_config('Cam2ID.txt',  '82')
Contact    = _read_config('Contact.txt', 'No contact information available.')

ButtonColor = "black"   # Seat-button text colour


# ─────────────────────────────────────────────────────────────────────────────
#  Network timeout
# ─────────────────────────────────────────────────────────────────────────────
# 1 second is enough for a camera on the local network; raise it if you see
# frequent false "Red" indicators at startup on a slow switch or Wi-Fi link.
SOCKET_TIMEOUT = 1  # seconds

# ─────────────────────────────────────────────────────────────────────────────
#  PTZ speed range
#
#  The VISCA Pan-Tilt Drive command accepts a pan-speed byte and a tilt-speed
#  byte, each in the range 0x01–0x18 (1–24 for pan, 1–20 for tilt).  We cap
#  at 18 so the same value is safe for both axes without separate clamping.
#
#  The QSlider exposes this range directly; SPEED_DEFAULT starts at ~mid-range.
#  For reference: the old SLOW button used speed 4, the old FAST button used 16.
#
#  Zoom speed is a separate nibble (0–7) derived by linear interpolation so
#  both axes always feel proportional to each other.
# ─────────────────────────────────────────────────────────────────────────────
SPEED_MIN     = 1   # slowest pan/tilt (VISCA minimum)
SPEED_MAX     = 18  # fastest safe pan/tilt (fits both pan 0x18 and tilt 0x14)
SPEED_DEFAULT = 8   # slider initial position (~medium; old SLOW=4, old FAST=16)

def _check_camera(ip, cam_id):
    """
    Try a one-shot TCP connection to verify a camera is reachable at startup.
    Returns "Green" if the camera responded within SOCKET_TIMEOUT, else "Red".
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(SOCKET_TIMEOUT)
            s.connect((ip, 5678))
            s.send(binascii.unhexlify(cam_id + "090400FF"))   # VISCA power inquiry
            s.recv(1024)
        return "Green"
    except (socket.timeout, socket.error, OSError):
        return "Red"


Cam1Check = _check_camera(IPAddress,  Cam1ID)
Cam2Check = _check_camera(IPAddress2, Cam2ID)


# ─────────────────────────────────────────────────────────────────────────────
#  VISCA preset number -> hex byte mapping
#
#  Presets 90-99 would land in the VISCA-reserved range 0x5A-0x8B, so they
#  are remapped to 0x8C-0x95.  All others use direct two-digit hex conversion.
# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
#  VISCA preset number → hex byte value
#
#  VISCA uses certain byte values (0x5A–0x8B) as internal framing bytes.
#  If a preset number maps to one of those bytes the camera silently ignores
#  the command.  Presets 90-99 would land in that range, so we remap them to
#  0x8C-0x95 (just above the reserved zone).  All other presets convert
#  directly (e.g. preset 4 → 0x04, preset 128 → 0x80).
#
#  Range covered: 1-128
#    1-3   : platform positions (Chairman, Left, Right) — always Camera 1
#    4-128 : audience seats — active camera depends on the panel selection
# ─────────────────────────────────────────────────────────────────────────────
PRESET_MAP = {}
for _i in range(1, 90):       # Direct hex for 1-89
    PRESET_MAP[_i] = f"{_i:02X}"
for _i in range(90, 100):     # 90-99 remapped to 0x8C-0x95 (avoids reserved bytes)
    PRESET_MAP[_i] = f"{0x8C + (_i - 90):02X}"
for _i in range(100, 130):    # Direct hex for 100-129 (range end is exclusive)
    PRESET_MAP[_i] = f"{_i:02X}"

# ─────────────────────────────────────────────────────────────────────────────
#  Seat pixel positions
#
#  Maps each preset number to the (x, y) pixel coordinates of its button on
#  the 1920×1080 background image.  The numbers match the physical seat labels
#  printed on the seating-plan image (Background_ISL_v2.jpg).
#  This is a module-level constant — it never changes while the app is running.
# ─────────────────────────────────────────────────────────────────────────────
SEAT_POSITIONS = {
    # Row 1
     4:(70,210),  5:(131,210),  6:(192,210),  7:(253,210),
     8:(479,210), 9:(540,210), 10:(601,210), 11:(662,210),
    12:(722,210),13:(783,210), 14:(844,210),
    15:(1070,210),16:(1130,210),17:(1191,210),18:(1252,210),
    # Row 2
    19:(70,295), 20:(131,295), 21:(192,295), 22:(253,295),
    23:(479,295),24:(540,295), 25:(601,295), 26:(662,295),
    27:(722,295),28:(783,295), 29:(844,295),
    30:(1070,295),31:(1130,295),32:(1191,295),33:(1252,295),
    # Row 3
    34:(70,382), 35:(131,382), 36:(192,382), 37:(253,382),
    38:(479,382),39:(540,382), 40:(601,382), 41:(662,382),
    42:(723,382),43:(783,382), 44:(844,382),
    45:(1070,382),46:(1130,382),47:(1191,382),48:(1252,382),
    # Row 4
    49:(70,465), 50:(131,465), 51:(192,465), 52:(253,465),
    53:(479,465),54:(540,465), 55:(601,465), 56:(662,465),
    57:(722,465),58:(783,465), 59:(844,465),
    60:(1070,465),61:(1130,465),62:(1191,465),63:(1252,465),
    # Row 5
    64:(70,550), 65:(131,550), 66:(192,550), 67:(253,550),
    68:(479,550),69:(540,550), 70:(601,550), 71:(662,550),
    72:(722,550),73:(783,550), 74:(844,550),
    75:(1070,550),76:(1130,550),77:(1191,550),78:(1252,550),
    # Row 6
    79:(70,635), 80:(131,635), 81:(192,635), 82:(253,635),
    83:(479,635),84:(540,635), 85:(601,635), 86:(662,635),
    87:(722,635),88:(783,635), 89:(844,635),
    90:(1070,635),91:(1130,635),92:(1191,635),93:(1252,635),
    # Row 7
    94:(70,720), 95:(131,720), 96:(192,720), 97:(253,720),
    98:(479,720),99:(540,720),100:(601,720),101:(662,720),
   102:(722,720),103:(783,720),104:(844,720),
   105:(1070,720),106:(1130,720),107:(1191,720),108:(1252,720),
    # Row 8
   109:(70,805), 110:(131,805),111:(192,805),112:(253,805),
   113:(479,805),114:(540,805),115:(601,805),116:(662,805),
   117:(722,805),118:(783,805),119:(844,805),
   120:(1070,805),121:(1130,805),122:(1191,805),123:(1252,805),
    # Row 9
   124:(108,975),125:(201,975),126:(481,975),127:(578,975),
    # Wheelchair space
   128:(150,110),
    # Second Room — separate space at the back of the hall
   129:(380,960),
}


# ─────────────────────────────────────────────────────────────────────────────
#  Validation helpers (used in the config dialogs)
# ─────────────────────────────────────────────────────────────────────────────

def _is_valid_ip(text):
    """Return True if text looks like a valid IPv4 address."""
    match = re.match(r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$', text.strip())
    if not match:
        return False
    return all(0 <= int(g) <= 255 for g in match.groups())


def _is_valid_cam_id(text):
    """Return True if text is a non-empty hexadecimal string (e.g. "81", "82")."""
    text = text.strip()
    if not text:
        return False
    try:
        binascii.unhexlify(text)
        return True
    except (binascii.Error, ValueError):
        return False


# ─────────────────────────────────────────────────────────────────────────────
#  Seat pixel positions (module-level constant — never changes at runtime)
#
#  Maps preset number -> (x, y) top-left corner of its button on screen.
# ─────────────────────────────────────────────────────────────────────────────
SEAT_POSITIONS = {
    # Row 1
     4:(70,210),  5:(131,210),  6:(192,210),  7:(253,210),
     8:(479,210), 9:(540,210), 10:(601,210), 11:(662,210),
    12:(722,210),13:(783,210), 14:(844,210),
    15:(1070,210),16:(1130,210),17:(1191,210),18:(1252,210),
    # Row 2
    19:(70,295), 20:(131,295), 21:(192,295), 22:(253,295),
    23:(479,295),24:(540,295), 25:(601,295), 26:(662,295),
    27:(722,295),28:(783,295), 29:(844,295),
    30:(1070,295),31:(1130,295),32:(1191,295),33:(1252,295),
    # Row 3
    34:(70,382), 35:(131,382), 36:(192,382), 37:(253,382),
    38:(479,382),39:(540,382), 40:(601,382), 41:(662,382),
    42:(723,382),43:(783,382), 44:(844,382),
    45:(1070,382),46:(1130,382),47:(1191,382),48:(1252,382),
    # Row 4
    49:(70,465), 50:(131,465), 51:(192,465), 52:(253,465),
    53:(479,465),54:(540,465), 55:(601,465), 56:(662,465),
    57:(722,465),58:(783,465), 59:(844,465),
    60:(1070,465),61:(1130,465),62:(1191,465),63:(1252,465),
    # Row 5
    64:(70,550), 65:(131,550), 66:(192,550), 67:(253,550),
    68:(479,550),69:(540,550), 70:(601,550), 71:(662,550),
    72:(722,550),73:(783,550), 74:(844,550),
    75:(1070,550),76:(1130,550),77:(1191,550),78:(1252,550),
    # Row 6
    79:(70,635), 80:(131,635), 81:(192,635), 82:(253,635),
    83:(479,635),84:(540,635), 85:(601,635), 86:(662,635),
    87:(722,635),88:(783,635), 89:(844,635),
    90:(1070,635),91:(1130,635),92:(1191,635),93:(1252,635),
    # Row 7
    94:(70,720), 95:(131,720), 96:(192,720), 97:(253,720),
    98:(479,720),99:(540,720),100:(601,720),101:(662,720),
   102:(722,720),103:(783,720),104:(844,720),
   105:(1070,720),106:(1130,720),107:(1191,720),108:(1252,720),
    # Row 8
   109:(70,805), 110:(131,805),111:(192,805),112:(253,805),
   113:(479,805),114:(540,805),115:(601,805),116:(662,805),
   117:(722,805),118:(783,805),119:(844,805),
   120:(1070,805),121:(1130,805),122:(1191,805),123:(1252,805),
    # Row 9
   124:(108,975),125:(201,975),126:(481,975),127:(578,975),
    # Wheelchair space
   128:(150,110),
   # Second Room
   129:(380,960),
}


# =============================================================================
#  CameraWorker — persistent TCP connection + serialised command queue
#
#  Each camera gets one worker instance.  Commands are enqueued from the
#  UI thread and consumed by a single daemon thread, so:
#    - The UI never blocks waiting for the network.
#    - Commands arrive at the camera in strict order (Stop always follows move).
#    - No thread-storm: rapid button presses queue up instead of spawning
#      hundreds of threads.
#    - The socket is kept open between commands and reconnected transparently
#      if the connection drops.
# =============================================================================

class CameraWorker:
    """Persistent VISCA-over-IP connection with a serialised send queue."""

    def __init__(self, ip, port=5678):
        self.ip   = ip
        self.port = port
        self._queue  = queue.Queue()
        self._sock   = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def send(self, hex_cmd):
        """Enqueue a complete VISCA hex string (cam_id + command, no spaces)."""
        self._queue.put(hex_cmd)

    # ------------------------------------------------------------------
    #  Internal helpers
    # ------------------------------------------------------------------

    def _connect(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(SOCKET_TIMEOUT)
            s.connect((self.ip, self.port))
            return s
        except (socket.timeout, socket.error, OSError):
            return None

    def _run(self):
        """Worker loop — blocks on the queue, sends each command in order."""
        while True:
            cmd = self._queue.get()
            for _ in range(2):   # one retry on network failure
                if self._sock is None:
                    self._sock = self._connect()
                if self._sock is None:
                    break
                try:
                    self._sock.send(binascii.unhexlify(cmd))
                    self._sock.recv(1024)   # discard VISCA ACK (always small)
                    break
                except (socket.timeout, socket.error, OSError):
                    try:
                        self._sock.close()
                    except Exception:
                        pass
                    self._sock = None


# =============================================================================
#  MainWindow
# =============================================================================

class MainWindow(QMainWindow):
    """
    Main application window (1920x1080).

    Layout:
      Left area  (x 0-1460)  : Seat-position preset buttons on a background image.
      Right panel (x 1500+)  : Camera selection, speed slider, preset mode,
                               PTZ arrows, zoom, focus/exposure, config buttons.
    """

    def __init__(self):
        super().__init__()

        self.setWindowTitle('Camera Controls')
        self.setGeometry(0, 0, 1920, 1080)

        # Per-camera backlight compensation state (True = ON).
        self.backlight_on = {1: False, 2: False}

        # One persistent worker (connection + queue) per camera IP
        self._workers = {
            IPAddress:  CameraWorker(IPAddress),
            IPAddress2: CameraWorker(IPAddress2),
        }

        # ── Background image ──────────────────────────────────────────────────
        pixmap = QPixmap("Background_ISL_v2.jpg")
        scaled_pixmap = pixmap.scaled(1920, 1080, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        background = QLabel(self)
        background.setPixmap(scaled_pixmap)
        background.setGeometry(0, -30, 1920, 1080)
        background.lower()



        # ── Seat buttons (dynamic, one per entry in SEAT_POSITIONS) ──────────
        # Each button calls go_to_preset(n) with the seat's preset number.
        # We use a default-argument trick (n=seat_number) to capture the loop
        # variable correctly inside the lambda.
        
        # ── Platform preset buttons (Chairman, Left, Right) ───────────────────
        Preset1 = QPushButton('Chairman', self)
        Preset1.resize(110, 110)
        Preset1.move(623, 35)
        Preset1.setStyleSheet(
            "background-color: rgba(0,0,0,0); font: 14px; font-weight: bold; "
            "color: black; padding-top: 70px"
        )
        Preset1.clicked.connect(lambda: self.go_to_preset(1))

        Preset2 = QPushButton('Left', self)
        Preset2.resize(110, 110)
        Preset2.move(460, 35)
        Preset2.setStyleSheet(
            "background-color: rgba(0,0,0,0); font: 14px; font-weight: bold; "
            "color: black; padding-top: 70px"
        )
        Preset2.clicked.connect(lambda: self.go_to_preset(2))

        Preset3 = QPushButton('Right', self)
        Preset3.resize(110, 110)
        Preset3.move(803, 35)
        Preset3.setStyleSheet(
            "background-color: rgba(0,0,0,0); font: 14px; font-weight: bold; "
            "color: black; padding-top: 70px"
        )
        Preset3.clicked.connect(lambda: self.go_to_preset(3))

        # ── Seat buttons ──────────────────────────────────────────────────────
        for seat_number in range(4, 130):
            if seat_number not in SEAT_POSITIONS:
                continue
            x, y = SEAT_POSITIONS[seat_number]

            button = GoButton(str(seat_number), self)
            button.move(x, y)

            if seat_number == 129:
                button.hide()
                button = QToolButton(self)
                button.move(x, y)
                button.resize(55, 65)
                button.setText('Second Room')
                button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
                button.setStyleSheet(
                    "QToolButton { background-color: rgba(0,0,0,10); border: 0px solid black; "
                    "border-radius: 5px; font: 8px; font-weight: bold; color: " + ButtonColor + "; }"
                )
                pix = QPixmap("second_room.png").scaled(
                    40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                button.setIcon(QtGui.QIcon(pix))
                button.setIconSize(QtCore.QSize(40, 40))

            button.clicked.connect(
                lambda checked=False, n=seat_number: self.go_to_preset(n)
            )
            setattr(self, f"Seat{seat_number}", button)

        # ── SESSION MANAGEMENT — top-left corner ──────────────────────────────
        self.session_active = False

        self.BtnSession = QPushButton('\u23fb', self)
        self.BtnSession.setGeometry(10, 10, 50, 50)
        self.BtnSession.setToolTip('Start Session: Power ON both cameras and go Home')
        self.BtnSession.setStyleSheet(
            "QPushButton{background-color: #8b1a1a; border: 2px solid #5a0d0d; "
            "font: bold 26px; color: white; border-radius: 25px}"
            "QPushButton:pressed{background-color: #5a0d0d}"
        )
        self.BtnSession.clicked.connect(self.ToggleSession)

        self.SessionStatus = QLabel('OFF', self)
        self.SessionStatus.setGeometry(68, 22, 60, 20)
        self.SessionStatus.setStyleSheet("font: bold 12px; color: #8b1a1a")

        # ── RIGHT PANEL — Section labels ──────────────────────────────────────
        for text, geom in [
            ('Camera Selection', (1500,  20, 360, 30)),
            ('PTZ Speed',        (1500, 138, 360, 30)),
            ('Camera Presets',   (1500, 253, 360, 30)),
            ('Camera Controls',  (1500, 367, 360, 30)),
        ]:
            lbl = QLabel(text, self)
            lbl.setGeometry(*geom)
            lbl.setAlignment(QtCore.Qt.AlignCenter)
            lbl.setStyleSheet("font: bold 20px; color: black")

        # ── RIGHT PANEL — Camera Selection ────────────────────────────────────
        # Exclusive checkable buttons; only one can be active at a time.
        # Platform = Camera 1; Comments = Camera 2.
        # Shared style for all toggle-button pairs (Camera, Speed, Preset mode).
        _toggle_style = (
            "QPushButton{background-color: white; border: 3px solid green; "
            "font: bold 20px; color: black}"
            "QPushButton:Checked{background-color: green; font: bold 20px; color: white}"
        )

        self.Cam1 = QPushButton('Platform', self)
        self.Cam1.setGeometry(1500, 60, 180, 70)
        self.Cam1.setCheckable(True)
        self.Cam1.setAutoExclusive(True)
        self.Cam1.setChecked(True)
        self.Cam1.setToolTip('Select Platform Camera')
        self.Cam1.setStyleSheet(_toggle_style)

        self.Cam2 = QPushButton('Comments', self)
        self.Cam2.setGeometry(1680, 60, 180, 70)
        self.Cam2.setCheckable(True)
        self.Cam2.setAutoExclusive(True)
        self.Cam2.setToolTip('Select Comments Camera')
        self.Cam2.setStyleSheet(_toggle_style)

        self.Camgroup = QButtonGroup(self)
        self.Camgroup.addButton(self.Cam1)
        self.Camgroup.addButton(self.Cam2)

        self.Cam1.clicked.connect(self._update_backlight_ui)
        self.Cam2.clicked.connect(self._update_backlight_ui)

        # ── RIGHT PANEL — PTZ Speed Slider ───────────────────────────────────
        # Replaces the old SLOW/FAST toggle buttons with a continuous slider.
        # The slider value maps directly to the VISCA speed byte (1-18).
        # Zoom speed (nibble 0-7) is derived proportionally via _get_zoom_speed().
        #
        # Visual layout inside the 360 px-wide right panel (x 1500-1860):
        #
        #   x=1500        x=1560                  x=1790  x=1860
        #     SLOW  |====== green slider track ======|  FAST
        #                   Speed: 8  (medium)

        SlowLabel = QLabel('SLOW', self)
        SlowLabel.setGeometry(1500, 190, 55, 20)
        SlowLabel.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        SlowLabel.setStyleSheet("font: bold 13px; color: #444")

        self.SpeedSlider = QSlider(Qt.Horizontal, self)
        self.SpeedSlider.setGeometry(1560, 172, 230, 48)
        self.SpeedSlider.setMinimum(SPEED_MIN)
        self.SpeedSlider.setMaximum(SPEED_MAX)
        self.SpeedSlider.setValue(SPEED_DEFAULT)
        self.SpeedSlider.setTickPosition(QSlider.TicksBelow)
        self.SpeedSlider.setTickInterval(3)
        self.SpeedSlider.setToolTip(
            f'Drag to set PTZ speed  ({SPEED_MIN} = slowest  /  {SPEED_MAX} = fastest)'
        )
        self.SpeedSlider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 8px; background: #cccccc; border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #1a7a1a; border: 2px solid #0d4d0d;
                width: 24px; height: 24px; margin: -9px 0; border-radius: 12px;
            }
            QSlider::sub-page:horizontal {
                background: #4caf50; border-radius: 4px;
            }
        """)

        FastLabel = QLabel('FAST', self)
        FastLabel.setGeometry(1797, 190, 55, 20)
        FastLabel.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        FastLabel.setStyleSheet("font: bold 13px; color: #444")

        self.SpeedValueLabel = QLabel(self._speed_label_text(SPEED_DEFAULT), self)
        self.SpeedValueLabel.setGeometry(1500, 224, 360, 20)
        self.SpeedValueLabel.setAlignment(QtCore.Qt.AlignCenter)
        self.SpeedValueLabel.setStyleSheet("font: 12px; color: #555")

        self.SpeedSlider.valueChanged.connect(self._on_speed_changed)


        # ── RIGHT PANEL — Section labels ──────────────────────────────────────
        for text, geom in [
            ('Camera Selection',  (1500,  20, 360, 30)),
            ('PTZ Speed',         (1500, 138, 360, 30)),
            ('Camera Presets',    (1500, 253, 360, 30)),
            ('Camera Controls',   (1500, 367, 360, 30)),
        ]:
            lbl = QLabel(text, self)
            lbl.setGeometry(*geom)
            lbl.setAlignment(QtCore.Qt.AlignCenter)
            lbl.setStyleSheet("font: bold 20px; color:black")
            
        # ── RIGHT PANEL — Preset mode (Call / Set) ───────────────────────────
        # "Call" = recall a stored preset position.
        # "Set"  = overwrite a preset with the camera's current position.
        self.BtnCall = QPushButton('Call', self)
        self.BtnCall.setGeometry(1500, 290, 180, 70)
        self.BtnCall.setCheckable(True)
        self.BtnCall.setAutoExclusive(True)
        self.BtnCall.setChecked(True)
        self.BtnCall.setToolTip('Select Preset')
        self.BtnCall.setStyleSheet(_toggle_style)

        self.BtnSet = QPushButton('Set', self)
        self.BtnSet.setGeometry(1680, 290, 180, 70)
        self.BtnSet.setCheckable(True)
        self.BtnSet.setAutoExclusive(True)
        self.BtnSet.setToolTip('Record Preset')
        self.BtnSet.setStyleSheet(_toggle_style)

        PresetModeGroup = QButtonGroup(self)
        PresetModeGroup.addButton(self.BtnCall)
        PresetModeGroup.addButton(self.BtnSet)

        # ── RIGHT PANEL — Zoom buttons ────────────────────────────────────────
        ZoomIn = QPushButton(self)
        ZoomIn.setGeometry(1680, 403, 100, 100)
        ZoomIn.pressed.connect(self.ZoomIn)
        ZoomIn.released.connect(self.ZoomStop)
        ZoomIn.setStyleSheet("background-image: url(ZoomIn_120.png); border: none")

        ZoomOut = QPushButton(self)
        ZoomOut.setGeometry(1510, 403, 100, 100)
        ZoomOut.pressed.connect(self.ZoomOut)
        ZoomOut.released.connect(self.ZoomStop)
        ZoomOut.setStyleSheet("background-image: url(ZoomOut_120.png); border: none")

        # ── RIGHT PANEL — Arrow / direction buttons ───────────────────────────
        # Each arrow button sends a continuous pan/tilt VISCA command on press
        # and a Stop command on release.  _arrow_btn() builds a 100×100 px
        # transparent button with a rotated copy of angle.png as its icon.
        # The rotation angle (degrees) determines which direction the arrow points.
        for x, y, deg, handler in [
            (1500, 510, 135, self.UpLeft),   (1605, 510, 180, self.Up),
            (1710, 510, 225, self.UpRight),  (1500, 617,  90, self.Left),
            (1710, 617, 270, self.Right),    (1500, 724,  45, self.DownLeft),
            (1605, 724,   0, self.Down),     (1710, 724, 315, self.DownRight),
        ]:
            btn = self._arrow_btn(x, y, deg)
            btn.pressed.connect(handler)
            btn.released.connect(self.Stop)

        Home = QPushButton('', self)
        Home.setGeometry(1605, 617, 100, 100)
        Home.clicked.connect(self.HomeButton)
        Home.setStyleSheet("background-image: url(home.png); border: none")

        # ── RIGHT PANEL — Focus & Exposure ────────────────────────────────────
        FocusExposureLabel = QLabel('Focus & Exposure', self)
        FocusExposureLabel.setGeometry(1500, 835, 360, 25)
        FocusExposureLabel.setAlignment(QtCore.Qt.AlignCenter)
        FocusExposureLabel.setStyleSheet("font: bold 16px; color: black")

        _btn_style = (
            "QPushButton{background-color: white; border: 2px solid #555; "
            "font: bold 13px; color: black; border-radius: 4px}"
            "QPushButton:pressed{background-color: #ccc}"
        )

        # Focus row: Auto Focus keeps adjusting continuously; One Push AF focuses
        # once then returns to manual mode; Manual Focus locks focus completely.
        # Brightness row: each click shifts exposure by one VISCA step.
        # All five buttons share the same style and are built from a data table.
        for label, geom, tooltip, handler in [
            ('Auto\nFocus',   (1500, 863, 110, 50), 'Auto Focus ON',                    self.AutoFocus),
            ('One Push\nAF',  (1625, 863, 110, 50), 'One-shot autofocus, then manual',  self.OnePushAF),
            ('Manual\nFocus', (1750, 863, 110, 50), 'Manual Focus mode',                self.ManualFocus),
            ('▼ Darker',      (1500, 920, 110, 45), 'Decrease exposure one step',       self.BrightnessDown),
            ('▲ Brighter',    (1750, 920, 110, 45), 'Increase exposure one step',       self.BrightnessUp),
        ]:
            btn = QPushButton(label, self)
            btn.setGeometry(*geom)
            btn.setToolTip(tooltip)
            btn.setStyleSheet(_btn_style)
            btn.clicked.connect(handler)

        self.BtnBacklight = QPushButton('Backlight\nOFF', self)
        self.BtnBacklight.setGeometry(1625, 920, 110, 45)
        self.BtnBacklight.setToolTip('Toggle backlight compensation (contraluz)')
        self._backlight_style_off = (
            "QPushButton{background-color: white; border: 2px solid #555; "
            "font: bold 13px; color: black; border-radius: 4px}"
        )
        self._backlight_style_on = (
            "QPushButton{background-color: #e6a800; border: 2px solid #b37f00; "
            "font: bold 13px; color: white; border-radius: 4px}"
        )
        self.BtnBacklight.setStyleSheet(self._backlight_style_off)
        self.BtnBacklight.clicked.connect(self.BacklightToggle)

        # ── Config / status buttons (bottom of right panel) ───────────────────
        Cam1Address = QPushButton('Platform [Platform]  -  ' + IPAddress, self)
        Cam1Address.setGeometry(1500, 975, 310, 22)
        Cam1Address.setStyleSheet("font: bold 15px; color:" + Cam1Check)
        Cam1Address.clicked.connect(self.PTZ1Address)

        self._cam2_addr_btn = QPushButton('Comments [Audience]  -  ' + IPAddress2, self)
        self._cam2_addr_btn.setGeometry(1500, 995, 310, 22)
        self._cam2_addr_btn.setStyleSheet("font: bold 15px; color:" + Cam2Check)
        self._cam2_addr_btn.clicked.connect(self.PTZ2Address)

        self._ptz1_id_btn = QPushButton(' ID-' + Cam1ID, self)
        self._ptz1_id_btn.setGeometry(1815, 975, 45, 22)
        self._ptz1_id_btn.setStyleSheet("font: bold 15px; color:" + Cam1Check)
        self._ptz1_id_btn.clicked.connect(self.PTZ1IDchange)

        self._ptz2_id_btn = QPushButton(' ID-' + Cam2ID, self)
        self._ptz2_id_btn.setGeometry(1815, 995, 45, 22)
        self._ptz2_id_btn.setStyleSheet("font: bold 15px; color:" + Cam2Check)
        self._ptz2_id_btn.clicked.connect(self.PTZ2IDchange)

        # Version label
        VersionLabel = QLabel('v2 — IP RPI — March 2026', self)
        VersionLabel.setGeometry(1500, 1022, 360, 20)
        VersionLabel.setAlignment(QtCore.Qt.AlignCenter)
        VersionLabel.setStyleSheet("font: 12px; color: grey")

        Version = QPushButton('Close window', self)
        Version.setGeometry(1500, 1050, 310, 22)
        Version.setStyleSheet("background-color: lightgrey; font: 15px; color: black; border: none")
        Version.clicked.connect(self.Quit)

        Help = QPushButton('?', self)
        Help.setGeometry(1815, 1050, 45, 22)
        Help.setStyleSheet("background-color: lightgrey; font: 15px; color: black; border: none")
        Help.clicked.connect(self.HelpMsg)

    # -------------------------------------------------------------------------
    #  Speed helpers
    # -------------------------------------------------------------------------

    def _speed_label_text(self, value):
        """Build the human-readable string shown below the speed slider."""
        mid = (SPEED_MIN + SPEED_MAX) / 2
        if value <= SPEED_MIN:
            desc = "minimum"
        elif value >= SPEED_MAX:
            desc = "maximum"
        elif value < mid - 2:
            desc = "slow"
        elif value > mid + 2:
            desc = "fast"
        else:
            desc = "medium"
        return f"Speed: {value}  ({desc})"

    def _on_speed_changed(self, value):
        """Slot connected to SpeedSlider.valueChanged."""
        self.SpeedValueLabel.setText(self._speed_label_text(value))

    def _get_speed(self):
        """Return the current pan/tilt speed as an integer in [SPEED_MIN, SPEED_MAX]."""
        return self.SpeedSlider.value()

    def _get_zoom_speed(self):
        """Map the pan/tilt slider to a zoom speed nibble (1-7) via linear interpolation."""
        raw = round(self.SpeedSlider.value() * 7 / SPEED_MAX)
        return max(1, min(7, raw))

    # -------------------------------------------------------------------------
    #  UI helpers
    # -------------------------------------------------------------------------

    def _arrow_btn(self, x, y, degrees):
        """Create a 100x100 transparent push-button with a rotated arrow icon."""
        btn = QPushButton(self)
        btn.setGeometry(x, y, 100, 100)
        btn.setStyleSheet("border: none; background: transparent")
        pix = QPixmap("angle.png").transformed(
            QtGui.QTransform().rotate(degrees), Qt.SmoothTransformation
        )
        btn.setIcon(QtGui.QIcon(pix))
        btn.setIconSize(QtCore.QSize(90, 90))
        return btn

    def _update_backlight_ui(self):
        """Refresh the Backlight button's label and colour for the active camera."""
        cam_key = 1 if self.Cam1.isChecked() else 2
        if self.backlight_on[cam_key]:
            self.BtnBacklight.setText('Backlight\nON')
            self.BtnBacklight.setStyleSheet(self._backlight_style_on)
        else:
            self.BtnBacklight.setText('Backlight\nOFF')
            self.BtnBacklight.setStyleSheet(self._backlight_style_off)

    # -------------------------------------------------------------------------
    #  Core VISCA send helper
    # -------------------------------------------------------------------------

    def _send_cmd(self, ip, cam_id_hex, cmd_suffix):
        """
        Open a TCP connection to the camera, send one VISCA command, read
        the acknowledgement, and close the socket.  Runs synchronously —
        the caller blocks until the network round-trip completes or times out.

        Use this for commands where knowing the outcome matters (presets,
        session power, focus, brightness).  Use _send_cmd_async() for
        continuous movement/zoom where speed matters more than confirmation.

        Args:
            ip          : Camera IP address string (e.g. "172.16.1.11")
            cam_id_hex  : Camera VISCA device ID as a hex string (e.g. "81")
            cmd_suffix  : Hex string for the command body after the device ID
                          (e.g. "01040722ff" for Zoom Tele slow)

        Returns:
            True  on success
            False on any network or OS error (caller may show an error dialog)
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(SOCKET_TIMEOUT)
                s.connect((ip, 5678))
                s.send(binascii.unhexlify(cam_id_hex + cmd_suffix))
                s.recv(64)   # VISCA ACK is at most 16 bytes; discard it
            return True
        except (socket.timeout, socket.error, OSError):
            return False

    def _send_cmd_async(self, ip, cam_id_hex, cmd_suffix):
        """
        Fire-and-forget version of _send_cmd: spawns a daemon thread so the
        UI stays responsive during continuous movement and zoom.
        No error feedback — if the command fails the camera simply won't move.
        """
        threading.Thread(
            target=self._send_cmd, args=(ip, cam_id_hex, cmd_suffix),
            daemon=True
        ).start()

    def _active_cam(self):
        """Return (ip, cam_id) for whichever camera is currently selected."""
        if self.Cam1.isChecked():
            return IPAddress, Cam1ID
        return IPAddress2, Cam2ID


    # ─────────────────────────────────────────────────────────────────────────
    #  Speed helpers (used by _move, ZoomIn, ZoomOut)
    # ─────────────────────────────────────────────────────────────────────────

    def _get_speed(self) -> int:
        """Return the current slider speed value in [SPEED_MIN, SPEED_MAX]."""
        return self.SpeedSlider.value()

    def _get_zoom_speed(self) -> int:
        """
        Map the pan/tilt slider range (1-18) to a VISCA zoom nibble (1-7).
        VISCA zoom speed nibble: 0 = stopped, 1 = slowest, 7 = fastest.
        We clamp to 1 minimum so a very slow pan still produces a visible zoom.
        """
        return max(1, min(7, round(self.SpeedSlider.value() * 7 / SPEED_MAX)))

    def _speed_label_text(self, value: int) -> str:
        """Build the descriptive text shown under the speed slider."""
        mid = (SPEED_MIN + SPEED_MAX) / 2
        if value <= SPEED_MIN:
            desc = "minimum"
        elif value >= SPEED_MAX:
            desc = "maximum"
        elif value < mid - 2:
            desc = "slow"
        elif value > mid + 2:
            desc = "fast"
        else:
            desc = "medium"
        return f"Speed: {value}  ({desc})"

    def _on_speed_changed(self, value: int):
        """Slot: update the numeric label whenever the slider moves."""
        self.SpeedValueLabel.setText(self._speed_label_text(value))

    # -------------------------------------------------------------------------

    # ─────────────────────────────────────────────────────────────────────────
    #   ErrorCapture() shows a generic
    #  warning so the operator knows something went wrong; ErrorCapture1/2
    #  continue to show camera-specific messages with the expected IP address.
    # ─────────────────────────────────────────────────────────────────────────

    def ErrorCapture(self):
        QMessageBox.warning(self, 'Camera Control Error',
                            'A network error occurred. Check camera connections.')

    def ErrorCapture1(self):
        QMessageBox.warning(self, 'Platform PTZ Control',
                            f'Check that the Platform Camera IP Address is set to '
                            f'"{IPAddress}" and ID 1.')

    def ErrorCapture2(self):
        QMessageBox.warning(self, 'Comments PTZ Control',
                            f'Check that the Comments Camera IP Address is set to '
                            f'"{IPAddress2}" and ID 2.')

    # ─────────────────────────────────────────────────────────────────────────

    #  SESSION MANAGEMENT
    # -------------------------------------------------------------------------

    def ToggleSession(self):
        """
        Toggle the broadcast session ON or OFF.

        ON path:
          1. Sets the flag, disables the button to prevent double-clicks.
          2. Sends VISCA Power-ON to both cameras.
          3. After 8 seconds (QTimer) moves both cameras to Home and re-enables.

        OFF path:
          1. Asks for confirmation.
          2. Sends VISCA Standby to both cameras.
          3. Resets the button to its red / OFF appearance.
        """
        if not self.session_active:
            self.session_active = True
            self.BtnSession.setEnabled(False)
            self.BtnSession.setStyleSheet(
                "QPushButton{background-color: #555; border: 2px solid #333; "
                "font: bold 26px; color: #aaa; border-radius: 25px}"
            )
            self.SessionStatus.setText('Starting...')
            self.SessionStatus.setStyleSheet("font: bold 12px; color: #888")
            self._send_cmd(IPAddress,  Cam1ID, "01040002FF")
            self._send_cmd(IPAddress2, Cam2ID, "01040002FF")
            QtCore.QTimer.singleShot(8000, self._session_home)

        else:
            reply = QMessageBox.question(
                self, 'End Session',
                'Power off both cameras and end the session?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self._send_cmd(IPAddress,  Cam1ID, "01040003FF")
                self._send_cmd(IPAddress2, Cam2ID, "01040003FF")
                self.session_active = False
                self.BtnSession.setStyleSheet(
                    "QPushButton{background-color: #8b1a1a; border: 2px solid #5a0d0d; "
                    "font: bold 26px; color: white; border-radius: 25px}"
                    "QPushButton:pressed{background-color: #5a0d0d}"
                )
                self.BtnSession.setToolTip('Start Session: Power ON both cameras and go Home')
                self.SessionStatus.setText('OFF')
                self.SessionStatus.setStyleSheet("font: bold 12px; color: #8b1a1a")

    def _session_home(self):
        """
        Called 8 seconds after session start (via QTimer.singleShot).
        Sends both cameras to their Home position and marks the session fully ON.
        """
        self._send_cmd(IPAddress,  Cam1ID, "010604FF")
        self._send_cmd(IPAddress2, Cam2ID, "010604FF")
        self.BtnSession.setStyleSheet(
            "QPushButton{background-color: #1a7a1a; border: 2px solid #0d4d0d; "
            "font: bold 26px; color: white; border-radius: 25px}"
            "QPushButton:pressed{background-color: #0d4d0d}"
        )
        self.BtnSession.setToolTip('End Session: Power OFF (standby) both cameras')
        self.BtnSession.setEnabled(True)
        self.SessionStatus.setText('ON')
        self.SessionStatus.setStyleSheet("font: bold 12px; color: #1a7a1a")

    # -------------------------------------------------------------------------
    #  FOCUS CONTROLS
    # -------------------------------------------------------------------------

    def AutoFocus(self):
        """Enable continuous autofocus.  VISCA: <id> 01 04 38 02 FF"""
        ip, cam_id = self._active_cam()
        if not self._send_cmd(ip, cam_id, "01043802FF"):
            self.ErrorCapture()

    def ManualFocus(self):
        """Lock to manual focus mode.  VISCA: <id> 01 04 38 03 FF"""
        ip, cam_id = self._active_cam()
        if not self._send_cmd(ip, cam_id, "01043803FF"):
            self.ErrorCapture()

    def OnePushAF(self):
        """Trigger one AF cycle then stay in manual.  VISCA: <id> 01 04 18 01 FF"""
        ip, cam_id = self._active_cam()
        if not self._send_cmd(ip, cam_id, "01041801FF"):
            self.ErrorCapture()

    # -------------------------------------------------------------------------
    #  EXPOSURE CONTROLS
    # -------------------------------------------------------------------------

    def BrightnessUp(self):
        """Increase exposure compensation one step.  VISCA: <id> 01 04 0D 02 FF"""
        ip, cam_id = self._active_cam()
        if not self._send_cmd(ip, cam_id, "01040D02FF"):
            self.ErrorCapture()

    def BrightnessDown(self):
        """Decrease exposure compensation one step.  VISCA: <id> 01 04 0D 03 FF"""
        ip, cam_id = self._active_cam()
        if not self._send_cmd(ip, cam_id, "01040D03FF"):
            self.ErrorCapture()

    def BacklightToggle(self):
        """
        Toggle backlight compensation (contraluz) for the active camera.
        Use this when the subject is lit from behind (e.g. a window behind them)
        and the camera is silhouetting them.

        Backlight ON  → VISCA: <id>01043302FF
        Backlight OFF → VISCA: <id>01043303FF

        State is tracked individually per camera (self.backlight_on dict) so
        switching between Platform and Comments shows the correct label/colour.
        The state is only updated if the network command succeeds.
        """
        ip, cam_id = self._active_cam()
        cam_key = 1 if ip == IPAddress else 2   # derived from ip — no second isChecked() call
        if self.backlight_on[cam_key]:
            self._send_cmd(ip, cam_id, "01043303FF")
            self.backlight_on[cam_key] = False
        else:
            self._send_cmd(ip, cam_id, "01043302FF")
            self.backlight_on[cam_key] = True
        self._update_backlight_ui()

    # -------------------------------------------------------------------------
    #  CAMERA MOVEMENT
    #
    #  VISCA Pan-Tilt Drive format:
    #      <id> 01 06 01 <pan_spd> <tilt_spd> <pan_dir> <tilt_dir> FF
    #
    #  Direction nibbles:
    #      Pan:  01 = left   02 = right   03 = stop
    #      Tilt: 01 = up     02 = down    03 = stop
    # -------------------------------------------------------------------------

    def HomeButton(self):

        """Move the active camera to its factory Home position."""
        ip, cam_id = self._active_cam()
        self._send_cmd_async(ip, cam_id, "010604FF")

    def _move(self, pan_dir: int, tilt_dir: int):
        """
        Send a continuous pan/tilt VISCA command using the current slider speed.

        Move camera to its factory Home position.  VISCA: <id> 01 06 04 FF"""
        ip, cam_id = self._active_cam()
        self._send_cmd_async(ip, cam_id, "010604FF")

    def _move(self, pan_dir, tilt_dir):
        """Send a VISCA Pan-Tilt Drive command for any direction."""
        ip, cam_id = self._active_cam()
        spd = self._get_speed()
        pan_spd  = 0 if pan_dir  == 0x03 else spd
        tilt_spd = 0 if tilt_dir == 0x03 else spd
        self._send_cmd(ip, cam_id,
            f"010601{pan_spd:02X}{tilt_spd:02X}{pan_dir:02X}{tilt_dir:02X}FF")

    def Up(self):        self._move(0x03, 0x01)
    def Down(self):      self._move(0x03, 0x02)
    def Left(self):      self._move(0x01, 0x03)
    def Right(self):     self._move(0x02, 0x03)
    def UpLeft(self):    self._move(0x01, 0x01)
    def UpRight(self):   self._move(0x02, 0x01)
    def DownLeft(self):  self._move(0x01, 0x02)
    def DownRight(self): self._move(0x02, 0x02)

    """ VISCA Pan-Tilt Drive format:
            <id> 01 06 01 <pan_spd> <tilt_spd> <pan_dir> <tilt_dir> FF

            pan_dir:  0x01=left  0x02=right  0x03=stop (no pan)
            tilt_dir: 0x01=up    0x02=down   0x03=stop (no tilt)

            When direction is "stop" (0x03) the corresponding speed byte is set to 0
            so VISCA doesn't try to apply a speed to a stopped axis.
            Runs asynchronously so the UI stays responsive while the button is held.
            """
    

    def UpLeft(self):    self._move(0x01, 0x01)
    def Up(self):        self._move(0x03, 0x01)
    def UpRight(self):   self._move(0x02, 0x01)
    def Left(self):      self._move(0x01, 0x03)
    def Right(self):     self._move(0x02, 0x03)
    def DownLeft(self):  self._move(0x01, 0x02)
    def Down(self):      self._move(0x03, 0x02)
    def DownRight(self): self._move(0x02, 0x02)

    def Stop(self):
        """Stop all pan/tilt movement.  Sent automatically when an arrow button is released."""

    def Stop(self):
        """Stop all pan/tilt movement.  VISCA: <id> 01 06 01 00 00 03 03 FF"""

        ip, cam_id = self._active_cam()
        self._send_cmd_async(ip, cam_id, "01060100000303FF")

    # -- Zoom -----------------------------------------------------------------

    def ZoomIn(self):

        """
        Zoom in (tele) at the current slider speed.
        VISCA Zoom Tele: <id> 01 04 07 <speed_byte> FF
        speed_byte = 0x2n where n = zoom nibble 1-7 (0x20 | nibble).
        """
        ip, cam_id = self._active_cam()
        self._send_cmd_async(ip, cam_id, f"010407{0x20 | self._get_zoom_speed():02X}FF")

    def ZoomOut(self):
        """
        Zoom out (wide) at the current slider speed.
        VISCA Zoom Wide: <id> 01 04 07 <speed_byte> FF
        speed_byte = 0x3n where n = zoom nibble 1-7 (0x30 | nibble).
        """
        ip, cam_id = self._active_cam()
        self._send_cmd_async(ip, cam_id, f"010407{0x30 | self._get_zoom_speed():02X}FF")

    def ZoomStop(self):
        """Stop zoom movement.  Sent automatically when a zoom button is released."""

        """Start zooming in (tele) at a speed proportional to the slider."""
        ip, cam_id = self._active_cam()
        zspd = self._get_zoom_speed()
        self._send_cmd(ip, cam_id, f"010407{0x20 | zspd:02X}FF")

    def ZoomOut(self):
        """Start zooming out (wide) at a speed proportional to the slider."""
        ip, cam_id = self._active_cam()
        zspd = self._get_zoom_speed()
        self._send_cmd(ip, cam_id, f"010407{0x30 | zspd:02X}FF")

    def ZoomStop(self):
        """Stop zoom movement.  VISCA: <id> 01 04 07 00 FF"""

        ip, cam_id = self._active_cam()
        self._send_cmd(ip, cam_id, "01040700FF")

    # -------------------------------------------------------------------------
    #  PRESET HANDLER — All seat buttons (presets 1-129)
    #
    #  Go1/Go2/Go3 always target Camera 1 regardless of the Camera Selection
    #  panel — these positions are only meaningful for the platform-facing camera.
    # ─────────────────────────────────────────────────────────────────────────

    def _go_platform_preset(self, preset_num, title):
        """
        Call or set one of the three fixed platform presets (presets 1-3).
        These always target Camera 1 — the platform-facing camera — because the
        Chairman, Left, and Right positions are only meaningful on that camera.

        VISCA Recall: <id> 01 04 3F 02 <preset_hex> FF
        VISCA Set:    <id> 01 04 3F 01 <preset_hex> FF
        """
        preset_hex = PRESET_MAP[preset_num]   # 1-3 are always in range; no check needed
        if self.BtnCall.isChecked():
            self._send_cmd(IPAddress, Cam1ID, f"01043f02{preset_hex}ff")
        elif self.BtnSet.isChecked():
            reply = QMessageBox.question(self, f'Record {title}', "Are You Sure?",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self._send_cmd(IPAddress, Cam1ID, f"01043f01{preset_hex}ff")

    def Go1(self): self._go_platform_preset(1, 'Chairman Position')
    def Go2(self): self._go_platform_preset(2, 'Platform Left')
    def Go3(self): self._go_platform_preset(3, 'Platform Right')

    # ─────────────────────────────────────────────────────────────────────────
    #  PRESET HANDLER — Seat buttons (presets 4-128, respects camera selection)
    # ─────────────────────────────────────────────────────────────────────────

    def go_to_preset(self, preset_number):
        """
        Call or set a preset on the active camera.

        Call mode (Set1 checked):
            VISCA Recall: <id> 01 04 3F 02 <preset_hex> FF
        Set mode (Set2 checked):
            VISCA Set:    <id> 01 04 3F 01 <preset_hex> FF
        """
        preset_hex = PRESET_MAP.get(preset_number)
        if not preset_hex:
            return

        if preset_number in (1, 2, 3):
            ip, cam_id = IPAddress, Cam1ID
            cam_name = 'Platform'
        else:
            ip, cam_id = self._active_cam()
            cam_name = 'Platform' if self.Cam1.isChecked() else 'Comments'

        if self.BtnCall.isChecked():
            # Call (recall): move camera to the stored position for this preset
            self._send_cmd(ip, cam_id, f"01043f02{preset_hex}ff")

        elif self.BtnSet.isChecked():
            # Set (record): overwrite the preset with the camera's current position.
            # Confirmation dialog prevents accidental overwrites during a live event.
            cam_name = "Platform" if self.Cam1.isChecked() else "Comments"
            reply = QMessageBox.question(
                self, f'Record Preset {preset_number} ({cam_name})',
                "Are you sure you want to record this preset?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self._send_cmd(ip, cam_id, f"01043f01{preset_hex}ff")

    # -------------------------------------------------------------------------
    #  CONFIG DIALOGS — change IP / VISCA ID at runtime without editing files
    # -------------------------------------------------------------------------

    def _change_ip(self, cam_num):
        """
        Show a dialog to change the IP address of Camera 1 or 2.
        After saving, the app restarts via os.execv() so the new IP is picked
        up cleanly — reloading config in-place would be complex and error-prone
        because IPAddress/IPAddress2 are module-level constants read at import time.
        """
        cam_name = 'Platform' if cam_num == 1 else 'Comments'
        current  = IPAddress if cam_num == 1 else IPAddress2
        filename = 'PTZ1IP.txt' if cam_num == 1 else 'PTZ2IP.txt'
        title    = f'{cam_name} PTZ Control'
        if QMessageBox.warning(self, title,
                               f'Do you want to change the IP address used to control the {cam_name} camera?',
                               QMessageBox.Ok, QMessageBox.Cancel) != QMessageBox.Ok:
            return
        text, ok = QInputDialog.getText(self, title,
                                        f'New IP address for {cam_name} Camera  (current: {current}):',
                                        text=current)
        if ok and text:
            if not _is_valid_ip(text):
                QMessageBox.warning(self, 'Invalid IP Address',
                                    f'"{text}" is not a valid IPv4 address.\n'
                                    'Please enter four numbers separated by dots (e.g. 172.16.1.11).')
                return
            with open(filename, "w") as f:
                f.write(text.strip())
            os.execv(sys.executable, [sys.executable] + sys.argv)

    def _change_cam_id(self, cam_num):
        """
        Show a dialog to change the VISCA device ID of Camera 1 or 2.
        The ID must be a valid hex string (e.g. "81").  An invalid value would
        cause binascii.Error at the next startup when VISCA commands are built.
        Saves to the config file and restarts the app (same reason as _change_ip).
        """
        cam_name = 'Platform' if cam_num == 1 else 'Comments'
        current  = Cam1ID if cam_num == 1 else Cam2ID
        filename = 'Cam1ID.txt' if cam_num == 1 else 'Cam2ID.txt'
        title    = f'{cam_name} PTZ Control'
        if QMessageBox.warning(self, title,
                               f'Do you want to change the VISCA ID used to control the {cam_name} camera?',
                               QMessageBox.Ok, QMessageBox.Cancel) != QMessageBox.Ok:
            return
        text, ok = QInputDialog.getText(self, title,
                                        f'New VISCA ID for {cam_name} Camera  (current: {current}):',
                                        text=current)
        if ok and text:
            if not _is_valid_cam_id(text):
                QMessageBox.warning(self, 'Invalid Camera ID',
                                    f'"{text}" is not a valid hexadecimal ID.\n'
                                    'Please enter a hex value such as "81" or "82".')
                return
            with open(filename, "w") as f:
                f.write(text.strip())
            os.execv(sys.executable, [sys.executable] + sys.argv)


        """Generic dialog to change the IP address of Camera 1 or 2.
        Validates, saves to the appropriate config file, and restarts.
        """
        cam_name = 'Platform' if cam_num == 1 else 'Comments'
        title    = f'{cam_name} PTZ Control'
        current  = IPAddress if cam_num == 1 else IPAddress2
        filename = 'PTZ1IP.txt' if cam_num == 1 else 'PTZ2IP.txt'
        result = QMessageBox.warning(
            self, title,
            f'Do you want to change the IP address for the {cam_name} camera?',
            QMessageBox.Ok, QMessageBox.Cancel
        )
        if result == QMessageBox.Ok:
            text, ok = QInputDialog.getText(
                self, title,
                f'New IP address for {cam_name} Camera  (current: {current}):',
                text=current
            )
            if ok and text:
                if not _is_valid_ip(text):
                    QMessageBox.warning(self, 'Invalid IP Address',
                                        f'"{text}" is not a valid IPv4 address.\n'
                                        'Enter four numbers 0-255 separated by dots.')
                    return
                with open(filename, 'w') as f:
                    f.write(text.strip())

                os.execv(sys.executable, [sys.executable] + sys.argv)

    def _change_cam_id(self, cam_num):
        """
        Generic dialog to change the VISCA device ID of Camera 1 or 2.
        Validates hex format, saves to config file, and restarts.
        """
        cam_name = 'Platform' if cam_num == 1 else 'Comments'
        title    = f'{cam_name} PTZ Control'
        current  = Cam1ID if cam_num == 1 else Cam2ID
        filename = 'Cam1ID.txt' if cam_num == 1 else 'Cam2ID.txt'
        result = QMessageBox.warning(
            self, title,
            f'Do you want to change the VISCA ID for the {cam_name} camera?',
            QMessageBox.Ok, QMessageBox.Cancel
        )
        if result == QMessageBox.Ok:
            text, ok = QInputDialog.getText(

                self, title,
                f'New VISCA ID for {cam_name} Camera  (current: {current}):',
                text=current
            )
            if ok and text:
                if not _is_valid_cam_id(text):
                    QMessageBox.warning(self, 'Invalid Camera ID',
                                        f'"{text}" is not valid hex (e.g. "81" or "82").')
                    return
                with open(filename, 'w') as f:
                    f.write(text.strip())
                os.execv(sys.executable, [sys.executable] + sys.argv)


    def PTZ1Address(self):  self._change_ip(1)
    def PTZ2Address(self):  self._change_ip(2)
    def PTZ1IDchange(self): self._change_cam_id(1)
    def PTZ2IDchange(self): self._change_cam_id(2)

    def Quit(self):
        """Close the application cleanly."""
        sys.exit()

    def HelpMsg(self):
        """Display the technical support contact loaded from Contact.txt."""
        QMessageBox.information(self, 'For Technical Assistance', Contact, QMessageBox.Ok)


# =============================================================================
#  GoButton -- compact numbered seat button
# =============================================================================

class GoButton(QPushButton):
    """
    A small (35×35 px) semi-transparent push-button used for seat preset numbers
    and the platform preset labels (Chairman, Left, Right).
    The nearly-transparent background lets the seating-plan image show through
    while still giving the button a visible hit area.
    """

    def __init__(self, text, parent=None):
        super().__init__(text, parent)   # QPushButton accepts text directly
        self.resize(35, 35)
        self.setStyleSheet(
            "background-color: rgba(0,0,0,10); border: 0px solid black; "
            "border-radius: 5px; font: 14px; font-weight: bold; color:" + ButtonColor
        )


# =============================================================================
#  Entry point
# =============================================================================

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    # Uncomment for production Raspberry Pi touchscreen:
    # window.showFullScreen()
    sys.exit(app.exec_())
