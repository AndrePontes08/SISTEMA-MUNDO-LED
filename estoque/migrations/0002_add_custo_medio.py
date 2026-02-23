from django.db import migrations, models
from decimal import Decimal

class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='produtoestoque',
            name='custo_medio',
            field=models.DecimalField(default=Decimal('0.0000'), max_digits=14, decimal_places=4),
        ),
    ]
