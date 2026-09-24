# -*- coding: utf-8 -*-
"""
app/semaforo.py - O CORACAO DO SISTEMA (secao 4 da especificacao).

Este arquivo responde a UMA pergunta, para cada alma:

    "De que cor e este card, e por que?"

TODO o calculo acontece AQUI, no servidor. O HTML so recebe a cor pronta e
pinta. Isso importa por dois motivos:
  1. A regra fica num lugar so, facil de auditar e de mudar.
  2. O navegador nao tem como "discordar" do sistema.

-----------------------------------------------------------------------------
OS DOIS RELOGIOS
-----------------------------------------------------------------------------
Cada alma tem DOIS relogios que andam ao mesmo tempo:

  1. RELOGIO DA TENTATIVA  - conta desde a ultima vez que alguem TENTOU falar
                             com ela, com qualquer resultado.
                             MEDE O RESPONSAVEL: ele esta trabalhando?

  2. RELOGIO DO EFETIVO    - conta desde a ultima vez que alguem CONSEGUIU
                             falar com ela.
                             MEDE A ALMA: ela esta respondendo?

Por que separar? Porque os dois problemas sao diferentes e pedem solucoes
diferentes:
  - Se o responsavel nao liga ha 20 dias, o problema e do responsavel.
  - Se ele ligou 8 vezes e ninguem atende, o problema nao e dele. Talvez o
    telefone esteja errado, ou a alma nao queira mais contato.

Um sistema que misturasse os dois puniria o responsavel dedicado e esconderia
o relapso.

-----------------------------------------------------------------------------
A COR
-----------------------------------------------------------------------------
A cor vem do PIOR dos dois relogios - o que tem mais dias:

     0 a 7 dias   VERDE      em dia
     8 a 14 dias  AMARELO    atencao
    15 a 21 dias  LARANJA    atrasado
    22+ dias      VERMELHO   critico

Fora do semaforo:
    ROXO   - "aguardando responsavel": ninguem cuida dela ainda.
             So aparece no painel do Admin, com relogio proprio (meta 24h).
    AZUL   - "aguardando primeiro contato": ja tem responsavel, ninguem
             tentou contato ainda e as 48h ainda nao passaram.
    CINZA  - qualquer outro status (integrado, mudou de cidade...).
             Sai do painel principal; fica acessivel por filtro.
"""

# --- IMPORTACOES ----------------------------------------------------------
from flask import current_app

from app import opcoes
from app.tempo import agora, garantir_utc, horas_desde, dias_desde


