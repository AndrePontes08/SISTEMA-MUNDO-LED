from __future__ import annotations

from io import StringIO
from unittest.mock import patch
from decimal import Decimal
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.urls import reverse
from django.test import override_settings
from django.test import TestCase
from django.utils import timezone

from compras.models import Compra, Fornecedor, ItemCompra, Produto
from estoque.models import (
    ProdutoEstoque,
    AlertaEstoque,
    StatusAlerta,
    Lote,
    EstoqueMovimento,
    ProdutoEstoqueUnidade,
    UnidadeLoja,
    TransferenciaEstoque,
)
from estoque.services.statistics_service import EstoqueStatisticsService
from estoque.services.estoque_service import registrar_entrada, registrar_saida
from estoque.services.contagem_service import aplicar_contagem_rapida
from estoque.services.transferencias_service import transferir_entre_unidades, transferir_lote_entre_unidades
from estoque.services.saida_operacional_service import registrar_saida_operacional_lote


class EstoqueRegrasTest(TestCase):
    def test_saida_abaixo_minimo_cria_alerta(self):
        produto = Produto.objects.create(nome="Produto X", sku="PX-1", ativo=True)
        cfg = ProdutoEstoque.objects.create(produto=produto, estoque_minimo=Decimal("5.000"), estoque_ideal=Decimal("10.000"))

        registrar_entrada(produto=produto, quantidade=Decimal("10.000"))
        cfg.refresh_from_db()
        self.assertEqual(cfg.saldo_atual, Decimal("10.000"))

        registrar_saida(produto=produto, quantidade=Decimal("6.000"))
        cfg.refresh_from_db()
        self.assertEqual(cfg.saldo_atual, Decimal("4.000"))

        alerta = AlertaEstoque.objects.filter(produto=produto, status=StatusAlerta.ABERTO).first()
        self.assertIsNotNone(alerta)
        self.assertEqual(alerta.saldo_no_momento, Decimal("4.000"))
        self.assertEqual(alerta.minimo_configurado, Decimal("5.000"))


class EstoqueStatisticsServiceTest(TestCase):
    def setUp(self):
        self.produto = Produto.objects.create(nome="Produto Estatistica", sku="EST-1", ativo=True)

    def test_tempo_medio_estoque_ponderado_por_lotes(self):
        hoje = timezone.localdate()
        Lote.objects.create(
            produto=self.produto,
            data_entrada=hoje - timedelta(days=10),
            quantidade_inicial=Decimal("10.000"),
            quantidade_restante=Decimal("10.000"),
        )
        Lote.objects.create(
            produto=self.produto,
            data_entrada=hoje - timedelta(days=40),
            quantidade_inicial=Decimal("20.000"),
            quantidade_restante=Decimal("20.000"),
        )

        tempo = EstoqueStatisticsService.tempo_medio_estoque(self.produto, dias=365)

        self.assertEqual(tempo, Decimal("30.00"))

    def test_giro_estoque_considera_saidas_no_periodo(self):
        hoje = timezone.localdate()
        ProdutoEstoque.objects.create(produto=self.produto, saldo_atual=Decimal("20.000"))
        EstoqueMovimento.objects.create(
            produto=self.produto,
            tipo="SAIDA",
            quantidade=Decimal("4.000"),
            data_movimento=hoje - timedelta(days=30),
        )
        EstoqueMovimento.objects.create(
            produto=self.produto,
            tipo="SAIDA",
            quantidade=Decimal("6.000"),
            data_movimento=hoje - timedelta(days=200),
        )
        EstoqueMovimento.objects.create(
            produto=self.produto,
            tipo="SAIDA",
            quantidade=Decimal("100.000"),
            data_movimento=hoje - timedelta(days=500),
        )

        giro = EstoqueStatisticsService.giro_estoque(self.produto, meses=12)

        self.assertEqual(giro, Decimal("0.50"))

    def test_relatorio_geral_traz_apenas_produtos_ativos(self):
        inativo = Produto.objects.create(nome="Produto Inativo", sku="EST-2", ativo=False)
        ProdutoEstoque.objects.create(produto=self.produto, saldo_atual=Decimal("7.000"))
        ProdutoEstoque.objects.create(produto=inativo, saldo_atual=Decimal("3.000"))

        relatorio = EstoqueStatisticsService.relatorio_geral()
        ids = {item["produto_id"] for item in relatorio}

        self.assertIn(self.produto.id, ids)
        self.assertNotIn(inativo.id, ids)


class NotifyLowStockCommandTest(TestCase):
    def test_comando_cria_alerta_e_emite_resumo(self):
        produto = Produto.objects.create(nome="Produto Comando", sku="CMD-1", ativo=True)
        ProdutoEstoque.objects.create(
            produto=produto,
            saldo_atual=Decimal("1.000"),
            estoque_minimo=Decimal("5.000"),
        )
        out = StringIO()

        call_command("notify_low_stock", stdout=out)

        self.assertTrue(AlertaEstoque.objects.filter(produto=produto, status=StatusAlerta.ABERTO).exists())
        self.assertIn("1 alerta(s) abertos.", out.getvalue())

    @override_settings(LOW_STOCK_EMAILS=["ops@example.com"], DEFAULT_FROM_EMAIL="erp@example.com")
    def test_comando_envia_email_quando_notificacao_ativa(self):
        produto = Produto.objects.create(nome="Produto Email", sku="CMD-2", ativo=True)
        ProdutoEstoque.objects.create(
            produto=produto,
            saldo_atual=Decimal("0.500"),
            estoque_minimo=Decimal("1.000"),
        )
        out = StringIO()

        with patch("estoque.management.commands.notify_low_stock.send_mail") as send_mail_mock:
            call_command("notify_low_stock", "--notify-email", stdout=out)

        send_mail_mock.assert_called_once()
        self.assertIn("E-mail enviado", out.getvalue())


