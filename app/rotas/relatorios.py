# -*- coding: utf-8 -*-
"""
app/rotas/relatorios.py - RELATORIOS E EXPORTACAO (secao 5.6). SO ADMIN.

    /relatorios          os graficos
    /relatorios/excel    baixa a planilha

POR QUE SO O ADMIN?
Os relatorios mostram a igreja inteira de uma vez - inclusive o desempenho de
cada responsavel. Um responsavel ver o ranking em que ele aparece mudaria a
natureza da ferramenta: de acompanhamento pastoral para vigilancia.

E a exportacao e ainda mais sensivel: um clique baixa a base inteira de dados
pessoais. Por isso ela e exclusiva do Admin E registrada na auditoria
(secao 7, item 12).
"""

# --- IMPORTACOES ----------------------------------------------------------
from flask import Blueprint, render_template, send_file

from app.extensions import db
from app import relatorios as calculos, auditoria
from app.seguranca import admin_necessario


relatorios = Blueprint("relatorios", __name__)


# ===========================================================================
# A TELA DOS GRAFICOS
# ===========================================================================
@relatorios.route("/relatorios")
@admin_necessario
def index():
    """Monta os numeros e entrega para os graficos desenharem."""
    dados = calculos.tudo()
    return render_template("relatorios/index.html", d=dados)


# ===========================================================================
# A EXPORTACAO PARA EXCEL (secao 5.6 e secao 7, item 12)
# ===========================================================================
@relatorios.route("/relatorios/excel")
@admin_necessario
def exportar_excel():
    """
    Gera e entrega a planilha.

    A AUDITORIA VEM ANTES do envio, de proposito. Se gravassemos depois, uma
    falha no meio do download deixaria a exportacao sem registro - e o log de
    auditoria so vale se for completo.
    """
    from app.excel import gerar_planilha

    buffer, nome, contagens = gerar_planilha()

    auditoria.registrar(
        acao=auditoria.EXPORTACAO_EXCEL,
        entidade="novo_convertido",
        detalhe=(
            f"Planilha gerada: "
            + ", ".join(f"{k}={v}" for k, v in contagens.items())
        ),
        gravar=True,
    )

    return send_file(
        buffer,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,       # baixa em vez de abrir no navegador
        download_name=nome,
    )
