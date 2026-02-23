from django.urls import path

from boletos.views import (
    BoletoListView,
    BoletoDetailView,
    BoletoCreateView,
    BoletoUpdateView,
    BoletoRegistrarPagamentoView,
    ClienteListView,
    ClienteDetailView,
    ClienteCreateView,
    ClienteUpdateView,
    ClienteAdicionarListaNegraMixin,
    ClienteRemoverListaNegraView,
    ListaNegraBoletoListView,
    ControleFiadoDetailView,
    ControleFiadoUpdateView,
    ControleFiadoListView,
    BoletoImportVencidosView,
    BoletoExportComprovantesView,
    BoletoExportPDFView,
)

app_name = "boletos"

urlpatterns = [
    # Boletos
    path("", BoletoListView.as_view(), name="boleto_list"),
    path("boleto/<int:pk>/", BoletoDetailView.as_view(), name="boleto_detail"),
    path("boleto/novo/", BoletoCreateView.as_view(), name="boleto_create"),
    path("boleto/<int:pk>/editar/", BoletoUpdateView.as_view(), name="boleto_update"),
    path(
        "boleto/<int:pk>/pagamento/",
        BoletoRegistrarPagamentoView.as_view(),
        name="boleto_pagamento",
    ),
    # Clientes
    path("clientes/", ClienteListView.as_view(), name="cliente_list"),
    path("cliente/<int:pk>/", ClienteDetailView.as_view(), name="cliente_detail"),
    path("cliente/novo/", ClienteCreateView.as_view(), name="cliente_create"),
    path("cliente/<int:pk>/editar/", ClienteUpdateView.as_view(), name="cliente_update"),
    # Lista Negra
    path("lista-negra/", ListaNegraBoletoListView.as_view(), name="lista_negra"),
    path(
        "cliente/<int:pk>/adicionar-lista-negra/",
        ClienteAdicionarListaNegraMixin.as_view(),
        name="cliente_adicionar_lista_negra",
    ),
    path(
        "cliente/<int:pk>/remover-lista-negra/",
        ClienteRemoverListaNegraView.as_view(),
        name="cliente_remover_lista_negra",
    ),
    # Importação de boletos vencidos (CSV)
    path(
        "importar-vencidos/",
        # view will be resolved by dotted path import below to avoid circulars
        # defined in views.py as BoletoImportVencidosView
        BoletoImportVencidosView.as_view(),
        name="boleto_import_vencidos",
    ),
    path("export-necessita-comprovante/", BoletoExportComprovantesView.as_view(), name="boleto_export_necessita_comprovante"),
    path("export-necessita-comprovante/pdf/", BoletoExportPDFView.as_view(), name="boleto_export_necessita_comprovante_pdf"),
    # Controle de Fiado
    path("fiados/", ControleFiadoListView.as_view(), name="controle_fiado_list"),
    path(
        "fiado/<int:pk>/",
        ControleFiadoDetailView.as_view(),
        name="controle_fiado_detail",
    ),
    path(
        "fiado/<int:pk>/editar/",
        ControleFiadoUpdateView.as_view(),
        name="controle_fiado_update",
    ),
]
