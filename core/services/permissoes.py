from __future__ import annotations

from typing import Iterable

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin


class GroupRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Restringe acesso por grupo.
    Use em CBVs: required_groups = ("financeiro",)
    """

    required_groups: Iterable[str] = tuple()

    def test_func(self) -> bool:
        user = self.request.user
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        if not self.required_groups:
            return True
        return user.groups.filter(name__in=list(self.required_groups)).exists()
