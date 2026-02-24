from __future__ import annotations

from decimal import Decimal
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from core.services.normalizacao import normalizar_nome


class CentroCustoChoices(models.TextChoices):
    FM = "FM", "FM"
    ML = "ML", "ML"
    PESSOAL = "PESSOAL", "PESSOAL"
    FM_ML = "FM/ML", "FM/ML"
    OUTROS = "OUTROS", "OUTROS"


class Fornecedor(models.Model):
    nome = models.CharField(max_length=255)
    nome_normalizado = models.CharField(max_length=255, db_index=True, unique=True)
    cnpj = models.CharField(max_length=18, blank=True, default="", db_index=True)
    telefone_contato = models.CharField(max_length=20, blank=True, default="")
    representante_comercial = models.CharField(max_length=255, blank=True, default="")
    contato_representante = models.CharField(max_length=120, blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["nome_normalizado"], name="idx_fornecedor_nome_norm"),
            models.Index(fields=["cnpj"], name="idx_fornecedor_cnpj"),
        ]
        ordering = ["nome"]

    def save(self, *args, **kwargs):
        self.nome = (self.nome or "").strip()
        self.nome_normalizado = normalizar_nome(self.nome)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.nome


class FornecedorAlias(models.Model):
    """
    Evita duplicidade em relatórios: variações de nome apontam para o Fornecedor principal.
    """
    principal = models.ForeignKey(Fornecedor, on_delete=models.CASCADE, related_name="aliases")
    nome = models.CharField(max_length=255)
    nome_normalizado = models.CharField(max_length=255, db_index=True, unique=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["nome_normalizado"], name="idx_fornalias_nome_norm"),
            models.Index(fields=["principal"], name="idx_fornalias_principal"),
        ]
        ordering = ["nome"]

    def save(self, *args, **kwargs):
        self.nome = (self.nome or "").strip()
        self.nome_normalizado = normalizar_nome(self.nome)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.nome} -> {self.principal.nome}"


class Produto(models.Model):
    nome = models.CharField(max_length=255)
    nome_normalizado = models.CharField(max_length=255, db_index=True)
    sku = models.CharField(max_length=64, blank=True, default="", db_index=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["nome_normalizado"], name="idx_prod_nome_norm"),
            models.Index(fields=["sku"], name="idx_prod_sku"),
        ]
        ordering = ["nome"]
        constraints = [
            # sku pode repetir vazio; quando preenchido, tende a ser único
            models.UniqueConstraint(
                fields=["sku"],
                condition=~models.Q(sku=""),
                name="uniq_prod_sku_when_filled",
            )
        ]

    def save(self, *args, **kwargs):
        self.nome = (self.nome or "").strip()
        self.nome_normalizado = normalizar_nome(self.nome)
        self.sku = (self.sku or "").strip()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.nome


def compra_upload_path(instance: "Compra", filename: str) -> str:
    return f"compras/notas/{instance.data_compra:%Y/%m}/{instance.id or 'novo'}_{filename}"


def orcamento_upload_path(instance: "Compra", filename: str) -> str:
    return f"compras/orcamentos/{instance.data_compra:%Y/%m}/{instance.id or 'novo'}_{filename}"


def garantia_upload_path(instance: "Garantia", filename: str) -> str:
    compra_id = instance.item.compra_id if instance.item_id else "sem_item"
    return f"compras/garantias/{timezone.now():%Y/%m}/{compra_id}_{filename}"


