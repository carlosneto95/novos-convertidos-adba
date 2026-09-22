# -*- coding: utf-8 -*-
"""
app/seguranca.py - AS TRAVAS DAS ROTAS.

Um "decorador" e uma etiqueta colada acima de uma funcao que a envolve com
comportamento extra. Na pratica:

    @admin_necessario
    def relatorios():
        ...

...significa "antes de executar relatorios(), confira se quem chamou e Admin.
Se nao for, nem execute: devolva 403".

POR QUE ISSO IMPORTA (secao 7, item 2 e 3):
Esconder um botao no HTML NAO e seguranca. Quem souber a URL digita direto no
navegador e entra. A unica trava que vale e esta aqui, no servidor, ANTES de
a funcao rodar.
"""

# --- IMPORTACOES ----------------------------------------------------------
from functools import wraps                 # preserva o nome da funcao decorada
from flask import abort, redirect, url_for, flash, request
from flask_login import current_user

from app import auditoria


def _negar(motivo, entidade=None, entidade_id=None):
    """Registra a tentativa de acesso indevido e devolve 403."""
    auditoria.registrar(
        acao=auditoria.ACESSO_NEGADO,
        entidade=entidade,
        entidade_id=entidade_id,
        detalhe=f"{motivo} | rota: {request.path}",
        gravar=True,
    )
    abort(403)      # interrompe tudo e mostra a pagina "Acesso nao autorizado"


# ===========================================================================
# TRAVA 1: SO ADMIN
# ===========================================================================
def admin_necessario(f):
    """
    Protege as telas exclusivas do Admin: Responsaveis, Relatorios, Mesclagem,
    designacao e transferencia de almas.
    """

    @wraps(f)                               # mantem o nome original da funcao
    def envolvida(*args, **kwargs):
        # 1. Esta logado?
        if not current_user.is_authenticated:
            flash("Faca login para acessar esta pagina.", "aviso")
            return redirect(url_for("auth.login", next=request.path))

        # 2. E Admin? O papel e lido do BANCO a cada requisicao, nunca do
        #    cookie - por isso nao da para se promover editando o navegador.
        if not current_user.eh_admin:
            _negar("Tentou acessar area exclusiva do Admin")

        # 3. Tudo certo: executa a funcao de verdade.
        return f(*args, **kwargs)

    return envolvida


# ===========================================================================
# TRAVA 2: A ALMA E MINHA?  (secao 7, item 2 - IDOR)
# ===========================================================================
def pode_ver_alma(alma, usuario=None):
    """
    Responde SIM ou NAO para "esta pessoa pode abrir a ficha desta alma?".

    A regra:
      - Admin ve todas.
      - Responsavel ve APENAS as almas designadas a ele NESTE momento.

    Usada em dois lugares:
      - no decorador abaixo, para barrar o acesso
      - nos templates, para decidir se mostra um botao

    IMPORTANTE: mesmo que um template esqueca de esconder um botao, o
    decorador barra. Nunca dependemos so da tela.
    """
    if usuario is None:
        usuario = current_user

    if not usuario or not usuario.is_authenticated:
        return False

    if usuario.eh_admin:
        return True

    return alma.responsavel_atual_id == usuario.id


def dono_da_alma_necessario(f):
    """
    Para rotas que recebem o id da alma na URL, como:
        /alma/<alma_id>/contato

    O decorador busca a alma, confere a permissao e ENTREGA o objeto pronto
    para a funcao - que nem precisa buscar de novo.

    E esta trava que faz um responsavel curioso, digitando o UUID de outra
    alma na barra de endereco, receber 403 em vez da ficha.
    """

    @wraps(f)
    def envolvida(*args, **kwargs):
        from app.extensions import db
        from app.models import NovoConvertido

        # 1. Esta logado?
        if not current_user.is_authenticated:
            flash("Faca login para acessar esta pagina.", "aviso")
            return redirect(url_for("auth.login", next=request.path))

        # 2. Pega o id da URL. Aceita os dois nomes mais usados.
        alma_id = kwargs.get("alma_id") or kwargs.get("convertido_id")
        if not alma_id:
            abort(404)

        # 3. Busca no banco. Nao achou = 404.
        alma = db.session.get(NovoConvertido, alma_id)
        if alma is None:
            abort(404)

        # 4. A trava de verdade.
        if not pode_ver_alma(alma):
            _negar(
                "Tentou abrir alma de outro responsavel",
                entidade="novo_convertido",
                entidade_id=alma_id,
            )

        # 5. Entrega a alma ja carregada para a funcao.
        kwargs["alma"] = alma
        return f(*args, **kwargs)

    return envolvida


# ===========================================================================
# TRAVA 3: OBSERVACAO SENSIVEL  (secao 7, item 11)
# ===========================================================================
def pode_ver_observacao_sensivel(alma, usuario=None):
    """
    O campo "observacao sensivel" guarda informacao intima: situacao familiar,
    vicio, saude mental.

    Regra: so o Admin e o responsavel ATUAL daquela alma. Um responsavel que
    cuidou dela no passado perde o acesso ao ser substituido.

    A leitura em si e registrada em auditoria pela rota que exibe o campo.
    """
    from flask import current_app

    if usuario is None:
        usuario = current_user

    if not usuario or not usuario.is_authenticated:
        return False

    # A chave de config permite desligar a restricao sem mexer no codigo.
    if not current_app.config.get("OBSERVACAO_SENSIVEL_RESTRITA", True):
        return True

    if usuario.eh_admin:
        return True

    return alma.responsavel_atual_id == usuario.id


# ===========================================================================
# PROTECAO CONTRA REDIRECIONAMENTO MALICIOSO
# ===========================================================================
def destino_seguro(destino, padrao="/painel"):
    """
    Depois do login, o sistema manda a pessoa para onde ela queria ir. Esse
    endereco vem na URL, assim: /login?next=/relatorios

    O PERIGO: um golpista manda o link
        /login?next=https://banco-falso.com
    A pessoa faz login no NOSSO sistema, confia, e e jogada num site clonado
    que pede a senha de novo. Chama-se "open redirect".

    A DEFESA: so aceitamos enderecos que comecam com uma barra unica - ou
    seja, que apontam para dentro do proprio sistema.
        "/painel"                 -> aceito
        "https://site-falso.com"  -> recusado
        "//site-falso.com"        -> recusado (o navegador trata como externo)
        "\\\\site-falso.com"          -> recusado
    """
    if not destino:
        return padrao

    destino = str(destino).strip()

    if not destino.startswith("/"):         # endereco absoluto: recusa
        return padrao

    if destino.startswith("//"):            # "//site.com" vira externo: recusa
        return padrao

    if destino.startswith("/\\") or "\\" in destino[:2]:
        return padrao

    return destino
