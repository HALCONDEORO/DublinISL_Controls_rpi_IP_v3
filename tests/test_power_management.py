#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. All rights reserved.
# Proprietary software - use, copying, distribution or modification requires written permission.

from __future__ import annotations

import power_management


def test_disable_screen_blanking_skips_non_linux(monkeypatch):
    calls = []

    monkeypatch.setattr(power_management.platform, "system", lambda: "Windows")
    monkeypatch.setattr(power_management, "_run_quiet", lambda command: calls.append(command))

    power_management.disable_screen_blanking()

    assert calls == []


def test_disable_screen_blanking_uses_xset_on_linux_x11(monkeypatch):
    calls = []

    monkeypatch.setattr(power_management.platform, "system", lambda: "Linux")
    monkeypatch.setattr(power_management.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(power_management, "_run_quiet", lambda command: calls.append(command))

    power_management.disable_screen_blanking()

    assert calls == [
        ["/usr/bin/xset", "s", "off"],
        ["/usr/bin/xset", "-dpms"],
        ["/usr/bin/xset", "s", "noblank"],
    ]
