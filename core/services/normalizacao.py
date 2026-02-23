from __future__ import annotations

import re
import unicodedata


_SPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]")


def normalizar_nome(valor: str) -> str:
    """
    - Remove acentos
    - Padroniza espaços
    - Remove pontuação (mantém letras/números/_)
    - Uppercase
    """
    if valor is None:
        return ""
    valor = str(valor).strip()
    if not valor:
        return ""

    # Remove acentos
    nfkd = unicodedata.normalize("NFKD", valor)
    sem_acentos = "".join(ch for ch in nfkd if not unicodedata.combining(ch))

    # Remove pontuação
    sem_pontuacao = _PUNCT_RE.sub(" ", sem_acentos)

    # Normaliza espaços
    sem_pontuacao = _SPACE_RE.sub(" ", sem_pontuacao).strip()

    return sem_pontuacao.upper()
