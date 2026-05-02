#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. All rights reserved.
# Proprietary software — use, copying, distribution or modification requires written permission.
# domain/camera.py — Modelo de cámara PTZ

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Camera:
    index: int    # 1 = Platform, 2 = Comments
    ip: str
    cam_id: str   # hex VISCA address (e.g. "81")
    label: str    # "Platform" | "Comments"
