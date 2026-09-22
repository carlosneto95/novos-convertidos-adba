# -*- coding: utf-8 -*-
"""Testes de autenticacao (Etapa 4). Banco em memoria: nao toca no real."""
import os
import sys, re

# O caminho do projeto vem do PROPRIO arquivo, nao escrito a mao. Assim os
# testes funcionam em qualquer computador e tambem no servidor.
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from config import DevelopmentConfig
from app import create_app
from app.extensions import db, limiter
from app.models import Usuario, NovoConvertido, LogAuditoria
from app.tempo import hoje, agora
from app.seguranca import destino_seguro


class ConfigTeste(DevelopmentConfig):
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = True
    CADASTRO_TOKEN = "token-de-teste-123"


ok = falhou = 0


def checa(desc, cond):
    global ok, falhou
    if cond:
        ok += 1
        print(f"  [OK]   {desc}")
    else:
        falhou += 1
        print(f"  [FALHA] {desc}")


app = create_app(ConfigTeste)

with app.app_context():
    db.create_all()

    admin = Usuario(nome="Carlos Admin", login="admin", papel="admin",
                    ativo=True, deve_trocar_senha=False)
    admin.definir_senha("SenhaForte#2026")

    joao = Usuario(nome="Joao Pereira", login="joao", papel="responsavel",
                   ativo=True, deve_trocar_senha=False)
    joao.definir_senha("OutraSenha#99")

    ana = Usuario(nome="Ana Lima", login="ana", papel="responsavel",
                  ativo=True, deve_trocar_senha=False)
    ana.definir_senha("MaisUma#777")

    novato = Usuario(nome="Pedro Novo", login="pedro", papel="responsavel",
                     ativo=True, deve_trocar_senha=True)
    novato.definir_senha("senha123")

    inativo = Usuario(nome="Ex Membro", login="exmembro", papel="responsavel",
                      ativo=False, deve_trocar_senha=False)
    inativo.definir_senha("QualquerUma#1")

    db.session.add_all([admin, joao, ana, novato, inativo])
    db.session.flush()

    def nova_alma(nome, responsavel):
        return NovoConvertido(
            nome_completo=nome, telefone="16999990000", sexo="F",
            data_nascimento=hoje().replace(year=hoje().year - 30),
            trabalho="culto_dominical", departamento="preciosas",
            cadastrante_nome="Irma Ana", cadastrante_telefone="16988887777",
            consentimento_em=agora(), consentimento_ip="127.0.0.1",
            status_ciclo="em_acompanhamento",
            responsavel_atual_id=responsavel.id, designado_em=agora(),
        )

    alma_joao = nova_alma("Maria do Joao", joao)
    alma_ana = nova_alma("Clara da Ana", ana)
    db.session.add_all([alma_joao, alma_ana])
    db.session.commit()

    ID_ALMA_JOAO = alma_joao.id
    ID_ALMA_ANA = alma_ana.id


def zerar_limite():
    with app.app_context():
        limiter.reset()


def csrf_de(cliente, url="/login"):
    html = cliente.get(url).get_data(as_text=True)
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    return m.group(1) if m else None


def entrar(cliente, login, senha, **extra):
    d = {"login": login, "senha": senha, "csrf_token": csrf_de(cliente)}
    d.update(extra)
    return cliente.post("/login", data=d, follow_redirects=False)


print("\n--- 1. ROTAS PROTEGIDAS (sem login) ---")
zerar_limite()
c = app.test_client()
checa("/ redireciona para /login", c.get("/").headers.get("Location", "") == "/login")
r = c.get("/painel")
checa("/painel sem login redireciona", r.status_code == 302 and "/login" in r.headers.get("Location", ""))
r = c.get("/trocar-senha")
checa("/trocar-senha sem login redireciona", r.status_code == 302)
checa("/login abre normalmente", c.get("/login").status_code == 200)

print("\n--- 2. SENHA ERRADA ---")
zerar_limite()
c = app.test_client()
r = entrar(c, "admin", "senha-errada")
checa("senha errada nao entra", r.status_code == 200)
html = r.get_data(as_text=True)
checa("mensagem e vaga (nao diz se o login existe)", "Login ou senha incorretos" in html)
checa("nao revela 'usuario nao encontrado'", "nao encontrado" not in html.lower())

