import os
import base64

TEST_DIR = os.path.dirname(__file__)
CERT_FILE = os.path.join(TEST_DIR, "sslcert", "server.crt")
KEY_FILE = os.path.join(TEST_DIR, "sslcert", "server.key")


def b64_ssl_cert():
    with open(CERT_FILE, "rb") as fd:
        ssl_cert = fd.read()
    return base64.b64encode(ssl_cert).decode("utf-8")


def b64_ssl_key():
    with open(KEY_FILE, "rb") as fd:
        ssl_key = fd.read()
    return base64.b64encode(ssl_key).decode("utf-8")
