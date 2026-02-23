from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Iterable

from django.db import transaction
from django.utils import timezone

from boletos.models import Boleto, StatusBoletoChoices
from compras.models import Produto
from estoque.models import ProdutoEstoque
from estoque.services.estoque_service import registrar_entrada, registrar_saida
from financeiro.models import Recebivel, StatusRecebivelChoices
from vendas.models import (
    ItemVenda,
    StatusVendaChoices,
    TipoDocumentoVendaChoices,
    TipoEventoVendaChoices,
    TipoMovimentoVendaChoices,
    TipoPagamentoChoices,
    Venda,
    VendaBoleto,
    VendaEvento,
    VendaMovimentoEstoque,
    VendaRecebivel,
)
from vendas.services.totais_service import recalcular_totais


@dataclass(frozen=True)
class ItemVendaPayload:
    produto: Produto
    quantidade: Decimal
    preco_unitario: Decimal
    desconto: Decimal = Decimal("0.00")


@dataclass(frozen=True)
class FaturamentoResult:
    venda: Venda
    movimentos_criados: int
    recebiveis_criados: int
    boletos_criados: int
    already_processed: bool = False


@dataclass(frozen=True)
class CancelamentoResult:
    venda: Venda
    reversoes_estoque: int
    recebiveis_cancelados: int
    boletos_cancelados: int
    already_canceled: bool = False


def _to_dec_2(valor: Decimal) -> Decimal:
    return (valor or Decimal("0.00")).quantize(Decimal("0.01"))


def _to_dec_3(valor: Decimal) -> Decimal:
    return (valor or Decimal("0.000")).quantize(Decimal("0.001"))


def _parcelar_valor(total: Decimal, parcelas: int) -> list[Decimal]:
    if parcelas <= 1:
        return [_to_dec_2(total)]

    total = _to_dec_2(total)
    base = (total / parcelas).quantize(Decimal("0.01"))
    valores = [base for _ in range(parcelas)]
    soma = sum(valores, Decimal("0.00"))
    diferenca = total - soma
    valores[-1] = _to_dec_2(valores[-1] + diferenca)
    return valores


def registrar_evento(venda: Venda, tipo: str, usuario=None, detalhe: str = "") -> VendaEvento:
    return VendaEvento.objects.create(
        venda=venda,
        tipo=tipo,
        usuario=usuario if getattr(usuario, "is_authenticated", False) else None,
        detalhe=detalhe or "",
    )


@transaction.atomic
def criar_venda_com_itens(
    *,
    cliente,
    vendedor,
    data_venda,
    tipo_pagamento: str,
    numero_parcelas: int,
    intervalo_parcelas_dias: int,
    acrescimo: Decimal,
    observacoes: str,
    itens: Iterable[ItemVendaPayload],
) -> Venda:
    venda = Venda.objects.create(
        cliente=cliente,
        vendedor=vendedor if getattr(vendedor, "is_authenticated", False) else vendedor,
        data_venda=data_venda,
        tipo_pagamento=tipo_pagamento,
        numero_parcelas=numero_parcelas,
        intervalo_parcelas_dias=intervalo_parcelas_dias,
        acrescimo=_to_dec_2(acrescimo),
        observacoes=observacoes or "",
        status=StatusVendaChoices.RASCUNHO,
    )

    bulk: list[ItemVenda] = []
    for payload in itens:
        bruto = _to_dec_2(payload.quantidade * payload.preco_unitario)
        desconto = _to_dec_2(payload.desconto)
        subtotal = bruto - desconto
        if subtotal < 0:
            subtotal = Decimal("0.00")
        bulk.append(
            ItemVenda(
                venda=venda,
                produto=payload.produto,
                quantidade=_to_dec_3(payload.quantidade),
                preco_unitario=_to_dec_2(payload.preco_unitario),
                desconto=desconto,
                subtotal=_to_dec_2(subtotal),
            )
        )
    ItemVenda.objects.bulk_create(bulk)

    venda = Venda.objects.select_for_update().get(pk=venda.pk)
    venda = recalcular_totais(venda)
    registrar_evento(venda, TipoEventoVendaChoices.CRIACAO, vendedor, "Venda criada")
    return venda


