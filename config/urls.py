from __future__ import annotations

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),

    # Home/Dashboard bÃ¡sico (inclui login, logout, password reset)
    path("", include("core.urls")),

    # Apps do ERP (serÃ£o implementados nos prÃ³ximos passos)
    path("compras/", include("compras.urls")),
    path("estoque/", include("estoque.urls")),
    path("contas/", include("contas.urls")),
    path("boletos/", include("boletos.urls")),
    path("vendas/", include("vendas.urls")),
    path("relatorios/", include("relatorios.urls")),
    path("financeiro/", include("financeiro.urls")),
    path("importadores/", include("importadores.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


