# -*- coding: utf-8 -*-
"""Testes das acoes da ficha (Etapa 6). Banco em memoria."""
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
from app.tempo import agora, hoje, para_local, FUSO_BRASIL
from app import opcoes, semaforo as sem


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
    joao = Usuario(nome="Joao Pereira", login="joao", papel="responsavel", ativo=True, deve_trocar_senha=False)
    joao.definir_senha("OutraSenha#99")
    ana = Usuario(nome="Ana Lima", login="ana", papel="responsavel", ativo=True, deve_trocar_senha=False)
    ana.definir_senha("MaisUma#777")
    db.session.add_all([admin, joao, ana])
    db.session.flush()
    ID_ADMIN, ID_JOAO, ID_ANA = admin.id, joao.id, ana.id

    def criar(nome, resp, dias=30):
        return NovoConvertido(
            nome_completo=nome, telefone="16992805852", sexo="F",
            data_nascimento=hoje().replace(year=hoje().year - 30),
            trabalho="culto_dominical", departamento="preciosas", data_conversao=hoje(),
            cadastrante_nome="Teste", cadastrante_telefone="16988887777",
            consentimento_em=agora(), consentimento_ip="127.0.0.1",
            status_ciclo=opcoes.STATUS_ATIVO, responsavel_atual_id=resp,
            designado_em=agora() - timedelta(days=dias), criado_em=agora() - timedelta(days=dias),
            observacao_sensivel="Informacao intima. NAO DIVULGAR.",
        )

    a1 = criar("Alma Um", ID_JOAO)
    a2 = criar("Alma Dois", ID_JOAO)
    a3 = criar("Alma Tres", ID_JOAO)
    a4 = criar("Alma da Ana", ID_ANA)
    db.session.add_all([a1, a2, a3, a4])
    db.session.flush()

    ev = Evento(nome="Culto Dominical", tipo="culto_dominical", data=hoje() - timedelta(days=3), ativo=True)
    ev_antigo = Evento(nome="Culto Antigo", tipo="culto_ceia", data=hoje() - timedelta(days=300), ativo=True)
    db.session.add_all([ev, ev_antigo])
    db.session.flush()

    db.session.add(Atribuicao(convertido_id=a1.id, responsavel_id=ID_JOAO,
                              inicio=agora() - timedelta(days=30)))
    db.session.commit()
    ID1, ID2, ID3, ID_ANA_ALMA = a1.id, a2.id, a3.id, a4.id
    ID_EV, ID_EV_ANTIGO = ev.id, ev_antigo.id


def entrar(login, senha):
    with app.app_context():
        limiter.reset()
    c = app.test_client()
    h = c.get("/login").get_data(as_text=True)
    tok = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', h).group(1)
    c.post("/login", data={"login": login, "senha": senha, "csrf_token": tok})
    return c


def csrf(c, alma_id):
    h = c.get(f"/alma/{alma_id}/ficha").get_data(as_text=True)
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', h)
    return m.group(1) if m else ""


def semaforo_de(alma_id):
    from app.rotas.painel import mapas_de_contato
    with app.app_context():
        a = db.session.get(NovoConvertido, alma_id)
        t, e = mapas_de_contato([a.id])
        return sem.calcular(a, t.get(a.id), e.get(a.id))


AGORA_LOCAL = para_local(agora()).strftime("%Y-%m-%dT%H:%M")

print("\n--- 1. REGISTRAR CONTATO ---")
c = entrar("joao", "OutraSenha#99")
antes = semaforo_de(ID1)
checa(f"antes: {antes.cor} com {antes.dias} dias", antes.cor == "vermelho")

r = c.post(f"/alma/{ID1}/contato", data={
    "csrf_token": csrf(c, ID1), "tipo": "telefone", "data_hora": AGORA_LOCAL,
    "resultado": "efetivo", "relato": "Conversamos, ela esta bem e vem domingo.",
})
checa("contato aceito (redireciona)", r.status_code == 302)
checa("volta com a ficha aberta", f"ficha={ID1}" in r.headers.get("Location", ""))

