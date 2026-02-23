from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("estoque", "0003_transferencias_unidades"),
    ]

    operations = [
        migrations.AddField(
            model_name="transferenciaestoque",
            name="lote_referencia",
            field=models.CharField(blank=True, db_index=True, default="", max_length=40),
        ),
        migrations.AddIndex(
            model_name="transferenciaestoque",
            index=models.Index(fields=["lote_referencia", "data_transferencia"], name="idx_transf_lote_data"),
        ),
    ]
