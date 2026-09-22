# -*- coding: utf-8 -*-
"""Testes das telas de Responsaveis e Eventos (Etapa 7). Banco em memoria."""
import os
import sys, re
from datetime import timedelta

# O caminho do projeto vem do PROPRIO arquivo, nao escrito a mao. Assim os
# testes funcionam em qualquer computador e tambem no servidor.
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.stdout.reconfigure(encoding="utf-8")

from config import DevelopmentConfig
from app import create_app
from app.extensions import db, limiter
from app.models import Usuario, NovoConvertido, Contato, Evento, Presenca, LogAuditoria
from app.tempo import agora, hoje
from app import opcoes


class ConfigTeste(DevelopmentConfig):
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = True
    CADASTRO_TOKEN = "t"


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
    admin = Usuario(nome="Carlos Admin", login="admin", papel="admin", ativo=True, deve_trocar_senha=False)
    admin.definir_senha("SenhaForte#2026")
    admin2 = Usuario(nome="Outro Admin", login="admin2", papel="admin", ativo=True, deve_trocar_senha=False)
    admin2.definir_senha("SegundaSenha#77")
    joao = Usuario(nome="Joao Pereira", login="joao", papel="responsavel", ativo=True, deve_trocar_senha=False)
    joao.definir_senha("OutraSenha#99")
    db.session.add_all([admin, admin2, joao])
    db.session.flush()
    ID_ADMIN, ID_ADMIN2, ID_JOAO = admin.id, admin2.id, joao.id

    def criar(nome, dias_contato=None):
        a = NovoConvertido(
            nome_completo=nome, telefone="16992805852", sexo="F",
            data_nascimento=hoje().replace(year=hoje().year - 30),
            trabalho="culto_dominical", departamento="preciosas", data_conversao=hoje(),
            cadastrante_nome="T", cadastrante_telefone="16988887777",
            consentimento_em=agora(), consentimento_ip="127.0.0.1",
            status_ciclo=opcoes.STATUS_ATIVO, responsavel_atual_id=ID_JOAO,
            designado_em=agora() - timedelta(days=40), criado_em=agora() - timedelta(days=40),
        )
        db.session.add(a)
        db.session.flush()
        if dias_contato is not None:
            db.session.add(Contato(
                convertido_id=a.id, responsavel_id=ID_JOAO, tipo="telefone",
                data_hora=agora() - timedelta(days=dias_contato), resultado="efetivo",
                relato="t", criado_em=agora() - timedelta(days=dias_contato)))
        return a

    criar("Verde Um", 1)
    criar("Verde Dois", 2)
    criar("Vermelha Um", 30)
    criar("Vermelha Dois", 40)

    ev_passado = Evento(nome="Culto Dominical", tipo="culto_dominical",
                        data=hoje() - timedelta(days=7), ativo=True, recorrente=True)
    db.session.add(ev_passado)
    db.session.flush()
    ID_EV = ev_passado.id
    db.session.commit()


def entrar(login, senha):
    with app.app_context():
        limiter.reset()
    c = app.test_client()
    h = c.get("/login").get_data(as_text=True)
    tok = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', h).group(1)
    c.post("/login", data={"login": login, "senha": senha, "csrf_token": tok})
    return c


def tok_de(c, url="/responsaveis"):
    h = c.get(url).get_data(as_text=True)
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', h)
    return m.group(1) if m else ""


print("\n--- 1. SO ADMIN ENTRA EM /responsaveis (secao 7, item 2) ---")
cj = entrar("joao", "OutraSenha#99")
r = cj.get("/responsaveis")
checa(f"responsavel recebe 403 (deu {r.status_code})", r.status_code == 403)
r = cj.post("/responsaveis/criar", data={"csrf_token": tok_de(cj, "/eventos"),
                                         "nome": "Invasor Silva", "login": "invasor", "papel": "admin"})
checa(f"responsavel nao cria usuario (deu {r.status_code})", r.status_code == 403)
with app.app_context():
    n = db.session.scalar(db.select(db.func.count()).select_from(Usuario)
                          .where(Usuario.login == "invasor"))
    checa("nenhum usuario foi criado", n == 0)
    negados = db.session.scalar(db.select(db.func.count()).select_from(LogAuditoria)
                                .where(LogAuditoria.acao == "acesso_negado"))
    checa("tentativas registradas na auditoria", negados >= 2)