# ===========================================================================
# O RESULTADO DO CALCULO
# ===========================================================================
class Semaforo:
    """
    Guarda tudo que a tela precisa saber sobre uma alma, ja mastigado.

    O template nao faz conta nenhuma: ele so le estes atributos.
    """

    def __init__(self, cor, dias, icone=None, motivo="", dias_tentativa=None,
                 dias_efetivo=None, estourou=False, no_semaforo=True):
        self.cor = cor                       # "verde" | "amarelo" | "laranja" | "vermelho" | "roxo" | "azul" | "cinza"
        self.dias = dias                     # o numero que aparece no card
        self.icone = icone                   # "sem-contato" | "sem-resposta" | None
        self.motivo = motivo                 # frase curta explicando (vai no titulo do card)
        self.dias_tentativa = dias_tentativa # relogio 1
        self.dias_efetivo = dias_efetivo     # relogio 2
        self.estourou = estourou             # True = passou do prazo
        self.no_semaforo = no_semaforo       # False = nao entra na contagem do painel

    # --- Atalhos para o HTML ---------------------------------------------
    @property
    def hex(self):
        """O codigo da cor, vindo do config.py. Ex: "#16a34a"."""
        return current_app.config["CORES_SEMAFORO"].get(self.cor, "#94a3b8")

    @property
    def classe_borda(self):
        """A classe Tailwind da barra lateral colorida do card."""
        return {
            "verde": "bg-semaforo-verde",
            "amarelo": "bg-semaforo-amarelo",
            "laranja": "bg-semaforo-laranja",
            "vermelho": "bg-semaforo-vermelho",
            "roxo": "bg-semaforo-roxo",
            "azul": "bg-semaforo-azul",
        }.get(self.cor, "bg-slate-300")

    @property
    def classe_circulo(self):
        """A classe do circulo com a inicial do nome."""
        return {
            "verde": "bg-semaforo-verde",
            "amarelo": "bg-semaforo-amarelo",
            "laranja": "bg-semaforo-laranja",
            "vermelho": "bg-semaforo-vermelho",
            "roxo": "bg-semaforo-roxo",
            "azul": "bg-semaforo-azul",
        }.get(self.cor, "bg-slate-400")

    @property
    def texto_dias(self):
        """A frase que aparece no card. Ex: "12 dias sem contato"."""
        if self.cor == "roxo":
            if self.dias == 0:
                return "Aguardando responsável desde hoje"
            if self.dias == 1:
                return "Aguardando responsável há 1 dia"
            return f"Aguardando responsável há {self.dias} dias"

        if self.cor == "azul":
            if self.dias == 0:
                return "Aguardando primeiro contato desde hoje"
            if self.dias == 1:
                return "Aguardando primeiro contato há 1 dia"
            return f"Aguardando primeiro contato há {self.dias} dias"

        if not self.no_semaforo:
            return self.motivo

        if self.dias is None:
            return "Sem informação"
        if self.dias == 0:
            return "Contato hoje"
        if self.dias == 1:
            return "1 dia sem contato"
        return f"{self.dias} dias sem contato"

    @property
    def texto_curto(self):
        """
        A versao curta, para a coluna da lista.

        A coluna tem 9rem (cerca de 144px). "Aguardando responsavel ha 3 dias"
        nao cabe e quebra em duas linhas, desalinhando a tabela inteira - foi
        exatamente o que aconteceu na primeira versao. Aqui so o essencial;
        o texto completo continua no "title" (aparece ao parar o mouse).
        """
        if not self.no_semaforo and self.cor == "cinza":
            return self.motivo

        # Azul: o que importa e o estado, nao os dias (sao no maximo 2).
        if self.cor == "azul":
            return "aguarda 1º contato"

        if self.dias is None:
            return "—"
        if self.dias == 0:
            return "hoje"
        if self.dias == 1:
            return "1 dia"
        return f"{self.dias} dias"

    def __repr__(self):
        return f"<Semaforo {self.cor} {self.dias}d>"


# ===========================================================================
# DA QUANTIDADE DE DIAS PARA A COR
# ===========================================================================
def cor_por_dias(dias):
    """
    Traduz "quantos dias" em "que cor".

    As faixas vem do config.py (FAIXAS_SEMAFORO), entao o pastor pode mudar
    os prazos sem que ninguem mexa neste arquivo.
    """
    if dias is None:
        return "cinza"

    faixas = current_app.config["FAIXAS_SEMAFORO"]

    if dias <= faixas["verde"]:         # ate 7 dias
        return "verde"
    if dias <= faixas["amarelo"]:       # ate 14
        return "amarelo"
    if dias <= faixas["laranja"]:       # ate 21
        return "laranja"
    return "vermelho"                   # 22 ou mais


