from dataclasses import dataclass

from charms.data_platform_libs.v0.data_interfaces import (
    DatabaseRequires,
)

from helpers import logger


@dataclass
class DatabaseConnectionContext:
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None


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
        )

    return DatabaseConnectionContext()
