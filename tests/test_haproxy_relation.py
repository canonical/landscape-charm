from base64 import b64encode
import unittest

from ops.model import BlockedStatus
from ops.testing import Context, Relation, State, StoredState
import yaml

from charm import (
    _create_grpc_service,
    _create_http_service,
    _create_https_service,
    _create_ubuntu_installer_attach_service,
    HAProxyErrorFile,
    LandscapeServerCharm,
)


class TestWebsiteRelationJoined:
    """
    Tests for handlers of the `on.website_relation_joined` hook.
    """

    def test_requires_ssl_cert_and_key(self):
        """
        If there is not a valid ssl_cert and ssl_key pair provided in the model
        configuration, enter blocked status.
        """

        context = Context(LandscapeServerCharm)
        relation = Relation("website")
        state_in = State(
            config={
                "root_url": "http://fake-root.test",
                "ssl_cert": "",
                "ssl_key": "",
            },
            relations=[relation],
        )
        state_out = context.run(context.on.relation_joined(relation), state_in)

        assert isinstance(state_out.unit_status, BlockedStatus)

    def test_allows_default_ssl_cert_without_key(self):
        """
        If the `ssl_cert` parameter is `"DEFAULT"`, then allow an empty `ssl_key`.
        Use the `"DEFAULT"` literal for the SSL configurations of the HTTPS,
        Ubuntu installer, and gRPC frontends.
        """

        context = Context(LandscapeServerCharm)
        relation = Relation("website")
        state_in = State(
            config={
                "root_url": "http://fake-root.test",
                "ssl_cert": "DEFAULT",
                "ssl_key": "",
                "worker_counts": 1,
            },
            relations=[relation],
        )
        state_out = context.run(context.on.relation_joined(relation), state_in)
        services = state_out.get_relation(relation.id).local_unit_data["services"]

        frontends = {
            "landscape-https",
            "landscape-grpc",
            "landscape-ubuntu-installer-attach",
        }

        for service in yaml.safe_load(services):
            if service["service_name"] in frontends:
                assert service["crts"] == ["DEFAULT"]

    def test_nondefault_ssl_cert_must_be_b64_encoded(self):
        """
        If the `ssl_cert` parameter is not `"DEFAULT"`, then the cert and key must be
        b64-encoded.
        """

        context = Context(LandscapeServerCharm)
        relation = Relation("website")
        state_in = State(
            config={
                "root_url": "http://fake-root.test",
                "ssl_cert": "notb64encoded!",
                "ssl_key": "notb64encoded!",
            },
            relations=[relation],
        )
        state_out = context.run(context.on.relation_joined(relation), state_in)

        assert isinstance(state_out.unit_status, BlockedStatus)

    def test_sets_root_url(self, capture_service_conf):
        """
        If the model does not provide a root URL, derive a root URL from the
        relation and use it to set the root-url configuration.

        Store the root URL as the 'default_root_url'.
        """
        public_address = "haproxy.test"
        expected_root_url = "https://" + public_address + "/"
        context = Context(LandscapeServerCharm)
        relation = Relation(
            "website", remote_units_data={0: {"public-address": public_address}}
        )
        state_in = State(
            config={
                "root_url": "",
                "ssl_cert": "DEFAULT",
                "ssl_key": "",
                "worker_counts": 1,
            },
            relations=[relation],
        )

        state_out = context.run(context.on.relation_joined(relation), state_in)

        stored_root_url = state_out.get_stored_state(
            "_stored", owner_path="LandscapeServerCharm"
        ).content.get("default_root_url")
        assert stored_root_url == expected_root_url

        config = capture_service_conf.get_config()
        assert config["global"].get("root-url") == expected_root_url
        assert config["api"].get("root-url") == expected_root_url
        assert config["package-upload"].get("root-url") == expected_root_url

    def test_excludes_ubuntu_installer_attach_if_disabled(self):
        """
        If the Ubuntu installer attach service is disabled, do not include a frontend
        for it.
        """
        context = Context(LandscapeServerCharm)
        relation = Relation("website")
        state_in = State(
            config={"root_url": "https//root.test"},
            relations=[relation],
            stored_states=[
                StoredState(
                    owner_path="LandscapeServerCharm",
                    content={"enable_ubuntu_installer_attach": False},
                )
            ],
        )
        state_out = context.run(context.on.relation_joined(relation), state_in)
        raw_services = state_out.get_relation(relation.id).local_unit_data["services"]
        services = yaml.safe_load(raw_services)
        service_names = (s["service_name"] for s in services)

        assert "landscape-ubuntu-installer-attach" not in service_names

    def test_includes_ubuntu_installer_attach_if_enabled(self):
        """
        If the Ubuntu installer attach service is enabled, include a frontend for it.
        """
        context = Context(LandscapeServerCharm)
        relation = Relation("website")
        state_in = State(
            config={"root_url": "https//root.test"},
            relations=[relation],
            stored_states=[
                StoredState(
                    owner_path="LandscapeServerCharm",
                    content={"enable_ubuntu_installer_attach": True},
                )
            ],
        )
        state_out = context.run(context.on.relation_joined(relation), state_in)
        raw_services = state_out.get_relation(relation.id).local_unit_data["services"]
        services = yaml.safe_load(raw_services)
        service_names = (s["service_name"] for s in services)

        assert "landscape-ubuntu-installer-attach" in service_names


