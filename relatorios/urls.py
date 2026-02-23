from django.urls import path

from relatorios.views import RelatoriosDashboardView

app_name = "relatorios"

urlpatterns = [
    path("", RelatoriosDashboardView.as_view(), name="home"),
]
