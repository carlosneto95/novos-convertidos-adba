# -*- coding: utf-8 -*-
"""
app/comandos.py - COMANDOS DE TERMINAL.

Sao tarefas que voce roda digitando no terminal, nao clicando no site:

    flask criar-admin     -> cria o primeiro usuario administrador
    flask seed-eventos    -> gera os cultos de domingo e terca, 90 dias a frente

POR QUE NO TERMINAL E NAO NUMA TELA?
Criar o primeiro admin por uma pagina web seria uma porta aberta: qualquer um
que achasse a URL viraria administrador. No terminal, so quem tem acesso ao
servidor consegue rodar.

O "click" e a biblioteca que o Flask usa para montar comandos. Ele cuida das
opcoes (--login, --senha), das perguntas e das cores no terminal.
"""

# --- IMPORTACOES ----------------------------------------------------------
import click                                   # monta os comandos de terminal
from flask.cli import with_appcontext   # garante o app ligado no comando
from datetime import timedelta                 # para somar dias a uma data
from flask import current_app                  # acesso ao app que esta rodando

from app.extensions import db
from app.models import Usuario, Evento
from app.tempo import hoje


# ===========================================================================
# AJUDANTES DE TEXTO NO TERMINAL
# ===========================================================================
def _ok(mensagem):
    """Imprime em verde."""
    click.secho(f"  [OK] {mensagem}", fg="green")


def _aviso(mensagem):
    """Imprime em amarelo."""
    click.secho(f"  [!]  {mensagem}", fg="yellow")


def _erro(mensagem):
    """Imprime em vermelho."""
    click.secho(f"  [X]  {mensagem}", fg="red")


def _titulo(mensagem):
    """Imprime um cabecalho destacado."""
    click.echo("")
    click.secho(f"  {mensagem}", fg="cyan", bold=True)
    click.secho("  " + "-" * len(mensagem), fg="cyan")


# ===========================================================================
# COMANDO 1: flask criar-admin
# ===========================================================================
@click.command("criar-admin")
@click.option("--login", default=None, help="Login do administrador.")
@click.option("--nome", default=None, help="Nome completo do administrador.")
@click.option("--telefone", default=None, help="Telefone de contato.")
@click.option(
    "--perguntar",
    is_flag=True,
    help="Pergunta a senha no terminal em vez de ler do .env (mais seguro).",
)
@click.option(
    "--redefinir-senha",
    is_flag=True,
    help="Se o admin ja existir, troca a senha dele em vez de recusar.",
)
@with_appcontext
def criar_admin(login, nome, telefone, perguntar, redefinir_senha):
    """Cria o primeiro usuario administrador do sistema."""

    _titulo("Criando o administrador")

    # --- 1. De onde vem os dados ----------------------------------------
    # Prioridade: o que voce digitou na linha de comando > o que esta no .env.
    login = login or current_app.config.get("ADMIN_LOGIN")
    nome = nome or current_app.config.get("ADMIN_NOME")

    if not login:
        _erro("Nenhum login informado. Use --login ou preencha ADMIN_LOGIN no .env")
        return

    # --- 2. De onde vem a senha ------------------------------------------
    if perguntar:
        # hide_input=True: a senha nao aparece na tela enquanto voce digita.
        # confirmation_prompt=True: pede duas vezes, para evitar erro de digitacao.
        senha = click.prompt(
            "  Senha do administrador",
            hide_input=True,
            confirmation_prompt=True,
        )
    else:
        senha = current_app.config.get("ADMIN_SENHA_INICIAL")

    if not senha:
        _erro("Nenhuma senha informada. Use --perguntar ou preencha ADMIN_SENHA_INICIAL no .env")
        return

    # --- 3. Aviso sobre senha fraca --------------------------------------
    # Nao bloqueamos: e uma senha de primeiro acesso e o sistema vai exigir a
    # troca no primeiro login. Mas o aviso precisa aparecer.
    if len(senha) < 8:
        _aviso(f"A senha tem apenas {len(senha)} caracteres. O recomendado e 8 ou mais.")

    # --- 4. O usuario ja existe? -----------------------------------------
    # .filter_by(login=login).first() -> busca a primeira linha com este login.
    # Devolve None se nao achar nada.
    existente = Usuario.query.filter_by(login=login).first()

    if existente:
        if not redefinir_senha:
            _aviso(f'O usuario "{login}" ja existe. Nada foi alterado.')
            click.echo("       Para trocar a senha dele, rode:")
            click.echo("       flask criar-admin --redefinir-senha")
            return

        # Redefinindo a senha de quem ja existe.
        existente.definir_senha(senha)        # gera o hash novo
        existente.deve_trocar_senha = True    # obriga a trocar no proximo login
        existente.ativo = True                # reativa, caso estivesse desativado
        db.session.commit()                   # grava de verdade no banco
        _ok(f'Senha do usuario "{login}" redefinida.')
        _aviso("Ele tera de criar uma senha nova no proximo login.")
        return

    # --- 5. Criando o usuario novo ---------------------------------------
    admin = Usuario(
        nome=nome or "Administrador",
        login=login,
        telefone=telefone,
        papel="admin",                 # o papel que da acesso a tudo
        ativo=True,
        deve_trocar_senha=True,        # trocar no primeiro login
    )
    admin.definir_senha(senha)         # nunca gravamos a senha em texto puro

    db.session.add(admin)              # coloca na "fila" de gravacao
    db.session.commit()                # executa a gravacao no banco

    _ok(f'Administrador "{login}" criado.')
    click.echo(f"       Nome:  {admin.nome}")
    click.echo(f"       Papel: {admin.papel_rotulo}")
    _aviso("Sera obrigatorio criar uma senha nova no primeiro login.")


