"""Verified HTTPS using native Windows/macOS trust and portable Linux CA roots."""
from __future__ import annotations

import os
from pathlib import Path
import ssl
import sys
import urllib.request


def create_https_context() -> ssl.SSLContext:
    if sys.platform in {'win32', 'darwin'}:
        import truststore
        # Native chain building can retrieve missing intermediates / trusted roots;
        # copying the small initial Windows Sandbox store into OpenSSL cannot.
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

    context = ssl.create_default_context()
    # Respect explicitly configured trust instead of silently replacing it.
    if os.environ.get('SSL_CERT_FILE') or os.environ.get('SSL_CERT_DIR'):
        return context
    if not context.cert_store_stats()['x509_ca']:
        defaults = ssl.get_default_verify_paths()
        if defaults.capath and any(Path(defaults.capath).glob('????????.[0-9]')):
            return context  # OpenSSL loads hashed certificate directories lazily.
        for path in ('/etc/ssl/certs/ca-certificates.crt', '/etc/ssl/cert.pem',
                     '/etc/pki/tls/cert.pem', '/etc/ssl/ca-bundle.pem',
                     '/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem'):
            if Path(path).is_file():
                context.load_verify_locations(cafile=path)
                return context
        # Minimal Linux images may have no ca-certificates package at all.
        import certifi
        context.load_verify_locations(cafile=certifi.where())
    return context


def verified_urlopen(request, *, timeout: float = 90):
    return urllib.request.urlopen(request, timeout=timeout, context=create_https_context())
