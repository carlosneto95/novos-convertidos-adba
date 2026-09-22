# -*- coding: utf-8 -*-
"""Testes do painel e do semaforo (Etapa 5). Banco em memoria."""
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
from app.models import Usuario, NovoConvertido, Contato, Atribuicao, LogAuditoria
from app.tempo import agora, hoje
from app import semaforo as sem, opcoes


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
    db.session.add_all([admin, joao, ana])
    db.session.flush()
    ID_ADMIN, ID_JOAO, ID_ANA = admin.id, joao.id, ana.id

    def criar_alma(nome, responsavel_id=None, dias_desig=None, status=None,
                   departamento="preciosas", trabalho="culto_dominical",
                   horas_atras=None, telefone="16999990000"):
        quando = agora() - timedelta(days=dias_desig or 0)
        if horas_atras is not None:
            quando = agora() - timedelta(hours=horas_atras)
        return NovoConvertido(
            nome_completo=nome, telefone=telefone, sexo="F",
            data_nascimento=hoje().replace(year=hoje().year - 30),
            trabalho=trabalho, departamento=departamento,
            data_conversao=hoje(),
            cadastrante_nome="Teste", cadastrante_telefone="16988887777",
            consentimento_em=quando, consentimento_ip="127.0.0.1",
            status_ciclo=status or (opcoes.STATUS_ATIVO if responsavel_id else opcoes.STATUS_INICIAL),
            responsavel_atual_id=responsavel_id,
            designado_em=quando if responsavel_id else None,
            criado_em=quando,
        )

    def contato(alma, dias, resultado="efetivo"):
        return Contato(
            convertido_id=alma.id, responsavel_id=alma.responsavel_atual_id,
            tipo="telefone", data_hora=agora() - timedelta(days=dias),
            resultado=resultado, relato="teste", criado_em=agora() - timedelta(days=dias),
        )

    a_verde = criar_alma("Verde Silva", ID_JOAO, 30)
    a_amarelo = criar_alma("Amarela Souza", ID_JOAO, 60)
    a_laranja = criar_alma("Laranja Costa", ID_JOAO, 60)
    a_vermelho = criar_alma("Vermelha Lima", ID_JOAO, 60)
    a_sem_efetivo = criar_alma("Nunca Atende", ID_JOAO, 40)
    a_abandonada = criar_alma("Abandonada Dias", ID_ANA, 20)
    a_da_ana = criar_alma("Privada da Ana", ID_ANA, 10)
    a_roxa_nova = criar_alma("Roxa Recente", horas_atras=4)
    a_roxa_velha = criar_alma("Roxa Antiga", horas_atras=100)
    a_integrada = criar_alma("Integrada Rocha", ID_JOAO, 90, status="integrado")
    a_integrada.status_alterado_em = hoje().replace(day=1)
    a_duplicata = criar_alma("Duplicada Nunes", ID_JOAO, 5)

    db.session.add_all([a_verde, a_amarelo, a_laranja, a_vermelho, a_sem_efetivo,
                        a_abandonada, a_da_ana, a_roxa_nova, a_roxa_velha,
                        a_integrada, a_duplicata])
    db.session.flush()

    a_duplicata.mesclado_em_id = a_verde.id

    db.session.add_all([
        contato(a_verde, 2),
        contato(a_amarelo, 10),
        contato(a_laranja, 18),
        contato(a_vermelho, 25),
        contato(a_sem_efetivo, 3, resultado="sem_resposta"),
        contato(a_da_ana, 1),
    ])
    db.session.commit()

    IDS = {
        "verde": a_verde.id, "amarelo": a_amarelo.id, "laranja": a_laranja.id,
        "vermelho": a_vermelho.id, "sem_efetivo": a_sem_efetivo.id,
        "abandonada": a_abandonada.id, "da_ana": a_da_ana.id,
        "roxa_nova": a_roxa_nova.id, "roxa_velha": a_roxa_velha.id,
        "integrada": a_integrada.id, "duplicata": a_duplicata.id,
    }


