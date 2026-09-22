# -*- coding: utf-8 -*-
"""
app/rotas/eventos.py - A AGENDA DE CULTOS (secao 5.5).

    /eventos                        lista os proximos e os passados
    POST /eventos/criar             cadastra um evento pontual (so Admin)
    POST /eventos/<id>/cancelar     cancela ou reativa (so Admin)
    POST /eventos/gerar-agenda      estende os cultos recorrentes (so Admin)

QUEM VE O QUE (secao 5):
    Admin       - ve e cadastra
    Responsavel - so visualiza

O Responsavel precisa ver a agenda para saber em qual culto marcar presenca.
Mas nao pode criar eventos: se cada um cadastrasse o seu, a agenda viraria
uma bagunca e as presencas ficariam espalhadas em cultos duplicados.
"""

# --- IMPORTACOES ----------------------------------------------------------
from datetime import timedelta

from flask import Blueprint, render_template, redirect, url_for, flash, abort, current_app
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Evento, Presenca
from app import opcoes, auditoria
from app.seguranca import admin_necessario
from app.tempo import agora, hoje


eventos = Blueprint("eventos", __name__)


# ===========================================================================
# A TELA
# ===========================================================================
@eventos.route("/eventos")
@login_required
def index():
    """Lista a agenda, separada entre o que vem e o que ja passou."""
    from app.forms import EventoForm

    hoje_ = hoje()

    # --- Os proximos (de hoje para a frente) ------------------------------
    proximos = db.session.execute(
        db.select(Evento)
        .where(Evento.data >= hoje_)
        .order_by(Evento.data.asc())      # o mais proximo primeiro
    ).scalars().all()

    # --- Os passados (ate 90 dias atras) ----------------------------------
    # Nao trazemos a agenda inteira: com o tempo seriam centenas de cultos
    # que ninguem consulta. 90 dias cobre o que ainda interessa.
    passados = db.session.execute(
        db.select(Evento)
        .where(
            Evento.data < hoje_,
            Evento.data >= hoje_ - timedelta(days=90),
        )
        .order_by(Evento.data.desc())     # o mais recente primeiro
    ).scalars().all()

    # --- Quantas presencas ja foram marcadas em cada evento ---------------
    # Uma consulta so, com GROUP BY - nunca uma por evento.
    ids = [e.id for e in proximos + passados]
    contagem_presencas = {}
    if ids:
        linhas = db.session.execute(
            db.select(Presenca.evento_id, db.func.count(Presenca.id))
            .where(Presenca.evento_id.in_(ids), Presenca.presente.is_(True))
            .group_by(Presenca.evento_id)
        ).all()
        contagem_presencas = {linha[0]: linha[1] for linha in linhas}

    return render_template(
        "eventos/index.html",
        proximos=proximos,
        passados=passados,
        contagem_presencas=contagem_presencas,
        form=EventoForm(),
        hoje=hoje_,
    )


# ===========================================================================
# CADASTRAR EVENTO PONTUAL (so Admin)
# ===========================================================================
@eventos.route("/eventos/criar", methods=["POST"])
@admin_necessario
def criar():
    """Cadastra uma vigilia, um congresso, um evento fora da rotina."""
    from app.forms import EventoForm

    form = EventoForm()

    if not form.validate_on_submit():
        mensagens = [e for campo in form for e in campo.errors]
        flash(" ".join(mensagens) or "Confira os campos.", "erro")
        return redirect(url_for("eventos.index"))

    # A tabela tem UNIQUE(tipo, data). Sem esta checagem, cadastrar um
    # repetido estouraria um erro de banco na cara do usuario.
    ja_existe = db.session.execute(
        db.select(Evento).where(
            Evento.tipo == form.tipo.data,
            Evento.data == form.data.data,
        )
    ).scalar_one_or_none()

    if ja_existe:
        flash(
            f"Já existe um {opcoes.rotulo(opcoes.TIPOS_EVENTO, form.tipo.data)} "
            f"nesta data.",
            "aviso",
        )
        return redirect(url_for("eventos.index"))

    evento = Evento(
        nome=(form.nome.data or "").strip()[:150],
        tipo=form.tipo.data,
        data=form.data.data,
        recorrente=False,            # foi cadastrado a mao, nao pelo seed
        criado_por_id=current_user.id,
        ativo=True,
        criado_em=agora(),
    )
    db.session.add(evento)
    db.session.flush()

    auditoria.registrar(
        acao="evento_criado",
        entidade="evento",
        entidade_id=evento.id,
        detalhe=f"{evento.nome} em {evento.data}",
    )

    db.session.commit()

    flash(f"{evento.nome} cadastrado para {evento.data.strftime('%d/%m/%Y')}.", "sucesso")
    return redirect(url_for("eventos.index"))


