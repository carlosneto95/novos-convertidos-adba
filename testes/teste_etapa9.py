# -*- coding: utf-8 -*-
"""Testes de mesclagem, auditoria e backup (Etapa 9). Banco em memoria."""
import sys, re, os, tempfile, sqlite3
from datetime import timedelta

# O caminho do projeto vem do PROPRIO arquivo, nao escrito a mao. Assim os
# testes funcionam em qualquer computador e tambem no servidor.
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.stdout.reconfigure(encoding="utf-8")

from config import DevelopmentConfig
from app import create_app
from app.extensions import db, limiter
from app.models import Usuario, NovoConvertido, Contato, Evento, Presenca, Atribuicao, LogAuditoria
from app.tempo import agora, hoje
from app import opcoes, duplicatas as dup


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

    def criar(nome, telefone, dias_atras=0, resp=None, **extra):
        campos = dict(
            nome_completo=nome, telefone=telefone, sexo="F",
            data_nascimento=hoje().replace(year=hoje().year - 30),
            trabalho="culto_dominical", departamento="preciosas", data_conversao=hoje(),
            cadastrante_nome="Teste", cadastrante_telefone="16988887777",
            consentimento_em=agora(), consentimento_ip="127.0.0.1",
            status_ciclo=opcoes.STATUS_ATIVO if resp else opcoes.STATUS_INICIAL,
            responsavel_atual_id=resp,
            designado_em=agora() - timedelta(days=dias_atras) if resp else None,
            criado_em=agora() - timedelta(days=dias_atras),
        )
        campos.update(extra)
        a = NovoConvertido(**campos)
        db.session.add(a)
        db.session.flush()
        return a

    # Par 1: MESMO TELEFONE (a antiga tem contatos; a nova tem o endereco)
    velha = criar("Maria Aparecida Silva", "16992805852", dias_atras=30, resp=ID_JOAO)
    nova = criar("Maria A Silva", "16992805852", dias_atras=2, resp=ID_ANA,
                 cep="14015-000", cidade="Ribeirao Preto", uf="SP",
                 como_chegou="Veio pela vizinha.")

    # Par 2: NOME PARECIDO, telefones diferentes
    n1 = criar("Jose Carlos de Oliveira", "16991110000", dias_atras=20, resp=ID_JOAO)
    n2 = criar("Jose Carlos Oliveira", "16991112222", dias_atras=1, resp=ID_JOAO)

    # Nao deve virar sugestao
    outro = criar("Pedro Henrique Costa", "16993334444", dias_atras=10, resp=ID_JOAO)
    irmao = criar("Paulo Henrique Costa", "16995556666", dias_atras=9, resp=ID_JOAO)

    ev1 = Evento(nome="Culto A", tipo="culto_dominical", data=hoje() - timedelta(days=7), ativo=True)
    ev2 = Evento(nome="Culto B", tipo="culto_ensino", data=hoje() - timedelta(days=5), ativo=True)
    db.session.add_all([ev1, ev2])
    db.session.flush()

    # A velha: 2 contatos + presenca no culto A
    for d, res in [(10, "efetivo"), (3, "sem_resposta")]:
        db.session.add(Contato(convertido_id=velha.id, responsavel_id=ID_JOAO, tipo="telefone",
                               data_hora=agora() - timedelta(days=d), resultado=res,
                               relato=f"contato da ficha velha {d}", criado_em=agora()))
    db.session.add(Presenca(convertido_id=velha.id, evento_id=ev1.id, presente=False,
                            registrado_por_id=ID_JOAO))

    # A nova: 1 contato + presenca nos DOIS cultos (o A vai colidir)
    db.session.add(Contato(convertido_id=nova.id, responsavel_id=ID_ANA, tipo="whatsapp",
                           data_hora=agora() - timedelta(days=1), resultado="efetivo",
                           relato="contato da ficha nova", criado_em=agora()))
    db.session.add(Presenca(convertido_id=nova.id, evento_id=ev1.id, presente=True,
                            registrado_por_id=ID_ANA))
    db.session.add(Presenca(convertido_id=nova.id, evento_id=ev2.id, presente=True,
                            registrado_por_id=ID_ANA))
    db.session.add(Atribuicao(convertido_id=nova.id, responsavel_id=ID_ANA, inicio=agora()))

    db.session.commit()
    ID_VELHA, ID_NOVA, ID_N1, ID_N2 = velha.id, nova.id, n1.id, n2.id
    ID_OUTRO, ID_IRMAO, ID_EV1, ID_EV2 = outro.id, irmao.id, ev1.id, ev2.id


