# -*- coding: utf-8 -*-
# ===========================================================================
# teste_multiapp.py - O SISTEMA CONVIVENDO COM OUTROS NO MESMO ENDERECO
#
# POR QUE ESTE TESTE EXISTE:
# No PythonAnywhere este sistema NAO tem o dominio so para ele. Ele divide
# carlosneto.pythonanywhere.com com dois sistemas que ja estavam no ar:
#
#     /demandas     Controle de Demandas
#     /fechamento   Fechamento Contas a Pagar
#     /adba         este sistema
#
# Um endereco = um processo Python = um sys.modules e um pote de cookies
# compartilhados. Isso cria tres jeitos de quebrar TUDO de uma vez:
#
#   1. COLISAO DE MODULO - os outros dois tem web_app.py, dados.py e core.py:
#      nomes genericos, iguais nos dois. O nosso tem "app" e "config", que sao
#      piores ainda. Sem limpar o sys.modules, um sistema importa o modulo do
#      outro - e o erro aparece longe da causa.
#
#   2. COOKIE ATROPELADO - se o nosso cookie se chamasse "session" (o padrao
#      do Flask), logar aqui derrubaria a sessao de quem estivesse nos outros.
#
#   3. PREFIXO PERDIDO - se url_for nao respeitar o SCRIPT_NAME, todo link
#      aponta para a raiz do dominio e nenhum clique chega neste sistema.
#
# O teste monta DOIS sistemas falsos com a mesma armadilha de nomes, anexa o
# bloco WSGI real (deploy/bloco_wsgi_adba.py) e verifica os tres pontos.
# ===========================================================================

