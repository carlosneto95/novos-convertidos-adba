# -*- coding: utf-8 -*-
"""
app/rotas/auth.py - ENTRAR E SAIR DO SISTEMA.

    /login          - a tela de entrada
    /logout         - encerra a sessao
    /trocar-senha   - troca de senha (obrigatoria no primeiro acesso)

Quatro protecoes vivem aqui (secao 7):
    item 1  - a senha e conferida contra o HASH, nunca contra texto puro
    item 9  - a sessao expira em 8 horas
    item 10 - no maximo 5 tentativas de login por 15 minutos por IP
    item 13 - login, logout e tentativa falha vao para a auditoria
"""

# --- IMPORTACOES ----------------------------------------------------------
from flask import (
    Blueprint, render_template, redirect, url_for, request, flash,
    session, current_app,
)
from flask_login import login_user, logout_user, login_required, current_user

from app.extensions import db, limiter
from app.forms import LoginForm, TrocarSenhaForm
from app.models import Usuario
from app.tempo import agora
from app import auditoria
from app.seguranca import destino_seguro


auth = Blueprint("auth", __name__)


# ===========================================================================
# ROTA 1: LOGIN
# ===========================================================================
@auth.route("/login", methods=["GET", "POST"])
@limiter.limit(
    lambda: current_app.config.get("LIMITE_LOGIN", "5 per 15 minutes"),
    methods=["POST"],                    # conta TENTATIVAS, nao visitas a tela
    deduct_when=lambda resposta: resposta.status_code != 302,
    # deduct_when: so desconta do limite quando o login FALHOU (nao houve
    # redirecionamento). Assim quem acerta a senha nunca fica trancado, e
    # quem fica chutando gasta as 5 tentativas rapido.
)
def login():
    """Mostra a tela de entrada (GET) e confere a senha (POST)."""

    # Ja esta logado? Entao nao tem o que fazer aqui.
    if current_user.is_authenticated:
        return redirect(url_for("painel.index"))

    form = LoginForm()

    if form.validate_on_submit():
        login_digitado = (form.login.data or "").strip().lower()

        # --- Busca o usuario -------------------------------------------
        # func.lower() compara em minusculas: "Admin" e "admin" entram igual.
        usuario = db.session.execute(
            db.select(Usuario).where(db.func.lower(Usuario.login) == login_digitado)
        ).scalar_one_or_none()

        # --- Confere a senha -------------------------------------------
        # Guardamos o resultado numa variavel e SO DEPOIS decidimos.
        # Assim o codigo trata "usuario nao existe" e "senha errada" da mesma
        # forma - com a mesma mensagem e o mesmo tempo de resposta.
        senha_confere = bool(usuario) and usuario.conferir_senha(form.senha.data or "")

        if not senha_confere:
            # MENSAGEM PROPOSITALMENTE VAGA (secao 7).
            # Se disséssemos "usuario nao encontrado", um atacante descobriria
            # quais logins existem so testando nomes - e ja teria metade do
            # trabalho feito.
            flash("Login ou senha incorretos.", "erro")

            auditoria.registrar(
                acao=auditoria.LOGIN_FALHOU,
                entidade="usuario",
                entidade_id=usuario.id if usuario else None,
                detalhe=f'Tentativa com o login "{login_digitado}"',
                usuario_id=None,          # ninguem esta logado nesta hora
                gravar=True,
            )
            return render_template("auth/login.html", form=form)

        # --- Usuario desativado -----------------------------------------
        if not usuario.ativo:
            flash(
                "Este acesso foi desativado. Fale com o administrador.",
                "aviso",
            )
            auditoria.registrar(
                acao=auditoria.LOGIN_FALHOU,
                entidade="usuario",
                entidade_id=usuario.id,
                detalhe="Usuario desativado tentou entrar",
                usuario_id=usuario.id,
                gravar=True,
            )
            return render_template("auth/login.html", form=form)

        # --- Login aceito ------------------------------------------------
        # session.clear() antes de login_user() evita "fixacao de sessao":
        # um ataque em que o golpista planta um id de sessao no navegador da
        # vitima ANTES do login e passa a compartilhar a sessao depois dele.
        session.clear()

        login_user(usuario, remember=form.lembrar.data)

        # permanent=True faz valer o PERMANENT_SESSION_LIFETIME do config.py:
        # a sessao morre sozinha em 8 horas (secao 7, item 9).
        session.permanent = True

        auditoria.registrar(
            acao=auditoria.LOGIN,
            entidade="usuario",
            entidade_id=usuario.id,
            detalhe=f"{usuario.nome} ({usuario.papel_rotulo})",
            gravar=True,
        )

        # --- Precisa trocar a senha? -------------------------------------
        if usuario.deve_trocar_senha:
            flash(
                "Por seguranca, crie uma senha nova antes de continuar.",
                "aviso",
            )
            return redirect(url_for("auth.trocar_senha"))

        # --- Para onde ir ------------------------------------------------
        # destino_seguro() recusa enderecos de fora do sistema, bloqueando o
        # golpe do "open redirect" (ver app/seguranca.py).
        destino = destino_seguro(request.args.get("next"), url_for("painel.index"))

        flash(f"Bem-vindo, {usuario.primeiro_nome}!", "sucesso")
        return redirect(destino)

    # GET, ou POST que nao passou na validacao
    return render_template("auth/login.html", form=form)


# ===========================================================================
# ROTA 2: LOGOUT
# ===========================================================================
@auth.route("/logout", methods=["POST"])
@login_required
def logout():
    """
    Encerra a sessao.

    POR QUE SO ACEITA POST?
    Se fosse GET, bastaria um site malicioso incluir
        <img src="http://nosso-sistema/logout">
    para deslogar a pessoa sem que ela pedisse. Com POST, o Flask-WTF exige o
    token anti-CSRF - e a imagem nao tem como enviar o token.
    """
    nome = current_user.primeiro_nome

    auditoria.registrar(
        acao=auditoria.LOGOUT,
        entidade="usuario",
        entidade_id=current_user.id,
        detalhe=current_user.nome,
        gravar=True,
    )

    logout_user()      # o Flask-Login apaga o usuario da sessao
    session.clear()    # e nos limpamos o resto por garantia

    flash(f"Ate logo, {nome}! Voce saiu do sistema.", "sucesso")
    return redirect(url_for("auth.login"))


# ===========================================================================
# ROTA 3: TROCAR A SENHA
# ===========================================================================
@auth.route("/trocar-senha", methods=["GET", "POST"])
@login_required
def trocar_senha():
    """
    Troca de senha. Obrigatoria no primeiro acesso, voluntaria depois.
    """
    form = TrocarSenhaForm()
    obrigatoria = current_user.deve_trocar_senha

    if form.validate_on_submit():

        # --- Confere a senha atual ---------------------------------------
        # Sem isso, quem pegasse um computador destravado trocaria a senha da
        # pessoa e tomaria a conta.
        if not current_user.conferir_senha(form.senha_atual.data or ""):
            form.senha_atual.errors.append("A senha atual esta incorreta.")
            return render_template(
                "auth/trocar_senha.html", form=form, obrigatoria=obrigatoria
            )

        # --- Grava a senha nova ------------------------------------------
        current_user.definir_senha(form.senha_nova.data)   # vira hash bcrypt
        current_user.deve_trocar_senha = False             # cumpriu a obrigacao

        auditoria.registrar(
            acao=auditoria.SENHA_ALTERADA,
            entidade="usuario",
            entidade_id=current_user.id,
            detalhe="Troca obrigatoria" if obrigatoria else "Troca voluntaria",
        )

        db.session.commit()

        flash("Senha alterada com sucesso!", "sucesso")
        return redirect(url_for("painel.index"))

    return render_template(
        "auth/trocar_senha.html", form=form, obrigatoria=obrigatoria
    )
