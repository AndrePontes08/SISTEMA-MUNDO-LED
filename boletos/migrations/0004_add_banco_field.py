"""Add banco field to Boleto

Revision ID: 0004_add_banco_field
Revises: 0003_compra_comprovante_pagamento_and_more
Create Date: 2026-02-13 00:00
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("boletos", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="boleto",
            name="banco",
            field=models.CharField(choices=[('SICREDI', 'Sicredi'), ('BRASIL', 'Banco do Brasil'), ('OUTRO', 'Outro')], default='OUTRO', max_length=20, db_index=True),
        ),
    ]
