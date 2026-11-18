# SPDX-License-Identifier: Apache-2.0
"""HTTPS downloads that work on a Python without its own certificate store.

The python.org installer for macOS ships without CA certificates until its "Install Certificates"
step is run, so every https download fails with CERTIFICATE_VERIFY_FAILED on a clean
install). Certificates are always verified: on that error the request is tried once more with the
operating system's CA bundle (or certifi when it is installed), never without verification."""
import os
import ssl
import urllib.error
import urllib.request

# CA bundles of the operating system, first one found is used
_SYSTEM_BUNDLES = (
    "/etc/ssl/cert.pem",                                  # macOS, Alpine, some BSDs
    "/etc/ssl/certs/ca-certificates.crt",                 # Debian, Ubuntu, Arch
    "/etc/pki/tls/certs/ca-bundle.crt",                   # Fedora, RHEL
    "/etc/ssl/ca-bundle.pem",                             # openSUSE
)


def _cert_failure(err):
    reason = getattr(err, "reason", err)
    return isinstance(reason, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(reason)


def fallback_context():
    """A verifying SSL context from certifi or a system bundle; None when neither exists."""
    try:
        import certifi  # optional, not a dependency
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    for path in _SYSTEM_BUNDLES:
        if os.path.isfile(path):
            return ssl.create_default_context(cafile=path)
    return None


def urlopen(url, timeout=60):
    """urllib.request.urlopen, retried once with the system CA bundle on a certificate error."""
    try:
        return urllib.request.urlopen(url, timeout=timeout)
    except urllib.error.URLError as e:
        ctx = fallback_context() if _cert_failure(e) else None
        if ctx is None:
            raise
        return urllib.request.urlopen(url, timeout=timeout, context=ctx)
