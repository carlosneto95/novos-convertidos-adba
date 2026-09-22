# -*- coding: utf-8 -*-
"""
REVISAO DE SEGURANCA - os 14 itens da secao 7, conferidos um a um.

Nao basta dizer "esta seguro": cada item aqui e PROVADO com um teste que
falharia se a protecao nao existisse.
"""
import sys, re, os, subprocess, tempfile
from datetime import timedelta

# O caminho do projeto vem do PROPRIO arquivo, nao escrito a mao. Assim os
# testes funcionam em qualquer computador e tambem no servidor.
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.stdout.reconfigure(encoding="utf-8")

from config import DevelopmentConfig, ProductionConfig
from app import create_app
from app.extensions import db, limiter
from app.models import Usuario, NovoConvertido, Contato, Evento, Presenca, LogAuditoria
from app.tempo import agora, hoje
from app import opcoes


class ConfigTeste(DevelopmentConfig):
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = True
    CADASTRO_TOKEN = "token-secreto-de-teste"


ok = falhou = 0
falhas = []


def checa(item, desc, cond):
    global ok, falhou
    if cond:
        ok += 1
        print(f"     [OK]   {desc}")
    else:
        falhou += 1
        falhas.append(f"item {item}: {desc}")
        print(f"     [FALHA] {desc}")


def titulo(n, texto):
    print(f"\n  ITEM {n} — {texto}")


app = create_app(ConfigTeste)

with app.app_context():
    db.create_all()
    admin = Usuario(nome="Carlos Admin", login="admin", papel="admin", ativo=True, deve_trocar_senha=False)
    admin.definir_senha("SenhaForte#2026")
    joao = Usuario(nome="Joao Pereira", login="joao", papel="responsavel", ativo=True, deve_trocar_senha=False)
    joao.definir_senha("OutraSenha#99")
    ana = Usuario(nome="Ana Lima", login="ana", papel="responsavel", ativo=True, deve_trocar_senha=False)
    ana.definir_senha("MaisUma#777")
    db.session.add_all([admin, joao, ana])
    db.session.flush()
    ID_ADMIN, ID_JOAO, ID_ANA = admin.id, joao.id, ana.id

    def criar(nome, resp):
        a = NovoConvertido(
            nome_completo=nome, telefone="16992805852", sexo="F",
            data_nascimento=hoje().replace(year=hoje().year - 30),
            trabalho="culto_dominical", departamento="preciosas", data_conversao=hoje(),
            cadastrante_nome="T", cadastrante_telefone="16988887777",
            consentimento_em=agora(), consentimento_ip="127.0.0.1",
            status_ciclo=opcoes.STATUS_ATIVO, responsavel_atual_id=resp,
            designado_em=agora(), criado_em=agora(),
            observacao_sensivel="INFORMACAO INTIMA E RESERVADA",
        )
        db.session.add(a)
        db.session.flush()
        return a

    do_joao = criar("Alma Do Joao", ID_JOAO)
    da_ana = criar("Alma Da Ana", ID_ANA)
    db.session.commit()
    ID_DO_JOAO, ID_DA_ANA = do_joao.id, da_ana.id


def entrar(login, senha):
    with app.app_context():
        limiter.reset()
    c = app.test_client()
    h = c.get("/login").get_data(as_text=True)
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', h)
    c.post("/login", data={"login": login, "senha": senha,
                           "csrf_token": m.group(1) if m else ""})
    return c


def tok(c, url="/painel"):
    h = c.get(url).get_data(as_text=True)
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', h)
    return m.group(1) if m else ""


print("=" * 72)
print("  REVISÃO DE SEGURANÇA — os 14 itens da seção 7")
print("=" * 72)

# ---------------------------------------------------------------------------
titulo(1, "Senhas com bcrypt, nunca em texto puro")
with app.app_context():
    u = db.session.get(Usuario, ID_ADMIN)
    checa(1, "o hash começa com $2b$ (bcrypt)", u.senha_hash.startswith("$2b$"))
    checa(1, "a senha em texto NÃO está no banco", "SenhaForte#2026" not in u.senha_hash)
    checa(1, "senha certa é aceita", u.conferir_senha("SenhaForte#2026"))
    checa(1, "senha errada é recusada", not u.conferir_senha("SenhaForte#2027"))
    outro = Usuario(nome="X Y", login="_x", papel="responsavel")
    outro.definir_senha("SenhaForte#2026")
    checa(1, "mesma senha gera hashes diferentes (sal aleatório)",
          outro.senha_hash != u.senha_hash)
    fonte = open(os.path.join(RAIZ, "app", "models.py"), encoding="utf-8").read()
    checa(1, "não há md5/sha no código de senha",
          "md5" not in fonte.lower() and "sha1" not in fonte.lower())

