# SPDX-License-Identifier: Apache-2.0
"""Downloads on a Python without a certificate store retry once with the system bundle, still verified."""
import ssl
import unittest
import urllib.error
from unittest import mock

from maris3d import net


class NetTest(unittest.TestCase):
    def test_retry_with_verifying_context_on_cert_error(self):
        err = urllib.error.URLError(ssl.SSLCertVerificationError("CERTIFICATE_VERIFY_FAILED"))
        calls = []

        def fake(url, timeout=60, context=None):
            calls.append(context)
            if context is None:
                raise err
            return "ok"
        with mock.patch.object(net.urllib.request, "urlopen", fake):
            self.assertEqual(net.urlopen("https://example.invalid/x"), "ok")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1].verify_mode, ssl.CERT_REQUIRED)

    def test_other_errors_are_not_retried(self):
        calls = []

        def fake(url, timeout=60, context=None):
            calls.append(context)
            raise urllib.error.URLError(ConnectionRefusedError(61, "refused"))
        with mock.patch.object(net.urllib.request, "urlopen", fake):
            with self.assertRaises(urllib.error.URLError):
                net.urlopen("https://example.invalid/x")
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