def zerar_limite():
    with app.app_context():
        limiter.reset()


def entrar(login, senha):
    zerar_limite()
    c = app.test_client()
    html = c.get("/login").get_data(as_text=True)
    tok = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
    c.post("/login", data={"login": login, "senha": senha, "csrf_token": tok})
    return c


def semaforo_de(alma_id):
    from app.rotas.painel import mapas_de_contato
    with app.app_context():
        alma = db.session.get(NovoConvertido, alma_id)
        t, e = mapas_de_contato([alma.id])
        return sem.calcular(alma, t.get(alma.id), e.get(alma.id))


# =========================================================================
print("\n--- 1. AS CORES DO SEMAFORO (secao 4) ---")
casos = [
    ("verde",      "verde",    "contato ha 2 dias"),
    ("amarelo",    "amarelo",  "contato ha 10 dias"),
    ("laranja",    "laranja",  "contato ha 18 dias"),
    ("vermelho",   "vermelho", "contato ha 25 dias"),
    ("roxa_nova",  "roxo",     "aguardando responsavel"),
    ("roxa_velha", "roxo",     "aguardando ha 100h"),
    ("integrada",  "cinza",    "status integrado sai do semaforo"),
    ("duplicata",  "cinza",    "duplicata mesclada sai do painel"),
]
for chave, cor_esperada, desc in casos:
    s = semaforo_de(IDS[chave])
    checa(f"{desc} -> {cor_esperada} (deu {s.cor})", s.cor == cor_esperada)

print("\n--- 2. OS DOIS RELOGIOS ---")
s = semaforo_de(IDS["sem_efetivo"])
checa(f"tentativa recente (3d) + nunca efetivo -> cor {s.cor}", s.cor == "vermelho")
checa("icone diz 'a alma nao responde'", s.icone == "sem-resposta")
checa(f"relogio da tentativa = 3 dias (deu {s.dias_tentativa})", s.dias_tentativa == 3)
checa(f"relogio do efetivo = 40 dias (deu {s.dias_efetivo})", s.dias_efetivo == 40)

s = semaforo_de(IDS["abandonada"])
checa(f"designada ha 20d sem NENHUM contato -> laranja (faixa 15-21). Deu {s.cor}", s.cor == "laranja")
checa("icone diz 'o responsavel nao tentou'", s.icone == "sem-contato")

s = semaforo_de(IDS["amarelo"])
checa("contato ha 10 dias estoura o prazo de 7", s.estourou is True)
checa("icone aponta o responsavel", s.icone == "sem-contato")

s = semaforo_de(IDS["verde"])
checa("contato ha 2 dias NAO estoura prazo", s.estourou is False)
checa("sem icone quando esta tudo em dia", s.icone is None)

print("\n--- 3. PRAZO DE 48H ESTOURADO NUNCA FICA VERDE ---")
with app.app_context():
    nova = NovoConvertido(
        nome_completo="Recem Designada", telefone="16900001111", sexo="F",
        data_nascimento=hoje().replace(year=hoje().year - 25),
        trabalho="culto_dominical", departamento="preciosas", data_conversao=hoje(),
        cadastrante_nome="Teste", cadastrante_telefone="16988887777",
        consentimento_em=agora(), consentimento_ip="127.0.0.1",
        status_ciclo=opcoes.STATUS_ATIVO, responsavel_atual_id=ID_JOAO,
        designado_em=agora() - timedelta(hours=72), criado_em=agora() - timedelta(hours=72),
    )
    db.session.add(nova)
    db.session.commit()
    ID_NOVA = nova.id

s = semaforo_de(ID_NOVA)
checa(f"designada ha 72h sem contato -> nao e verde (deu {s.cor})", s.cor != "verde")
checa("marcada como prazo estourado", s.estourou is True)
checa("icone aponta o responsavel", s.icone == "sem-contato")

