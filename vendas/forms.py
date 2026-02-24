from __future__ import annotations

from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.forms import inlineformset_factory
from django.utils import timezone

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

        if tipo != TipoPagamentoChoices.BOLETO:
            cleaned["numero_parcelas"] = 1
            cleaned["intervalo_parcelas_dias"] = 30
            cleaned["primeiro_vencimento"] = None
        if tipo == TipoPagamentoChoices.BOLETO and parcelas < 2:
            raise forms.ValidationError("Para venda parcelada, informe ao menos 2 parcelas.")
        if tipo == TipoPagamentoChoices.BOLETO and not primeiro_vencimento:
            raise forms.ValidationError("Informe o primeiro vencimento para vendas parceladas.")
        return cleaned


class ItemVendaForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
