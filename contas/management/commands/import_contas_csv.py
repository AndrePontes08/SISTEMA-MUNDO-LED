from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from contas.services.importacao_csv import import_contas_csv


class Command(BaseCommand):
    help = "Importa Contas a Pagar a partir de CSV (robusto para colunas 'Unnamed')."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str, help="Caminho do arquivo CSV")
        parser.add_argument(
            "--exige-comprovante",
            action="store_true",
            help="Se marcado, registros importados exigirão comprovante para confirmar pagamento.",
        )

    def handle(self, *args, **options):
        path = options["csv_path"]
        exige = bool(options["exige_comprovante"])

        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                result = import_contas_csv(f, fonte=f"CMD:{path}", exige_comprovante_padrao=exige)
        except FileNotFoundError as e:
            raise CommandError(str(e))

        self.stdout.write(self.style.SUCCESS(f"OK. Criados: {result['criados']} | Erros: {len(result['erros'])}"))
        for err in result["erros"][:50]:
            self.stdout.write(self.style.WARNING(err))
