from __future__ import annotations

from django import forms
from django.forms import formset_factory

from compras.models import Produto
from estoque.models import ProdutoEstoque, TipoMovimento, TipoSaidaOperacional, UnidadeLoja


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
    quantidade = forms.DecimalField(min_value=1, decimal_places=0, max_digits=14)


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
    quantidade = forms.DecimalField(min_value=1, decimal_places=0, max_digits=14)


TransferenciaItemFormSet = formset_factory(
    TransferenciaItemForm,
    extra=1,
    can_delete=True,
)


class ContagemRapidaForm(forms.Form):
    unidade = forms.ChoiceField(choices=UnidadeLoja.choices)
    data_contagem = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    observacao = forms.CharField(required=False, max_length=255)


class ContagemRapidaItemForm(forms.Form):
    produto = forms.ModelChoiceField(
        queryset=Produto.objects.filter(ativo=True).order_by("nome"),
        empty_label="Selecione...",
    )
    quantidade_contada = forms.DecimalField(min_value=0, decimal_places=0, max_digits=14)


ContagemRapidaItemFormSet = formset_factory(
    ContagemRapidaItemForm,
    extra=5,
    can_delete=True,
)


class SaidaOperacionalForm(forms.Form):
    unidade = forms.ChoiceField(choices=UnidadeLoja.choices)
    tipo = forms.ChoiceField(choices=TipoSaidaOperacional.choices)
    data_saida = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    observacao = forms.CharField(required=False, max_length=255)


class SaidaOperacionalItemForm(forms.Form):
    produto = forms.ModelChoiceField(
        queryset=Produto.objects.filter(ativo=True).order_by("nome"),
        empty_label="Selecione...",
    )
    quantidade = forms.DecimalField(min_value=1, decimal_places=0, max_digits=14)


SaidaOperacionalItemFormSet = formset_factory(
    SaidaOperacionalItemForm,
    extra=3,
    can_delete=True,
)


class ImportCustoEstoqueForm(forms.Form):
    arquivo = forms.FileField(help_text="CSV com colunas SKU e CUSTO_MEDIO (ou PRECO).")
