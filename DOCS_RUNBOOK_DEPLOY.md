Runbook mínimo para aplicar mudanças (Sprint 1/2)

1) Preparar ambiente (local/staging):

- Ative virtualenv e instale dependências:

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

- Gerar e aplicar migrations:

```powershell
python manage.py makemigrations
python manage.py migrate
```

2) Testes rápidos:

```powershell
python manage.py test compras.tests.ComprasRegrasTest
python manage.py test estoque.tests.EstoqueRegrasTest
```

3) Verificar integrações e tarefas:

- Executar comando de alertas:

```powershell
python manage.py notify_low_stock
```

4) Migração em produção:

- Crie backup do banco (pg_dump / sqlite copy) antes de executar migrações.
- Execute `python manage.py migrate` em ambiente de manutenção.
- Execute testes de smoke:
  - criar compra de teste e executar endpoint `marcar_recebida`.
  - verificar saldo do produto e Lote/EstoqueMovimento criados.

5) Rollback básico:

- Se migração causar falha, restaurar backup do banco e reverter branch.

6) Configurações recomendadas:

- `settings.LOW_STOCK_NOTIFY = True` e `settings.LOW_STOCK_EMAILS = ['ops@example.com']` para alertas por e-mail.
- Configure `DEFAULT_FROM_EMAIL` e backend de e-mail em `settings`.

7) Notas de segurança e permissões:

- O endpoint `marcar_recebida` usa `GroupRequiredMixin` e exige grupos `admin/gestor` ou `compras/estoque`.
- Garanta que apenas usuários autorizados executem recepção de mercadorias.

8) Passos pós-deploy:

- Monitorar logs por 48h para erros relacionados a `registrar_entrada` (saldo/custo médio).
- Rodar `python manage.py notify_low_stock --notify-email` para validar envio de e-mails.

