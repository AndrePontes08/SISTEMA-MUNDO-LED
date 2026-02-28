from __future__ import annotations

from django import forms
from django.forms import inlineformset_factory

from boletos.models import (
    Boleto,
    Cliente,
    ClienteListaNegra,
    RamoAtuacao,
    ControleFiado,
    ParcelaBoleto,
)


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = [
            "nome",
            "data_nascimento",
            "cpf_cnpj",
            "email",
            "telefone",
            "endereco",
            "ramo_atuacao",
            "ativo",
        ]
        widgets = {
            "data_nascimento": forms.DateInput(attrs={"type": "date"}),
            "endereco": forms.Textarea(attrs={"rows": 3}),
        }


class BoletoForm(forms.ModelForm):
    class Meta:
        model = Boleto
        fields = [
            "cliente",
            "banco",
            "nosso_numero",
            "numero_boleto",
            "descricao",
            "valor",
            "data_vencimento",
            "vendedor",
            "status",
            "comprovante_pagamento",
            "observacoes",
        ]
        widgets = {
            "data_vencimento": forms.DateInput(attrs={"type": "date"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        cleaned = super().clean()
        cliente = cleaned.get("cliente")

        # Verifica se cliente está na lista negra
        if cliente and hasattr(cliente, "lista_negra") and cliente.lista_negra.ativo:
            raise forms.ValidationError(
                f"Cliente {cliente.nome} está na lista negra e não pode receber boletos."
            )

        return cleaned


class BoletoComPagamentoForm(forms.ModelForm):
    """Form para registrar pagamento de boleto"""

    class Meta:
        model = Boleto
        fields = ["status", "data_pagamento", "comprovante_pagamento"]
        widgets = {
            "data_pagamento": forms.DateInput(attrs={"type": "date"}),
        }

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get("status")
        comprovante = cleaned.get("comprovante_pagamento")

        if status == "PAGO" and not comprovante:
            raise forms.ValidationError("Comprovante é obrigatório para boletos pagos.")

        return cleaned


class ParcelaBoletoForm(forms.ModelForm):
    class Meta:
        model = ParcelaBoleto
        fields = ["numero_parcela", "valor", "data_vencimento", "status"]
        widgets = {
            "data_vencimento": forms.DateInput(attrs={"type": "date"}),
        }


ParcelaBoletoFormSet = inlineformset_factory(
    Boleto,
    ParcelaBoleto,
    form=ParcelaBoletoForm,
    extra=0,
    can_delete=True,
)


class ClienteListaNegraForm(forms.ModelForm):
    class Meta:
        model = ClienteListaNegra
        fields = ["motivo", "ativo"]
        widgets = {
            "motivo": forms.Textarea(attrs={"rows": 4}),
        }


class ControleFiadoForm(forms.ModelForm):
    class Meta:
        model = ControleFiado
        fields = ["limite_credito", "saldo_fiado", "status"]


class RamoAtuacaoForm(forms.ModelForm):
    class Meta:
        model = RamoAtuacao
        fields = ["nome", "descricao", "ativo"]
        widgets = {
            "descricao": forms.Textarea(attrs={"rows": 3}),
        }


class ImportVencidosForm(forms.Form):
    arquivo = forms.FileField(label="Arquivo CSV")
    # Opcionalmente o usuário pode informar o banco ao importar
    banco = forms.ChoiceField(
        choices=[("", "-- Todos --"), ("SICREDI", "Sicredi"), ("BRASIL", "Banco do Brasil")],
        required=False,
        label="Filtrar por banco (opcional)",
    )
