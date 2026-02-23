from __future__ import annotations

from django.contrib import admin

from compras.models import (
    Fornecedor,
    FornecedorAlias,
    Produto,
    Compra,
    ItemCompra,
    Garantia,
)


class FornecedorAliasInline(admin.TabularInline):
    model = FornecedorAlias
    extra = 1
    fields = ("nome", "nome_normalizado")
    readonly_fields = ("nome_normalizado",)


@admin.register(Fornecedor)
class FornecedorAdmin(admin.ModelAdmin):
    list_display = ("nome", "cnpj", "criado_em")
    search_fields = ("nome", "nome_normalizado", "cnpj")
    list_filter = ("criado_em",)
    inlines = [FornecedorAliasInline]
    readonly_fields = ("nome_normalizado", "criado_em")


@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = ("nome", "sku", "ativo", "criado_em")
    search_fields = ("nome", "nome_normalizado", "sku")
    list_filter = ("ativo", "criado_em")
    readonly_fields = ("nome_normalizado", "criado_em")


class ItemCompraInline(admin.TabularInline):
    model = ItemCompra
    extra = 0
    autocomplete_fields = ("produto",)
    fields = ("produto", "quantidade", "preco_unitario")


class GarantiaInline(admin.TabularInline):
    model = Garantia
    extra = 0
    fields = ("item", "data_inicio", "data_fim", "arquivo", "observacao")
    autocomplete_fields = ("item",)


@admin.register(Compra)
class CompraAdmin(admin.ModelAdmin):
    list_display = ("id", "fornecedor", "centro_custo", "data_compra", "status", "orcamento_escolhido", "valor_total")
    list_filter = ("centro_custo", "data_compra", "status", "orcamento_escolhido")
    search_fields = ("id", "fornecedor__nome", "fornecedor__nome_normalizado")
    date_hierarchy = "data_compra"
    inlines = [ItemCompraInline]
    readonly_fields = ("valor_total", "criado_em")
    autocomplete_fields = ("fornecedor",)


@admin.register(Garantia)
class GarantiaAdmin(admin.ModelAdmin):
    list_display = ("id", "item", "data_inicio", "data_fim")
    list_filter = ("data_fim",)
    search_fields = ("item__compra__fornecedor__nome", "item__produto__nome")
    autocomplete_fields = ("item",)


@admin.register(FornecedorAlias)
class FornecedorAliasAdmin(admin.ModelAdmin):
    list_display = ("nome", "principal")
    search_fields = ("nome", "nome_normalizado", "principal__nome", "principal__nome_normalizado")
    autocomplete_fields = ("principal",)
    readonly_fields = ("nome_normalizado", "criado_em")


@admin.register(ItemCompra)
class ItemCompraAdmin(admin.ModelAdmin):
    list_display = ("id", "compra", "produto", "quantidade", "preco_unitario")
    search_fields = ("compra__id", "produto__nome", "produto__nome_normalizado")
    autocomplete_fields = ("compra", "produto")
