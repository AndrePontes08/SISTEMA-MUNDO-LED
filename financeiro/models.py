from __future__ import annotations

import hashlib
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


def ofx_upload_path(instance: "ExtratoImportacao", filename: str) -> str:
    digest = hashlib.sha1(filename.encode("utf-8", errors="ignore")).hexdigest()[:10]
    dt = instance.criado_em if getattr(instance, "criado_em", None) else timezone.now()
    return f"financeiro/ofx/{dt:%Y/%m}/{digest}_{filename}"


class TipoContaChoices(models.TextChoices):
    CORRENTE = "CORRENTE", "Corrente"
    POUPANCA = "POUPANCA", "Poupanca"
    OUTRA = "OUTRA", "Outra"


class StatusImportacaoChoices(models.TextChoices):
    PREVIEW = "PREVIEW", "Preview"
    SUCESSO = "SUCESSO", "Sucesso"
    PARCIAL = "PARCIAL", "Parcial"
    ERRO = "ERRO", "Erro"


class TipoMovimentoChoices(models.TextChoices):
    ENTRADA = "ENTRADA", "Entrada"
    SAIDA = "SAIDA", "Saida"


class StatusConciliacaoChoices(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    SUGERIDA = "SUGERIDA", "Sugerida"
    CONCILIADA = "CONCILIADA", "Conciliada"
    DIVERGENTE = "DIVERGENTE", "Divergente"
    IGNORADA = "IGNORADA", "Ignorada"


class StatusRecebivelChoices(models.TextChoices):
    ABERTO = "ABERTO", "Aberto"
    RECEBIDO = "RECEBIDO", "Recebido"
    CANCELADO = "CANCELADO", "Cancelado"


class ContaBancaria(models.Model):
    nome = models.CharField(max_length=120)
    banco_codigo = models.CharField(max_length=10, blank=True, default="")
    banco_nome = models.CharField(max_length=120, blank=True, default="")
    agencia = models.CharField(max_length=20)
    conta_numero = models.CharField(max_length=30)
    conta_digito = models.CharField(max_length=5, blank=True, default="")
    tipo_conta = models.CharField(
        max_length=20,
        choices=TipoContaChoices.choices,
        default=TipoContaChoices.CORRENTE,
    )
    ativa = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["banco_codigo", "agencia", "conta_numero", "conta_digito"],
                name="uniq_fin_conta_banco_ag_conta",
            )
        ]
        indexes = [
            models.Index(fields=["banco_nome"], name="idx_fin_conta_banco_nome"),
            models.Index(fields=["conta_numero"], name="idx_fin_conta_numero"),
        ]

    def __str__(self) -> str:
        banco = self.banco_nome or self.banco_codigo or "Banco"
        digito = f"-{self.conta_digito}" if self.conta_digito else ""
        return f"{self.nome} ({banco} ag {self.agencia} cc {self.conta_numero}{digito})"


class ExtratoImportacao(models.Model):
    conta = models.ForeignKey(
        ContaBancaria,
        on_delete=models.PROTECT,
        related_name="importacoes",
        blank=True,
        null=True,
    )
    banco_codigo = models.CharField(max_length=10, blank=True, default="")
    banco_nome = models.CharField(max_length=120, blank=True, default="")
    arquivo = models.FileField(upload_to=ofx_upload_path)
    arquivo_nome = models.CharField(max_length=255, blank=True, default="")
    arquivo_sha256 = models.CharField(max_length=64, db_index=True)
    periodo_inicio = models.DateField(blank=True, null=True)
    periodo_fim = models.DateField(blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=StatusImportacaoChoices.choices,
        default=StatusImportacaoChoices.PREVIEW,
        db_index=True,
    )
    transacoes_detectadas = models.PositiveIntegerField(default=0)
    transacoes_importadas = models.PositiveIntegerField(default=0)
    transacoes_duplicadas = models.PositiveIntegerField(default=0)
    alertas = models.JSONField(default=list, blank=True)
    resumo = models.JSONField(default=dict, blank=True)
    log_erro = models.TextField(blank=True, default="")
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="importacoes_extrato",
    )
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["status", "criado_em"], name="idx_fin_imp_status_dt"),
            models.Index(fields=["conta", "criado_em"], name="idx_fin_imp_conta_dt"),
        ]

    def __str__(self) -> str:
        conta = self.conta.nome if self.conta_id else "Conta nao vinculada"
        return f"Importacao OFX {self.id} - {conta} - {self.status}"