def entrar(login, senha):
    with app.app_context():
        limiter.reset()
    c = app.test_client()
    h = c.get("/login").get_data(as_text=True)
    tok = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', h).group(1)
    c.post("/login", data={"login": login, "senha": senha, "csrf_token": tok})
    return c


def tok_de(c, url="/admin/duplicatas"):
    h = c.get(url).get_data(as_text=True)
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', h)
    return m.group(1) if m else ""


print("\n--- 1. COMPARACAO DE NOMES ---")
casos_iguais = [
    ("Maria Aparecida da Silva", "Maria Aparecida Silva"),
    ("JOSE CARLOS OLIVEIRA", "jose carlos oliveira"),
    ("João Pedro de Souza", "Joao Pedro Souza"),
    ("Ana Lúcia dos Santos", "Ana Lucia Santos"),
]
for a, b in casos_iguais:
    s = dup.semelhanca(a, b)
    checa(f'"{a}" = "{b}" ({round(s*100)}%)', s >= dup.SEMELHANCA_MINIMA)

# O teste mede a DECISAO ("vira sugestao?"), nao so o percentual.
# "Maria Silva" x "Mario Silva" bate 91% no nome inteiro - passaria pelo
# percentual sozinho. Quem barra o par e a trava do primeiro nome.
def viraria_sugestao(a, b):
    return (dup.semelhanca(a, b) >= dup.SEMELHANCA_MINIMA
            and dup.mesmo_primeiro_nome(a, b))

casos_diferentes = [
    ("Maria Silva", "Mario Silva"),
    ("Pedro Henrique Costa", "Paulo Henrique Costa"),
    ("Ana Lima", "Ana Souza"),
]
for a, b in casos_diferentes:
    s = dup.semelhanca(a, b)
    checa(f'"{a}" != "{b}" (nome inteiro {round(s*100)}%, mas nao vira sugestao)',
          not viraria_sugestao(a, b))

# E o caso que a trava NAO pode barrar: erro de digitacao de verdade.
checa('"Joana Beatriz Souza" = "Joanna Beatriz Souza" (erro de digitacao)',
      viraria_sugestao("Joana Beatriz Souza", "Joanna Beatriz Souza"))
checa("primeiro nome identico basta",
      dup.mesmo_primeiro_nome("Maria Aparecida Silva", "Maria A Silva"))
checa("primeiro nome diferente barra",
      not dup.mesmo_primeiro_nome("Maria Silva", "Mario Silva"))

print("\n--- 2. ENCONTRAR AS DUPLICATAS ---")
with app.app_context():
    pares = dup.encontrar_duplicatas()
    ids = {(p["principal"].id, p["duplicata"].id): p for p in pares}

checa(f"achou pares suspeitos ({len(pares)})", len(pares) >= 2)
checa("achou o par do MESMO TELEFONE", (ID_VELHA, ID_NOVA) in ids)
checa("marcou o motivo como telefone", ids.get((ID_VELHA, ID_NOVA), {}).get("motivo") == "telefone")
checa("achou o par de NOME PARECIDO", (ID_N1, ID_N2) in ids)
checa("marcou o motivo como nome", ids.get((ID_N1, ID_N2), {}).get("motivo") == "nome")
checa("NAO sugeriu Pedro x Paulo Henrique Costa",
      (ID_OUTRO, ID_IRMAO) not in ids and (ID_IRMAO, ID_OUTRO) not in ids)
