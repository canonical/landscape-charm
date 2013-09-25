"""
Utility library for juju hooks
"""

from subprocess import check_call
from psycopg2 import connect
import sys
from juju import Juju

juju = Juju()


def setup_landscape_server(host, admin_user, admin_password):
    """
    Wrapper around setup-landscape-server.  I need to do this in a safe way in
    a distributed environment since multiple landscape servers could be
    accessing the database at the same time.
    """
    conn = connect(database="postgres", host=host, user=admin_user,
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
        conn = connect(database="postgres", host=host, user=admin_user,
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


def is_db_up(database, host, user, password):
    """
    Return True if the database relation is configured, False otherwise.
    """
    try:
        conn = connect(database="postgres", host=host, user=user,
                       password=password)
        conn.cursor()
        return True
    except Exception as e:
        juju.juju_log(str(e))
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass
