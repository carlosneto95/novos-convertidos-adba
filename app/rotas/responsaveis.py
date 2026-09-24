# -*- coding: utf-8 -*-
"""
app/rotas/responsaveis.py - A EQUIPE (secao 5.4). SO ADMIN.

    /responsaveis                      lista + tabela de carga
    POST /responsaveis/criar           cria um usuario
    POST /responsaveis/<id>/ativar     liga ou desliga o acesso
    POST /responsaveis/<id>/senha      sorteia uma senha nova

A TABELA DE CARGA e o que esta tela tem de mais util. Ela responde:
    "quem esta sobrecarregado e quem esta deixando alma para tras?"

Sem ela, o Admin so descobre o problema quando alguem reclama.
"""

# --- IMPORTACOES ----------------------------------------------------------
import secrets
import string

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import current_user

from app.extensions import db
from app.models import Usuario, NovoConvertido, Contato
from app import opcoes, semaforo as sem, auditoria
from app.seguranca import admin_necessario
from app.tempo import agora, dias_desde
from app.validacao import normalizar_nome, normalizar_telefone


responsaveis = Blueprint("responsaveis", __name__)


# ===========================================================================
# SORTEIO DE SENHA
# ===========================================================================
# Alfabeto SEM caracteres que se confundem quando alguem le a senha em voz
# alta ou copia de um papel:
#   0 e O    1, l e I
# Uma senha que a pessoa nao consegue digitar e uma senha inutil.
ALFABETO_SENHA = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def sortear_senha(tamanho=10):
    """
    Sorteia uma senha temporaria.

    Usa "secrets", e nao "random". A diferenca importa: random e previsivel -
    sabendo algumas senhas geradas, da para calcular as proximas. O secrets
    usa a fonte de aleatoriedade do sistema operacional, a mesma que protege
    conexoes bancarias.

    A senha e mostrada UMA vez na tela e nunca mais: no banco fica so o hash.
    Se o Admin perder, sorteia outra.
    """
    return "".join(secrets.choice(ALFABETO_SENHA) for _ in range(tamanho))


# ===========================================================================
# A TABELA DE CARGA (secao 5.4)
# ===========================================================================
def calcular_carga():
    """
    Para cada responsavel, calcula:
        almas       - quantas esta acompanhando
        verde       - quantas estao em dia
        percentual  - % no verde
        criticas    - quantas estao no vermelho
        dias_medios - media de dias entre um contato e outro

    TUDO em poucas consultas, nao uma por pessoa.
    """
    from app.rotas.painel import mapas_de_contato

    # --- 1. Todos os usuarios ativos --------------------------------------
    usuarios = db.session.execute(
        db.select(Usuario).order_by(Usuario.ativo.desc(), Usuario.nome)
    ).scalars().all()

    # --- 2. Todas as almas em acompanhamento, de uma vez ------------------
    almas = db.session.execute(
        db.select(NovoConvertido).where(
            NovoConvertido.status_ciclo == opcoes.STATUS_ATIVO,
            NovoConvertido.mesclado_em_id.is_(None),
        )
    ).scalars().all()

    tentativas, efetivos = mapas_de_contato([a.id for a in almas])

    # --- 3. Agrupa as almas por responsavel -------------------------------
    por_responsavel = {}
    for alma in almas:
        por_responsavel.setdefault(alma.responsavel_atual_id, []).append(alma)

    # --- 4. Media de dias entre contatos, por responsavel -----------------
    # Conta quantos contatos cada um registrou e ha quanto tempo trabalha.
    # E uma media grosseira de proposito: o que importa e comparar as pessoas
    # entre si, nao ter o numero exato.
    linhas_contato = db.session.execute(
        db.select(
            Contato.responsavel_id,
            db.func.count(Contato.id),
            db.func.min(Contato.data_hora),
        ).group_by(Contato.responsavel_id)
    ).all()
    estatistica_contatos = {
        linha[0]: {"total": linha[1], "primeiro": linha[2]} for linha in linhas_contato
    }

    # --- 5. Monta a linha de cada responsavel -----------------------------
    carga = []
    for u in usuarios:
        minhas = por_responsavel.get(u.id, [])
        pares = sem.calcular_muitas(minhas, tentativas, efetivos)
        contagem = sem.contar_por_cor(pares)

        total = len(minhas)
        # O azul (aguardando o 1º contato, dentro das 48h) tambem esta no
        # prazo: nao pode baixar o percentual de quem acabou de receber a alma.
        verde = contagem["verde"] + contagem["azul"]
        percentual = round(verde * 100 / total) if total else None

        # Dias medios entre contatos
        info = estatistica_contatos.get(u.id)
        dias_medios = None
        if info and info["total"] > 1 and info["primeiro"]:
            dias_trabalhando = dias_desde(info["primeiro"]) or 0
            if dias_trabalhando > 0:
                dias_medios = round(dias_trabalhando / info["total"], 1)

        carga.append({
            "usuario": u,
            "almas": total,
            "verde": verde,
            "atencao": contagem["atencao"],
            "criticas": contagem["vermelho"],
            "percentual": percentual,
            "contatos": info["total"] if info else 0,
            "dias_medios": dias_medios,
        })

    return carga