@transaction.atomic
def confirmar_venda(venda: Venda, usuario=None) -> Venda:
    venda = Venda.objects.select_for_update().get(pk=venda.pk)
    if venda.status in (StatusVendaChoices.CANCELADA, StatusVendaChoices.FATURADA, StatusVendaChoices.FINALIZADA):
        return venda
    if venda.status == StatusVendaChoices.CONFIRMADA:
        return venda
    venda.status = StatusVendaChoices.CONFIRMADA
    venda.save(update_fields=["status", "atualizado_em"])
    registrar_evento(venda, TipoEventoVendaChoices.CONFIRMACAO, usuario, "Venda confirmada")
    return venda


@transaction.atomic
def converter_orcamento_em_venda(venda: Venda, usuario=None) -> Venda:
    venda = Venda.objects.select_for_update().get(pk=venda.pk)
    if venda.tipo_documento == TipoDocumentoVendaChoices.VENDA:
        return venda
    if venda.status == StatusVendaChoices.CANCELADA:
        raise ValueError("Orcamento cancelado nao pode ser convertido.")

    venda.tipo_documento = TipoDocumentoVendaChoices.VENDA
    if venda.status == StatusVendaChoices.RASCUNHO:
        venda.status = StatusVendaChoices.CONFIRMADA
    venda.save(update_fields=["tipo_documento", "status", "atualizado_em"])
    registrar_evento(venda, TipoEventoVendaChoices.CONFIRMACAO, usuario, "Orcamento convertido em venda")
    return venda


