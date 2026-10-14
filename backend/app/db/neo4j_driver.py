from neo4j import GraphDatabase, Driver
from app.config import get_settings
import logging

logger = logging.getLogger(__name__)

_driver: Driver | None = None


def get_driver() -> Driver:
    global _driver
    if _driver is None:
        settings = get_settings()
        _driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            max_connection_lifetime=3600,
            max_connection_pool_size=50,
        )
        logger.info(f"Neo4j driver created → {settings.neo4j_uri}")
    return _driver


def close_driver():
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None
        logger.info("Neo4j driver closed")


def get_session():
    """Dependency-injectable session factory."""
    settings = get_settings()
    driver = get_driver()
    with driver.session(database=settings.neo4j_database) as session:
        yield session


def verify_connectivity() -> dict:
    """Ping Neo4j and return server info."""
    driver = get_driver()
    driver.verify_connectivity()
    info = driver.get_server_info()
    return {
        "status": "connected",
        "address": str(info.address),
        "agent": info.agent,
        "protocol_version": str(info.protocol_version),
    }
