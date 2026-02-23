from __future__ import annotations

from pathlib import Path

from decouple import config

try:
    import dj_database_url
except ImportError:  # pragma: no cover - dependency is installed in production
    dj_database_url = None

def get_database_config(base_dir: Path) -> dict:
    """
    Dev: SQLite por padrão.
    Prod: Postgres via DATABASE_URL ou variáveis DB_*.
    """
    database_url = config("DATABASE_URL", default="").strip()
    if database_url:
        if dj_database_url is None:
            raise RuntimeError("DATABASE_URL definido, mas dj-database-url não está instalado.")
        return {
            "default": dj_database_url.parse(
                database_url,
                conn_max_age=config("DB_CONN_MAX_AGE", default=600, cast=int),
            )
        }

    engine = config("DB_ENGINE", default="sqlite").lower().strip()

    if engine == "postgres":
        name = config("DB_NAME")
        user = config("DB_USER")
        password = config("DB_PASSWORD")
        host = config("DB_HOST", default="127.0.0.1")
        port = config("DB_PORT", default="5432")
        sslmode = config("DB_SSLMODE", default="require").strip()

        options = {}
        if sslmode:
            options["sslmode"] = sslmode

        return {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": name,
                "USER": user,
                "PASSWORD": password,
                "HOST": host,
                "PORT": port,
                "CONN_MAX_AGE": config("DB_CONN_MAX_AGE", default=600, cast=int),
                "OPTIONS": options,
            }
        }

    # SQLite
    return {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": base_dir / config("SQLITE_PATH", default="db.sqlite3"),
        }
    }
