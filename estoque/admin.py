from __future__ import annotations

from django.contrib import admin

from estoque.models import (
    ProdutoEstoque,
    Lote,
    EstoqueMovimento,
    AlertaEstoque,
    ProdutoEstoqueUnidade,
    TransferenciaEstoque,
)


@admin.register(ProdutoEstoque)
class ProdutoEstoqueAdmin(admin.ModelAdmin):
    list_display = ("produto", "saldo_atual", "estoque_minimo", "estoque_ideal", "estoque_maximo", "atualizado_em")
    search_fields = ("produto__nome", "produto__nome_normalizado", "produto__sku")
    list_filter = ("atualizado_em",)
    autocomplete_fields = ("produto",)


@admin.register(Lote)
class LoteAdmin(admin.ModelAdmin):
    list_display = ("id", "produto", "data_entrada", "quantidade_inicial", "quantidade_restante", "compra")
    search_fields = ("produto__nome", "produto__sku")
    list_filter = ("data_entrada",)
    autocomplete_fields = ("produto", "compra", "item_compra")


@admin.register(EstoqueMovimento)
class EstoqueMovimentoAdmin(admin.ModelAdmin):
    list_display = ("id", "produto", "tipo", "quantidade", "data_movimento", "compra", "lote")
    search_fields = ("produto__nome", "produto__sku", "observacao")
    list_filter = ("tipo", "data_movimento")
    autocomplete_fields = ("produto", "compra", "item_compra", "lote")


@admin.register(AlertaEstoque)
class AlertaEstoqueAdmin(admin.ModelAdmin):
    list_display = ("id", "produto", "status", "saldo_no_momento", "minimo_configurado", "criado_em", "resolvido_em")
    list_filter = ("status", "criado_em")
    search_fields = ("produto__nome", "produto__sku")
    autocomplete_fields = ("produto",)


@admin.register(ProdutoEstoqueUnidade)
class ProdutoEstoqueUnidadeAdmin(admin.ModelAdmin):
    list_display = ("produto", "unidade", "saldo_atual", "atualizado_em")
    list_filter = ("unidade",)
    search_fields = ("produto__nome", "produto__sku")
    autocomplete_fields = ("produto",)


@admin.register(TransferenciaEstoque)
class TransferenciaEstoqueAdmin(admin.ModelAdmin):
    list_display = ("id", "lote_referencia", "produto", "unidade_origem", "unidade_destino", "quantidade", "data_transferencia", "usuario")
    list_filter = ("unidade_origem", "unidade_destino", "data_transferencia")
    search_fields = ("produto__nome", "produto__sku", "observacao")
    autocomplete_fields = ("produto", "usuario")