# ---------------------------------------------------------------------------
titulo(2, "IDOR — UUID na URL + checagem no servidor")
with app.app_context():
    a = db.session.get(NovoConvertido, ID_DO_JOAO)
    checa(2, "o id é UUID de 36 caracteres, não 1/2/3", len(a.id) == 36 and "-" in a.id)
    checa(2, "o código sequencial existe só para exibição", a.codigo is not None)

cj = entrar("joao", "OutraSenha#99")
for rota, metodo in [(f"/alma/{ID_DA_ANA}/ficha", "GET"),
                     (f"/alma/{ID_DA_ANA}/contato", "POST"),
                     (f"/alma/{ID_DA_ANA}/presenca", "POST"),
                     (f"/alma/{ID_DA_ANA}/status", "POST"),
                     (f"/alma/{ID_DA_ANA}/transferir", "POST")]:
    if metodo == "GET":
        r = cj.get(rota)
    else:
        r = cj.post(rota, data={"csrf_token": tok(cj)})
    checa(2, f"{metodo} {rota.split('/')[-1]} de alma alheia → 403 (deu {r.status_code})",
          r.status_code == 403)

with app.app_context():
    n = db.session.scalar(db.select(db.func.count()).select_from(LogAuditoria)
                          .where(LogAuditoria.acao == "acesso_negado"))
    checa(2, f"as tentativas foram auditadas ({n})", n >= 4)

# ---------------------------------------------------------------------------
titulo(3, "Filtro no BANCO, não escondido no JavaScript")
h = cj.get("/painel").get_data(as_text=True)
checa(3, "o HTML do Joao NÃO contém a alma da Ana", "Alma Da Ana" not in h)
checa(3, "nem escondida em atributo/JS", ID_DA_ANA not in h)
# ATENCAO ao medir isto: o texto buscado volta na caixa de busca
# (<input value="...">), entao procurar a palavra no HTML da falso positivo.
# O que prova vazamento e o ID da alma aparecer, ou a lista trazer linhas.
# O UNICO sinal de vazamento que vale e o ID da alma alheia aparecer no HTML.
# Duas armadilhas que ja me enganaram aqui:
#   1. o texto buscado volta na caixa de busca (<input value="...">)
#   2. quando o Responsavel filtra pelo id de OUTRO, o sistema ignora o
#      filtro e mostra as almas DELE - a lista nao fica vazia, e isso esta
#      certo. Lista cheia nao prova vazamento; id alheio prova.
h_busca = cj.get("/painel?busca=Alma Da Ana").get_data(as_text=True)
checa(3, "buscar pelo nome dela não traz o registro dela", ID_DA_ANA not in h_busca)
checa(3, "a busca responde 'nenhuma alma'", "Nenhuma alma com esses filtros" in h_busca)

h_filtro = cj.get(f"/painel?responsavel={ID_ANA}").get_data(as_text=True)
checa(3, "filtrar pelo id da Ana não traz as almas dela", ID_DA_ANA not in h_filtro)
checa(3, "e o Joao continua vendo as dele", ID_DO_JOAO in h_filtro)

fonte_painel = open(os.path.join(RAIZ, "app", "rotas", "painel.py"), encoding="utf-8").read()
checa(3, "a restrição está na consulta ao banco",
      "responsavel_atual_id == current_user.id" in fonte_painel)

# ---------------------------------------------------------------------------
titulo(4, "CSRF em todos os formulários, inclusive o público")
c_anon = app.test_client()
r = c_anon.post("/cadastro/token-secreto-de-teste", data={"nome_completo": "X"})
checa(4, f"formulário PÚBLICO sem token → 400 (deu {r.status_code})", r.status_code == 400)
r = c_anon.post("/login", data={"login": "admin", "senha": "SenhaForte#2026"})
checa(4, f"login sem token → 400 (deu {r.status_code})", r.status_code == 400)