# ===========================================================================
# A TELA
# ===========================================================================
@responsaveis.route("/responsaveis")
@admin_necessario
def index():
    """Lista a equipe com a tabela de carga."""
    from app.forms import UsuarioForm

    carga = calcular_carga()

    # A senha sorteada viaja na URL depois de criar/redefinir, para aparecer
    # UMA vez na tela. Nao fica gravada em lugar nenhum.
    senha_nova = request.args.get("senha", "")
    login_novo = request.args.get("login", "")

    return render_template(
        "responsaveis/index.html",
        carga=carga,
        form=UsuarioForm(),
        senha_nova=senha_nova,
        login_novo=login_novo,
        total_ativos=sum(1 for c in carga if c["usuario"].ativo),
    )


# ===========================================================================
# CRIAR USUARIO
# ===========================================================================
@responsaveis.route("/responsaveis/criar", methods=["POST"])
@admin_necessario
def criar():
    """Cria um usuario e sorteia a senha do primeiro acesso."""
    from app.forms import UsuarioForm

    form = UsuarioForm()

    if not form.validate_on_submit():
        mensagens = [e for campo in form for e in campo.errors]
        flash(" ".join(mensagens) or "Confira os campos.", "erro")
        return redirect(url_for("responsaveis.index"))

    senha = sortear_senha()

    usuario = Usuario(
        nome=normalizar_nome(form.nome.data),
        login=(form.login.data or "").strip().lower(),
        telefone=normalizar_telefone(form.telefone.data) or None,
        papel=form.papel.data,
        ativo=True,
        deve_trocar_senha=True,   # a senha passou pelas maos do Admin
        criado_em=agora(),
    )
    usuario.definir_senha(senha)   # so o hash vai para o banco

    db.session.add(usuario)
    db.session.flush()

    auditoria.registrar(
        acao=auditoria.USUARIO_CRIADO,
        entidade="usuario",
        entidade_id=usuario.id,
        detalhe=f"{usuario.login} ({usuario.papel})",
    )

    db.session.commit()

    # A senha vai na URL para ser mostrada UMA vez. Nao e gravada.
    return redirect(url_for("responsaveis.index", senha=senha, login=usuario.login))


# ===========================================================================
# ATIVAR / DESATIVAR
# ===========================================================================
@responsaveis.route("/responsaveis/<usuario_id>/ativar", methods=["POST"])
@admin_necessario
def alternar_ativo(usuario_id):
    """
    Liga ou desliga o acesso de alguem.

    NUNCA apagamos um usuario. Se apagássemos, os contatos e as designacoes
    dele ficariam orfaos e o historico perderia o sentido - "registrado por
    (ninguem)". Desativar mantem a historia inteira e fecha a porta.
    """
    usuario = db.session.get(Usuario, usuario_id)
    if usuario is None:
        abort(404)

    # --- Trava 1: nao desative a si mesmo --------------------------------
    # Um Admin sozinho que se desativasse trancaria a igreja inteira para
    # fora do sistema, sem ninguem para reverter pela tela.
    if usuario.id == current_user.id:
        flash("Você não pode desativar o seu próprio acesso.", "erro")
        return redirect(url_for("responsaveis.index"))

    # --- Trava 2: nao fique sem nenhum Admin ------------------------------
    if usuario.ativo and usuario.eh_admin:
        outros_admins = db.session.scalar(
            db.select(db.func.count()).select_from(Usuario).where(
                Usuario.papel == "admin",
                Usuario.ativo.is_(True),
                Usuario.id != usuario.id,
            )
        )
        if not outros_admins:
            flash(
                "Este é o único administrador ativo. Crie outro antes de desativá-lo.",
                "erro",
            )
            return redirect(url_for("responsaveis.index"))

    usuario.ativo = not usuario.ativo

    auditoria.registrar(
        acao=auditoria.USUARIO_REATIVADO if usuario.ativo else auditoria.USUARIO_DESATIVADO,
        entidade="usuario",
        entidade_id=usuario.id,
        detalhe=usuario.login,
    )

    db.session.commit()

    if usuario.ativo:
        flash(f"{usuario.primeiro_nome} voltou a ter acesso.", "sucesso")
    else:
        almas = db.session.scalar(
            db.select(db.func.count()).select_from(NovoConvertido).where(
                NovoConvertido.responsavel_atual_id == usuario.id,
                NovoConvertido.status_ciclo == opcoes.STATUS_ATIVO,
            )
        )
        aviso = f"{usuario.primeiro_nome} não entra mais no sistema."
        if almas:
            # Avisar e essencial: sem isso, N almas ficariam com um
            # responsavel que nunca mais abre o sistema, e o semaforo delas
            # iria para o vermelho sem ninguem entender por que.
            aviso += (
                f" ATENÇÃO: {almas} alma(s) continuam sob responsabilidade dele. "
                f"Transfira-as pela ficha de cada uma."
            )
        flash(aviso, "aviso")

    return redirect(url_for("responsaveis.index"))


# ===========================================================================
# REDEFINIR SENHA
# ===========================================================================
@responsaveis.route("/responsaveis/<usuario_id>/senha", methods=["POST"])
@admin_necessario
def redefinir_senha(usuario_id):
    """Sorteia uma senha nova para quem esqueceu a dele."""
    usuario = db.session.get(Usuario, usuario_id)
    if usuario is None:
        abort(404)

    senha = sortear_senha()
    usuario.definir_senha(senha)
    usuario.deve_trocar_senha = True   # obriga a trocar no proximo login

    auditoria.registrar(
        acao=auditoria.SENHA_REDEFINIDA,
        entidade="usuario",
        entidade_id=usuario.id,
        detalhe=f"senha de {usuario.login} redefinida pelo admin",
    )

    db.session.commit()

    return redirect(url_for("responsaveis.index", senha=senha, login=usuario.login))
