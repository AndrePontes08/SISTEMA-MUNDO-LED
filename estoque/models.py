from __future__ import annotations

from decimal import Decimal
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from compras.models import Produto, Compra, ItemCompra


class TipoMovimento(models.TextChoices):
    ENTRADA = "ENTRADA", "Entrada"
    SAIDA = "SAIDA", "Saída"
    AJUSTE = "AJUSTE", "Ajuste"


class ProdutoEstoque(models.Model):
    """
    Parametrização do estoque por produto.
    Mantém um saldo consolidado (atualizado por services).
    """
    produto = models.OneToOneField(Produto, on_delete=models.CASCADE, related_name="estoque_cfg")
    saldo_atual = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0.000"), db_index=True)

    estoque_minimo = models.DecimalField(
        max_digits=14, decimal_places=3, default=Decimal("0.000"), validators=[MinValueValidator(Decimal("0.000"))]
    )
    estoque_ideal = models.DecimalField(
        max_digits=14, decimal_places=3, default=Decimal("0.000"), validators=[MinValueValidator(Decimal("0.000"))]
    )
    estoque_maximo = models.DecimalField(
        max_digits=14, decimal_places=3, default=Decimal("0.000"), validators=[MinValueValidator(Decimal("0.000"))]
    )

    atualizado_em = models.DateTimeField(auto_now=True)
    custo_medio = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("0.0000"))

    class Meta:
        indexes = [
            models.Index(fields=["saldo_atual"], name="idx_prodestoque_saldo"),
            models.Index(fields=["estoque_minimo"], name="idx_prodestoque_min"),
        ]
        ordering = ["produto__nome"]

    def __str__(self) -> str:
        return f"{self.produto.nome} (saldo {self.saldo_atual})"


class Lote(models.Model):
    """
    Representa uma entrada de estoque, normalmente originada de uma compra/item.
    Permite calcular tempo armazenado (dias desde a entrada).
    """
    produto = models.ForeignKey(Produto, on_delete=models.PROTECT, related_name="lotes")

    compra = models.ForeignKey(Compra, on_delete=models.SET_NULL, blank=True, null=True, related_name="lotes_estoque")
    item_compra = models.ForeignKey(ItemCompra, on_delete=models.SET_NULL, blank=True, null=True, related_name="lotes")

    data_entrada = models.DateField(default=timezone.localdate, db_index=True)
    quantidade_inicial = models.DecimalField(
        max_digits=14, decimal_places=3, validators=[MinValueValidator(Decimal("0.001"))]
    )
    quantidade_restante = models.DecimalField(
        max_digits=14, decimal_places=3, validators=[MinValueValidator(Decimal("0.000"))], default=Decimal("0.000")
    )

    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["produto", "data_entrada"], name="idx_lote_prod_data"),
            models.Index(fields=["quantidade_restante"], name="idx_lote_restante"),
        ]
        ordering = ["data_entrada", "id"]

    def save(self, *args, **kwargs):
        if self.quantidade_restante is None:
            self.quantidade_restante = self.quantidade_inicial
        if self._state.adding and (self.quantidade_restante == Decimal("0.000")):
            self.quantidade_restante = self.quantidade_inicial
        super().save(*args, **kwargs)

    @property
    def dias_em_estoque(self) -> int:
        return (timezone.localdate() - self.data_entrada).days

    def __str__(self) -> str:
        return f"Lote {self.id} - {self.produto.nome} ({self.quantidade_restante}/{self.quantidade_inicial})"


