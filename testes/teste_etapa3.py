# -*- coding: utf-8 -*-
"""Testes do formulario publico (Etapa 3). Usa um banco em memoria: nao toca no real."""
import os
import sys, re
from datetime import date, timedelta

# O caminho do projeto vem do PROPRIO arquivo, nao escrito a mao. Assim os
# testes funcionam em qualquer computador e tambem no servidor.
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from config import DevelopmentConfig
from app import create_app
from app.extensions import db
from app.models import NovoConvertido, LogAuditoria
from app.tempo import hoje


class ConfigTeste(DevelopmentConfig):
    SQLALCHEMY_DATABASE_URI = "sqlite://"     # banco em memoria, descartado no fim
    WTF_CSRF_ENABLED = True
    CADASTRO_TOKEN = "token-de-teste-123"
    RATELIMIT_ENABLED = True
    # Fixamos o limite AQUI, em vez de usar o do config.py. Assim o teste
    # mede o COMPORTAMENTO (bloqueia depois de N envios) e nao a configuracao
    # do momento - que pode mudar sem o teste estar errado.
    LIMITE_CADASTRO_PUBLICO = "5 per hour"


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

TOKEN = ConfigTeste.CADASTRO_TOKEN
URL = f"/cadastro/{TOKEN}"


def pegar_csrf(cliente):
    """Le o token anti-CSRF do HTML, como um navegador de verdade faria."""
    html = cliente.get(URL).get_data(as_text=True)
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    return m.group(1) if m else None


def dados_validos(**mudancas):
    d = {
        "cadastrante_nome": "Irma Ana Claudia",
        "cadastrante_telefone": "(16) 98888-7777",
        "nome_completo": "Maria Aparecida Silva",
        "telefone": "(16) 99280-5852",
        "sexo": "F",
        "data_nascimento": "1992-03-14",
        "cep": "14015-000",
        "logradouro": "Rua Visconde do Rio Branco",
        "numero": "100",
        "bairro": "Centro",
        "cidade": "Ribeirao Preto",
        "uf": "SP",
        "trabalho": "culto_dominical",
        "data_conversao": hoje().isoformat(),
        "departamento": "preciosas",
        "como_chegou": "Convidada por uma vizinha.",
        "tem_conhecido": "nao",
        "ja_frequentou_igreja": "nao",
        "consentimento": "y",
        "website": "",
    }
    d.update(mudancas)
    return d


def enviar(cliente, **mudancas):
    d = dados_validos(**mudancas)
    d["csrf_token"] = pegar_csrf(cliente)
    return cliente.post(URL, data=d, follow_redirects=False)


def zerar_limite():
    """Zera o contador de envios por IP.

    Todos os test_clients saem do mesmo IP (127.0.0.1). Sem isto, o limite de
    5 envios/hora bloquearia os testes seguintes - foi exatamente o que
    aconteceu na primeira rodada.
    """
    from app.extensions import limiter
    with app.app_context():
        limiter.reset()


def contar():
    with app.app_context():
        return db.session.query(NovoConvertido).count()


print("\n--- 1. TOKEN NA URL (secao 7, item 7) ---")
c = app.test_client()
checa("token correto abre o formulario", c.get(URL).status_code == 200)
checa("token errado devolve 404 (nao 403)", c.get("/cadastro/errado").status_code == 404)
checa("URL sem token nao existe", c.get("/cadastro/").status_code == 404)

print("\n--- 2. CSRF (secao 7, item 4) ---")
c = app.test_client()
d = dados_validos()
d["csrf_token"] = "token-falsificado"
r = c.post(URL, data=d)
checa("POST com CSRF falso e recusado", r.status_code == 400)
checa("nada foi gravado", contar() == 0)

d2 = dados_validos()
r = c.post(URL, data=d2)   # sem csrf_token nenhum
checa("POST sem CSRF e recusado", r.status_code == 400)
checa("nada foi gravado", contar() == 0)

print("\n--- 3. CADASTRO VALIDO ---")
c = app.test_client()
r = enviar(c)
checa("cadastro valido e aceito (redireciona)", r.status_code == 302)
checa("vai para a tela de sucesso", "/cadastro/sucesso" in r.headers.get("Location", ""))
checa("a alma foi gravada", contar() == 1)

