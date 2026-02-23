from django.urls import path

from compras.views import (
    CompraListView,
    CompraAprovacaoListView,
    CompraDetailView,
    CompraCreateView,
    CompraUpdateView,
    GarantiaCreateView,
    DownloadCompraFileView,
    FornecedorQuickCreateView,
    ProdutoQuickCreateView,
    MarcarRecebidaView,
    AprovarCompraView,
)

app_name = "compras"

urlpatterns = [
    path("", CompraListView.as_view(), name="compra_list"),
    path("aprovacoes/", CompraAprovacaoListView.as_view(), name="compra_aprovacao_list"),
    path("novo/", CompraCreateView.as_view(), name="compra_create"),
    path("<int:pk>/", CompraDetailView.as_view(), name="compra_detail"),
    path("<int:pk>/editar/", CompraUpdateView.as_view(), name="compra_update"),
    path("garantias/nova/", GarantiaCreateView.as_view(), name="garantia_create"),

    path("<int:pk>/download/<str:field>/", DownloadCompraFileView.as_view(), name="compra_download_file"),
    path("<int:pk>/aprovar/", AprovarCompraView.as_view(), name="compra_aprovar"),
    path("<int:pk>/marcar_recebida/", MarcarRecebidaView.as_view(), name="compra_marcar_recebida"),

    # Cadastro rápido
    path("quick/fornecedor/novo/", FornecedorQuickCreateView.as_view(), name="fornecedor_quick_create"),
    path("quick/produto/novo/", ProdutoQuickCreateView.as_view(), name="produto_quick_create"),
]