class MovimentoCreateViewTest(TestCase):
    def test_registra_entrada_para_multiplos_produtos(self):
        user_model = get_user_model()
        admin = user_model.objects.create_superuser("admin", "admin@example.com", "pass")
        produto_1 = Produto.objects.create(nome="Produto Lote 1", sku="ML-1", ativo=True)
        produto_2 = Produto.objects.create(nome="Produto Lote 2", sku="ML-2", ativo=True)
        self.client.force_login(admin)

        response = self.client.post(
            reverse("estoque:movimento_create"),
            data={
                "tipo": "ENTRADA",
                "data_movimento": timezone.localdate().isoformat(),
                "observacao": "Entrada em lote",
                "itens-TOTAL_FORMS": "2",
                "itens-INITIAL_FORMS": "0",
                "itens-MIN_NUM_FORMS": "0",
                "itens-MAX_NUM_FORMS": "1000",
                "itens-0-produto": str(produto_1.id),
                "itens-0-quantidade": "3.000",
                "itens-1-produto": str(produto_2.id),
                "itens-1-quantidade": "2.500",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(EstoqueMovimento.objects.filter(tipo="ENTRADA").count(), 2)
        self.assertEqual(ProdutoEstoque.objects.get(produto=produto_1).saldo_atual, Decimal("3.000"))
        self.assertEqual(ProdutoEstoque.objects.get(produto=produto_2).saldo_atual, Decimal("2.500"))


class TransferenciaEntreUnidadesTest(TestCase):
    def test_transferencia_movimenta_saldos_entre_lojas(self):
        produto = Produto.objects.create(nome="Produto Transferencia", sku="TR-1", ativo=True)
        ProdutoEstoqueUnidade.objects.create(produto=produto, unidade=UnidadeLoja.LOJA_1, saldo_atual=Decimal("10.000"))
        ProdutoEstoqueUnidade.objects.create(produto=produto, unidade=UnidadeLoja.LOJA_2, saldo_atual=Decimal("2.000"))

        result = transferir_entre_unidades(
            produto=produto,
            unidade_origem=UnidadeLoja.LOJA_1,
            unidade_destino=UnidadeLoja.LOJA_2,
            quantidade=Decimal("3.500"),
            observacao="Reposicao",
        )

        origem = ProdutoEstoqueUnidade.objects.get(produto=produto, unidade=UnidadeLoja.LOJA_1)
        destino = ProdutoEstoqueUnidade.objects.get(produto=produto, unidade=UnidadeLoja.LOJA_2)
        self.assertEqual(origem.saldo_atual, Decimal("6.500"))
        self.assertEqual(destino.saldo_atual, Decimal("5.500"))
        self.assertEqual(result.saldo_origem, Decimal("6.500"))
        self.assertEqual(result.saldo_destino, Decimal("5.500"))
        self.assertEqual(TransferenciaEstoque.objects.count(), 1)

    def test_transferencia_bloqueia_saldo_insuficiente(self):
        produto = Produto.objects.create(nome="Produto Sem Saldo", sku="TR-2", ativo=True)
        ProdutoEstoqueUnidade.objects.create(produto=produto, unidade=UnidadeLoja.LOJA_1, saldo_atual=Decimal("1.000"))
        ProdutoEstoqueUnidade.objects.create(produto=produto, unidade=UnidadeLoja.LOJA_2, saldo_atual=Decimal("0.000"))

        with self.assertRaises(ValueError):
            transferir_entre_unidades(
                produto=produto,
                unidade_origem=UnidadeLoja.LOJA_1,
                unidade_destino=UnidadeLoja.LOJA_2,
                quantidade=Decimal("5.000"),
            )

    def test_transferencia_em_lote_gera_mesmo_lote_referencia(self):
        produto_1 = Produto.objects.create(nome="Produto LT 1", sku="TR-L1", ativo=True)
        produto_2 = Produto.objects.create(nome="Produto LT 2", sku="TR-L2", ativo=True)
        ProdutoEstoqueUnidade.objects.create(produto=produto_1, unidade=UnidadeLoja.LOJA_1, saldo_atual=Decimal("10.000"))
        ProdutoEstoqueUnidade.objects.create(produto=produto_1, unidade=UnidadeLoja.LOJA_2, saldo_atual=Decimal("0.000"))
        ProdutoEstoqueUnidade.objects.create(produto=produto_2, unidade=UnidadeLoja.LOJA_1, saldo_atual=Decimal("8.000"))
        ProdutoEstoqueUnidade.objects.create(produto=produto_2, unidade=UnidadeLoja.LOJA_2, saldo_atual=Decimal("0.000"))

        result = transferir_lote_entre_unidades(
            itens=[
                {"produto": produto_1, "quantidade": Decimal("3.000")},
                {"produto": produto_2, "quantidade": Decimal("2.000")},
            ],
            unidade_origem=UnidadeLoja.LOJA_1,
            unidade_destino=UnidadeLoja.LOJA_2,
            observacao="Lote semanal",
        )

        self.assertTrue(result.lote_referencia.startswith("L"))
        self.assertEqual(result.total_itens, 2)
        lotes = set(TransferenciaEstoque.objects.values_list("lote_referencia", flat=True))
        self.assertEqual(lotes, {result.lote_referencia})


class TransferenciaCreateViewTest(TestCase):
    def test_post_em_lote_registra_varios_produtos(self):
        user_model = get_user_model()
        admin = user_model.objects.create_superuser("gestor", "gestor@example.com", "pass")
        produto_1 = Produto.objects.create(nome="Produto View T1", sku="TV-1", ativo=True)
        produto_2 = Produto.objects.create(nome="Produto View T2", sku="TV-2", ativo=True)
        ProdutoEstoqueUnidade.objects.create(produto=produto_1, unidade=UnidadeLoja.LOJA_1, saldo_atual=Decimal("9.000"))
        ProdutoEstoqueUnidade.objects.create(produto=produto_2, unidade=UnidadeLoja.LOJA_1, saldo_atual=Decimal("9.000"))
        self.client.force_login(admin)

        response = self.client.post(
            reverse("estoque:transferencia_create"),
            data={
                "unidade_origem": UnidadeLoja.LOJA_1,
                "unidade_destino": UnidadeLoja.LOJA_2,
                "data_transferencia": timezone.localdate().isoformat(),
                "observacao": "Reposicao multi",
                "itens-TOTAL_FORMS": "2",
                "itens-INITIAL_FORMS": "0",
                "itens-MIN_NUM_FORMS": "0",
                "itens-MAX_NUM_FORMS": "1000",
                "itens-0-produto": str(produto_1.id),
                "itens-0-quantidade": "1.500",
                "itens-1-produto": str(produto_2.id),
                "itens-1-quantidade": "2.000",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(TransferenciaEstoque.objects.count(), 2)


class ContagemRapidaTest(TestCase):
    def test_contagem_rapida_ajusta_unidade_e_total(self):
        produto = Produto.objects.create(nome="Produto Contagem", sku="CT-1", ativo=True)
        ProdutoEstoque.objects.create(produto=produto, saldo_atual=Decimal("10.000"))
        ProdutoEstoqueUnidade.objects.create(produto=produto, unidade=UnidadeLoja.LOJA_1, saldo_atual=Decimal("6.000"))
        ProdutoEstoqueUnidade.objects.create(produto=produto, unidade=UnidadeLoja.LOJA_2, saldo_atual=Decimal("4.000"))

        result = aplicar_contagem_rapida(
            unidade=UnidadeLoja.LOJA_1,
            itens=[{"produto": produto, "quantidade_contada": Decimal("8.500")}],
            observacao="Inventario semanal",
        )

        self.assertEqual(result.total_itens, 1)
        self.assertEqual(result.itens_ajustados, 1)
        unidade_fm = ProdutoEstoqueUnidade.objects.get(produto=produto, unidade=UnidadeLoja.LOJA_1)
        unidade_ml = ProdutoEstoqueUnidade.objects.get(produto=produto, unidade=UnidadeLoja.LOJA_2)
        cfg = ProdutoEstoque.objects.get(produto=produto)
        self.assertEqual(unidade_fm.saldo_atual, Decimal("8.500"))
        self.assertEqual(unidade_ml.saldo_atual, Decimal("4.000"))
        self.assertEqual(cfg.saldo_atual, Decimal("12.500"))


class SaidaOperacionalTest(TestCase):
    def test_saida_operacional_baixa_unidade_e_total(self):
        produto = Produto.objects.create(nome="Produto Operacional", sku="OP-1", ativo=True)
        ProdutoEstoque.objects.create(produto=produto, saldo_atual=Decimal("15.000"))
        ProdutoEstoqueUnidade.objects.create(produto=produto, unidade=UnidadeLoja.LOJA_1, saldo_atual=Decimal("10.000"))
        ProdutoEstoqueUnidade.objects.create(produto=produto, unidade=UnidadeLoja.LOJA_2, saldo_atual=Decimal("5.000"))

        result = registrar_saida_operacional_lote(
            unidade=UnidadeLoja.LOJA_1,
            tipo="TROCA",
            itens=[{"produto": produto, "quantidade": Decimal("2.000")}],
            observacao="Troca balcão",
        )

        self.assertEqual(result.total_itens, 1)
        self.assertEqual(result.itens_processados, 1)
        cfg = ProdutoEstoque.objects.get(produto=produto)
        fm = ProdutoEstoqueUnidade.objects.get(produto=produto, unidade=UnidadeLoja.LOJA_1)
        ml = ProdutoEstoqueUnidade.objects.get(produto=produto, unidade=UnidadeLoja.LOJA_2)
        self.assertEqual(cfg.saldo_atual, Decimal("13.000"))
        self.assertEqual(fm.saldo_atual, Decimal("8.000"))
        self.assertEqual(ml.saldo_atual, Decimal("5.000"))


class RecebimentoEstoqueFlowTest(TestCase):
    def test_compra_aprovada_aparece_na_fila_e_estoquista_confirma_recebimento(self):
        user_model = get_user_model()
        estoquista = user_model.objects.create_user("estoquista_fluxo", password="pass")
        Group.objects.get_or_create(name="estoquista")[0].user_set.add(estoquista)
        fornecedor = Fornecedor.objects.create(nome="Fornecedor Recebimento")
        produto = Produto.objects.create(nome="Produto Recebimento", sku="REC-1", ativo=True)
        compra = Compra.objects.create(
            fornecedor=fornecedor,
            centro_custo="FM",
            data_compra=timezone.localdate(),
            status=Compra.StatusChoices.APROVADA,
            orcamento_escolhido="ORC_1",
            justificativa_escolha="OK",
            observacoes="Aguardando recebimento",
        )
        ItemCompra.objects.create(compra=compra, produto=produto, quantidade=Decimal("4.000"), preco_unitario=Decimal("12.50"))

        self.client.force_login(estoquista)
        resp_list = self.client.get(reverse("estoque:recebimento_list"))
        self.assertEqual(resp_list.status_code, 200)
        self.assertContains(resp_list, f"#{compra.id}")

        resp_confirm = self.client.post(
            reverse("estoque:recebimento_confirmar", kwargs={"pk": compra.pk}),
            data={"observacao_conferencia": "Conferencia sem divergencias"},
        )
        self.assertEqual(resp_confirm.status_code, 302)

        compra.refresh_from_db()
        self.assertEqual(compra.status, Compra.StatusChoices.RECEBIDA)
        self.assertEqual(compra.recebido_por_id, estoquista.id)
        self.assertIsNotNone(compra.recebido_em)
        self.assertTrue(EstoqueMovimento.objects.filter(compra=compra, tipo="ENTRADA").exists())

    def test_comprador_nao_acessa_fila_recebimento_estoque(self):
        user_model = get_user_model()
        comprador = user_model.objects.create_user("comprador_sem_acesso", password="pass")
        Group.objects.get_or_create(name="comprador")[0].user_set.add(comprador)
        self.client.force_login(comprador)
        response = self.client.get(reverse("estoque:recebimento_list"))
        self.assertEqual(response.status_code, 403)
