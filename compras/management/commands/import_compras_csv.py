from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from compras.services.importacao_service import import_compras_csv


class Command(BaseCommand):
    help = "Importa compras a partir de um CSV."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str, help="Caminho do arquivo CSV")

    def handle(self, *args, **options):
        path = options["csv_path"]
        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                result = import_compras_csv(f)
        except FileNotFoundError as e:
            raise CommandError(str(e))

        self.stdout.write(self.style.SUCCESS(
            f"OK: compras={result.compras_criadas}, itens={result.itens_criados}, erros={len(result.erros)}"
        ))
        for err in result.erros[:50]:
            self.stdout.write(self.style.WARNING(err))
