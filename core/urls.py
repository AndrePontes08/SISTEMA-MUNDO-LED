from django.urls import path
from django.contrib.auth.views import (
    LoginView, PasswordChangeView, PasswordChangeDoneView,
    PasswordResetView, PasswordResetDoneView, PasswordResetConfirmView,
    PasswordResetCompleteView
)

from core.views import HomeView, CustomLogoutView, DocumentacaoView, healthz

app_name = "core"

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("healthz/", healthz, name="healthz"),
    path("documentacao/", DocumentacaoView.as_view(), name="documentacao"),
    
    # Auth URLs
    path("accounts/login/", LoginView.as_view(), name="login"),
    path("accounts/logout/", CustomLogoutView.as_view(), name="logout", kwargs={"next_page": "/"}),
    path("accounts/password_change/", PasswordChangeView.as_view(), name="password_change"),
    path("accounts/password_change/done/", PasswordChangeDoneView.as_view(), name="password_change_done"),
    path("accounts/password_reset/", PasswordResetView.as_view(), name="password_reset"),
    path("accounts/password_reset/done/", PasswordResetDoneView.as_view(), name="password_reset_done"),
    path("accounts/reset/<uidb64>/<token>/", PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("accounts/reset/done/", PasswordResetCompleteView.as_view(), name="password_reset_complete"),
]