# ===========================================================================
# O CALCULO PRINCIPAL
# ===========================================================================
def calcular(alma, ultima_tentativa=None, ultimo_efetivo=None):
    """
    Calcula o semaforo de uma alma.

    Parametros:
        alma             - o objeto NovoConvertido
        ultima_tentativa - data/hora do ultimo contato de QUALQUER tipo
        ultimo_efetivo   - data/hora do ultimo contato EFETIVO

    POR QUE AS DATAS VEM DE FORA?
    Se esta funcao fosse buscar os contatos no banco, uma tela com 200 almas
    faria 400 consultas - e levaria segundos para abrir. O painel busca tudo
    de uma vez, numa consulta so, e passa os valores prontos para ca.
    Isso se chama evitar o "problema N+1".
    """

    # =====================================================================
    # CASO 1 - DUPLICATA MESCLADA
    # =====================================================================
    # Some do painel, mas nunca e apagada do banco (secao 5.7).
    if alma.mesclado_em_id is not None:
        return Semaforo(
            cor="cinza", dias=None, motivo="Registro duplicado (mesclado)",
            no_semaforo=False,
        )

    # =====================================================================
    # CASO 2 - AGUARDANDO RESPONSAVEL -> ROXO
    # =====================================================================
    # Excecao da secao 4: relogio proprio, meta de 24h para o Admin designar.
    if alma.status_ciclo == opcoes.STATUS_INICIAL:
        horas = horas_desde(alma.criado_em) or 0
        dias = dias_desde(alma.criado_em) or 0
        meta = current_app.config.get("PRAZO_DESIGNACAO_HORAS", 24)

        return Semaforo(
            cor="roxo",
            dias=dias,
            icone="alerta",
            motivo=(
                f"Cadastrada há {int(horas)}h e ainda sem responsável "
                f"(meta: {meta}h)"
            ),
            estourou=horas > meta,
            no_semaforo=False,      # nao entra na contagem verde/amarelo/vermelho
        )

    # =====================================================================
    # CASO 3 - STATUS ENCERRADO -> CINZA
    # =====================================================================
    # Integrado, mudou de cidade, nao deseja contato... Sai do semaforo
    # (secao 4, "Excecoes"). Fica acessivel por filtro.
    if alma.status_ciclo != opcoes.STATUS_ATIVO:
        return Semaforo(
            cor="cinza", dias=None,
            motivo=opcoes.rotulo(opcoes.STATUS_CICLO, alma.status_ciclo),
            no_semaforo=False,
        )

    # =====================================================================
    # CASO 4 - EM ACOMPANHAMENTO: O SEMAFORO DE VERDADE
    # =====================================================================

    # O "marco zero" dos dois relogios e a designacao. Se, por algum motivo,
    # a alma esta em acompanhamento sem data de designacao, usamos a data de
    # cadastro - assim o relogio nunca fica parado sem ninguem perceber.
    marco_zero = garantir_utc(alma.designado_em) or garantir_utc(alma.criado_em)

    ultima_tentativa = garantir_utc(ultima_tentativa)
    ultimo_efetivo = garantir_utc(ultimo_efetivo)

    # --- RELOGIO 1: a ultima tentativa ----------------------------------
    # Se ninguem nunca tentou, o relogio conta desde a designacao.
    referencia_tentativa = ultima_tentativa or marco_zero
    dias_tentativa = dias_desde(referencia_tentativa) or 0
    horas_tentativa = horas_desde(referencia_tentativa) or 0

    # --- RELOGIO 2: o ultimo contato efetivo ----------------------------
    referencia_efetivo = ultimo_efetivo or marco_zero
    dias_efetivo = dias_desde(referencia_efetivo) or 0
    horas_efetivo = horas_desde(referencia_efetivo) or 0

    # --- OS PRAZOS -------------------------------------------------------
    prazo_primeiro_h = current_app.config.get("PRAZO_PRIMEIRO_CONTATO_HORAS", 48)
    prazo_dias = current_app.config.get("PRAZO_CONTATO_DIAS", 7)

    # Alma recem-designada e sem NENHUM contato: prazo curto de 48 horas.
    # Esse e o momento mais importante do acompanhamento - quem nao e
    # procurado nos dois primeiros dias costuma nao voltar.
    #
    # Na TRANSFERENCIA, o campo designado_em e atualizado. Por isso o relogio
    # volta sozinho para 48h, exatamente como pede a secao 4 - sem nenhum
    # codigo especial aqui.
    if ultima_tentativa is None:
        estourou_tentativa = horas_tentativa > prazo_primeiro_h
    else:
        estourou_tentativa = dias_tentativa > prazo_dias

    if ultimo_efetivo is None:
        estourou_efetivo = horas_efetivo > prazo_primeiro_h
    else:
        estourou_efetivo = dias_efetivo > prazo_dias

    # --- CASO ESPECIAL: AGUARDANDO O PRIMEIRO CONTATO -> AZUL ------------
    # A alma acabou de ganhar responsavel e ninguem tentou falar com ela
    # ainda, mas as 48h NAO passaram. Antes ela ficava VERDE ("em dia"),
    # o que confundia: parecia que o acompanhamento ja tinha comecado.
    # O azul diz "o relogio esta correndo, o primeiro contato esta pendente".
    #
    # Quando as 48h estouram sem tentativa, ela sai do azul e cai na regra
    # normal logo abaixo (minimo AMARELO, com o icone de "nao tentou").
    if ultima_tentativa is None and not estourou_tentativa:
        return Semaforo(
            cor="azul",
            dias=dias_tentativa,
            motivo=(
                f"Designada há {int(horas_tentativa)}h, aguardando o primeiro "
                f"contato (prazo: {prazo_primeiro_h}h)"
            ),
            dias_tentativa=dias_tentativa,
            dias_efetivo=dias_efetivo,
            estourou=False,
            no_semaforo=True,       # conta em "Em acompanhamento"
        )

    # --- A COR: o PIOR dos dois relogios ---------------------------------
    # max() pega o maior numero de dias. O relogio mais atrasado manda.
    dias_pior = max(dias_tentativa, dias_efetivo)
    cor = cor_por_dias(dias_pior)

    # --- AJUSTE: prazo estourado nunca pode ficar VERDE ------------------
    # AQUI HA UM CONFLITO NA ESPECIFICACAO, e esta e a decisao que tomamos.
    #
    # O PROBLEMA:
    # A secao 4 diz duas coisas que brigam entre si numa situacao especifica.
    #   (a) "Alma designada e sem nenhum contato -> prazo de 48 horas."
    #   (b) a tabela de cores: "0 a 7 dias -> VERDE".
    #
    # Uma alma designada ha 3 dias, com ZERO tentativas de contato, estourou
    # o prazo de 48h (regra a) mas cairia no verde (regra b). O card diria
    # "em dia" sobre alguem que foi abandonado desde o primeiro dia - e a
    # regra das 48h viraria enfeite.
    #
    # A DECISAO:
    # Verde significa "dentro do prazo". Se o prazo estourou, o minimo e
    # AMARELO. A tabela de cores continua valendo para todo o resto.
    #
    # COMO REVERTER, se o pastor preferir a leitura literal:
    # apague o bloco de 3 linhas abaixo.
    if estourou_tentativa or estourou_efetivo:
        if cor == "verde":
            cor = "amarelo"

    # --- O ICONE: qual relogio estourou ----------------------------------
    # A ordem importa. Se o responsavel nao tentou, esse e O problema -
    # nao adianta dizer "a alma nao responde" se ninguem ligou para ela.
    icone = None
    motivo = "Em dia"

    if estourou_tentativa:
        icone = "sem-contato"           # 📵 da especificacao
        if ultima_tentativa is None:
            motivo = f"Designada há {int(horas_tentativa)}h e ninguém tentou contato ainda"
        else:
            motivo = f"O responsável não tenta contato há {dias_tentativa} dias"

    elif estourou_efetivo:
        icone = "sem-resposta"          # 🚫 da especificacao
        if ultimo_efetivo is None:
            motivo = "Há tentativas, mas ninguém conseguiu falar com ela ainda"
        else:
            motivo = f"Sem conversa efetiva há {dias_efetivo} dias"

    return Semaforo(
        cor=cor,
        dias=dias_pior,
        icone=icone,
        motivo=motivo,
        dias_tentativa=dias_tentativa,
        dias_efetivo=dias_efetivo,
        estourou=estourou_tentativa or estourou_efetivo,
        no_semaforo=True,
    )


