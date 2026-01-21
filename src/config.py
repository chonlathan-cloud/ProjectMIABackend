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
    
    # Vertex AI
    vertex_ai_location: str = "us-central1"
    vertex_ai_model: str = "gemini-1.5-pro"
    vertex_ai_embedding_model: str = "text-embedding-004"
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",")]
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()
