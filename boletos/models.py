from __future__ import annotations

from decimal import Decimal
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from core.services.normalizacao import normalizar_nome


class StatusBoletoChoices(models.TextChoices):
    ABERTO = "ABERTO", "Aberto"
    PAGO = "PAGO", "Pago"
    VENCIDO = "VENCIDO", "Vencido"
    CANCELADO = "CANCELADO", "Cancelado"
    PENDENTE = "PENDENTE", "Pendente"


class StatusFiadoChoices(models.TextChoices):
    ATIVO = "ATIVO", "Ativo"
    PAGO = "PAGO", "Pago"
    VENCIDO = "VENCIDO", "Vencido"
    BLOQUEADO = "BLOQUEADO", "Bloqueado"


class RamoAtuacao(models.Model):
    """Ramo de atuação das empresas/clientes"""
    nome = models.CharField(max_length=120, unique=True)
    descricao = models.TextField(blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "Ramo de Atuação"
        verbose_name_plural = "Ramos de Atuação"

    def __str__(self) -> str:
        return self.nome


class Cliente(models.Model):
    """Cliente que pode ter boletos e fiados"""
    nome = models.CharField(max_length=255)
    data_nascimento = models.DateField(blank=True, null=True)
    nome_normalizado = models.CharField(max_length=255, db_index=True)
    cpf_cnpj = models.CharField(max_length=18, unique=True, db_index=True)
    email = models.EmailField(blank=True, default="")
    telefone = models.CharField(max_length=20, blank=True, default="")
    endereco = models.TextField(blank=True, default="")
    ramo_atuacao = models.ForeignKey(
        RamoAtuacao,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clientes"
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    ativo = models.BooleanField(default=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["nome_normalizado"], name="idx_cliente_nome_norm"),
            models.Index(fields=["cpf_cnpj"], name="idx_cliente_cpf_cnpj"),
            models.Index(fields=["ativo"], name="idx_cliente_ativo"),
        ]
        ordering = ["nome"]

    def save(self, *args, **kwargs):
        self.nome = (self.nome or "").strip()
        self.nome_normalizado = normalizar_nome(self.nome)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.nome


class ClienteListaNegra(models.Model):
    """Lista negra de clientes que não podem receber crédito"""
    cliente = models.OneToOneField(
        Cliente,
        on_delete=models.CASCADE,
        related_name="lista_negra"
    )
    data_bloqueio = models.DateField(auto_now_add=True, db_index=True)
    motivo = models.TextField()
    responsavel = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="bloqueios_clientes"
    )
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Cliente em Lista Negra"
        verbose_name_plural = "Clientes em Lista Negra"
        ordering = ["-data_bloqueio"]

    def __str__(self) -> str:
        return f"{self.cliente.nome} - Bloqueado em {self.data_bloqueio}"


class Boleto(models.Model):
    """Controle de boletos emitidos"""
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name="boletos"
    )
    numero_boleto = models.CharField(max_length=50, unique=True, db_index=True)
    descricao = models.CharField(max_length=255)
    valor = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))]
    )
    data_emissao = models.DateField(auto_now_add=True)
    data_vencimento = models.DateField(db_index=True)
    data_pagamento = models.DateField(blank=True, null=True)
    
    status = models.CharField(
        max_length=20,
        choices=StatusBoletoChoices.choices,
        default=StatusBoletoChoices.ABERTO,
        db_index=True
    )
    
    vendedor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="boletos_responsaveis"
    )

    class BancoChoices(models.TextChoices):
        SICREDI = "SICREDI", "Sicredi"
        BRASIL = "BRASIL", "Banco do Brasil"
        OUTRO = "OUTRO", "Outro"

    banco = models.CharField(
        max_length=20,
        choices=BancoChoices.choices,
        default=BancoChoices.OUTRO,
        db_index=True,
    )

    nosso_numero = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        db_index=True,
        help_text="Identificador do banco (Nosso Número)",
    )

    necessita_comprovante = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Indica que o boleto foi importado como vencido e precisa de comprovante",
    )
    
    comprovante_pagamento = models.FileField(
        upload_to="boletos/comprovantes/",
        blank=True,
        null=True
    )
    
    observacoes = models.TextField(blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["numero_boleto"], name="idx_boleto_numero"),
            models.Index(fields=["cliente", "status"], name="idx_boleto_cliente_status"),
            models.Index(fields=["data_vencimento"], name="idx_boleto_vencimento"),
            models.Index(fields=["vendedor"], name="idx_boleto_vendedor"),
        ]
        ordering = ["-data_vencimento", "-id"]

    def __str__(self) -> str:
        return f"Boleto {self.numero_boleto} - {self.cliente.nome}"

    @property
    def dias_vencimento(self) -> int:
        """Retorna dias até o vencimento (negativo se vencido)"""
        return (self.data_vencimento - timezone.now().date()).days


class ControleFiado(models.Model):
    """Controle de valores em fiado por cliente"""
    cliente = models.OneToOneField(
        Cliente,
        on_delete=models.CASCADE,
        related_name="controle_fiado"
    )
    limite_credito = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))]
    )
    saldo_fiado = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00")
    )
    status = models.CharField(
        max_length=20,
        choices=StatusFiadoChoices.choices,
        default=StatusFiadoChoices.ATIVO,
        db_index=True
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Controle de Fiado"
        verbose_name_plural = "Controle de Fiados"

    def __str__(self) -> str:
        return f"Fiado {self.cliente.nome} - Saldo: R$ {self.saldo_fiado}"

    @property
    def saldo_disponivel(self) -> Decimal:
        """Retorna saldo disponível para novo crédito"""
        return self.limite_credito - self.saldo_fiado

    @property
    def percentual_utilizado(self) -> float:
        """Percentual do limite utilizado"""
        if self.limite_credito == 0:
            return 0.0
        percentual: float = float((self.saldo_fiado / self.limite_credito) * 100)
        return percentual


class ParcelaBoleto(models.Model):
    """Parcelas quando um boleto é dividido"""
    boleto = models.ForeignKey(
        Boleto,
        on_delete=models.CASCADE,
        related_name="parcelas"
    )
    numero_parcela = models.PositiveIntegerField()
    valor = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))]
    )
    data_vencimento = models.DateField(db_index=True)
    data_pagamento = models.DateField(blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=StatusBoletoChoices.choices,
        default=StatusBoletoChoices.ABERTO,
        db_index=True
    )

    class Meta:
        unique_together = ("boleto", "numero_parcela")
        ordering = ["numero_parcela"]

    def __str__(self) -> str:
        return f"{self.boleto.numero_boleto} - Parcela {self.numero_parcela}"
