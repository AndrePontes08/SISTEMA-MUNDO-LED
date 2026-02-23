from django.urls import path

from financeiro.views import (
    ConciliacaoActionView,
    ConciliacaoListView,
    ContaBancariaCreateView,
    FinanceiroDashboardView,
    HistoricoImportacoesView,
    ImportacaoDetailView,
    ImportarOFXView,
)

app_name = "financeiro"

urlpatterns = [
    path("", FinanceiroDashboardView.as_view(), name="dashboard"),
    path("contas-bancarias/nova/", ContaBancariaCreateView.as_view(), name="conta_bancaria_create"),
    path("importar-ofx/", ImportarOFXView.as_view(), name="importar_ofx"),
    path("importacoes/", HistoricoImportacoesView.as_view(), name="historico_importacoes"),
    path("importacoes/<int:pk>/", ImportacaoDetailView.as_view(), name="importacao_detail"),
    path("conciliacao/", ConciliacaoListView.as_view(), name="conciliacao"),
    path("conciliacao/<int:pk>/acao/", ConciliacaoActionView.as_view(), name="conciliacao_action"),
]