import os
import shutil
import subprocess
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# O grosso do teste roda num processo FILHO, e isso e de proposito: o bloco
# WSGI mexe no sys.path e no sys.modules do interpretador, o que envenenaria
# as outras suites se rodasse aqui dentro.
# ---------------------------------------------------------------------------
FILHO = r'''# -*- coding: utf-8 -*-
import os, re, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = sys.argv[1]

os.environ["URL_PREFIXO"] = "/adba"
os.environ["APP_ENV"] = "development"

sys.path.insert(0, AQUI)
import wsgi_conta
from werkzeug.test import Client

ok = falhas = 0


def checar(t, c, d=""):
    global ok, falhas
    if c:
        ok += 1
    else:
        falhas += 1
        print("  [FALHA] " + t + ("  -> " + str(d) if d else ""))


cliente = Client(wsgi_conta.application)

# --- 1. os dois sistemas que ja estavam no ar ------------------------------
for nome in ("demandas", "fechamento"):
    r = cliente.get("/%s/" % nome)
    corpo = r.get_data(as_text=True)
    checar("/%s/ responde 200" % nome, r.status_code == 200, r.status_code)
    checar("/%s/ e o app certo" % nome, "sistema=" + nome in corpo, corpo[:80])
    # A armadilha: core.py e dados.py existem nos dois, com nome identico.
    checar("/%s/ nao importou o modulo do outro" % nome,
           "modulo_visto=" + nome in corpo, corpo[:80])

# --- 2. a raiz anuncia os tres --------------------------------------------
raiz = cliente.get("/").get_data(as_text=True)
for p in ("/demandas/", "/fechamento/", "/adba/"):
    checar("a raiz lista " + p, p in raiz, raiz)

# --- 3. o nosso sistema subiu ---------------------------------------------
r = cliente.get("/adba/", follow_redirects=True)
pagina = r.get_data(as_text=True)
checar("/adba/ responde 200", r.status_code == 200, r.status_code)
checar("/adba/ e a nossa tela de login", "csrf_token" in pagina, pagina[:150])
checar("/adba/ nao vazou traceback", "Traceback" not in pagina)

# --- 4. todo link gerado carrega o prefixo --------------------------------
links = set(re.findall(r'(?:href|src|action)="(/[^"]*)"', pagina))
fora = [l for l in links if not l.startswith("/adba/")]
checar("a pagina tem links", len(links) > 0, len(links))
checar("nenhum link escapa do /adba/", not fora, fora)

# --- 5. estaticos sob o prefixo -------------------------------------------
estaticos = [l for l in links if "/static/" in l]
checar("a pagina referencia estaticos", len(estaticos) > 0)
for e in sorted(estaticos)[:3]:
    checar(e + " carrega", cliente.get(e).status_code == 200)

# --- 6. o cookie nao invade os outros sistemas ----------------------------
from app import create_app
a = create_app()
checar('o cookie tem nome proprio, nao "session"',
       a.config["SESSION_COOKIE_NAME"] == "adba_sessao",
       a.config["SESSION_COOKIE_NAME"])
checar("o PATH do cookie de sessao e /adba",
       a.config["SESSION_COOKIE_PATH"] == "/adba",
       a.config["SESSION_COOKIE_PATH"])
checar('o PATH do cookie "lembrar" e /adba',
       a.config["REMEMBER_COOKIE_PATH"] == "/adba",
       a.config["REMEMBER_COOKIE_PATH"])

# --- 7. a sessao sobrevive a ida e volta pelo prefixo ---------------------
# Cookie com PATH errado falha EM SILENCIO: o navegador guarda e nunca devolve.
# Nao usamos senha de verdade aqui. O truque: mandar o CSRF correto com uma
# senha ERRADA. Se o cookie voltou, o CSRF passa e a resposta e "Login ou senha
# incorretos". Se o cookie nao voltou, o CSRF falha antes disso.
c2 = Client(wsgi_conta.application)
r = c2.get("/adba/login")
biscoitos = [v for (k, v) in r.headers if k.lower() == "set-cookie"]
checar("o cookie sai com Path=/adba",
       any("Path=/adba" in h for h in biscoitos), biscoitos)

m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', r.get_data(as_text=True))
checar("achou o token CSRF", bool(m))
if m:
    r = c2.post("/adba/login",
                data={"csrf_token": m.group(1), "login": "ninguem",
                      "senha": "senha-errada-de-proposito"},
                follow_redirects=True)
    corpo = r.get_data(as_text=True)
    checar("o CSRF passou (logo o cookie voltou)", r.status_code == 200, r.status_code)
    checar("chegou na validacao da senha, nao num erro de sessao",
           "incorretos" in corpo, corpo[:200])

# --- 8. sem prefixo, o comportamento antigo continua ----------------------
# Carregado direto do arquivo: o bloco WSGI ja tirou a pasta do sys.path, de
# proposito - entao um "import config" normal nao acharia mais nada aqui.
import importlib.util
os.environ["URL_PREFIXO"] = ""
_s = importlib.util.spec_from_file_location("config_sem_prefixo",
                                           os.path.join(RAIZ, "config.py"))
_c = importlib.util.module_from_spec(_s)
_s.loader.exec_module(_c)
b = _c.obter_config()
checar('sem URL_PREFIXO o cookie volta para "/"',
       b.SESSION_COOKIE_PATH == "/", b.SESSION_COOKIE_PATH)
checar("o nome proprio do cookie continua",
       b.SESSION_COOKIE_NAME == "adba_sessao", b.SESSION_COOKIE_NAME)

# --- 9. o JavaScript nao pode escrever endereco a mao ---------------------
# Este e o tipo de erro mais traicoeiro do prefixo. No HTML o Jinja resolve
# tudo com url_for(); mas o app.js e estatico e nao sabe onde o sistema mora.
# Um fetch("/alma/123/ficha") sai SEM o /adba, cai no roteador da conta - que
# responde 200 com uma lista em texto puro. Nao da erro nenhum: a tela so
# deixa de funcionar. Foi assim que a ficha lateral parou de abrir.
_js = open(os.path.join(RAIZ, "app", "static", "js", "app.js"),
           encoding="utf-8").read()

# Os COMENTARIOS saem antes da busca. Este arquivo explica o bug citando o
# codigo errado ('fetch("/alma/123/ficha")'), e sem tirar os comentarios o
# teste acusaria a propria explicacao - foi o que aconteceu na primeira
# rodada.
_codigo = re.sub(r"/\*.*?\*/", "", _js, flags=re.S)   # blocos /* ... */
_codigo = re.sub(r"//[^\n]*", "", _codigo)            # linhas // ...

# Pegamos o que vem logo depois de "fetch(": se for uma aspa seguida de
# barra, e um endereco NOSSO escrito a mao. O "." casa com a aspa, seja ela
# simples ou dupla - assim a expressao nao precisa de barras invertidas.
# Enderecos de fora ("https://viacep...") nao casam: depois da aspa vem "h".
_amao = re.findall(r"fetch\(\s*.(/[^\s)]*)", _codigo)
checar("nenhum fetch com endereco escrito a mao no app.js", not _amao, _amao)

checar("o app.js tem o ajudante enderecoDoSistema()",
       "function enderecoDoSistema(" in _js)
checar("a ficha lateral usa o ajudante",
       'enderecoDoSistema("/alma/' in _js)

# E o prefixo precisa chegar ate o JavaScript.
_base = open(os.path.join(RAIZ, "app", "templates", "base.html"),
             encoding="utf-8").read()
checar("o base.html publica o prefixo em window.ADBA_BASE",
       "window.ADBA_BASE" in _base and "request.script_root" in _base)

# --- 10. e o valor que chega na pagina e o certo --------------------------
# Ler o arquivo nao basta: o que importa e o que o servidor MANDA. Se o
# request.script_root nao valesse, aqui viria vazio e a ficha quebraria de
# novo - sem nenhum erro aparecer.
_html = cliente.get("/adba/login").get_data(as_text=True)
_linha = [l.strip() for l in _html.splitlines() if "ADBA_BASE" in l]
checar('a pagina servida em /adba traz ADBA_BASE = "/adba"',
       'window.ADBA_BASE = "/adba"' in _html, _linha[:1])

print("%d testes passaram, %d falharam" % (ok, falhas))
sys.exit(1 if falhas else 0)
'''

