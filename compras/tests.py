from __future__ import annotations

from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile

from compras.models import Fornecedor, Produto, Compra, ItemCompra
from compras.services.compras_service import recalcular_total
from compras.forms import CompraForm
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from estoque.models import ProdutoEstoque, EstoqueMovimento, Lote


class ComprasRegrasTest(TestCase):
    def test_recalcular_total_compra(self):
        fornecedor = Fornecedor.objects.create(nome="Fornecedor Exemplo LTDA")
        prod1 = Produto.objects.create(nome="Lampada LED 9W", sku="LED-9W")
        prod2 = Produto.objects.create(nome="Fita LED 5m", sku="FITA-5M")

        compra = Compra.objects.create(
            fornecedor=fornecedor,
            centro_custo="FM",
            data_compra=timezone.localdate(),
            status=Compra.StatusChoices.APROVADA,
            orcamento_escolhido="ORC_1",
            justificativa_escolha="Melhor custo-beneficio",
            observacoes="Compra aprovada para recebimento",
        )

        ItemCompra.objects.create(compra=compra, produto=prod1, quantidade=Decimal("2"), preco_unitario=Decimal("10.00"))
        ItemCompra.objects.create(compra=compra, produto=prod2, quantidade=Decimal("1"), preco_unitario=Decimal("50.00"))

        recalcular_total(compra)
        compra.refresh_from_db()

        self.assertEqual(compra.valor_total, Decimal("70.00"))

    def test_marcar_recebida_cria_entradas_estoque(self):
        User = get_user_model()
        admin = User.objects.create_superuser(username='admin', email='admin@example.com', password='pass')

        fornecedor = Fornecedor.objects.create(nome="Fornecedor Exemplo LTDA")
        prod1 = Produto.objects.create(nome="Parafuso M4", sku="P-M4")

        compra = Compra.objects.create(
            fornecedor=fornecedor,
            centro_custo="FM",
            data_compra=timezone.localdate(),
            status=Compra.StatusChoices.APROVADA,
            orcamento_escolhido="ORC_1",
            justificativa_escolha="Escolha validada",
            observacoes="Observacao obrigatoria",
        )

        ItemCompra.objects.create(compra=compra, produto=prod1, quantidade=Decimal("10"), preco_unitario=Decimal("1.50"))

        self.client.force_login(admin)
        url = reverse('compras:compra_marcar_recebida', kwargs={'pk': compra.pk})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)

        # Verifica lote e movimento e saldo
        lote = Lote.objects.filter(produto=prod1, compra=compra).first()
        self.assertIsNotNone(lote)
        mov = EstoqueMovimento.objects.filter(produto=prod1, tipo='ENTRADA', compra=compra).first()
        self.assertIsNotNone(mov)
        cfg = ProdutoEstoque.objects.get(produto=prod1)
        self.assertEqual(cfg.saldo_atual, lote.quantidade_inicial)

    def test_compra_form_exige_tres_orcamentos_e_observacoes(self):
        fornecedor = Fornecedor.objects.create(nome="Fornecedor Form")
        form = CompraForm(
            data={
                "fornecedor": fornecedor.id,
                "centro_custo": "FM",
                "data_compra": timezone.localdate(),
                "orcamento_escolhido": "",
                "justificativa_escolha": "",
                "observacoes": "",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("3 orcamentos", str(form.errors))

    def test_aprovacao_e_recebimento_restritos_por_papel(self):
        User = get_user_model()
        admin = User.objects.create_superuser(username="admin2", email="admin2@example.com", password="pass")
        comprador = User.objects.create_user(username="comprador", password="pass")
        estoquista = User.objects.create_user(username="estoquista", password="pass")
        Group.objects.get_or_create(name="comprador")[0].user_set.add(comprador)
        Group.objects.get_or_create(name="estoquista")[0].user_set.add(estoquista)

        fornecedor = Fornecedor.objects.create(nome="Fornecedor Aprov")
        produto = Produto.objects.create(nome="Produto Aprov", sku="APR-1")
        compra = Compra.objects.create(
            fornecedor=fornecedor,
            centro_custo="FM",
            data_compra=timezone.localdate(),
            orcamento_escolhido="ORC_1",
            justificativa_escolha="Escolha teste",
            observacoes="Obs teste",
            orcamento_1=SimpleUploadedFile("o1.txt", b"1"),
            orcamento_2=SimpleUploadedFile("o2.txt", b"2"),
            orcamento_3=SimpleUploadedFile("o3.txt", b"3"),
        )
        ItemCompra.objects.create(compra=compra, produto=produto, quantidade=Decimal("5"), preco_unitario=Decimal("2.00"))

        self.client.force_login(comprador)
        resp = self.client.post(reverse("compras:compra_marcar_recebida", kwargs={"pk": compra.pk}))
        self.assertEqual(resp.status_code, 302)
        compra.refresh_from_db()
        self.assertNotEqual(compra.status, Compra.StatusChoices.RECEBIDA)

        self.client.force_login(admin)
        self.client.post(reverse("compras:compra_aprovar", kwargs={"pk": compra.pk}))
        compra.refresh_from_db()
        self.assertEqual(compra.status, Compra.StatusChoices.APROVADA)

        self.client.force_login(estoquista)
        self.client.post(reverse("compras:compra_marcar_recebida", kwargs={"pk": compra.pk}))
        compra.refresh_from_db()
        self.assertEqual(compra.status, Compra.StatusChoices.RECEBIDA)

    def test_fila_aprovacao_restrita_a_admin(self):
        User = get_user_model()
        admin = User.objects.create_superuser(username="admin3", email="admin3@example.com", password="pass")
        comprador = User.objects.create_user(username="comprador2", password="pass")
        Group.objects.get_or_create(name="comprador")[0].user_set.add(comprador)

        fornecedor = Fornecedor.objects.create(nome="Fornecedor Fila")
        Compra.objects.create(
            fornecedor=fornecedor,
            centro_custo="FM",
            data_compra=timezone.localdate(),
            status=Compra.StatusChoices.SOLICITADA,
            observacoes="x",
        )

        self.client.force_login(comprador)
        resp_nao = self.client.get(reverse("compras:compra_aprovacao_list"))
        self.assertEqual(resp_nao.status_code, 302)

        self.client.force_login(admin)
        resp_ok = self.client.get(reverse("compras:compra_aprovacao_list"))
        self.assertEqual(resp_ok.status_code, 200)
