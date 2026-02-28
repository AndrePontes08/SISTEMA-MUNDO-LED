from __future__ import annotations

from decimal import Decimal
import re

from django import forms
from django.contrib.auth import get_user_model
from django.forms import inlineformset_factory
from django.utils import timezone

from boletos.models import Cliente
from core.services.formato_brl import payment_label
from vendas.models import ItemVenda, TipoPagamentoChoices, Venda


class VendaForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        if self.instance.pk is None:
            self.fields["data_venda"].initial = timezone.localdate()
        else:
            self.fields["data_venda"].initial = self.instance.data_venda
        self.fields["data_venda"].widget = forms.DateInput(
            format="%Y-%m-%d",
            attrs={"type": "date", "readonly": "readonly"},
        )
        self.fields["data_venda"].input_formats = ["%Y-%m-%d"]

        if self.user and self.user.is_authenticated:
            is_manager = self.user.is_superuser or self.user.groups.filter(name="admin/gestor").exists()
            if self.instance.pk is None:
                self.fields["vendedor"].initial = self.user
            if not is_manager:
                user_model = get_user_model()
                self.fields["vendedor"].queryset = user_model.objects.filter(pk=self.user.pk)
                self.fields["vendedor"].initial = self.user
                self.fields["vendedor"].disabled = True

        self.fields["tipo_pagamento"].choices = [
            (value, payment_label(value))
            for value, _label in self.fields["tipo_pagamento"].choices
        ]

    class Meta:
        model = Venda
        fields = [
            "tipo_documento",
            "cliente",
            "vendedor",
            "unidade_saida",
            "data_venda",
            "tipo_pagamento",
            "numero_parcelas",
            "intervalo_parcelas_dias",
            "primeiro_vencimento",
            "acrescimo",
            "observacoes",
        ]
        widgets = {
            "data_venda": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date", "readonly": "readonly"}),
            "primeiro_vencimento": forms.DateInput(attrs={"type": "date"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        cleaned = super().clean()
        cleaned["data_venda"] = self.instance.data_venda if self.instance.pk else timezone.localdate()
        tipo = cleaned.get("tipo_pagamento")
        parcelas = cleaned.get("numero_parcelas") or 1
        primeiro_vencimento = cleaned.get("primeiro_vencimento")
        pagamentos_tipos = [t for t in self.data.getlist("pagamentos_tipo") if t]
        possui_boleto = TipoPagamentoChoices.BOLETO in pagamentos_tipos or tipo == TipoPagamentoChoices.BOLETO

        if not possui_boleto:
            cleaned["numero_parcelas"] = 1
            cleaned["intervalo_parcelas_dias"] = 30
            cleaned["primeiro_vencimento"] = None
        if possui_boleto and parcelas < 2:
            raise forms.ValidationError("Para venda parcelada, informe ao menos 2 parcelas.")
        if possui_boleto and not primeiro_vencimento:
            raise forms.ValidationError("Informe o primeiro vencimento para vendas parceladas.")
        return cleaned


class ClienteRapidoForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = [
            "nome",
            "data_nascimento",
            "cpf_cnpj",
            "endereco",
            "telefone",
        ]
        widgets = {
            "data_nascimento": forms.DateInput(attrs={"type": "date"}),
            "endereco": forms.Textarea(attrs={"rows": 2}),
        }

    def clean_nome(self):
        nome = (self.cleaned_data.get("nome") or "").strip()
        if not nome:
            raise forms.ValidationError("Informe o nome do cliente.")
        return nome

    def clean_cpf_cnpj(self):
        raw = (self.cleaned_data.get("cpf_cnpj") or "").strip()
        digits = re.sub(r"\D", "", raw)
        if len(digits) not in (11, 14):
            raise forms.ValidationError("Informe um CPF (11 dígitos) ou CNPJ (14 dígitos).")
        if Cliente.objects.filter(cpf_cnpj=digits).exists():
            raise forms.ValidationError("Já existe cliente cadastrado com este CPF/CNPJ.")
        return digits


class ItemVendaForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["quantidade"].widget.attrs.setdefault("step", "1")
        self.fields["quantidade"].widget.attrs.setdefault("min", "1")
        self.fields["preco_unitario"].label = "Valor unitário"
        self.fields["preco_unitario"].widget.attrs.setdefault("step", "0.01")
        self.fields["preco_unitario"].widget.attrs.setdefault("min", "0")
        self.fields["desconto"].label = "Desconto (%)"
        self.fields["desconto"].help_text = "Informe percentual de desconto do item."
        self.fields["desconto"].widget.attrs.setdefault("step", "0.01")
        self.fields["desconto"].widget.attrs.setdefault("min", "0")
        self.fields["desconto"].widget.attrs.setdefault("max", "100")

        instance = getattr(self, "instance", None)
        if instance and instance.pk:
            preco = instance.preco_unitario or Decimal("0.00")
            qtd = instance.quantidade or Decimal("0.000")
            bruto = preco * qtd
            if bruto > 0 and (instance.desconto or Decimal("0.00")) > 0:
                percentual = ((instance.desconto / bruto) * Decimal("100.00")).quantize(Decimal("0.01"))
                self.initial["desconto"] = percentual
            else:
                self.initial["desconto"] = Decimal("0.00")

    def clean_quantidade(self):
        quantidade = self.cleaned_data.get("quantidade")
        if quantidade is None:
            return quantidade
        if quantidade <= 0:
            raise forms.ValidationError("Quantidade deve ser maior que zero.")
        if quantidade != quantidade.to_integral_value():
            raise forms.ValidationError("Quantidade deve ser um número inteiro.")
        return quantidade.quantize(Decimal("1"))

    def clean_preco_unitario(self):
        preco = self.cleaned_data.get("preco_unitario")
        if preco is None:
            return preco
        if preco < 0:
            raise forms.ValidationError("Valor unitário não pode ser negativo.")
        return preco.quantize(Decimal("0.01"))

    def clean_desconto(self):
        percentual = self.cleaned_data.get("desconto") or Decimal("0.00")
        if percentual < 0:
            raise forms.ValidationError("Desconto deve ser maior ou igual a 0.")
        if percentual > Decimal("100.00"):
            raise forms.ValidationError("Desconto percentual nao pode ultrapassar 100%.")

        preco = self.cleaned_data.get("preco_unitario") or Decimal("0.00")
        quantidade = self.cleaned_data.get("quantidade") or Decimal("0.000")
        bruto = preco * quantidade
        if bruto <= 0:
            return Decimal("0.00")

        valor_desconto = (bruto * percentual / Decimal("100.00")).quantize(Decimal("0.01"))
        return valor_desconto

    class Meta:
        model = ItemVenda
        fields = ["produto", "quantidade", "preco_unitario", "desconto"]


ItemVendaFormSet = inlineformset_factory(
    Venda,
    ItemVenda,
    form=ItemVendaForm,
    extra=1,
    can_delete=True,
)


class CancelarVendaForm(forms.Form):
    motivo = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))


class FechamentoCaixaForm(forms.Form):
    data_referencia = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={"type": "date"}),
        initial=timezone.localdate,
    )
    observacoes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
