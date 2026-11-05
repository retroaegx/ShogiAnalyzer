These are public test fixtures, not production credentials.
The local test CA, localhost server certificate and private key are used only by a
loopback HTTPS server in test_https_client.py. Never use them for deployment.
They are deliberately not added to the OS trust store. Individual tests load
the CA into a temporary SSL context to check trust and name validation.
