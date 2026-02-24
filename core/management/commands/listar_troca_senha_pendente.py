from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Lista usuarios que ainda precisam trocar a senha (grupo troca_senha_obrigatoria)."

    def handle(self, *args, **options):
        User = get_user_model()
        qs = (
            User.objects.filter(is_active=True, groups__name="troca_senha_obrigatoria")
            .order_by("username")
            .distinct()
        )
        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS("Nenhum usuario com troca de senha pendente."))
            return

        self.stdout.write(f"Usuarios com troca de senha pendente: {total}")
        for u in qs:
            nome = f"{u.first_name} {u.last_name}".strip() or "-"
            grupos = ", ".join(u.groups.exclude(name="troca_senha_obrigatoria").values_list("name", flat=True)) or "-"
            self.stdout.write(f"- {u.username} | nome: {nome} | email: {u.email or '-'} | grupos: {grupos}")
