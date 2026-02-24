from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.core.management import call_command


USERS = [
    {"nome": "Pedro Henrique", "username": "pedro.henrique", "email": "pedro.henrique@mundoled.local", "unidade": "ML"},
    {"nome": "Rhuan Robson", "username": "rhuan.robson", "email": "rhuan.robson@mundoled.local", "unidade": "ML"},
    {"nome": "Rhuan Kennedy", "username": "rhuan.kennedy", "email": "rhuan.kennedy@mundoled.local", "unidade": "ML"},
    {"nome": "Gabriel Pereira", "username": "gabriel.pereira", "email": "gabriel.pereira@mundoled.local", "unidade": "FM"},
    {"nome": "Hairton Fernandes", "username": "hairton.fernandes", "email": "hairton.fernandes@mundoled.local", "unidade": "FM"},
    {"nome": "Valeska Lima", "username": "valeska.lima", "email": "valeska.lima@mundoled.local", "unidade": "FM"},
    {"nome": "Debora Tuany", "username": "debora.tuany", "email": "debora.tuany@mundoled.local", "unidade": "FM"},
    {"nome": "Rhuan Gurgel", "username": "rhuan.gurgel", "email": "rhuan.gurgel@mundoled.local", "unidade": "FM"},
]

GROUPS_TO_ENSURE = [
    "vendedores",
    "estoque",
    "compras",
    "financeiro",
    "vendedor",
    "estoquista",
    "comprador",
    "compras/estoque",
    "admin/gestor",
    "ML COMERCIO - UNIDADE",
    "FM COMERCIO - UNIDADE",
    "troca_senha_obrigatoria",
]


class Command(BaseCommand):
    help = "Cria grupos e provisiona usuarios da MUNDO LED com senha temporaria e troca obrigatoria."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default="12345678",
            help="Senha temporaria padrao (default: 12345678).",
        )

    def handle(self, *args, **options):
        temp_password = options["password"]
        User = get_user_model()

        # Reusa comando existente para permissões dos grupos principais.
        call_command("seed_groups")

        ensured_groups = {name: Group.objects.get_or_create(name=name)[0] for name in GROUPS_TO_ENSURE}
        group_vendedor = ensured_groups["vendedor"]
        group_vendedores_alias = ensured_groups["vendedores"]
        group_forca_senha = ensured_groups["troca_senha_obrigatoria"]
        group_unidade_ml = ensured_groups["ML COMERCIO - UNIDADE"]
        group_unidade_fm = ensured_groups["FM COMERCIO - UNIDADE"]

        self.stdout.write("Provisionando usuarios...")
        for row in USERS:
            first_name = row["nome"].split(" ")[0]
            last_name = " ".join(row["nome"].split(" ")[1:]).strip()
            user, created = User.objects.get_or_create(
                username=row["username"],
                defaults={
                    "email": row["email"],
                    "first_name": first_name,
                    "last_name": last_name,
                    "is_active": True,
                },
            )
            user.email = row["email"]
            user.first_name = first_name
            user.last_name = last_name
            user.is_active = True
            user.is_superuser = False
            user.set_password(temp_password)
            user.save()

            unit_group = group_unidade_ml if row["unidade"] == "ML" else group_unidade_fm
            user.groups.add(group_vendedor, group_vendedores_alias, unit_group, group_forca_senha)

            self.stdout.write(
                f" - {row['nome']} ({row['username']}) => {'criado' if created else 'atualizado'} | unidade {row['unidade']}"
            )

        self.stdout.write(self.style.SUCCESS("Provisionamento concluido."))
        self.stdout.write(self.style.WARNING(f"Senha temporaria aplicada: {temp_password}"))
        self.stdout.write("Todos os usuarios foram marcados para troca obrigatoria de senha no primeiro login.")
