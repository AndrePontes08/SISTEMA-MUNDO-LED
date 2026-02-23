from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, Sum
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from boletos.forms import (
    BoletoForm,
    BoletoComPagamentoForm,
    ClienteForm,
    ClienteListaNegraForm,
    ControleFiadoForm,
    ParcelaBoletoFormSet,
)
from boletos.models import (
    Boleto,
    Cliente,
    ClienteListaNegra,
    ControleFiado,
    RamoAtuacao,
    StatusBoletoChoices,
)
from boletos.services.boletos_service import (
    BoletoService,
    ClienteService,
    ControleFiadoService,
)
from core.services.paginacao import get_pagination_params
from core.services.permissoes import GroupRequiredMixin
from boletos.forms import ImportVencidosForm
import csv
import io
import re
from decimal import Decimal, InvalidOperation
from datetime import datetime
from django.views.generic.edit import FormView
from django.db.models import Sum
from django.http import HttpResponse
from django.views import View
from django.template.loader import render_to_string


class BoletoAccessMixin(GroupRequiredMixin):
    """Controle de acesso para boletos"""

    required_groups = ("admin/gestor", "boletos/vendedor")


# ==================== BOLETOS ====================


class BoletoListView(BoletoAccessMixin, ListView):
    model = Boleto
    template_name = "boletos/boleto_list.html"
    context_object_name = "boletos"

    def get_paginate_by(self, queryset):
        return get_pagination_params(self.request).page_size

    def get_queryset(self):
        qs = Boleto.objects.select_related("cliente", "vendedor").order_by(
            "-data_vencimento", "-id"
        )

        # Filtros
        status = self.request.GET.get("status", "").strip()
        cliente_id = self.request.GET.get("cliente", "").strip()
        vendedor_id = self.request.GET.get("vendedor", "").strip()

        if status:
            qs = qs.filter(status=status)
        if cliente_id:
            qs = qs.filter(cliente_id=cliente_id)
        if vendedor_id:
            qs = qs.filter(vendedor_id=vendedor_id)

        # Filtrar apenas boletos marcados como necessitam de comprovante
        necessita = self.request.GET.get("necessita_comprovante", "").lower()
        if necessita in ("1", "true", "on"):
            qs = qs.filter(necessita_comprovante=True)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = StatusBoletoChoices.choices
        context["clientes"] = Cliente.objects.filter(ativo=True)
        context["stats"] = BoletoService.obter_estatisticas()
        # Totais por banco para boletos vencidos
        vencidos_qs = Boleto.objects.filter(status=StatusBoletoChoices.VENCIDO)
        totals = (
            vencidos_qs.values("banco")
            .annotate(total_valor=Sum("valor"))
            .order_by("banco")
        )
        # Convert to dict for template convenience
        context["vencidos_by_bank"] = {item["banco"]: item["total_valor"] for item in totals}
        context["import_form"] = ImportVencidosForm()
        context["filter_necessita_comprovante"] = self.request.GET.get("necessita_comprovante", "")
        return context


class BoletoExportComprovantesView(BoletoAccessMixin, View):
    """Exporta CSV com boletos que precisam de comprovante (filtro opcional por banco)."""

    def get(self, request, *args, **kwargs):
        qs = Boleto.objects.select_related("cliente").filter(necessita_comprovante=True)
        bank = request.GET.get("banco", "").strip()
        if bank:
            qs = qs.filter(banco=bank)

        # Build CSV
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = "attachment; filename=boletos_necessitam_comprovante.csv"
        writer = csv.writer(response)
        writer.writerow(["numero_boleto", "nosso_numero", "cliente", "cpf_cnpj", "valor", "data_vencimento", "banco", "status"])
        for b in qs.order_by("data_vencimento"):
            writer.writerow([
                b.numero_boleto,
                b.nosso_numero or "",
                b.cliente.nome if b.cliente else "",
                b.cliente.cpf_cnpj if b.cliente else "",
                f"{b.valor}",
                b.data_vencimento.isoformat() if b.data_vencimento else "",
                b.banco,
                b.status,
            ])

        return response


