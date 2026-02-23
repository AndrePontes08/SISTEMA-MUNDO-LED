from __future__ import annotations

from dataclasses import dataclass
from django.conf import settings


@dataclass(frozen=True)
class PaginationParams:
    page: int
    page_size: int


def get_pagination_params(request) -> PaginationParams:
    """
    Paginação padrão: 20 itens; opções: 50 e 100.
    Querystring:
      ?page=2&page_size=50
    """
    default_size = getattr(settings, "PAGINATION_DEFAULT_SIZE", 20)
    allowed = set(getattr(settings, "PAGINATION_ALLOWED_SIZES", (20, 50, 100)))

    try:
        page = int(request.GET.get("page", "1"))
    except ValueError:
        page = 1

    try:
        page_size = int(request.GET.get("page_size", str(default_size)))
    except ValueError:
        page_size = default_size

    if page < 1:
        page = 1
    if page_size not in allowed:
        page_size = default_size

    return PaginationParams(page=page, page_size=page_size)
