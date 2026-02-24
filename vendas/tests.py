from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from boletos.models import Cliente
from compras.models import Compra, Fornecedor, ItemCompra, Produto
from estoque.models import EstoqueMovimento, ProdutoEstoque, ProdutoEstoqueUnidade, UnidadeLoja
from estoque.services.estoque_service import registrar_entrada
from estoque.services.integracao_compras import dar_entrada_por_compra
from financeiro.models import Recebivel, StatusRecebivelChoices
from vendas.models import (
    FechamentoCaixaDiario,
    StatusVendaChoices,
    TipoDocumentoVendaChoices,
    TipoPagamentoChoices,
    Venda,
    VendaEvento,
    VendaMovimentoEstoque,
    VendaRecebivel,
)
from vendas.services.fechamento_caixa_service import gerar_fechamento_caixa
from vendas.services.vendas_service import (
    ItemVendaPayload,
    cancelar_venda,
    converter_orcamento_em_venda,
    criar_venda_com_itens,
    faturar_venda,
)


class VendasServiceTest(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser("admin", "admin@example.com", "pass")
        self.cliente = Cliente.objects.create(nome="Cliente Teste", cpf_cnpj="12345678901")
        self.produto = Produto.objects.create(nome="Produto Venda", sku="VEN-1", ativo=True)
        registrar_entrada(produto=self.produto, quantidade=Decimal("10.000"))

    def _criar_venda_base(self, tipo_pagamento=TipoPagamentoChoices.ESPECIE, parcelas=1) -> Venda:
        return criar_venda_com_itens(
            cliente=self.cliente,
            vendedor=self.user,
            data_venda=timezone.localdate(),
            tipo_pagamento=tipo_pagamento,
            numero_parcelas=parcelas,
            intervalo_parcelas_dias=30,
            acrescimo=Decimal("5.00"),
            observacoes="",
            itens=[
                ItemVendaPayload(
                    produto=self.produto,
                    quantidade=Decimal("2.000"),
                    preco_unitario=Decimal("100.00"),
                    desconto=Decimal("10.00"),
                )
            ],
        )

    def test_criacao_venda(self):
        venda = self._criar_venda_base()
        self.assertEqual(venda.status, StatusVendaChoices.RASCUNHO)
        self.assertEqual(venda.subtotal, Decimal("190.00"))
        self.assertEqual(venda.total_final, Decimal("195.00"))
        self.assertTrue(venda.codigo_identificacao.startswith("VEN-"))

    def test_criacao_venda_com_multiplos_produtos(self):
        produto_2 = Produto.objects.create(nome="Produto Venda 2", sku="VEN-2", ativo=True)
        registrar_entrada(produto=produto_2, quantidade=Decimal("20.000"))
        venda = criar_venda_com_itens(
            cliente=self.cliente,
            vendedor=self.user,
            data_venda=timezone.localdate(),
            tipo_pagamento=TipoPagamentoChoices.ESPECIE,
            numero_parcelas=1,
            intervalo_parcelas_dias=30,
            acrescimo=Decimal("0.00"),
            observacoes="",
            itens=[
                ItemVendaPayload(produto=self.produto, quantidade=Decimal("1.000"), preco_unitario=Decimal("100.00")),
                ItemVendaPayload(produto=produto_2, quantidade=Decimal("2.000"), preco_unitario=Decimal("50.00")),
            ],
        )
        self.assertEqual(venda.itens.count(), 2)
        self.assertEqual(venda.total_final, Decimal("200.00"))

    def test_faturamento_com_baixa_estoque(self):
        venda = self._criar_venda_base()
        venda.status = StatusVendaChoices.CONFIRMADA
        venda.unidade_saida = UnidadeLoja.LOJA_1
        venda.save(update_fields=["status", "unidade_saida"])

        faturar_venda(venda, self.user)
        venda.refresh_from_db()
        cfg = ProdutoEstoque.objects.get(produto=self.produto)
        saldo_unidade = ProdutoEstoqueUnidade.objects.get(produto=self.produto, unidade=UnidadeLoja.LOJA_1)

        self.assertEqual(venda.status, StatusVendaChoices.FATURADA)
        self.assertEqual(cfg.saldo_atual, Decimal("8.000"))
        self.assertEqual(saldo_unidade.saldo_atual, Decimal("8.000"))
        self.assertEqual(VendaMovimentoEstoque.objects.filter(venda=venda, tipo="SAIDA").count(), 1)

    def test_gera_recebiveis_para_venda_a_prazo(self):
        venda = self._criar_venda_base(tipo_pagamento=TipoPagamentoChoices.CREDITO_LOJA, parcelas=3)
        venda.status = StatusVendaChoices.CONFIRMADA
        venda.primeiro_vencimento = timezone.localdate()
        venda.save(update_fields=["status", "primeiro_vencimento"])

        faturar_venda(venda, self.user)
        self.assertEqual(VendaRecebivel.objects.filter(venda=venda).count(), 3)
        self.assertEqual(
            Recebivel.objects.filter(origem_app="vendas", origem_pk=venda.id).count(),
            3,
        )
        total = sum(
            VendaRecebivel.objects.filter(venda=venda).values_list("valor", flat=True),
            Decimal("0.00"),
        )
        self.assertEqual(total, venda.total_final)

    def test_cancelamento_reverte_estoque_e_recebiveis(self):
        venda = self._criar_venda_base(tipo_pagamento=TipoPagamentoChoices.CREDITO_LOJA, parcelas=2)
        venda.status = StatusVendaChoices.CONFIRMADA
        venda.primeiro_vencimento = timezone.localdate()
        venda.save(update_fields=["status", "primeiro_vencimento"])

        faturar_venda(venda, self.user)
        result = cancelar_venda(venda, self.user, motivo="Erro de cadastro")
        venda.refresh_from_db()
        cfg = ProdutoEstoque.objects.get(produto=self.produto)

        self.assertFalse(result.already_canceled)
        self.assertEqual(venda.status, StatusVendaChoices.CANCELADA)
        self.assertEqual(cfg.saldo_atual, Decimal("10.000"))
        self.assertEqual(
            Recebivel.objects.filter(origem_app="vendas", origem_pk=venda.id, status=StatusRecebivelChoices.CANCELADO).count(),
            2,
        )

    def test_idempotencia_faturamento(self):
        venda = self._criar_venda_base(tipo_pagamento=TipoPagamentoChoices.BOLETO, parcelas=2)
        venda.status = StatusVendaChoices.CONFIRMADA
        venda.primeiro_vencimento = timezone.localdate()
        venda.save(update_fields=["status", "primeiro_vencimento"])

        faturar_venda(venda, self.user)
        novamente = faturar_venda(venda, self.user)

        self.assertTrue(novamente.already_processed)
        self.assertEqual(VendaMovimentoEstoque.objects.filter(venda=venda, tipo="SAIDA").count(), 1)
        self.assertEqual(VendaRecebivel.objects.filter(venda=venda).count(), 2)

    def test_orcamento_precisa_converter_antes_de_faturar(self):
        venda = self._criar_venda_base()
        venda.tipo_documento = TipoDocumentoVendaChoices.ORCAMENTO
        venda.status = StatusVendaChoices.CONFIRMADA
        venda.save(update_fields=["tipo_documento", "status"])
        venda.refresh_from_db()
        self.assertTrue(venda.codigo_identificacao.startswith("ORC-"))

        with self.assertRaises(ValueError):
            faturar_venda(venda, self.user)

        converter_orcamento_em_venda(venda, self.user)
        venda.refresh_from_db()
        self.assertEqual(venda.tipo_documento, TipoDocumentoVendaChoices.VENDA)
        self.assertTrue(venda.codigo_identificacao.startswith("VEN-"))

        faturar_venda(venda, self.user)
        venda.refresh_from_db()
        self.assertEqual(venda.status, StatusVendaChoices.FATURADA)


class IntegracaoRegressaoTest(TestCase):
    def test_fluxo_compra_para_estoque_permanece_idempotente(self):
        fornecedor = Fornecedor.objects.create(nome="Fornecedor Integracao")
        produto = Produto.objects.create(nome="Produto Integracao", sku="INT-1")
        compra = Compra.objects.create(
            fornecedor=fornecedor,
            centro_custo="FM",
            data_compra=timezone.localdate(),
        )
        item = ItemCompra.objects.create(
            compra=compra,
            produto=produto,
            quantidade=Decimal("5.000"),
            preco_unitario=Decimal("10.00"),
        )

        criados_1 = dar_entrada_por_compra(compra)
        criados_2 = dar_entrada_por_compra(compra)

        self.assertEqual(criados_1, 1)
        self.assertEqual(criados_2, 0)
        self.assertEqual(EstoqueMovimento.objects.filter(item_compra=item, tipo="ENTRADA").count(), 1)


class VendasViewUXTest(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.gerente = user_model.objects.create_superuser("gerente", "gerente@example.com", "pass")
        self.vendedor = user_model.objects.create_user("vend", "vend@example.com", "pass")
        vendedor_group, _ = Group.objects.get_or_create(name="vendedor")
        self.vendedor.groups.add(vendedor_group)

        self.cliente = Cliente.objects.create(nome="Cliente UX", cpf_cnpj="99999999999")
        self.produto = Produto.objects.create(nome="Produto UX", sku="UX-1", ativo=True)
        registrar_entrada(produto=self.produto, quantidade=Decimal("50.000"))

    def test_vendedor_logado_define_proprietario_da_venda(self):
        self.client.force_login(self.vendedor)
        data_antiga = (timezone.localdate() - timedelta(days=30)).isoformat()
        response = self.client.post(
            reverse("vendas:venda_create"),
            data={
                "tipo_documento": "VENDA",
                "cliente": str(self.cliente.id),
                "vendedor": str(self.gerente.id),
                "unidade_saida": "LOJA_1",
                "data_venda": data_antiga,
                "tipo_pagamento": "AVISTA",
                "numero_parcelas": "1",
                "intervalo_parcelas_dias": "30",
                "primeiro_vencimento": "",
                "acrescimo": "0.00",
                "observacoes": "teste",
                "itens-TOTAL_FORMS": "1",
                "itens-INITIAL_FORMS": "0",
                "itens-MIN_NUM_FORMS": "0",
                "itens-MAX_NUM_FORMS": "1000",
                "itens-0-produto": str(self.produto.id),
                "itens-0-quantidade": "1.000",
                "itens-0-preco_unitario": "100.00",
                "itens-0-desconto": "0.00",
            },
        )
        self.assertEqual(response.status_code, 302)
        venda = Venda.objects.latest("id")
        self.assertEqual(venda.vendedor_id, self.vendedor.id)
        self.assertEqual(venda.data_venda, timezone.localdate())

    def test_desconto_acima_de_10_exige_autorizacao(self):
        self.client.force_login(self.vendedor)
        before_count = Venda.objects.count()
        response = self.client.post(
            reverse("vendas:venda_create"),
            data={
                "tipo_documento": "VENDA",
                "cliente": str(self.cliente.id),
                "vendedor": str(self.vendedor.id),
                "unidade_saida": "LOJA_1",
                "data_venda": timezone.localdate().isoformat(),
                "tipo_pagamento": "AVISTA",
                "numero_parcelas": "1",
                "intervalo_parcelas_dias": "30",
                "primeiro_vencimento": "",
                "acrescimo": "0.00",
                "observacoes": "teste desconto",
                "itens-TOTAL_FORMS": "1",
                "itens-INITIAL_FORMS": "0",
                "itens-MIN_NUM_FORMS": "0",
                "itens-MAX_NUM_FORMS": "1000",
                "itens-0-produto": str(self.produto.id),
                "itens-0-quantidade": "1.000",
                "itens-0-preco_unitario": "100.00",
                "itens-0-desconto": "20.00",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Venda.objects.count(), before_count)
        self.assertContains(response, "excede o limite de 10%")

    def test_desconto_acima_de_10_com_autorizacao_admin(self):
        self.client.force_login(self.vendedor)
        response = self.client.post(
            reverse("vendas:venda_create"),
            data={
                "tipo_documento": "VENDA",
                "cliente": str(self.cliente.id),
                "vendedor": str(self.vendedor.id),
                "unidade_saida": "LOJA_1",
                "data_venda": timezone.localdate().isoformat(),
                "tipo_pagamento": "AVISTA",
                "numero_parcelas": "1",
                "intervalo_parcelas_dias": "30",
                "primeiro_vencimento": "",
                "acrescimo": "0.00",
                "observacoes": "teste desconto autorizado",
                "desconto_autorizador": self.gerente.username,
                "desconto_senha": "pass",
                "itens-TOTAL_FORMS": "1",
                "itens-INITIAL_FORMS": "0",
                "itens-MIN_NUM_FORMS": "0",
                "itens-MAX_NUM_FORMS": "1000",
                "itens-0-produto": str(self.produto.id),
                "itens-0-quantidade": "1.000",
                "itens-0-preco_unitario": "100.00",
                "itens-0-desconto": "20.00",
            },
        )
        self.assertEqual(response.status_code, 302)

    def test_desconto_em_percentual_abate_total_final(self):
        self.client.force_login(self.vendedor)
        response = self.client.post(
            reverse("vendas:venda_create"),
            data={
                "tipo_documento": "VENDA",
                "cliente": str(self.cliente.id),
                "vendedor": str(self.vendedor.id),
                "unidade_saida": "LOJA_1",
                "data_venda": timezone.localdate().isoformat(),
                "tipo_pagamento": "AVISTA",
                "numero_parcelas": "1",
                "intervalo_parcelas_dias": "30",
                "primeiro_vencimento": "",
                "acrescimo": "0.00",
                "observacoes": "desconto percentual",
                "itens-TOTAL_FORMS": "1",
                "itens-INITIAL_FORMS": "0",
                "itens-MIN_NUM_FORMS": "0",
                "itens-MAX_NUM_FORMS": "1000",
                "itens-0-produto": str(self.produto.id),
                "itens-0-quantidade": "2.000",
                "itens-0-preco_unitario": "100.00",
                "itens-0-desconto": "10.00",
            },
        )
        self.assertEqual(response.status_code, 302)
        venda = Venda.objects.latest("id")
        self.assertEqual(venda.desconto_total, Decimal("20.00"))
        self.assertEqual(venda.total_final, Decimal("180.00"))

    def test_historico_filtra_por_vendedor(self):
        criar_venda_com_itens(
            cliente=self.cliente,
            vendedor=self.vendedor,
            data_venda=timezone.localdate(),
            tipo_pagamento=TipoPagamentoChoices.ESPECIE,
            numero_parcelas=1,
            intervalo_parcelas_dias=30,
            acrescimo=Decimal("0.00"),
            observacoes="venda vendedor 1",
            itens=[
                ItemVendaPayload(
                    produto=self.produto,
                    quantidade=Decimal("1.000"),
                    preco_unitario=Decimal("50.00"),
                    desconto=Decimal("0.00"),
                )
            ],
        )
        outro = get_user_model().objects.create_user("outro_vendedor", "outro@example.com", "pass")
        criar_venda_com_itens(
            cliente=self.cliente,
            vendedor=outro,
            data_venda=timezone.localdate(),
            tipo_pagamento=TipoPagamentoChoices.ESPECIE,
            numero_parcelas=1,
            intervalo_parcelas_dias=30,
            acrescimo=Decimal("0.00"),
            observacoes="venda vendedor 2",
            itens=[
                ItemVendaPayload(
                    produto=self.produto,
                    quantidade=Decimal("1.000"),
                    preco_unitario=Decimal("60.00"),
                    desconto=Decimal("0.00"),
                )
            ],
        )
        self.client.force_login(self.gerente)
        resp = self.client.get(reverse("vendas:venda_historico"), {"vendedor": "vend"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "vend</td>")
        self.assertNotContains(resp, "outro_vendedor</td>")

    def test_alteracao_registra_log_no_historico(self):
        venda = criar_venda_com_itens(
            cliente=self.cliente,
            vendedor=self.gerente,
            data_venda=timezone.localdate(),
            tipo_pagamento=TipoPagamentoChoices.ESPECIE,
            numero_parcelas=1,
            intervalo_parcelas_dias=30,
            acrescimo=Decimal("0.00"),
            observacoes="orig",
            itens=[
                ItemVendaPayload(
                    produto=self.produto,
                    quantidade=Decimal("1.000"),
                    preco_unitario=Decimal("100.00"),
                    desconto=Decimal("0.00"),
                )
            ],
        )
        self.client.force_login(self.gerente)
        resp = self.client.post(
            reverse("vendas:venda_update", kwargs={"pk": venda.pk}),
            data={
                "tipo_documento": "ORCAMENTO",
                "cliente": str(self.cliente.id),
                "vendedor": str(self.gerente.id),
                "unidade_saida": "LOJA_1",
                "data_venda": timezone.localdate().isoformat(),
                "tipo_pagamento": "AVISTA",
                "numero_parcelas": "1",
                "intervalo_parcelas_dias": "30",
                "primeiro_vencimento": "",
                "acrescimo": "0.00",
                "observacoes": "alterado",
                "itens-TOTAL_FORMS": "1",
                "itens-INITIAL_FORMS": "1",
                "itens-MIN_NUM_FORMS": "0",
                "itens-MAX_NUM_FORMS": "1000",
                "itens-0-id": str(venda.itens.first().id),
                "itens-0-venda": str(venda.id),
                "itens-0-produto": str(self.produto.id),
                "itens-0-quantidade": "2.000",
                "itens-0-preco_unitario": "100.00",
                "itens-0-desconto": "0.00",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            VendaEvento.objects.filter(venda=venda, detalhe__icontains="Alteracoes registradas").exists()
        )

    def test_pdf_da_venda(self):
        venda = criar_venda_com_itens(
            cliente=self.cliente,
            vendedor=self.gerente,
            data_venda=timezone.localdate(),
            tipo_pagamento=TipoPagamentoChoices.ESPECIE,
            numero_parcelas=1,
            intervalo_parcelas_dias=30,
            acrescimo=Decimal("0.00"),
            observacoes="",
            itens=[
                ItemVendaPayload(
                    produto=self.produto,
                    quantidade=Decimal("1.000"),
                    preco_unitario=Decimal("80.00"),
                    desconto=Decimal("0.00"),
                )
            ],
        )
        self.client.force_login(self.gerente)
        resp = self.client.get(reverse("vendas:venda_pdf", kwargs={"pk": venda.pk}))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")


class FechamentoCaixaTest(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.gerente = user_model.objects.create_superuser("gerente_fc", "gerente_fc@example.com", "pass")
        self.cliente = Cliente.objects.create(nome="Cliente Fechamento", cpf_cnpj="11111111111")
        self.produto = Produto.objects.create(nome="Produto Fechamento", sku="FC-1", ativo=True)
        registrar_entrada(produto=self.produto, quantidade=Decimal("30.000"))

        venda = criar_venda_com_itens(
            cliente=self.cliente,
            vendedor=self.gerente,
            data_venda=timezone.localdate(),
            tipo_pagamento=TipoPagamentoChoices.PIX,
            numero_parcelas=1,
            intervalo_parcelas_dias=30,
            acrescimo=Decimal("0.00"),
            observacoes="",
            itens=[
                ItemVendaPayload(
                    produto=self.produto,
                    quantidade=Decimal("2.000"),
                    preco_unitario=Decimal("50.00"),
                    desconto=Decimal("10.00"),
                )
            ],
        )
        venda.status = StatusVendaChoices.CONFIRMADA
        venda.save(update_fields=["status"])
        faturar_venda(venda, self.gerente)

    def test_gerar_fechamento_caixa_com_pdf(self):
        fechamento = gerar_fechamento_caixa(
            data_referencia=timezone.localdate(),
            usuario=self.gerente,
            observacoes="Fechamento teste",
        )
        self.assertIsNotNone(fechamento.pk)
        self.assertGreater(fechamento.total_vendas, 0)
        self.assertTrue(bool(fechamento.arquivo_pdf))

    def test_tela_fechamento_lista_e_baixa_pdf(self):
        fechamento = gerar_fechamento_caixa(
            data_referencia=timezone.localdate(),
            usuario=self.gerente,
            observacoes="Fechamento teste 2",
        )
        self.client.force_login(self.gerente)
        resp_list = self.client.get(reverse("vendas:fechamento_caixa_list"))
        self.assertEqual(resp_list.status_code, 200)
        self.assertContains(resp_list, "Histórico de fechamentos")

        resp_pdf = self.client.get(reverse("vendas:fechamento_caixa_pdf", kwargs={"pk": fechamento.pk}))
        self.assertEqual(resp_pdf.status_code, 200)
        self.assertEqual(resp_pdf["Content-Type"], "application/pdf")

    def test_historico_filtra_por_forma_pagamento(self):
        venda_credito = criar_venda_com_itens(
            cliente=self.cliente,
            vendedor=self.gerente,
            data_venda=timezone.localdate(),
            tipo_pagamento=TipoPagamentoChoices.CREDITO,
            numero_parcelas=1,
            intervalo_parcelas_dias=30,
            acrescimo=Decimal("0.00"),
            observacoes="venda no crédito",
            itens=[
                ItemVendaPayload(
                    produto=self.produto,
                    quantidade=Decimal("1.000"),
                    preco_unitario=Decimal("40.00"),
                    desconto=Decimal("0.00"),
                )
            ],
        )
        venda_credito.status = StatusVendaChoices.FATURADA
        venda_credito.save(update_fields=["status"])

        self.client.force_login(self.gerente)
        resp = self.client.get(reverse("vendas:venda_historico"), {"tipo_pagamento": TipoPagamentoChoices.CREDITO})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "CREDITO")
