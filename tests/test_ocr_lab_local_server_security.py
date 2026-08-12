from __future__ import annotations

import unittest

from apps.ocr_lab.api.local_server_security import (
    require_local_host_header,
    require_loopback_host,
)


class OcrLabLocalServerSecurityTests(unittest.TestCase):
    def test_accepts_ipv4_ipv6_and_localhost_loopback(self) -> None:
        self.assertEqual("127.0.0.1", require_loopback_host("127.0.0.1"))
        self.assertEqual("::1", require_loopback_host("::1"))
        self.assertEqual("localhost", require_loopback_host("localhost"))

    def test_rejects_network_exposure(self) -> None:
        for host in ("0.0.0.0", "192.168.1.10", "ocr-lab.internal"):
            with self.subTest(host=host), self.assertRaises(ValueError):
                require_loopback_host(host)

    def test_accepts_loopback_host_headers_with_ports(self) -> None:
        self.assertEqual("localhost:8765", require_local_host_header("localhost:8765"))
        self.assertEqual("127.0.0.1:8765", require_local_host_header("127.0.0.1:8765"))
        self.assertEqual("[::1]:8765", require_local_host_header("[::1]:8765"))

    def test_rejects_non_local_host_headers(self) -> None:
        for host in ("attacker.example", "192.168.1.10:8765", "localhost:0"):
            with self.subTest(host=host), self.assertRaises(ValueError):
                require_local_host_header(host)


if __name__ == "__main__":
    unittest.main()
