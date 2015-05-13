import os

TEST_DIR = os.path.dirname(os.path.dirname(__file__))
CERT_FILE = os.path.join(TEST_DIR, "sslcert", "server.crt")
KEY_FILE = os.path.join(TEST_DIR, "sslcert", "server.key")
