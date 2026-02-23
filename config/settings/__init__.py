from __future__ import annotations

from decouple import config

environment = config("DJANGO_ENV", default="dev").lower().strip()

if environment in {"prod", "production"}:
    from .prod import *  # noqa: F401,F403
else:
    from .dev import *  # noqa: F401,F403
