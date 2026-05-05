#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:5000}"
COLLECTION="${COLLECTION:-skyn_elite}"

echo "1) Init QRCode"
INIT_JSON=$(curl -sS -X POST "$BASE_URL/api/skyn/qrcode/init" -H "Content-Type: application/json")
echo "$INIT_JSON" | jq .
SESSION_ID=$(echo "$INIT_JSON" | jq -r .session_id)
SLUG=$(echo "$INIT_JSON" | jq -r .slug)
SHORT_URL=$(echo "$INIT_JSON" | jq -r .short_url)

if [[ -z "${SESSION_ID:-}" || "$SESSION_ID" == "null" ]]; then
  echo "ERRO: session_id vazio"; exit 1;
fi
if [[ -z "${SLUG:-}" || "$SLUG" == "null" ]]; then
  echo "ERRO: slug vazio"; exit 1;
fi

echo "2) Verificar redirecionamento do short_url (GET cabeçalhos)"
curl -sS -D - -o /dev/null "$SHORT_URL" | sed -n '1,10p'

echo "3) Complete Session"
COMPLETE_BODY=$(jq -n --arg sid "$SESSION_ID" --arg slug "$SLUG" '{session_id:$sid, slug:$slug}')
COMPLETE_JSON=$(curl -sS -X POST "$BASE_URL/api/skyn/session/complete" \
  -H "Content-Type: application/json" \
  --data-binary "$COMPLETE_BODY")
echo "$COMPLETE_JSON" | jq .

echo "4) Create User (usa o slug como code)"
EMAIL="skyn.teste+$(date +%s)@example.com"
CREATE_BODY=$(jq -n --arg name "Teste SKYN" --arg email "$EMAIL" --arg slug "$SLUG" \
  '{name:$name, email:$email, code:$slug}')
CREATE_JSON=$(curl -sS -X POST "$BASE_URL/api/users/?collection=$COLLECTION" \
  -H "Content-Type: application/json" \
  --data-binary "$CREATE_BODY")
echo "$CREATE_JSON" | jq .

USER_ID=$(echo "$CREATE_JSON" | jq -r .id)
if [[ -z "${USER_ID:-}" || "$USER_ID" == "null" ]]; then
  echo "ERRO: não retornou id do usuário"; exit 1;
fi

echo "5) Get User by Email"
curl -sS "$BASE_URL/api/users/email/$EMAIL?collection=$COLLECTION" | jq .

echo "OK"

# -----------------------------------------------------
# Funções adicionais: testar ciclo da sessão
# -----------------------------------------------------

echo "6) Acessar página /form (simula usuário escaneando QR com sid)"
curl -sS -D - "$BASE_URL/api/skyn/form?sid=$SESSION_ID" -o /dev/null | head -n 10

echo "7) Concluir sessão novamente (deve recusar ou marcar como encerrada)"
COMPLETE_JSON2=$(curl -sS -X POST "$BASE_URL/api/skyn/session/complete" \
  -H "Content-Type: application/json" \
  --data-binary "$COMPLETE_BODY")
echo "$COMPLETE_JSON2" | jq .

echo "8) Acessar página /form após sessão concluída (deve mostrar usada/expirada)"
curl -sS -D - "$BASE_URL/api/skyn/form?sid=$SESSION_ID" -o /dev/null | head -n 10

echo "9) Acessar /cta (sempre disponível)"
curl -sS -D - "$BASE_URL/api/skyn/cta" -o /dev/null | head -n 10

echo "10) Acessar /on (sempre disponível)"
curl -sS -D - "$BASE_URL/api/skyn/on" -o /dev/null | head -n 10

echo "11) Testar middleware anti-replay (POST /session/complete duas vezes seguidas)"
BODY=$(jq -n --arg sid "$SESSION_ID" --arg slug "$SLUG" '{session_id:$sid, slug:$slug}')
curl -s -o /dev/null -w "Primeira chamada: %{http_code}\n" \
  -X POST "$BASE_URL/api/skyn/session/complete" -H "Content-Type: application/json" --data-binary "$BODY"
curl -s -o /dev/null -w "Segunda chamada (esperado 429): %{http_code}\n" \
  -X POST "$BASE_URL/api/skyn/session/complete" -H "Content-Type: application/json" --data-binary "$BODY"
