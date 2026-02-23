from __future__ import annotations

from decimal import Decimal
from django.db import models
from django.utils import timezone


def comprovante_upload_path(instance: "ContaAPagar", filename: str) -> str:
    # Mantido por retrocompatibilidade com migrações antigas.
    return f"contas/comprovantes/{filename}"


class CentroCustoChoices(models.TextChoices):
    FM = "FM", "FM"
    ML = "ML", "ML"
    PESSOAL = "PESSOAL", "PESSOAL"
    FM_ML = "FM/ML", "FM/ML"
    OUTROS = "OUTROS", "OUTROS"


class StatusContaChoices(models.TextChoices):
    ABERTA = "ABERTA", "ABERTA"
    PAGA = "PAGA", "PAGA"
    CANCELADA = "CANCELADA", "CANCELADA"


class Categoria(models.Model):
    nome = models.CharField(max_length=120, unique=True)

    def __str__(self) -> str:
        return self.nome


class ContaAPagar(models.Model):
    vencimento = models.DateField(db_index=True)
    descricao = models.CharField(max_length=255)

    centro_custo = models.CharField(
        max_length=20,
        choices=CentroCustoChoices.choices,
        default=CentroCustoChoices.OUTROS,
        db_index=True,
    )

    valor = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    status = models.CharField(
        max_length=20,
        choices=StatusContaChoices.choices,
        default=StatusContaChoices.ABERTA,
        db_index=True,
    )

    pago_em = models.DateField(blank=True, null=True)

    # ✅ CATEGORIA NÃO OBRIGATÓRIA
    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contas_a_pagar",
    )

    observacoes = models.TextField(blank=True, default="")

    # ✅ ANEXOS SEPARADOS
    boleto = models.FileField(upload_to="contas/boletos/", blank=True, null=True)
    nota_fiscal = models.FileField(upload_to="contas/notas_fiscais/", blank=True, null=True)
    comprovante = models.FileField(upload_to="contas/comprovantes/", blank=True, null=True)
    pedido = models.FileField(upload_to="contas/pedidos/", blank=True, null=True)

    # ✅ REGRAS DE EXIGÊNCIA (opcionais)
    exige_boleto = models.BooleanField(default=False)
    exige_nota_fiscal = models.BooleanField(default=False)
    exige_comprovante = models.BooleanField(default=False)

    # ✅ CAMPOS DE IMPORTAÇÃO (opcionais)
    importado = models.BooleanField(default=False, db_index=True)
    fonte_importacao = models.CharField(max_length=80, blank=True, default="")
    linha_importacao = models.IntegerField(blank=True, null=True)

    criado_em = models.DateTimeField(default=timezone.now, db_index=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-vencimento", "-id"]
        indexes = [
            models.Index(fields=["status", "vencimento"], name="idx_conta_status_venc"),
            models.Index(fields=["centro_custo", "vencimento"], name="idx_conta_cc_venc"),
        ]

    def __str__(self) -> str:
        return f"{self.vencimento} - {self.descricao} - {self.valor}"


class ProjecaoMensal(models.Model):
    """
    Projeção de custo fixo mensal (ex: aluguel, folha etc).
    """
    nome = models.CharField(max_length=120, default="")
    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="projecoes_mensais",  # ✅ evita clash com ContaAPagar
    )
    centro_custo = models.CharField(
        max_length=20,
        choices=CentroCustoChoices.choices,
        default=CentroCustoChoices.OUTROS,
    )
    valor = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    ativo = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.nome


class RegraImposto(models.Model):
    """
    Regra simples para cálculo mensal (ex: percentual sobre soma do mês).
    """
    nome = models.CharField(max_length=120, default="Regra padrão")
    aliquota_percentual = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal("0.000"))  # ex 1.500 = 1,5%
    ativo = models.BooleanField(default=True)

    criado_em = models.DateTimeField(default=timezone.now)

    def __str__(self) -> str:
        return f"{self.nome} ({self.aliquota_percentual}%)"