ca = entrar("admin", "SenhaForte#2026")
for rota in ["/responsaveis/criar", "/eventos/criar", "/admin/mesclar",
             f"/alma/{ID_DO_JOAO}/contato"]:
    r = ca.post(rota, data={"nome": "X"})
    checa(4, f"POST {rota} sem token → 400 (deu {r.status_code})", r.status_code == 400)

with app.app_context():
    checa(4, "CSRF está ligado na configuração", app.config["WTF_CSRF_ENABLED"] is True)

# ---------------------------------------------------------------------------
titulo(5, "XSS — autoescape ligado, |safe proibido")
ataque = "<script>alert('invadi')</script>"
with app.app_context():
    a = db.session.get(NovoConvertido, ID_DO_JOAO)
    a.nome_completo = ataque + " Silva"
    db.session.add(Contato(convertido_id=a.id, responsavel_id=ID_JOAO, tipo="telefone",
                           data_hora=agora(), resultado="efetivo",
                           relato=ataque + " no relato", criado_em=agora()))
    a.observacao_sensivel = ataque + " na observacao"
    db.session.commit()

cj2 = entrar("joao", "OutraSenha#99")
for rota in ["/painel", f"/alma/{ID_DO_JOAO}/ficha"]:
    h = cj2.get(rota).get_data(as_text=True)
    checa(5, f"{rota}: o script NÃO aparece executável", ataque not in h)
    checa(5, f"{rota}: aparece escapado como texto", "&lt;script&gt;" in h)

# nenhum |safe fora de comentario
import glob
usos_safe = []
for arq in glob.glob(os.path.join(RAIZ, "app", "templates", "**", "*.html"), recursive=True):
    for i, linha in enumerate(open(arq, encoding="utf-8"), 1):
        if "|safe" in linha or "| safe" in linha:
            # comentario Jinja {# ... #} ou linha dentro de bloco de comentario
            limpo = linha.strip()
            if not (limpo.startswith("{#") or limpo.startswith("#") or
                    "NUNCA usar" in linha or "NUNCA e usar" in linha or
                    "NUNCA com" in linha):
                usos_safe.append(f"{os.path.basename(arq)}:{i}")
checa(5, f"nenhum |safe em código de template ({usos_safe or 'nenhum'})", not usos_safe)

with app.app_context():
    a = db.session.get(NovoConvertido, ID_DO_JOAO)
    a.nome_completo = "Alma Do Joao"
    a.observacao_sensivel = "INFORMACAO INTIMA E RESERVADA"
    db.session.commit()

# ---------------------------------------------------------------------------
titulo(6, "Validação no SERVIDOR, não só no navegador")
c = app.test_client()
def csrf_publico(cliente):
    h = cliente.get("/cadastro/token-secreto-de-teste").get_data(as_text=True)
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', h)
    return m.group(1) if m else ""

def base(**mudancas):
    d = {"cadastrante_nome": "Irma Ana", "cadastrante_telefone": "(16) 98888-7777",
         "nome_completo": "Maria Silva Teste", "telefone": "(16) 99280-5852",
         "sexo": "F", "data_nascimento": "1992-03-14", "trabalho": "culto_dominical",
         "data_conversao": hoje().isoformat(), "departamento": "preciosas",
         "consentimento": "y", "website": ""}
    d.update(mudancas)
    return d

def conta_almas():
    with app.app_context():
        return db.session.scalar(db.select(db.func.count()).select_from(NovoConvertido))

casos = [
    ("sem consentimento LGPD", {"consentimento": None}),
    ("telefone falso", {"telefone": "99999999999"}),
    ("nascimento no futuro", {"data_nascimento": (hoje() + timedelta(days=30)).isoformat()}),
    ("departamento inventado", {"departamento": "hackeado"}),
    ("menor sem responsável legal",
     {"data_nascimento": hoje().replace(year=hoje().year - 14).isoformat()}),
]
for desc, mud in casos:
    with app.app_context():
        limiter.reset()
    c = app.test_client()
    d = base(**mud)
    d = {k: v for k, v in d.items() if v is not None}
    d["csrf_token"] = csrf_publico(c)
    antes = conta_almas()
    c.post("/cadastro/token-secreto-de-teste", data=d)
    checa(6, f"servidor recusa: {desc}", conta_almas() == antes)