checa("a ficha MAIS ANTIGA e a principal",
      ids[(ID_VELHA, ID_NOVA)]["principal"].id == ID_VELHA)
checa("os mais provaveis vem primeiro", pares[0]["forca"] >= pares[-1]["forca"])

print("\n--- 3. SO ADMIN MESCLA (secao 7, item 2) ---")
cj = entrar("joao", "OutraSenha#99")
checa(f"responsavel recebe 403 na tela (deu {cj.get('/admin/duplicatas').status_code})",
      cj.get("/admin/duplicatas").status_code == 403)
r = cj.post("/admin/mesclar", data={"csrf_token": tok_de(cj, "/painel"),
                                    "principal_id": ID_VELHA, "duplicata_id": ID_NOVA})
checa(f"responsavel recebe 403 ao mesclar (deu {r.status_code})", r.status_code == 403)
with app.app_context():
    n = db.session.get(NovoConvertido, ID_NOVA)
    checa("nada foi mesclado", n.mesclado_em_id is None)

print("\n--- 4. A MESCLAGEM ---")
ca = entrar("admin", "SenhaForte#2026")
with app.app_context():
    v = db.session.get(NovoConvertido, ID_VELHA)
    contatos_antes = len(v.contatos)
    checa(f"a ficha que fica tinha {contatos_antes} contatos", contatos_antes == 2)
    checa("e nao tinha cidade", not v.cidade)

r = ca.post("/admin/mesclar", data={
    "csrf_token": tok_de(ca), "principal_id": ID_VELHA, "duplicata_id": ID_NOVA})
checa("mesclagem aceita", r.status_code == 302)

with app.app_context():
    v = db.session.get(NovoConvertido, ID_VELHA)
    n = db.session.get(NovoConvertido, ID_NOVA)

    print("   a ficha duplicada:")
    checa("NAO foi apagada do banco (secao 5.7)", n is not None)
    checa("foi MARCADA como mesclada", n.mesclado_em_id == ID_VELHA)

    print("   o que foi transferido:")
    checa(f"os contatos passaram: 2 + 1 = 3 (deu {len(v.contatos)})", len(v.contatos) == 3)
    checa("o contato da ficha nova esta la",
          any("ficha nova" in c.relato for c in v.contatos))
    n_contatos_orfaos = db.session.scalar(
        db.select(db.func.count()).select_from(Contato).where(Contato.convertido_id == ID_NOVA))
    checa("nao sobrou contato na ficha duplicada", n_contatos_orfaos == 0)

    print("   as presencas (o caso dificil):")
    presencas = db.session.execute(
        db.select(Presenca).where(Presenca.convertido_id == ID_VELHA)).scalars().all()
    checa(f"2 presencas, nao 3 (a do culto A colidiu) - deu {len(presencas)}", len(presencas) == 2)
    p_ev1 = next((p for p in presencas if p.evento_id == ID_EV1), None)
    checa("no culto que as duas marcaram, PRESENCA venceu a falta",
          p_ev1 is not None and p_ev1.presente is True)
    checa("a presenca do culto B foi transferida",
          any(p.evento_id == ID_EV2 for p in presencas))

    print("   os campos vazios completados:")
    checa("puxou a cidade da ficha duplicada", v.cidade == "Ribeirao Preto")
    checa("puxou o CEP", v.cep == "14015-000")
    checa("puxou o 'como chegou'", "vizinha" in (v.como_chegou or ""))
    checa("NAO sobrescreveu o nome da ficha que fica", v.nome_completo == "Maria Aparecida Silva")
    checa("NAO trocou o responsavel (ja tinha um)", v.responsavel_atual_id == ID_JOAO)

    print("   o historico de responsaveis:")
    atribs = db.session.execute(
        db.select(Atribuicao).where(Atribuicao.convertido_id == ID_VELHA)).scalars().all()
    checa(f"as atribuicoes passaram ({len(atribs)})", len(atribs) >= 1)
    abertas = [a for a in atribs if a.fim is None]
    checa(f"no maximo UMA atribuicao aberta (deu {len(abertas)})", len(abertas) <= 1)

    print("   a auditoria:")
    n_log = db.session.scalar(db.select(db.func.count()).select_from(LogAuditoria)
                              .where(LogAuditoria.acao == "mesclagem"))
    checa("a mesclagem foi auditada", n_log == 1)
    linha = db.session.execute(
        db.select(LogAuditoria).where(LogAuditoria.acao == "mesclagem")).scalar_one()
    checa("registra QUEM mesclou", linha.usuario_id == ID_ADMIN)
    checa("registra os dois codigos", "mesclada em" in (linha.detalhe or ""))

