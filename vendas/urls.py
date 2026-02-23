from __future__ import annotations

from django.urls import path

from vendas.views import (
    VendaCancelarView,
    VendaConfirmarView,
    VendaCreateView,
    VendaDetailView,
    VendaFaturarView,
    VendaFinalizarView,
    OrcamentoConverterView,
    VendaPDFView,
    VendaListView,
    VendaUpdateView,
    VendasDashboardView,
)

app_name = "vendas"

urlpatterns = [
    path("", VendaListView.as_view(), name="venda_list"),
    path("dashboard/", VendasDashboardView.as_view(), name="dashboard"),
    path("nova/", VendaCreateView.as_view(), name="venda_create"),
    path("<int:pk>/", VendaDetailView.as_view(), name="venda_detail"),
    path("<int:pk>/pdf/", VendaPDFView.as_view(), name="venda_pdf"),
    path("<int:pk>/editar/", VendaUpdateView.as_view(), name="venda_update"),
    path("<int:pk>/confirmar/", VendaConfirmarView.as_view(), name="venda_confirmar"),
    path("<int:pk>/converter-orcamento/", OrcamentoConverterView.as_view(), name="orcamento_converter"),
    path("<int:pk>/faturar/", VendaFaturarView.as_view(), name="venda_faturar"),
    path("<int:pk>/finalizar/", VendaFinalizarView.as_view(), name="venda_finalizar"),
    path("<int:pk>/cancelar/", VendaCancelarView.as_view(), name="venda_cancelar"),
]
