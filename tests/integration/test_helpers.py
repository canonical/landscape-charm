import pytest

from tests.integration.helpers import build_url


@pytest.mark.parametrize(
    "scheme,host,port,path,expected_url",
    [
        ("http", "192.168.0.1", None, "", "http://192.168.0.1"),
        ("https", "192.168.0.1", None, "", "https://192.168.0.1"),
        ("http", "192.168.0.1", 80, "", "http://192.168.0.1:80"),
        ("https", "192.168.0.1", 443, "/api", "https://192.168.0.1:443/api"),
        (
            "http",
            "2001:0db8:85a3:0000:0000:8a2e:0370:7334",
            None,
            "/",
            "http://[2001:0db8:85a3:0000:0000:8a2e:0370:7334]/",
        ),
        (
            "http",
            "2001:db8:85a3::8a2e:370:7334",
            None,
            "/",
            "http://[2001:db8:85a3::8a2e:370:7334]/",
        ),
        ("https", "2001:db8::1", 8081, "/ping", "https://[2001:db8::1]:8081/ping"),
        (
            "http",
            "2001:0db8:0000:0000:0000:ff00:0042:8329",
            1234,
            "/api/about",
            "http://[2001:0db8:0000:0000:0000:ff00:0042:8329]:1234/api/about",
        ),
        ("http", "example.com", None, "", "http://example.com"),
        (
            "https",
            "example.com",
            8443,
            "/api/v2/computers",
            "https://example.com:8443/api/v2/computers",
        ),
        ("http", "localhost", 5000, "/", "http://localhost:5000/"),
        ("http", "localhost", None, "/status", "http://localhost/status"),
    ],
)
def test_build_url(scheme, host, port, path, expected_url):
    url = build_url(scheme, host, port, path)
    assert url == expected_url
