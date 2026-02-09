from urllib.parse import urlparse

from charmlibs.interfaces.tls_certificates import CertificateRequestAttributes
from ops import testing
import pytest
from scenario import Context, State

from charm import LandscapeServerCharm


def test_get_certificate_request_attributes(lb_certs_state):
    """
    No root url, no hostname (, no problems).
    """
    ctx = Context(LandscapeServerCharm)
    state = State(**lb_certs_state)

    with ctx(ctx.on.start(), state) as mgr:
        ip = mgr.charm.unit_ip
        assert ip is not None

        cert_req_attr = mgr.charm._get_certificate_request_attributes()
        assert cert_req_attr is not None

        assert mgr.charm.charm_config.root_url is None
        expected = CertificateRequestAttributes(
            common_name=ip,
            sans_ip=[ip],
            sans_dns=None,
        )

        assert expected == cert_req_attr


def test_get_certificate_request_attributes_root_url(lb_certs_state):
    ctx = Context(LandscapeServerCharm)
    root_url = "https://landscape.example.com/"
    state = State(**lb_certs_state, config={"root_url": root_url})

    with ctx(ctx.on.start(), state) as mgr:
        ip = mgr.charm.unit_ip
        assert ip is not None

        cert_req_attr = mgr.charm._get_certificate_request_attributes()
        assert cert_req_attr is not None

        assert mgr.charm.charm_config.root_url == root_url
        hostname = urlparse(root_url).hostname
        expected = CertificateRequestAttributes(
            common_name=hostname,
            sans_ip=[ip],
            sans_dns=[hostname],
        )

        assert expected == cert_req_attr


def test_haproxy_update_calls_get_cert_req_attr(
    lb_certs_state, certificate_and_key_fixture, haproxy_root_fixture
):
    ctx = Context(LandscapeServerCharm)
    state = State(**lb_certs_state)
    tls_mock = haproxy_root_fixture[3]

    with ctx(ctx.on.config_changed(), state) as mgr:
        provider_cert, private_key = certificate_and_key_fixture

        stored = mgr.charm._stored
        assert provider_cert is not None and private_key is not None

    tls_mock.assert_called_once_with(
        provider_certificate=provider_cert, private_key=private_key
    )

    assert "ssl crt /etc/haproxy/haproxy.pem" in stored.haproxy_config


def test_get_certificate_request_attributes_root_url_no_hostname(lb_certs_state):
    """Test with root_url that has no hostname (edge case)."""
    ctx = Context(LandscapeServerCharm)
    root_url = "https://"
    state = State(**lb_certs_state, config={"root_url": root_url})

    with ctx(ctx.on.start(), state) as mgr:
        ip = mgr.charm.unit_ip
        assert ip is not None

        cert_req_attr = mgr.charm._get_certificate_request_attributes()
        assert cert_req_attr is not None

        expected = CertificateRequestAttributes(
            common_name=ip,
            sans_ip=[ip],
            sans_dns=None,
        )

        assert expected == cert_req_attr


def test_get_certificate_request_attributes_ipv6_in_url(lb_certs_state):
    """Test with IPv6 address in root_url."""
    ctx = Context(LandscapeServerCharm)
    root_url = "https://[2001:db8::1]/"
    state = State(**lb_certs_state, config={"root_url": root_url})

    with ctx(ctx.on.start(), state) as mgr:
        ip = mgr.charm.unit_ip
        assert ip is not None

        cert_req_attr = mgr.charm._get_certificate_request_attributes()
        assert cert_req_attr is not None

        hostname = urlparse(root_url).hostname
        assert hostname == "2001:db8::1"

        expected = CertificateRequestAttributes(
            common_name=hostname,
            sans_ip=[ip],
            sans_dns=[hostname],
        )

        assert expected == cert_req_attr


def test_update_haproxy_returns_early_when_no_cert_attrs(
    lb_certs_state, certificate_and_key_fixture, haproxy_root_fixture, monkeypatch
):
    """Test that _update_haproxy returns early when cert attributes
    cannot be generated.
    """
    ctx = Context(LandscapeServerCharm)
    state = State(**lb_certs_state)

    monkeypatch.setattr(
        LandscapeServerCharm, "_get_certificate_request_attributes", lambda self: None
    )

    with ctx(ctx.on.config_changed(), state) as mgr:
        stored = mgr.charm._stored

    assert not hasattr(stored, "haproxy_config") or not stored.haproxy_config


