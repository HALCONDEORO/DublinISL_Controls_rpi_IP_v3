#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. Todos los derechos reservados.
# Software propietario y de uso privado exclusivo. Queda prohibida su copia,
# distribucion, modificacion o uso sin autorizacion escrita del autor.
"""
Tests unitarios para descubrimiento de camaras sin tocar la red real.
"""

from types import SimpleNamespace

import camera_discovery as cd


class TestCameraSubnet:

    def test_get_camera_subnet_uses_first_three_octets(self, monkeypatch):
        monkeypatch.setattr(cd, "CAM1", SimpleNamespace(ip="172.16.1.11"))

        assert cd.get_camera_subnet() == "172.16.1"

    def test_get_camera_subnet_falls_back_on_invalid_ip_shape(self, monkeypatch):
        monkeypatch.setattr(cd, "CAM1", SimpleNamespace(ip="not-an-ip"))

        assert cd.get_camera_subnet() == "172.16.1"


class TestArpScan:

    def test_arp_scan_parses_matching_unique_ips_and_skips_broadcast(self, monkeypatch):
        stdout = """
Interface: 172.16.1.10 --- 0x8
  Internet Address      Physical Address      Type
  172.16.1.11           aa-bb-cc-dd-ee-01     dynamic
  172.16.1.12           aa-bb-cc-dd-ee-02     dynamic
  172.16.1.12           aa-bb-cc-dd-ee-02     dynamic
  172.16.1.255          ff-ff-ff-ff-ff-ff     static
  10.0.0.5              aa-bb-cc-dd-ee-03     dynamic
"""

        def fake_run(*_args, **_kwargs):
            return SimpleNamespace(stdout=stdout)

        monkeypatch.setattr(cd.subprocess, "run", fake_run)

        assert cd.arp_scan("172.16.1") == ["172.16.1.11", "172.16.1.12"]

    def test_arp_scan_ignores_interface_headers_and_deduplicates(self, monkeypatch):
        stdout = """
Interface: 172.16.1.10 --- 0x8
  Internet Address      Physical Address      Type
  172.16.1.20           aa-bb-cc-dd-ee-20     dynamic
  172.16.1.20           aa-bb-cc-dd-ee-20     dynamic
Interface: 172.16.1.254 --- 0x9
  Internet Address      Physical Address      Type
  172.16.1.21           aa-bb-cc-dd-ee-21     dynamic
  172.16.2.22           aa-bb-cc-dd-ee-22     dynamic
"""

        monkeypatch.setattr(cd.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(stdout=stdout))

        assert cd.arp_scan("172.16.1") == ["172.16.1.20", "172.16.1.21"]
    def test_arp_scan_returns_empty_on_subprocess_error(self, monkeypatch):
        def fake_run(*_args, **_kwargs):
            raise OSError("arp unavailable")

        monkeypatch.setattr(cd.subprocess, "run", fake_run)

        assert cd.arp_scan("172.16.1") == []


class _FakeSocket:
    open_hosts = set()

    def __init__(self, *_args, **_kwargs):
        self.timeout = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def settimeout(self, timeout):
        self.timeout = timeout

    def connect_ex(self, address):
        host, _port = address
        return 0 if host in self.open_hosts else 1


class TestTcpScan:

    def test_tcp_scan_returns_sorted_open_hosts(self, monkeypatch):
        _FakeSocket.open_hosts = {"172.16.1.7", "172.16.1.3"}
        monkeypatch.setattr(cd.socket, "socket", _FakeSocket)

        assert cd.tcp_scan("172.16.1", workers=1, timeout=0.01) == ["172.16.1.3", "172.16.1.7"]


class TestDiscoverCameras:

    def test_discover_cameras_unions_tcp_and_arp_results(self, monkeypatch):
        monkeypatch.setattr(cd, "tcp_scan", lambda subnet: ["172.16.1.12", "172.16.1.11"])
        monkeypatch.setattr(cd, "arp_scan", lambda subnet: ["172.16.1.12", "172.16.1.13"])

        assert cd.discover_cameras("172.16.1") == ["172.16.1.11", "172.16.1.12", "172.16.1.13"]
