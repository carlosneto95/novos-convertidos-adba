#!/bin/bash
# ===========================================================================
# preparar-venv.sh - DEIXA O VENV SERVIR OS TRES SISTEMAS
#
# Rode assim, no console Bash:
#
#   bash ~/novos-convertidos/preparar-venv.sh
#
# ---------------------------------------------------------------------------
# O PROBLEMA QUE ELE RESOLVE
#
# No PythonAnywhere, um web app tem UM virtualenv - e aqui um web app serve
# TRES sistemas (/demandas, /fechamento e /adba). Entao esse unico virtualenv
# precisa ter as bibliotecas dos tres.
#
# O campo Virtualenv da aba Web aponta para o venv deste projeto, que foi
# criado do zero e so tem o que o nosso requirements.txt pede. O Fechamento
# usa "requests", que nao esta la. O site continua no ar porque o processo que
# esta rodando subiu ANTES dessa troca: o PythonAnywhere so passa a usar o
# virtualenv novo no Reload.
#
# Ou seja: o Reload e que derrubaria os tres. Este script conserta isso ANTES.
#
# ---------------------------------------------------------------------------
# COMO ELE CONSERTA
#
# Liga "include-system-site-packages" no venv. Com isso o Python procura:
#   1. primeiro no venv    -> as NOSSAS versoes, as do requirements.txt
#   2. depois no sistema   -> o que os outros dois sistemas ja usavam
#
# A ordem importa: a nossa versao do Flask continua ganhando. O sistema so
# preenche o que falta.
#
# ---------------------------------------------------------------------------
# E SE NAO RESOLVER?
#
# O script testa o arquivo WSGI de verdade, carregando os tres sistemas. Se
# ainda faltar alguma coisa, ele DESFAZ a mudanca, mostra o que falta e avisa
# para NAO recarregar. Nada fica pela metade.
# ===========================================================================

set -u   # erro se usar variavel que nao existe
# Sem "set -e": aqui os comandos FALHAM de proposito, e queremos tratar a
# falha em vez de abortar o script no meio.

USUARIO=$(whoami)
PROJETO=${ADBA_PROJETO:-$HOME/novos-convertidos}
WSGI=${ADBA_WSGI:-/var/www/${USUARIO}_pythonanywhere_com_wsgi.py}
CFG="$PROJETO/venv/pyvenv.cfg"

cd "$PROJETO" || exit 1

echo ""
echo "==========================================================="
echo "  PREPARANDO O VENV PARA OS TRES SISTEMAS"
echo "==========================================================="

# ---------------------------------------------------------------------------
# A funcao que decide tudo: o arquivo WSGI carrega inteiro?
#
# Carregamos o arquivo DE VERDADE, com o mesmo Python que o servidor vai usar.
# E o unico teste que vale: qualquer outro seria um palpite.
# ---------------------------------------------------------------------------
testar_wsgi() {
    "$PROJETO/venv/bin/python" - "$WSGI" <<'FIM'
import sys

caminho = sys.argv[1]
ambiente = {"__file__": caminho, "__name__": "wsgi_teste"}
try:
    with open(caminho, encoding="utf-8") as f:
        exec(compile(f.read(), caminho, "exec"), ambiente)
except Exception as erro:
    # Sem traceback gigante: so o que interessa para decidir o que fazer.
    print("ERRO: %s: %s" % (type(erro).__name__, erro))
    sys.exit(1)

app = ambiente.get("application")
montados = sorted(getattr(app, "mounts", {}))
print("MONTADOS: " + (" ".join(montados) if montados else "(nenhum)"))
sys.exit(0)
FIM
}

echo ""
echo ">>> 1/3  Testando o arquivo WSGI com o venv atual..."
SAIDA=$(testar_wsgi 2>&1)
if [ $? -eq 0 ]; then
    echo "         $SAIDA"
    echo ""
    echo "  O venv ja serve os tres. Nada a mudar."
    JA_ESTAVA_BOM=1
else
    echo "         $SAIDA"
    JA_ESTAVA_BOM=0
fi

if [ "$JA_ESTAVA_BOM" = "0" ]; then
    # -----------------------------------------------------------------------
    echo ""
    echo ">>> 2/3  Ligando o acesso aos pacotes do sistema..."

    if [ ! -f "$CFG" ]; then
        echo "  ERRO: nao achei $CFG"
        echo "  O venv existe? Rode antes: bash ~/novos-convertidos/instalar.sh"
        exit 1
    fi

    cp "$CFG" "$CFG.backup"
    if grep -q '^include-system-site-packages' "$CFG"; then
        sed -i 's/^include-system-site-packages.*/include-system-site-packages = true/' "$CFG"
    else
        echo "include-system-site-packages = true" >> "$CFG"
    fi
    echo "         $(grep '^include-system-site-packages' "$CFG")"

    # -----------------------------------------------------------------------
    echo ""
    echo ">>> 3/3  Testando de novo..."
    SAIDA=$(testar_wsgi 2>&1)
    if [ $? -eq 0 ]; then
        echo "         $SAIDA"
        rm -f "$CFG.backup"
    else
        # Nao resolveu: desfaz, para nao deixar o ambiente mexido a toa.
        cp "$CFG.backup" "$CFG"
        rm -f "$CFG.backup"
        echo "         $SAIDA"
        echo ""
        echo "==========================================================="
        echo "  *** NAO RECARREGUE A ABA WEB ***"
        echo "==========================================================="
        echo ""
        echo "  Desfiz a mudanca: o venv voltou como estava."
        echo "  Os tres sistemas seguem no ar enquanto ninguem der Reload."
        echo ""
        echo "  Ainda falta a biblioteca que aparece no ERRO acima. Para"
        echo "  instala-la no venv:"
        echo ""
        echo "     source ~/novos-convertidos/venv/bin/activate"
        echo "     pip install NOME-DA-BIBLIOTECA"
        echo ""
        echo "  E rode este script de novo."
        echo ""
        exit 1
    fi
fi

# ---------------------------------------------------------------------------
PREFIXO=$(grep '^URL_PREFIXO=' .env 2>/dev/null | cut -d= -f2- | sed 's|/$||')

echo ""
echo "==========================================================="
echo "  PODE RECARREGAR"
echo "==========================================================="
echo ""
echo "  Os tres sistemas carregam com este venv. Agora sim:"
echo ""
echo "  1. Aba Web -> secao 'Static files' -> Enter URL / Enter path:"
echo ""
echo "       URL:       $PREFIXO/static/"
echo "       Directory: $PROJETO/app/static/"
echo ""
echo "     (opcional - so deixa os arquivos mais rapidos; sem isso o"
echo "      proprio Flask os entrega)"
echo ""
echo "  2. Botao verde Reload."
echo ""
echo "  Depois confira os tres:"
echo "       https://$USUARIO.pythonanywhere.com/demandas/"
echo "       https://$USUARIO.pythonanywhere.com/fechamento/"
echo "       https://$USUARIO.pythonanywhere.com$PREFIXO/"
echo ""
echo "==========================================================="
echo ""
