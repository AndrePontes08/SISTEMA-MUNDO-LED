"""Add nosso_numero to Boleto

Revision ID: 0005_add_nosso_numero
Revises: 0004_add_banco_field
Create Date: 2026-02-13 01:10
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("boletos", "0004_add_banco_field"),
    ]

    operations = [
        migrations.AddField(
            model_name="boleto",
            name="nosso_numero",
            field=models.CharField(help_text='Identificador do banco (Nosso Número)', max_length=64, null=True, db_index=True, blank=True),
        ),
    ]
