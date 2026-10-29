#!/usr/bin/env bash
# Roda os testes de todos os serviços num ambiente isolado: um projeto separado do Docker Compose,
# "truco-testes", com containers, redes e volumes próprios. Os bancos e o broker do sistema que
# está em uso (o projeto "truco-online") não são tocados, e ele pode continuar no ar.
#
#   ./testes.sh                todas as suítes: auth, game, lobby, ranking e bots
#   ./testes.sh game bots      só as indicadas
#
# O ambiente sobe com o código atual (--build) e é apagado no fim, com os volumes, passando ou
# não. O gateway não sobe: os testes chamam os serviços por dentro da rede do Docker, e assim
# nenhuma porta do computador é ocupada.

set -euo pipefail
cd "$(dirname "$0")"

PROJETO=truco-testes
SUITES=(auth game lobby ranking bots)
if [ $# -gt 0 ]; then
  SUITES=("$@")
fi

compose() {
  docker compose -p "$PROJETO" "$@"
}

# Apaga o ambiente de testes ao sair, inclusive depois de um erro ou de um Ctrl+C.
trap 'echo "== Apagando o ambiente de testes"; compose down -v --remove-orphans >/dev/null 2>&1 || true' EXIT

# Os testes de serviço dos Bots jogam partidas com os serviços no ar, por isso sobem todos, e
# não só os das suítes pedidas.
echo "== Subindo o ambiente de testes ($PROJETO)"
compose up -d --build --wait auth game lobby ranking bots

falhas=()
for suite in "${SUITES[@]}"; do
  echo "== Testes: $suite"
  compose run --rm --no-deps "$suite" pytest || falhas+=("$suite")
done

if [ ${#falhas[@]} -gt 0 ]; then
  echo "== Falharam: ${falhas[*]}"
  exit 1
fi
echo "== Todas as suítes passaram: ${SUITES[*]}"
