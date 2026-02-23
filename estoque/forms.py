from __future__ import annotations

from django import forms
from django.forms import formset_factory

from compras.models import Produto
from estoque.models import ProdutoEstoque, TipoMovimento, UnidadeLoja


class ProdutoEstoqueForm(forms.ModelForm):
    class Meta:
        model = ProdutoEstoque
        fields = ["estoque_minimo", "estoque_ideal", "estoque_maximo"]


class MovimentoForm(forms.Form):
    tipo = forms.ChoiceField(choices=TipoMovimento.choices)
    data_movimento = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    observacao = forms.CharField(required=False, max_length=255)


class MovimentoItemForm(forms.Form):
    produto = forms.ModelChoiceField(
        queryset=Produto.objects.filter(ativo=True).order_by("nome"),
        empty_label="Selecione...",
    )
    quantidade = forms.DecimalField(min_value=0.001, decimal_places=3, max_digits=14)


MovimentoItemFormSet = formset_factory(
    MovimentoItemForm,
    extra=1,
    can_delete=True,
)


class TransferenciaForm(forms.Form):
    unidade_origem = forms.ChoiceField(choices=UnidadeLoja.choices)
    unidade_destino = forms.ChoiceField(choices=UnidadeLoja.choices)
    data_transferencia = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    observacao = forms.CharField(required=False, max_length=255)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("unidade_origem") == cleaned.get("unidade_destino"):
            raise forms.ValidationError("Origem e destino devem ser diferentes.")
        return cleaned


class TransferenciaItemForm(forms.Form):
    produto = forms.ModelChoiceField(
        queryset=Produto.objects.filter(ativo=True).order_by("nome"),
        empty_label="Selecione...",
    )
    quantidade = forms.DecimalField(min_value=0.001, decimal_places=3, max_digits=14)


TransferenciaItemFormSet = formset_factory(
    TransferenciaItemForm,
    extra=1,
    can_delete=True,
)