class BoletoExportPDFView(BoletoAccessMixin, View):
    """Exporta PDF com boletos que precisam de comprovante (filtro opcional por banco)."""

    def get(self, request, *args, **kwargs):
        qs = Boleto.objects.select_related("cliente").filter(necessita_comprovante=True)
        bank = request.GET.get("banco", "").strip()
        if bank:
            qs = qs.filter(banco=bank)

        boletos = qs.order_by("data_vencimento")

        html_string = render_to_string("boletos/boleto_export_pdf.html", {"boletos": boletos, "bank": bank})

   

        # Fallback: return rendered HTML with content-type text/html
        return HttpResponse(html_string)


class BoletoImportVencidosView(BoletoAccessMixin, FormView):
    template_name = "boletos/boleto_import.html"
    form_class = ImportVencidosForm
    success_url = reverse_lazy("boletos:boleto_list")

    def form_valid(self, form):
        arquivo = form.cleaned_data["arquivo"]
        banco_filter = form.cleaned_data.get("banco")

        # Read raw bytes and try to decode (latin-1 is permissive for Windows CSVs)
        data = arquivo.read()
        try:
            text = data.decode("utf-8")
        except Exception:
            text = data.decode("latin-1")

        # Detect delimiter (prefer ';' for bank exports)
        sample = text[:8192]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=';,')
            delimiter = dialect.delimiter
        except Exception:
            delimiter = ';'

        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)

        encontrados = []
        nao_encontrados = []

        def normalize_key(k: str) -> str:
            return re.sub(r"[^a-z0-9]", "_", (k or "").strip().lower())

        def get_cell(row, *candidates):
            for c in candidates:
                # try direct
                if c in row and row[c] is not None:
                    return row[c].strip()
            # try normalized keys
            norm_map = {normalize_key(k): v for k, v in row.items()}
            for c in candidates:
                key = normalize_key(c)
                if key in norm_map and norm_map[key] is not None:
                    return norm_map[key].strip()
            return ""

        def parse_date(s: str):
            s = (s or "").strip()
            for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
                try:
                    return datetime.strptime(s, fmt).date()
                except Exception:
                    continue
            return None

        def parse_decimal(s: str):
            s = (s or "").strip().replace('.', '').replace(',', '.') if s.count(',') > 0 and s.count('.')>1 else (s or '').replace(',', '.')
            try:
                return Decimal(s)
            except (InvalidOperation, ValueError):
                return None

        for row in reader:
            numero = get_cell(row, "Nosso_Numero", "NossoNumero", "Nosso-Numero", "nosso_numero", "numero_boleto", "numero")
            cpf = get_cell(row, "CPF_CNPJ", "cpf_cnpj", "cpf", "cnpj")
            pagador = get_cell(row, "Pagador", "pagador", "nome")
            valor_raw = get_cell(row, "Valor", "valor", "Valor(R$)")
            venc_raw = get_cell(row, "Vencimento", "vencimento", "data_vencimento")

            numero = (numero or "").strip()
            if not numero:
                # skip rows without identifier
                continue

            valor = parse_decimal(valor_raw)
            venc = parse_date(venc_raw)

            # Try direct lookup by numero_boleto, then nosso_numero, then fallback by cpf+valor+venc
            boleto = None
            try:
                boleto = Boleto.objects.get(numero_boleto=numero)
            except Boleto.DoesNotExist:
                try:
                    boleto = Boleto.objects.get(nosso_numero=numero)
                except Boleto.DoesNotExist:
                    # fallback: try find by cliente cpf + valor + vencimento
                    if cpf:
                        cpf_norm = re.sub(r"\D", "", cpf)
                        cliente = None
                        for c in Cliente.objects.all():
                            if re.sub(r"\D", "", (c.cpf_cnpj or "")) == cpf_norm:
                                cliente = c
                                break
                        if cliente and valor is not None and venc is not None:
                            qs = Boleto.objects.filter(cliente=cliente, valor=valor, data_vencimento=venc)
                            if qs.exists():
                                boleto = qs.first()

            if not boleto:
                # criar boleto provisório para rastrear necessidade de comprovante
                cliente = None
                if cpf:
                    cpf_norm = re.sub(r"\D", "", cpf)
                    for c in Cliente.objects.all():
                        if re.sub(r"\D", "", (c.cpf_cnpj or "")) == cpf_norm:
                            cliente = c
                            break
                if not cliente:
                    # criar cliente mínimo
                    cliente = Cliente.objects.create(nome=pagador or f"Cliente {numero}", cpf_cnpj=cpf or "", ativo=True)

                boleto = Boleto.objects.create(
                    cliente=cliente,
                    numero_boleto=numero,
                    descricao=f"Importado - {pagador or 'importado'}",
                    valor=valor or 0,
                    data_vencimento=venc or datetime.now().date(),
                    status=StatusBoletoChoices.VENCIDO,
                    nosso_numero=numero,
                    banco=banco_filter or Boleto.BancoChoices.OUTRO,
                    necessita_comprovante=True,
                )
                encontrados.append(boleto)

            if banco_filter:
                boleto.banco = banco_filter

            if boleto.status != StatusBoletoChoices.VENCIDO:
                boleto.status = StatusBoletoChoices.VENCIDO

            boleto.save()
            encontrados.append(boleto)

        messages.success(self.request, f"Importação processada: {len(encontrados)} encontrados, {len(nao_encontrados)} não encontrados.")
        self.request.session["import_encontrados"] = [b.pk for b in encontrados]
        self.request.session["import_nao_encontrados"] = nao_encontrados
        return super().form_valid(form)


