from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    db_user: str = "qrate"
    db_password: str = "localpassword"
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "menucrawler"

    # AWS
    aws_region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    bedrock_model_id: str = "anthropic.claude-sonnet-4-5"
    titan_embedding_model_id: str = "amazon.titan-embed-text-v2:0"
    bedrock_endpoint: str = ""  # empty = use real AWS Bedrock

    # DynamoDB
    dynamodb_sessions_table: str = "recommendation-sessions-dev"
    dynamodb_endpoint: str = ""  # empty = use real AWS DynamoDB

    # Cognito
    cognito_user_pool_id: str = ""
    cognito_app_client_id: str = ""
    cognito_region: str = "us-east-1"

    # Environmental APIs
    weather_api_key: str = ""
    predicthq_api_key: str = ""

    # Service
    port: int = 8004
    environment: str = "dev"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