class Compra(models.Model):
    fornecedor = models.ForeignKey(Fornecedor, on_delete=models.PROTECT, related_name="compras")
    centro_custo = models.CharField(max_length=20, choices=CentroCustoChoices.choices, db_index=True)
    data_compra = models.DateField(default=timezone.localdate, db_index=True)

    nota_fiscal = models.FileField(upload_to=compra_upload_path, blank=True, null=True)
    boleto = models.FileField(upload_to="compras/boletos/", blank=True, null=True)
    pedido = models.FileField(upload_to="compras/pedidos/", blank=True, null=True)
    comprovante_pagamento = models.FileField(upload_to="compras/comprovantes/", blank=True, null=True)
    orcamento_1 = models.FileField(upload_to=orcamento_upload_path, blank=True, null=True)
    orcamento_2 = models.FileField(upload_to=orcamento_upload_path, blank=True, null=True)
    orcamento_3 = models.FileField(upload_to=orcamento_upload_path, blank=True, null=True)

    class OrcamentoEscolhidoChoices(models.TextChoices):
        ORC_1 = "ORC_1", "Orcamento 1"
        ORC_2 = "ORC_2", "Orcamento 2"
        ORC_3 = "ORC_3", "Orcamento 3"

    orcamento_escolhido = models.CharField(
        max_length=10,
        choices=OrcamentoEscolhidoChoices.choices,
        blank=True,
        default="",
        db_index=True,
    )
    justificativa_escolha = models.TextField(blank=True, default="")

    valor_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        db_index=True,
    )

    observacoes = models.TextField(blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)
    
    class StatusChoices(models.TextChoices):
        SOLICITADA = "SOLICITADA", "Solicitada"
        APROVADA = "APROVADA", "Aprovada"
        COMPRADA = "COMPRADA", "Comprada"
        RECEBIDA = "RECEBIDA", "Recebida"
        CANCELADA = "CANCELADA", "Cancelada"

    status = models.CharField(max_length=20, choices=StatusChoices.choices, default=StatusChoices.SOLICITADA, db_index=True)

    aprovado_em = models.DateTimeField(blank=True, null=True)
    aprovado_por = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, blank=True, null=True, related_name="compras_aprovadas"
    )
    recebido_em = models.DateTimeField(blank=True, null=True)
    recebido_por = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, blank=True, null=True, related_name="compras_recebidas"
    )

    class Meta:
        indexes = [
            models.Index(fields=["data_compra"], name="idx_compra_data"),
            models.Index(fields=["centro_custo", "data_compra"], name="idx_compra_cc_data"),
            models.Index(fields=["fornecedor", "data_compra"], name="idx_compra_forn_data"),
            models.Index(fields=["orcamento_escolhido", "data_compra"], name="idx_compra_orc_data"),
        ]
        ordering = ["-data_compra", "-id"]

    def __str__(self) -> str:
        return f"Compra #{self.id} - {self.fornecedor.nome} - {self.data_compra:%d/%m/%Y}"


class ItemCompra(models.Model):
    compra = models.ForeignKey(Compra, on_delete=models.CASCADE, related_name="itens")
    produto = models.ForeignKey(Produto, on_delete=models.PROTECT, related_name="itens_compra")

    quantidade = models.DecimalField(
        max_digits=12, decimal_places=3, validators=[MinValueValidator(Decimal("0.001"))]
    )
    preco_unitario = models.DecimalField(
        max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))]
    )

    class Meta:
        indexes = [
            models.Index(fields=["compra"], name="idx_item_compra"),
            models.Index(fields=["produto"], name="idx_item_produto"),
        ]
        ordering = ["id"]

    @property
    def subtotal(self) -> Decimal:
        bruto = (self.quantidade or Decimal("0")) * (self.preco_unitario or Decimal("0"))
        return bruto.quantize(Decimal("0.01"))

    def __str__(self) -> str:
        return f"{self.compra_id} - {self.produto.nome}"


class Garantia(models.Model):
    """
    Garantia vinculada ao item.
    """
    item = models.ForeignKey(ItemCompra, on_delete=models.CASCADE, related_name="garantias")
    arquivo = models.FileField(upload_to=garantia_upload_path, blank=True, null=True)

    data_inicio = models.DateField(default=timezone.localdate, db_index=True)
    data_fim = models.DateField(db_index=True)

    observacao = models.CharField(max_length=255, blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["data_fim"], name="idx_garantia_data_fim"),
            models.Index(fields=["item"], name="idx_garantia_item"),
        ]
        ordering = ["-data_fim", "-id"]

    def clean(self):
        # Validação simples: fim >= inicio
        if self.data_fim and self.data_inicio and self.data_fim < self.data_inicio:
            from django.core.exceptions import ValidationError
            raise ValidationError({"data_fim": "A data fim da garantia não pode ser menor que a data de início."})

    def __str__(self) -> str:
        return f"Garantia item {self.item_id} até {self.data_fim:%d/%m/%Y}"


class CompraEvento(models.Model):
    """Evento/audit trail leve para ações em uma `Compra`."""
    class TipoEvento(models.TextChoices):
        APROVACAO = "APROVACAO", "Aprovação"
        RECEBIMENTO = "RECEBIMENTO", "Recebimento"
        CANCELAMENTO = "CANCELAMENTO", "Cancelamento"
        OUTRO = "OUTRO", "Outro"

    compra = models.ForeignKey(Compra, on_delete=models.CASCADE, related_name="eventos")
    tipo = models.CharField(max_length=20, choices=TipoEvento.choices, default=TipoEvento.OUTRO, db_index=True)
    usuario = models.ForeignKey("auth.User", on_delete=models.SET_NULL, blank=True, null=True)
    detalhe = models.TextField(blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em", "-id"]

    def __str__(self) -> str:
        return f"Evento {self.tipo} - Compra {self.compra_id} - {self.criado_em:%d/%m/%Y %H:%M}"
