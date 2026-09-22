# -*- coding: utf-8 -*-
"""Teste das regras da Etapa 2. Grava e depois desfaz tudo (rollback)."""
import os
import sys
from datetime import date, timedelta
from sqlalchemy.exc import IntegrityError, StatementError

# O caminho do projeto vem do PROPRIO arquivo, nao escrito a mao. Assim os
# testes funcionam em qualquer computador e tambem no servidor.
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from config import DevelopmentConfig
from app import create_app
from app.extensions import db
from app.models import Usuario, NovoConvertido, Evento, Presenca, Contato, Atribuicao
from app.tempo import agora, hoje, calcular_idade, eh_menor_de_idade, dias_desde
from app import opcoes

# ATENCAO: banco em MEMORIA.
# A primeira versao deste teste usava o banco real - e quebrou assim que o
# comando dados-exemplo criou registros. Teste que depende do estado do banco
# de producao nao e teste: e loteria.
class ConfigTeste(DevelopmentConfig):
    SQLALCHEMY_DATABASE_URI = "sqlite://"

app = create_app(ConfigTeste)

# Monta o cenario do zero, dentro da memoria.
with app.app_context():
    db.create_all()
    from app.comandos import CULTOS_RECORRENTES
    from datetime import timedelta as _td
    _admin = Usuario(nome="Administrador", login="admin", papel="admin",
                     ativo=True, deve_trocar_senha=True)
    _admin.definir_senha("senha123")
    db.session.add(_admin)
    _inicio = hoje()
    for _d in range(91):
        _data = _inicio + _td(days=_d)
        for _culto in CULTOS_RECORRENTES:
            if _data.weekday() == _culto["dia_semana"]:
                db.session.add(Evento(nome=_culto["nome"], tipo=_culto["tipo"],
                                      data=_data, recorrente=True, ativo=True))
    db.session.commit()
ok = 0
falhou = 0


def checa(descricao, condicao):
    global ok, falhou
    if condicao:
        ok += 1
        print(f"  [OK]   {descricao}")
    else:
        falhou += 1
        print(f"  [FALHA] {descricao}")


