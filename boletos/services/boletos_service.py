from __future__ import annotations

from decimal import Decimal
from datetime import timedelta
from django.utils import timezone
from django.db import transaction, models

from boletos.models import (
    Boleto,
    Cliente,
    ClienteListaNegra,
    ControleFiado,
    StatusBoletoChoices,
    StatusFiadoChoices,
)


class BoletoService:
    """Serviço para controle e gestão de boletos"""

    @staticmethod
    def criar_boleto(
        cliente: Cliente,
        numero_boleto: str,
        descricao: str,
        valor: Decimal,
        data_vencimento,
        vendedor=None,
        observacoes: str = "",
    ) -> Boleto:
        """Cria um novo boleto com validações"""
        # Validar se cliente está na lista negra
        if hasattr(cliente, "lista_negra") and cliente.lista_negra.ativo:
            raise ValueError(f"Cliente {cliente.nome} está na lista negra.")

        boleto = Boleto.objects.create(
            cliente=cliente,
            numero_boleto=numero_boleto,
            descricao=descricao,
            valor=valor,
            data_vencimento=data_vencimento,
            vendedor=vendedor,
            observacoes=observacoes,
            status=StatusBoletoChoices.ABERTO,
        )

        return boleto

    @staticmethod
    def registrar_pagamento(
        boleto: Boleto,
        data_pagamento=None,
        comprovante=None,
    ) -> Boleto:
        """Registra o pagamento de um boleto"""
        if data_pagamento is None:
            data_pagamento = timezone.now().date()

        boleto.status = StatusBoletoChoices.PAGO
        boleto.data_pagamento = data_pagamento
        if comprovante:
            boleto.comprovante_pagamento = comprovante

        boleto.save()
        return boleto

    @staticmethod
    def verificar_vencimentos_em_atraso():
        """Atualiza boletos que passaram da data de vencimento"""
        hoje = timezone.now().date()
        boletos_vencidos = Boleto.objects.filter(
            data_vencimento__lt=hoje,
            status__in=[StatusBoletoChoices.ABERTO, StatusBoletoChoices.PENDENTE],
        )

        boletos_vencidos.update(status=StatusBoletoChoices.VENCIDO)
        return boletos_vencidos.count()

    @staticmethod
    def listar_boletos_criticos(dias_antecedencia: int = 7):
        """Retorna boletos próximos ao vencimento"""
        hoje = timezone.now().date()
        data_limite = hoje + timedelta(days=dias_antecedencia)

        return Boleto.objects.filter(
            data_vencimento__range=[hoje, data_limite],
            status__in=[StatusBoletoChoices.ABERTO, StatusBoletoChoices.PENDENTE],
        ).order_by("data_vencimento")

    @staticmethod
    def obter_total_em_aberto(cliente: Cliente = None) -> Decimal:
        """Calcula total de boletos em aberto"""
        qs = Boleto.objects.filter(
            status__in=[StatusBoletoChoices.ABERTO, StatusBoletoChoices.PENDENTE]
        )

        if cliente:
            qs = qs.filter(cliente=cliente)

        return sum(b.valor for b in qs) or Decimal("0.00")

    @staticmethod
    def obter_estatisticas():
        """Retorna estatísticas gerais de boletos"""
        hoje = timezone.now().date()

        return {
            "total_abertos": Boleto.objects.filter(
                status=StatusBoletoChoices.ABERTO
            ).count(),
            "total_pendentes": Boleto.objects.filter(
                status=StatusBoletoChoices.PENDENTE
            ).count(),
            "total_pagos": Boleto.objects.filter(
                status=StatusBoletoChoices.PAGO
            ).count(),
            "total_vencidos": Boleto.objects.filter(
                status=StatusBoletoChoices.VENCIDO
            ).count(),
            "valor_total_aberto": Boleto.objects.filter(
                status__in=[StatusBoletoChoices.ABERTO, StatusBoletoChoices.PENDENTE]
            ).aggregate(total=models.Sum("valor"))["total"]
            or Decimal("0.00"),
        }


class ClienteService:
    """Serviço para gerenciamento de clientes"""

    @staticmethod
    def adicionar_lista_negra(cliente: Cliente, motivo: str, responsavel) -> ClienteListaNegra:
        """Adiciona cliente à lista negra"""
        lista_negra, created = ClienteListaNegra.objects.get_or_create(
            cliente=cliente,
            defaults={"motivo": motivo, "responsavel": responsavel, "ativo": True},
        )

        if not created:
            lista_negra.motivo = motivo
            lista_negra.responsavel = responsavel
            lista_negra.ativo = True
            lista_negra.save()

        return lista_negra

    @staticmethod
    def remover_lista_negra(cliente: Cliente):
        """Remove cliente da lista negra"""
        try:
            lista_negra = ClienteListaNegra.objects.get(cliente=cliente)
            lista_negra.ativo = False
            lista_negra.save()
        except ClienteListaNegra.DoesNotExist:
            pass

    @staticmethod
    def obter_clientes_em_lista_negra():
        """Retorna todos os clientes na lista negra ativa"""
        return Cliente.objects.filter(lista_negra__ativo=True)


class ControleFiadoService:
    """Serviço para controle de fiados"""

    @staticmethod
    @transaction.atomic
    def adicionar_fiado(
        cliente: Cliente, valor: Decimal, responsavel=None
    ) -> ControleFiado:
        """Adiciona valor ao fiado do cliente"""
        controle, created = ControleFiado.objects.get_or_create(
            cliente=cliente,
            defaults={
                "limite_credito": Decimal("0.00"),
                "saldo_fiado": Decimal("0.00"),
            },
        )

        # Verifica se cliente está na lista negra
        if hasattr(cliente, "lista_negra") and cliente.lista_negra.ativo:
            raise ValueError(f"Cliente {cliente.nome} está na lista negra.")

        # Verifica saldo disponível
        if controle.saldo_disponivel < valor:
            raise ValueError(
                f"Saldo insuficiente. Disponível: R$ {controle.saldo_disponivel}"
            )

        controle.saldo_fiado += valor
        controle.save()

        return controle

    @staticmethod
    @transaction.atomic
    def pagar_fiado(cliente: Cliente, valor: Decimal) -> ControleFiado:
        """Registra pagamento de fiado"""
        controle = ControleFiado.objects.get(cliente=cliente)

        controle.saldo_fiado = max(Decimal("0.00"), controle.saldo_fiado - valor)
        controle.save()

        return controle

    @staticmethod
    def estabelecer_limite(cliente: Cliente, limite: Decimal) -> ControleFiado:
        """Estabelece limite de crédito do cliente"""
        controle, created = ControleFiado.objects.get_or_create(
            cliente=cliente,
            defaults={"limite_credito": limite, "saldo_fiado": Decimal("0.00")},
        )

        if not created:
            controle.limite_credito = limite
            controle.save()

        return controle

    @staticmethod
    def bloquear_fiado(cliente: Cliente):
        """Bloqueia fiado de um cliente"""
        try:
            controle = ControleFiado.objects.get(cliente=cliente)
            controle.status = StatusFiadoChoices.BLOQUEADO
            controle.save()
        except ControleFiado.DoesNotExist:
            pass

    @staticmethod
    def desbloquear_fiado(cliente: Cliente):
        """Desbloqueia fiado de um cliente"""
        try:
            controle = ControleFiado.objects.get(cliente=cliente)
            controle.status = StatusFiadoChoices.ATIVO
            controle.save()
        except ControleFiado.DoesNotExist:
            pass
