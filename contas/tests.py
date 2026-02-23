from __future__ import annotations

from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from contas.models import Categoria, ContaAPagar, StatusContaChoices
from contas.services.pagamento_service import confirmar_pagamento
from contas.services.importacao_csv import import_contas_csv

import io


class ContasRegrasTest(TestCase):
    def setUp(self):
        self.cat = Categoria.objects.create(nome="GERAL")

    def test_nao_confirma_sem_comprovante_quando_exige(self):
        conta = ContaAPagar.objects.create(
            vencimento=timezone.localdate(),
            descricao="Conta teste",
            centro_custo="FM",
            categoria=self.cat,
            valor=Decimal("100.00"),
            exige_comprovante=True,
            importado=False,
        )
        with self.assertRaises(ValueError):
            confirmar_pagamento(conta)

    def test_import_csv_cria_contas(self):
        csv_text = "vencimento;descricao;centro_custo;valor;observacao\n10/01/2023;CHEQUE NIVALDO 238;FM;R$ 1.900,00;teste\n"
        f = io.StringIO(csv_text)
        result = import_contas_csv(f, fonte="TEST", exige_comprovante_padrao=False)
        self.assertGreaterEqual(result["criados"], 1)

    def test_confirma_pagamento_define_status_e_data(self):
        conta = ContaAPagar.objects.create(
            vencimento=timezone.localdate(),
            descricao="Conta pago",
            centro_custo="FM",
            categoria=self.cat,
            valor=Decimal("50.00"),
            exige_comprovante=False,
            importado=True,
        )
        confirmar_pagamento(conta)
        conta.refresh_from_db()
        self.assertEqual(conta.status, StatusContaChoices.PAGA)
        self.assertEqual(conta.pago_em, timezone.localdate())


class ContasDashboardViewTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser("admin", "admin@example.com", "pass")
        self.client.force_login(self.admin)

    def test_dashboard_mostra_contas_do_dia(self):
        hoje = timezone.localdate()
        ContaAPagar.objects.create(
            vencimento=hoje,
            descricao="Conta do dia",
            centro_custo="FM",
            valor=Decimal("123.45"),
            status=StatusContaChoices.ABERTA,
        )

        response = self.client.get(reverse("contas:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Conta do dia")
        self.assertContains(response, "123,45")


class ContasPeriodoPDFViewTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser("admin2", "admin2@example.com", "pass")
        self.client.force_login(self.admin)

    def test_pdf_dia_retorna_arquivo_pdf(self):
        ContaAPagar.objects.create(
            vencimento=timezone.localdate(),
            descricao="Conta PDF",
            centro_custo="FM",
            valor=Decimal("88.00"),
            status=StatusContaChoices.ABERTA,
        )

        response = self.client.get(reverse("contas:contas_periodo_pdf", kwargs={"periodo": "dia"}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
