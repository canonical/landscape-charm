"""
Utility library for juju hooks
"""

from psycopg2 import connect, Error as psycopg2Error
from juju import Juju
from contextlib import closing
from subprocess import check_output

import os

juju = Juju()


def connect_exclusive(host, admin_user, admin_password):
    """
    database user creation and setup-landscape-server need to be done in a
    safe way so multiple units do not try to configure landscape at the same
    time.  This method succeeds on the first unit and fails on every other
    unit.
    """
    table = "landscape_install_lock"
    conn = connect(database="postgres", host=host, user=admin_user,
                   password=admin_password)
    try:
        cur = conn.cursor()
        juju.juju_log("Gaining MUTEX on %s" % table)
        cur.execute(
            "CREATE TABLE IF NOT EXISTS %s (id serial PRIMARY KEY);" % table)
        cur.execute("LOCK %s IN ACCESS EXCLUSIVE MODE;" % table)
        juju.juju_log("MUTEX Acquired on %s, Proceeding" % table)
    except:
        juju.juju_log("MUTEX failed on %s." % table)
        conn.close()
        raise
    return conn


def create_user(user, password, host, admin_user, admin_password):
    """Create a user in the database if one does not already exist."""
    conn = connect(database="postgres", host=host, user=admin_user,
                   password=admin_password)
    try:
        cur = conn.cursor()
        cur.execute("SELECT usename FROM pg_user WHERE usename=%s", (user,))
        result = cur.fetchall()
        if not result:
            juju.juju_log("Creating postgres db user: %s" % user)
            cur.execute("CREATE user %s WITH PASSWORD '%s'" % (user, password))
            conn.commit()
    finally:
        conn.close()


def create_landscape_admin(db_user, db_password, db_host, admin_name,
                           admin_email, admin_password):
    """
    Create the first Landscape administrator. If successful, returns
    the API credentials as a tuple (key, secret). Otherwise, None.
    """
    with closing(connect(database="landscape-standalone-main", host=db_host,
                         user=db_user, password=db_password)) as conn:
        cur = conn.cursor()
        # make sure it's a blank account
        cur.execute("SELECT COUNT(person.id),COUNT(account.id) FROM "
                    "person,account")
        result = cur.fetchall()[0]
        if int(result[0]) == 0 and int(result[1]) == 0:
            juju.juju_log("Creating first administrator")
            env = os.environ.copy()
            env["LANDSCAPE_CONFIG"] = "standalone"
            cmd = ["./schema", "--create-lds-account-only", "--admin-name",
                   admin_name, "--admin-email", admin_email,
                   "--admin-password", admin_password]
            output = check_output(cmd, cwd="/opt/canonical/landscape", env=env)
            # XXX parse "output"
            return ("key", "secret")
        else:
            juju.juju_log("DB not empty, skipping first admin creation")


def change_root_url(database, user, password, host, url):
    """Change the root url in the database."""
    url = "u%s:%s" % (len(url), url)
    with closing(connect(database=database, host=host,
                         user=user, password=password)) as conn:
        cur = conn.cursor()
        cur.execute("SELECT encode(key, 'escape'),encode(value, 'escape') "
                    "FROM system_configuration "
                    "WHERE key='landscape.root_url' FOR UPDATE")
        result = cur.fetchall()
        if not result:
            juju.juju_log("Setting new root_url: %s" % url)
            cur.execute(
                "INSERT INTO system_configuration "
                "VALUES (decode('landscape.root_url', 'escape'), "
                "        decode(%s, 'escape'))", (url,))
        else:
            juju.juju_log("Updating root_url %s => %s" % (result, url))
            cur.execute(
                "UPDATE system_configuration "
                "SET key=decode('landscape.root_url', 'escape'),"
                "    value=decode(%s, 'escape') "
                "WHERE encode(key, 'escape')='landscape.root_url'", (url,))
        conn.commit()


def is_db_up(database, host, user, password):
    """
    Return True if the database relation is configured with write permission,
    False otherwise.
    """
    try:
        conn = connect_exclusive(host, user, password)
        cur = conn.cursor()
        # Ensure we are user with write access, to avoid hot standby dbs
        cur.execute(
            'CREATE TEMP TABLE "write_access_test_%s" (id serial PRIMARY KEY) '
            "ON COMMIT DROP" % juju.local_unit().replace("/", "_"))
    except psycopg2Error as e:
        juju.juju_log("Database not yet up: %s" % e)
        return False
    else:
        return True
    finally:
        try:
            conn.close()
        except:
            pass