# ===========================================================================
# CANCELAR / REATIVAR (so Admin)
# ===========================================================================
@eventos.route("/eventos/<evento_id>/cancelar", methods=["POST"])
@admin_necessario
def cancelar(evento_id):
    """
    Cancela um culto (chuva, feriado) ou volta atras.

    NUNCA apagamos o evento. As presencas ja marcadas apontam para ele: se
    o apagássemos, o banco recusaria - ou, pior, o historico de frequencia
    de varias almas sumiria junto.
    """
    evento = db.session.get(Evento, evento_id)
    if evento is None:
        abort(404)

    evento.ativo = not evento.ativo

    auditoria.registrar(
        acao="evento_reativado" if evento.ativo else "evento_cancelado",
        entidade="evento",
        entidade_id=evento.id,
        detalhe=f"{evento.nome} em {evento.data}",
    )

    db.session.commit()

    if evento.ativo:
        flash(f"{evento.nome} voltou para a agenda.", "sucesso")
    else:
        marcadas = db.session.scalar(
            db.select(db.func.count()).select_from(Presenca)
            .where(Presenca.evento_id == evento.id)
        )
        aviso = f"{evento.nome} de {evento.data.strftime('%d/%m')} foi cancelado."
        if marcadas:
            aviso += f" As {marcadas} presença(s) já marcadas continuam no histórico."
        flash(aviso, "aviso")

    return redirect(url_for("eventos.index"))


# ===========================================================================
# ESTENDER A AGENDA (so Admin)
# ===========================================================================
@eventos.route("/eventos/gerar-agenda", methods=["POST"])
@admin_necessario
def gerar_agenda():
    """
    Gera os cultos de domingo e terca para os proximos 90 dias.

    E o mesmo trabalho do comando "flask seed-eventos", mas por um botao -
    para o Admin nao precisar de terminal. A agenda acaba, e quando acabar
    ninguem consegue marcar presenca.
    """
    from app.comandos import CULTOS_RECORRENTES

    dias = current_app.config.get("DIAS_AGENDA_EVENTOS", 90)
    inicio = hoje()
    fim = inicio + timedelta(days=dias)

    # O que ja existe no periodo, de uma vez so.
    existentes = {
        (linha.tipo, linha.data)
        for linha in db.session.execute(
            db.select(Evento.tipo, Evento.data).where(
                Evento.data >= inicio, Evento.data <= fim
            )
        ).all()
    }

    criados = 0
    data_atual = inicio
    while data_atual <= fim:
        for culto in CULTOS_RECORRENTES:
            if data_atual.weekday() != culto["dia_semana"]:
                continue
            if (culto["tipo"], data_atual) in existentes:
                continue
            db.session.add(
                Evento(
                    nome=culto["nome"],
                    tipo=culto["tipo"],
                    data=data_atual,
                    recorrente=True,
                    criado_por_id=current_user.id,
                    ativo=True,
                    criado_em=agora(),
                )
            )
            criados += 1
        data_atual += timedelta(days=1)

    auditoria.registrar(
        acao="agenda_gerada",
        entidade="evento",
        detalhe=f"{criados} culto(s) gerado(s) ate {fim}",
    )

    db.session.commit()

    if criados:
        flash(
            f"{criados} culto(s) gerado(s) até {fim.strftime('%d/%m/%Y')}.",
            "sucesso",
        )
    else:
        flash("A agenda já estava completa. Nada foi criado.", "aviso")

    return redirect(url_for("eventos.index"))
