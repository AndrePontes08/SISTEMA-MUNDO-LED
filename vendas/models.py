from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from boletos.models import Boleto, Cliente
from compras.models import Produto
from estoque.models import EstoqueMovimento, UnidadeLoja
from financeiro.models import Recebivel


class StatusVendaChoices(models.TextChoices):
    RASCUNHO = "RASCUNHO", "Rascunho"
    CONFIRMADA = "CONFIRMADA", "Confirmada"
    FATURADA = "FATURADA", "Faturada"
    FINALIZADA = "FINALIZADA", "Finalizada"
    CANCELADA = "CANCELADA", "Cancelada"


class TipoPagamentoChoices(models.TextChoices):
    PIX = "PIX", "PIX"
    CREDITO = "CREDITO", "CREDITO"
    DEBITO = "DEBITO", "DEBITO"
    ESPECIE = "AVISTA", "ESPECIE"
    BOLETO = "PARCELADO_BOLETO", "BOLETO"
    CREDITO_LOJA = "PARCELADO", "CREDITO NA LOJA"


class TipoDocumentoVendaChoices(models.TextChoices):
    VENDA = "VENDA", "Venda"
    ORCAMENTO = "ORCAMENTO", "Orcamento"


class TipoEventoVendaChoices(models.TextChoices):
    CRIACAO = "CRIACAO", "Criacao"
    CONFIRMACAO = "CONFIRMACAO", "Confirmacao"
    FATURAMENTO = "FATURAMENTO", "Faturamento"
    FINALIZACAO = "FINALIZACAO", "Finalizacao"
    CANCELAMENTO = "CANCELAMENTO", "Cancelamento"
    OUTRO = "OUTRO", "Outro"


class TipoMovimentoVendaChoices(models.TextChoices):
    SAIDA = "SAIDA", "Saida"
    REVERSAO = "REVERSAO", "Reversao"


class Venda(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="vendas")
    vendedor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="vendas_registradas",
        blank=True,
        null=True,
    )
    data_venda = models.DateField(default=timezone.localdate, db_index=True)
    unidade_saida = models.CharField(
        max_length=20,
        choices=UnidadeLoja.choices,
        default=UnidadeLoja.LOJA_1,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=StatusVendaChoices.choices,
        default=StatusVendaChoices.RASCUNHO,
        db_index=True,
    )
    codigo_identificacao = models.CharField(max_length=20, blank=True, default="", unique=True)
    tipo_documento = models.CharField(
        max_length=15,
        choices=TipoDocumentoVendaChoices.choices,
        default=TipoDocumentoVendaChoices.VENDA,
        db_index=True,
    )
    tipo_pagamento = models.CharField(
        max_length=25,
        choices=TipoPagamentoChoices.choices,
        default=TipoPagamentoChoices.ESPECIE,
        db_index=True,
    )
    numero_parcelas = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(36)],
    )
    intervalo_parcelas_dias = models.PositiveSmallIntegerField(
        default=30,
        validators=[MinValueValidator(1), MaxValueValidator(120)],
    )
    primeiro_vencimento = models.DateField(blank=True, null=True, db_index=True)

    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    desconto_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    acrescimo = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total_final = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), db_index=True)

    observacoes = models.TextField(blank=True, default="")

    faturada_em = models.DateTimeField(blank=True, null=True)
    faturada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="vendas_faturadas",
        blank=True,
        null=True,
    )
    cancelada_em = models.DateTimeField(blank=True, null=True)
    cancelada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="vendas_canceladas",
        blank=True,
        null=True,
    )

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-data_venda", "-id"]
        indexes = [
            models.Index(fields=["status", "data_venda"], name="idx_venda_status_data"),
            models.Index(fields=["cliente", "data_venda"], name="idx_venda_cliente_data"),
            models.Index(fields=["tipo_pagamento", "data_venda"], name="idx_venda_pgto_data"),
            models.Index(fields=["tipo_documento", "data_venda"], name="idx_venda_doc_data"),
        ]

    def clean(self):
        if self.tipo_pagamento == TipoPagamentoChoices.ESPECIE:
            self.numero_parcelas = 1
        if self.numero_parcelas <= 1:
            self.intervalo_parcelas_dias = 30

    def __str__(self) -> str:
        return f"Venda #{self.id} - {self.cliente.nome}"

    @property
    def is_orcamento(self) -> bool:
        return self.tipo_documento == TipoDocumentoVendaChoices.ORCAMENTO

    def _codigo_esperado(self) -> str:
        prefixo = "ORC" if self.tipo_documento == TipoDocumentoVendaChoices.ORCAMENTO else "VEN"
        pk = self.pk or 0
        return f"{prefixo}-{pk:06d}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        esperado = self._codigo_esperado()
        if self.codigo_identificacao != esperado:
            type(self).objects.filter(pk=self.pk).update(codigo_identificacao=esperado)
            self.codigo_identificacao = esperado