print("\n--- 5. A DUPLICATA SOME DO PAINEL, MAS NAO DO BANCO ---")
h = ca.get("/painel").get_data(as_text=True)
checa("a ficha que fica aparece no painel", "Maria Aparecida Silva" in h)
checa("a duplicata NAO aparece no painel", "Maria A Silva" not in h)
with app.app_context():
    ainda_existe = db.session.get(NovoConvertido, ID_NOVA)
    checa("mas continua no banco, inteira", ainda_existe is not None
          and ainda_existe.nome_completo == "Maria A Silva")

print("\n--- 6. MESCLAGENS INVALIDAS ---")
r = ca.post("/admin/mesclar", data={"csrf_token": tok_de(ca),
                                    "principal_id": ID_VELHA, "duplicata_id": ID_VELHA})
with app.app_context():
    v = db.session.get(NovoConvertido, ID_VELHA)
    checa("recusa mesclar uma ficha com ela mesma", v.mesclado_em_id is None)

r = ca.post("/admin/mesclar", data={"csrf_token": tok_de(ca),
                                    "principal_id": ID_N1, "duplicata_id": ID_NOVA})
with app.app_context():
    n = db.session.get(NovoConvertido, ID_NOVA)
    checa("recusa mesclar o que JA foi mesclado", n.mesclado_em_id == ID_VELHA)

r = ca.post("/admin/mesclar", data={"csrf_token": tok_de(ca),
                                    "principal_id": "id-inventado", "duplicata_id": ID_N2})
with app.app_context():
    n = db.session.get(NovoConvertido, ID_N2)
    checa("recusa id inexistente", n.mesclado_em_id is None)

r = ca.post("/admin/mesclar", data={"principal_id": ID_N1, "duplicata_id": ID_N2})
checa(f"recusa POST sem token CSRF (deu {r.status_code})", r.status_code == 400)

print("\n--- 7. O PAR MESCLADO SAI DAS SUGESTOES ---")
with app.app_context():
    pares2 = dup.encontrar_duplicatas()
    ids2 = {(p["principal"].id, p["duplicata"].id) for p in pares2}
checa("o par ja mesclado nao e sugerido de novo", (ID_VELHA, ID_NOVA) not in ids2)
checa("o par de nome ainda e sugerido", (ID_N1, ID_N2) in ids2)

print("\n--- 8. A TELA DE AUDITORIA (secao 7, item 13) ---")
cj2 = entrar("joao", "OutraSenha#99")
checa(f"responsavel recebe 403 (deu {cj2.get('/admin/auditoria').status_code})",
      cj2.get("/admin/auditoria").status_code == 403)

r = ca.get("/admin/auditoria")
checa("o admin abre", r.status_code == 200)
h = r.get_data(as_text=True)
checa("mostra a mesclagem", "mesclagem" in h)
checa("mostra os logins", "login" in h)
checa("avisa que e so leitura", "somente de" in h and "leitura" in h)
checa("NAO tem botao de apagar", "Excluir" not in h and "Apagar" not in h)

checa("filtro por acao funciona",
      "mesclagem" in ca.get("/admin/auditoria?acao=mesclagem").get_data(as_text=True))
checa("filtro por usuario responde",
      ca.get(f"/admin/auditoria?usuario={ID_ADMIN}").status_code == 200)
checa("filtro por periodo responde",
      ca.get("/admin/auditoria?dias=7").status_code == 200)

