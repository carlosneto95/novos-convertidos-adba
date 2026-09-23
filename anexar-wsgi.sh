#!/bin/bash
# ===========================================================================
# anexar-wsgi.sh - LIGA O SISTEMA ADBA EM /adba, SEM DERRUBAR OS OUTROS
#
# Rode assim, no console Bash:
#
#   bash ~/novos-convertidos/anexar-wsgi.sh
#
# O QUE ELE FAZ:
#   1. copia o WSGI atual para /var/www/*.backup-DATA  (volta atras sempre)
#   2. anexa o nosso bloco no FIM do arquivo - nenhuma linha existente muda
#   3. confere a sintaxe do arquivo montado
#   4. se a sintaxe quebrar, RESTAURA a copia e para
#   5. garante URL_PREFIXO=/adba no .env
#
# POR QUE ANEXAR E NAO REESCREVER:
# O WSGI desta conta ja serve /demandas e /fechamento, e guarda as senhas
# deles dentro do arquivo. Reescrever derrubaria os dois sistemas e trocaria
# segredos que estao em uso agora.
#
# Pode rodar quantas vezes quiser: se o bloco ja estiver la, ele avisa e sai
# sem duplicar nada.
# ===========================================================================

set -e

USUARIO=$(whoami)

# Os dois caminhos saem de variaveis so para que este script possa ser TESTADO
# fora do servidor, apontando para uma copia. No uso normal ninguem define
# nada disso e valem os caminhos reais do PythonAnywhere.
PROJETO=${ADBA_PROJETO:-$HOME/novos-convertidos}
WSGI=${ADBA_WSGI:-/var/www/${USUARIO}_pythonanywhere_com_wsgi.py}

BLOCO="$PROJETO/deploy/bloco_wsgi_adba.py"
MARCADOR=ADBA_NC_INICIO

echo ""
echo "==========================================================="
echo "  LIGANDO O ADBA EM /adba"
echo "==========================================================="
echo ""

# --- 0. Os arquivos existem? ----------------------------------------------
if [ ! -f "$WSGI" ]; then
    echo "  ERRO: nao achei o arquivo WSGI em:"
    echo "        $WSGI"
    echo "  Confira o nome na aba Web, em 'WSGI configuration file'."
    exit 1
fi
if [ ! -f "$BLOCO" ]; then
    echo "  ERRO: nao achei $BLOCO"
    echo "  Rode 'git pull' na pasta do projeto e tente de novo."
    exit 1
fi

# --- 1. Ja esta instalado? ------------------------------------------------
if grep -q "$MARCADOR" "$WSGI"; then
    echo "  O bloco do ADBA JA ESTA no arquivo WSGI. Nada a fazer."
    echo ""
    echo "  Para reinstalar do zero, apague do arquivo o trecho entre"
    echo "  ADBA_NC_INICIO e ADBA_NC_FIM e rode este script de novo."
    JA=1
else
    JA=0
fi

if [ "$JA" = "0" ]; then
    # --- 2. Copia de seguranca -------------------------------------------
    COPIA="${WSGI}.backup-$(date +%Y%m%d-%H%M%S)"
    cp "$WSGI" "$COPIA"
    echo ">>> 1/4  Copia de seguranca feita:"
    echo "         $COPIA"

    # --- 3. Anexa --------------------------------------------------------
    # A linha em branco garante que o bloco nao cole na ultima linha do
    # arquivo original (que pode nao terminar com quebra de linha).
    printf '\n\n' >> "$WSGI"
    cat "$BLOCO" >> "$WSGI"
    echo ">>> 2/4  Bloco anexado no fim do arquivo."

    # --- 4. A sintaxe sobreviveu? ----------------------------------------
    # Se quebrou, o site inteiro cai - os TRES sistemas. Por isso conferimos
    # aqui e voltamos atras sozinhos, antes de qualquer Reload.
    PY=$(command -v python3 || command -v python)
    if "$PY" -c "import sys; compile(open(sys.argv[1], encoding='utf-8').read(), sys.argv[1], 'exec')" "$WSGI"; then
        echo ">>> 3/4  Sintaxe do arquivo montado: OK"
    else
        cp "$COPIA" "$WSGI"
        echo ""
        echo "  *** A SINTAXE QUEBROU. RESTAUREI A COPIA. ***"
        echo "  Nada foi alterado no ar. Me mande o erro acima."
        exit 1
    fi
else
    echo ">>> 1-3  (pulados: bloco ja instalado)"
fi

# --- 5. URL_PREFIXO no .env ----------------------------------------------
# Este valor precisa ser IGUAL ao prefixo do WSGI (/adba). Ele define o PATH
# do cookie de sessao; errado, o login falha em silencio.
cd "$PROJETO"
if grep -q '^URL_PREFIXO=' .env 2>/dev/null; then
    sed -i 's|^URL_PREFIXO=.*|URL_PREFIXO=/adba|' .env
    echo ">>> 4/4  URL_PREFIXO corrigido para /adba no .env"
else
    printf '\nURL_PREFIXO=/adba\n' >> .env
    echo ">>> 4/4  URL_PREFIXO=/adba acrescentado ao .env"
fi

echo ""
echo "==========================================================="
echo "  PRONTO - FALTA UM CLIQUE"
echo "==========================================================="
echo ""
echo "  1. Aba Web -> secao 'Static files' -> Enter URL / Enter path:"
echo ""
echo "       URL:       /adba/static/"
echo "       Directory: $PROJETO/app/static/"
echo ""
echo "  2. Botao verde Reload."
echo ""
echo "  Depois o sistema abre em:"
echo "       https://$USUARIO.pythonanywhere.com/adba/"
echo ""
echo "  Os outros dois continuam onde estavam:"
echo "       https://$USUARIO.pythonanywhere.com/demandas/"
echo "       https://$USUARIO.pythonanywhere.com/fechamento/"
echo ""
echo "==========================================================="
echo ""
