from django.urls import path

from contas.views import (
    ContasDashboardView,
    ContaListView,
    ContaDetailView,
    ContaCreateView,
    ContaUpdateView,
    ConfirmarPagamentoView,
    ImportCSVView,
    ReabrirContaView,
    ContaToggleExigeComprovanteView,
    ContasPeriodoPDFView,
    DownloadComprovanteView,
    DownloadBoletoView,
    DownloadNotaFiscalView,
    DownloadPedidoView,
)

app_name = "contas"

urlpatterns = [
    path("", ContasDashboardView.as_view(), name="dashboard"),
    path("lista/", ContaListView.as_view(), name="conta_list"),
    path("nova/", ContaCreateView.as_view(), name="conta_create"),
    path("<int:pk>/", ContaDetailView.as_view(), name="conta_detail"),
    path("<int:pk>/editar/", ContaUpdateView.as_view(), name="conta_update"),
    path("<int:pk>/confirmar-pagamento/", ConfirmarPagamentoView.as_view(), name="confirmar_pagamento"),
    path("<int:pk>/reabrir/", ReabrirContaView.as_view(), name="reabrir_conta"),
    path("<int:pk>/toggle-exige-comprovante/", ContaToggleExigeComprovanteView.as_view(), name="toggle_exige_comprovante"),
    path("<int:pk>/download/comprovante/", DownloadComprovanteView.as_view(), name="download_comprovante"),
    path("<int:pk>/download/boleto/", DownloadBoletoView.as_view(), name="download_boleto"),
    path("<int:pk>/download/nota-fiscal/", DownloadNotaFiscalView.as_view(), name="download_nota_fiscal"),
    path("<int:pk>/download/pedido/", DownloadPedidoView.as_view(), name="download_pedido"),
    path("relatorios/pdf/<str:periodo>/", ContasPeriodoPDFView.as_view(), name="contas_periodo_pdf"),
    path("importar/", ImportCSVView.as_view(), name="import_csv"),
]
