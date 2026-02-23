from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal
from typing import IO, List, Optional

from django.db import transaction
from django.utils.dateparse import parse_date

from compras.models import Fornecedor, Produto, Compra, ItemCompra, CentroCustoChoices, FornecedorAlias
from core.services.normalizacao import normalizar_nome


@dataclass
class ImportResult:
    compras_criadas: int
    itens_criados: int
    fornecedores_criados: int
    produtos_criados: int
    erros: List[str]


def _get_or_create_fornecedor(nome: str) -> Fornecedor:
    nome = (nome or "").strip()
    norm = normalizar_nome(nome)
    if not norm:
        raise ValueError("Fornecedor vazio")

    # 1) tenta alias
    alias = FornecedorAlias.objects.select_related("principal").filter(nome_normalizado=norm).first()
    if alias:
        return alias.principal

    # 2) tenta principal
    obj = Fornecedor.objects.filter(nome_normalizado=norm).first()
    if obj:
        return obj

    return Fornecedor.objects.create(nome=nome)


def _get_or_create_produto(nome: str, sku: str = "") -> Produto:
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("Produto vazio")
    sku = (sku or "").strip()

    if sku:
        obj = Produto.objects.filter(sku=sku).first()
        if obj:
            return obj

    norm = normalizar_nome(nome)
    obj = Produto.objects.filter(nome_normalizado=norm).first()
    if obj:
        return obj

    return Produto.objects.create(nome=nome, sku=sku)


@transaction.atomic
def import_compras_csv(file: IO[str]) -> ImportResult:
    """
    CSV esperado (colunas):
      data_compra (YYYY-MM-DD), centro_custo (FM/ML/PESSOAL/FM/ML/OUTROS),
      fornecedor, produto, sku(opcional), quantidade, preco_unitario
    Cada linha = 1 item (agrupado por data+centro_custo+fornecedor).
    """
    reader = csv.DictReader(file)
    compras_map = {}  # key -> Compra
    compras_criadas = itens_criados = fornecedores_criados = produtos_criados = 0
    erros: List[str] = []

    for i, row in enumerate(reader, start=2):
        try:
            data_compra = parse_date((row.get("data_compra") or "").strip())
            if not data_compra:
                raise ValueError("data_compra inválida")

            centro = (row.get("centro_custo") or "").strip()
            if centro not in CentroCustoChoices.values:
                raise ValueError(f"centro_custo inválido: {centro}")

            fornecedor_nome = (row.get("fornecedor") or "").strip()
            fornecedor = _get_or_create_fornecedor(fornecedor_nome)

            produto_nome = (row.get("produto") or "").strip()
            sku = (row.get("sku") or "").strip()
            produto = _get_or_create_produto(produto_nome, sku=sku)

            quantidade = Decimal((row.get("quantidade") or "0").replace(",", "."))
            preco = Decimal((row.get("preco_unitario") or "0").replace(",", "."))

            key = (data_compra.isoformat(), centro, fornecedor.id)
            compra = compras_map.get(key)
            if not compra:
                compra = Compra.objects.create(
                    fornecedor=fornecedor,
                    centro_custo=centro,
                    data_compra=data_compra,
                    observacoes="Importado via CSV",
                )
                compras_map[key] = compra
                compras_criadas += 1

            ItemCompra.objects.create(
                compra=compra,
                produto=produto,
                quantidade=quantidade,
                preco_unitario=preco,
            )
            itens_criados += 1

        except Exception as e:
            erros.append(f"Linha {i}: {e}")

    # Recalcula totals de todas as compras importadas
    for compra in compras_map.values():
        total = Decimal("0.00")
        for it in compra.itens.all():
            total += (it.quantidade or Decimal("0")) * (it.preco_unitario or Decimal("0"))
        compra.valor_total = total.quantize(Decimal("0.01"))
        compra.save(update_fields=["valor_total"])

    # Contagens aproximadas de fornecedores/produtos criados (não rastreamos aqui com precisão sem mais queries)
    # Mantemos como 0 por default para não mentir.
    return ImportResult(
        compras_criadas=compras_criadas,
        itens_criados=itens_criados,
        fornecedores_criados=fornecedores_criados,
        produtos_criados=produtos_criados,
        erros=erros,
    )
