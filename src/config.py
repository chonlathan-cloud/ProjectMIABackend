from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Database
    db_url: str
    
    # Google Cloud
    google_application_credentials: str
    google_cloud_project: str
    pubsub_topic_incoming: str = "line-incoming-events"
    pubsub_subscription_incoming: str = "line-incoming-events-sub"
    gcs_bucket_name: str

    # Firebase
    firebase_credentials_path: str
    
    # API Configuration
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    api_prefix: str = "/api"

    # Debug
    debug: bool = True
    port: int = 8000

    # Vertex AI
    vertex_ai_location: str = "us-central1"
    vertex_ai_model: str = "gemini-1.5-pro"
    vertex_ai_embedding_model: str = "text-embedding-004"

    # JWT
    jwt_secret: str
    jwt_issuer: str = "mia-core"
    jwt_exp_minutes: int = 60
    jwt_refresh_days: int = 7
    refresh_cookie_name: str = "cb_refresh_token"
    cookie_secure: bool = True
    cookie_samesite: str = "none"

    # LINE Login
    line_login_channel_id: str = ""
    line_login_channel_secret: str = ""
    line_login_redirect_uri: str = ""
    frontend_base_url: str = ""
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",")]
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()
