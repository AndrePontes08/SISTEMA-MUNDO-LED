from __future__ import annotations

from django.core.management.base import BaseCommand

from compras.models import Fornecedor
from core.services.normalizacao import normalizar_nome


class Command(BaseCommand):
    help = "Recalcula nome_normalizado de fornecedores e garante consistência."

    def handle(self, *args, **options):
        updated = 0
        for f in Fornecedor.objects.all():
            new_norm = normalizar_nome(f.nome)
            if f.nome_normalizado != new_norm:
                f.nome_normalizado = new_norm
                f.save(update_fields=["nome_normalizado"])
                updated += 1
        self.stdout.write(self.style.SUCCESS(f"OK. Fornecedores atualizados: {updated}"))