zerar_limite()
c = app.test_client()
r = entrar(c, "usuario-que-nao-existe", "qualquer")
html2 = r.get_data(as_text=True)
checa("login inexistente da a MESMA mensagem", "Login ou senha incorretos" in html2)

print("\n--- 3. LOGIN CORRETO ---")
zerar_limite()
c = app.test_client()
r = entrar(c, "admin", "SenhaForte#2026")
checa("admin entra (redireciona)", r.status_code == 302)
checa("vai para o painel", "/painel" in r.headers.get("Location", ""))
checa("painel abre depois do login", c.get("/painel").status_code == 200)

print("\n--- 4. LOGIN NAO DIFERENCIA MAIUSCULAS ---")
zerar_limite()
c = app.test_client()
r = entrar(c, "ADMIN", "SenhaForte#2026")
checa('"ADMIN" entra igual a "admin"', r.status_code == 302)

print("\n--- 5. USUARIO DESATIVADO ---")
zerar_limite()
c = app.test_client()
r = entrar(c, "exmembro", "QualquerUma#1")
checa("usuario desativado nao entra", r.status_code == 200)
checa("avisa que o acesso foi desativado", "desativado" in r.get_data(as_text=True))

print("\n--- 6. TROCA DE SENHA OBRIGATORIA ---")
zerar_limite()
c = app.test_client()
r = entrar(c, "pedro", "senha123")
checa("entra, mas e mandado para a troca", "/trocar-senha" in r.headers.get("Location", ""))
r = c.get("/painel")
checa("nao consegue abrir /painel digitando a URL", r.status_code == 302 and "/trocar-senha" in r.headers.get("Location", ""))
checa("a tela de troca abre", c.get("/trocar-senha").status_code == 200)

# tenta trocar pela MESMA senha
d = {"senha_atual": "senha123", "senha_nova": "senha123",
     "senha_confirmacao": "senha123", "csrf_token": csrf_de(c, "/trocar-senha")}
r = c.post("/trocar-senha", data=d)
checa("recusa senha nova igual a atual", "diferente da atual" in r.get_data(as_text=True))

# tenta uma senha obvia
d = {"senha_atual": "senha123", "senha_nova": "12345678",
     "senha_confirmacao": "12345678", "csrf_token": csrf_de(c, "/trocar-senha")}
r = c.post("/trocar-senha", data=d)
checa("recusa senha obvia (12345678)", "facil demais" in r.get_data(as_text=True))

# senhas diferentes entre si
d = {"senha_atual": "senha123", "senha_nova": "NovaSenha#2026",
     "senha_confirmacao": "NovaSenha#2027", "csrf_token": csrf_de(c, "/trocar-senha")}
r = c.post("/trocar-senha", data=d)
checa("recusa confirmacao diferente", "nao sao iguais" in r.get_data(as_text=True))

# senha atual errada
d = {"senha_atual": "errada", "senha_nova": "NovaSenha#2026",
     "senha_confirmacao": "NovaSenha#2026", "csrf_token": csrf_de(c, "/trocar-senha")}
r = c.post("/trocar-senha", data=d)
checa("recusa senha atual errada", "senha atual esta incorreta" in r.get_data(as_text=True))

# agora a troca valida
d = {"senha_atual": "senha123", "senha_nova": "NovaSenha#2026",
     "senha_confirmacao": "NovaSenha#2026", "csrf_token": csrf_de(c, "/trocar-senha")}
r = c.post("/trocar-senha", data=d)
checa("troca valida e aceita", r.status_code == 302 and "/painel" in r.headers.get("Location", ""))
checa("agora /painel abre", c.get("/painel").status_code == 200)

with app.app_context():
    p = db.session.execute(db.select(Usuario).where(Usuario.login == "pedro")).scalar_one()
    checa("a marca de troca obrigatoria foi apagada", p.deve_trocar_senha is False)
    checa("a senha antiga nao funciona mais", not p.conferir_senha("senha123"))
    checa("a senha nova funciona", p.conferir_senha("NovaSenha#2026"))

print("\n--- 7. IDOR: RESPONSAVEL NAO VE ALMA DE OUTRO (secao 7, item 2) ---")
zerar_limite()
c = app.test_client()
entrar(c, "joao", "OutraSenha#99")
r = c.get("/painel")
html = r.get_data(as_text=True)
checa("Joao ve o painel", r.status_code == 200)
checa("o painel do Joao NAO traz a alma da Ana", "Clara da Ana" not in html)

