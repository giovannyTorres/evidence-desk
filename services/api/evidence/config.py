from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    mode: str = 'DEMO'
    database_url: str = 'postgresql+psycopg://evidence:evidence@localhost:5541/evidence'
    provider: str = 'openai'
    model: str = 'gpt-4.1-mini'
    openai_api_key: str = ''
    gemini_api_key: str = ''
    embedding_model: str = 'text-embedding-3-small'
    embedding_dimensions: int = 1536
    model_timeout: float = 30
    model_concurrency: int = 4
    max_output_tokens: int = 1200
    temperature: float = 0.1
    public_origin: str = 'http://localhost:3101'
    cookie_secure: bool = False
    demo_login_enabled: bool = True
    max_upload_bytes: int = 5 * 1024 * 1024
    otel_enabled: bool = True
    otel_console: bool = False

    def missing(self) -> list[str]:
        if self.mode not in {'DEMO', 'LIVE'}:
            return ['MODE must be DEMO or LIVE']
        if self.mode == 'DEMO':
            return []
        missing = []
        if self.provider not in {'openai', 'gemini'}:
            missing.append('PROVIDER must be openai or gemini')
        if not self.openai_api_key:
            missing.append('OPENAI_API_KEY (embeddings and OpenAI generation)')
        if self.provider == 'gemini' and not self.gemini_api_key:
            missing.append('GEMINI_API_KEY')
        if not self.model:
            missing.append('MODEL')
        return missing


@lru_cache
def settings() -> Settings:
    return Settings()
