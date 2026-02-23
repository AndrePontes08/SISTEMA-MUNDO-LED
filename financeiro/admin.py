from django.contrib import admin

from financeiro.models import (
    Conciliacao,
    ConciliacaoItem,
    ContaBancaria,
    ExtratoImportacao,
    Recebivel,
    TransacaoBancaria,
)


@admin.register(ContaBancaria)
class ContaBancariaAdmin(admin.ModelAdmin):
    list_display = ("nome", "banco_nome", "agencia", "conta_numero", "ativa")
    list_filter = ("ativa", "banco_nome")
    search_fields = ("nome", "banco_nome", "agencia", "conta_numero", "banco_codigo")


@admin.register(ExtratoImportacao)
class ExtratoImportacaoAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "conta",
        "banco_nome",
        "status",
        "transacoes_detectadas",
        "transacoes_importadas",
        "transacoes_duplicadas",
        "criado_em",
    )
    list_filter = ("status", "banco_nome", "criado_em")
    search_fields = ("id", "arquivo_nome", "arquivo_sha256", "log_erro")
    readonly_fields = ("arquivo_sha256", "resumo", "alertas")


@admin.register(TransacaoBancaria)
class TransacaoBancariaAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "conta",
        "data_lancamento",
        "descricao",
        "valor",
        "tipo_movimento",
        "status_conciliacao",
    )
    list_filter = ("tipo_movimento", "status_conciliacao", "conta")
    search_fields = ("descricao", "external_id", "idempotency_key")
    readonly_fields = ("idempotency_key",)


@admin.register(Recebivel)
class RecebivelAdmin(admin.ModelAdmin):
    list_display = ("id", "descricao", "data_prevista", "valor", "status", "origem_app")
    list_filter = ("status", "origem_app")
    search_fields = ("descricao", "referencia_externa")


class ConciliacaoItemInline(admin.TabularInline):
    model = ConciliacaoItem
    extra = 0


@admin.register(Conciliacao)
class ConciliacaoAdmin(admin.ModelAdmin):
    list_display = ("id", "transacao", "status_final", "tipo", "conciliado_por", "conciliado_em")
    list_filter = ("status_final", "tipo", "conciliado_em")
    search_fields = ("transacao__descricao", "observacao")
    inlines = [ConciliacaoItemInline]

