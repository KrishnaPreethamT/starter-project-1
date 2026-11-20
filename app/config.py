import os
from dataclasses import dataclass


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

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            azure_openai_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", ""),
            azure_openai_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", ""),
            azure_openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION", ""),
            azure_openai_api_key=os.getenv("AZURE_OPENAI_API_KEY", ""),
            database_url=os.getenv(
                "DATABASE_URL",
                "postgresql://starter:starter@localhost:5432/starter_project_1",
            ),
            lead_time_days=int(os.getenv("LEAD_TIME_DAYS", "3")),
            request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")),
            llm_max_attempts=int(os.getenv("LLM_MAX_ATTEMPTS", "3")),
        )

    def validate_azure(self) -> None:
        missing = [
            name
            for name, value in (
                ("AZURE_OPENAI_ENDPOINT", self.azure_openai_endpoint),
                ("AZURE_OPENAI_DEPLOYMENT", self.azure_openai_deployment),
                ("AZURE_OPENAI_API_VERSION", self.azure_openai_api_version),
                ("AZURE_OPENAI_API_KEY", self.azure_openai_api_key),
            )
            if not value
        ]
        if missing:
            raise ValueError("Azure OpenAI configuration is incomplete: " + ", ".join(missing))