depois = semaforo_de(ID1)
checa(f"o semaforo virou {depois.cor} (era {antes.cor})", depois.cor == "verde")
checa("os dois relogios zeraram", depois.dias == 0)
checa("sumiu o icone de alerta", depois.icone is None)

with app.app_context():
    ct = db.session.execute(db.select(Contato).where(Contato.convertido_id == ID1)).scalars().all()
    checa("o contato foi gravado", len(ct) == 1)
    checa("o relato foi gravado", "ela esta bem" in ct[0].relato)
    checa("registrou quem fez", ct[0].responsavel_id == ID_JOAO)
    n = db.session.scalar(db.select(db.func.count()).select_from(LogAuditoria)
                          .where(LogAuditoria.acao == "contato_registrado"))
    checa("foi para a auditoria", n == 1)

print("\n--- 2. CONTATO SEM RESPOSTA ZERA SO UM RELOGIO ---")
r = c.post(f"/alma/{ID2}/contato", data={
    "csrf_token": csrf(c, ID2), "tipo": "whatsapp", "data_hora": AGORA_LOCAL,
    "resultado": "sem_resposta", "relato": "Mandei mensagem, nao respondeu.",
})
s = semaforo_de(ID2)
checa("relogio da tentativa zerou", s.dias_tentativa == 0)
checa(f"relogio do efetivo continua ({s.dias_efetivo} dias)", s.dias_efetivo == 30)
checa("icone diz 'a alma nao responde'", s.icone == "sem-resposta")

