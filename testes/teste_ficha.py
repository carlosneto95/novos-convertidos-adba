# -*- coding: utf-8 -*-
"""Testes da ficha lateral (drawer). Banco em memoria."""
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
from app.models import Usuario, NovoConvertido, Contato, Atribuicao, Evento, Presenca, LogAuditoria
from app.tempo import agora, hoje
from app import opcoes


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

    admin = Usuario(nome="Carlos Admin", login="admin", papel="admin", ativo=True, deve_trocar_senha=False)
    admin.definir_senha("SenhaForte#2026")
    joao = Usuario(nome="Joao Pereira", login="joao", papel="responsavel", ativo=True, deve_trocar_senha=False)
    joao.definir_senha("OutraSenha#99")
    ana = Usuario(nome="Ana Lima", login="ana", papel="responsavel", ativo=True, deve_trocar_senha=False)
    ana.definir_senha("MaisUma#777")
    db.session.add_all([admin, joao, ana])
    db.session.flush()
    ID_JOAO, ID_ANA, ID_ADMIN = joao.id, ana.id, admin.id

    def criar(nome, resp_id, dias=30):
        return NovoConvertido(
            nome_completo=nome, telefone="16992805852", sexo="F",
            data_nascimento=hoje().replace(year=hoje().year - 30),
            trabalho="culto_dominical", departamento="preciosas", data_conversao=hoje(),
            cadastrante_nome="Irma Ana", cadastrante_telefone="16988887777",
            consentimento_em=agora(), consentimento_ip="127.0.0.1",
            status_ciclo=opcoes.STATUS_ATIVO, responsavel_atual_id=resp_id,
            designado_em=agora() - timedelta(days=dias),
            criado_em=agora() - timedelta(days=dias),
            observacao_sensivel="Situacao familiar delicada. NAO DIVULGAR.",
        )

    do_joao = criar("Alma do Joao", ID_JOAO)
    da_ana = criar("Alma da Ana", ID_ANA)
    db.session.add_all([do_joao, da_ana])
    db.session.flush()
    ID_DO_JOAO, ID_DA_ANA = do_joao.id, da_ana.id

    # 3 contatos na alma do Joao
    for dias, resultado, relato in [
        (10, "efetivo", "Conversamos por telefone, ela esta bem."),
        (5, "sem_resposta", "Liguei duas vezes, nao atendeu."),
        (2, "efetivo", "Visita na casa dela, recebeu bem."),
    ]:
        db.session.add(Contato(
            convertido_id=do_joao.id, responsavel_id=ID_JOAO, tipo="telefone",
            data_hora=agora() - timedelta(days=dias), resultado=resultado,
            relato=relato, criado_em=agora() - timedelta(days=dias),
        ))

    # 2 cultos recentes, com 1 presenca e 1 falta
    e1 = Evento(nome="Culto Dominical", tipo="culto_dominical", data=hoje() - timedelta(days=7), ativo=True)
    e2 = Evento(nome="Culto de Ensino", tipo="culto_ensino", data=hoje() - timedelta(days=3), ativo=True)
    e3 = Evento(nome="Culto Antigo", tipo="culto_dominical", data=hoje() - timedelta(days=200), ativo=True)
    db.session.add_all([e1, e2, e3])
    db.session.flush()
    db.session.add(Presenca(convertido_id=do_joao.id, evento_id=e1.id, presente=True, registrado_por_id=ID_JOAO))
    db.session.add(Presenca(convertido_id=do_joao.id, evento_id=e2.id, presente=False, registrado_por_id=ID_JOAO))

    db.session.add(Atribuicao(convertido_id=do_joao.id, responsavel_id=ID_ANA,
                              inicio=agora() - timedelta(days=60), fim=agora() - timedelta(days=30),
                              motivo="Ana saiu de ferias", atribuido_por_id=ID_ADMIN))
    db.session.add(Atribuicao(convertido_id=do_joao.id, responsavel_id=ID_JOAO,
                              inicio=agora() - timedelta(days=30), motivo="Assumiu o acompanhamento",
                              atribuido_por_id=ID_ADMIN))
    db.session.commit()


def entrar(login, senha):
    with app.app_context():
        limiter.reset()
    c = app.test_client()
    html = c.get("/login").get_data(as_text=True)
    tok = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
    c.post("/login", data={"login": login, "senha": senha, "csrf_token": tok})
    return c


print("\n--- 1. A FICHA ABRE ---")
c_joao = entrar("joao", "OutraSenha#99")
r = c_joao.get(f"/alma/{ID_DO_JOAO}/ficha")
checa("Joao abre a ficha da alma dele", r.status_code == 200)
h = r.get_data(as_text=True)
checa("mostra as 4 abas", all(a in h for a in ["Dados", "Contatos", "Presenças", "Histórico"]))

