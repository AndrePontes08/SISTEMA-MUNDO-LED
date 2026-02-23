from __future__ import annotations

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand


GROUPS = [
    "admin/gestor",
    "financeiro",
    "vendedor",
    "compras/estoque",
    "comprador",
    "estoquista",
]


def _assign_permissions(group: Group) -> int:
    """
    Tenta atribuir permissoes padroes por app de forma idempotente.
    """
    desired_codenames = set()

    if group.name == "admin/gestor":
        perms = Permission.objects.exclude(content_type__app_label__in=["admin", "sessions", "contenttypes"])
        group.permissions.set(perms)
        return perms.count()

    if group.name == "financeiro":
        desired_codenames |= {
            # contas
            "view_contaapagar", "add_contaapagar", "change_contaapagar",
            "view_categoria", "add_categoria", "change_categoria",
            "view_centrocusto", "add_centrocusto", "change_centrocusto",
            "view_regraimposto", "add_regraimposto", "change_regraimposto",
            "view_projecaomensal", "add_projecaomensal", "change_projecaomensal",
            # financeiro
            "view_contabancaria", "add_contabancaria", "change_contabancaria",
            "view_extratoimportacao", "add_extratoimportacao", "change_extratoimportacao",
            "view_transacaobancaria", "add_transacaobancaria", "change_transacaobancaria",
            "view_recebivel", "add_recebivel", "change_recebivel",
            "view_conciliacao", "add_conciliacao", "change_conciliacao",
            "view_conciliacaoitem", "add_conciliacaoitem", "change_conciliacaoitem",
            # importadores
            "view_caixarelatorioimportacao", "add_caixarelatorioimportacao", "change_caixarelatorioimportacao",
            "view_caixarelatorioitem", "add_caixarelatorioitem", "change_caixarelatorioitem",
            "view_caixaimportacaoinconsistencia", "add_caixaimportacaoinconsistencia", "change_caixaimportacaoinconsistencia",
            "view_movimentovendaestoque", "add_movimentovendaestoque", "change_movimentovendaestoque",
            "view_unidadecontafinanceiraconfig", "add_unidadecontafinanceiraconfig", "change_unidadecontafinanceiraconfig",
        }

    if group.name == "vendedor":
        desired_codenames |= {
            "view_boleto", "add_boleto", "change_boleto",
            "view_pagamentoboleto", "add_pagamentoboleto", "change_pagamentoboleto",
            "view_cliente", "add_cliente", "change_cliente",
            "view_listanegra", "add_listanegra", "change_listanegra",
            "view_fiado", "add_fiado", "change_fiado",
            "view_venda", "add_venda", "change_venda",
            "view_itemvenda", "add_itemvenda", "change_itemvenda",
            "view_vendaevento",
            "view_vendarecebivel",
            "view_vendaboleto",
        }

    if group.name == "compras/estoque":
        desired_codenames |= {
            "view_compra", "add_compra", "change_compra",
            "view_itemcompra", "add_itemcompra", "change_itemcompra",
            "view_garantia", "add_garantia", "change_garantia",
            "view_fornecedor", "add_fornecedor", "change_fornecedor",
            "view_produto", "add_produto", "change_produto",
            "view_estoquemovimento", "add_estoquemovimento", "change_estoquemovimento",
            "view_lote", "add_lote", "change_lote",
            "view_alertaestoque", "add_alertaestoque", "change_alertaestoque",
            # importadores (operacao caixa + baixa de estoque)
            "view_caixarelatorioimportacao", "add_caixarelatorioimportacao", "change_caixarelatorioimportacao",
            "view_caixarelatorioitem", "add_caixarelatorioitem", "change_caixarelatorioitem",
            "view_caixaimportacaoinconsistencia", "add_caixaimportacaoinconsistencia", "change_caixaimportacaoinconsistencia",
            "view_movimentovendaestoque", "add_movimentovendaestoque", "change_movimentovendaestoque",
        }

    if group.name == "comprador":
        desired_codenames |= {
            "view_compra", "add_compra", "change_compra",
            "view_itemcompra", "add_itemcompra", "change_itemcompra",
            "view_fornecedor", "add_fornecedor", "change_fornecedor",
            "view_produto", "add_produto", "change_produto",
            "view_compraevento",
        }

    if group.name == "estoquista":
        desired_codenames |= {
            "view_compra", "change_compra", "view_itemcompra",
            "view_estoquemovimento", "add_estoquemovimento", "change_estoquemovimento",
            "view_lote", "add_lote", "change_lote",
            "view_alertaestoque", "add_alertaestoque", "change_alertaestoque",
        }

    perms = Permission.objects.filter(codename__in=list(desired_codenames))
    group.permissions.set(perms)
    return perms.count()


class Command(BaseCommand):
    help = "Cria grupos padrao do ERP e atribui permissoes disponiveis (idempotente)."

    def handle(self, *args, **options):
        self.stdout.write("Criando/atualizando grupos...")
        for name in GROUPS:
            group, _ = Group.objects.get_or_create(name=name)
            count = _assign_permissions(group)
            self.stdout.write(f" - {name}: {count} permissoes atribuidas")

        self.stdout.write(self.style.SUCCESS("OK. Execute novamente apos migrar todos os apps."))