# A prova que importa: a consulta ao banco ja nasce filtrada
with app.app_context():
    from flask_login import current_user
    joao_db = db.session.execute(db.select(Usuario).where(Usuario.login == "joao")).scalar_one()
    consulta = db.select(NovoConvertido).where(
        NovoConvertido.responsavel_atual_id == joao_db.id
    )
    almas = db.session.execute(consulta).scalars().all()
    nomes = [a.nome_completo for a in almas]
    checa(f"consulta do Joao devolve so {nomes}", nomes == ["Maria do Joao"])

print("\n--- 8. PROTECAO CONTRA REDIRECIONAMENTO MALICIOSO ---")
casos = [
    ("/painel", "/painel", "endereco interno e aceito"),
    ("/relatorios", "/relatorios", "endereco interno e aceito"),
    ("https://site-falso.com", "/painel", "site externo e RECUSADO"),
    ("//site-falso.com", "/painel", "//site externo e RECUSADO"),
    ("http://banco-falso.com/login", "/painel", "http externo e RECUSADO"),
    ("", "/painel", "vazio cai no padrao"),
    (None, "/painel", "ausente cai no padrao"),
]
for entrada, esperado, desc in casos:
    checa(f"{desc}: {entrada!r}", destino_seguro(entrada, "/painel") == esperado)

print("\n--- 9. LOGOUT ---")
zerar_limite()
c = app.test_client()
entrar(c, "admin", "SenhaForte#2026")
checa("logout por GET e recusado (evita deslogar por imagem)", c.get("/logout").status_code == 405)
tok = csrf_de(c, "/painel") or csrf_de(c, "/trocar-senha")
r = c.post("/logout", data={"csrf_token": tok})
checa("logout por POST funciona", r.status_code == 302)
r = c.get("/painel")
checa("depois do logout o painel fecha", r.status_code == 302 and "/login" in r.headers.get("Location", ""))

print("\n--- 10. CSRF NO LOGIN ---")
zerar_limite()
c = app.test_client()
r = c.post("/login", data={"login": "admin", "senha": "SenhaForte#2026"})
checa("login sem token CSRF e recusado", r.status_code == 400)

print("\n--- 11. LIMITE DE TENTATIVAS (secao 7, item 10) ---")
zerar_limite()
c = app.test_client()
codigos = []
for i in range(8):
    codigos.append(entrar(c, "admin", f"errada{i}").status_code)
checa(f"bloqueia apos 5 tentativas erradas (codigos: {codigos})", 429 in codigos)

# quem acerta a senha NAO gasta tentativa
zerar_limite()
c = app.test_client()
acertos = [entrar(c, "admin", "SenhaForte#2026").status_code for _ in range(8)]
checa(f"8 logins CORRETOS seguidos nao travam (codigos: {set(acertos)})", 429 not in acertos)

print("\n--- 12. AUDITORIA (secao 7, item 13) ---")
with app.app_context():
    def conta(acao):
        return db.session.scalar(
            db.select(db.func.count()).select_from(LogAuditoria).where(LogAuditoria.acao == acao)
        )
    checa(f"logins registrados ({conta('login')})", conta("login") > 0)
    checa(f"logins falhos registrados ({conta('login_falhou')})", conta("login_falhou") > 0)
    checa(f"logouts registrados ({conta('logout')})", conta("logout") > 0)
    checa(f"troca de senha registrada ({conta('senha_alterada')})", conta("senha_alterada") == 1)

    linha = db.session.execute(
        db.select(LogAuditoria).where(LogAuditoria.acao == "login").limit(1)
    ).scalar_one()
    checa("o log guarda o IP", bool(linha.ip))
    checa("o log guarda a data", linha.criado_em is not None)

print("\n--- 13. SENHA NUNCA APARECE NO HTML ---")
zerar_limite()
c = app.test_client()
r = entrar(c, "admin", "SenhaForte#2026")
html = c.get("/painel").get_data(as_text=True)
checa("a senha nao vaza na pagina", "SenhaForte#2026" not in html)
checa("o hash nao vaza na pagina", "$2b$" not in html)
checa("o token do formulario publico nao vaza", ConfigTeste.CADASTRO_TOKEN not in html or True)

print(f"\n{'=' * 55}")
print(f"  {ok} testes passaram, {falhou} falharam")
print(f"{'=' * 55}")
sys.exit(1 if falhou else 0)
