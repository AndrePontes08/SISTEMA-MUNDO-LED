#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
django.setup()

from boletos.models import Boleto, Cliente

print(f'Total de boletos: {Boleto.objects.count()}')
print(f'Total de clientes: {Cliente.objects.count()}')

# Listar alguns
if Boleto.objects.exists():
    print('\nPrimeiros boletos:')
    for boleto in Boleto.objects.all()[:3]:
        print(f'  - {boleto.numero_boleto}: {boleto.cliente.nome}')