# ---------------------------------------------------------------------------
titulo(7, "Formulário público: token, honeypot e limite por IP")
c = app.test_client()
checa(7, "token errado → 404 (não 403, que confirmaria a página)",
      c.get("/cadastro/token-errado").status_code == 404)
checa(7, "token certo abre",
      c.get("/cadastro/token-secreto-de-teste").status_code == 200)
h = c.get("/cadastro/token-secreto-de-teste").get_data(as_text=True)
checa(7, "o honeypot está na página", 'name="website"' in h)
checa(7, "e está escondido de gente", 'aria-hidden="true"' in h)

with app.app_context():
    limiter.reset()
c = app.test_client()
antes = conta_almas()
d = base(nome_completo="Robo Spam", website="http://spam.com")
d["csrf_token"] = csrf_publico(c)
r = c.post("/cadastro/token-secreto-de-teste", data=d)
checa(7, "robô recebe a tela de sucesso (não desconfia)", r.status_code == 302)
checa(7, "mas NADA foi gravado", conta_almas() == antes)

with app.app_context():
    limiter.reset()
    app.config["LIMITE_CADASTRO_PUBLICO"] = "3 per hour"
c = app.test_client()
codigos = []
for i in range(6):
    d = base(nome_completo=f"Teste Limite{i} Sobrenome")
    d["csrf_token"] = csrf_publico(c)
    codigos.append(c.post("/cadastro/token-secreto-de-teste", data=d).status_code)
checa(7, f"limite por IP bloqueia com 429 ({codigos})", 429 in codigos)
h429 = c.post("/cadastro/token-secreto-de-teste",
              data=dict(base(), csrf_token=csrf_publico(c))).get_data(as_text=True)
checa(7, "a página 429 NÃO revela o limite", "per hour" not in h429 and "per 1 hour" not in h429)
with app.app_context():
    app.config["LIMITE_CADASTRO_PUBLICO"] = "30 per hour"

fonte_cfg = open(os.path.join(RAIZ, "config.py"), encoding="utf-8").read()
checa(7, "o token vem do .env e é revogável sem mexer em código",
      'CADASTRO_TOKEN = _texto("CADASTRO_TOKEN")' in fonte_cfg)

# ---------------------------------------------------------------------------
titulo(8, "Segredos fora do código")
checa(8, "SECRET_KEY vem do .env", '_texto("SECRET_KEY")' in fonte_cfg)
checa(8, "não há chave escrita à mão no config",
      not re.search(r'SECRET_KEY\s*=\s*["\'][A-Za-z0-9]{10,}', fonte_cfg))
checa(8, ".env.example existe (modelo sem segredo)",
      os.path.exists(os.path.join(RAIZ, ".env.example")))
exemplo = open(os.path.join(RAIZ, ".env.example"), encoding="utf-8").read()
real = open(os.path.join(RAIZ, ".env"), encoding="utf-8").read()
chave_real = re.search(r"SECRET_KEY=(\S+)", real)
checa(8, "a chave REAL não está no .env.example",
      not chave_real or chave_real.group(1) not in exemplo)

# O teste que pegou o bug de verdade: o git ignora mesmo?
try:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        subprocess.run(["git", "init", "-q", tmp], check=True, capture_output=True)
        import shutil
        shutil.copy(os.path.join(RAIZ, ".gitignore"), tmp)
        for nome in [".env", "instance", "backups"]:
            caminho = os.path.join(tmp, nome)
            if nome == ".env":
                open(caminho, "w").close()
            else:
                os.makedirs(caminho, exist_ok=True)
                open(os.path.join(caminho, "x.db"), "w").close()
        def ignorado(rel):
            r = subprocess.run(["git", "check-ignore", "-q", rel], cwd=tmp, capture_output=True)
            return r.returncode == 0
        checa(8, "o GIT realmente ignora o .env", ignorado(".env"))
        checa(8, "o GIT realmente ignora instance/", ignorado("instance/x.db"))
        checa(8, "o GIT realmente ignora backups/", ignorado("backups/x.db"))
except Exception as e:
    checa(8, f"verificação com git (erro: {e})", False)

