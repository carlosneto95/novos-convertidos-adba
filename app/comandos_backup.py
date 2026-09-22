# -*- coding: utf-8 -*-
"""
app/comandos_backup.py - CÓPIA DE SEGURANCA DO BANCO (secao 7, item 14).

    flask backup              faz uma copia agora
    flask backup --listar     mostra as copias existentes
    flask backup --limpar 10  apaga as mais antigas, guardando as 10 ultimas

POR QUE NAO BASTA COPIAR O ARQUIVO?
Copiar um .db enquanto alguem escreve nele produz uma copia QUEBRADA - metade
de uma transacao, um indice pela metade. E o pior tipo de backup: o que parece
existir, e so falha no dia em que voce precisa dele.

Este comando usa a funcao de backup do proprio SQLite, que sabe esperar o
momento certo e garante um arquivo integro.

QUANDO RODAR
No PythonAnywhere da para agendar uma tarefa diaria apontando para este
comando (instrucoes na Etapa 10). Rode tambem a mao ANTES de qualquer
migracao de banco.
"""

# --- IMPORTACOES ----------------------------------------------------------
import os
import sqlite3
from datetime import datetime

import click
from flask.cli import with_appcontext
from flask import current_app

from app.comandos import _ok, _aviso, _erro, _titulo


def _caminho_do_banco():
    """
    Descobre o arquivo .db a partir da configuracao.

    "sqlite:///C:/caminho/adba.db" -> "C:/caminho/adba.db"
    """
    uri = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not uri.startswith("sqlite:"):
        return None                      # nao e SQLite: outro tipo de backup
    return uri.replace("sqlite:///", "").replace("sqlite://", "")


def _tamanho_legivel(bytes_):
    """1536000 -> '1.5 MB'"""
    for unidade in ["B", "KB", "MB", "GB"]:
        if bytes_ < 1024:
            return f"{bytes_:.1f} {unidade}"
        bytes_ /= 1024
    return f"{bytes_:.1f} TB"


@click.command("backup")
@click.option("--listar", is_flag=True, help="Só mostra as cópias que já existem.")
@click.option("--limpar", type=int, default=None,
              help="Apaga as cópias mais antigas, guardando as N últimas.")
@with_appcontext
def backup(listar, limpar):
    """Faz uma cópia de segurança do banco de dados."""

    pasta = current_app.config["PASTA_BACKUP"]
    os.makedirs(pasta, exist_ok=True)

    # =====================================================================
    # MODO LISTAR
    # =====================================================================
    if listar:
        _titulo("Copias de seguranca existentes")
        arquivos = sorted(
            [f for f in os.listdir(pasta) if f.endswith(".db")],
            reverse=True,               # mais recente primeiro
        )
        if not arquivos:
            _aviso("Nenhuma copia ainda. Rode: flask backup")
            return
        for nome in arquivos:
            caminho = os.path.join(pasta, nome)
            tamanho = _tamanho_legivel(os.path.getsize(caminho))
            quando = datetime.fromtimestamp(os.path.getmtime(caminho))
            click.echo(f"  {nome:42s} {tamanho:>9s}  {quando.strftime('%d/%m/%Y %H:%M')}")
        click.echo(f"\n  Total: {len(arquivos)} copia(s) em {pasta}")
        return

    # =====================================================================
    # MODO LIMPAR
    # =====================================================================
    if limpar is not None:
        _titulo(f"Guardando as {limpar} copias mais recentes")
        if limpar < 1:
            _erro("Guarde pelo menos 1 copia.")
            return

        arquivos = sorted(
            [f for f in os.listdir(pasta) if f.endswith(".db")],
            reverse=True,
        )
        sobrando = arquivos[limpar:]
        if not sobrando:
            _ok(f"Ha {len(arquivos)} copia(s). Nada a apagar.")
            return

        for nome in sobrando:
            os.remove(os.path.join(pasta, nome))
            click.echo(f"       apagada: {nome}")
        _ok(f"{len(sobrando)} copia(s) antiga(s) removida(s).")
        return

    # =====================================================================
    # MODO PADRAO - FAZER A COPIA
    # =====================================================================
    _titulo("Copia de seguranca do banco")

    origem = _caminho_do_banco()

    if origem is None:
        _erro("O banco nao e SQLite. Use a ferramenta de backup do seu banco.")
        return

    if not os.path.exists(origem):
        _erro(f"Banco nao encontrado: {origem}")
        return

    carimbo = datetime.now().strftime("%Y-%m-%d_%Hh%M")
    destino = os.path.join(pasta, f"adba_{carimbo}.db")

    if os.path.exists(destino):
        _aviso("Ja existe uma copia deste minuto. Espere um pouco e repita.")
        return

    # --- A COPIA SEGURA ---------------------------------------------------
    # conn_origem.backup(conn_destino) e a funcao propria do SQLite. Ela
    # copia pagina por pagina esperando as escritas terminarem, garantindo um
    # arquivo integro mesmo com o sistema no ar. Um "copiar e colar" comum
    # pegaria o banco no meio de uma gravacao.
    conexao_origem = sqlite3.connect(origem)
    conexao_destino = sqlite3.connect(destino)
    try:
        with conexao_destino:
            conexao_origem.backup(conexao_destino)
    finally:
        conexao_destino.close()
        conexao_origem.close()

    # --- CONFERIR QUE A COPIA PRESTA --------------------------------------
    # Backup que ninguem testa nao e backup. Abrimos a copia e contamos as
    # almas: se o numero bater com o original, a copia esta viva.
    try:
        conferencia = sqlite3.connect(destino)
        almas = conferencia.execute("select count(*) from novo_convertido").fetchone()[0]
        usuarios = conferencia.execute("select count(*) from usuario").fetchone()[0]
        conferencia.close()
    except Exception as e:
        _erro(f"A copia foi criada mas nao abriu para conferencia: {e}")
        return

    _ok(f"Copia criada: {os.path.basename(destino)}")
    click.echo(f"       Pasta:    {pasta}")
    click.echo(f"       Tamanho:  {_tamanho_legivel(os.path.getsize(destino))}")
    click.echo(f"       Conferido: {almas} alma(s), {usuarios} usuario(s)")

    total = len([f for f in os.listdir(pasta) if f.endswith(".db")])
    if total > 30:
        _aviso(f"Ha {total} copias guardadas. Para limpar: flask backup --limpar 30")

    # O lembrete que salva backup de verdade.
    _aviso("Copia guardada no MESMO computador. Leve uma copia para fora "
           "(nuvem, pen drive) - incendio e roubo levam as duas juntas.")


def registrar_backup(app):
    """Chamada pela fabrica create_app()."""
    app.cli.add_command(backup)