# ---------------------------------------------------------------------------
# Segundo processo: o QUE ACONTECE SE O NOSSO SISTEMA NAO SUBIR.
#
# Esta e a promessa central do bloco WSGI: um erro nosso (import quebrado,
# .env faltando, migracao pendente) NAO pode levar /demandas e /fechamento
# junto. O try/except do bloco existe exatamente para isso.
#
# Aqui o caminho do ADBA aponta para uma pasta vazia, entao "from app import
# create_app" estoura de verdade.
# ---------------------------------------------------------------------------
FILHO_QUEBRADO = '''# -*- coding: utf-8 -*-
import os, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
os.environ["URL_PREFIXO"] = "/adba"
os.environ["APP_ENV"] = "development"

sys.path.insert(0, AQUI)
import wsgi_quebrado                      # tem que carregar SEM estourar
from werkzeug.test import Client

ok = falhas = 0


def checar(t, c, d=""):
    global ok, falhas
    if c:
        ok += 1
    else:
        falhas += 1
        print("  [FALHA] " + t + ("  -> " + str(d) if d else ""))


cliente = Client(wsgi_quebrado.application)

# O WSGI carregou apesar do nosso erro - senao o import acima teria estourado.
checar("o arquivo WSGI carrega mesmo com o ADBA quebrado", True)

for nome in ("demandas", "fechamento"):
    r = cliente.get("/%s/" % nome)
    checar("com o ADBA quebrado, /%s/ continua no ar" % nome,
           r.status_code == 200 and "sistema=" + nome in r.get_data(as_text=True),
           r.status_code)

r = cliente.get("/adba/")
corpo = r.get_data(as_text=True)
# O DispatcherMiddleware entrega ao app padrao o que nao casa com nenhum
# prefixo. Com o ADBA fora, /adba/ cai na lista da conta - que justamente NAO
# menciona o /adba. Quem abrir o link ve que o sistema nao esta la, em vez de
# uma tela de erro.
checar("/adba/ nao serve o nosso sistema quebrado",
       "csrf_token" not in corpo, corpo[:120])
checar("/adba/ cai na lista da conta, sem derrubar o processo",
       "Sistemas nesta conta" in corpo, corpo[:120])

raiz = cliente.get("/").get_data(as_text=True)
checar("a raiz nao anuncia um /adba/ que nao subiu", "/adba/" not in raiz, raiz)
checar("a raiz continua anunciando os outros dois",
       "/demandas/" in raiz and "/fechamento/" in raiz, raiz)

print("%d testes passaram, %d falharam" % (ok, falhas))
sys.exit(1 if falhas else 0)
'''

# --- os dois sistemas falsos ----------------------------------------------
# Com a MESMA armadilha do servidor real: web_app.py, dados.py e core.py
# existindo nos dois, com nomes identicos.
IRMAO_CORE = 'QUEM = "%s"\n'
IRMAO_DADOS = 'from core import QUEM\nORIGEM = QUEM\n'
IRMAO_WEB = '''from flask import Flask
from dados import ORIGEM

app = Flask(__name__)
app.config["SECRET_KEY"] = "teste-%s"


@app.route("/")
def inicio():
    # Se a limpeza do sys.modules falhar, ORIGEM vem do sistema ERRADO.
    return "sistema=%s modulo_visto=" + ORIGEM
'''

