"""Configuration lue dans les variables d'environnement (voir .env.example)."""
import os


def _env(nom, defaut=""):
    return os.environ.get(nom, defaut).strip()


DATABASE_URL = _env("DATABASE_URL", "sqlite:///./local.db")
# Supabase/Render donnent "postgres://..." ou "postgresql://..." : on force le pilote psycopg
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgresql://"):]

ACCESS_CODE = _env("ACCESS_CODE")  # vide = pas de protection (utile en local)
FMP_API_KEY = _env("FMP_API_KEY")
ALPHAVANTAGE_API_KEY = _env("ALPHAVANTAGE_API_KEY")
TWELVEDATA_API_KEY = _env("TWELVEDATA_API_KEY")
SEC_USER_AGENT = _env('SEC_USER_AGENT')

# Limites quotidiennes des offres gratuites (modifiables sans toucher au code)
LIMITS = {
    "fmp": int(_env("FMP_DAILY_LIMIT", "250")),
    "alphavantage": int(_env("ALPHAVANTAGE_DAILY_LIMIT", "25")),
    "twelvedata": max(0, int(_env("TWELVEDATA_DAILY_LIMIT", "800"))),
}

# Passe a "true" si tu prends un jour une offre FMP qui couvre les bourses hors Etats-Unis
FMP_COVERS_WORLD = _env("FMP_COVERS_WORLD", "false").lower() == "true"

STATIC_DIR = _env("STATIC_DIR")  # dossier de l'interface compilee (rempli par le Dockerfile)

CRON_SECRET = _env('CRON_SECRET')
VAPID_PUBLIC_KEY = _env('VAPID_PUBLIC_KEY')
VAPID_PRIVATE_KEY = _env('VAPID_PRIVATE_KEY')
VAPID_SUBJECT = _env('VAPID_SUBJECT')

GEMINI_API_KEY = _env('GEMINI_API_KEY')
GEMINI_MODEL = _env('GEMINI_MODEL', 'gemini-2.5-flash')
LIMITS['gemini'] = max(0, int(_env('GEMINI_DAILY_LIMIT', '10')))
