from hashlib import md5
from subprocess import check_output
from ConfigParser import RawConfigParser
from subprocess import check_call

config_file = "/etc/landscape/service.conf"


def get_passwords():
    parser = RawConfigParser()
    parser.read([config_file])

    if not parser.has_option("schema", "store_password"):
        passwords = check_output(["pwgen", "-s", "16", "4"]).splitlines()
        parser.set("schema", "store_password", passwords[0])
        parser.set("stores", "password", passwords[1])
        parser.set("maintenance", "store_password", passwords[2])
        with open(config_file, "w+") as output_file:
            parser.write(output_file)
    else:
        passwords = []
        passwords.append(parser.get("schema", "store_password"))
        passwords.append(parser.get("stores", "password"))
        passwords.append(parser.get("maintenance", "store_password"))

    return passwords


def get_users():
    passwords = get_passwords()

    users = {"landscape_superuser": ("admin", passwords[0]),
             "landscape": ("user", passwords[1]),
             "landscape_maintenance": ("user", passwords[2])}
    return users


def set_host(store):

    host = check_output(["relation-get", "private-address"]).strip()
    ready = check_output(["relation-get", "ready"]).strip()

    if host and ready:
        parser = RawConfigParser()
        parser.read([config_file])

        parser.set("stores", "%s-host" % store, host)
        with open(config_file, "w+") as output_file:
            parser.write(output_file)

        stores = ["main", "account-1", "resource-1", "package", "session",
                  "knowledge"]
        databases = {}
        for store in stores:
            if parser.has_option("stores", "%s-host" % store):
                databases[store] = parser.get("stores", "%s-host" % store)
            else:
                break
        if len(databases) == len(stores):
            users = get_users()
            configure_pgbouncer(databases, users)

def juju_log(message):
    check_call(["juju-log", message])

def configure_pgbouncer(databases, users):

    auth = []
    for user, (role, password) in users.items():
        password = md5("%s%s" % (password, user)).hexdigest()
        auth.append('"%s" "md5%s"' % (user, password))

    with file("/etc/pgbouncer/userlist.txt", "w+") as bouncer_config:
        bouncer_config.write("\n".join(auth))
        bouncer_config.write("\n")

    pgbouncer_config_file = "/etc/pgbouncer/pgbouncer.ini"

    parser = RawConfigParser()
    parser.read([pgbouncer_config_file])

    for db, host in databases.items():
        parser.set(
            "databases", "landscape-standalone-%s" % db, "host=%s" % host)

    with open(pgbouncer_config_file, "w+") as output_file:
        parser.write(output_file)

    check_output(["service", "pgbouncer", "restart"])
