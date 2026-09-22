# -*- coding: utf-8 -*-
"""
app/excel.py - A EXPORTACAO PARA EXCEL (secao 5.6).

Gera um arquivo .xlsx com quatro abas:
    Novos Convertidos - a ficha de cada alma
    Contatos          - todo contato registrado
    Presencas         - quem esteve em qual culto
    Responsaveis      - a tabela de carga da equipe

POR QUE UM ARQUIVO E NAO UMA TELA?
Para o pastor levar numa reuniao, imprimir, mandar por e-mail, cruzar com
outra planilha. A tela responde "como estamos agora"; a planilha responde
"me deixa trabalhar com isso do meu jeito".

O ARQUIVO NASCE NA MEMORIA, nao no disco. Ele e montado, entregue ao
navegador e descartado. Nunca fica um .xlsx com dados de pessoas esquecido
numa pasta do servidor.

SEGURANCA (secao 7, item 12): a rota que chama este arquivo e exclusiva do
Admin e registra a exportacao na auditoria. Faz sentido: um unico clique aqui
baixa a base inteira de dados pessoais da igreja.
"""

# --- IMPORTACOES ----------------------------------------------------------
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from app.extensions import db
from app.models import NovoConvertido, Usuario, Contato, Evento, Presenca
from app import opcoes, semaforo as sem
from app.tempo import para_local, hoje, agora
from app.validacao import formatar_telefone


# ===========================================================================
# APARENCIA DA PLANILHA
# ===========================================================================
# O azul-grafite da marca, no formato que o Excel entende: "FF" de opacidade
# + o RGB, tudo em maiuscula e SEM o "#".
COR_CABECALHO = "FF3E3D42"

FONTE_CABECALHO = Font(name="Calibri", size=11, bold=True, color="FFFFFFFF")
FUNDO_CABECALHO = PatternFill("solid", fgColor=COR_CABECALHO)
ALINHAMENTO_CABECALHO = Alignment(horizontal="left", vertical="center")

BORDA_FINA = Border(bottom=Side(style="thin", color="FFD9D9D9"))


def _formatar_aba(aba, colunas, total_linhas):
    """
    Deixa a aba pronta para uso: cabecalho colorido, filtros, colunas na
    largura certa e a primeira linha congelada.

    E o que separa "um monte de dado" de "uma planilha que da para usar".
    """
    # --- 1. O cabecalho ---------------------------------------------------
    for i, (titulo, largura) in enumerate(colunas, start=1):
        celula = aba.cell(row=1, column=i)
        celula.value = titulo
        celula.font = FONTE_CABECALHO
        celula.fill = FUNDO_CABECALHO
        celula.alignment = ALINHAMENTO_CABECALHO
        aba.column_dimensions[get_column_letter(i)].width = largura

    aba.row_dimensions[1].height = 22

    # --- 2. Congelar a primeira linha -------------------------------------
    # Ao rolar 200 linhas para baixo, o cabecalho continua na tela. Sem isso,
    # ninguem lembra o que e a coluna J.
    aba.freeze_panes = "A2"

    # --- 3. Filtros no cabecalho ------------------------------------------
    # Habilita as setinhas de filtro do Excel (exigido pela secao 5.6).
    if total_linhas:
        ultima_coluna = get_column_letter(len(colunas))
        aba.auto_filter.ref = f"A1:{ultima_coluna}{total_linhas + 1}"


def _sim_nao(valor):
    """True/False/None viram Sim/Nao/vazio - ninguem le "TRUE" numa planilha."""
    if valor is None:
        return ""
    return "Sim" if valor else "Nao"


def _data(valor):
    """Data no formato brasileiro, ou vazio."""
    if valor is None:
        return ""
    if hasattr(valor, "hour"):                 # e uma data COM hora
        return para_local(valor).strftime("%d/%m/%Y %H:%M")
    return valor.strftime("%d/%m/%Y")


