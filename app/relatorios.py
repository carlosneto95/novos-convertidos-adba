# -*- coding: utf-8 -*-
"""
app/relatorios.py - OS NUMEROS DOS RELATORIOS (secao 5.6).

Este arquivo so CALCULA. Nao desenha nada, nao decide cor, nao monta HTML.
Ele devolve numeros prontos, e quem desenha e o template (graficos) ou o
app/excel.py (planilha).

POR QUE SEPARAR ASSIM?
Os mesmos numeros aparecem em dois lugares: na tela e no Excel. Se o calculo
estivesse dentro do template, a planilha teria de repetir tudo - e um dia os
dois discordariam. Aqui existe UMA fonte da verdade.

PORTABILIDADE: os agrupamentos por mes sao feitos em Python, nao com funcoes
de data do SQLite. Assim, se um dia o banco virar PostgreSQL (o config.py ja
permite), nada aqui precisa mudar.
"""

# --- IMPORTACOES ----------------------------------------------------------
from collections import Counter, OrderedDict
from datetime import timedelta

from app.extensions import db
from app.models import NovoConvertido, Usuario, Contato, Evento, Presenca
from app import opcoes, semaforo as sem
from app.tempo import hoje, para_local


# ===========================================================================
# AJUDANTE: a base de almas que entra em TODO relatorio
# ===========================================================================
def _almas_validas():
    """
    Todas as almas, menos as duplicatas mescladas.

    Uma duplicata nao pode entrar em relatorio nenhum: ela inflaria as
    contagens e faria a igreja achar que teve mais conversoes do que teve.
    """
    return db.select(NovoConvertido).where(NovoConvertido.mesclado_em_id.is_(None))


# ===========================================================================
# 1. CONVERSOES POR MES (grafico de linha)
# ===========================================================================
def conversoes_por_mes(meses=12):
    """
    Quantas almas se converteram em cada um dos ultimos N meses.

    Devolve rotulos e valores ja na ordem certa, do mais antigo ao mais novo.

    Os meses SEM nenhuma conversao aparecem com zero, de proposito. Se a gente
    pulasse os meses vazios, a linha do grafico mentiria: dois pontos vizinhos
    poderiam estar separados por seis meses e parecer consecutivos.
    """
    MESES_PT = ["jan", "fev", "mar", "abr", "mai", "jun",
                "jul", "ago", "set", "out", "nov", "dez"]

    hoje_ = hoje()

    # --- Monta a lista dos meses, do mais antigo para o mais novo ---------
    serie = OrderedDict()
    ano, mes = hoje_.year, hoje_.month
    chaves = []
    for _ in range(meses):
        chaves.append((ano, mes))
        mes -= 1
        if mes == 0:            # voltou de janeiro para dezembro do ano anterior
            mes = 12
            ano -= 1
    for chave in reversed(chaves):
        serie[chave] = 0

    # --- Conta as conversoes ---------------------------------------------
    limite = chaves[-1]         # o mes mais antigo da janela
    primeiro_dia = hoje_.replace(year=limite[0], month=limite[1], day=1)

    datas = db.session.execute(
        _almas_validas().with_only_columns(NovoConvertido.data_conversao)
        .where(NovoConvertido.data_conversao >= primeiro_dia)
    ).scalars().all()

    for d in datas:
        chave = (d.year, d.month)
        if chave in serie:
            serie[chave] += 1

    rotulos = [f"{MESES_PT[m - 1]}/{str(a)[2:]}" for (a, m) in serie.keys()]
    valores = list(serie.values())

    return {"rotulos": rotulos, "valores": valores, "total": sum(valores)}


# ===========================================================================
# 2. CONVERSOES POR TRABALHO (grafico de barras)
# ===========================================================================
def conversoes_por_trabalho():
    """
    Em que trabalho da igreja as pessoas estao aceitando Jesus.

    E o relatorio que mais muda decisao: mostra onde vale a pena investir.
    Ordenado do maior para o menor - a pergunta e "qual rende mais?".
    """
    linhas = db.session.execute(
        db.select(NovoConvertido.trabalho, db.func.count(NovoConvertido.id))
        .where(NovoConvertido.mesclado_em_id.is_(None))
        .group_by(NovoConvertido.trabalho)
    ).all()

    dados = sorted(linhas, key=lambda x: x[1], reverse=True)

    return {
        "rotulos": [opcoes.rotulo(opcoes.TRABALHOS, t) for t, _ in dados],
        "valores": [n for _, n in dados],
        "chaves": [t for t, _ in dados],
    }


# ===========================================================================
# 3. DISTRIBUICAO POR DEPARTAMENTO (rosca)
# ===========================================================================
def por_departamento():
    """Quantas almas cada departamento esta acolhendo."""
    linhas = db.session.execute(
        db.select(NovoConvertido.departamento, db.func.count(NovoConvertido.id))
        .where(NovoConvertido.mesclado_em_id.is_(None))
        .group_by(NovoConvertido.departamento)
    ).all()

    contagem = {chave: 0 for chave in opcoes.DEPARTAMENTOS}
    for dep, n in linhas:
        contagem[dep] = n

    total = sum(contagem.values())

    return {
        "rotulos": [opcoes.rotulo(opcoes.DEPARTAMENTOS, d) for d in contagem],
        "valores": list(contagem.values()),
        "total": total,
        # O percentual vai pronto para o rotulo direto de cada fatia - e ele
        # que dispensa o leitor de decifrar a cor (exigencia de acessibilidade).
        "percentuais": [
            round(v * 100 / total) if total else 0 for v in contagem.values()
        ],
    }


