"""
Utility library for juju hooks
"""

from contextlib import closing
from subprocess import check_call
from psycopg2 import connect, IntegrityError
import sys
from juju import Juju

juju = Juju()


def setup_landscape_server(host, admin_user, admin_password):
    """
    Wrapper around setup-landscape-server.  We need to do this in a safe way in
    a distributed environment since multiple landscape servers could be
    accessing the database at the same time.
    """
    with closing(connect(database="postgres", host=host, user=admin_user,
                         password=admin_password)) as conn:
        with closing(conn.cursor()) as cursor:
            try:
                cursor.execute(
                    "CREATE TABLE IF NOT EXISTS "
                    "landscape_install_lock (id serial PRIMARY KEY)")
            except IntegrityError:
                # Two CREATE TABLE statements can conflict even with
                # the IF NOT EXISTS clause
                conn.rollback()
            else:
                conn.commit()
        with closing(conn.cursor()) as cursor:
            cursor.execute(
                "LOCK landscape_install_lock IN ACCESS EXCLUSIVE MODE")
            juju.juju_log(
                "Mutex acquired on landscape_install_lock, Proceeding")
            check_call("setup-landscape-server")


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
        cur.execute("SELECT usename FROM pg_user WHERE usename=%s", (user, ))
        result = cur.fetchall()
        if not result:
            print "Creating landscape user"
            cur.execute(
                "CREATE USER %s WITH PASSWORD %%s" % user, (password, ))
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
