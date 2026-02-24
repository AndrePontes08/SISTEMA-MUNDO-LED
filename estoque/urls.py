from django.urls import path

from estoque.views import (
    ConfirmarRecebimentoCompraView,
    ContagemRapidaView,
    EstoqueCompletoView,
    EstoqueDashboardView,
    ProdutoEstoqueListView,
    ProdutoEstoqueUpdateView,
    SaidaOperacionalView,
    MovimentoCreateView,
    MovimentoListView,
    EntradaPorCompraView,
    IndicadoresEstoqueView,
    RecebimentoCompraDetailView,
    RecebimentoCompraListView,
    TransferenciaCreateView,
)

app_name = "estoque"

urlpatterns = [
    path("", EstoqueDashboardView.as_view(), name="dashboard"),
    path("produtos/", ProdutoEstoqueListView.as_view(), name="produtoestoque_list"),
    path("completo/", EstoqueCompletoView.as_view(), name="estoque_completo"),
    path("produtos/<int:pk>/editar/", ProdutoEstoqueUpdateView.as_view(), name="produtoestoque_update"),
    path("movimentos/novo/", MovimentoCreateView.as_view(), name="movimento_create"),
    path("transferencias/nova/", TransferenciaCreateView.as_view(), name="transferencia_create"),
    path("contagem-rapida/", ContagemRapidaView.as_view(), name="contagem_rapida"),
    path("saidas-operacionais/", SaidaOperacionalView.as_view(), name="saida_operacional"),
    path("movimentos/", MovimentoListView.as_view(), name="movimento_list"),
    path("indicadores/", IndicadoresEstoqueView.as_view(), name="indicadores"),
    path("entrada/compra/<int:compra_id>/", EntradaPorCompraView.as_view(), name="entrada_por_compra"),
    path("recebimentos/", RecebimentoCompraListView.as_view(), name="recebimento_list"),
    path("recebimentos/<int:pk>/", RecebimentoCompraDetailView.as_view(), name="recebimento_detail"),
    path("recebimentos/<int:pk>/confirmar/", ConfirmarRecebimentoCompraView.as_view(), name="recebimento_confirmar"),
]
