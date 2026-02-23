from __future__ import annotations

import hashlib
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from compras.models import Produto
from financeiro.models import ContaBancaria
from estoque.models import EstoqueMovimento, UnidadeLoja


def caixa_pdf_upload_path(instance: "CaixaRelatorioImportacao", filename: str) -> str:
    digest = hashlib.sha1(filename.encode("utf-8", errors="ignore")).hexdigest()[:10]
    dt = instance.criado_em if getattr(instance, "criado_em", None) else timezone.now()
    return f"importadores/caixa_pdf/{dt:%Y/%m}/{digest}_{filename}"


class StatusImportacaoPDFChoices(models.TextChoices):
    SUCESSO = "SUCESSO", "Sucesso"
    PARCIAL = "PARCIAL", "Parcial"
    ERRO = "ERRO", "Erro"


class UnidadeContaFinanceiraConfig(models.Model):
    unidade = models.CharField(max_length=20, choices=UnidadeLoja.choices, unique=True)
    conta_bancaria = models.ForeignKey(
        ContaBancaria,
        on_delete=models.PROTECT,
        related_name="config_unidades",
    )
    ativa = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Config unidade x conta financeira"
        verbose_name_plural = "Config unidade x conta financeira"

    def __str__(self) -> str:
        return f"{self.get_unidade_display()} -> {self.conta_bancaria}"


class CaixaRelatorioImportacao(models.Model):
    data_referencia = models.DateField(db_index=True)
    unidade = models.CharField(max_length=20, choices=UnidadeLoja.choices, db_index=True)
    empresa_nome = models.CharField(max_length=120, blank=True, default="")

    arquivo_pdf = models.FileField(upload_to=caixa_pdf_upload_path)
    arquivo_nome = models.CharField(max_length=255, blank=True, default="")
    arquivo_hash = models.CharField(max_length=64, db_index=True)

    total_vendas = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total_trocas = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    vendas_detalhadas = models.JSONField(default=dict, blank=True)

    status = models.CharField(
        max_length=20,
        choices=StatusImportacaoPDFChoices.choices,
        default=StatusImportacaoPDFChoices.SUCESSO,
        db_index=True,
    )

    itens_detectados = models.PositiveIntegerField(default=0)
    itens_baixados = models.PositiveIntegerField(default=0)
    itens_inconsistentes = models.PositiveIntegerField(default=0)

    log_erro = models.TextField(blank=True, default="")
    observacoes = models.JSONField(default=list, blank=True)

    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="importacoes_caixa_pdf",
    )
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-data_referencia", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["arquivo_hash", "data_referencia", "unidade"],
                name="uniq_caixa_pdf_hash_data_unidade",
            )
        ]
        indexes = [
            models.Index(fields=["unidade", "data_referencia"], name="idx_caixa_pdf_unid_data"),
            models.Index(fields=["status", "criado_em"], name="idx_caixa_pdf_status_data"),
        ]

    def __str__(self) -> str:
        return f"Caixa PDF {self.data_referencia} - {self.unidade} - {self.total_vendas}"


class CaixaRelatorioItem(models.Model):
    importacao = models.ForeignKey(
        CaixaRelatorioImportacao,
        on_delete=models.CASCADE,
        related_name="itens",
    )
    codigo_mercadoria = models.CharField(max_length=50, db_index=True)
    descricao = models.CharField(max_length=255, blank=True, default="")
    quantidade = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0.000"))

    produto = models.ForeignKey(Produto, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    estoque_baixado = models.BooleanField(default=False)
    mensagem = models.CharField(max_length=255, blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        indexes = [
            models.Index(fields=["importacao", "codigo_mercadoria"], name="idx_caixa_item_imp_cod"),
        ]

    def __str__(self) -> str:
        return f"{self.codigo_mercadoria} x {self.quantidade}"


class CaixaImportacaoInconsistencia(models.Model):
    importacao = models.ForeignKey(
        CaixaRelatorioImportacao,
        on_delete=models.CASCADE,
        related_name="inconsistencias",
    )
    codigo = models.CharField(max_length=50, blank=True, default="")
    descricao = models.CharField(max_length=255)
    detalhes = models.TextField(blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"Inconsistencia {self.codigo or '-'}: {self.descricao}"


class MovimentoVendaEstoque(models.Model):
    """
    Trilho especifico para baixa por venda de PDF, sem alterar choices existentes de EstoqueMovimento.
    """

    importacao = models.ForeignKey(
        CaixaRelatorioImportacao,
        on_delete=models.CASCADE,
        related_name="movimentos_venda",
    )
    item = models.ForeignKey(CaixaRelatorioItem, on_delete=models.CASCADE, related_name="movimentos_venda")
    movimento_estoque = models.ForeignKey(
        EstoqueMovimento,
        on_delete=models.PROTECT,
        related_name="movimentos_venda_pdf",
    )
    unidade = models.CharField(max_length=20, choices=UnidadeLoja.choices, db_index=True)
    tipo = models.CharField(max_length=20, default="VENDA", db_index=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["item", "movimento_estoque"],
                name="uniq_mov_venda_item_mov",
            )
        ]