# ===========================================================================
# CALCULO EM LOTE - usado pelo painel
# ===========================================================================
def calcular_muitas(almas, mapa_tentativas, mapa_efetivos):
    """
    Calcula o semaforo de uma lista de almas de uma vez.

    Parametros:
        almas           - a lista de NovoConvertido
        mapa_tentativas - {id_da_alma: data_do_ultimo_contato}
        mapa_efetivos   - {id_da_alma: data_do_ultimo_contato_efetivo}

    Devolve uma lista de pares (alma, semaforo), na mesma ordem.
    """
    resultado = []
    for alma in almas:
        s = calcular(
            alma,
            ultima_tentativa=mapa_tentativas.get(alma.id),
            ultimo_efetivo=mapa_efetivos.get(alma.id),
        )
        resultado.append((alma, s))
    return resultado


# ===========================================================================
# CONTAGEM PARA OS CARTOES DE KPI
# ===========================================================================
def contar_por_cor(pares):
    """
    Conta quantas almas ha de cada cor, para os cartoes do topo do painel.

    Recebe a lista de (alma, semaforo) e devolve um dicionario:
        {"verde": 12, "amarelo": 3, "laranja": 1, "vermelho": 2,
         "em_acompanhamento": 18, "atencao": 4}
    """
    contagem = {
        "verde": 0, "amarelo": 0, "laranja": 0, "vermelho": 0,
        "roxo": 0, "azul": 0, "cinza": 0,
    }

    for _alma, s in pares:
        if s.cor in contagem:
            contagem[s.cor] += 1

    # Totais derivados, para o template nao precisar somar nada.
    contagem["em_acompanhamento"] = (
        contagem["azul"] + contagem["verde"] + contagem["amarelo"]
        + contagem["laranja"] + contagem["vermelho"]
    )
    # "Em atencao" junta amarelo e laranja (secao 5.2).
    contagem["atencao"] = contagem["amarelo"] + contagem["laranja"]

    return contagem
