from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Iterable


class NormalizacaoService:
    @staticmethod
    def decode_bytes(raw: bytes) -> str:
        for enc in ("utf-8", "cp1252", "latin-1"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="ignore")

    @staticmethod
    def normalizar_texto(value: str | None) -> str:
        if not value:
            return ""
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def normalizar_data_ofx(value: str | None) -> date | None:
        if not value:
            return None
        digits = "".join(ch for ch in value if ch.isdigit())
        if len(digits) < 8:
            return None
        try:
            return datetime.strptime(digits[:8], "%Y%m%d").date()
        except ValueError:
            return None

    @staticmethod
    def normalizar_decimal(value: str | None) -> Decimal:
        if value is None:
            return Decimal("0.00")
        txt = value.strip().replace(" ", "")
        if "," in txt and "." in txt:
            txt = txt.replace(".", "").replace(",", ".")
        else:
            txt = txt.replace(",", ".")
        try:
            return Decimal(txt).quantize(Decimal("0.01"))
        except InvalidOperation:
            return Decimal("0.00")

    @staticmethod
    def gerar_hash_idempotencia(partes: Iterable[str]) -> str:
        joined = "|".join((p or "").strip().lower() for p in partes)
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()