print("\n--- 4. TRANSFERENCIA VOLTA O RELOGIO PARA 48H ---")
with app.app_context():
    alma = db.session.get(NovoConvertido, IDS["vermelho"])
    antes = sem.calcular(alma, agora() - timedelta(days=25), agora() - timedelta(days=25))
    alma.designado_em = agora()          # o que a transferencia faz
    alma.responsavel_atual_id = ID_ANA
    db.session.commit()
checa(f"antes da transferencia: {antes.cor}", antes.cor == "vermelho")
s = semaforo_de(IDS["vermelho"])
checa("o historico de contatos continua contando", s.dias_tentativa == 25)

print("\n--- 5. O PAINEL ABRE ---")
c_admin = entrar("admin", "SenhaForte#2026")
r = c_admin.get("/painel")
checa("admin abre o painel", r.status_code == 200)
html = r.get_data(as_text=True)
checa("mostra a faixa roxa", "aguardando responsável" in html)
checa("mostra os cartoes de KPI", "Em acompanhamento" in html and "Críticas" in html)
checa("mostra a legenda do semaforo", "Legenda" in html)

print("\n--- 6. IDOR: O PAINEL DO RESPONSAVEL (secao 7, itens 2 e 3) ---")
c_joao = entrar("joao", "OutraSenha#99")
html = c_joao.get("/painel").get_data(as_text=True)
checa("Joao ve as almas dele", "Verde Silva" in html)
checa("Joao NAO ve a alma da Ana", "Privada da Ana" not in html)
checa("Joao NAO ve a faixa roxa (e so do Admin)", "aguardando responsável" not in html)
checa("Joao NAO ve a duplicata mesclada", "Duplicada Nunes" not in html)

print("   busca nao vaza dados de outro responsavel:")
html = c_joao.get("/painel?busca=Privada").get_data(as_text=True)
checa("buscar pelo nome da alma da Ana nao devolve nada", "Privada da Ana" not in html)
html = c_joao.get("/painel?responsavel=" + ID_ANA).get_data(as_text=True)
checa("filtrar pelo id da Ana nao devolve as almas dela", "Privada da Ana" not in html)

print("\n--- 7. FILTROS ---")
checa("filtro de cor vermelho", "Vermelha Lima" in c_admin.get("/painel?cor=vermelho").get_data(as_text=True))
checa("filtro de cor verde nao traz as vermelhas",
      "Vermelha Lima" not in c_admin.get("/painel?cor=verde").get_data(as_text=True))
checa("busca por nome", "Verde Silva" in c_admin.get("/painel?busca=Verde").get_data(as_text=True))
checa("busca por telefone", "Verde Silva" in c_admin.get("/painel?busca=16999990000").get_data(as_text=True))
h = c_admin.get("/painel?status=todos").get_data(as_text=True)
checa("status=todos traz as integradas", "Integrada Rocha" in h)
h = c_admin.get("/painel").get_data(as_text=True)
checa("sem filtro, integradas ficam fora do painel", "Integrada Rocha" not in h)
checa("sem filtro, duplicatas ficam fora do painel", "Duplicada Nunes" not in h)

print("\n--- 8. DESIGNAR RESPONSAVEL ---")
tok = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', c_admin.get("/painel").get_data(as_text=True)).group(1)

# responsavel invalido
r = c_admin.post(f"/alma/{IDS['roxa_nova']}/designar",
                 data={"responsavel_id": "id-inventado", "csrf_token": tok})
with app.app_context():
    a = db.session.get(NovoConvertido, IDS["roxa_nova"])
    checa("recusa responsavel inexistente", a.responsavel_atual_id is None)

# designacao valida
r = c_admin.post(f"/alma/{IDS['roxa_nova']}/designar",
                 data={"responsavel_id": ID_JOAO, "csrf_token": tok})
