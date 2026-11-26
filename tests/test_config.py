from app import config
from app.config import Settings


def test_database_url_loads_from_project_dotenv_file(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DATABASE_URL=postgresql://db.invalid:5432/starter_test\n", encoding="utf-8")
    monkeypatch.setattr(config, "PROJECT_ROOT_ENV_FILE", env_file)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    settings = Settings.from_environment()

    assert settings.database_url == "postgresql://db.invalid:5432/starter_test"


def test_process_environment_database_url_takes_precedence_over_dotenv(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DATABASE_URL=postgresql://file.invalid:5432/starter_test\n", encoding="utf-8")
    monkeypatch.setattr(config, "PROJECT_ROOT_ENV_FILE", env_file)
    monkeypatch.setenv("DATABASE_URL", "postgresql://environment.invalid:5432/starter_test")

    settings = Settings.from_environment()

    assert settings.database_url == "postgresql://environment.invalid:5432/starter_test"
