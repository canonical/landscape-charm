"""
Utility library for juju hooks
"""

from hashlib import md5
from subprocess import check_output, check_call
from ConfigParser import RawConfigParser
from psycopg2 import connect
import sys
from juju import Juju

config_file = "/etc/landscape/service.conf"
juju = Juju()

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
    accessing the database at the same time.
    """
    conn = connect(database='postgres', host=host, user=admin_user,
                   password=admin_password)
    try:
        cur = conn.cursor()
        cur.execute(
                "CREATE TABLE landscape_install_lock (id serial PRIMARY KEY);")
        cur.execute("LOCK landscape_install_lock IN ACCESS EXCLUSIVE MODE;")
        juju.juju_log("Mutex acquired on landscape_install_lock, Proceeding")
        check_call("setup-landscape-server")
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
