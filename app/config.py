import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


@dataclass(frozen=True)
class Settings:
    azure_openai_endpoint: str
    azure_openai_deployment: str
    azure_openai_api_version: str
    azure_openai_api_key: str
    database_url: str
    lead_time_days: int = 3
    request_timeout_seconds: float = 30.0
    llm_max_attempts: int = 3
    azure_openai_embedding_deployment: str = ""
    discount_tiers: str = "9:0,49:5,199:8,*:12"
    free_delivery_threshold_inr: Decimal = Decimal("50000")
    delivery_charge_inr: Decimal = Decimal("1500")
    quote_validity_days: int = 7

    @classmethod
    def from_environment(cls) -> "Settings":
        # Keep OS-provided variables authoritative while loading project config
        # when the application is started without Uvicorn's --env-file option.
        load_dotenv(dotenv_path=PROJECT_ROOT_ENV_FILE, override=False)
        return cls(
            azure_openai_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", ""),
            azure_openai_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", ""),
            azure_openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION", ""),
            azure_openai_api_key=os.getenv("AZURE_OPENAI_API_KEY", ""),
            database_url=os.getenv("DATABASE_URL", ""),
            lead_time_days=int(os.getenv("LEAD_TIME_DAYS", "3")),
            request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")),
            llm_max_attempts=int(os.getenv("LLM_MAX_ATTEMPTS", "3")),
            azure_openai_embedding_deployment=os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", ""),
            discount_tiers=os.getenv("DISCOUNT_TIERS", "9:0,49:5,199:8,*:12"),
            free_delivery_threshold_inr=Decimal(os.getenv("FREE_DELIVERY_THRESHOLD_INR", "50000")),
            delivery_charge_inr=Decimal(os.getenv("DELIVERY_CHARGE_INR", "1500")),
            quote_validity_days=int(os.getenv("QUOTE_VALIDITY_DAYS", "7")),
        )

    def validate_azure(self) -> None:
        missing = [
            name
            for name, value in (
                ("AZURE_OPENAI_ENDPOINT", self.azure_openai_endpoint),
                ("AZURE_OPENAI_DEPLOYMENT", self.azure_openai_deployment),
                ("AZURE_OPENAI_API_VERSION", self.azure_openai_api_version),
                ("AZURE_OPENAI_API_KEY", self.azure_openai_api_key),
                ("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", self.azure_openai_embedding_deployment),
            )
            if not value
        ]
        if missing:
            raise ValueError("Azure OpenAI configuration is incomplete: " + ", ".join(missing))

    def validate_database(self) -> None:
        if not self.database_url:
            raise ValueError("DATABASE_URL is not configured")

    def discount_percent(self, quantity: int) -> int:
        for limit, percent in (part.split(":", 1) for part in self.discount_tiers.split(",")):
            if limit == "*" or quantity <= int(limit):
                return int(percent)
        raise ValueError("DISCOUNT_TIERS has no default tier")
