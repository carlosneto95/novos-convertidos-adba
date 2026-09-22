# -*- coding: utf-8 -*-
"""
app/tempo.py - TUDO QUE ENVOLVE DATA E HORA.

POR QUE UM ARQUIVO SO PARA ISSO?
O semaforo (secao 4) e inteiro baseado em "quantos dias desde...". Se a conta
das horas estiver errada, o sistema inteiro mente para o pastor.

A ARMADILHA: o seu computador esta no horario de Brasilia (UTC-3), mas o
servidor do PythonAnywhere roda em UTC. Se gravassemos "a hora do relogio"
sem dizer qual fuso, uma alma cadastrada as 22h de terca no Brasil viraria
quarta-feira no servidor - e o relogio do semaforo pularia um dia sozinho.

A SOLUCAO padrao do mercado:
  GRAVAR sempre em UTC (o "horario zero" do mundo).
  EXIBIR sempre convertido para o horario de Brasilia.

Assim o sistema da a mesma resposta no seu PC e no servidor.
"""

# --- IMPORTACOES ----------------------------------------------------------
from datetime import datetime, timezone, date   # tipos de data e hora do Python
from zoneinfo import ZoneInfo                   # fusos horarios (ja vem no Python 3.9+)


# --- O FUSO DA IGREJA -----------------------------------------------------
# "America/Sao_Paulo" cuida sozinho de horario de verao, se um dia voltar.
FUSO_BRASIL = ZoneInfo("America/Sao_Paulo")
FUSO_UTC = timezone.utc


# ===========================================================================
# GRAVACAO
# ===========================================================================
def agora():
    """
    A hora de AGORA em UTC, com o fuso anexado.

    Esta funcao e o valor padrao de todo campo DateTime dos modelos.
    Note que passamos a funcao (sem parenteses) para o SQLAlchemy: assim ele
    chama na hora de gravar cada linha, e nao uma unica vez quando o sistema
    sobe.
    """
    return datetime.now(FUSO_UTC)


def hoje():
    """A data de hoje no calendario de Brasilia (nao em UTC)."""
    # Se sao 21h de segunda no Brasil, em UTC ja e terca. Para "data de
    # conversao" e "data do culto", o que vale e o calendario daqui.
    return datetime.now(FUSO_BRASIL).date()


# ===========================================================================
# CONVERSAO
# ===========================================================================
def garantir_utc(momento):
    """
    Garante que uma data/hora tenha fuso anexado.

    O SQLite nao guarda o fuso junto: ele devolve a data "pelada". Se tentarmos
    subtrair uma data pelada de uma data com fuso, o Python levanta erro. Esta
    funcao assume que toda data pelada vinda do banco esta em UTC - que e
    verdade, porque e assim que gravamos.
    """
    if momento is None:
        return None
    if momento.tzinfo is None:                       # data "pelada", sem fuso
        return momento.replace(tzinfo=FUSO_UTC)      # anexa UTC sem mudar os numeros
    return momento.astimezone(FUSO_UTC)              # ja tinha fuso: converte para UTC


def para_local(momento):
    """Converte uma data/hora UTC para o horario de Brasilia, para exibir."""
    momento = garantir_utc(momento)
    if momento is None:
        return None
    return momento.astimezone(FUSO_BRASIL)


# ===========================================================================
# FORMATACAO PARA A TELA
# ===========================================================================
def formatar_data(valor):
    """Devolve 07/09/2026. Aceita datetime (converte o fuso) ou date."""
    if valor is None:
        return "-"
    if isinstance(valor, datetime):        # se tem hora junto, converte o fuso antes
        valor = para_local(valor).date()
    return valor.strftime("%d/%m/%Y")


def formatar_data_curta(valor):
    """Devolve 07/09 - o formato usado no relatorio do WhatsApp (secao 5.3)."""
    if valor is None:
        return "-"
    if isinstance(valor, datetime):
        valor = para_local(valor).date()
    return valor.strftime("%d/%m")


def formatar_data_hora(valor):
    """Devolve 07/09/2026 as 19:30, no horario de Brasilia."""
    if valor is None:
        return "-"
    return para_local(valor).strftime("%d/%m/%Y as %H:%M")


# ===========================================================================
# CONTAS DO SEMAFORO
# ===========================================================================
def horas_desde(momento):
    """
    Quantas HORAS se passaram desde o momento informado.
    Usado nos prazos curtos: 48h do primeiro contato, 24h para designar.
    Devolve None se o momento nao existir (ex: alma nunca designada).
    """
    momento = garantir_utc(momento)
    if momento is None:
        return None
    diferenca = agora() - momento                    # subtracao devolve um timedelta
    return diferenca.total_seconds() / 3600.0        # segundos -> horas


def dias_desde(momento):
    """
    Quantos DIAS INTEIROS se passaram desde o momento informado.

    Usa int(), que arredonda para baixo: 47 horas viram 1 dia, nao 2.
    E o comportamento correto para o texto "X dias sem contato".
    """
    horas = horas_desde(momento)
    if horas is None:
        return None
    return int(horas // 24)                          # // e divisao inteira


def calcular_idade(data_nascimento, referencia=None):
    """
    Idade em anos completos.

    A conta e mais sutil do que parece: nao basta subtrair os anos. Se a pessoa
    nasceu em 20/12/2000 e hoje e 10/09/2026, ela ainda tem 25 - nao 26, porque
    o aniversario deste ano ainda nao chegou.

    O truque: (mes, dia) de hoje < (mes, dia) do nascimento? Entao subtrai 1.
    """
    if data_nascimento is None:
        return None
    if referencia is None:
        referencia = hoje()
    if isinstance(referencia, datetime):
        referencia = para_local(referencia).date()

    anos = referencia.year - data_nascimento.year                     # diferenca bruta de anos
    aniversario_ja_passou = (referencia.month, referencia.day) >= (   # compara mes e dia
        data_nascimento.month,
        data_nascimento.day,
    )
    if not aniversario_ja_passou:      # o aniversario deste ano ainda nao chegou
        anos -= 1
    return anos


def eh_menor_de_idade(data_nascimento, maioridade=18, referencia=None):
    """
    True se a pessoa for menor de idade.

    E esta funcao que dispara a exigencia do responsavel legal no formulario
    publico (secao 5.1) - validada NO SERVIDOR, nao so no navegador.
    """
    idade = calcular_idade(data_nascimento, referencia)
    if idade is None:
        return False
    return idade < maioridade
