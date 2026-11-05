These are public test fixtures, not production credentials.
The self-signed localhost certificate and its private key are used only by a
loopback HTTPS server in test_https_client.py. Never use them for deployment.
They are deliberately not added to the OS trust store. Individual tests load
the certificate into a temporary SSL context to check trust and name validation.
