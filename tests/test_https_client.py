"""Exercise verified TLS over a real loopback HTTPS connection."""
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import ssl
import threading
import unittest
from unittest.mock import patch
import urllib.error

from https_client import create_https_context, verified_urlopen

FIXTURES=Path(__file__).parent/'fixtures/tls'


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'verified TLS')

    def log_message(self,*args):
        pass


class HTTPSClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=HTTPServer(('127.0.0.1',0),Handler)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(FIXTURES/'localhost-test.pem'),str(FIXTURES/'localhost-test.key'))
        cls.server.socket=context.wrap_socket(cls.server.socket,server_side=True)
        cls.worker=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.worker.start()
        cls.port=cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join(timeout=5)

    def trusted_context(self):
        context=create_https_context()
        context.load_verify_locations(cafile=str(FIXTURES/'localhost-test-ca.pem'))
        return context

    def test_certificate_and_hostname_verification_required(self):
        context=create_https_context()
        self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)

    def test_explicitly_trusted_certificate_succeeds(self):
        with patch('https_client.create_https_context',return_value=self.trusted_context()):
            with verified_urlopen(f'https://localhost:{self.port}',timeout=5) as response:
                self.assertEqual(response.read(),b'verified TLS')

    def test_unknown_certificate_rejected(self):
        with self.assertRaises(urllib.error.URLError) as error:
            verified_urlopen(f'https://localhost:{self.port}',timeout=5)
        self.assertIsInstance(error.exception.reason,ssl.SSLCertVerificationError)

    def test_wrong_hostname_rejected_even_with_trusted_certificate(self):
        with patch('https_client.create_https_context',return_value=self.trusted_context()):
            with self.assertRaises(urllib.error.URLError) as error:
                verified_urlopen(f'https://127.0.0.1:{self.port}',timeout=5)
        self.assertIsInstance(error.exception.reason,ssl.SSLCertVerificationError)


if __name__=='__main__':
    unittest.main()
