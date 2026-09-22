#!/bin/bash
# ===========================================================================
# instalar.sh - INSTALA O SISTEMA NO PYTHONANYWHERE
#
# Rode assim, no console Bash (UMA linha so):
#
#   bash ~/novos-convertidos/instalar.sh
#
# POR QUE UM ARQUIVO EM VEZ DE COLAR OS COMANDOS?
# O console do PythonAnywhere embaralha textos longos colados - ele processa
# as linhas fora de ordem e o bash reclama de sintaxe. Um arquivo no
# repositorio nao tem esse problema: o console recebe uma linha curta e le o
# resto do disco.
#
# Pode ser rodado de novo quantas vezes quiser: ele detecta o que ja existe
# e nao refaz. O .env, em especial, NUNCA e sobrescrito - senao uma segunda
# execucao trocaria os segredos e derrubaria todas as sessoes abertas.
# ===========================================================================

set -e   # para no primeiro erro, em vez de seguir com o sistema pela metade

PROJETO=~/novos-convertidos
USUARIO=$(whoami)

cd "$PROJETO"

echo ""
echo "==========================================================="
echo "  INSTALANDO O SISTEMA ADBA"
echo "==========================================================="
echo ""

# ---------------------------------------------------------------------------
# 1. AMBIENTE VIRTUAL
# ---------------------------------------------------------------------------
if [ -d venv ]; then
    echo ">>> 1/5  Ambiente virtual ja existe, aproveitando."
else
    echo ">>> 1/5  Criando o ambiente virtual..."
    python3.13 -m venv venv
fi

source venv/bin/activate

# ---------------------------------------------------------------------------
# 2. BIBLIOTECAS
# ---------------------------------------------------------------------------
if python -c "import flask, openpyxl, bcrypt" 2>/dev/null; then
    echo ">>> 2/5  Bibliotecas ja instaladas, pulando."
else
    echo ">>> 2/5  Instalando as bibliotecas (demora ~3 minutos)..."
    pip install -q --upgrade pip
    pip install -q -r requirements.txt
fi

# ---------------------------------------------------------------------------
# 3. SEGREDOS
# ---------------------------------------------------------------------------
# O .env NUNCA e sobrescrito. Se este script rodasse de novo e trocasse a
# SECRET_KEY, todos os logins abertos cairiam - e o token do formulario
# publico mudaria, quebrando o link ja divulgado na igreja.
if [ -f .env ]; then
    echo ">>> 3/5  Arquivo de segredos ja existe, MANTENDO o que esta la."
    SENHA="(a que voce ja anotou)"
    TOKEN=$(grep '^CADASTRO_TOKEN=' .env | cut -d= -f2-)
    LOGIN=$(grep '^ADMIN_LOGIN=' .env | cut -d= -f2-)
else
    echo ">>> 3/5  Gerando segredos NOVOS, aqui no servidor..."

    SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")
    TOKEN=$(python -c "import secrets; print(secrets.token_urlsafe(24))")
    SENHA=$(python -c "import secrets, string; alfabeto = string.ascii_letters + string.digits; print(''.join(secrets.choice(alfabeto) for _ in range(14)))")
    LOGIN=carlos

    {
        echo "APP_ENV=production"
        echo ""
        echo "SECRET_KEY=$SECRET"
        echo "CADASTRO_TOKEN=$TOKEN"
        echo ""
        echo "DATABASE_URL="
        echo ""
        echo "ADMIN_NOME=Carlos Moran"
        echo "ADMIN_LOGIN=$LOGIN"
        echo "ADMIN_SENHA_INICIAL=$SENHA"
        echo ""
        echo "LIMITE_CADASTRO_PUBLICO="
        echo "LIMITE_LOGIN="
    } > .env

    # So o dono consegue ler o arquivo.
    chmod 600 .env
fi

export FLASK_APP=run.py

# ---------------------------------------------------------------------------
# 4. BANCO DE DADOS
# ---------------------------------------------------------------------------
echo ">>> 4/5  Preparando o banco de dados..."
flask db upgrade

# ---------------------------------------------------------------------------
# 5. ADMIN, AGENDA E PRIMEIRA COPIA
# ---------------------------------------------------------------------------
echo ">>> 5/5  Criando o administrador e a agenda de cultos..."
flask criar-admin
flask seed-eventos
flask backup

# ---------------------------------------------------------------------------
# O RESUMO
# ---------------------------------------------------------------------------
echo ""
echo "==========================================================="
echo "  INSTALADO"
echo "==========================================================="
echo ""
echo "  Endereco do sistema:"
echo "     https://$USUARIO.pythonanywhere.com"
echo ""
echo "     login: $LOGIN"
echo "     senha: $SENHA"
echo ""
echo "     O sistema vai EXIGIR uma senha nova no primeiro acesso."
echo ""
echo "  Link publico de cadastro (para divulgar na igreja):"
echo "     https://$USUARIO.pythonanywhere.com/cadastro/$TOKEN"
echo ""
echo "==========================================================="
echo "  AINDA FALTA configurar a aba Web (virtualenv, WSGI,"
echo "  arquivos estaticos e HTTPS). O site so abre depois disso."
echo "==========================================================="
echo ""