class EstoqueMovimento(models.Model):
    """
    Movimento de estoque (não guarda saldo, apenas o evento).
    O saldo é recalculado/aplicado pelo service.
    """
    produto = models.ForeignKey(Produto, on_delete=models.PROTECT, related_name="movimentos")
    tipo = models.CharField(max_length=10, choices=TipoMovimento.choices, db_index=True)

    quantidade = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
        db_index=True,
    )

    data_movimento = models.DateField(default=timezone.localdate, db_index=True)

    # Origem opcional
    compra = models.ForeignKey(Compra, on_delete=models.SET_NULL, blank=True, null=True, related_name="movimentos_estoque")
    item_compra = models.ForeignKey(ItemCompra, on_delete=models.SET_NULL, blank=True, null=True, related_name="movimentos_estoque")
    lote = models.ForeignKey(Lote, on_delete=models.SET_NULL, blank=True, null=True, related_name="movimentos")

    observacao = models.CharField(max_length=255, blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["produto", "data_movimento"], name="idx_mov_prod_data"),
            models.Index(fields=["tipo", "data_movimento"], name="idx_mov_tipo_data"),
        ]
        ordering = ["-data_movimento", "-id"]

    def __str__(self) -> str:
        return f"{self.tipo} {self.produto.nome} ({self.quantidade})"


class StatusAlerta(models.TextChoices):
    ABERTO = "ABERTO", "Aberto"
    RESOLVIDO = "RESOLVIDO", "Resolvido"


class AlertaEstoque(models.Model):
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name="alertas_estoque")
    status = models.CharField(max_length=10, choices=StatusAlerta.choices, default=StatusAlerta.ABERTO, db_index=True)

    saldo_no_momento = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0.000"))
    minimo_configurado = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0.000"))

    criado_em = models.DateTimeField(auto_now_add=True)
    resolvido_em = models.DateTimeField(blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "criado_em"], name="idx_alerta_status_data"),
            models.Index(fields=["produto", "status"], name="idx_alerta_prod_status"),
        ]
        ordering = ["status", "-criado_em", "-id"]

    def __str__(self) -> str:
        return f"Alerta {self.produto.nome} ({self.status})"


class UnidadeLoja(models.TextChoices):
    LOJA_1 = "LOJA_1", "Loja 1"
    LOJA_2 = "LOJA_2", "Loja 2"


class ProdutoEstoqueUnidade(models.Model):
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name="estoque_unidades")
    unidade = models.CharField(max_length=20, choices=UnidadeLoja.choices, db_index=True)
    saldo_atual = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0.000"))
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["produto", "unidade"], name="uniq_estoque_prod_unidade"),
        ]
        indexes = [
            models.Index(fields=["unidade", "produto"], name="idx_unid_prod"),
        ]
        ordering = ["unidade", "produto__nome"]

    def __str__(self) -> str:
        return f"{self.produto.nome} - {self.get_unidade_display()} ({self.saldo_atual})"


class TransferenciaEstoque(models.Model):
    lote_referencia = models.CharField(max_length=40, db_index=True, blank=True, default="")
    produto = models.ForeignKey(Produto, on_delete=models.PROTECT, related_name="transferencias_estoque")
    unidade_origem = models.CharField(max_length=20, choices=UnidadeLoja.choices, db_index=True)
    unidade_destino = models.CharField(max_length=20, choices=UnidadeLoja.choices, db_index=True)
    quantidade = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    data_transferencia = models.DateField(default=timezone.localdate, db_index=True)
    observacao = models.CharField(max_length=255, blank=True, default="")
    usuario = models.ForeignKey("auth.User", on_delete=models.SET_NULL, blank=True, null=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["lote_referencia", "data_transferencia"], name="idx_transf_lote_data"),
            models.Index(fields=["data_transferencia"], name="idx_transf_data"),
            models.Index(fields=["produto", "data_transferencia"], name="idx_transf_prod_data"),
        ]
        ordering = ["-data_transferencia", "-id"]

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.unidade_origem == self.unidade_destino:
            raise ValidationError({"unidade_destino": "A unidade de destino deve ser diferente da origem."})

    def __str__(self) -> str:
        lote = self.lote_referencia or "-"
        return (
            f"Transferencia {lote} {self.produto.nome}: "
            f"{self.get_unidade_origem_display()} -> {self.get_unidade_destino_display()} "
            f"({self.quantidade})"
        )
