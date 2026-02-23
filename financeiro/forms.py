from __future__ import annotations

from django import forms

from financeiro.models import ContaBancaria, Recebivel, StatusImportacaoChoices


class OFXUploadForm(forms.Form):
    arquivo = forms.FileField(required=True, help_text="Envie um arquivo OFX.")
    conta_bancaria = forms.ModelChoiceField(
        queryset=ContaBancaria.objects.filter(ativa=True).order_by("nome"),
        required=False,
        help_text="Opcional: selecione se a conta nao for detectada automaticamente.",
    )

    def clean_arquivo(self):
        arquivo = self.cleaned_data["arquivo"]
        nome = (arquivo.name or "").lower()
        if not nome.endswith(".ofx"):
            raise forms.ValidationError("Envie um arquivo com extensao .ofx.")
        if arquivo.size > 8 * 1024 * 1024:
            raise forms.ValidationError("Arquivo maior que 8 MB.")
        return arquivo


class HistoricoImportacaoFiltroForm(forms.Form):
    conta = forms.ModelChoiceField(
        queryset=ContaBancaria.objects.order_by("nome"),
        required=False,
        empty_label="Todas as contas",
    )
    banco = forms.CharField(required=False)
    status = forms.ChoiceField(
        required=False,
        choices=[("", "Todos")] + list(StatusImportacaoChoices.choices),
    )
    data_inicio = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    data_fim = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))


class ConciliacaoActionForm(forms.Form):
    recebiveis = forms.ModelMultipleChoiceField(
        queryset=Recebivel.objects.filter(status="ABERTO").order_by("data_prevista"),
        required=False,
    )
    observacao = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))


class ContaBancariaForm(forms.ModelForm):
    class Meta:
        model = ContaBancaria
        fields = [
            "nome",
            "banco_codigo",
            "banco_nome",
            "agencia",
            "conta_numero",
            "conta_digito",
            "tipo_conta",
            "ativa",
        ]