print("\n--- 3. CONTATO RECUSADO ---")
casos = [
    ("relato vazio", {"tipo": "telefone", "data_hora": AGORA_LOCAL, "resultado": "efetivo", "relato": ""}),
    ("sem tipo", {"data_hora": AGORA_LOCAL, "resultado": "efetivo", "relato": "teste ok"}),
    ("sem resultado", {"tipo": "telefone", "data_hora": AGORA_LOCAL, "relato": "teste ok"}),
    ("tipo inventado", {"tipo": "pombo_correio", "data_hora": AGORA_LOCAL, "resultado": "efetivo", "relato": "teste ok"}),
    ("data no futuro", {"tipo": "telefone", "resultado": "efetivo", "relato": "teste ok",
                        "data_hora": (para_local(agora()) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")}),
]
for desc, dados in casos:
    with app.app_context():
        n_antes = db.session.scalar(db.select(db.func.count()).select_from(Contato)
                                    .where(Contato.convertido_id == ID3))
    dados["csrf_token"] = csrf(c, ID3)
    c.post(f"/alma/{ID3}/contato", data=dados)
    with app.app_context():
        n_depois = db.session.scalar(db.select(db.func.count()).select_from(Contato)
                                     .where(Contato.convertido_id == ID3))
    checa(f"recusa: {desc}", n_antes == n_depois)

print("\n--- 4. MARCAR PRESENCA ---")
r = c.post(f"/alma/{ID1}/presenca", data={
    "csrf_token": csrf(c, ID1), "evento_id": ID_EV, "presente": "sim"})
checa("presenca aceita", r.status_code == 302)
with app.app_context():
    p = db.session.execute(db.select(Presenca).where(
        Presenca.convertido_id == ID1, Presenca.evento_id == ID_EV)).scalar_one_or_none()
    checa("gravou a presenca", p is not None and p.presente is True)
    checa("registrou quem marcou", p.registrado_por_id == ID_JOAO)

# marcar de novo deve ATUALIZAR, nao quebrar
r = c.post(f"/alma/{ID1}/presenca", data={
    "csrf_token": csrf(c, ID1), "evento_id": ID_EV, "presente": "nao"})
checa("marcar de novo nao quebra", r.status_code == 302)
with app.app_context():
    p = db.session.execute(db.select(Presenca).where(
        Presenca.convertido_id == ID1, Presenca.evento_id == ID_EV)).scalar_one()
    checa("a marcacao foi ATUALIZADA para falta", p.presente is False)
    n = db.session.scalar(db.select(db.func.count()).select_from(Presenca)
                          .where(Presenca.convertido_id == ID1))
    checa("continua tendo so 1 linha (sem duplicar)", n == 1)

r = c.post(f"/alma/{ID1}/presenca", data={
    "csrf_token": csrf(c, ID1), "evento_id": ID_EV_ANTIGO, "presente": "sim"})
with app.app_context():
    p = db.session.execute(db.select(Presenca).where(
        Presenca.convertido_id == ID1, Presenca.evento_id == ID_EV_ANTIGO)).scalar_one_or_none()
    checa("recusa culto fora da janela de 60 dias", p is None)

print("\n--- 5. ALTERAR STATUS ---")
antes_n = semaforo_de(ID1).cor
r = c.post(f"/alma/{ID1}/status", data={
    "csrf_token": csrf(c, ID1), "status_ciclo": "integrado", "justificativa": ""})
with app.app_context():
    a = db.session.get(NovoConvertido, ID1)
    checa("recusa encerrar SEM justificativa", a.status_ciclo == opcoes.STATUS_ATIVO)

r = c.post(f"/alma/{ID1}/status", data={
    "csrf_token": csrf(c, ID1), "status_ciclo": "integrado",
    "justificativa": "Foi batizada e ja participa do grupo de jovens."})
checa("aceita com justificativa", r.status_code == 302)
with app.app_context():
    a = db.session.get(NovoConvertido, ID1)
    checa("status mudou para integrado", a.status_ciclo == "integrado")
    checa("guardou a justificativa", "batizada" in (a.status_justificativa or ""))
    checa("guardou a data da mudanca", a.status_alterado_em is not None)
    n = db.session.scalar(db.select(db.func.count()).select_from(LogAuditoria)
                          .where(LogAuditoria.acao == "status_alterado"))
    checa("foi para a auditoria", n == 1)

s = semaforo_de(ID1)
checa(f"saiu do semaforo (agora {s.cor})", s.cor == "cinza" and not s.no_semaforo)

r = c.post(f"/alma/{ID1}/status", data={
    "csrf_token": csrf(c, ID1), "status_ciclo": "status_inventado", "justificativa": "x"})
with app.app_context():
    a = db.session.get(NovoConvertido, ID1)
    checa("recusa status inventado", a.status_ciclo == "integrado")

print("\n--- 6. TRANSFERIR: SO ADMIN (secao 7, item 2) ---")
r = c.post(f"/alma/{ID2}/transferir", data={
    "csrf_token": csrf(c, ID2), "responsavel_id": ID_ANA, "motivo": "teste"})
checa(f"responsavel recebe 403 (deu {r.status_code})", r.status_code == 403)
with app.app_context():
    a = db.session.get(NovoConvertido, ID2)
    checa("a alma continua com o Joao", a.responsavel_atual_id == ID_JOAO)

print("\n--- 7. TRANSFERIR: O ADMIN CONSEGUE ---")
ca = entrar("admin", "SenhaForte#2026")
with app.app_context():
    antes_designado = db.session.get(NovoConvertido, ID2).designado_em

r = ca.post(f"/alma/{ID2}/transferir", data={
    "csrf_token": csrf(ca, ID2), "responsavel_id": ID_ANA,
    "motivo": "O Joao vai viajar por dois meses."})
checa("transferencia aceita", r.status_code == 302)

with app.app_context():
    a = db.session.get(NovoConvertido, ID2)
    checa("a alma passou para a Ana", a.responsavel_atual_id == ID_ANA)
    checa("o relogio voltou (designado_em atualizado)", a.designado_em > antes_designado)
    checa("a observacao sensivel NAO foi repassada", a.observacao_sensivel is None)

    atrib = db.session.execute(db.select(Atribuicao).where(
        Atribuicao.convertido_id == ID2).order_by(Atribuicao.inicio)).scalars().all()
    checa(f"o historico tem 2 linhas ({len(atrib)})", len(atrib) >= 1)
    abertas = [x for x in atrib if x.fim is None]
    checa("so uma atribuicao esta aberta", len(abertas) == 1)
    checa("a aberta e a da Ana", abertas[0].responsavel_id == ID_ANA)
    checa("guardou o motivo", "viajar" in (abertas[0].motivo or ""))
    n = db.session.scalar(db.select(db.func.count()).select_from(LogAuditoria)
                          .where(LogAuditoria.acao == "transferir"))
    checa("foi para a auditoria", n == 1)

print("\n--- 8. O HISTORICO DE CONTATOS SOBREVIVE A TRANSFERENCIA ---")
with app.app_context():
    n = db.session.scalar(db.select(db.func.count()).select_from(Contato)
                          .where(Contato.convertido_id == ID2))
    checa(f"os contatos continuam la ({n})", n == 1)

print("\n--- 9. TRANSFERIR REPASSANDO A OBSERVACAO ---")
r = ca.post(f"/alma/{ID3}/transferir", data={
    "csrf_token": csrf(ca, ID3), "responsavel_id": ID_ANA,
    "motivo": "Reequilibrio de carga.", "manter_observacao": "y"})
with app.app_context():
    a = db.session.get(NovoConvertido, ID3)
    checa("com a caixa marcada, a observacao e mantida", a.observacao_sensivel is not None)

print("\n--- 10. IDOR NAS ACOES (secao 7, item 2) ---")
cj = entrar("joao", "OutraSenha#99")
for rota, dados in [
    ("contato", {"tipo": "telefone", "data_hora": AGORA_LOCAL, "resultado": "efetivo", "relato": "invadindo"}),
    ("presenca", {"evento_id": ID_EV, "presente": "sim"}),
    ("status", {"status_ciclo": "integrado", "justificativa": "invadindo"}),
]:
    dados["csrf_token"] = csrf(cj, ID2)   # token valido, alma de OUTRA pessoa
    r = cj.post(f"/alma/{ID_ANA_ALMA}/{rota}", data=dados)
    checa(f"Joao recebe 403 em /{rota} da alma da Ana (deu {r.status_code})", r.status_code == 403)

with app.app_context():
    a = db.session.get(NovoConvertido, ID_ANA_ALMA)
    checa("a alma da Ana nao foi tocada", a.status_ciclo == opcoes.STATUS_ATIVO)
    n = db.session.scalar(db.select(db.func.count()).select_from(Contato)
                          .where(Contato.convertido_id == ID_ANA_ALMA))
    checa("nenhum contato foi gravado nela", n == 0)

print("\n--- 11. CSRF NAS ACOES (secao 7, item 4) ---")
r = cj.post(f"/alma/{ID2}/contato", data={
    "tipo": "telefone", "data_hora": AGORA_LOCAL, "resultado": "efetivo", "relato": "sem token"})
checa(f"POST sem token CSRF e recusado (deu {r.status_code})", r.status_code == 400)

print("\n--- 12. O RELATORIO DO WHATSAPP (secao 5.3) ---")
h = ca.get(f"/alma/{ID3}/ficha").get_data(as_text=True)
import html as libhtml
trecho = libhtml.unescape(h[h.find("🙌"):h.find("🙌") + 500].split("</textarea>")[0])
linhas = trecho.split("\n")
checa("linha 1 tem o nome e o codigo", linhas[0].startswith("🙌 *Acompanhamento —") and "#" in linhas[0])
checa("linha 2 tem a conversao", linhas[1].startswith("📅"))
checa("linha 3 tem o departamento", linhas[2].startswith("🏠 Departamento:"))
checa("linha 4 tem o responsavel", linhas[3].startswith("👤 Responsável:"))
checa("linha 5 tem o ultimo contato", linhas[4].startswith("📞 Último contato:"))
checa("linha 6 tem as presencas", linhas[5].startswith("⛪ Presenças:"))
checa("linha 7 tem a bolinha do semaforo", any(b in linhas[6] for b in "🟢🟡🟠🔴🟣"))

print(f"\n{'=' * 55}")
print(f"  {ok} testes passaram, {falhou} falharam")
print(f"{'=' * 55}")
sys.exit(1 if falhou else 0)
