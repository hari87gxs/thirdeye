import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    PROJECT_NAME: str = "Third Eye"
    VERSION: str = "1.0.0"
    API_PREFIX: str = "/api"

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./third_eye.db")

    # Azure OpenAI
    AZURE_OPENAI_API_KEY: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    AZURE_OPENAI_ENDPOINT: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    AZURE_OPENAI_API_VERSION: str = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
    AZURE_OPENAI_DEPLOYMENT: str = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
    AZURE_OPENAI_VISION_DEPLOYMENT: str = os.getenv("AZURE_OPENAI_VISION_DEPLOYMENT", "gpt-4o")

    # File upload
    UPLOAD_DIR: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
    MAX_FILE_SIZE_MB: int = 50

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

    # CORS
    ALLOWED_ORIGINS: list = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


settings = Settings()

# Ensure upload directory exists
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
