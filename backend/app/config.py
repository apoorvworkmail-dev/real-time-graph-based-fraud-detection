from typing import Optional
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "fraud2024pass"
    neo4j_database: str = "neo4j"
    app_env: str = "development"
    app_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173,http://127.0.0.1:3000"

    # Phase 10 — Security & JWT Authentication
    jwt_secret_key: str = "dev-secret-key-change-in-production-min-32-chars-long-1234567890"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "fraudgraph-api"
    jwt_audience: str = "fraudgraph-client"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    cookie_secure: bool = False  # Set to True in production HTTPS
    cookie_samesite: str = "lax"
    initial_admin_username: str = "admin"
    initial_admin_password: Optional[str] = None
    initial_admin_email: str = "admin@example.com"
    allow_public_read_in_dev: bool = False


    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()