class ItemVenda(models.Model):
    venda = models.ForeignKey(Venda, on_delete=models.CASCADE, related_name="itens")
    produto = models.ForeignKey(Produto, on_delete=models.PROTECT, related_name="itens_venda")
    quantidade = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    preco_unitario = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    desconto = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        indexes = [
            models.Index(fields=["venda"], name="idx_itemvenda_venda"),
            models.Index(fields=["produto"], name="idx_itemvenda_produto"),
        ]

    def save(self, *args, **kwargs):
        bruto = (self.quantidade or Decimal("0")) * (self.preco_unitario or Decimal("0"))
        subtotal = bruto - (self.desconto or Decimal("0"))
        if subtotal < 0:
            subtotal = Decimal("0.00")
        self.subtotal = subtotal.quantize(Decimal("0.01"))
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Venda {self.venda_id} - {self.produto.nome}"


class VendaEvento(models.Model):
    venda = models.ForeignKey(Venda, on_delete=models.CASCADE, related_name="eventos")
    tipo = models.CharField(
        max_length=20,
        choices=TipoEventoVendaChoices.choices,
        default=TipoEventoVendaChoices.OUTRO,
        db_index=True,
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    detalhe = models.TextField(blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em", "-id"]
        indexes = [
            models.Index(fields=["venda", "tipo"], name="idx_vendevento_venda_tipo"),
        ]


class VendaMovimentoEstoque(models.Model):
    venda = models.ForeignKey(Venda, on_delete=models.CASCADE, related_name="movimentos_estoque")
    item_venda = models.ForeignKey(ItemVenda, on_delete=models.CASCADE, related_name="movimentos_estoque")
    movimento = models.OneToOneField(EstoqueMovimento, on_delete=models.PROTECT, related_name="venda_link")
    tipo = models.CharField(max_length=10, choices=TipoMovimentoVendaChoices.choices, db_index=True)
    quantidade = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0.000"))
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["venda", "item_venda", "tipo"],
                name="uniq_venda_item_movtipo",
            )
        ]
        indexes = [
            models.Index(fields=["venda", "tipo"], name="idx_vendamov_venda_tipo"),
        ]


class VendaRecebivel(models.Model):
    venda = models.ForeignKey(Venda, on_delete=models.CASCADE, related_name="recebiveis")
    numero_parcela = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(36)],
    )
    recebivel = models.OneToOneField(Recebivel, on_delete=models.PROTECT, related_name="venda_link")
    valor = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    data_vencimento = models.DateField(db_index=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["numero_parcela"]
        constraints = [
            models.UniqueConstraint(fields=["venda", "numero_parcela"], name="uniq_venda_parcela_recebivel"),
        ]
        indexes = [
            models.Index(fields=["venda", "data_vencimento"], name="idx_vendarec_venda_venc"),
        ]


class VendaBoleto(models.Model):
    venda = models.ForeignKey(Venda, on_delete=models.CASCADE, related_name="boletos")
    numero_parcela = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(36)],
    )
    boleto = models.OneToOneField(Boleto, on_delete=models.PROTECT, related_name="venda_link")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["numero_parcela"]
        constraints = [
            models.UniqueConstraint(fields=["venda", "numero_parcela"], name="uniq_venda_parcela_boleto"),
        ]


class FechamentoCaixaDiario(models.Model):
    """
    Snapshot diário de fechamento de caixa de vendas.
    Mantém histórico para reimpressão e auditoria operacional.
    """

    data_referencia = models.DateField(db_index=True)
    total_vendas = models.PositiveIntegerField(default=0)
    total_receita = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total_descontos = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    totais_por_pagamento = models.JSONField(default=dict, blank=True)
    observacoes = models.TextField(blank=True, default="")
    detalhes_json = models.JSONField(default=dict, blank=True)
    arquivo_pdf = models.BinaryField(blank=True, null=True, editable=False)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="fechamentos_caixa_vendas",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data_referencia", "-id"]
        indexes = [
            models.Index(fields=["data_referencia", "criado_em"], name="idx_fechcaixa_data_criado"),
        ]

    def __str__(self) -> str:
        return f"Fechamento {self.data_referencia:%d/%m/%Y} #{self.id}"
