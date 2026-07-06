from __future__ import annotations

import ssl
import unittest
from unittest.mock import Mock, patch

from trade_signal_app.ssl_compat import create_default_ssl_context


class SSLCompatTests(unittest.TestCase):
    def setUp(self) -> None:
        create_default_ssl_context.cache_clear()

    def tearDown(self) -> None:
        create_default_ssl_context.cache_clear()

    def test_uses_certifi_when_default_cafile_is_missing(self) -> None:
        verify_paths = Mock(cafile=None, openssl_cafile="/tmp/missing-cert.pem")
        context = object()
        with patch("trade_signal_app.ssl_compat.ssl.get_default_verify_paths", return_value=verify_paths):
            with patch("trade_signal_app.ssl_compat.Path.exists", return_value=False):
                with patch("trade_signal_app.ssl_compat.certifi.where", return_value="/tmp/certifi.pem"):
                    with patch("trade_signal_app.ssl_compat.ssl.create_default_context", return_value=context) as factory:
                        result = create_default_ssl_context()

        self.assertIs(result, context)
        factory.assert_called_once_with(cafile="/tmp/certifi.pem")

    def test_uses_system_default_context_when_cafile_exists(self) -> None:
        verify_paths = Mock(cafile="/tmp/system.pem", openssl_cafile="/tmp/system.pem")
        context = object()
        with patch("trade_signal_app.ssl_compat.ssl.get_default_verify_paths", return_value=verify_paths):
            with patch("trade_signal_app.ssl_compat.Path.exists", return_value=True):
                with patch("trade_signal_app.ssl_compat.ssl.create_default_context", return_value=context) as factory:
                    result = create_default_ssl_context()

        self.assertIs(result, context)
        factory.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
