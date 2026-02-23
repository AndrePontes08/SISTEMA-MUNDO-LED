from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from financeiro.models import (
    ContaBancaria,
    ExtratoImportacao,
    StatusConciliacaoChoices,
    StatusImportacaoChoices,
    TipoMovimentoChoices,
    TransacaoBancaria,
)
from importadores.models import CaixaRelatorioImportacao, UnidadeContaFinanceiraConfig
from importadores.services.importacao_caixa_service import ImportacaoCaixaService
from importadores.services.pdf_caixa_service import PDFCaixaService
from importadores.services.resultado_diario_service import ResultadoDiarioService
from estoque.models import UnidadeLoja


class PDFCaixaServiceTest(TestCase):
    def test_parse_text_encontra_total_data_unidade(self):
        text = """
        Empresa: MATRIZ
        Data: 17/02/2026
        Totalizacao do Caixa
        Vendas
        Especie: 269,00
        Duplicata: 0,00
        Boleto: 0,00
        Cartao de Credito: 1.387,20
        Cartao de Debito: 1.150,20
        Pix: 0,00
        Pix Off: 5.139,00
        Total: 7.945,40
        Total Trocas: 0,00
        """
        parsed = PDFCaixaService.parse_caixa_text(text)
        self.assertEqual(parsed["unidade"], UnidadeLoja.LOJA_1)
        self.assertEqual(parsed["total_vendas"], Decimal("7945.40"))
        self.assertEqual(parsed["total_trocas"], Decimal("0.00"))
        self.assertEqual(parsed["vendas_detalhadas"]["ESPECIE"], Decimal("269.00"))
        self.assertEqual(parsed["vendas_detalhadas"]["CARTAO_CREDITO"], Decimal("1387.20"))
        self.assertEqual(parsed["vendas_detalhadas"]["PIX_OFF"], Decimal("5139.00"))
        self.assertEqual(parsed["data_referencia"].strftime("%d/%m/%Y"), "17/02/2026")


class ImportacaoCaixaIdempotenciaTest(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user("tester", password="123")

    @patch("importadores.services.pdf_caixa_service.PDFCaixaService.extract_text_from_pdf_bytes")
    def test_mesmo_pdf_mesma_data_unidade_nao_importa_duas_vezes(self, mock_extract):
        mock_extract.return_value = """
        Empresa: MATRIZ
        Data: 17/02/2026
        Totalizacao do Caixa
        Vendas
        TOTAL: 100,00
        """
        f1 = SimpleUploadedFile("caixa.pdf", b"%PDF-1.4 sample", content_type="application/pdf")
        ImportacaoCaixaService.importar_pdf(uploaded_file=f1, usuario=self.user)
        self.assertEqual(CaixaRelatorioImportacao.objects.count(), 1)

        f2 = SimpleUploadedFile("caixa.pdf", b"%PDF-1.4 sample", content_type="application/pdf")
        with self.assertRaises(Exception):
            ImportacaoCaixaService.importar_pdf(uploaded_file=f2, usuario=self.user)
        self.assertEqual(CaixaRelatorioImportacao.objects.count(), 1)


class ResultadoDiarioServiceTest(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user("finance", password="123")
        self.conta = ContaBancaria.objects.create(
            nome="Conta Loja 1",
            banco_codigo="001",
            banco_nome="BB",
            agencia="1234",
            conta_numero="99999",
        )
        UnidadeContaFinanceiraConfig.objects.create(unidade=UnidadeLoja.LOJA_1, conta_bancaria=self.conta)

        self.importacao_fin = ExtratoImportacao.objects.create(
            conta=self.conta,
            banco_codigo="001",
            banco_nome="BB",
            arquivo=SimpleUploadedFile("dummy.ofx", b"OFXHEADER:100", content_type="application/octet-stream"),
            arquivo_nome="dummy.ofx",
            arquivo_sha256="b" * 64,
            status=StatusImportacaoChoices.SUCESSO,
            transacoes_detectadas=1,
        )

        self.data_ref = timezone.localdate() - timedelta(days=1)
        CaixaRelatorioImportacao.objects.create(
            data_referencia=self.data_ref,
            unidade=UnidadeLoja.LOJA_1,
            empresa_nome="MATRIZ",
            arquivo_pdf=SimpleUploadedFile("caixa2.pdf", b"%PDF-1.4 x", content_type="application/pdf"),
            arquivo_nome="caixa2.pdf",
            arquivo_hash="c" * 64,
            total_vendas=Decimal("1000.00"),
            status="SUCESSO",
            criado_por=self.user,
        )
        TransacaoBancaria.objects.create(
            conta=self.conta,
            importacao=self.importacao_fin,
            data_lancamento=self.data_ref,
            valor=Decimal("250.00"),
            tipo_movimento=TipoMovimentoChoices.SAIDA,
            descricao="Pagamento teste",
            idempotency_key="saida-250",
            status_conciliacao=StatusConciliacaoChoices.CONCILIADA,
        )

    def test_resultado_dia(self):
        payload = ResultadoDiarioService.payload_dashboard()
        self.assertEqual(payload["data_referencia"], self.data_ref)
        self.assertEqual(payload["total_vendas_geral"], Decimal("1000.00"))
        self.assertEqual(payload["total_saidas_geral"], Decimal("250.00"))
        self.assertEqual(payload["resultado_geral"], Decimal("750.00"))