with app.app_context():
    alma = db.session.query(NovoConvertido).first()
    checa(f"recebeu o codigo {alma.codigo_formatado}", alma.codigo == 1)
    checa("status inicial = aguardando_responsavel", alma.status_ciclo == "aguardando_responsavel")
    checa("nasce sem responsavel", alma.responsavel_atual_id is None)
    checa("telefone normalizado (so numeros)", alma.telefone == "16992805852")
    checa("CEP normalizado", alma.cep == "14015-000")
    checa("consentimento datado", alma.consentimento_em is not None)
    checa("IP do consentimento guardado", bool(alma.consentimento_ip))
    checa("nao gravou responsavel legal (e adulta)", alma.responsavel_legal_nome is None)
    logs = db.session.query(LogAuditoria).filter_by(acao="cadastro_publico").count()
    checa("cadastro registrado na auditoria", logs == 1)

print("\n--- 4. TELA DE SUCESSO NAO VAZA DADOS (secao 5.1) ---")
html = c.get("/cadastro/sucesso").get_data(as_text=True)
checa("nao mostra o nome cadastrado", "Maria Aparecida" not in html)
checa("nao mostra o codigo", "#001" not in html)
checa("nao tem link para /painel", "/painel" not in html)
checa("nao tem link para /login", "/login" not in html)

print("\n--- 5. CONSENTIMENTO LGPD OBRIGATORIO ---")
c = app.test_client()
antes = contar()
d = dados_validos()
del d["consentimento"]                      # simula checkbox desmarcado
d["csrf_token"] = pegar_csrf(c)
r = c.post(URL, data=d)
checa("sem consentimento o envio e recusado", r.status_code == 200)
checa("nada foi gravado", contar() == antes)
checa("mostra a mensagem de erro", "autorizar o uso dos dados" in r.get_data(as_text=True))

print("\n--- 6. MENOR DE IDADE (secao 5.1) ---")
_h = hoje()
nasc_menor = _h.replace(year=_h.year - 14).isoformat()   # exatamente 14 anos hoje

c = app.test_client()
antes = contar()
r = enviar(c, data_nascimento=nasc_menor)    # menor, SEM responsavel legal
checa("menor sem responsavel legal e recusado", r.status_code == 200)
checa("nada foi gravado", contar() == antes)
texto = r.get_data(as_text=True)
checa("avisa que e obrigatorio para menores", "Obrigatório para menores" in texto)
checa("exige a autorizacao do responsavel", "responsável legal precisa autorizar" in texto)

c = app.test_client()
r = enviar(
    c,
    nome_completo="Joana Beatriz Souza",
    data_nascimento=nasc_menor,
    departamento="geracao_life",
    responsavel_legal_nome="Marcia Souza",
    responsavel_legal_telefone="(16) 97777-6666",
    consentimento_responsavel="y",
)
checa("menor COM responsavel legal e aceito", r.status_code == 302)
with app.app_context():
    menor = db.session.query(NovoConvertido).filter_by(nome_completo="Joana Beatriz Souza").first()
    checa("gravou o nome do responsavel legal", menor.responsavel_legal_nome == "Marcia Souza")
    checa("gravou o telefone normalizado", menor.responsavel_legal_telefone == "16977776666")
    checa(f"idade calculada = {menor.idade}", menor.idade == 14)

print("\n--- 7. ARMADILHA ANTI-ROBO (honeypot) ---")
c = app.test_client()
antes = contar()
r = enviar(c, nome_completo="Robo Spam Bot", website="http://spam.com")
checa("robo recebe a tela de sucesso (nao desconfia)", r.status_code == 302)
checa("mas NADA foi gravado", contar() == antes)
with app.app_context():
    bloq = db.session.query(LogAuditoria).filter_by(acao="cadastro_bloqueado_honeypot").count()
    checa("bloqueio registrado na auditoria", bloq == 1)

print("\n--- 8. VALIDACAO DE CAMPOS NO SERVIDOR (secao 7, item 6) ---")
casos = [
    ("telefone invalido (5 digitos)", {"telefone": "12345"}),
    ("telefone com todos os digitos iguais", {"telefone": "99999999999"}),
    ("nascimento no futuro", {"data_nascimento": (hoje() + timedelta(days=30)).isoformat()}),
    ("conversao no futuro", {"data_conversao": (hoje() + timedelta(days=5)).isoformat()}),
    ("nome sem sobrenome", {"nome_completo": "Maria"}),
    ("departamento inventado", {"departamento": "departamento_falso"}),
    ("trabalho inventado", {"trabalho": "culto_inventado"}),
    ("trabalho 'outro' sem descrever", {"trabalho": "outro", "trabalho_outro": ""}),
    ("diz que conhece alguem mas nao diz quem", {"tem_conhecido": "sim", "conhecido_nome": ""}),
    ("UF invalida", {"uf": "ZZ"}),
]
for desc, mudanca in casos:
    zerar_limite()
    c = app.test_client()
    antes = contar()
    r = enviar(c, **mudanca)
    checa(f"recusa: {desc}", r.status_code == 200 and contar() == antes)

