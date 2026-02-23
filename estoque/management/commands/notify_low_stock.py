from __future__ import annotations

from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from decimal import Decimal

from estoque.models import ProdutoEstoque, AlertaEstoque, StatusAlerta
from estoque.services.alertas_service import verificar_e_criar_alerta


class Command(BaseCommand):
    help = "Verifica produtos com saldo abaixo do mínimo, cria alertas e envia notificação por e-mail (opcional)."

    def add_arguments(self, parser):
        parser.add_argument("--notify-email", action="store_true", help="Enviar e-mail de notificação para destinatários configurados.")

    def handle(self, *args, **options):
        enviados = 0
        criados = 0
        encontrados = []

        qs = ProdutoEstoque.objects.select_related("produto").all()
        for cfg in qs:
            saldo = cfg.saldo_atual or Decimal("0.000")
            minimo = cfg.estoque_minimo or Decimal("0.000")
            # chama a rotina já responsável por criar/atualizar alertas
            verificar_e_criar_alerta(cfg.produto)
            aberto = AlertaEstoque.objects.filter(produto=cfg.produto, status=StatusAlerta.ABERTO).first()
            if aberto:
                encontrados.append((cfg.produto.nome, saldo, minimo))
                criados += 1

        out_lines = [f"Relatório de alertas de estoque - {timezone.localdate()}", ""]
        if encontrados:
            out_lines.append("Produtos com alerta aberto:")
            for nome, saldo, minimo in encontrados:
                out_lines.append(f"- {nome}: saldo={saldo} min={minimo}")
        else:
            out_lines.append("Nenhum alerta aberto encontrado.")

        resumo = "\n".join(out_lines)
        self.stdout.write(resumo)

        if options.get("notify_email") or getattr(settings, "LOW_STOCK_NOTIFY", False):
            recipients = getattr(settings, "LOW_STOCK_EMAILS", [])
            if recipients:
                subject = f"[ERP] Alertas de estoque - {timezone.localdate()}"
                message = resumo
                from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None)
                try:
                    send_mail(subject, message, from_email, recipients)
                    enviados = len(recipients)
                    self.stdout.write(self.style.SUCCESS(f"E-mail enviado para {enviados} destinatário(s)."))
                except Exception as exc:
                    self.stderr.write(f"Falha ao enviar e-mail: {exc}")
            else:
                self.stdout.write("Nenhum destinatário configurado em LOW_STOCK_EMAILS.")

        self.stdout.write(self.style.SUCCESS(f"Verificados {qs.count()} produtos. {criados} alerta(s) abertos."))
