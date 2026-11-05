from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    mode: str = 'DEMO'
    database_url: str = 'postgresql+psycopg://evidence:evidence@localhost:5541/evidence'
    provider: str = 'openai'
    model: str = 'gpt-4.1-mini'
    openai_api_key: str = Field(default='', repr=False)
    gemini_api_key: str = Field(default='', repr=False)
    embedding_model: str = 'text-embedding-3-small'
    embedding_dimensions: int = Field(default=1536, ge=1, le=3072)
    model_timeout: float = Field(default=30, gt=0, le=120)
    model_concurrency: int = Field(default=4, ge=1, le=16)
    max_output_tokens: int = Field(default=1200, ge=1, le=8192)
    temperature: float = Field(default=0.1, ge=0, le=2)
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
        elif not self.supports_generation():
            missing.append('MODEL is outside the reviewed structured-streaming capability profiles')
        if self.embedding_model not in {'text-embedding-3-small', 'text-embedding-3-large'}:
            missing.append('EMBEDDING_MODEL must support the dimensions parameter (text-embedding-3-small/large)')
        elif self.embedding_model == 'text-embedding-3-small' and self.embedding_dimensions > 1536:
            missing.append('text-embedding-3-small supports at most 1536 dimensions')
        return missing

    def supports_generation(self) -> bool:
        """Reviewed request profiles; arbitrary model names are not evidence of capability."""
        if self.provider == 'openai':
            return self.model in {
                'gpt-4.1', 'gpt-4.1-mini', 'gpt-4.1-nano',
                'gpt-4.1-2025-04-14', 'gpt-4.1-mini-2025-04-14', 'gpt-4.1-nano-2025-04-14',
                'gpt-4o', 'gpt-4o-2024-08-06', 'gpt-4o-2024-11-20',
                'gpt-4o-mini', 'gpt-4o-mini-2024-07-18',
            }
        return self.provider == 'gemini' and self.model in {'gemini-2.5-flash', 'gemini-2.5-pro'}


@lru_cache
def settings() -> Settings:
    return Settings()