# ===========================================================================
# 4. FUNIL DO CICLO DE VIDA
# ===========================================================================
def funil_do_ciclo():
    """
    Quantas almas estao em cada etapa do ciclo de vida.

    A ordem NAO e por tamanho: e a ordem da JORNADA - de quem acabou de
    chegar ate quem se firmou ou se perdeu. E isso que torna o grafico um
    funil e nao um ranking.
    """
    linhas = db.session.execute(
        db.select(NovoConvertido.status_ciclo, db.func.count(NovoConvertido.id))
        .where(NovoConvertido.mesclado_em_id.is_(None))
        .group_by(NovoConvertido.status_ciclo)
    ).all()

    contagem = {chave: 0 for chave in opcoes.STATUS_CICLO}
    for status, n in linhas:
        contagem[status] = n

    # A ordem da jornada, escrita a mao.
    ordem = [
        "aguardando_responsavel",
        "em_acompanhamento",
        "integrado",
        "frequenta_outra_igreja",
        "mudou_cidade",
        "nao_deseja_contato",
        "perdido_contato",
    ]

    total = sum(contagem.values())

    return {
        "rotulos": [opcoes.rotulo(opcoes.STATUS_CICLO, s) for s in ordem],
        "valores": [contagem[s] for s in ordem],
        "chaves": ordem,
        "total": total,
    }


# ===========================================================================
# 5. TAXA DE RETENCAO
# ===========================================================================
def taxa_de_retencao(dias=30):
    """
    Que fatia das almas em acompanhamento apareceu em algum culto nos
    ultimos N dias.

    ESTE NUMERO NAO VIRA GRAFICO - e um numero so, e numero solitario se le
    melhor grande, na tela, do que virando uma barra sozinha.

    E, na opiniao de quem acompanha, o numero mais honesto do sistema:
    contato por telefone qualquer um registra; presenca no culto e a prova de
    que a pessoa esta de fato voltando.
    """
    desde = hoje() - timedelta(days=dias)

    # Quantas almas estao em acompanhamento
    em_acompanhamento = db.session.scalar(
        db.select(db.func.count()).select_from(NovoConvertido).where(
            NovoConvertido.status_ciclo == opcoes.STATUS_ATIVO,
            NovoConvertido.mesclado_em_id.is_(None),
        )
    ) or 0

    if not em_acompanhamento:
        return {"percentual": None, "presentes": 0, "total": 0, "dias": dias}

    # Quantas delas tiveram pelo menos UMA presenca no periodo.
    # distinct() e essencial: quem foi a quatro cultos conta uma vez, nao quatro.
    presentes = db.session.scalar(
        db.select(db.func.count(db.distinct(Presenca.convertido_id)))
        .select_from(Presenca)
        .join(Evento, Presenca.evento_id == Evento.id)
        .join(NovoConvertido, Presenca.convertido_id == NovoConvertido.id)
        .where(
            Presenca.presente.is_(True),
            Evento.data >= desde,
            NovoConvertido.status_ciclo == opcoes.STATUS_ATIVO,
            NovoConvertido.mesclado_em_id.is_(None),
        )
    ) or 0

    return {
        "percentual": round(presentes * 100 / em_acompanhamento),
        "presentes": presentes,
        "total": em_acompanhamento,
        "dias": dias,
    }


# ===========================================================================
# 6. RANKING DE RESPONSAVEIS
# ===========================================================================
def ranking_de_responsaveis():
    """
    A mesma tabela de carga da tela de Responsaveis, ordenada pelo % em dia.

    CUIDADO AO LER: quem tem 2 almas e facilmente chega a 100%. Quem tem 30
    dificilmente passa de 70%. Por isso o grafico mostra a QUANTIDADE junto -
    sem ela, o ranking premia quem trabalha menos.
    """
    from app.rotas.responsaveis import calcular_carga

    carga = [c for c in calcular_carga() if c["almas"] > 0]
    carga.sort(key=lambda c: (c["percentual"] or 0, c["almas"]), reverse=True)

    return {
        "rotulos": [c["usuario"].primeiro_nome for c in carga],
        "percentuais": [c["percentual"] or 0 for c in carga],
        "almas": [c["almas"] for c in carga],
        "criticas": [c["criticas"] for c in carga],
        "linhas": carga,
    }


# ===========================================================================
# OS NUMEROS DO TOPO
# ===========================================================================
def resumo():
    """Os quatro numeros grandes do cabecalho dos relatorios."""
    total = db.session.scalar(
        db.select(db.func.count()).select_from(NovoConvertido)
        .where(NovoConvertido.mesclado_em_id.is_(None))
    ) or 0

    em_acompanhamento = db.session.scalar(
        db.select(db.func.count()).select_from(NovoConvertido).where(
            NovoConvertido.status_ciclo == opcoes.STATUS_ATIVO,
            NovoConvertido.mesclado_em_id.is_(None),
        )
    ) or 0

    integradas = db.session.scalar(
        db.select(db.func.count()).select_from(NovoConvertido).where(
            NovoConvertido.status_ciclo == "integrado",
            NovoConvertido.mesclado_em_id.is_(None),
        )
    ) or 0

    contatos = db.session.scalar(
        db.select(db.func.count()).select_from(Contato)
    ) or 0

    return {
        "total": total,
        "em_acompanhamento": em_acompanhamento,
        "integradas": integradas,
        "contatos": contatos,
    }


# ===========================================================================
# TUDO DE UMA VEZ
# ===========================================================================
def tudo():
    """Junta todos os relatorios. Usado pela tela e pela exportacao."""
    return {
        "resumo": resumo(),
        "por_mes": conversoes_por_mes(),
        "por_trabalho": conversoes_por_trabalho(),
        "por_departamento": por_departamento(),
        "funil": funil_do_ciclo(),
        "retencao": taxa_de_retencao(),
        "ranking": ranking_de_responsaveis(),
    }