class BoletoDetailView(BoletoAccessMixin, DetailView):
    model = Boleto
    template_name = "boletos/boleto_detail.html"
    context_object_name = "boleto"

    def get_queryset(self):
        return Boleto.objects.select_related("cliente", "vendedor")


class BoletoCreateView(BoletoAccessMixin, CreateView):
    model = Boleto
    form_class = BoletoForm
    template_name = "boletos/boleto_form.html"

    def get_success_url(self):
        return reverse("boletos:boleto_detail", kwargs={"pk": self.object.pk})

    def form_valid(self, form):
        messages.success(self.request, "Boleto criado com sucesso!")
        return super().form_valid(form)


class BoletoUpdateView(BoletoAccessMixin, UpdateView):
    model = Boleto
    form_class = BoletoForm
    template_name = "boletos/boleto_form.html"

    def get_success_url(self):
        return reverse("boletos:boleto_detail", kwargs={"pk": self.object.pk})

    def form_valid(self, form):
        messages.success(self.request, "Boleto atualizado com sucesso!")
        return super().form_valid(form)


class BoletoRegistrarPagamentoView(BoletoAccessMixin, UpdateView):
    model = Boleto
    form_class = BoletoComPagamentoForm
    template_name = "boletos/boleto_pagamento.html"

    def get_success_url(self):
        return reverse("boletos:boleto_detail", kwargs={"pk": self.object.pk})

    def form_valid(self, form):
        boleto = form.save(commit=False)
        BoletoService.registrar_pagamento(
            boleto,
            data_pagamento=form.cleaned_data.get("data_pagamento"),
            comprovante=form.cleaned_data.get("comprovante_pagamento"),
        )
        messages.success(self.request, "Pagamento registrado com sucesso!")
        return redirect(self.get_success_url())


# ==================== CLIENTES ====================


class ClienteListView(BoletoAccessMixin, ListView):
    model = Cliente
    template_name = "boletos/cliente_list.html"
    context_object_name = "clientes"

    def get_paginate_by(self, queryset):
        return get_pagination_params(self.request).page_size

    def get_queryset(self):
        qs = Cliente.objects.prefetch_related("boletos", "lista_negra").order_by(
            "nome"
        )

        search = self.request.GET.get("search", "").strip()
        ramo_id = self.request.GET.get("ramo", "").strip()
        em_lista_negra = self.request.GET.get("lista_negra", "").strip()

        if search:
            qs = qs.filter(
                Q(nome__icontains=search)
                | Q(nome_normalizado__icontains=search)
                | Q(cpf_cnpj__icontains=search)
            )
        if ramo_id:
            qs = qs.filter(ramo_atuacao_id=ramo_id)
        if em_lista_negra == "sim":
            qs = qs.filter(lista_negra__ativo=True)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["ramos"] = RamoAtuacao.objects.filter(ativo=True)
        return context


