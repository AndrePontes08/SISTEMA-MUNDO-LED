from django.contrib import admin

from importadores.models import (
    CaixaImportacaoInconsistencia,
    CaixaRelatorioImportacao,
    CaixaRelatorioItem,
    MovimentoVendaEstoque,
    UnidadeContaFinanceiraConfig,
)


class CaixaRelatorioItemInline(admin.TabularInline):
    model = CaixaRelatorioItem
    extra = 0
    readonly_fields = ("codigo_mercadoria", "descricao", "quantidade", "produto", "estoque_baixado", "mensagem")


class CaixaImportacaoInconsistenciaInline(admin.TabularInline):
    model = CaixaImportacaoInconsistencia
    extra = 0
    readonly_fields = ("codigo", "descricao", "detalhes", "criado_em")


@admin.register(CaixaRelatorioImportacao)
class CaixaRelatorioImportacaoAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "data_referencia",
        "unidade",
        "total_vendas",
        "total_trocas",
        "status",
        "itens_detectados",
        "itens_baixados",
        "itens_inconsistentes",
        "criado_em",
    )
    list_filter = ("status", "unidade", "data_referencia")
    search_fields = ("arquivo_nome", "empresa_nome", "arquivo_hash")
    inlines = [CaixaRelatorioItemInline, CaixaImportacaoInconsistenciaInline]


@admin.register(UnidadeContaFinanceiraConfig)
class UnidadeContaFinanceiraConfigAdmin(admin.ModelAdmin):
    list_display = ("unidade", "conta_bancaria", "ativa")
    list_filter = ("unidade", "ativa")


@admin.register(MovimentoVendaEstoque)
class MovimentoVendaEstoqueAdmin(admin.ModelAdmin):
    list_display = ("id", "importacao", "item", "unidade", "tipo", "criado_em")
    list_filter = ("unidade", "tipo")
