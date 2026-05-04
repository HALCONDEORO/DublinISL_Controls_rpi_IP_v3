#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. All rights reserved.
# Proprietary software — use, copying, distribution or modification requires written permission.
# tests/test_atem_dispatcher.py — Tests de la capa de seguridad/acciones ATEM

from __future__ import annotations

import sys
from unittest.mock import patch

from PyQt5.QtCore import QCoreApplication, Qt

if not QCoreApplication.instance():
    _app = QCoreApplication(sys.argv)

from atem_dispatcher import ATEMDispatcher
from atem_state import ATEMState


def _dispatcher(*, session_active: bool = True, mapping: dict[str, str] | None = None):
    with patch("atem_dispatcher._load_mapping", return_value=mapping or {"3->2": "comments_home"}):
        dispatcher = ATEMDispatcher(session_provider=lambda: session_active)
    actions: list[str] = []
    dispatcher.action_triggered.connect(actions.append, Qt.DirectConnection)
    return dispatcher, actions


class TestATEMDispatcherActions:
    def test_default_transition_only_triggers_on_3_to_2(self):
        cases = [
            ([3, 2], ["comments_home"]),
            ([1, 2], []),
            ([2, 2], []),
            ([3, 1, 2], []),
            ([2], []),
        ]

        for inputs, expected in cases:
            dispatcher, actions = _dispatcher()
            dispatcher.set_armed(True)

            for input_id in inputs:
                dispatcher.on_program_changed(input_id)

            assert actions == expected, inputs

    def test_explicit_input_mapping_still_triggers_on_entering_input(self):
        dispatcher, actions = _dispatcher(mapping={"2": "comments_home"})
        dispatcher.set_armed(True)

        dispatcher.on_program_changed(2)

        assert actions == ["comments_home"]

    def test_duplicate_input_is_deduplicated(self):
        dispatcher, actions = _dispatcher(mapping={"2": "comments_home"})
        dispatcher.set_armed(True)

        dispatcher.on_program_changed(2)
        dispatcher.on_program_changed(2)

        assert actions == ["comments_home"]

    def test_platform_home_action_is_emitted(self):
        dispatcher, actions = _dispatcher(mapping={"1": "platform_home"})
        dispatcher.set_armed(True)

        dispatcher.on_program_changed(1)

        assert actions == ["platform_home"]


class TestATEMDispatcherBlocks:
    def test_disarmed_blocks_actions(self):
        dispatcher, actions = _dispatcher(mapping={"2": "comments_home"})

        dispatcher.on_program_changed(2)

        assert actions == []

    def test_inactive_session_blocks_actions(self):
        dispatcher, actions = _dispatcher(session_active=False, mapping={"2": "comments_home"})
        dispatcher.set_armed(True)

        dispatcher.on_program_changed(2)

        assert actions == []

    def test_manual_cooldown_blocks_actions(self):
        dispatcher, actions = _dispatcher(mapping={"2": "comments_home"})
        dispatcher.set_armed(True)
        dispatcher.notify_manual_control()

        dispatcher.on_program_changed(2)

        assert actions == []

    def test_reconnect_guard_blocks_until_cleared(self):
        dispatcher, actions = _dispatcher()
        dispatcher.set_armed(True)
        dispatcher.mark_reconnecting()

        dispatcher.on_program_changed(3)
        dispatcher.on_program_changed(2)
        assert actions == []

        dispatcher.clear_reconnect_guard()
        dispatcher.reset_input_tracking()
        dispatcher.on_program_changed(3)
        dispatcher.on_program_changed(2)
        assert actions == ["comments_home"]

    def test_log_only_blocks_action_emission(self):
        dispatcher, actions = _dispatcher(mapping={"2": "comments_home"})
        dispatcher.set_armed(True)
        dispatcher.set_log_only(True)

        dispatcher.on_program_changed(2)

        assert actions == []


class TestATEMDispatcherState:
    def test_connected_with_known_previous_input_sets_reconnect_guard(self):
        dispatcher, actions = _dispatcher(mapping={"2": "comments_home"})
        dispatcher.set_armed(True)
        dispatcher.on_program_changed(1)

        dispatcher.on_atem_state_changed(ATEMState.CONNECTED)

        assert dispatcher.reconnect_guard is True
        dispatcher.on_program_changed(2)
        assert actions == []

    def test_reset_input_tracking_does_not_clear_reconnect_guard(self):
        dispatcher, _actions = _dispatcher()
        dispatcher.set_armed(True)
        dispatcher.mark_reconnecting()

        dispatcher.reset_input_tracking()

        assert dispatcher.reconnect_guard is True

    def test_mark_reconnecting_only_sets_guard_when_armed(self):
        dispatcher, _actions = _dispatcher()

        dispatcher.mark_reconnecting()
        assert dispatcher.reconnect_guard is False

        dispatcher.set_armed(True)
        dispatcher.mark_reconnecting()
        assert dispatcher.reconnect_guard is True

    def test_dry_run_reports_transition_action(self):
        dispatcher, _actions = _dispatcher()
        dispatcher.set_armed(True)
        dispatcher.on_program_changed(3)

        assert dispatcher.dry_run(2) == "Would trigger: comments_home"
