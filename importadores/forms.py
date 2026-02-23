from __future__ import annotations

from django import forms

from estoque.models import UnidadeLoja


class CaixaPDFUploadForm(forms.Form):
    arquivo_pdf = forms.FileField(required=True, help_text="Envie o Relatorio Caixa Analitico em PDF.")
    data_referencia_override = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Opcional: preencha se o PDF nao trouxer data legivel.",
    )
    unidade_override = forms.ChoiceField(
        required=False,
        choices=[("", "Detectar do PDF")] + list(UnidadeLoja.choices),
        help_text="Use apenas se a unidade nao puder ser detectada automaticamente.",
    )

    def clean_arquivo_pdf(self):
        arquivo = self.cleaned_data["arquivo_pdf"]
        nome = (arquivo.name or "").lower()
        if not nome.endswith(".pdf"):
            raise forms.ValidationError("Envie um arquivo com extensao .pdf.")
        if arquivo.size > 15 * 1024 * 1024:
            raise forms.ValidationError("Arquivo PDF maior que 15 MB.")
        return arquivo
