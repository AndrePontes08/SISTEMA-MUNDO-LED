from __future__ import annotations

from django.contrib import admin
from .models import ContaAPagar, Categoria, ProjecaoMensal, RegraImposto


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    search_fields = ("nome",)
    list_display = ("id", "nome")
    ordering = ("nome",)


@admin.register(ContaAPagar)
class ContaAPagarAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "vencimento",
        "descricao",
        "centro_custo",
        "categoria",
        "valor",
        "status",
        "exige_boleto",
        "exige_nota_fiscal",
        "exige_comprovante",
        "importado",
    )
    list_filter = (
        "status",
        "centro_custo",
        "importado",
        "exige_boleto",
        "exige_nota_fiscal",
        "exige_comprovante",
        "categoria",
    )
    search_fields = ("descricao", "observacoes")
    date_hierarchy = "vencimento"
    ordering = ("-vencimento", "-id")

    fields = (
        "vencimento",
        "descricao",
        "centro_custo",
        "categoria",
        "valor",
        "status",
        "pago_em",
        "exige_boleto",
        "exige_nota_fiscal",
        "exige_comprovante",
        "boleto",
        "nota_fiscal",
        "comprovante",
        "observacoes",
        "importado",
        "fonte_importacao",
        "linha_importacao",
    )
    readonly_fields = ("importado", "fonte_importacao", "linha_importacao")


@admin.register(ProjecaoMensal)
class ProjecaoMensalAdmin(admin.ModelAdmin):
    list_display = ("id", "nome", "centro_custo", "categoria", "valor", "ativo")
    list_filter = ("ativo", "centro_custo", "categoria")
    search_fields = ("nome",)
    ordering = ("nome",)


@admin.register(RegraImposto)
class RegraImpostoAdmin(admin.ModelAdmin):
    list_display = ("id", "nome", "aliquota_percentual", "ativo", "criado_em")
    list_filter = ("ativo",)
    ordering = ("-id",)
