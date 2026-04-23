#!/usr/bin/env python3
# domain/seat.py — Modelo de asiento

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Seat:
    number: int
    x: int
    y: int
    name: Optional[str] = None
