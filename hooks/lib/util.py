"""
Utility library for juju hooks
"""

from psycopg2 import connect
from juju import Juju

juju = Juju()


def connect_exclusive(host, admin_user, admin_password):
    """
    database user creation and setup-landscape-server need to be done in a
    safe way so multiple units do not try to configure landscape at the same
    time.  This method succeeds on the first unit and fails on every other
    unit.
    """
    conn = connect(database="postgres", host=host, user=admin_user,
                   password=admin_password)
    try:
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE landscape_install_lock (id serial PRIMARY KEY);")
        cur.execute("LOCK landscape_install_lock IN ACCESS EXCLUSIVE MODE;")
        juju.juju_log("Mutex acquired on landscape_install_lock, Proceeding")
    except:
        juju.juju_log("Mutex acquire on landscape_install_lock failed.")
        conn.close()
        raise
    return conn


def create_user(conn, user, password):
    """Create a user in the database if one does not already exist."""
    cur = conn.cursor()
    cur.execute("SELECT usename FROM pg_user WHERE usename='%s'" % user)
    result = cur.fetchall()
    if not result:
        juju.juju_log("Creating landscape db user")
        cur.execute("CREATE user %s WITH PASSWORD '%s'" % (user, password))
        conn.commit()


def is_db_up(database, host, user, password):
    """
    Return True if the database relation is configured with write permission,
    False otherwise.
    """
    try:
        conn = connect(database="postgres", host=host, user=user,
                       password=password)
        cur = conn.cursor()
        # Ensure we are user with write access, to avoid hot standby dbs
        cur.execute(
            "CREATE TEMP TABLE write_access_test_%s (id serial PRIMARY KEY) "
            "ON COMMIT DROP;"
            % juju.local_unit().replace("/", "_"))
        return True
    except Exception as e:
        juju.juju_log(str(e))
        return False
    finally:
        try:
            conn.close()
        except:
            pass
