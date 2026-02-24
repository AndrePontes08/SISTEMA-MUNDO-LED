from __future__ import annotations

from decimal import Decimal

from django import forms
from django.forms import inlineformset_factory

from compras.models import Compra, ItemCompra, Garantia, Fornecedor, Produto


class FornecedorForm(forms.ModelForm):
    class Meta:
        model = Fornecedor
        fields = ["nome", "cnpj", "telefone_contato", "representante_comercial", "contato_representante"]


class ProdutoForm(forms.ModelForm):
    class Meta:
        model = Produto
        fields = ["nome", "sku", "ativo"]


class CompraForm(forms.ModelForm):
    def clean(self):
        cleaned = super().clean()
        orc1 = cleaned.get("orcamento_1") or getattr(self.instance, "orcamento_1", None)
        orc2 = cleaned.get("orcamento_2") or getattr(self.instance, "orcamento_2", None)
        orc3 = cleaned.get("orcamento_3") or getattr(self.instance, "orcamento_3", None)
        escolhido = (cleaned.get("orcamento_escolhido") or "").strip()
        justificativa = (cleaned.get("justificativa_escolha") or "").strip()
        observacoes = (cleaned.get("observacoes") or "").strip()

        if not (orc1 and orc2 and orc3):
            raise forms.ValidationError("E obrigatorio anexar 3 orcamentos para o pedido de compra.")
        if escolhido not in {"ORC_1", "ORC_2", "ORC_3"}:
            raise forms.ValidationError("Selecione o orcamento escolhido para compra.")
        if not justificativa:
            raise forms.ValidationError("Preencha a justificativa da escolha do orcamento.")
        if not observacoes:
            raise forms.ValidationError("Preencha as observacoes da compra.")
        return cleaned

    class Meta:
        model = Compra
        fields = [
            "fornecedor",
            "centro_custo",
            "data_compra",
            "nota_fiscal",
            "boleto",
            "pedido",
            "orcamento_1",
            "orcamento_2",
            "orcamento_3",
            "orcamento_escolhido",
            "justificativa_escolha",
            "comprovante_pagamento",
            "observacoes",
        ]
        widgets = {
            "data_compra": forms.DateInput(attrs={"type": "date"}),
            "justificativa_escolha": forms.Textarea(attrs={"rows": 3}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }


class ItemCompraForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["quantidade"].widget.attrs.update({"step": "1", "min": "1"})
        self.fields["preco_unitario"].widget.attrs.update({"step": "0.01", "min": "0"})

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
            raise forms.ValidationError("Preço unitário não pode ser negativo.")
        return preco.quantize(Decimal("0.01"))

    class Meta:
        model = ItemCompra
        fields = ["produto", "quantidade", "preco_unitario"]


ItemCompraFormSet = inlineformset_factory(
    Compra,
    ItemCompra,
    form=ItemCompraForm,
    extra=1,
    can_delete=True,
)


class GarantiaForm(forms.ModelForm):
    class Meta:
        model = Garantia
        fields = ["item", "arquivo", "data_inicio", "data_fim", "observacao"]
        widgets = {
            "data_inicio": forms.DateInput(attrs={"type": "date"}),
            "data_fim": forms.DateInput(attrs={"type": "date"}),
        }
