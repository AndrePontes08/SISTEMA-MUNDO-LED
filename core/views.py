from __future__ import annotations

import os
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LogoutView
from django.views.generic import TemplateView, ListView
from django.http import HttpResponse
from pathlib import Path

from importadores.services.resultado_diario_service import ResultadoDiarioService


def healthz(request):
    return HttpResponse("ok", content_type="text/plain")


class HomeView(LoginRequiredMixin, TemplateView):
    template_name = "base.html"

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
