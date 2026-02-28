from __future__ import annotations

from django.contrib import messages
from django.shortcuts import redirect


class ForcePasswordChangeMiddleware:
    """
    Forca troca de senha para usuarios no grupo `troca_senha_obrigatoria`.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            if user.groups.filter(name="troca_senha_obrigatoria").exists():
                password_change_path = "/accounts/password_change/"
                allowed_paths = {
                    password_change_path,
                    "/accounts/password_change/done/",
                    "/accounts/logout/",
                }
                if not (
                    request.path in allowed_paths
                    or request.path.startswith("/static/")
                    or request.path.startswith("/media/")
                ):
                    if not request.session.get("senha_forcada_alertada", False):
                        messages.warning(request, "Por segurança, altere sua senha antes de continuar.")
                        request.session["senha_forcada_alertada"] = True
                    return redirect(password_change_path)

        return self.get_response(request)
