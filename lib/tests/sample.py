import base64


SAMPLE_DB_UNIT_DATA = {
    "database": "all",
    "allowed-units": "landscape-server/0",
    "state": "standalone",
    "host": "10.0.3.168",
    "user": "db_admin_1",
    "password": "sekret",
    "port": "5432"
}

SAMPLE_LEADER_CONTEXT_DATA = {
    "database-password": "landscape-sekret",
    "secret-token": "landscape-token",
    "leader-ip": "1.2.3.4",
}

SAMPLE_LEADER_DATA = {
    "database-password": "landscape-sekret",
    "secret-token": "landscape-token",
    "leader-ip": "1.2.3.4",
}

SAMPLE_WEBSITE_UNIT_DATA = {
    "public-address": "1.2.3.4",
    "ssl_cert": base64.b64encode("<ssl data>"),
}

SAMPLE_AMQP_UNIT_DATA = {
    "hostname": "10.0.3.170",
    "password": "guessme",
}

SAMPLE_CONFIG = {
    "worker-counts": 2,
    "source": "ppa:landscape/14.10",
    "smtp-relay-host": "",
}

SAMPLE_CONFIG_OPENID_DATA = SAMPLE_CONFIG.copy()
SAMPLE_CONFIG_OPENID_DATA.update({
    "openid-provider-url": "http://openid-host/",
    "openid-logout-url": "http://openid-host/logout",
})

SAMPLE_CONFIG_LICENSE_DATA = {
    "license-file": base64.b64encode("license data"),
}

SAMPLE_HOSTED_DATA = {
    "deployment-mode": "standalone",
}

SAMPLE_WORKER_COUNT_DATA = {
    "appserver": 2,
    "message-server": 2,
    "pingserver": 2,
}
