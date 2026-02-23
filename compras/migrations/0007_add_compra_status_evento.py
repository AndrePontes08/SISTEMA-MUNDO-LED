from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings

class Migration(migrations.Migration):

    initial = False

    dependencies = [
        ('compras', '0003_compra_comprovante_pagamento_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='compra',
            name='status',
            field=models.CharField(choices=[('SOLICITADA', 'Solicitada'), ('APROVADA', 'Aprovada'), ('COMPRADA', 'Comprada'), ('RECEBIDA', 'Recebida'), ('CANCELADA', 'Cancelada')], default='SOLICITADA', max_length=20, db_index=True),
        ),
        migrations.AddField(
            model_name='compra',
            name='aprovado_em',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='compra',
            name='aprovado_por',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='compras_aprovadas', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='compra',
            name='recebido_em',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='compra',
            name='recebido_por',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='compras_recebidas', to=settings.AUTH_USER_MODEL),
        ),
        migrations.CreateModel(
            name='CompraEvento',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo', models.CharField(choices=[('APROVACAO', 'Aprovação'), ('RECEBIMENTO', 'Recebimento'), ('CANCELAMENTO', 'Cancelamento'), ('OUTRO', 'Outro')], default='OUTRO', max_length=20, db_index=True)),
                ('detalhe', models.TextField(blank=True, default='')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('compra', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='eventos', to='compras.compra')),
                ('usuario', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-criado_em', '-id'],
            },
        ),
    ]
