from dataclasses import dataclass
from subprocess import CalledProcessError, check_call

from charms.data_platform_libs.v0.data_interfaces import DatabaseRequires

from helpers import get_modified_env_vars, logger


@dataclass
class DatabaseConnectionContext:
    host: str | None = None
    port: str | None = None
    username: str | None = None
    password: str | None = None
    version: str | None = None


@dataclass
class PostgresRoles:
    """
    Names of the relevant PostgreSQL roles for Landscape.
    """

    relation: str
    """
    The role created by the relation. Stored in `schema.store_user`.
    Ex. "relation-9"
    """
    application: str
    """
    The role that does application level database operations.
    Ex. "landscape"
    """
    owner: str
    """
    The role that owns the databases. This depends on the version of
    Charmed Postgres. On 14 and below, it is `postgres`. On 16+, it is
    `charmed_dba`.
    """
    superuser: str | None
    """
    The role that is escalated to become a superuser.
    Ex. "landscape_maintenance"
    """


def fetch_postgres_relation_data(
    db_manager: DatabaseRequires,
) -> DatabaseConnectionContext:
    """
    Get the required data from the Postgres relation helper.

    NOTE: Despite being named endpoint**s**, it's just one string
    of db_host:port.
    """
    relation_data = db_manager.fetch_relation_data()
    for data in relation_data.values():
        if not data:
            continue

        logger.info("New database endpoint is %s", data["endpoints"])
        host, port = data["endpoints"].split(":")

        return DatabaseConnectionContext(
            host=host,
            port=port,
            username=data["username"],
            password=data["password"],
            version=data["version"],
        )

    return DatabaseConnectionContext()


def get_postgres_owner_role_from_version(
    version: str,
) -> str:
    """
    Charmed Postgres 16 no longer has a role called `postgres`,
    so we use `charmed_dba` instead.
    """
    owner_role = "postgres"

    try:
        major = int(str(version).split(".", 1)[0])
    except ValueError:
        logger.warning("Unable to parse PostgreSQL version '%s'", version)
    else:
        if major >= 16:
            owner_role = "charmed_dba"

    return owner_role


def execute_psql(
    host: str,
    port: str,
    relation_user: str,
    relation_password: str,
    sql: str,
    database: str = "postgres",
) -> None:
    """
    :raises `CalledProcessError`: The command failed.
    """
    cmd = [
        "psql",
        "-h",
        host,
        "-p",
        port,
        "-U",
        relation_user,
        "-d",
        database,
        "-c",
        sql,
    ]

    env = get_modified_env_vars()
    env["PGPASSWORD"] = relation_password

    try:
        check_call(cmd, env=env)
    except CalledProcessError as e:
        logger.error(
            "Running `psql` failed: (exit %s): %s",
            e.returncode,
            e,
        )
        raise e


def grant_role(
    host: str,
    port: str,
    relation_user: str,
    relation_password: str,
    user: str,
    role: str,
) -> None:
    """
    Because Charmed Postgres 16 now forces us to use one of the existing
    roles, we have to grant it to the `landscape` (application) Postgres
    user.

    NOTE: We cannot manually add it to the `pg_hba.conf` because it's generated
    by Patroni.

    :raises `CalledProcessError`: Granting the role failed.
    """
    sql = f"GRANT {role} TO {user};"

    try:
        execute_psql(
            host=host,
            port=port,
            relation_user=relation_user,
            relation_password=relation_password,
            sql=sql,
        )

    except CalledProcessError as e:
        logger.error(
            "Failed to grant %s to %s (exit %s): %s",
            role,
            user,
            e.returncode,
            e,
        )
        raise e
