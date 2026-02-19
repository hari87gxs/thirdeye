import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    PROJECT_NAME: str = "Third Eye"
    VERSION: str = "1.0.0"
    API_PREFIX: str = "/api"

    # Database — use /app/data for persistence with Docker volumes
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "sqlite:////app/data/third_eye.db",
    )

    # Azure OpenAI
    AZURE_OPENAI_API_KEY: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    AZURE_OPENAI_ENDPOINT: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    AZURE_OPENAI_API_VERSION: str = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
    AZURE_OPENAI_DEPLOYMENT: str = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
    AZURE_OPENAI_VISION_DEPLOYMENT: str = os.getenv("AZURE_OPENAI_VISION_DEPLOYMENT", "gpt-4o")

    # File upload
    UPLOAD_DIR: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
    MAX_FILE_SIZE_MB: int = 50

    # JWT Authentication
    JWT_SECRET: str = os.getenv("JWT_SECRET", "thirdeye-dev-secret-change-in-production")
    JWT_EXPIRY_HOURS: int = int(os.getenv("JWT_EXPIRY_HOURS", "72"))

    # PDF Processing
    PDF_TO_IMAGE_DPI: int = 200
    CHECK_SPECIFIC_DPI: dict = {
        "document_dimension": 300,
        "page_clarity": 300,
        "sharpness_spread": 300,
        "visual_tampering": 150,
        "page_count_discrepancy": 100,
    }

    # Tampering thresholds
    DIMENSION_MIN_HEIGHT: int = 800
    DIMENSION_MIN_WIDTH: int = 1000
    SHARPNESS_THRESHOLD: float = 500.0
    SHARPNESS_SPREAD_RATIO: float = 0.5
    SHARPNESS_MAX_STD_DEV: float = 100.0

    # CORS — set ALLOWED_ORIGINS env var as comma-separated URLs for production
    # e.g. ALLOWED_ORIGINS=https://thirdeye.example.com,http://localhost:3000
    ALLOWED_ORIGINS: list = [
        x.strip()
        for x in os.getenv(
            "ALLOWED_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001,http://thirdeye-ec2-alb-1720575765.ap-southeast-1.elb.amazonaws.com"
        ).split(",")
    ]


settings = Settings()

# Ensure upload directory exists
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
