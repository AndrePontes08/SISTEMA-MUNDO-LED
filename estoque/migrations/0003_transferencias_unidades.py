from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("estoque", "0002_add_custo_medio"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ProdutoEstoqueUnidade",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("unidade", models.CharField(choices=[("LOJA_1", "Loja 1"), ("LOJA_2", "Loja 2")], db_index=True, max_length=20)),
                ("saldo_atual", models.DecimalField(decimal_places=3, default=Decimal("0.000"), max_digits=14)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("produto", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="estoque_unidades", to="compras.produto")),
            ],
            options={
                "ordering": ["unidade", "produto__nome"],
            },
        ),
        migrations.CreateModel(
            name="TransferenciaEstoque",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("unidade_origem", models.CharField(choices=[("LOJA_1", "Loja 1"), ("LOJA_2", "Loja 2")], db_index=True, max_length=20)),
                ("unidade_destino", models.CharField(choices=[("LOJA_1", "Loja 1"), ("LOJA_2", "Loja 2")], db_index=True, max_length=20)),
                ("quantidade", models.DecimalField(decimal_places=3, max_digits=14, validators=[django.core.validators.MinValueValidator(Decimal("0.001"))])),
                ("data_transferencia", models.DateField(db_index=True)),
                ("observacao", models.CharField(blank=True, default="", max_length=255)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("produto", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="transferencias_estoque", to="compras.produto")),
                ("usuario", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-data_transferencia", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="produtoestoqueunidade",
            constraint=models.UniqueConstraint(fields=("produto", "unidade"), name="uniq_estoque_prod_unidade"),
        ),
        migrations.AddIndex(
            model_name="produtoestoqueunidade",
            index=models.Index(fields=["unidade", "produto"], name="idx_unid_prod"),
        ),
        migrations.AddIndex(
            model_name="transferenciaestoque",
            index=models.Index(fields=["data_transferencia"], name="idx_transf_data"),
        ),
        migrations.AddIndex(
            model_name="transferenciaestoque",
            index=models.Index(fields=["produto", "data_transferencia"], name="idx_transf_prod_data"),
        ),
    ]