print("\n--- 2. OS CONTATOS APARECEM (o pedido principal) ---")
checa("contato 1 aparece", "Conversamos por telefone" in h)
checa("contato 2 aparece", "Liguei duas vezes" in h)
checa("contato 3 aparece", "Visita na casa dela" in h)
checa("mostra o resultado de cada um", "Sem resposta" in h)
checa("mostra quem registrou", "Joao Pereira" in h)

print("\n--- 3. AS PRESENCAS APARECEM ---")
checa("culto com presenca aparece", "Culto Dominical" in h)
checa("culto com falta aparece", "Culto de Ensino" in h)
checa("culto de 200 dias atras NAO aparece (fora da janela)", "Culto Antigo" not in h)
checa("conta 1 presenca", "1 presença" in h)
checa("mostra 'faltou'", "faltou" in h)

print("\n--- 4. O HISTORICO DE RESPONSAVEIS ---")
checa("responsavel anterior aparece", "Ana Lima" in h)
checa("motivo da troca aparece", "Ana saiu de ferias" in h)
checa("marca qual e o atual", "atual" in h)

print("\n--- 5. TELEFONE FORMATADO ---")
checa("telefone sai bonito, nao cru", "(16) 99280-5852" in h)
checa("nao mostra o telefone sem formatacao", ">16992805852<" not in h)

print("\n--- 6. IDOR: FICHA DE OUTRO RESPONSAVEL (secao 7, item 2) ---")
r = c_joao.get(f"/alma/{ID_DA_ANA}/ficha")
checa(f"Joao recebe 403 na ficha da Ana (deu {r.status_code})", r.status_code == 403)
checa("nao vaza o nome da alma", "Alma da Ana" not in r.get_data(as_text=True))
with app.app_context():
    n = db.session.scalar(db.select(db.func.count()).select_from(LogAuditoria)
                          .where(LogAuditoria.acao == "acesso_negado"))
    checa("tentativa registrada na auditoria", n >= 1)

print("\n--- 7. UUID INVENTADO ---")
r = c_joao.get("/alma/3f2a91c4-8d7e-4b1a-9c33-000000000000/ficha")
checa(f"UUID inexistente devolve 404 (deu {r.status_code})", r.status_code == 404)

print("\n--- 8. SEM LOGIN ---")
c_anon = app.test_client()
r = c_anon.get(f"/alma/{ID_DO_JOAO}/ficha")
checa("sem login e barrado", r.status_code in (302, 401, 403))
if r.status_code == 302:
    checa("manda para o login", "/login" in r.headers.get("Location", ""))

print("\n--- 9. OBSERVACAO SENSIVEL (secao 7, item 11) ---")
h_joao = c_joao.get(f"/alma/{ID_DO_JOAO}/ficha").get_data(as_text=True)
checa("responsavel ATUAL ve a observacao sensivel", "NAO DIVULGAR" in h_joao)

c_admin = entrar("admin", "SenhaForte#2026")
h_admin = c_admin.get(f"/alma/{ID_DO_JOAO}/ficha").get_data(as_text=True)
checa("Admin tambem ve", "NAO DIVULGAR" in h_admin)

c_ana = entrar("ana", "MaisUma#777")
r = c_ana.get(f"/alma/{ID_DO_JOAO}/ficha")
checa(f"ex-responsavel (Ana) NAO abre a ficha (deu {r.status_code})", r.status_code == 403)
checa("e nao ve a observacao", "NAO DIVULGAR" not in r.get_data(as_text=True))

with app.app_context():
    n = db.session.scalar(db.select(db.func.count()).select_from(LogAuditoria)
                          .where(LogAuditoria.acao == "leitura_observacao_sensivel"))
    checa(f"toda leitura foi auditada ({n} registros)", n >= 2)

print("\n--- 10. XSS NO RELATO (secao 7, item 5) ---")
with app.app_context():
    alma = db.session.get(NovoConvertido, ID_DO_JOAO)
    db.session.add(Contato(
        convertido_id=alma.id, responsavel_id=ID_JOAO, tipo="whatsapp",
        data_hora=agora(), resultado="efetivo",
        relato="<script>alert('invadi')</script> tentativa de ataque",
        criado_em=agora(),
    ))
    db.session.commit()
h = c_joao.get(f"/alma/{ID_DO_JOAO}/ficha").get_data(as_text=True)
checa("script NAO aparece executavel", "<script>alert('invadi')</script>" not in h)
checa("mas o texto aparece escapado", "&lt;script&gt;" in h)

print(f"\n{'=' * 55}")
print(f"  {ok} testes passaram, {falhou} falharam")
print(f"{'=' * 55}")
sys.exit(1 if falhou else 0)
