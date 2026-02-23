from django.urls import path

from importadores.views import CaixaImportacaoDetailView, CaixaImportacaoListView, CaixaImportarView

app_name = "importadores"

urlpatterns = [
    path("caixa/importar/", CaixaImportarView.as_view(), name="caixa_importar"),
    path("caixa/importacoes/", CaixaImportacaoListView.as_view(), name="caixa_importacoes"),
    path("caixa/importacoes/<int:pk>/", CaixaImportacaoDetailView.as_view(), name="caixa_importacao_detail"),
]