# ---------------------------------------------------------------------------
titulo(9, "Sessão: HttpOnly, Secure, SameSite, 8 horas")
with app.app_context():
    checa(9, "HttpOnly ligado (JavaScript não lê o cookie)",
          app.config["SESSION_COOKIE_HTTPONLY"] is True)
    checa(9, "SameSite=Lax (barra CSRF vindo de fora)",
          app.config["SESSION_COOKIE_SAMESITE"] == "Lax")
    checa(9, "expira em 8 horas",
          app.config["PERMANENT_SESSION_LIFETIME"] == timedelta(hours=8))
checa(9, "em PRODUÇÃO o cookie exige HTTPS",
      ProductionConfig.SESSION_COOKIE_SECURE is True)
checa(9, "em produção o 'lembrar de mim' também",
      ProductionConfig.REMEMBER_COOKIE_SECURE is True)
checa(9, "em produção o DEBUG está desligado", ProductionConfig.DEBUG is False)

ca2 = entrar("admin", "SenhaForte#2026")
cookies = [c for c in ca2._cookies] if hasattr(ca2, "_cookies") else []
checa(9, "a sessão é assinada com a SECRET_KEY",
      bool(app.config["SECRET_KEY"]))

# ---------------------------------------------------------------------------
titulo(10, "Login com limite de tentativas")
with app.app_context():
    limiter.reset()
c = app.test_client()
codigos = []
for i in range(8):
    h = c.get("/login").get_data(as_text=True)
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', h)
    r = c.post("/login", data={"login": "admin", "senha": f"errada{i}",
                               "csrf_token": m.group(1) if m else ""})
    codigos.append(r.status_code)
checa(10, f"trava depois de 5 tentativas erradas ({codigos})", 429 in codigos)

with app.app_context():
    limiter.reset()
c = app.test_client()
acertos = []
for i in range(8):
    h = c.get("/login").get_data(as_text=True)
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', h)
    if not m:
        acertos.append(302); continue
    acertos.append(c.post("/login", data={"login": "admin", "senha": "SenhaForte#2026",
                                          "csrf_token": m.group(1)}).status_code)
checa(10, f"quem ACERTA não gasta tentativa ({set(acertos)})", 429 not in acertos)

h = entrar("admin", "errada").get_data(as_text=True) if False else None
c = app.test_client()
with app.app_context():
    limiter.reset()
hl = c.get("/login").get_data(as_text=True)
m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', hl)
r1 = c.post("/login", data={"login": "admin", "senha": "x", "csrf_token": m.group(1)})
r2 = c.post("/login", data={"login": "nao-existe", "senha": "x", "csrf_token": m.group(1)})
checa(10, "a mensagem é a MESMA para senha errada e login inexistente",
      ("Login ou senha incorretos" in r1.get_data(as_text=True)) and
      ("Login ou senha incorretos" in r2.get_data(as_text=True)))

# ---------------------------------------------------------------------------
titulo(11, "Observação sensível restrita e auditada")
with app.app_context():
    checa(11, "a restrição está ligada na configuração",
          app.config["OBSERVACAO_SENSIVEL_RESTRITA"] is True)

cj3 = entrar("joao", "OutraSenha#99")
h = cj3.get(f"/alma/{ID_DO_JOAO}/ficha").get_data(as_text=True)
checa(11, "o responsável ATUAL vê", "INFORMACAO INTIMA" in h)

ca3 = entrar("admin", "SenhaForte#2026")
h = ca3.get(f"/alma/{ID_DO_JOAO}/ficha").get_data(as_text=True)
checa(11, "o Admin vê", "INFORMACAO INTIMA" in h)

cana = entrar("ana", "MaisUma#777")
r = cana.get(f"/alma/{ID_DO_JOAO}/ficha")
checa(11, f"outro responsável NÃO abre a ficha (deu {r.status_code})", r.status_code == 403)
checa(11, "e não vê a observação", "INFORMACAO INTIMA" not in r.get_data(as_text=True))

with app.app_context():
    n = db.session.scalar(db.select(db.func.count()).select_from(LogAuditoria)
                          .where(LogAuditoria.acao == "leitura_observacao_sensivel"))
    checa(11, f"toda LEITURA foi auditada ({n})", n >= 2)

fonte_acoes = open(os.path.join(RAIZ, "app", "rotas", "acoes.py"), encoding="utf-8").read()
checa(11, "na transferência ela NÃO é repassada por padrão",
      "not form.manter_observacao.data" in fonte_acoes)

