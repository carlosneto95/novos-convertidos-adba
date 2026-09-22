# -*- coding: utf-8 -*-
"""
app/rotas/admin.py - MESCLAGEM E AUDITORIA (secoes 5.7 e 7, item 13). SO ADMIN.

    /admin/duplicatas            sugestoes de registros repetidos
    POST /admin/mesclar          junta dois registros
    /admin/auditoria             a caixa-preta do sistema

SOBRE A AUDITORIA:
A tela e SO DE LEITURA, e isso nao e um detalhe. Um log que pode ser editado
nao serve para nada - a primeira coisa que alguem faria ao errar seria apagar
o proprio rastro. Por isso nao existe rota de alteracao nem de exclusao para
essa tabela em lugar nenhum do sistema (secao 7, item 13).
"""

# --- IMPORTACOES ----------------------------------------------------------
from datetime import timedelta

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import current_user

from app.extensions import db
from app.models import NovoConvertido, Usuario, LogAuditoria
from app import duplicatas as dup, auditoria
from app.seguranca import admin_necessario
from app.tempo import hoje


admin = Blueprint("admin", __name__)


# ===========================================================================
# TELA 1 - DUPLICATAS (secao 5.7)
# ===========================================================================
@admin.route("/admin/duplicatas")
@admin_necessario
def duplicatas():
    """Lista os pares suspeitos, do mais provavel para o menos."""
    pares = dup.encontrar_duplicatas()

    # Quantas ja foram mescladas alguma vez - so para mostrar o numero.
    ja_mescladas = db.session.scalar(
        db.select(db.func.count()).select_from(NovoConvertido)
        .where(NovoConvertido.mesclado_em_id.isnot(None))
    ) or 0

    return render_template(
        "admin/duplicatas.html",
        pares=pares,
        ja_mescladas=ja_mescladas,
    )


# ===========================================================================
# ACAO - MESCLAR
# ===========================================================================
@admin.route("/admin/mesclar", methods=["POST"])
@admin_necessario
def mesclar():
    """
    Junta dois registros.

    Os DOIS ids vem do formulario e os DOIS sao conferidos aqui. Nunca
    confiamos no que chegou da tela: alguem poderia mandar o id de uma alma
    que nao tem nada a ver e apagar o acompanhamento dela do painel.
    """
    id_principal = (request.form.get("principal_id") or "").strip()
    id_duplicata = (request.form.get("duplicata_id") or "").strip()

    principal = db.session.get(NovoConvertido, id_principal) if id_principal else None
    duplicata = db.session.get(NovoConvertido, id_duplicata) if id_duplicata else None

    if principal is None or duplicata is None:
        flash("Registro não encontrado. Nada foi alterado.", "erro")
        return redirect(url_for("admin.duplicatas"))

    try:
        resumo = dup.mesclar(principal, duplicata, usuario_id=current_user.id)
    except ValueError as e:
        # Mesclar consigo mesmo, ou mesclar o que ja foi mesclado.
        flash(str(e), "erro")
        return redirect(url_for("admin.duplicatas"))

    db.session.commit()

    # A mensagem diz EXATAMENTE o que se moveu. Numa operacao que junta duas
    # fichas de pessoas, "feito com sucesso" nao basta - o Admin precisa
    # conseguir conferir.
    partes = []
    if resumo["contatos"]:
        partes.append(f"{resumo['contatos']} contato(s)")
    if resumo["presencas"]:
        partes.append(f"{resumo['presencas']} presença(s)")
    if resumo["presencas_descartadas"]:
        partes.append(f"{resumo['presencas_descartadas']} presença(s) repetida(s) fundida(s)")
    if resumo["atribuicoes"]:
        partes.append(f"{resumo['atribuicoes']} registro(s) de responsável")
    if resumo["campos"]:
        partes.append(f"{len(resumo['campos'])} campo(s) completado(s)")

    detalhe = " · ".join(partes) if partes else "nada a transferir"

    flash(
        f"{duplicata.codigo_formatado} foi mesclada em "
        f"{principal.codigo_formatado} ({principal.nome_completo}). "
        f"Transferido: {detalhe}. O registro duplicado não foi apagado — "
        f"só saiu do painel.",
        "sucesso",
    )

    return redirect(url_for("admin.duplicatas"))


# ===========================================================================
# TELA 2 - AUDITORIA (secao 7, item 13)
# ===========================================================================
# Quantas linhas por pagina. O log cresce para sempre; sem paginacao, um dia
# esta tela tentaria desenhar 200 mil linhas de uma vez.
POR_PAGINA = 100


@admin.route("/admin/auditoria")
@admin_necessario
def registro_auditoria():
    """A caixa-preta: quem fez o que, quando e de onde. SO LEITURA."""

    f_acao = (request.args.get("acao") or "").strip()
    f_usuario = (request.args.get("usuario") or "").strip()
    f_dias = (request.args.get("dias") or "30").strip()
    pagina = max(1, int(request.args.get("pagina") or 1))

    consulta = db.select(LogAuditoria)

    if f_acao:
        consulta = consulta.where(LogAuditoria.acao == f_acao)

    if f_usuario:
        consulta = consulta.where(LogAuditoria.usuario_id == f_usuario)

    dias = {"7": 7, "30": 30, "90": 90, "365": 365}.get(f_dias)
    if dias:
        consulta = consulta.where(
            LogAuditoria.criado_em >= hoje() - timedelta(days=dias)
        )

    total = db.session.scalar(
        db.select(db.func.count()).select_from(consulta.subquery())
    ) or 0

    linhas = db.session.execute(
        consulta.order_by(LogAuditoria.criado_em.desc())
        .limit(POR_PAGINA)
        .offset((pagina - 1) * POR_PAGINA)
    ).scalars().all()

    # As acoes que de fato existem no log - nao a lista inteira de constantes.
    # Mostrar filtros que nunca devolvem nada so frustra.
    acoes_existentes = [
        linha[0] for linha in db.session.execute(
            db.select(LogAuditoria.acao).distinct().order_by(LogAuditoria.acao)
        ).all()
    ]

    usuarios = db.session.execute(
        db.select(Usuario).order_by(Usuario.nome)
    ).scalars().all()

    return render_template(
        "admin/auditoria.html",
        linhas=linhas,
        total=total,
        pagina=pagina,
        por_pagina=POR_PAGINA,
        total_paginas=max(1, (total + POR_PAGINA - 1) // POR_PAGINA),
        acoes_existentes=acoes_existentes,
        usuarios=usuarios,
        filtros={"acao": f_acao, "usuario": f_usuario, "dias": f_dias},
    )