print("\n--- 2. A TABELA DE CARGA ---")
ca = entrar("admin", "SenhaForte#2026")
h = ca.get("/responsaveis").get_data(as_text=True)
checa("a tela abre", "Responsáveis" in h)
checa("mostra o Joao", "Joao Pereira" in h)

from app.rotas.responsaveis import calcular_carga
with app.app_context():
    carga = calcular_carga()
    linha_joao = next(c for c in carga if c["usuario"].id == ID_JOAO)
    checa(f"Joao tem 4 almas (deu {linha_joao['almas']})", linha_joao["almas"] == 4)
    checa(f"2 no verde (deu {linha_joao['verde']})", linha_joao["verde"] == 2)
    checa(f"2 criticas (deu {linha_joao['criticas']})", linha_joao["criticas"] == 2)
    checa(f"50% em dia (deu {linha_joao['percentual']}%)", linha_joao["percentual"] == 50)
    linha_admin = next(c for c in carga if c["usuario"].id == ID_ADMIN)
    checa("admin sem almas mostra percentual vazio", linha_admin["percentual"] is None)

print("\n--- 3. CRIAR USUARIO E SORTEAR SENHA ---")
r = ca.post("/responsaveis/criar", data={
    "csrf_token": tok_de(ca), "nome": "Maria Souza Lima",
    "login": "maria.souza", "telefone": "(16) 99280-5852", "papel": "responsavel"})
checa("criacao aceita", r.status_code == 302)
destino = r.headers.get("Location", "")
checa("a senha volta na URL para ser mostrada", "senha=" in destino)

senha_sorteada = re.search(r"senha=([^&]+)", destino).group(1)
checa(f"senha tem 10 caracteres (deu {len(senha_sorteada)})", len(senha_sorteada) == 10)
checa("sem caracteres confusos (0 O 1 l I)",
      not any(x in senha_sorteada for x in "0O1lI"))

with app.app_context():
    m = db.session.execute(db.select(Usuario).where(Usuario.login == "maria.souza")).scalar_one()
    checa("o usuario existe", m is not None)
    checa("a senha sorteada funciona", m.conferir_senha(senha_sorteada))
    checa("a senha NAO esta em texto puro no banco", senha_sorteada not in (m.senha_hash or ""))
    checa("hash e bcrypt", m.senha_hash.startswith("$2b$"))
    checa("tera de trocar no primeiro login", m.deve_trocar_senha is True)
    checa("telefone normalizado", m.telefone == "16992805852")
    checa("papel correto", m.papel == "responsavel")
    n = db.session.scalar(db.select(db.func.count()).select_from(LogAuditoria)
                          .where(LogAuditoria.acao == "usuario_criado"))
    checa("criacao auditada", n == 1)

print("\n--- 4. DUAS SENHAS SORTEADAS SAO DIFERENTES ---")
from app.rotas.responsaveis import sortear_senha
senhas = {sortear_senha() for _ in range(50)}
checa(f"50 sorteios deram 50 senhas distintas ({len(senhas)})", len(senhas) == 50)

print("\n--- 5. LOGIN INVALIDO OU REPETIDO ---")
casos = [
    ("login repetido", {"nome": "Outra Pessoa Silva", "login": "maria.souza", "papel": "responsavel"}),
    ("login com espaco", {"nome": "Outra Pessoa Silva", "login": "maria souza", "papel": "responsavel"}),
    ("login com acento", {"nome": "Outra Pessoa Silva", "login": "joão", "papel": "responsavel"}),
    ("login curto demais", {"nome": "Outra Pessoa Silva", "login": "ab", "papel": "responsavel"}),
    ("nome sem sobrenome", {"nome": "Maria", "login": "maria2", "papel": "responsavel"}),
    ("papel inventado", {"nome": "Outra Pessoa Silva", "login": "outra", "papel": "super_admin"}),
]
for desc, dados in casos:
    with app.app_context():
        antes = db.session.scalar(db.select(db.func.count()).select_from(Usuario))
    dados["csrf_token"] = tok_de(ca)
    ca.post("/responsaveis/criar", data=dados)
    with app.app_context():
        depois = db.session.scalar(db.select(db.func.count()).select_from(Usuario))
    checa(f"recusa: {desc}", antes == depois)

