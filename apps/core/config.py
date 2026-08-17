from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    GEMINI_API_KEY1: str = ''
    GEMINI_API_KEY2: str = ''
    DEEPSEEK_API_KEY1: str = ''
    DEEPSEEK_API_KEY2: str = ''
    GROQ_API_KEY1: str = ''
    GROQ_API_KEY2: str = ''
    GROQ_API_KEY3: str = ''

    # Which provider backs the planner. Only providers with real code behind
    # them belong here -- see apps/services/providers.py.
    AI_PROVIDER: str = 'gemini'
    # 'gemini-flash-latest' is a rolling alias -- pinning an exact dated
    # model (e.g. gemini-2.0-flash) goes stale as Google deprecates versions.
    GEMINI_MODEL: str = 'gemini-flash-latest'
    DEEPSEEK_MODEL: str = 'deepseek-chat'
    # Groq's compound systems have built-in web search (via Tavily) and
    # decide per-query whether to invoke it -- used only by the project
    # assistant (apps/services/providers/groq.py), never the planner above.
    GROQ_MODEL: str = 'groq/compound-mini'

    # Shared secret Django's Celery worker must send; keeps this service from
    # being invoked (and burning LLM credits) by anything else that can
    # reach it on the network. Empty means "no check" -- fine for local dev,
    # must be set in any real deployment.
    SERVICE_AUTH_TOKEN: str = ''

    REQUEST_TIMEOUT_SECONDS: float = 60.0

    model_config = SettingsConfigDict(env_file=str(BASE_DIR / '.env'), extra='ignore')


settings = Settings()
