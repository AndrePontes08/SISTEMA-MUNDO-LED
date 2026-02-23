from __future__ import annotations

from django.contrib import admin
from django.utils.html import format_html

from boletos.models import (
    Boleto,
    Cliente,
    ClienteListaNegra,
    ControleFiado,
    ParcelaBoleto,
    RamoAtuacao,
)


class ParcelaBoletoInline(admin.TabularInline):
    model = ParcelaBoleto
    extra = 0
    fields = (
        "numero_parcela",
        "valor",
        "data_vencimento",
        "data_pagamento",
        "status",
    )


@admin.register(RamoAtuacao)
class RamoAtuacaoAdmin(admin.ModelAdmin):
    list_display = ("nome", "ativo", "criado_em")
    search_fields = ("nome",)
    list_filter = ("ativo", "criado_em")


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("nome", "cpf_cnpj", "ramo_atuacao", "telefone", "ativo", "em_lista_negra")
    search_fields = ("nome", "nome_normalizado", "cpf_cnpj", "email")
    list_filter = ("ativo", "criado_em", "ramo_atuacao")
    readonly_fields = ("nome_normalizado", "criado_em")
    fieldsets = (
        ("Informações Básicas", {
            "fields": ("nome", "nome_normalizado", "cpf_cnpj", "email", "telefone")
        }),
        ("Detalhes", {
            "fields": ("ramo_atuacao", "endereco", "ativo", "criado_em")
        }),
    )

    def em_lista_negra(self, obj):
        if hasattr(obj, "lista_negra") and obj.lista_negra.ativo:
            return format_html('<span style="color: red;">🚫 SIM</span>')
        return "Não"
    em_lista_negra.short_description = "Lista Negra"


@admin.register(ClienteListaNegra)
class ClienteListaNegraAdmin(admin.ModelAdmin):
    list_display = ("cliente", "data_bloqueio", "responsavel", "ativo")
    search_fields = ("cliente__nome", "motivo")
    list_filter = ("ativo", "data_bloqueio", "responsavel")
    readonly_fields = ("data_bloqueio", "cliente")
    fields = ("cliente", "motivo", "responsavel", "ativo", "data_bloqueio")


@admin.register(Boleto)
class BoletoAdmin(admin.ModelAdmin):
    list_display = (
        "numero_boleto",
        "cliente",
        "valor",
        "data_vencimento",
        "status_display",
        "vendedor",
    )
    search_fields = ("numero_boleto", "cliente__nome", "descricao")
    list_filter = ("status", "data_vencimento", "criado_em", "vendedor")
    readonly_fields = ("numero_boleto", "criado_em", "atualizado_em", "dias_vencimento")
    inlines = [ParcelaBoletoInline]
    fieldsets = (
        ("Identificação", {
            "fields": ("numero_boleto", "cliente", "descricao")
        }),
        ("Valores e Datas", {
            "fields": ("valor", "data_emissao", "data_vencimento", "dias_vencimento", "data_pagamento")
        }),
        ("Responsável e Status", {
            "fields": ("vendedor", "status")
        }),
        ("Documentos", {
            "fields": ("comprovante_pagamento",)
        }),
        ("Observações e Auditoria", {
            "fields": ("observacoes", "criado_em", "atualizado_em"),
            "classes": ("collapse",)
        }),
    )

    def status_display(self, obj):
        colors = {
            "ABERTO": "#FFA500",
            "PAGO": "#008000",
            "VENCIDO": "#FF0000",
            "PENDENTE": "#FFFF00",
            "CANCELADO": "#808080",
        }
        color = colors.get(obj.status, "#000000")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display(),
        )
    status_display.short_description = "Status"


@admin.register(ParcelaBoleto)
class ParcelaBoletoAdmin(admin.ModelAdmin):
    list_display = ("boleto", "numero_parcela", "valor", "data_vencimento", "status")
    search_fields = ("boleto__numero_boleto",)
    list_filter = ("status", "data_vencimento")
    readonly_fields = ("boleto",)


@admin.register(ControleFiado)
class ControleFiadoAdmin(admin.ModelAdmin):
    list_display = (
        "cliente",
        "limite_credito",
        "saldo_fiado",
        "saldo_disponivel_display",
        "percentual_display",
        "status",
    )
    search_fields = ("cliente__nome",)
    list_filter = ("status", "criado_em")
    readonly_fields = ("saldo_disponivel_display", "percentual_display", "criado_em", "atualizado_em")
    fields = (
        "cliente",
        "limite_credito",
        "saldo_fiado",
        "saldo_disponivel_display",
        "percentual_display",
        "status",
        "criado_em",
        "atualizado_em",
    )

    def saldo_disponivel_display(self, obj):
        return f"R$ {obj.saldo_disponivel}"
    saldo_disponivel_display.short_description = "Saldo Disponível"

    def percentual_display(self, obj):
        return f"{obj.percentual_utilizado:.1f}%"
    percentual_display.short_description = "% Utilizado"