class ClienteDetailView(BoletoAccessMixin, DetailView):
    model = Cliente
    template_name = "boletos/cliente_detail.html"
    context_object_name = "cliente"

    def get_queryset(self):
        return Cliente.objects.prefetch_related("boletos", "controle_fiado")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cliente = self.object
        context["boletos"] = cliente.boletos.all().order_by("-data_vencimento")
        context["total_em_aberto"] = BoletoService.obter_total_em_aberto(cliente)
        context["em_lista_negra"] = hasattr(cliente, "lista_negra") and cliente.lista_negra.ativo
        
        if hasattr(cliente, "controle_fiado"):
            context["controle_fiado"] = cliente.controle_fiado
        
        return context


class ClienteCreateView(BoletoAccessMixin, CreateView):
    model = Cliente
    form_class = ClienteForm
    template_name = "boletos/cliente_form.html"

    def get_success_url(self):
        return reverse("boletos:cliente_detail", kwargs={"pk": self.object.pk})

    def form_valid(self, form):
        messages.success(self.request, "Cliente criado com sucesso!")
        return super().form_valid(form)


class ClienteUpdateView(BoletoAccessMixin, UpdateView):
    model = Cliente
    form_class = ClienteForm
    template_name = "boletos/cliente_form.html"

    def get_success_url(self):
        return reverse("boletos:cliente_detail", kwargs={"pk": self.object.pk})

    def form_valid(self, form):
        messages.success(self.request, "Cliente atualizado com sucesso!")
        return super().form_valid(form)


# ==================== LISTA NEGRA ====================


class ClienteAdicionarListaNegraMixin(BoletoAccessMixin, View):
    """Adiciona cliente à lista negra"""

    def post(self, request, pk):
        cliente = get_object_or_404(Cliente, pk=pk)
        motivo = request.POST.get("motivo", "")

        ClienteService.adicionar_lista_negra(cliente, motivo, request.user)
        messages.success(self.request, f"{cliente.nome} adicionado(a) à lista negra.")

        return redirect("boletos:cliente_detail", pk=cliente.pk)


class ClienteRemoverListaNegraView(BoletoAccessMixin, View):
    """Remove cliente da lista negra"""

    def post(self, request, pk):
        cliente = get_object_or_404(Cliente, pk=pk)
        ClienteService.remover_lista_negra(cliente)
        messages.success(self.request, f"{cliente.nome} removido(a) da lista negra.")

        return redirect("boletos:cliente_detail", pk=cliente.pk)


class ListaNegraBoletoListView(BoletoAccessMixin, ListView):
    model = ClienteListaNegra
    template_name = "boletos/lista_negra.html"
    context_object_name = "clientes_bloqueados"

    def get_queryset(self):
        return ClienteListaNegra.objects.filter(ativo=True).select_related("cliente")


# ==================== CONTROLE DE FIADO ====================


class ControleFiadoDetailView(BoletoAccessMixin, DetailView):
    model = ControleFiado
    template_name = "boletos/controle_fiado_detail.html"
    context_object_name = "controle"

    def get_queryset(self):
        return ControleFiado.objects.select_related("cliente")


class ControleFiadoUpdateView(BoletoAccessMixin, UpdateView):
    model = ControleFiado
    form_class = ControleFiadoForm
    template_name = "boletos/controle_fiado_form.html"

    def get_success_url(self):
        return reverse("boletos:controle_fiado_detail", kwargs={"pk": self.object.pk})

    def form_valid(self, form):
        messages.success(self.request, "Controle de fiado atualizado com sucesso!")
        return super().form_valid(form)


class ControleFiadoListView(BoletoAccessMixin, ListView):
    model = ControleFiado
    template_name = "boletos/controle_fiado_list.html"
    context_object_name = "controles"

    def get_paginate_by(self, queryset):
        return get_pagination_params(self.request).page_size

    def get_queryset(self):
        return ControleFiado.objects.select_related("cliente").order_by(
            "-saldo_fiado"
        )