# ===========================================================================
# COMANDO 2: flask seed-eventos
# ===========================================================================
# Quais cultos sao recorrentes e em que dia da semana caem.
# No Python, a semana comeca na segunda: 0=segunda, 1=terca, ..., 6=domingo.
CULTOS_RECORRENTES = [
    {"dia_semana": 6, "tipo": "culto_dominical", "nome": "Culto Dominical"},
    {"dia_semana": 1, "tipo": "culto_ensino", "nome": "Culto de Ensino"},
]


@click.command("seed-eventos")
@click.option("--dias", default=None, type=int, help="Quantos dias gerar a frente.")
@with_appcontext
def seed_eventos(dias):
    """Gera os cultos recorrentes de domingo e terca para os proximos 90 dias."""

    _titulo("Gerando a agenda de cultos")

    # Quantos dias a frente: o que voce digitou, ou o valor do config.py.
    if dias is None:
        dias = current_app.config.get("DIAS_AGENDA_EVENTOS", 90)

    data_inicio = hoje()
    data_fim = data_inicio + timedelta(days=dias)

    click.echo(f"       Periodo: {data_inicio.strftime('%d/%m/%Y')} ate {data_fim.strftime('%d/%m/%Y')}")

    # --- 1. O que JA existe no banco -------------------------------------
    # Buscamos de uma vez os pares (tipo, data) ja cadastrados no periodo.
    # Assim o comando pode ser rodado quantas vezes quiser sem criar repetido.
    ja_existem = db.session.execute(
        db.select(Evento.tipo, Evento.data).where(
            Evento.data >= data_inicio,
            Evento.data <= data_fim,
        )
    ).all()

    # set() e um "conjunto": a busca dentro dele e instantanea, mesmo com
    # milhares de itens. Muito melhor que consultar o banco para cada dia.
    existentes = {(linha.tipo, linha.data) for linha in ja_existem}

    # --- 2. Percorrer dia por dia ----------------------------------------
    criados = 0
    pulados = 0
    data_atual = data_inicio

    while data_atual <= data_fim:                  # enquanto nao passar do fim
        for culto in CULTOS_RECORRENTES:
            # .weekday() devolve 0 (segunda) ate 6 (domingo).
            if data_atual.weekday() != culto["dia_semana"]:
                continue                           # nao e o dia deste culto: pula

            if (culto["tipo"], data_atual) in existentes:
                pulados += 1                       # ja estava no banco
                continue

            # Cria o evento na "fila" de gravacao.
            db.session.add(
                Evento(
                    nome=culto["nome"],
                    tipo=culto["tipo"],
                    data=data_atual,
                    recorrente=True,               # marca que nasceu do seed
                    criado_por_id=None,            # nenhum usuario criou: foi o sistema
                    ativo=True,
                )
            )
            criados += 1

        data_atual += timedelta(days=1)            # avanca um dia

    # --- 3. Gravar tudo de uma vez ---------------------------------------
    # Um unico commit no fim e muito mais rapido do que um por evento.
    db.session.commit()

    _ok(f"{criados} culto(s) criado(s).")
    if pulados:
        click.echo(f"       {pulados} ja existiam e foram mantidos.")

    total = db.session.scalar(db.select(db.func.count()).select_from(Evento))
    click.echo(f"       Total de eventos no banco: {total}")


# ===========================================================================
# COMANDO 3: flask preparar-sistema  (atalho que roda os dois acima)
# ===========================================================================
@click.command("preparar-sistema")
@click.pass_context
@with_appcontext
def preparar_sistema(ctx):
    """Atalho: cria o admin e gera a agenda de cultos numa tacada so."""
    ctx.invoke(criar_admin)      # chama o comando criar-admin
    ctx.invoke(seed_eventos)     # chama o comando seed-eventos
    click.echo("")
    _ok("Sistema preparado. Ja da para fazer login.")


# ===========================================================================
# REGISTRO DOS COMANDOS NO APP
# ===========================================================================
def registrar_comandos(app):
    """
    Chamada pela fabrica create_app(). Sem isto, o Flask nao enxerga os
    comandos e "flask criar-admin" responderia "No such command".
    """
    app.cli.add_command(criar_admin)
    app.cli.add_command(seed_eventos)
    app.cli.add_command(preparar_sistema)

    # Comando de dados de teste, num arquivo proprio para nao poluir este.
    from app.comandos_exemplo import dados_exemplo
    app.cli.add_command(dados_exemplo)
