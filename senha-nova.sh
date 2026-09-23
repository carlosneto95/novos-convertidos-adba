#!/bin/bash
# ===========================================================================
# senha-nova.sh - SORTEIA UMA SENHA NOVA PARA O ADMINISTRADOR
#
# Rode assim, no console Bash:
#
#   bash ~/novos-convertidos/senha-nova.sh
#
# QUANDO USAR:
#   - voce perdeu a senha do primeiro acesso
#   - a instalacao terminou sem mostrar a senha
#   - voce suspeita que a senha vazou
#
# A senha aparece UMA vez na tela. No banco fica so o hash, que nao tem
# volta - nem o sistema consegue mostra-la de novo.
# ===========================================================================

set -e

cd ~/novos-convertidos
source venv/bin/activate
export FLASK_APP=run.py

# --- Em que prefixo este sistema mora? ------------------------------------
# Neste servidor o endereco e dividido com outros sistemas, cada um sob um
# caminho. Sem ler isso aqui, o script imprimiria um link que nao abre.
PREFIXO=$(grep '^URL_PREFIXO=' .env 2>/dev/null | cut -d= -f2- | sed 's|/$||')

echo ""
echo "==========================================================="
echo "  CONFERINDO A INSTALACAO"
echo "==========================================================="

# --- O .env esta completo? -------------------------------------------------
# Mostramos apenas os NOMES e se estao preenchidos. Os valores em si nunca
# aparecem na tela: o console guarda historico, e o que aparece aqui pode
# acabar num print de tela.
for campo in APP_ENV SECRET_KEY CADASTRO_TOKEN ADMIN_LOGIN URL_PREFIXO; do
    valor=$(grep "^$campo=" .env 2>/dev/null | cut -d= -f2-)
    if [ -z "$valor" ]; then
        echo "  $campo: *** VAZIO - PROBLEMA ***"
    elif [ "$campo" = "APP_ENV" ] || [ "$campo" = "ADMIN_LOGIN" ]       || [ "$campo" = "URL_PREFIXO" ]; then
        echo "  $campo: $valor"
    else
        echo "  $campo: preenchido (${#valor} caracteres)"
    fi
done

echo ""
echo "==========================================================="
echo "  SORTEANDO UMA SENHA NOVA"
echo "==========================================================="

# --- Sorteia e grava no .env ----------------------------------------------
NOVA=$(python -c "import secrets, string; alfabeto = string.ascii_letters + string.digits; print(''.join(secrets.choice(alfabeto) for _ in range(14)))")

# sed -i troca a linha no proprio arquivo. O "|" como separador evita
# problema caso a senha sorteada contenha uma barra.
sed -i "s|^ADMIN_SENHA_INICIAL=.*|ADMIN_SENHA_INICIAL=$NOVA|" .env

# --redefinir-senha atualiza quem ja existe, em vez de reclamar que o
# usuario esta duplicado. E religa a exigencia de trocar no primeiro acesso.
flask criar-admin --redefinir-senha

LOGIN=$(grep '^ADMIN_LOGIN=' .env | cut -d= -f2-)
TOKEN=$(grep '^CADASTRO_TOKEN=' .env | cut -d= -f2-)
USUARIO=$(whoami)

echo ""
echo "==========================================================="
echo "  ANOTE AGORA - NAO APARECE DE NOVO"
echo "==========================================================="
echo ""
echo "     https://$USUARIO.pythonanywhere.com$PREFIXO/"
echo ""
echo "     login: $LOGIN"
echo "     senha: $NOVA"
echo ""
echo "  O sistema vai EXIGIR uma senha sua no primeiro acesso."
echo ""
echo "  Link publico de cadastro:"
echo "     https://$USUARIO.pythonanywhere.com$PREFIXO/cadastro/$TOKEN"
echo ""
echo "==========================================================="
echo ""