@transaction.atomic
def faturar_venda(venda: Venda, usuario=None) -> FaturamentoResult:
    venda = (
        Venda.objects.select_for_update()
        .select_related("cliente", "vendedor")
        .prefetch_related("itens__produto")
        .get(pk=venda.pk)
    )

    if venda.status == StatusVendaChoices.CANCELADA:
        raise ValueError("Venda cancelada nao pode ser faturada.")
    if venda.tipo_documento == TipoDocumentoVendaChoices.ORCAMENTO:
        raise ValueError("Converta o orcamento em venda antes de faturar.")
    if venda.status in (StatusVendaChoices.FATURADA, StatusVendaChoices.FINALIZADA):
        return FaturamentoResult(
            venda=venda,
            movimentos_criados=0,
            recebiveis_criados=0,
            boletos_criados=0,
            already_processed=True,
        )

    itens = list(venda.itens.all())
    if not itens:
        raise ValueError("Venda sem itens nao pode ser faturada.")

    produto_ids = list({item.produto_id for item in itens})
    cfg_map = {
        cfg.produto_id: cfg
        for cfg in ProdutoEstoque.objects.select_for_update().filter(produto_id__in=produto_ids)
    }
    for item in itens:
        cfg = cfg_map.get(item.produto_id)
        saldo = cfg.saldo_atual if cfg else Decimal("0.000")
        if saldo < (item.quantidade or Decimal("0.000")):
            raise ValueError(f"Saldo insuficiente para produto {item.produto.nome}.")

    movimentos_criados = 0
    recebiveis_criados = 0
    boletos_criados = 0

    for item in itens:
        if VendaMovimentoEstoque.objects.filter(
            venda=venda,
            item_venda=item,
            tipo=TipoMovimentoVendaChoices.SAIDA,
        ).exists():
            continue

        mov_result = registrar_saida(
            produto=item.produto,
            quantidade=_to_dec_3(item.quantidade),
            data_movimento=venda.data_venda,
            observacao=f"Saida por faturamento da venda #{venda.id}",
        )
        VendaMovimentoEstoque.objects.create(
            venda=venda,
            item_venda=item,
            movimento=mov_result.movimento,
            tipo=TipoMovimentoVendaChoices.SAIDA,
            quantidade=_to_dec_3(item.quantidade),
        )
        movimentos_criados += 1

    eh_prazo = venda.tipo_pagamento in (TipoPagamentoChoices.PARCELADO, TipoPagamentoChoices.PARCELADO_BOLETO)
    if eh_prazo:
        parcelas = max(1, venda.numero_parcelas or 1)
        valores = _parcelar_valor(venda.total_final, parcelas)
        base_vencimento = venda.primeiro_vencimento or venda.data_venda
        for idx in range(parcelas):
            numero_parcela = idx + 1
            data_venc = base_vencimento + timedelta(days=(idx * (venda.intervalo_parcelas_dias or 30)))
            ref = f"VENDA-{venda.id}-P{numero_parcela:02d}"

            vinculo = VendaRecebivel.objects.filter(venda=venda, numero_parcela=numero_parcela).first()
            if vinculo is None:
                recebivel = (
                    Recebivel.objects.filter(origem_app="vendas", origem_pk=venda.id, referencia_externa=ref).first()
                )
                if recebivel is None:
                    recebivel = Recebivel.objects.create(
                        descricao=f"Venda #{venda.id} - parcela {numero_parcela}/{parcelas}",
                        data_prevista=data_venc,
                        valor=valores[idx],
                        status=StatusRecebivelChoices.ABERTO,
                        origem_app="vendas",
                        origem_pk=venda.id,
                        referencia_externa=ref,
                    )
                    recebiveis_criados += 1
                VendaRecebivel.objects.create(
                    venda=venda,
                    numero_parcela=numero_parcela,
                    recebivel=recebivel,
                    valor=valores[idx],
                    data_vencimento=data_venc,
                )

            if venda.tipo_pagamento == TipoPagamentoChoices.PARCELADO_BOLETO:
                numero_boleto = f"VD{venda.id:08d}-{numero_parcela:02d}"
                boleto, created = Boleto.objects.get_or_create(
                    numero_boleto=numero_boleto,
                    defaults={
                        "cliente": venda.cliente,
                        "descricao": f"Venda #{venda.id} - parcela {numero_parcela}/{parcelas}",
                        "valor": valores[idx],
                        "data_vencimento": data_venc,
                        "vendedor": venda.vendedor,
                        "status": StatusBoletoChoices.ABERTO,
                        "observacoes": "Gerado automaticamente pelo faturamento de venda.",
                    },
                )
                if created:
                    boletos_criados += 1
                VendaBoleto.objects.get_or_create(
                    venda=venda,
                    numero_parcela=numero_parcela,
                    defaults={"boleto": boleto},
                )

    if venda.status != StatusVendaChoices.CONFIRMADA:
        venda.status = StatusVendaChoices.CONFIRMADA
    venda.status = StatusVendaChoices.FATURADA
    venda.faturada_em = timezone.now()
    venda.faturada_por = usuario if getattr(usuario, "is_authenticated", False) else None
    venda.save(update_fields=["status", "faturada_em", "faturada_por", "atualizado_em"])

    registrar_evento(venda, TipoEventoVendaChoices.FATURAMENTO, usuario, "Venda faturada")

    return FaturamentoResult(
        venda=venda,
        movimentos_criados=movimentos_criados,
        recebiveis_criados=recebiveis_criados,
        boletos_criados=boletos_criados,
        already_processed=False,
    )


@transaction.atomic
def finalizar_venda(venda: Venda, usuario=None) -> Venda:
    venda = Venda.objects.select_for_update().get(pk=venda.pk)
    if venda.status == StatusVendaChoices.CANCELADA:
        raise ValueError("Venda cancelada nao pode ser finalizada.")
    if venda.status == StatusVendaChoices.FINALIZADA:
        return venda
    if venda.status != StatusVendaChoices.FATURADA:
        raise ValueError("Apenas vendas faturadas podem ser finalizadas.")
    venda.status = StatusVendaChoices.FINALIZADA
    venda.save(update_fields=["status", "atualizado_em"])
    registrar_evento(venda, TipoEventoVendaChoices.FINALIZACAO, usuario, "Venda finalizada")
    return venda


