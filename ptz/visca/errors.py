#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. Todos los derechos reservados.
# ptz/visca/errors.py — Jerarquía de excepciones VISCA


class ViscaError(Exception):
    """Base para todos los errores VISCA."""


class ViscaNetworkError(ViscaError):
    """Error de red al enviar o recibir datos VISCA."""


class ViscaParseError(ViscaError):
    """Error al parsear una respuesta VISCA inesperada o malformada."""
