# ===========================================================================
# ADBA_NC_INICIO  <- marcador: o anexar-wsgi.sh procura esta linha para saber
#                    se o bloco ja foi instalado. NAO apague.
#
# NOVOS CONVERTIDOS ADBA - montado em /adba
#
# POR QUE ESTE BLOCO E APENAS ACRESCENTADO NO FIM DO ARQUIVO:
# O WSGI desta conta ja servia DOIS sistemas no ar (/demandas e /fechamento) e
# guarda as senhas deles em os.environ. Reescrever o arquivo derrubaria os dois
# e trocaria segredos em uso. Anexando, nenhuma linha existente e tocada - e o
# Python simplesmente usa a ULTIMA atribuicao de "application".
#
# Tudo que este bloco usa (sys, DispatcherMiddleware, Response, app_demandas,
# app_fechamento) ja foi definido acima, pelo arquivo original.
# ===========================================================================

# --- 1. As rotas que JA existiam ------------------------------------------
# Lidas de globals() em vez de escritas na mao: se um dia um dos sistemas
# sair do arquivo, este bloco continua valido em vez de estourar
# NameError - o que levaria TODOS os sistemas ao ar junto.
_adba_rotas = {}
for _adba_prefixo, _adba_nome in (
    ("/demandas", "app_demandas"),
    ("/fechamento", "app_fechamento"),
):
    if _adba_nome in globals():
        _adba_rotas[_adba_prefixo] = globals()[_adba_nome]

# --- 2. O nosso sistema ---------------------------------------------------
_ADBA_CAMINHO = "/home/carlosneto/novos-convertidos"

# O try/except inteiro existe por UM motivo: se o ADBA nao subir (erro de
# import, .env faltando, migracao pendente), os dois sistemas que JA estavam
# no ar continuam funcionando. Sem isso, um erro nosso derrubaria os tres.
try:
    if _ADBA_CAMINHO not in sys.path:
        sys.path.insert(0, _ADBA_CAMINHO)

    # Mesma disciplina do bloco do Fechamento, logo acima: "app" e "config"
    # sao nomes genericos de modulo. Se algum outro sistema tiver carregado
    # algo com esse nome, nos importariamos o modulo ERRADO - e o erro
    # apareceria longe daqui, sem apontar a causa.
    for _adba_m in ("app", "config"):
        sys.modules.pop(_adba_m, None)

    # O .env tem que ser lido ANTES de create_app(): e dele que vem a
    # SECRET_KEY, o CADASTRO_TOKEN, o URL_PREFIXO e o APP_ENV=production.
    from dotenv import load_dotenv
    load_dotenv(_ADBA_CAMINHO + "/.env")

    from app import create_app

    _adba_rotas["/adba"] = create_app()

except Exception:
    # O traceback vai para o Error log da aba Web - e o unico lugar onde da
    # para ver o motivo, ja que a pagina nao vai mostrar erro nenhum.
    import traceback
    traceback.print_exc()

finally:
    # Tiramos o caminho da lista de busca, como o arquivo original faz com os
    # outros dois. Isso NAO quebra o nosso sistema: o pacote "app" ja esta em
    # sys.modules com o caminho absoluto dele, e todo import interno nosso e
    # qualificado ("from app.rotas...").
    if _ADBA_CAMINHO in sys.path:
        sys.path.remove(_ADBA_CAMINHO)

# --- 3. A pagina da raiz --------------------------------------------------
# Lista so o que realmente subiu. Se o ADBA falhar no passo 2, a raiz nao
# anuncia um endereco quebrado.
_adba_texto_raiz = "Sistemas nesta conta:\n"
for _adba_prefixo, _adba_desc in (
    ("/demandas", "Controle de Demandas"),
    ("/fechamento", "Fechamento Contas a Pagar"),
    ("/adba", "Novos Convertidos (ADBA)"),
):
    if _adba_prefixo in _adba_rotas:
        _adba_texto_raiz += "  %-13s - %s\n" % (_adba_prefixo + "/", _adba_desc)

# --- 4. A montagem final --------------------------------------------------
# Esta atribuicao vem DEPOIS da original, entao e esta que vale.
application = DispatcherMiddleware(
    Response(_adba_texto_raiz, mimetype="text/plain"),
    _adba_rotas,
)
# ADBA_NC_FIM
# ===========================================================================