print("\n--- 9. XSS: SCRIPT NO NOME NAO EXECUTA (secao 7, item 5) ---")
c = app.test_client()
ataque = "<script>alert('xss')</script> Silva"
r = enviar(c, nome_completo=ataque)
html = c.get(URL).get_data(as_text=True)
checa("script nao aparece cru no HTML", "<script>alert('xss')</script>" not in html)

print("\n--- 10. LIMITE DE ENVIOS POR IP (secao 7, item 7) ---")
c = app.test_client()
codigos = []
for i in range(8):
    r = enviar(c, nome_completo=f"Teste Limite{i} Sobrenome", telefone="1699280585" + str(i % 10))
    codigos.append(r.status_code)
bloqueados = codigos.count(429)
checa(f"bloqueia apos 5 envios/hora (codigos: {codigos})", bloqueados >= 1)

print("\n--- 11. VOLTAR AO FORMULARIO ENTREGA UMA PAGINA LIMPA ---")
# O cadastro anterior JA FOI SALVO. Se o botao "Cadastrar outra pessoa"
# voltasse no historico (history.back()), o formulario reabriria com tudo ainda
# preenchido - e a proxima pessoa comecaria com os dados da anterior. Numa
# igreja, onde o mesmo tablet passa de mao em mao, isso mistura os cadastros e
# ainda mostra a quem chegou depois os dados de quem acabou de se cadastrar.
zerar_limite()
c = app.test_client()
NOME_ANTERIOR = "Joaquina Distinta Sobrenome"
TEL_ANTERIOR = "(16) 97777-3333"   # diferente do telefone da igreja, que sai no
                                   # rodape de LGPD e daria falso positivo aqui
r = enviar(c, nome_completo=NOME_ANTERIOR, telefone=TEL_ANTERIOR)
sucesso = c.get(r.headers.get("Location", "/cadastro/sucesso")).get_data(as_text=True)

checa("a tela de sucesso nao usa history.back()", "history.back()" not in sucesso)
_link = re.search(r'href="(/cadastro/[^"]*)"', sucesso)
checa("a tela de sucesso leva ao formulario por um endereco de verdade", bool(_link))
checa("a tela de sucesso nao mostra o nome de quem foi cadastrado",
      NOME_ANTERIOR not in sucesso)
checa("a tela de sucesso nao mostra o telefone", "97777-3333" not in sucesso)

if _link:
    limpo = c.get(_link.group(1)).get_data(as_text=True)
    # Procurar o texto solto no HTML acharia as OPCOES do formulario ("SP",
    # "nao", "100"), que existem sempre. O que importa e se algum campo veio
    # PREENCHIDO - com value=, checked ou selected.
    _cheios = re.findall(
        r'name="(nome_completo|telefone|cadastrante_nome|cadastrante_telefone|'
        r'logradouro|numero|bairro|cidade|cep)"[^>]*value="([^"]+)"', limpo)
    checa(f"nenhum campo de texto veio preenchido ({_cheios})", not _cheios)
    checa("nenhum radio ou caixa veio marcada",
          not re.search(r"<input[^>]*\bchecked\b", limpo))
    checa("nenhuma lista veio com opcao ja escolhida",
          not re.search(r"<option[^>]*\bselected\b", limpo))
    checa("o nome da pessoa anterior nao aparece", NOME_ANTERIOR not in limpo)
    checa("o telefone dela nao aparece", "97777-3333" not in limpo)

# Sem sessao (cookie apagado, outro aparelho) nao pode sobrar link quebrado.
_outro = app.test_client()
_sem_sessao = _outro.get("/cadastro/sucesso").get_data(as_text=True)
checa("sem sessao, nao aparece um link quebrado", "/cadastro/None" not in _sem_sessao)
checa("sem sessao, tambem nao volta o history.back()",
      "history.back()" not in _sem_sessao)

# Na tela de "muitas tentativas" o history.back() esta CERTO: la o cadastro NAO
# foi salvo, e a pessoa precisa dos dados dela de volta.
_t429 = open(os.path.join(RAIZ, "app", "templates", "erros", "429.html"),
             encoding="utf-8").read()
checa("a tela de muitas tentativas mantem o history.back(), de proposito",
      "history.back()" in _t429)

print(f"\n{'=' * 55}")
print(f"  {ok} testes passaram, {falhou} falharam")
print(f"{'=' * 55}")
sys.exit(1 if falhou else 0)
