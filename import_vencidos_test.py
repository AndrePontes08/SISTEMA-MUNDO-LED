"""Script de teste para importar boletos vencidos a partir de CSV local.
Uso: python import_vencidos_test.py sample_vencidos.csv [--bank SICREDI|BRASIL|OUTRO]
"""
from __future__ import annotations

import sys
import csv
import io
import re
from decimal import Decimal, InvalidOperation
from datetime import datetime
import argparse

import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
import django
django.setup()

from boletos.models import Boleto, Cliente, StatusBoletoChoices


def normalize_key(k: str) -> str:
    return re.sub(r"[^a-z0-9]", "_", (k or "").strip().lower())


def get_cell(row, *candidates):
    for c in candidates:
        if c in row and row[c] is not None:
            return row[c].strip()
    norm_map = {normalize_key(k): (v or "") for k, v in row.items()}
    for c in candidates:
        key = normalize_key(c)
        if key in norm_map:
            return norm_map[key].strip()
    return ""


def parse_date(s: str):
    s = (s or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue
    return None


def parse_decimal(s: str):
    s = (s or "").strip()
    if not s:
        return None
    if s.count(',') and s.count('.')>1:
        s = s.replace('.', '')
    s = s.replace(',', '.')
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('csvfile')
    parser.add_argument('--bank', choices=['SICREDI','BRASIL','OUTRO'], default=None)
    args = parser.parse_args()

    path = args.csvfile
    text = None
    with open(path, 'rb') as f:
        data = f.read()
        try:
            text = data.decode('utf-8')
        except Exception:
            text = data.decode('latin-1')

    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=';,')
        delimiter = dialect.delimiter
    except Exception:
        delimiter = ';'

    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)

    encontrados = []
    nao_encontrados = []

    for row in reader:
        numero = get_cell(row, 'Nosso_Numero', 'NossoNumero', 'nosso_numero', 'numero_boleto', 'numero')
        cpf = get_cell(row, 'CPF_CNPJ', 'cpf_cnpj', 'cpf', 'cnpj')
        valor_raw = get_cell(row, 'Valor', 'valor')
        venc_raw = get_cell(row, 'Vencimento', 'vencimento')

        numero = (numero or '').strip()
        if not numero:
            continue
        valor = parse_decimal(valor_raw)
        venc = parse_date(venc_raw)

        boleto = None
        try:
            boleto = Boleto.objects.get(numero_boleto=numero)
        except Boleto.DoesNotExist:
            if cpf:
                cpf_norm = re.sub(r"\D", "", cpf)
                cliente = None
                for c in Cliente.objects.all():
                    if re.sub(r"\D", "", (c.cpf_cnpj or '')) == cpf_norm:
                        cliente = c
                        break
                if cliente and valor is not None and venc is not None:
                    qs = Boleto.objects.filter(cliente=cliente, valor=valor, data_vencimento=venc)
                    if qs.exists():
                        boleto = qs.first()

        if not boleto:
            # criar boleto provisório
            cliente = None
            if cpf:
                cpf_norm = re.sub(r"\D", "", cpf)
                for c in Cliente.objects.all():
                    if re.sub(r"\D", "", (c.cpf_cnpj or '')) == cpf_norm:
                        cliente = c
                        break
            if not cliente:
                cliente = Cliente.objects.create(nome=get_cell(row, 'Pagador','pagador','nome') or f'Cliente {numero}', cpf_cnpj=cpf or '')

            boleto = Boleto.objects.create(
                cliente=cliente,
                numero_boleto=numero,
                descricao=f"Importado - {get_cell(row,'Pagador','pagador','nome')}",
                valor=valor or Decimal('0.00'),
                data_vencimento=venc or datetime.now().date(),
                status=StatusBoletoChoices.VENCIDO,
                nosso_numero=numero,
                banco=args.bank or Boleto.BancoChoices.OUTRO,
                necessita_comprovante=True,
            )
            encontrados.append(boleto)
            continue

        if args.bank:
            boleto.banco = args.bank

        if boleto.status != StatusBoletoChoices.VENCIDO:
            boleto.status = StatusBoletoChoices.VENCIDO
        boleto.save()
        encontrados.append(boleto)

    print(f'Encontrados: {len(encontrados)}')
    print(f'Não encontrados: {len(nao_encontrados)}')
    if nao_encontrados:
        print('Exemplos não encontrados:', nao_encontrados[:10])


if __name__ == '__main__':
    main()
