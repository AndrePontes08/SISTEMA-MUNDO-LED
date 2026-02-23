from __future__ import annotations

from django.contrib import admin

from vendas.models import ItemVenda, Venda, VendaBoleto, VendaEvento, VendaMovimentoEstoque, VendaRecebivel


class ItemVendaInline(admin.TabularInline):
    model = ItemVenda
    extra = 0
    autocomplete_fields = ("produto",)


@admin.register(Venda)
class VendaAdmin(admin.ModelAdmin):
    list_display = ("codigo_identificacao", "tipo_documento", "cliente", "status", "data_venda", "tipo_pagamento", "total_final", "vendedor")
    list_filter = ("tipo_documento", "status", "tipo_pagamento", "data_venda")
    search_fields = ("id", "cliente__nome", "cliente__nome_normalizado")
    autocomplete_fields = ("cliente", "vendedor")
    readonly_fields = ("subtotal", "desconto_total", "total_final", "criado_em", "atualizado_em")
    inlines = [ItemVendaInline]


@admin.register(ItemVenda)
class ItemVendaAdmin(admin.ModelAdmin):
    list_display = ("id", "venda", "produto", "quantidade", "preco_unitario", "desconto", "subtotal")
    search_fields = ("venda__id", "produto__nome", "produto__nome_normalizado")
    autocomplete_fields = ("venda", "produto")


@admin.register(VendaEvento)
class VendaEventoAdmin(admin.ModelAdmin):
    list_display = ("id", "venda", "tipo", "usuario", "criado_em")
    list_filter = ("tipo", "criado_em")
    search_fields = ("venda__id", "detalhe")
    autocomplete_fields = ("venda", "usuario")


@admin.register(VendaMovimentoEstoque)
class VendaMovimentoEstoqueAdmin(admin.ModelAdmin):
    list_display = ("id", "venda", "item_venda", "tipo", "quantidade", "movimento")
    list_filter = ("tipo",)
    autocomplete_fields = ("venda", "item_venda", "movimento")


@admin.register(VendaRecebivel)
class VendaRecebivelAdmin(admin.ModelAdmin):
    list_display = ("id", "venda", "numero_parcela", "valor", "data_vencimento", "recebivel")
    autocomplete_fields = ("venda", "recebivel")


@admin.register(VendaBoleto)
class VendaBoletoAdmin(admin.ModelAdmin):
    list_display = ("id", "venda", "numero_parcela", "boleto")
    autocomplete_fields = ("venda", "boleto")