# ===========================================================================
# ABA 1 - NOVOS CONVERTIDOS
# ===========================================================================
def _aba_convertidos(planilha):
    aba = planilha.active
    aba.title = "Novos Convertidos"

    colunas = [
        ("Codigo", 9), ("Nome completo", 30), ("Telefone", 17),
        ("Sexo", 10), ("Nascimento", 12), ("Idade", 7),
        ("Cidade", 18), ("UF", 5), ("Bairro", 18),
        ("Trabalho da conversao", 22), ("Data da conversao", 16),
        ("Departamento", 15), ("Status", 22), ("Responsavel atual", 22),
        ("Designada em", 16), ("Dias sem contato", 16), ("Semaforo", 11),
        ("Ja frequentou igreja", 18), ("Conhece alguem", 15),
        ("Quem cadastrou", 24), ("Telefone de quem cadastrou", 22),
        ("Consentimento LGPD em", 20),
        ("Responsavel legal", 24), ("Telefone do responsavel legal", 24),
        ("Cadastrada em", 16),
    ]

    from app.rotas.painel import mapas_de_contato

    almas = db.session.execute(
        db.select(NovoConvertido)
        .where(NovoConvertido.mesclado_em_id.is_(None))
        .order_by(NovoConvertido.codigo)
    ).scalars().all()

    tentativas, efetivos = mapas_de_contato([a.id for a in almas])

    for linha, alma in enumerate(almas, start=2):
        s = sem.calcular(alma, tentativas.get(alma.id), efetivos.get(alma.id))

        valores = [
            alma.codigo_formatado,
            alma.nome_completo,
            formatar_telefone(alma.telefone),
            opcoes.rotulo(opcoes.SEXOS, alma.sexo, ""),
            _data(alma.data_nascimento),
            alma.idade,
            alma.cidade or "",
            alma.uf or "",
            alma.bairro or "",
            alma.trabalho_rotulo,
            _data(alma.data_conversao),
            alma.departamento_rotulo,
            alma.status_rotulo,
            alma.responsavel_atual.nome if alma.responsavel_atual else "",
            _data(alma.designado_em),
            s.dias if s.no_semaforo else "",
            s.cor if s.no_semaforo else "",
            _sim_nao(alma.ja_frequentou_igreja),
            _sim_nao(alma.tem_conhecido),
            alma.cadastrante_nome,
            formatar_telefone(alma.cadastrante_telefone),
            _data(alma.consentimento_em),
            alma.responsavel_legal_nome or "",
            formatar_telefone(alma.responsavel_legal_telefone) if alma.responsavel_legal_telefone else "",
            _data(alma.criado_em),
        ]

        for coluna, valor in enumerate(valores, start=1):
            celula = aba.cell(row=linha, column=coluna, value=valor)
            celula.border = BORDA_FINA

    # ATENCAO: a observacao sensivel NAO entra na planilha, de proposito.
    # Ela e o campo mais delicado do sistema (secao 7, item 11) e um arquivo
    # de Excel circula por e-mail, WhatsApp e pen drive sem controle nenhum.
    # Quem precisa dela le na ficha, e a leitura fica registrada na auditoria.

    _formatar_aba(aba, colunas, len(almas))
    return len(almas)


# ===========================================================================
# ABA 2 - CONTATOS
# ===========================================================================
def _aba_contatos(planilha):
    aba = planilha.create_sheet("Contatos")

    colunas = [
        ("Codigo da alma", 14), ("Nome da alma", 30),
        ("Data e hora do contato", 20), ("Tipo", 13), ("Resultado", 24),
        ("Relato", 60), ("Registrado por", 22), ("Registrado em", 20),
    ]

    contatos = db.session.execute(
        db.select(Contato)
        .join(NovoConvertido, Contato.convertido_id == NovoConvertido.id)
        .where(NovoConvertido.mesclado_em_id.is_(None))
        .order_by(Contato.data_hora.desc())
    ).scalars().all()

    for linha, c in enumerate(contatos, start=2):
        valores = [
            c.convertido.codigo_formatado if c.convertido else "",
            c.convertido.nome_completo if c.convertido else "",
            _data(c.data_hora),
            c.tipo_rotulo,
            c.resultado_rotulo,
            c.relato,
            c.responsavel.nome if c.responsavel else "",
            _data(c.criado_em),
        ]
        for coluna, valor in enumerate(valores, start=1):
            celula = aba.cell(row=linha, column=coluna, value=valor)
            celula.border = BORDA_FINA
            if coluna == 6:                       # a coluna do relato
                celula.alignment = Alignment(wrap_text=True, vertical="top")

    _formatar_aba(aba, colunas, len(contatos))
    return len(contatos)


# ===========================================================================
# ABA 3 - PRESENCAS
# ===========================================================================
def _aba_presencas(planilha):
    aba = planilha.create_sheet("Presencas")

    colunas = [
        ("Codigo da alma", 14), ("Nome da alma", 30),
        ("Evento", 26), ("Tipo do evento", 20), ("Data do evento", 15),
        ("Esteve presente", 15), ("Registrado por", 22), ("Registrado em", 20),
    ]

    presencas = db.session.execute(
        db.select(Presenca)
        .join(NovoConvertido, Presenca.convertido_id == NovoConvertido.id)
        .join(Evento, Presenca.evento_id == Evento.id)
        .where(NovoConvertido.mesclado_em_id.is_(None))
        .order_by(Evento.data.desc())
    ).scalars().all()

    for linha, p in enumerate(presencas, start=2):
        valores = [
            p.convertido.codigo_formatado if p.convertido else "",
            p.convertido.nome_completo if p.convertido else "",
            p.evento.nome if p.evento else "",
            p.evento.tipo_rotulo if p.evento else "",
            _data(p.evento.data) if p.evento else "",
            _sim_nao(p.presente),
            p.registrado_por.nome if p.registrado_por else "",
            _data(p.registrado_em),
        ]
        for coluna, valor in enumerate(valores, start=1):
            celula = aba.cell(row=linha, column=coluna, value=valor)
            celula.border = BORDA_FINA

    _formatar_aba(aba, colunas, len(presencas))
    return len(presencas)


