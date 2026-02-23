from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from financeiro.models import (
    ContaBancaria,
    ExtratoImportacao,
    Recebivel,
    StatusConciliacaoChoices,
    StatusImportacaoChoices,
    TipoMovimentoChoices,
    TransacaoBancaria,
)
from financeiro.services.conciliacao_service import ConciliacaoService
from financeiro.services.importacao_service import ImportacaoOFXService
from financeiro.services.ofx_parser_service import OFXParserService


class OFXParserServiceTest(TestCase):
    def test_parse_ofx_com_transacoes(self):
        sample = """
        OFXHEADER:100
        DATA:OFXSGML
        VERSION:102
        <OFX>
          <BANKMSGSRSV1>
            <STMTTRNRS>
              <STMTRS>
                <BANKACCTFROM>
                  <BANKID>001
                  <BRANCHID>1234
                  <ACCTID>999999
                  <ACCTTYPE>CHECKING
                </BANKACCTFROM>
                <BANKTRANLIST>
                  <DTSTART>20260101
                  <DTEND>20260131
                  <STMTTRN>
                    <TRNTYPE>CREDIT
                    <DTPOSTED>20260110
                    <TRNAMT>1500.00
                    <FITID>ABC123
                    <MEMO>Recebimento
                  </STMTTRN>
                </BANKTRANLIST>
              </STMTRS>
            </STMTTRNRS>
          </BANKMSGSRSV1>
        </OFX>
        """.encode("utf-8")

        parsed = OFXParserService.parse_bytes(sample)
        self.assertEqual(len(parsed["transactions"]), 1)
        self.assertEqual(parsed["transactions"][0]["fitid"], "ABC123")
        self.assertEqual(parsed["transactions"][0]["amount"], Decimal("1500.00"))


class ImportacaoOFXServiceTest(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="tester", password="123")
        self.conta = ContaBancaria.objects.create(
            nome="Conta BB",
            banco_codigo="001",
            banco_nome="Banco do Brasil",
            agencia="1234",
            conta_numero="999999",
            conta_digito="0",
        )
        self.ofx_bytes = """
        OFXHEADER:100
        DATA:OFXSGML
        VERSION:102
        <OFX>
          <BANKMSGSRSV1>
            <STMTTRNRS>
              <STMTRS>
                <BANKACCTFROM>
                  <BANKID>001
                  <BRANCHID>1234
                  <ACCTID>999999
                </BANKACCTFROM>
                <BANKTRANLIST>
                  <DTSTART>20260101
                  <DTEND>20260131
                  <STMTTRN>
                    <TRNTYPE>CREDIT
                    <DTPOSTED>20260110
                    <TRNAMT>100.00
                    <FITID>FIT-100
                    <MEMO>Credito teste
                  </STMTTRN>
                </BANKTRANLIST>
              </STMTRS>
            </STMTTRNRS>
          </BANKMSGSRSV1>
        </OFX>
        """.encode("utf-8")

    def test_importacao_idempotente(self):
        file1 = SimpleUploadedFile("extrato.ofx", self.ofx_bytes, content_type="application/octet-stream")
        imp1, _ = ImportacaoOFXService.criar_preview(file1, self.user, self.conta)
        result1 = ImportacaoOFXService.confirmar_importacao(imp1, self.conta, self.user)
        self.assertEqual(result1["novas"], 1)
        self.assertEqual(result1["duplicadas"], 0)

        file2 = SimpleUploadedFile("extrato.ofx", self.ofx_bytes, content_type="application/octet-stream")
        imp2, _ = ImportacaoOFXService.criar_preview(file2, self.user, self.conta)
        result2 = ImportacaoOFXService.confirmar_importacao(imp2, self.conta, self.user)
        self.assertEqual(result2["novas"], 0)
        self.assertEqual(result2["duplicadas"], 1)


class ConciliacaoServiceTest(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="conciliador", password="123")
        self.conta = ContaBancaria.objects.create(
            nome="Conta Sicredi",
            banco_codigo="748",
            banco_nome="Sicredi",
            agencia="0001",
            conta_numero="123456",
            conta_digito="7",
        )
        self.importacao = ExtratoImportacao.objects.create(
            conta=self.conta,
            banco_codigo="748",
            banco_nome="Sicredi",
            arquivo=SimpleUploadedFile("dummy.ofx", b"OFXHEADER:100", content_type="application/octet-stream"),
            arquivo_nome="dummy.ofx",
            arquivo_sha256="a" * 64,
            status=StatusImportacaoChoices.SUCESSO,
            transacoes_detectadas=0,
        )

    def test_conciliar_transacao_com_recebivel(self):
        recebivel = Recebivel.objects.create(
            descricao="Venda PDV 1001",
            data_prevista=timezone.localdate(),
            valor=Decimal("500.00"),
        )
        transacao = TransacaoBancaria.objects.create(
            conta=self.conta,
            importacao=self.importacao,
            data_lancamento=timezone.localdate(),
            valor=Decimal("500.00"),
            tipo_movimento=TipoMovimentoChoices.ENTRADA,
            descricao="Credito venda 1001",
            idempotency_key="k-500",
        )
        sugestoes = ConciliacaoService.gerar_sugestoes(transacao)
        self.assertTrue(len(sugestoes) >= 1)

        conciliacao = ConciliacaoService.conciliar(transacao, [recebivel], self.user, observacao="ok")
        transacao.refresh_from_db()
        recebivel.refresh_from_db()
        self.assertEqual(conciliacao.status_final, StatusConciliacaoChoices.CONCILIADA)
        self.assertEqual(transacao.status_conciliacao, StatusConciliacaoChoices.CONCILIADA)
        self.assertEqual(recebivel.status, "RECEBIDO")