# --- o WSGI da conta, com a mesma estrutura do arquivo real ----------------
WSGI_CONTA = '''import sys

from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.wrappers import Response

CAMINHO_DEM = r"{dem}"
if CAMINHO_DEM not in sys.path:
    sys.path.insert(0, CAMINHO_DEM)
from web_app import app as app_demandas

sys.path.remove(CAMINHO_DEM)
for _m in ("web_app", "dados", "core"):
    sys.modules.pop(_m, None)

CAMINHO_FEC = r"{fec}"
if CAMINHO_FEC not in sys.path:
    sys.path.insert(0, CAMINHO_FEC)
from web_app import app as app_fechamento

_raiz = Response(
    "Sistemas nesta conta:\\n"
    "  /demandas/    - Controle de Demandas\\n"
    "  /fechamento/  - Fechamento Contas a Pagar\\n",
    mimetype="text/plain")

application = DispatcherMiddleware(_raiz, {{
    "/demandas": app_demandas,
    "/fechamento": app_fechamento,
}})
'''

# O caminho de producao que o bloco WSGI usa. Trocamos pelo caminho local para
# testar o bloco REAL, sem uma copia que pode ficar desatualizada.
CAMINHO_PRODUCAO = '"/home/carlosneto/novos-convertidos"'


def _escrever(caminho, texto):
    with open(caminho, "w", encoding="utf-8", newline="\n") as f:
        f.write(texto)


def _ler(caminho):
    with open(caminho, encoding="utf-8") as f:
        return f.read()


def main():
    pasta = tempfile.mkdtemp(prefix="adba_multiapp_")
    try:
        # --- os dois irmaos ------------------------------------------------
        for nome in ("demandas", "fechamento"):
            d = os.path.join(pasta, nome, "sistema")
            os.makedirs(d)
            _escrever(os.path.join(d, "core.py"), IRMAO_CORE % nome)
            _escrever(os.path.join(d, "dados.py"), IRMAO_DADOS)
            _escrever(os.path.join(d, "web_app.py"), IRMAO_WEB % (nome, nome))

        # --- o WSGI da conta + o NOSSO bloco real anexado ------------------
        bloco = _ler(os.path.join(RAIZ, "deploy", "bloco_wsgi_adba.py"))
        if CAMINHO_PRODUCAO not in bloco:
            print("  [FALHA] o caminho de producao mudou em bloco_wsgi_adba.py")
            print("0 testes passaram, 1 falharam")
            return 1
        bloco = bloco.replace(CAMINHO_PRODUCAO, "r%r" % RAIZ)

        conteudo = WSGI_CONTA.format(
            dem=os.path.join(pasta, "demandas", "sistema"),
            fec=os.path.join(pasta, "fechamento", "sistema"),
        ) + "\n\n" + bloco
        _escrever(os.path.join(pasta, "wsgi_conta.py"), conteudo)
        _escrever(os.path.join(pasta, "filho.py"), FILHO)

        r = subprocess.run(
            [sys.executable, os.path.join(pasta, "filho.py"), RAIZ],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        saida = (r.stdout or "").rstrip()
        if "passaram" not in saida:
            print(saida)
            print((r.stderr or "")[-1500:])
            print("0 testes passaram, 1 falharam")
            return 1

        # --- a mesma montagem, mas com o NOSSO sistema quebrado -----------
        # Pasta vazia no lugar do projeto: "from app import create_app" falha
        # de verdade, e verificamos que os outros dois sobrevivem.
        vazia = os.path.join(pasta, "projeto_que_nao_existe")
        os.makedirs(vazia)
        quebrado = WSGI_CONTA.format(
            dem=os.path.join(pasta, "demandas", "sistema"),
            fec=os.path.join(pasta, "fechamento", "sistema"),
        ) + "\n\n" + _ler(
            os.path.join(RAIZ, "deploy", "bloco_wsgi_adba.py")
        ).replace(CAMINHO_PRODUCAO, "r%r" % vazia)
        _escrever(os.path.join(pasta, "wsgi_quebrado.py"), quebrado)
        _escrever(os.path.join(pasta, "filho_quebrado.py"), FILHO_QUEBRADO)

        r2 = subprocess.run(
            [sys.executable, os.path.join(pasta, "filho_quebrado.py")],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=pasta,
        )
        saida2 = (r2.stdout or "").rstrip()
        if "passaram" not in saida2:
            print(saida2)
            print((r2.stderr or "")[-1500:])
            print("0 testes passaram, 1 falharam")
            return 1

        # Junta as contagens das duas rodadas numa linha so, que e o que o
        # rodar_tudo.py le.
        total_ok = total_falhas = 0
        for s in (saida, saida2):
            for linha in s.splitlines():
                if "passaram" in linha:
                    partes = [x for x in linha.replace(",", " ").split() if x.isdigit()]
                    if len(partes) >= 2:
                        total_ok += int(partes[0])
                        total_falhas += int(partes[1])
                else:
                    print(linha)
        print("%d testes passaram, %d falharam" % (total_ok, total_falhas))
        return 1 if total_falhas else 0
    finally:
        shutil.rmtree(pasta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
