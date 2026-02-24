from __future__ import annotations

import os
from datetime import timedelta
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LogoutView
from django.db.models import DecimalField, ExpressionWrapper, F, Q, Value
from django.views.generic import TemplateView, ListView
from django.http import HttpResponse
from pathlib import Path

from importadores.services.resultado_diario_service import ResultadoDiarioService
from estoque.models import EstoqueMovimento, SaidaOperacionalEstoque
from vendas.models import ItemVenda


def healthz(request):
    return HttpResponse("ok", content_type="text/plain")


class HomeView(LoginRequiredMixin, TemplateView):
    template_name = "base.html"

    @staticmethod
    def _is_admin_dashboard(user) -> bool:
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or user.groups.filter(name="admin/gestor").exists():
            return True
        return user.username.lower() in {"lucas", "tabatha"}

    @staticmethod
    def _build_alertas_operacionais():
        from django.utils import timezone

        hoje = timezone.localdate()
        alertas: list[dict] = []

        descontos = (
            ItemVenda.objects.select_related("venda", "produto")
            .filter(venda__data_venda__gte=hoje - timedelta(days=15), preco_unitario__gt=0)
            .annotate(
                pct=ExpressionWrapper(
                    (F("desconto") * Value(100.0)) / F("preco_unitario"),
                    output_field=DecimalField(max_digits=10, decimal_places=2),
                )
            )
            .filter(pct__gt=10)
            .order_by("-venda__data_venda", "-id")[:20]
        )
        for row in descontos:
            alertas.append(
                {
                    "tipo": "DESCONTO > 10%",
                    "data": row.venda.data_venda,
                    "detalhe": (
                        f"Venda {row.venda.codigo_identificacao} | "
                        f"Produto {row.produto.nome} | "
                        f"Desconto {row.pct}%"
                    ),
                }
            )

        movimentos = (
            EstoqueMovimento.objects.select_related("produto")
            .filter(data_movimento__gte=hoje - timedelta(days=7))
            .filter(Q(tipo="AJUSTE", quantidade__gte=10) | Q(tipo="SAIDA", quantidade__gte=20))
            .order_by("-data_movimento", "-id")[:20]
        )
        for mov in movimentos:
            alertas.append(
                {
                    "tipo": "MOVIMENTO FORA DO PADRAO",
                    "data": mov.data_movimento,
                    "detalhe": f"{mov.tipo} | {mov.produto.nome} | Qtd {mov.quantidade}",
                }
            )

        saidas_ops = (
            SaidaOperacionalEstoque.objects.select_related("produto")
            .filter(data_saida__gte=hoje - timedelta(days=7))
            .filter(Q(tipo="AVARIA") | Q(quantidade__gte=5))
            .order_by("-data_saida", "-id")[:20]
        )
        for saida in saidas_ops:
            alertas.append(
                {
                    "tipo": "SAIDA OPERACIONAL",
                    "data": saida.data_saida,
                    "detalhe": (
                        f"{saida.get_tipo_display()} | {saida.get_unidade_display()} | "
                        f"{saida.produto.nome} | Qtd {saida.quantidade}"
                    ),
                }
            )

        alertas.sort(key=lambda x: x["data"], reverse=True)
        return alertas[:30]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        try:
            ctx["resultado_diario_dashboard"] = ResultadoDiarioService.payload_dashboard()
        except Exception:
            ctx["resultado_diario_dashboard"] = {
                "data_referencia": None,
                "linhas": [],
                "total_vendas_geral": 0,
                "total_saidas_geral": 0,
                "resultado_geral": 0,
            }
        if self._is_admin_dashboard(self.request.user):
            ctx["alertas_operacionais"] = self._build_alertas_operacionais()
        return ctx


class CustomLogoutView(LogoutView):
    """Custom logout view que aceita GET e POST"""
    http_method_names = ['get', 'post', 'head', 'options', 'trace']
    
    def get(self, request, *args, **kwargs):
        """Permite logout via GET também"""
        return super().post(request, *args, **kwargs)


class DocumentacaoView(LoginRequiredMixin, TemplateView):
    """View para servir a documentação do sistema"""
    template_name = "documentacao/indice.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Lista todos os arquivos .md na raiz do projeto
        base_path = Path(os.path.dirname(os.path.dirname(__file__)))
        doc_files = sorted([
            {
                'name': f.stem.replace('_', ' ').title(),
                'filename': f.name,
                'path': f.name,
            }
            for f in base_path.glob('*.md')
            if f.name not in ['manage.py']
        ])
        
        context['doc_files'] = doc_files
        return context