class TransacaoBancaria(models.Model):
    conta = models.ForeignKey(ContaBancaria, on_delete=models.PROTECT, related_name="transacoes")
    importacao = models.ForeignKey(
        ExtratoImportacao,
        on_delete=models.PROTECT,
        related_name="transacoes",
    )
    data_lancamento = models.DateField(db_index=True)
    valor = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    tipo_movimento = models.CharField(max_length=10, choices=TipoMovimentoChoices.choices, db_index=True)
    descricao = models.CharField(max_length=255)
    external_id = models.CharField(max_length=120, blank=True, null=True)
    idempotency_key = models.CharField(max_length=64, unique=True)
    status_conciliacao = models.CharField(
        max_length=20,
        choices=StatusConciliacaoChoices.choices,
        default=StatusConciliacaoChoices.PENDENTE,
        db_index=True,
    )
    metadados = models.JSONField(default=dict, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data_lancamento", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["conta", "external_id"],
                condition=models.Q(external_id__isnull=False),
                name="uniq_fin_transacao_conta_external_id",
            ),
        ]
        indexes = [
            models.Index(fields=["conta", "data_lancamento"], name="idx_fin_transacao_conta_dt"),
            models.Index(fields=["conta", "valor"], name="idx_fin_transacao_conta_valor"),
        ]

    def __str__(self) -> str:
        return f"{self.data_lancamento} {self.descricao} {self.valor}"


class Recebivel(models.Model):
    descricao = models.CharField(max_length=255)
    data_prevista = models.DateField(db_index=True)
    valor = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(
        max_length=20,
        choices=StatusRecebivelChoices.choices,
        default=StatusRecebivelChoices.ABERTO,
        db_index=True,
    )
    origem_app = models.CharField(max_length=50, blank=True, default="")
    origem_pk = models.PositiveBigIntegerField(blank=True, null=True)
    referencia_externa = models.CharField(max_length=120, blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["data_prevista", "id"]
        indexes = [
            models.Index(fields=["status", "data_prevista"], name="idx_fin_recebivel_status_dt"),
        ]

    def __str__(self) -> str:
        return f"{self.data_prevista} {self.descricao} {self.valor}"


class TipoConciliacaoChoices(models.TextChoices):
    AUTO = "AUTO", "Automatica"
    MANUAL = "MANUAL", "Manual"


class Conciliacao(models.Model):
    transacao = models.OneToOneField(
        TransacaoBancaria,
        on_delete=models.PROTECT,
        related_name="conciliacao",
    )
    tipo = models.CharField(max_length=10, choices=TipoConciliacaoChoices.choices, default=TipoConciliacaoChoices.MANUAL)
    status_final = models.CharField(max_length=20, choices=StatusConciliacaoChoices.choices)
    observacao = models.TextField(blank=True, default="")
    conciliado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conciliacoes_realizadas",
    )
    conciliado_em = models.DateTimeField(auto_now_add=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-conciliado_em"]
        indexes = [
            models.Index(fields=["status_final", "conciliado_em"], name="idx_fin_conc_status_dt"),
        ]

    def __str__(self) -> str:
        return f"Conciliacao {self.transacao_id} - {self.status_final}"


class ConciliacaoItem(models.Model):
    conciliacao = models.ForeignKey(Conciliacao, on_delete=models.CASCADE, related_name="itens")
    recebivel = models.ForeignKey(Recebivel, on_delete=models.PROTECT, related_name="conciliacoes")
    valor_alocado = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["conciliacao", "recebivel"], name="uniq_fin_conc_item"),
        ]

    def __str__(self) -> str:
        return f"{self.conciliacao_id} -> {self.recebivel_id} ({self.valor_alocado})"