def test_update_haproxy_sets_default_root_url(
    lb_certs_state, certificate_and_key_fixture, haproxy_root_fixture
):
    """Test that _update_haproxy sets default root_url when not configured."""
    ctx = Context(LandscapeServerCharm)
    state = State(**lb_certs_state)

    with ctx(ctx.on.config_changed(), state) as mgr:
        peer_ips = mgr.charm.peer_ips
        stored = mgr.charm._stored

    assert peer_ips is not None
    expected_url = f"https://{peer_ips.leader_ip}/"
    assert stored.default_root_url == expected_url


def test_update_haproxy_does_not_override_configured_root_url(
    lb_certs_state, certificate_and_key_fixture, haproxy_root_fixture
):
    """Test that _update_haproxy doesn't set default_root_url when
    root_url is configured.
    """
    ctx = Context(LandscapeServerCharm)
    root_url = "https://landscape.example.com/"
    state = State(**lb_certs_state, config={"root_url": root_url})

    with ctx(ctx.on.config_changed(), state) as mgr:
        stored = mgr.charm._stored

    assert not hasattr(stored, "default_root_url") or not stored.default_root_url


def test_update_haproxy_marks_ready_on_success(
    lb_certs_state, certificate_and_key_fixture, haproxy_root_fixture
):
    """Test that _update_haproxy marks load-balancer-certificates as ready
    on success.
    """
    ctx = Context(LandscapeServerCharm)
    state = State(**lb_certs_state)

    with ctx(ctx.on.config_changed(), state) as mgr:
        stored = mgr.charm._stored

    assert stored.ready.get("load-balancer-certificates") is True


def test_tls_certificates_refresh_events(lb_certs_state):
    """Test that TLS certificates are refreshed on the expected events."""
    ctx = Context(LandscapeServerCharm)
    state = State(**lb_certs_state)

    events_to_test = [
        ctx.on.config_changed(),
        ctx.on.leader_elected(),
    ]

    for event in events_to_test:
        with ctx(event, state) as mgr:
            cert_attrs = mgr.charm._get_certificate_request_attributes()
            assert cert_attrs is not None
            assert cert_attrs.sans_ip is not None


def test_action_get_certificates_success(
    lb_certs_state, certificate_and_key_fixture, haproxy_root_fixture
):
    """Test get-certificates action returns cert data when available."""
    ctx = Context(LandscapeServerCharm)
    state = State(**lb_certs_state)

    ctx.run(ctx.on.action("get-certificates"), state)

    assert ctx.action_results is not None
    assert "certificate" in ctx.action_results
    assert "ca" in ctx.action_results
    assert "chain" in ctx.action_results


def test_action_get_certificates_no_attrs(
    lb_certs_state, certificate_and_key_fixture, haproxy_root_fixture, monkeypatch
):
    """Test get-certificates action fails when cert attrs unavailable."""
    ctx = Context(LandscapeServerCharm)
    state = State(**lb_certs_state)

    monkeypatch.setattr(
        LandscapeServerCharm, "_get_certificate_request_attributes", lambda self: None
    )

    with pytest.raises(testing.ActionFailed):
        ctx.run(ctx.on.action("get-certificates"), state)


def test_action_get_certificates_no_provider_cert(
    lb_certs_state, haproxy_root_fixture, monkeypatch
):
    """Test get-certificates action fails when provider certificate is unavailable."""
    ctx = Context(LandscapeServerCharm)
    state = State(**lb_certs_state)

    monkeypatch.setattr(
        "charmlibs.interfaces.tls_certificates.TLSCertificatesRequiresV4.get_assigned_certificate",
        lambda *args, **kwargs: (None, None),
    )

    with pytest.raises(testing.ActionFailed):
        ctx.run(ctx.on.action("get-certificates"), state)


def test_upgrade_charm_updates_haproxy_config(
    lb_certs_state, certificate_and_key_fixture, haproxy_root_fixture
):
    ctx = Context(LandscapeServerCharm)
    state = State(**lb_certs_state)

    with ctx(ctx.on.upgrade_charm(), state) as mgr:
        stored = mgr.charm._stored

    assert stored.ready.get("load-balancer-certificates") is True
    assert "ssl crt /etc/haproxy/haproxy.pem" in stored.haproxy_config
