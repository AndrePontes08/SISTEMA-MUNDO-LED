from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("boletos", "0006_add_necessita_comprovante"),
    ]

    operations = [
        migrations.AddField(
            model_name="cliente",
            name="data_nascimento",
            field=models.DateField(blank=True, null=True),
        ),
    ]
