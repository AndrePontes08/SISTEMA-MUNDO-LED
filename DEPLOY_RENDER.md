# Deploy no Render

## 1) Subir o código
- Envie este projeto para um repositório Git (GitHub/GitLab).

## 2) Criar via Blueprint
- No Render, use **New + > Blueprint** e selecione o repositório.
- O arquivo `render.yaml` criará:
  - 1 Web Service (`erp9-web`)
  - 1 PostgreSQL (`erp9-db`)

## 3) Ajustar variáveis obrigatórias
- Em `erp9-web`, atualize:
  - `DJANGO_ALLOWED_HOSTS` para o domínio real (ex.: `erp9-web.onrender.com`)
  - `CSRF_TRUSTED_ORIGINS` para a URL HTTPS real (ex.: `https://erp9-web.onrender.com`)

## 4) Deploy e migrações
- O build instala dependências e roda `collectstatic`.
- Antes de publicar, o Render executa `python manage.py migrate`.

## 5) Validar saúde da aplicação
- Acesse:
  - `/healthz/` deve retornar `ok`
  - `/admin/` e telas principais do ERP

## 6) Primeiro acesso admin
- Crie superusuário em Shell do Render:
  - `python manage.py createsuperuser`
