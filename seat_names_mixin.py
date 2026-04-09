#!/usr/bin/env python3
# seat_names_mixin.py — Mixin para asignación y persistencia de nombres en asientos
#
# Responsabilidad: todos los callbacks que responden a drag-drop de nombres,
# cambios CRUD en NamesPanel, y restauración de nombres persistidos al arrancar.
#
# Accede en runtime a atributos de MainWindow:
#   self._names_list, self._seat_names, self._chairman_presets
#   self._names_panel  (NamesPanel)
#   self._chairman_btn (ChairmanButton)
#   getattr(self, f"Seat{N}")  (GoButton / SpecialDragButton / ChairmanButton)

from config import save_names_data
from chairman_presets import save_chairman_presets
from widgets import GoButton, SpecialDragButton


class SeatNamesMixin:

    def _restore_seat_names(self):
        for seat_str, name in self._seat_names.items():
            btn = getattr(self, f"Seat{seat_str}", None)
            if isinstance(btn, (GoButton, SpecialDragButton)) and name:
                # emit_signal=False: no mueve cámara ni persiste al arrancar
                btn.set_name(name, emit_signal=False)
        self._sync_assigned_to_panel()

    def _on_seat_name_assigned(self, seat_number: int, name: str):
        key = str(seat_number)
        if name:
            # Exclusividad: un nombre solo puede estar en un asiento a la vez
            for other_key, other_name in list(self._seat_names.items()):
                if other_name == name and other_key != key:
                    other_btn = getattr(self, f"Seat{other_key}", None)
                    if isinstance(other_btn, (GoButton, SpecialDragButton)):
                        other_btn.set_name("", emit_signal=False)
                    del self._seat_names[other_key]
                    break
            self._seat_names[key] = name
        else:
            self._seat_names.pop(key, None)

        save_names_data(self._names_list, self._seat_names)
        self._sync_assigned_to_panel()

    def _on_names_list_changed(self, old_name: str = None, new_name: str = None):
        if old_name and new_name:
            for key, v in self._seat_names.items():
                if v == old_name:
                    self._seat_names[key] = new_name
                    btn = getattr(self, f"Seat{key}", None)
                    if isinstance(btn, (GoButton, SpecialDragButton)):
                        btn.set_name(new_name, emit_signal=False)

            # Migrar preset de Chairman si la persona renombrada tenía uno.
            if old_name in self._chairman_presets:
                self._chairman_presets[new_name] = self._chairman_presets.pop(old_name)
                save_chairman_presets(self._chairman_presets)

        save_names_data(self._names_list, self._seat_names)

    def _sync_assigned_to_panel(self):
        """Pasa al NamesPanel el set actualizado de nombres asignados."""
        self._names_panel.set_assigned(set(self._seat_names.values()))

    def _clear_all_seats(self):
        """Borra todos los nombres asignados de los asientos."""
        for key in list(self._seat_names.keys()):
            btn = getattr(self, f"Seat{key}", None)
            if isinstance(btn, (GoButton, SpecialDragButton)):
                btn.set_name("", emit_signal=False)
        self._seat_names.clear()
        save_names_data(self._names_list, self._seat_names)
        self._sync_assigned_to_panel()
