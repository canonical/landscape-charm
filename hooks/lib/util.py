"""
Utility library for juju hooks
"""

from hashlib import md5
from subprocess import check_output, call, check_call
from ConfigParser import RawConfigParser
from psycopg2 import connect
import sys

config_file = "/etc/landscape/service.conf"
landscape_env = "/opt/canonical/landscape/scripts/landscape-env.sh"

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

def setup_landscape_server(host, admin_user, admin_password):
    """
    Wrapper around setup-landscape-server.  I need to do this in a safe way in
    a distributed environment since multiple landscape servers could be
    accessing the database at the same time.  Similarly, we want to make sure
    we don't run this again if it's not needed (if the schema check passes)
    """
    conn = connect(database='postgres', host=host, user=admin_user,
                   password=admin_password)
    try:
        cur = conn.cursor()
        cur.execute(
                "CREATE TABLE landscape_install_lock (id serial PRIMARY KEY);")
        cur.execute("LOCK landscape_install_lock IN ACCESS EXCLUSIVE MODE;")
        print "Mutex acquired on landscape_install_lock, Proceeding"
        if call(". %s; schema-check", shell=True) == 0:
            print "Landscape database already configured/updated"
            return
        check_call("setup-landscape-server")
    finally:
        conn.close()

def lock_install(host, admin_user, admin_password, user, password):
    """
    A simple mutex for installing and prepping the database.
    """
    try:
        conn = connect(database='postgres', host=host, user=admin_user,
                       password=admin_password)
    except Exception:
        print "Error connecting to database as %s" % admin_user
        sys.exit(1)

    try:
        cur = conn.cursor()
        cur.execute("select usename from pg_user where usename='%s'" % user)
        result = cur.fetchall()
        if not result:
            print "Creating landscape user"
            cur.execute("create user %s with password '%s'" % (user, password))
            conn.commit()
    finally:
        conn.close()


def create_user(host, admin_user, admin_password, user, password):
    """
    Create a user in the database.  Attempts to connect to the database
    first as the admin user just to check
    """
    try:
        conn = connect(database='postgres', host=host, user=admin_user,
                       password=admin_password)
    except Exception:
        print "Error connecting to database as %s" % admin_user
        sys.exit(1)

    try:
        cur = conn.cursor()
        cur.execute("select usename from pg_user where usename='%s'" % user)
        result = cur.fetchall()
        if not result:
            print "Creating landscape user"
            cur.execute("create user %s with password '%s'" % (user, password))
            conn.commit()
    finally:
        conn.close()


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