checa("designacao valida redireciona", r.status_code == 302)
with app.app_context():
    a = db.session.get(NovoConvertido, IDS["roxa_nova"])
    checa("a alma ganhou responsavel", a.responsavel_atual_id == ID_JOAO)
    checa("saiu do roxo para em acompanhamento", a.status_ciclo == opcoes.STATUS_ATIVO)
    checa("o relogio de 48h comecou (designado_em preenchido)", a.designado_em is not None)
    atrib = db.session.execute(
        db.select(Atribuicao).where(Atribuicao.convertido_id == a.id)
    ).scalars().all()
    checa("criou linha no historico de atribuicoes", len(atrib) == 1)
    checa("a atribuicao esta aberta (sem fim)", atrib[0].fim is None)
    checa("registrou quem designou", atrib[0].atribuido_por_id == ID_ADMIN)
    logs = db.session.scalar(
        db.select(db.func.count()).select_from(LogAuditoria).where(LogAuditoria.acao == "designar")
    )
    checa("designacao foi para a auditoria", logs == 1)

s = semaforo_de(IDS["roxa_nova"])
checa(f"a alma saiu do roxo e entrou no semaforo (agora {s.cor})", s.cor != "roxo")

print("\n--- 9. RESPONSAVEL NAO PODE DESIGNAR (secao 7, item 2) ---")
tok_joao = re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                     c_joao.get("/painel").get_data(as_text=True))
tok_joao = tok_joao.group(1) if tok_joao else "sem-token"
r = c_joao.post(f"/alma/{IDS['roxa_velha']}/designar",
                data={"responsavel_id": ID_JOAO, "csrf_token": tok_joao})
checa(f"responsavel recebe 403 ao tentar designar (deu {r.status_code})", r.status_code == 403)
with app.app_context():
    a = db.session.get(NovoConvertido, IDS["roxa_velha"])
    checa("a alma continua sem responsavel", a.responsavel_atual_id is None)
    negados = db.session.scalar(
        db.select(db.func.count()).select_from(LogAuditoria).where(LogAuditoria.acao == "acesso_negado")
    )
    checa("a tentativa foi registrada na auditoria", negados >= 1)

print("\n--- 10. DESIGNAR SEM LOGIN ---")
c_anon = app.test_client()
r = c_anon.post(f"/alma/{IDS['roxa_velha']}/designar", data={"responsavel_id": ID_JOAO})
checa("sem login nao designa", r.status_code in (302, 400, 403))

print("\n--- 11. CONTAGEM DOS KPIs ---")
with app.app_context():
    from app.rotas.painel import mapas_de_contato
    almas = db.session.execute(
        db.select(NovoConvertido).where(NovoConvertido.mesclado_em_id.is_(None))
    ).scalars().all()
    t, e = mapas_de_contato([a.id for a in almas])
    pares = sem.calcular_muitas(almas, t, e)
    cont = sem.contar_por_cor(pares)
checa(f"em acompanhamento = verde+amarelo+laranja+vermelho ({cont['em_acompanhamento']})",
      cont["em_acompanhamento"] == cont["verde"] + cont["amarelo"] + cont["laranja"] + cont["vermelho"])
checa(f"em atencao = amarelo+laranja ({cont['atencao']})",
      cont["atencao"] == cont["amarelo"] + cont["laranja"])
checa("duplicata nao entra em nenhuma contagem de cor",
      sum(1 for a, s in pares if a.id == IDS["duplicata"]) == 0)

print("\n--- 12. O SEMAFORO E CALCULADO NO SERVIDOR (secao 4) ---")
html = c_admin.get("/painel").get_data(as_text=True)
checa("o HTML ja vem com as cores prontas", "bg-semaforo-vermelho" in html or "bg-semaforo-verde" in html)
checa("nao ha conta de dias no JavaScript da pagina",
      "dias_desde" not in html and "calcularSemaforo" not in html)

print(f"\n{'=' * 55}")
print(f"  {ok} testes passaram, {falhou} falharam")
print(f"{'=' * 55}")
sys.exit(1 if falhou else 0)