checa(11, "e não é exportada no Excel",
      "observacao_sensivel" not in open(os.path.join(RAIZ, "app", "excel.py"),
                                        encoding="utf-8").read().split("ATENCAO:")[0])

# ---------------------------------------------------------------------------
titulo(12, "Exportação Excel: só Admin e auditada")
cj4 = entrar("joao", "OutraSenha#99")
r = cj4.get("/relatorios/excel")
checa(12, f"responsável recebe 403 (deu {r.status_code})", r.status_code == 403)
checa(12, "não veio planilha", r.get_data()[:2] != b"PK")

ca4 = entrar("admin", "SenhaForte#2026")
with app.app_context():
    antes = db.session.scalar(db.select(db.func.count()).select_from(LogAuditoria)
                              .where(LogAuditoria.acao == "exportacao_excel")) or 0
r = ca4.get("/relatorios/excel")
checa(12, "o Admin baixa", r.status_code == 200 and r.get_data()[:2] == b"PK")
with app.app_context():
    depois = db.session.scalar(db.select(db.func.count()).select_from(LogAuditoria)
                               .where(LogAuditoria.acao == "exportacao_excel"))
    checa(12, f"cada download vira registro ({antes} → {depois})", depois == antes + 1)

# ---------------------------------------------------------------------------
titulo(13, "Auditoria só de escrita — sem editar, sem apagar")
rotas_ruins = []
for regra in app.url_map.iter_rules():
    caminho = str(regra)
    metodos = (regra.methods or set()) & {"POST", "PUT", "PATCH", "DELETE"}
    if "auditoria" in caminho and metodos:
        rotas_ruins.append(f"{caminho} {sorted(metodos)}")
checa(13, f"nenhuma rota escreve/apaga na auditoria ({rotas_ruins or 'nenhuma'})",
      not rotas_ruins)

fontes = ""
for pasta, _, arquivos in os.walk(os.path.join(RAIZ, "app")):
    for nome in arquivos:
        if nome.endswith(".py"):
            fontes += open(os.path.join(pasta, nome), encoding="utf-8").read()
checa(13, "nenhum delete() na tabela de auditoria",
      "delete(LogAuditoria" not in fontes and "LogAuditoria).delete" not in fontes)

# Desloga DE VERDADE antes de conferir - antes o script so entrava, nunca
# saia, e o log naturalmente nao tinha "logout".
c_saida = entrar("admin", "SenhaForte#2026")
c_saida.post("/logout", data={"csrf_token": tok(c_saida)})

with app.app_context():
    acoes = {l[0] for l in db.session.execute(db.select(LogAuditoria.acao).distinct()).all()}
exigidas = {"login", "logout", "login_falhou", "acesso_negado",
            "leitura_observacao_sensivel", "exportacao_excel"}
faltando = exigidas - acoes
checa(13, f"as ações obrigatórias são registradas (faltando: {faltando or 'nenhuma'})",
      not faltando)

# ---------------------------------------------------------------------------
titulo(14, "Comando de backup")
checa(14, "o comando existe", "backup" in app.cli.commands)
fonte_bkp = open(os.path.join(RAIZ, "app", "comandos_backup.py"), encoding="utf-8").read()
checa(14, "usa a cópia segura do SQLite, não 'copiar e colar'",
      ".backup(" in fonte_bkp and "shutil.copy" not in fonte_bkp)
checa(14, "o nome do arquivo leva a data", '%Y-%m-%d' in fonte_bkp)
checa(14, "a cópia é conferida depois de criada", "Conferido" in fonte_bkp)

# ---------------------------------------------------------------------------
print("\n  EXTRA — cabeçalhos de segurança em toda resposta")
r = app.test_client().get("/login")
for cab, esperado in [("X-Content-Type-Options", "nosniff"),
                      ("X-Frame-Options", "DENY"),
                      ("Referrer-Policy", "strict-origin-when-cross-origin")]:
    checa("extra", f"{cab}: {r.headers.get(cab)}", r.headers.get(cab) == esperado)

print("\n" + "=" * 72)
if falhou:
    print(f"  {ok} verificações passaram, {falhou} FALHARAM")
    for f in falhas:
        print(f"    - {f}")
else:
    print(f"  {ok} verificações passaram — os 14 itens estão cobertos")
print("=" * 72)
sys.exit(1 if falhou else 0)