print("\n--- 6. ATIVAR E DESATIVAR ---")
r = ca.post(f"/responsaveis/{ID_JOAO}/ativar", data={"csrf_token": tok_de(ca)})
with app.app_context():
    j = db.session.get(Usuario, ID_JOAO)
    checa("Joao foi desativado", j.ativo is False)
cj2 = entrar("joao", "OutraSenha#99")
r = cj2.get("/painel")
checa("desativado nao entra mais", r.status_code == 302)

ca.post(f"/responsaveis/{ID_JOAO}/ativar", data={"csrf_token": tok_de(ca)})
with app.app_context():
    j = db.session.get(Usuario, ID_JOAO)
    checa("Joao foi reativado", j.ativo is True)
    n = db.session.scalar(db.select(db.func.count()).select_from(LogAuditoria)
                          .where(LogAuditoria.acao.in_(["usuario_desativado", "usuario_reativado"])))
    checa("as duas acoes foram auditadas", n == 2)

print("\n--- 7. TRAVAS DE SEGURANCA DO DESATIVAR ---")
r = ca.post(f"/responsaveis/{ID_ADMIN}/ativar", data={"csrf_token": tok_de(ca)})
with app.app_context():
    a = db.session.get(Usuario, ID_ADMIN)
    checa("nao da para desativar a si mesmo", a.ativo is True)

# deixa so um admin e tenta desativa-lo
ca.post(f"/responsaveis/{ID_ADMIN2}/ativar", data={"csrf_token": tok_de(ca)})
with app.app_context():
    a2 = db.session.get(Usuario, ID_ADMIN2)
    checa("o segundo admin foi desativado", a2.ativo is False)

c2 = entrar("admin", "SenhaForte#2026")
r = c2.post(f"/responsaveis/{ID_ADMIN}/ativar", data={"csrf_token": tok_de(c2)})
with app.app_context():
    a = db.session.get(Usuario, ID_ADMIN)
    checa("o unico admin ativo nao pode se desativar", a.ativo is True)

ca.post(f"/responsaveis/{ID_ADMIN2}/ativar", data={"csrf_token": tok_de(ca)})   # reativa

print("\n--- 8. REDEFINIR SENHA ---")
with app.app_context():
    hash_antigo = db.session.execute(
        db.select(Usuario).where(Usuario.login == "maria.souza")).scalar_one().senha_hash

r = ca.post(f"/responsaveis/{ID_JOAO}/senha", data={"csrf_token": tok_de(ca)})
checa("redefinicao aceita", r.status_code == 302)
nova = re.search(r"senha=([^&]+)", r.headers.get("Location", "")).group(1)
with app.app_context():
    j = db.session.get(Usuario, ID_JOAO)
    checa("a senha nova funciona", j.conferir_senha(nova))
    checa("a senha antiga nao funciona mais", not j.conferir_senha("OutraSenha#99"))
    checa("tera de trocar no proximo login", j.deve_trocar_senha is True)
    n = db.session.scalar(db.select(db.func.count()).select_from(LogAuditoria)
                          .where(LogAuditoria.acao == "senha_redefinida"))
    checa("redefinicao auditada", n == 1)

print("\n--- 9. EVENTOS: QUEM VE O QUE (secao 5.5) ---")
cj3 = entrar("joao", nova)
# Joao precisa trocar a senha antes; trocamos para seguir o teste
tokt = re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                 cj3.get("/trocar-senha").get_data(as_text=True)).group(1)
cj3.post("/trocar-senha", data={"senha_atual": nova, "senha_nova": "JoaoNovo#2026",
                                "senha_confirmacao": "JoaoNovo#2026", "csrf_token": tokt})
r = cj3.get("/eventos")
checa("responsavel VE a agenda", r.status_code == 200)
h = r.get_data(as_text=True)
checa("mas NAO ve o botao de cadastrar", "Novo evento" not in h)
checa("nem o de gerar agenda", "Gerar agenda" not in h)

r = cj3.post("/eventos/criar", data={"csrf_token": tok_de(cj3, "/eventos"),
                                     "nome": "Evento Pirata", "tipo": "outro",
                                     "data": hoje().isoformat()})
checa(f"responsavel recebe 403 ao criar evento (deu {r.status_code})", r.status_code == 403)
with app.app_context():
    n = db.session.scalar(db.select(db.func.count()).select_from(Evento)
                          .where(Evento.nome == "Evento Pirata"))
    checa("o evento nao foi criado", n == 0)