with app.app_context():
    print("\n--- 1. SENHA (secao 7, item 1) ---")
    admin = Usuario.query.filter_by(login="admin").first()
    checa("admin existe no banco", admin is not None)
    checa("senha NAO esta em texto puro", "senha123" not in (admin.senha_hash or ""))
    checa("hash e bcrypt (comeca com $2b$)", admin.senha_hash.startswith("$2b$"))
    checa("senha correta e aceita", admin.conferir_senha("senha123"))
    checa("senha errada e recusada", not admin.conferir_senha("senha124"))
    checa("papel e admin", admin.eh_admin)
    checa("deve trocar a senha no 1o login", admin.deve_trocar_senha is True)

    # dois usuarios com a MESMA senha tem hashes diferentes (sal aleatorio)
    u = Usuario(nome="Teste", login="_teste_sal", papel="responsavel")
    u.definir_senha("senha123")
    checa("hashes diferentes para a mesma senha (sal)", u.senha_hash != admin.senha_hash)

    print("\n--- 2. EVENTOS RECORRENTES ---")
    domingos = Evento.query.filter_by(tipo="culto_dominical").all()
    tercas = Evento.query.filter_by(tipo="culto_ensino").all()
    checa(f"{len(domingos)} cultos dominicais gerados", len(domingos) > 0)
    checa(f"{len(tercas)} cultos de ensino gerados", len(tercas) > 0)
    checa("todo culto dominical cai num domingo", all(e.data.weekday() == 6 for e in domingos))
    checa("todo culto de ensino cai numa terca", all(e.data.weekday() == 1 for e in tercas))
    checa("todos marcados como recorrentes", all(e.recorrente for e in domingos + tercas))

    print("\n--- 3. CODIGO SEQUENCIAL (#001, #002...) ---")
    def nova_alma(nome, nasc, tel="16999990000"):
        return NovoConvertido(
            nome_completo=nome, telefone=tel, sexo="F", data_nascimento=nasc,
            trabalho="culto_dominical", departamento="preciosas",
            cadastrante_nome="Irma Ana", cadastrante_telefone="16988887777",
            consentimento_em=agora(), consentimento_ip="127.0.0.1",
        )

    a1 = nova_alma("Maria Silva", date(1990, 5, 20))
    a2 = nova_alma("Joana Souza", date(2010, 3, 2))
    db.session.add_all([a1, a2])
    db.session.flush()
    checa(f"primeira alma recebeu codigo {a1.codigo}", a1.codigo == 1)
    checa(f"segunda alma recebeu codigo {a2.codigo}", a2.codigo == 2)
    checa(f'codigo formatado = {a1.codigo_formatado}', a1.codigo_formatado == "#001")
    checa("id e UUID, nao numero sequencial", len(a1.id) == 36 and "-" in a1.id)
    checa("status inicial = aguardando_responsavel", a1.status_ciclo == "aguardando_responsavel")
    checa("nasce sem responsavel", a1.responsavel_atual_id is None)

    print("\n--- 4. IDADE E MENOR DE 18 (secao 5.1) ---")
    checa(f"Maria (1990) tem {a1.idade} anos", a1.idade == calcular_idade(date(1990, 5, 20)))
    checa("Maria NAO e menor de idade", not eh_menor_de_idade(a1.data_nascimento))
    checa("Joana (2010) E menor de idade", eh_menor_de_idade(a2.data_nascimento))
    quase18 = hoje() - timedelta(days=365 * 18 + 5)
    checa("quem fez 18 ha 5 dias nao e menor", not eh_menor_de_idade(quase18))

    print("\n--- 5. SUGESTAO DE DEPARTAMENTO ---")
    checa("mulher de 30 -> preciosas", opcoes.sugerir_departamento("F", 30) == "preciosas")
    checa("homem de 40 -> irmaos", opcoes.sugerir_departamento("M", 40) == "irmaos")
    checa("jovem de 16 -> geracao_life", opcoes.sugerir_departamento("F", 16) == "geracao_life")
    checa("jovem de 24 -> geracao_life", opcoes.sugerir_departamento("M", 24) == "geracao_life")
    checa("adulto de 25 ja sai do geracao_life", opcoes.sugerir_departamento("M", 25) == "irmaos")

    print("\n--- 6. TRAVA DE VALORES INVALIDOS (Enum) ---")
    try:
        ruim = nova_alma("Teste Ruim", date(1990, 1, 1))
        ruim.departamento = "departamento_inventado"
        db.session.add(ruim)
        db.session.flush()
        checa("banco recusa departamento invalido", False)
    except (IntegrityError, StatementError, LookupError, ValueError):
        db.session.rollback()
        db.session.add_all([a1, a2])
        db.session.flush()
        checa("banco recusa departamento invalido", True)

    print("\n--- 7. PRESENCA UNICA POR EVENTO ---")
    evento = domingos[0]
    p1 = Presenca(convertido_id=a1.id, evento_id=evento.id, presente=True,
                  registrado_por_id=admin.id)
    db.session.add(p1)
    db.session.flush()
    checa("primeira presenca gravada", p1.id is not None)
    try:
        p2 = Presenca(convertido_id=a1.id, evento_id=evento.id, presente=False,
                      registrado_por_id=admin.id)
        db.session.add(p2)
        db.session.flush()
        checa("banco recusa presenca duplicada no mesmo culto", False)
    except IntegrityError:
        db.session.rollback()
        checa("banco recusa presenca duplicada no mesmo culto", True)

    print("\n--- 8. EVENTO UNICO POR TIPO E DATA ---")
    try:
        repetido = Evento(nome="Culto Dominical", tipo="culto_dominical",
                          data=domingos[0].data, recorrente=True)
        db.session.add(repetido)
        db.session.flush()
        checa("banco recusa dois cultos iguais na mesma data", False)
    except IntegrityError:
        db.session.rollback()
        checa("banco recusa dois cultos iguais na mesma data", True)

    print("\n--- 9. LOGIN UNICO ---")
    try:
        db.session.add(Usuario(nome="Impostor", login="admin", papel="admin",
                               senha_hash="x"))
        db.session.flush()
        checa("banco recusa login repetido", False)
    except IntegrityError:
        db.session.rollback()
        checa("banco recusa login repetido", True)

    print("\n--- 10. RELOGIOS DO SEMAFORO (secao 4) ---")
    checa("dias_desde(agora) = 0", dias_desde(agora()) == 0)
    checa("dias_desde(10 dias atras) = 10",
          dias_desde(agora() - timedelta(days=10)) == 10)
    checa("dias_desde(47 horas) = 1 (arredonda p/ baixo)",
          dias_desde(agora() - timedelta(hours=47)) == 1)
    checa("dias_desde(None) = None", dias_desde(None) is None)

    print("\n--- 11. CAMPOS SENSIVEIS EXISTEM ---")
    colunas = {c.name for c in NovoConvertido.__table__.columns}
    for campo in ["observacao_sensivel", "consentimento_em", "consentimento_ip",
                  "responsavel_legal_nome", "responsavel_legal_telefone",
                  "mesclado_em_id", "status_justificativa", "designado_em"]:
        checa(f"campo {campo} existe", campo in colunas)

    # desfaz TUDO que este teste gravou
    db.session.rollback()

print(f"\n{'=' * 50}")
print(f"  {ok} testes passaram, {falhou} falharam")
print(f"{'=' * 50}")
sys.exit(1 if falhou else 0)