class TestCreateHTTPService(unittest.TestCase):
    """
    Tests for `_create_http_service`.
    """

    def setUp(self):
        self.appserver_port = 9000
        self.pingserver_port = 10000
        self.service_ports = {
            "appserver": self.appserver_port,
            "pingserver": self.pingserver_port,
        }
        self.server_options = ["check", "inter 5000", "rise 2", "fall 5", "maxconn 50"]
        self.http_service = {
            "service_name": "landscape-http",
            "service_host": "0.0.0.0",
            "service_port": 80,
            "service_options": [
                "mode http",
                "timeout client 3000000",
                "timeout server 300000",
            ],
        }

    def test_pingserver_backend(self):
        """
        Creates a backend for pingserver
        """
        http = _create_http_service(
            http_service=self.http_service,
            server_ip="10.1.1.10",
            unit_name="unitname",
            worker_counts=1,
            error_files=(),
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        self.assertEqual(
            [
                {
                    "backend_name": "landscape-ping",
                    "servers": [
                        (
                            "landscape-pingserver-unitname-0",
                            "10.1.1.10",
                            self.pingserver_port,
                            self.server_options,
                        )
                    ],
                }
            ],
            http["backends"],
        )

    def test_pingserver_workers(self):
        """
        If worker_counts is provided, create an pingserver worker for each
        worker. Increment the port by 1 for each worker.
        """

        workers = 3

        http = _create_http_service(
            http_service=self.http_service,
            server_ip="10.1.1.10",
            unit_name="unitname",
            worker_counts=workers,
            error_files=(),
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        expected = [
            {
                "backend_name": "landscape-ping",
                "servers": [
                    (
                        f"landscape-pingserver-unitname-{i}",
                        "10.1.1.10",
                        self.pingserver_port + i,
                        self.server_options,
                    )
                    for i in range(workers)
                ],
            }
        ]

        self.assertEqual(expected, http["backends"])

    def test_appserver_server(self):
        """
        Creates a server stanza for the appserver.
        """

        http = _create_http_service(
            http_service=self.http_service,
            server_ip="10.1.1.10",
            unit_name="unitname",
            worker_counts=1,
            error_files=(),
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        self.assertEqual(
            [
                (
                    "landscape-appserver-unitname-0",
                    "10.1.1.10",
                    self.appserver_port,
                    self.server_options,
                )
            ],
            http["servers"],
        )

    def test_appserver_workers(self):
        """
        If worker_counts is provided, create an appserver worker for each
        worker. Increment the port by 1 for each worker.
        """

        workers = 3

        http = _create_http_service(
            http_service=self.http_service,
            server_ip="10.1.1.10",
            unit_name="unitname",
            worker_counts=workers,
            error_files=(),
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        expected = [
            (
                f"landscape-appserver-unitname-{i}",
                "10.1.1.10",
                self.appserver_port + i,
                self.server_options,
            )
            for i in range(workers)
        ]

        self.assertEqual(expected, http["servers"])

    def test_error_files(self):
        """
        Sets error files for the service if provided.
        """

        error_files = [
            HAProxyErrorFile(http_status=404, content=b64encode(b"Not Found!")),
            HAProxyErrorFile(http_status=405, content=b64encode(b"Not Allowed!")),
            HAProxyErrorFile(http_status=500, content=b64encode(b"Oops, our fault...")),
        ]

        http = _create_http_service(
            http_service=self.http_service,
            server_ip="10.1.1.10",
            unit_name="unitname",
            worker_counts=1,
            error_files=error_files,
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        expected = [
            {"http_status": 404, "content": b64encode(b"Not Found!")},
            {"http_status": 405, "content": b64encode(b"Not Allowed!")},
            {"http_status": 500, "content": b64encode(b"Oops, our fault...")},
        ]

        self.assertEqual(expected, http["error_files"])


class TestCreateHTTPSService(unittest.TestCase):
    """
    Tests for `_create_https_service`.
    """

    def setUp(self):
        self.appserver_port = 9000
        self.message_server_port = 11000
        self.api_port = 12000
        self.package_upload_port = 13000
        self.service_ports = {
            "appserver": self.appserver_port,
            "message-server": self.message_server_port,
            "api": self.api_port,
            "package-upload": self.package_upload_port,
        }
        self.server_options = ["check", "inter 5000", "rise 2", "fall 5", "maxconn 50"]
        self.https_service = {
            "service_name": "landscape-https",
            "service_host": "0.0.0.0",
            "service_port": 443,
            "service_options": [
                "mode http",
                "timeout client 2000000",
                "timeout server 2000000",
            ],
        }

    def test_ssl_cert(self):
        """
        Uses the provided ssl cert.
        """

        ssl_cert = "some-ssl-data-plz-trust-this"

        service = _create_https_service(
            https_service=self.https_service,
            ssl_cert=ssl_cert,
            server_ip="",
            unit_name="",
            worker_counts=1,
            is_leader=True,
            error_files=(),
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        self.assertEqual([ssl_cert], service["crts"])

    def test_error_files(self):
        """
        Sets error files for the service if provided.
        """

        error_files = [
            HAProxyErrorFile(http_status=404, content=b64encode(b"Not Found!")),
            HAProxyErrorFile(http_status=405, content=b64encode(b"Not Allowed!")),
            HAProxyErrorFile(http_status=500, content=b64encode(b"Oops, our fault...")),
        ]

        service = _create_https_service(
            https_service=self.https_service,
            ssl_cert="",
            server_ip="",
            unit_name="",
            worker_counts=1,
            is_leader=True,
            error_files=error_files,
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        expected = [
            {"http_status": 404, "content": b64encode(b"Not Found!")},
            {"http_status": 405, "content": b64encode(b"Not Allowed!")},
            {"http_status": 500, "content": b64encode(b"Oops, our fault...")},
        ]

        self.assertEqual(expected, service["error_files"])

    def test_appserver_server(self):
        """
        Creates an appserver server stanza.
        """
        server_ip = "10.194.61.5"
        unitname = "unitname"

        service = _create_https_service(
            https_service=self.https_service,
            ssl_cert="",
            server_ip=server_ip,
            unit_name=unitname,
            worker_counts=1,
            is_leader=True,
            error_files=(),
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        expected = [
            (
                f"landscape-appserver-{unitname}-0",
                server_ip,
                self.appserver_port,
                self.server_options,
            )
        ]

        self.assertEqual(expected, service["servers"])

    def test_appserver_workers(self):
        """
        Creates an appserver for each worker, incrementing the port by 1.
        """
        workers = 3
        server_ip = "10.194.61.5"
        unitname = "unitname"

        service = _create_https_service(
            https_service=self.https_service,
            ssl_cert="",
            server_ip=server_ip,
            unit_name=unitname,
            worker_counts=workers,
            is_leader=True,
            error_files=(),
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        expected = [
            (
                f"landscape-appserver-{unitname}-{i}",
                server_ip,
                self.appserver_port + i,
                self.server_options,
            )
            for i in range(workers)
        ]

        self.assertEqual(expected, service["servers"])

    def test_api_backend(self):
        """
        Creates a landscape-api backend.
        """
        server_ip = "10.194.61.5"
        unitname = "unitname"

        service = _create_https_service(
            https_service=self.https_service,
            ssl_cert="",
            server_ip=server_ip,
            unit_name=unitname,
            worker_counts=1,
            is_leader=True,
            error_files=(),
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        expected = {
            "backend_name": "landscape-api",
            "servers": [
                (
                    f"landscape-api-{unitname}-0",
                    server_ip,
                    self.api_port,
                    self.server_options,
                )
            ],
        }

        self.assertIn(expected, service["backends"])

    def test_api_workers(self):
        """
        Creates an landscape-api backend for each worker, incrementing the port by 1.
        """
        workers = 3
        server_ip = "10.194.61.5"
        unitname = "unitname"

        service = _create_https_service(
            https_service=self.https_service,
            ssl_cert="",
            server_ip=server_ip,
            unit_name=unitname,
            worker_counts=workers,
            is_leader=True,
            error_files=(),
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        expected = {
            "backend_name": "landscape-api",
            "servers": [
                (
                    f"landscape-api-{unitname}-{i}",
                    server_ip,
                    self.api_port + i,
                    self.server_options,
                )
                for i in range(workers)
            ],
        }

        self.assertIn(expected, service["backends"])

    def test_message_server_backend(self):
        """
        Creates a landscape-message backend.
        """
        server_ip = "10.194.61.5"
        unitname = "unitname"

        service = _create_https_service(
            https_service=self.https_service,
            ssl_cert="",
            server_ip=server_ip,
            unit_name=unitname,
            worker_counts=1,
            is_leader=True,
            error_files=(),
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        expected = {
            "backend_name": "landscape-message",
            "servers": [
                (
                    f"landscape-message-server-{unitname}-0",
                    server_ip,
                    self.message_server_port,
                    self.server_options,
                )
            ],
        }

        self.assertIn(expected, service["backends"])

    def test_message_server_workers(self):
        """
        Creates a landscape-message backend for each worker, incrementing the port by 1.
        """
        workers = 3
        server_ip = "10.194.61.5"
        unitname = "unitname"

        service = _create_https_service(
            https_service=self.https_service,
            ssl_cert="",
            server_ip=server_ip,
            unit_name=unitname,
            worker_counts=workers,
            is_leader=True,
            error_files=(),
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        expected = {
            "backend_name": "landscape-message",
            "servers": [
                (
                    f"landscape-message-server-{unitname}-{i}",
                    server_ip,
                    self.message_server_port + i,
                    self.server_options,
                )
                for i in range(workers)
            ],
        }

        self.assertIn(expected, service["backends"])

    def test_package_upload_backend(self):
        """
        Creates a landscape-package-upload backend if the unit is the leader.
        """
        server_ip = "10.194.61.5"
        unitname = "unitname"

        service = _create_https_service(
            https_service=self.https_service,
            ssl_cert="",
            server_ip=server_ip,
            unit_name=unitname,
            worker_counts=1,
            is_leader=True,
            error_files=(),
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        expected = {
            "backend_name": "landscape-package-upload",
            "servers": [
                (
                    f"landscape-package-upload-{unitname}-0",
                    server_ip,
                    self.package_upload_port,
                    self.server_options,
                )
            ],
        }

        self.assertIn(expected, service["backends"])

    def test_no_package_upload_on_nonleader(self):
        """
        Does not create a landscape-package-upload backend if the unit is not
        the leader.
        """
        service = _create_https_service(
            https_service=self.https_service,
            ssl_cert="",
            server_ip="",
            unit_name="",
            worker_counts=1,
            is_leader=False,
            error_files=(),
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        expected = {
            "backend_name": "landscape-package-upload",
            "servers": [],
        }

        self.assertIn(expected, service["backends"])

    def test_hashid_databases_backend(self):
        """
        Creates a landscape-hashid-databases backend if the unit is the leader.

        The landscape-hashid-databases backend uses the appservers.
        """
        server_ip = "10.194.61.5"
        unitname = "unitname"

        service = _create_https_service(
            https_service=self.https_service,
            ssl_cert="",
            server_ip=server_ip,
            unit_name=unitname,
            worker_counts=1,
            is_leader=True,
            error_files=(),
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        expected = {
            "backend_name": "landscape-hashid-databases",
            "servers": [
                (
                    f"landscape-appserver-{unitname}-0",
                    server_ip,
                    self.appserver_port,
                    self.server_options,
                )
            ],
        }

        self.assertIn(expected, service["backends"])

    def test_no_hashid_databases_on_nonleader(self):
        """
        Does not create a landscape-hashid-databases backend if the unit is not the
        leader.
        """
        service = _create_https_service(
            https_service=self.https_service,
            ssl_cert="",
            server_ip="",
            unit_name="",
            worker_counts=1,
            is_leader=False,
            error_files=(),
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        expected = {
            "backend_name": "landscape-hashid-databases",
            "servers": [],
        }

        self.assertIn(expected, service["backends"])


class TestCreateGRPCService(unittest.TestCase):
    """
    Tests for `_create_grpc_service`.
    """

    def setUp(self):
        self.hostagent_port = 50052
        self.service_ports = {"hostagent-messenger": self.hostagent_port}
        self.server_options = ["check", "inter 5000", "rise 2", "fall 5", "maxconn 50"]
        self.grpc_service = {
            "service_name": "landscape-grpc",
            "service_host": "0.0.0.0",
            "service_port": 6554,
            "service_options": [],
            "server_options": ["proto h2"],
        }

    def test_ssl_cert(self):
        """
        Sets the provided ssl_cert.
        """
        ssl_cert = "some-ssl-cert-data"

        service = _create_grpc_service(
            grpc_service=self.grpc_service,
            ssl_cert=ssl_cert,
            server_ip="",
            unit_name="",
            error_files=(),
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        self.assertEqual([ssl_cert], service["crts"])

    def test_hostagent_messengers(self):
        """
        Creates a landscape-hostagent-messenger server.

        The gRPC server consolidates the general server options provided for all
        services and the options specifically provided for the gRPC service.
        """
        server_ip = "10.194.61.5"
        unitname = "unitname"

        service = _create_grpc_service(
            grpc_service=self.grpc_service,
            ssl_cert="",
            server_ip=server_ip,
            unit_name=unitname,
            error_files=(),
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        options = self.server_options + self.grpc_service["server_options"]
        expected = [
            (
                f"landscape-hostagent-messenger-{unitname}-0",
                server_ip,
                self.hostagent_port,
                options,
            )
        ]

        self.assertEqual(expected, service["servers"])

    def test_error_files(self):
        """
        Sets the error files.
        """
        error_files = [
            HAProxyErrorFile(http_status=404, content=b64encode(b"Not Found!")),
            HAProxyErrorFile(http_status=405, content=b64encode(b"Not Allowed!")),
            HAProxyErrorFile(http_status=500, content=b64encode(b"Oops, our fault...")),
        ]

        service = _create_grpc_service(
            grpc_service=self.grpc_service,
            ssl_cert="",
            server_ip="",
            unit_name="",
            error_files=error_files,
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        expected = [
            {"http_status": 404, "content": b64encode(b"Not Found!")},
            {"http_status": 405, "content": b64encode(b"Not Allowed!")},
            {"http_status": 500, "content": b64encode(b"Oops, our fault...")},
        ]

        self.assertEqual(expected, service["error_files"])


class TestCreateUbuntuInstallerAttachService(unittest.TestCase):
    """
    Tests for `_create_ubuntu_installer_attach_service`.
    """

    def setUp(self):
        self.backend_port = 53354
        self.service_ports = {"ubuntu-installer-attach": self.backend_port}
        self.server_options = ["check", "inter 5000", "rise 2", "fall 5", "maxconn 50"]
        self.service = {
            "service_name": "landscape-ubuntu-installer-attach",
            "service_host": "0.0.0.0",
            "service_port": 50051,
            "service_options": [
                "acl host_found hdr(host) -m found",
                "http-request set-var(req.full_fqdn) hdr(authority) if !host_found",
                "http-request set-var(req.full_fqdn) hdr(host) if host_found",
                "http-request set-header X-FQDN %[var(req.full_fqdn)]",
            ],
            "server_options": ["proto h2"],
        }

    def test_ssl_cert(self):
        """
        Sets the provided ssl_cert.
        """
        ssl_cert = "some-ssl-cert-data"

        service = _create_ubuntu_installer_attach_service(
            ubuntu_installer_attach_service=self.service,
            ssl_cert=ssl_cert,
            server_ip="",
            unit_name="",
            error_files=(),
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        self.assertEqual([ssl_cert], service["crts"])

    def test_ubuntu_installer_attach_server(self):
        """
        Creates a landscape-ubuntu-installer-attach server.
        """

        server_ip = "10.194.61.15"
        unitname = "unitname"

        service = _create_ubuntu_installer_attach_service(
            ubuntu_installer_attach_service=self.service,
            ssl_cert="",
            server_ip=server_ip,
            unit_name=unitname,
            error_files=(),
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        options = self.server_options + self.service["server_options"]
        expected = [
            (
                f"landscape-ubuntu-installer-attach-{unitname}-0",
                server_ip,
                self.backend_port,
                options,
            )
        ]

        self.assertEqual(expected, service["servers"])

    def test_error_files(self):
        """
        Sets the error files.
        """
        error_files = [
            HAProxyErrorFile(http_status=404, content=b64encode(b"Not Found!")),
            HAProxyErrorFile(http_status=405, content=b64encode(b"Not Allowed!")),
            HAProxyErrorFile(http_status=500, content=b64encode(b"Oops, our fault...")),
        ]

        service = _create_ubuntu_installer_attach_service(
            ubuntu_installer_attach_service=self.service,
            ssl_cert="",
            server_ip="",
            unit_name="",
            error_files=error_files,
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        expected = [
            {"http_status": 404, "content": b64encode(b"Not Found!")},
            {"http_status": 405, "content": b64encode(b"Not Allowed!")},
            {"http_status": 500, "content": b64encode(b"Oops, our fault...")},
        ]

        self.assertEqual(expected, service["error_files"])
