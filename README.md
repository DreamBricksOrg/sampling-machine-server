# Projeto Usar Data Registration - Backend

Escopo inicial conforme backlog:

- Autenticação JWT
- Cadastro de usuário sem login e senha, somente dados
- Gestão de submissões (CRUD/admin)
- Geração de QR code para liberação do cadastro com ID
- Health-check

---

## Pré-requisitos

* Python 3.10+
* Docker

---

## 📦 Instalação e execução em modo de desenvolvimento

1. Clone o repositório e entre na pasta:

   ```bash
   git clone git@github.com:DreamBricksOrg/kapo_user_reg.git
   cd kapo_user_reg
   ```

2. Crie um virtualenv e instale dependências:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Configure seu `.env` (veja [exemplo de `.env.example`](./.env.example)).

4. Inicie a aplicação:

   Rode assim para debuggar

   ```bash
   uvicorn main:app \
     --app-dir src \
     --host 0.0.0.0 \
     --port 5000 \
     --reload \
     --log-level debug
   ```

  Use log-level info para ambientes de produção, ou stack tracing com Datadog ou Sentry.

## 🐳 Docker

```bash
docker build -t kapo_user_reg .
docker run -d \
  --name kapo_reg \
  -p 5009:5009 \
  --env-file .env \
  -v "$(pwd)/src/frontend/static":/app/src/frontend/static \
  kapo_user_reg
```

---

