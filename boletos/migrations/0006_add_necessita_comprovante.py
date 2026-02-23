"""Add necessita_comprovante to Boleto

Revision ID: 0006_add_necessita_comprovante
Revises: 0005_add_nosso_numero
Create Date: 2026-02-13 01:30
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("boletos", "0005_add_nosso_numero"),
    ]

    operations = [
        migrations.AddField(
            model_name="boleto",
            name="necessita_comprovante",
            field=models.BooleanField(default=False, db_index=True, help_text='Indica que o boleto foi importado como vencido e precisa de comprovante'),
        ),
    ]