print("\n--- 9. A AUDITORIA NAO PODE SER ALTERADA ---")
# Nao deve existir NENHUMA rota que escreva na tabela de auditoria.
rotas_perigosas = []
for regra in app.url_map.iter_rules():
    caminho = str(regra)
    metodos = regra.methods or set()
    if "auditoria" in caminho and (metodos & {"POST", "PUT", "PATCH", "DELETE"}):
        rotas_perigosas.append(f"{caminho} {sorted(metodos & {'POST','PUT','PATCH','DELETE'})}")
checa(f"nenhuma rota escreve na auditoria (achei: {rotas_perigosas or 'nenhuma'})",
      not rotas_perigosas)

print("\n--- 10. O COMANDO DE BACKUP (secao 7, item 14) ---")
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as pasta_temp:
    banco = os.path.join(pasta_temp, "teste.db")
    pasta_backup = os.path.join(pasta_temp, "backups")

    class ConfigBackup(DevelopmentConfig):
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + banco
        PASTA_BACKUP = pasta_backup
        CADASTRO_TOKEN = "t"

    app_b = create_app(ConfigBackup)
    with app_b.app_context():
        db.create_all()
        u = Usuario(nome="Backup Teste", login="bkp", papel="admin", ativo=True)
        u.definir_senha("SenhaQualquer#1")
        db.session.add(u)
        db.session.add(NovoConvertido(
            nome_completo="Alma Do Backup", telefone="16992805852", sexo="F",
            data_nascimento=hoje().replace(year=hoje().year - 30),
            trabalho="culto_dominical", departamento="preciosas", data_conversao=hoje(),
            cadastrante_nome="T", cadastrante_telefone="16988887777",
            consentimento_em=agora(), consentimento_ip="127.0.0.1"))
        db.session.commit()

    runner = app_b.test_cli_runner()
    resultado = runner.invoke(args=["backup"])
    checa(f"o comando roda sem erro (saida {resultado.exit_code})", resultado.exit_code == 0)

    copias = [f for f in os.listdir(pasta_backup) if f.endswith(".db")]
    checa(f"criou 1 copia ({copias})", len(copias) == 1)
    checa("o nome tem a data", re.match(r"adba_\d{4}-\d{2}-\d{2}_\d{2}h\d{2}\.db", copias[0]))

    # A copia PRESTA? Abrimos e contamos.
    con = sqlite3.connect(os.path.join(pasta_backup, copias[0]))
    n_almas = con.execute("select count(*) from novo_convertido").fetchone()[0]
    nome = con.execute("select nome_completo from novo_convertido").fetchone()[0]
    con.close()
    checa("a copia abre e tem os dados", n_almas == 1 and nome == "Alma Do Backup")
    checa("o comando confere a copia sozinho", "Conferido" in resultado.output)
    checa("avisa para levar copia para fora do computador",
          "fora" in resultado.output or "nuvem" in resultado.output)

    checa("--listar funciona", runner.invoke(args=["backup", "--listar"]).exit_code == 0)

    # Cria mais copias e testa a limpeza
    import time
    for i in range(2):
        alvo = os.path.join(pasta_backup, f"adba_2020-01-0{i+1}_10h00.db")
        with open(alvo, "wb") as f:
            f.write(b"copia antiga")
    total_antes = len([f for f in os.listdir(pasta_backup) if f.endswith(".db")])
    runner.invoke(args=["backup", "--limpar", "1"])
    total_depois = len([f for f in os.listdir(pasta_backup) if f.endswith(".db")])
    checa(f"--limpar 1 guarda so a mais recente ({total_antes} -> {total_depois})",
          total_depois == 1)

    # Solta o arquivo antes de a pasta temporaria ser apagada - no Windows
    # um .db com conexao aberta nao pode ser removido.
    with app_b.app_context():
        db.engine.dispose()

print(f"\n{'=' * 55}")
print(f"  {ok} testes passaram, {falhou} falharam")
print(f"{'=' * 55}")
sys.exit(1 if falhou else 0)
