"""
Management command para importar dados do arquivo COMPRAS_PROCESSADO2.XLSX
Características:
- Normaliza nomes de fornecedores e produtos
- Valida dados antes de importar
- Trata erros de forma graceful
- Fornece relatório detalhado
"""
from __future__ import annotations

from decimal import Decimal
from datetime import datetime
import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from compras.models import Fornecedor, Produto, Compra, ItemCompra, CentroCustoChoices
from core.services.normalizacao import normalizar_nome


class Command(BaseCommand):
    help = "Importa dados do arquivo COMPRAS_PROCESSADO2.XLSX"

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            default='compras_processado2.xlsx',
            help='Caminho do arquivo XLSX (default: compras_processado2.xlsx)'
        )
        parser.add_argument(
            '--centro-custo',
            type=str,
            default='FM/ML',
            choices=[choice[0] for choice in CentroCustoChoices.choices],
            help='Centro de custo padrão para todas as compras'
        )
        parser.add_argument(
            '--skip-errors',
            action='store_true',
            help='Continua importação mesmo com erros em alguns registros'
        )

    def handle(self, *args, **options):
        file_path = options['file']
        centro_custo = options['centro_custo']
        skip_errors = options['skip_errors']

        self.stdout.write(self.style.SUCCESS(f"🚀 Iniciando importação de {file_path}..."))

        try:
            df = pd.read_excel(file_path)
        except FileNotFoundError:
            raise CommandError(f"❌ Arquivo não encontrado: {file_path}")
        except Exception as e:
            raise CommandError(f"❌ Erro ao ler arquivo: {e}")

        # Validação básica de colunas
        required_columns = {'descricao', 'quantidade', 'valor_unitario', 'valor_total', 'fornecedor', 'data'}
        missing = required_columns - set(df.columns)
        if missing:
            raise CommandError(f"❌ Colunas obrigatórias faltando: {missing}")

        # Renomear e limpar dados
        df.columns = df.columns.str.lower().str.strip()
        df = df.dropna(subset=['descricao', 'quantidade', 'valor_unitario', 'fornecedor', 'data'])

        self.stdout.write(f"📊 Total de registros: {len(df)}")

        # Inicializar contadores
        stats = {
            'fornecedores_criados': 0,
            'produtos_criados': 0,
            'compras_criadas': 0,
            'itens_criados': 0,
            'erros': 0,
            'avisos': 0,
        }

        try:
            with transaction.atomic():
                # Processar por grupos de fornecedor e data
                df['data'] = pd.to_datetime(df['data'], errors='coerce')
                grouped = df.groupby(['fornecedor', 'data'])

                for (fornecedor_nome, data_compra), grupo in grouped:
                    try:
                        # Criar/obter Fornecedor
                        fornecedor, created = self._get_or_create_fornecedor(fornecedor_nome)
                        if created:
                            stats['fornecedores_criados'] += 1

                        # Criar Compra
                        compra = Compra.objects.create(
                            fornecedor=fornecedor,
                            centro_custo=centro_custo,
                            data_compra=data_compra.date(),
                            observacoes="Importação inicial do sistema"
                        )
                        stats['compras_criadas'] += 1

                        valor_total_compra = Decimal('0')

                        # Processar itens do grupo
                        for idx, row in grupo.iterrows():
                            try:
                                produto, created = self._get_or_create_produto(row['descricao'])
                                if created:
                                    stats['produtos_criados'] += 1

                                # Validar e converter valores
                                try:
                                    quantidade = Decimal(str(row['quantidade']).strip())
                                    preco_unitario = Decimal(str(row['valor_unitario']).strip())
                                except (ValueError, TypeError) as e:
                                    self.stdout.write(
                                        self.style.WARNING(
                                            f"⚠️ Linha {idx}: Valor inválido - {e}"
                                        )
                                    )
                                    stats['avisos'] += 1
                                    continue

                                if quantidade <= 0 or preco_unitario < 0:
                                    self.stdout.write(
                                        self.style.WARNING(
                                            f"⚠️ Linha {idx}: Quantidade ou preço inválido"
                                        )
                                    )
                                    stats['avisos'] += 1
                                    continue

                                # Criar item de compra
                                ItemCompra.objects.create(
                                    compra=compra,
                                    produto=produto,
                                    quantidade=quantidade,
                                    preco_unitario=preco_unitario
                                )
                                stats['itens_criados'] += 1
                                valor_total_compra += (quantidade * preco_unitario)

                            except Exception as e:
                                if skip_errors:
                                    self.stdout.write(
                                        self.style.WARNING(f"⚠️ Erro na linha {idx}: {e}")
                                    )
                                    stats['avisos'] += 1
                                    continue
                                else:
                                    raise

                        # Atualizar valor total da compra
                        compra.valor_total = valor_total_compra
                        compra.save()

                    except Exception as e:
                        stats['erros'] += 1
                        if not skip_errors:
                            raise
                        self.stdout.write(
                            self.style.ERROR(f"❌ Erro ao processar grupo {fornecedor_nome}/{data_compra}: {e}")
                        )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Erro crítico: {e}"))
            if not skip_errors:
                raise CommandError(f"Importação abortada: {e}")

        # Exibir relatório
        self._exibir_relatorio(stats)

    def _get_or_create_fornecedor(self, nome: str) -> tuple[Fornecedor, bool]:
        """Obter ou criar fornecedor, normalizando o nome."""
        nome = (nome or "").strip()
        if not nome:
            raise ValueError("Nome do fornecedor vazio")

        nome_norm = normalizar_nome(nome)
        fornecedor, created = Fornecedor.objects.get_or_create(
            nome_normalizado=nome_norm,
            defaults={'nome': nome}
        )
        return fornecedor, created

    def _get_or_create_produto(self, descricao: str) -> tuple[Produto, bool]:
        """Obter ou criar produto, normalizando o nome."""
        descricao = (descricao or "").strip()
        if not descricao:
            raise ValueError("Descrição do produto vazia")

        nome_norm = normalizar_nome(descricao)
        produto, created = Produto.objects.get_or_create(
            nome_normalizado=nome_norm,
            defaults={'nome': descricao}
        )
        return produto, created

    def _exibir_relatorio(self, stats: dict):
        """Exibir relatório detalhado da importação."""
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("📋 RELATÓRIO DE IMPORTAÇÃO"))
        self.stdout.write("=" * 60)
        self.stdout.write(f"✅ Fornecedores criados: {stats['fornecedores_criados']}")
        self.stdout.write(f"✅ Produtos criados: {stats['produtos_criados']}")
        self.stdout.write(f"✅ Compras criadas: {stats['compras_criadas']}")
        self.stdout.write(f"✅ Itens criados: {stats['itens_criados']}")
        self.stdout.write(f"⚠️  Avisos: {stats['avisos']}")
        self.stdout.write(f"❌ Erros: {stats['erros']}")
        self.stdout.write("=" * 60)
        self.stdout.write(self.style.SUCCESS("✨ Importação concluída com sucesso!"))
