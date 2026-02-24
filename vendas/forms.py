from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from django.forms import inlineformset_factory
from django.utils import timezone

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

        if tipo != TipoPagamentoChoices.PARCELADO_BOLETO:
            cleaned["numero_parcelas"] = 1
            cleaned["intervalo_parcelas_dias"] = 30
            cleaned["primeiro_vencimento"] = None
        if tipo == TipoPagamentoChoices.PARCELADO_BOLETO and parcelas < 2:
            raise forms.ValidationError("Para venda parcelada, informe ao menos 2 parcelas.")
        if tipo == TipoPagamentoChoices.PARCELADO_BOLETO and not primeiro_vencimento:
            raise forms.ValidationError("Informe o primeiro vencimento para vendas parceladas.")
        return cleaned


class ItemVendaForm(forms.ModelForm):
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
