from __future__ import annotations

from typing import Optional, Type

from django.db.models import Model, Q

from core.services.normalizacao import normalizar_nome


def resolver_por_alias_ou_nome(
    *,
    alias_model: Type[Model],
    main_model: Type[Model],
    nome: str,
    alias_field: str = "nome_normalizado",
    main_field: str = "nome_normalizado",
) -> Optional[Model]:
    """
    Função genérica:
    - normaliza nome
    - procura no Alias primeiro (alias_model -> main FK)
    - depois procura no principal
    Retorna instância do main_model.
    """
    n = normalizar_nome(nome)
    if not n:
        return None

    # Alias deve ter FK "principal" por convenção (será garantido nos apps)
    alias_q = {alias_field: n}
    alias_obj = alias_model.objects.select_related("principal").filter(**alias_q).first()
    if alias_obj and getattr(alias_obj, "principal_id", None):
        return getattr(alias_obj, "principal")

    main_q = {main_field: n}
    return main_model.objects.filter(**main_q).first()


def resolver_ou_criar_principal(
    *,
    main_model: Type[Model],
    nome: str,
    nome_field_raw: str = "nome",
    nome_field_norm: str = "nome_normalizado",
) -> Model:
    """
    Resolve pelo nome normalizado; se não existir, cria.
    """
    n = normalizar_nome(nome)
    qs = main_model.objects.filter(**{nome_field_norm: n})
    obj = qs.first()
    if obj:
        return obj

    payload = {
        nome_field_raw: nome.strip(),
        nome_field_norm: n,
    }
    return main_model.objects.create(**payload)