@transaction.atomic
def cancelar_venda(venda: Venda, usuario=None, motivo: str = "") -> CancelamentoResult:
    venda = (
        Venda.objects.select_for_update()
        .prefetch_related("itens__produto", "movimentos_estoque__item_venda", "recebiveis__recebivel", "boletos__boleto")
        .get(pk=venda.pk)
    )

    if venda.status == StatusVendaChoices.CANCELADA:
        return CancelamentoResult(venda, 0, 0, 0, already_canceled=True)

    if venda.boletos.filter(boleto__status=StatusBoletoChoices.PAGO).exists():
        raise ValueError("Nao e possivel cancelar venda com boleto pago.")
    if venda.recebiveis.filter(recebivel__status=StatusRecebivelChoices.RECEBIDO).exists():
        raise ValueError("Nao e possivel cancelar venda com recebivel recebido.")

    reversoes_estoque = 0
    recebiveis_cancelados = 0
    boletos_cancelados = 0

    if venda.status in (StatusVendaChoices.FATURADA, StatusVendaChoices.FINALIZADA):
        saidas = (
            VendaMovimentoEstoque.objects.select_related("item_venda__produto")
            .filter(venda=venda, tipo=TipoMovimentoVendaChoices.SAIDA)
            .order_by("id")
        )
        for registro in saidas:
            if VendaMovimentoEstoque.objects.filter(
                venda=venda,
                item_venda=registro.item_venda,
                tipo=TipoMovimentoVendaChoices.REVERSAO,
            ).exists():
                continue
            mov_result = registrar_entrada(
                produto=registro.item_venda.produto,
                quantidade=_to_dec_3(registro.quantidade),
                data_movimento=timezone.localdate(),
                observacao=f"Reversao por cancelamento da venda #{venda.id}",
            )
            VendaMovimentoEstoque.objects.create(
                venda=venda,
                item_venda=registro.item_venda,
                movimento=mov_result.movimento,
                tipo=TipoMovimentoVendaChoices.REVERSAO,
                quantidade=_to_dec_3(registro.quantidade),
            )
            reversoes_estoque += 1

    for vinculo in venda.recebiveis.select_related("recebivel"):
        if vinculo.recebivel.status == StatusRecebivelChoices.ABERTO:
            vinculo.recebivel.status = StatusRecebivelChoices.CANCELADO
            vinculo.recebivel.save(update_fields=["status", "atualizado_em"])
            recebiveis_cancelados += 1

    for vinculo in venda.boletos.select_related("boleto"):
        if vinculo.boleto.status not in (StatusBoletoChoices.PAGO, StatusBoletoChoices.CANCELADO):
            vinculo.boleto.status = StatusBoletoChoices.CANCELADO
            vinculo.boleto.save(update_fields=["status", "atualizado_em"])
            boletos_cancelados += 1

    venda.status = StatusVendaChoices.CANCELADA
    venda.cancelada_em = timezone.now()
    venda.cancelada_por = usuario if getattr(usuario, "is_authenticated", False) else None
    venda.save(update_fields=["status", "cancelada_em", "cancelada_por", "atualizado_em"])

    registrar_evento(
        venda,
        TipoEventoVendaChoices.CANCELAMENTO,
        usuario,
        motivo or "Venda cancelada",
    )

    return CancelamentoResult(
        venda=venda,
        reversoes_estoque=reversoes_estoque,
        recebiveis_cancelados=recebiveis_cancelados,
        boletos_cancelados=boletos_cancelados,
        already_canceled=False,
    )