# ===========================================================================
# ABA 4 - RESPONSAVEIS
# ===========================================================================
def _aba_responsaveis(planilha):
    aba = planilha.create_sheet("Responsaveis")

    colunas = [
        ("Nome", 26), ("Login", 18), ("Papel", 16), ("Telefone", 17),
        ("Acesso ativo", 13), ("Almas acompanhando", 18),
        ("Em dia (verde)", 14), ("Em atencao", 12), ("Criticas", 10),
        ("% em dia", 10), ("Contatos registrados", 19),
        ("Dias medios entre contatos", 24), ("Criado em", 16),
    ]

    from app.rotas.responsaveis import calcular_carga

    carga = calcular_carga()

    for linha, c in enumerate(carga, start=2):
        u = c["usuario"]
        valores = [
            u.nome, u.login, u.papel_rotulo,
            formatar_telefone(u.telefone) if u.telefone else "",
            _sim_nao(u.ativo),
            c["almas"], c["verde"], c["atencao"], c["criticas"],
            c["percentual"] if c["percentual"] is not None else "",
            c["contatos"],
            c["dias_medios"] if c["dias_medios"] is not None else "",
            _data(u.criado_em),
        ]
        for coluna, valor in enumerate(valores, start=1):
            celula = aba.cell(row=linha, column=coluna, value=valor)
            celula.border = BORDA_FINA

    # A senha NUNCA entra aqui - nem o hash. Um hash bcrypt numa planilha que
    # circula por WhatsApp e material para ataque offline.

    _formatar_aba(aba, colunas, len(carga))
    return len(carga)


# ===========================================================================
# ABA 5 - RESUMO (a capa da planilha)
# ===========================================================================
def _aba_resumo(planilha, contagens):
    """
    Uma capa curta: quando foi gerado, por quem, e os numeros principais.

    Serve para quando a planilha reaparecer daqui a seis meses no e-mail de
    alguem e ninguem lembrar de que data ela e.
    """
    from flask import current_app
    from flask_login import current_user
    from app import relatorios

    aba = planilha.create_sheet("Resumo", 0)   # 0 = vira a PRIMEIRA aba
    aba.column_dimensions["A"].width = 34
    aba.column_dimensions["B"].width = 28

    dados = relatorios.tudo()

    def escrever(linha, rotulo, valor, negrito=False):
        a = aba.cell(row=linha, column=1, value=rotulo)
        b = aba.cell(row=linha, column=2, value=valor)
        if negrito:
            a.font = Font(bold=True)
            b.font = Font(bold=True)
        return linha + 1

    linha = 1
    titulo = aba.cell(row=1, column=1, value=current_app.config["IGREJA_NOME_LEGAL"])
    titulo.font = Font(size=14, bold=True)
    linha = 3

    linha = escrever(linha, "Relatorio gerado em", _data(agora()))
    try:
        linha = escrever(linha, "Gerado por", current_user.nome)
    except Exception:
        linha = escrever(linha, "Gerado por", "sistema")
    linha += 1

    linha = escrever(linha, "NUMEROS GERAIS", "", negrito=True)
    linha = escrever(linha, "Total de almas cadastradas", dados["resumo"]["total"])
    linha = escrever(linha, "Em acompanhamento", dados["resumo"]["em_acompanhamento"])
    linha = escrever(linha, "Integradas", dados["resumo"]["integradas"])
    linha = escrever(linha, "Contatos registrados", dados["resumo"]["contatos"])

    ret = dados["retencao"]
    if ret["percentual"] is not None:
        linha = escrever(
            linha,
            f"Retencao ({ret['dias']} dias)",
            f"{ret['percentual']}% ({ret['presentes']} de {ret['total']})",
        )
    linha += 1

    linha = escrever(linha, "LINHAS EM CADA ABA", "", negrito=True)
    for nome, n in contagens.items():
        linha = escrever(linha, nome, n)

    linha += 1
    aviso = aba.cell(
        row=linha, column=1,
        value="ATENCAO: esta planilha contem dados pessoais (LGPD). "
              "Nao compartilhe fora da equipe pastoral.",
    )
    aviso.font = Font(bold=True, color="FFC13B34")   # o vermelho da marca


# ===========================================================================
# A FUNCAO PRINCIPAL
# ===========================================================================
def gerar_planilha():
    """
    Monta a planilha inteira e devolve os bytes dela.

    Devolve (conteudo_em_bytes, nome_do_arquivo).
    """
    planilha = Workbook()

    contagens = {
        "Novos Convertidos": _aba_convertidos(planilha),
        "Contatos": _aba_contatos(planilha),
        "Presencas": _aba_presencas(planilha),
        "Responsaveis": _aba_responsaveis(planilha),
    }

    _aba_resumo(planilha, contagens)

    # BytesIO e um "arquivo de mentira" que vive na memoria RAM. A planilha e
    # escrita nele, entregue ao navegador e some. Nada toca o disco do servidor.
    buffer = BytesIO()
    planilha.save(buffer)
    buffer.seek(0)

    nome = f"adba-novos-convertidos-{hoje().strftime('%Y-%m-%d')}.xlsx"

    return buffer, nome, contagens
