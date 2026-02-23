#!/usr/bin/env python
import os
import django
from decimal import Decimal
from datetime import date, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
django.setup()

from boletos.models import Cliente, RamoAtuacao, Boleto
from django.contrib.auth.models import User

# Criar ramo
ramo = RamoAtuacao.objects.create(nome="Indústria", descricao="Empresas Industriais")
print(f"✅ Ramo criado: {ramo.nome}")

# Criar cliente
cliente = Cliente.objects.create(
    nome="Empresa XYZ LTDA",
    cpf_cnpj="12.345.678/0001-90",
    email="contato@empresa.com",
    telefone="(81) 99999-9999",
    endereco="Rua ABC, 123, Recife, PE",
    ramo_atuacao=ramo,
    ativo=True
)
print(f"✅ Cliente criado: {cliente.nome}")

# Pegar o admin user
admin_user = User.objects.filter(is_superuser=True).first()

# Criar boletos de teste
boletos_data = [
    ("001/2026", "Serviço Profissional", Decimal("1500.00"), date.today()),
    ("002/2026", "Consultoria", Decimal("2500.00"), date.today() + timedelta(days=5)),
    ("003/2026", "Desenvolvimento", Decimal("3200.00"), date.today() + timedelta(days=15)),
    ("004/2026", "Suporte", Decimal("800.00"), date.today() - timedelta(days=3)),  # Vencido
]

for numero, descricao, valor, vencimento in boletos_data:
    boleto = Boleto.objects.create(
        numero_boleto=numero,
        cliente=cliente,
        descricao=descricao,
        valor=valor,
        data_vencimento=vencimento,
        vendedor=admin_user,
        status="ABERTO",
        observacoes="Boleto de teste"
    )
    print(f"✅ Boleto criado: {boleto.numero_boleto} - R$ {valor}")

print(f"\n🎉 Dados de teste criados com sucesso!")
print(f"   Total: {Boleto.objects.count()} boletos, {Cliente.objects.count()} clientes")