print("\n--- 10. EVENTOS: O ADMIN CADASTRA ---")
r = ca.post("/eventos/criar", data={
    "csrf_token": tok_de(ca, "/eventos"), "nome": "Vigília de Oração",
    "tipo": "outro", "data": (hoje() + timedelta(days=10)).isoformat()})
checa("cadastro aceito", r.status_code == 302)
with app.app_context():
    e = db.session.execute(db.select(Evento).where(Evento.nome == "Vigília de Oração")).scalar_one_or_none()
    checa("o evento existe", e is not None)
    checa("marcado como NAO recorrente", e.recorrente is False)
    checa("registrou quem criou", e.criado_por_id == ID_ADMIN)

# repetido na mesma data e tipo
r = ca.post("/eventos/criar", data={
    "csrf_token": tok_de(ca, "/eventos"), "nome": "Outra Vigília",
    "tipo": "outro", "data": (hoje() + timedelta(days=10)).isoformat()})
with app.app_context():
    n = db.session.scalar(db.select(db.func.count()).select_from(Evento)
                          .where(Evento.nome == "Outra Vigília"))
    checa("recusa evento repetido (mesmo tipo e data)", n == 0)

casos_data = [
    ("data muito antiga", (hoje() - timedelta(days=400)).isoformat()),
    ("data muito distante", (hoje() + timedelta(days=800)).isoformat()),
]
for desc, data in casos_data:
    with app.app_context():
        antes = db.session.scalar(db.select(db.func.count()).select_from(Evento))
    ca.post("/eventos/criar", data={"csrf_token": tok_de(ca, "/eventos"),
                                    "nome": "Teste Data", "tipo": "culto_ceia", "data": data})
    with app.app_context():
        depois = db.session.scalar(db.select(db.func.count()).select_from(Evento))
    checa(f"recusa: {desc}", antes == depois)

print("\n--- 11. CANCELAR EVENTO PRESERVA AS PRESENCAS ---")
with app.app_context():
    alma = db.session.execute(db.select(NovoConvertido)).scalars().first()
    db.session.add(Presenca(convertido_id=alma.id, evento_id=ID_EV,
                            presente=True, registrado_por_id=ID_ADMIN))
    db.session.commit()

r = ca.post(f"/eventos/{ID_EV}/cancelar", data={"csrf_token": tok_de(ca, "/eventos")})
with app.app_context():
    e = db.session.get(Evento, ID_EV)
    checa("o evento foi cancelado", e.ativo is False)
    checa("mas NAO foi apagado", e is not None)
    n = db.session.scalar(db.select(db.func.count()).select_from(Presenca)
                          .where(Presenca.evento_id == ID_EV))
    checa("a presenca continua no historico", n == 1)

print("\n--- 12. GERAR AGENDA ---")
with app.app_context():
    antes = db.session.scalar(db.select(db.func.count()).select_from(Evento))
ca.post("/eventos/gerar-agenda", data={"csrf_token": tok_de(ca, "/eventos")})
with app.app_context():
    depois = db.session.scalar(db.select(db.func.count()).select_from(Evento))
checa(f"gerou os cultos recorrentes ({depois - antes} novos)", depois > antes)

ca.post("/eventos/gerar-agenda", data={"csrf_token": tok_de(ca, "/eventos")})
with app.app_context():
    terceiro = db.session.scalar(db.select(db.func.count()).select_from(Evento))
checa("rodar de novo nao duplica nada", terceiro == depois)

with app.app_context():
    domingos = db.session.execute(db.select(Evento).where(
        Evento.tipo == "culto_dominical", Evento.data >= hoje())).scalars().all()
    checa("todo culto dominical cai num domingo",
          all(e.data.weekday() == 6 for e in domingos))

print("\n--- 13. CSRF NAS ACOES ---")
r = ca.post("/responsaveis/criar", data={"nome": "Sem Token Silva", "login": "semtoken",
                                         "papel": "responsavel"})
checa(f"criar usuario sem token e recusado (deu {r.status_code})", r.status_code == 400)
r = ca.post("/eventos/criar", data={"nome": "Sem Token", "tipo": "outro",
                                    "data": hoje().isoformat()})
checa(f"criar evento sem token e recusado (deu {r.status_code})", r.status_code == 400)

print(f"\n{'=' * 55}")
print(f"  {ok} testes passaram, {falhou} falharam")
print(f"{'=' * 55}")
sys.exit(1 if falhou else 0)
