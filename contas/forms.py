from __future__ import annotations

from django import forms
from .models import ContaAPagar


class ContaAPagarForm(forms.ModelForm):
    class Meta:
        model = ContaAPagar
        fields = [
            "vencimento",
            "descricao",
            "centro_custo",
            "categoria",
            "valor",
            "status",
            "pago_em",
            "exige_boleto",
            "exige_nota_fiscal",
            "exige_comprovante",
            "boleto",
            "nota_fiscal",
            "comprovante",
            "pedido",
            "observacoes",
        ]
        widgets = {
            "vencimento": forms.DateInput(attrs={"type": "date"}),
            "pago_em": forms.DateInput(attrs={"type": "date"}),
        }

    def clean(self):
        cleaned = super().clean()

        if cleaned.get("exige_comprovante") and not cleaned.get("comprovante"):
            self.add_error("comprovante", "Comprovante é obrigatório para esta conta.")

        if cleaned.get("exige_boleto") and not cleaned.get("boleto"):
            self.add_error("boleto", "Boleto é obrigatório para esta conta.")

        if cleaned.get("exige_nota_fiscal") and not cleaned.get("nota_fiscal"):
            self.add_error("nota_fiscal", "Nota fiscal é obrigatória para esta conta.")

        return cleaned


class ConfirmarPagamentoForm(forms.Form):
    comprovante = forms.FileField(required=False)


class ImportCSVForm(forms.Form):
    arquivo = forms.FileField(
        required=True,
        help_text="Arquivo CSV com colunas de contas a pagar.",
    )
    exige_comprovante_padrao = forms.BooleanField(
        required=False,
        initial=False,
        label="Exigir comprovante nos registros importados",
    )

    def clean_arquivo(self):
        arquivo = self.cleaned_data["arquivo"]
        nome = (arquivo.name or "").lower()
        if not nome.endswith(".csv"):
            raise forms.ValidationError("Envie um arquivo .csv.")
        return arquivo
