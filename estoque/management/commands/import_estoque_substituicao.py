from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from compras.models import Produto
from estoque.models import ProdutoEstoque, ProdutoEstoqueUnidade, UnidadeLoja
from estoque.services.unidade_estoque_service import garantir_unidades_produto


@dataclass
class AggregatedRow:
    nome: str
    sku: str
    quantidade: Decimal
    custo_total: Decimal
    custo_medio_fallback: Decimal
    valor_venda_fallback: Decimal


def _dec(value) -> Decimal:
    raw = str(value or "").strip()
    if raw == "":
        return Decimal("0")
    if "." in raw and "," in raw:
        # formato 1.234,56
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        # formato 1234,56
        raw = raw.replace(",", ".")
    # se vier 1234.56 mantém como está
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return Decimal("0")


class Command(BaseCommand):
    help = "Substitui o estoque atual por um CSV (quantidade e custo médio por SKU)."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str, help="Caminho do CSV de estoque.")
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Zera os saldos atuais antes de carregar o CSV.",
        )
        parser.add_argument(
            "--create-missing",
            action="store_true",
            help="Cria produtos ausentes no cadastro quando SKU não existir.",
        )
        parser.add_argument(
            "--target-unit",
            choices=[UnidadeLoja.LOJA_1, UnidadeLoja.LOJA_2],
            default=UnidadeLoja.LOJA_1,
            help="Unidade que receberá o saldo importado quando o CSV não tiver coluna por unidade.",
        )
        parser.add_argument(
            "--same-in-both-units",
            action="store_true",
            help="Replica o mesmo saldo nas duas unidades (FM e ML).",
        )

    def _load_rows(self, csv_path: Path) -> dict[str, AggregatedRow]:
        raw = csv_path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except Exception:
            text = raw.decode("latin-1")

        sample = text[:4096]
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=";,").delimiter
        except Exception:
            delimiter = ";"

        reader = csv.DictReader(text.splitlines(), delimiter=delimiter)
        aggregated: dict[str, AggregatedRow] = {}
        for row in reader:
            sku = (row.get("SKU") or row.get("sku") or "").strip()
            nome = (row.get("Nome do Produto") or row.get("nome") or row.get("NOME") or "").strip()
            if not sku:
                continue
            reservado = _dec(row.get("Reservado") or row.get("reservado"))
            disponivel = _dec(row.get("Disponível") or row.get("disponivel") or row.get("Disponivel"))
            quantidade = reservado + disponivel
            custo_total = _dec(row.get("Custo Total") or row.get("custo_total") or row.get("CUSTO_TOTAL"))
            custo_medio = _dec(row.get("Custo Médio") or row.get("custo_medio") or row.get("CUSTO_MEDIO"))
            valor_venda = _dec(row.get("Valor de Venda") or row.get("valor_venda") or row.get("VALOR_VENDA"))

            existing = aggregated.get(sku)
            if existing is None:
                aggregated[sku] = AggregatedRow(
                    nome=nome or sku,
                    sku=sku,
                    quantidade=quantidade,
                    custo_total=custo_total,
                    custo_medio_fallback=custo_medio,
                    valor_venda_fallback=valor_venda,
                )
            else:
                existing.quantidade += quantidade
                existing.custo_total += custo_total
                if custo_medio > 0:
                    existing.custo_medio_fallback = custo_medio
                if valor_venda > 0:
                    existing.valor_venda_fallback = valor_venda
                if nome and len(nome) > len(existing.nome):
                    existing.nome = nome
        return aggregated

    def handle(self, *args, **options):
        csv_path = Path(options["csv_path"]).expanduser()
        if not csv_path.exists():
            raise CommandError(f"Arquivo não encontrado: {csv_path}")

        rows = self._load_rows(csv_path)
        if not rows:
            raise CommandError("Nenhuma linha válida encontrada no CSV.")

        if options["replace"]:
            ProdutoEstoque.objects.update(saldo_atual=Decimal("0.000"), custo_medio=Decimal("0.0000"))
            ProdutoEstoqueUnidade.objects.update(saldo_atual=Decimal("0.000"))

        created_products = 0
        updated_products = 0
        skipped = 0
        target_unit = options["target_unit"]
        other_unit = UnidadeLoja.LOJA_2 if target_unit == UnidadeLoja.LOJA_1 else UnidadeLoja.LOJA_1
        same_in_both_units = bool(options.get("same_in_both_units"))

        for idx, (sku, row) in enumerate(rows.items(), start=1):
            produto = Produto.objects.filter(sku=sku).first()
            if produto is None:
                if not options["create_missing"]:
                    skipped += 1
                    continue
                try:
                    produto = Produto.objects.create(nome=(row.nome or sku)[:255], sku=sku[:64], ativo=True)
                except Exception:
                    skipped += 1
                    continue
                created_products += 1

            garantir_unidades_produto(produto)
            cfg, _ = ProdutoEstoque.objects.get_or_create(produto=produto)

            quantidade = (row.quantidade or Decimal("0")).quantize(Decimal("0.001"))
            if quantidade < 0:
                quantidade = Decimal("0.000")

            if row.custo_total > 0 and quantidade > 0:
                custo_medio = (row.custo_total / quantidade).quantize(Decimal("0.0001"))
            elif row.custo_medio_fallback > 0:
                custo_medio = row.custo_medio_fallback.quantize(Decimal("0.0001"))
            elif row.valor_venda_fallback > 0:
                # Fallback operacional: quando custo vem zerado no CSV, usa valor de venda
                # para não deixar produto sem valor no estoque.
                custo_medio = row.valor_venda_fallback.quantize(Decimal("0.0001"))
            else:
                custo_medio = Decimal("0.0000")

            cfg.saldo_atual = quantidade
            if custo_medio >= 0:
                cfg.custo_medio = custo_medio
            cfg.save(update_fields=["saldo_atual", "custo_medio", "atualizado_em"])

            unidade_target, _ = ProdutoEstoqueUnidade.objects.get_or_create(produto=produto, unidade=target_unit)
            unidade_other, _ = ProdutoEstoqueUnidade.objects.get_or_create(produto=produto, unidade=other_unit)
            unidade_target.saldo_atual = quantidade
            unidade_target.save(update_fields=["saldo_atual", "atualizado_em"])
            unidade_other.saldo_atual = quantidade if same_in_both_units else Decimal("0.000")
            unidade_other.save(update_fields=["saldo_atual", "atualizado_em"])

            updated_products += 1
            if idx % 500 == 0:
                self.stdout.write(f" ... {idx}/{len(rows)} SKUs processados")

        self.stdout.write(self.style.SUCCESS("Importação de substituição concluída."))
        self.stdout.write(f"CSV lido: {csv_path}")
        self.stdout.write(f"SKUs processados: {len(rows)}")
        self.stdout.write(f"Produtos atualizados: {updated_products}")
        self.stdout.write(f"Produtos criados: {created_products}")
        self.stdout.write(f"SKUs ignorados (sem produto e sem --create-missing): {skipped}")
        if same_in_both_units:
            self.stdout.write("Saldo importado igualmente para as duas unidades (FM e ML).")
        else:
            self.stdout.write(f"Saldo importado para unidade: {target_unit}")
