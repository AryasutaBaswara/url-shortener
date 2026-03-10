from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_ENV: str = "development"
    DATABASE_URL: str = "postgresql://user:password@localhost:5433/urlshortener"
    REDIS_URL: str = "redis://localhost:6379/0"
    KEYCLOAK_URL: str = "http://localhost:8081"
    KEYCLOAK_REALM: str = "your_realm"
    KEYCLOAK_CLIENT_ID: str = "your_client_id"

    model_config = SettingsConfigDict(
        extra="ignore"
    )

settings = Settings()