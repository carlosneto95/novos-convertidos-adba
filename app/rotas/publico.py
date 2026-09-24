# -*- coding: utf-8 -*-
"""
app/rotas/publico.py - AS DUAS UNICAS PAGINAS SEM LOGIN.

    /cadastro/<token>   - o formulario
    /cadastro/sucesso   - a tela "Cadastro realizado!"

Esta e a superficie mais exposta do sistema: qualquer pessoa da internet pode
chegar aqui. Por isso ela concentra quatro camadas de protecao (secao 7):

    1. TOKEN na URL      - quem nao tem o link nao acha a pagina
    2. HONEYPOT          - armadilha invisivel que pega robo
    3. RATE LIMIT        - no maximo 5 envios por hora por IP
    4. CSRF              - so aceita envio vindo de uma pagina nossa
"""

# --- IMPORTACOES ----------------------------------------------------------
import secrets                                  # comparacao segura de token
from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    abort,
    current_app,
    session,
)

from app.extensions import db, limiter
from app.forms import CadastroPublicoForm
from app.models import NovoConvertido, LogAuditoria
from app.tempo import agora, eh_menor_de_idade
from app import opcoes
from app.validacao import (
    normalizar_nome,
    normalizar_telefone,
    normalizar_cep,
    normalizar_texto,
    normalizar_uf,
)


# --- O BLUEPRINT ----------------------------------------------------------
# Um Blueprint e um "bloco de rotas". Este se chama "publico", entao as rotas
# dele sao referenciadas como "publico.cadastro", "publico.sucesso".
publico = Blueprint("publico", __name__)


# ===========================================================================
# AJUDANTES
# ===========================================================================
def obter_ip():
    """
    Descobre o IP de quem esta acessando - guardado como prova do consentimento
    LGPD (secao 5.1).

    A sutileza: no PythonAnywhere o sistema nao fala direto com o visitante.
    Existe um intermediario (proxy) na frente. Sem tratamento, TODO cadastro
    registraria o IP do proxy, e a prova de consentimento nao valeria nada.
    O ProxyFix, ligado no __init__.py quando estamos em producao, resolve isso.
    """
    return request.headers.get("X-Real-IP") or request.remote_addr or "desconhecido"


def token_confere(token_recebido):
    """
    Compara o token da URL com o do .env.

    Usa secrets.compare_digest, e nao o "==" comum. Motivo: o "==" para de
    comparar assim que acha a primeira letra diferente. Medindo o tempo de
    resposta, um atacante conseguiria descobrir o token letra por letra.
    O compare_digest sempre leva o mesmo tempo, independentemente do resultado.
    """
    token_correto = current_app.config.get("CADASTRO_TOKEN") or ""
    if not token_correto or not token_recebido:
        return False
    return secrets.compare_digest(str(token_recebido), str(token_correto))


def registrar_log(acao, entidade=None, entidade_id=None, detalhe=None):
    """Grava uma linha no log de auditoria (secao 7, item 13)."""
    db.session.add(
        LogAuditoria(
            usuario_id=None,          # cadastro publico nao tem usuario logado
            acao=acao,
            entidade=entidade,
            entidade_id=entidade_id,
            detalhe=detalhe,
            ip=obter_ip(),
        )
    )


# ===========================================================================
# ROTA 1: O FORMULARIO
# ===========================================================================
@publico.route("/cadastro/<token>", methods=["GET", "POST"])
@limiter.limit(
    lambda: current_app.config.get("LIMITE_CADASTRO_PUBLICO", "5 per hour"),
    methods=["POST"],          # o limite conta ENVIOS, nao visitas a pagina
)
def cadastro(token):
    """Mostra o formulario (GET) e grava a alma (POST)."""

    # --- PROTECAO 1: o token da URL --------------------------------------
    if not token_confere(token):
        # Devolvemos 404 ("nao existe"), e nao 403 ("proibido"), de proposito.
        # 403 confirmaria que a pagina existe e que o token e que estava errado -
        # um convite para o atacante continuar tentando.
        abort(404)

    form = CadastroPublicoForm()

    # --- request.method == "POST" significa "a pessoa clicou em enviar" ---
    if form.validate_on_submit():
        # validate_on_submit() faz DUAS coisas: confere se e POST e se o
        # formulario passou em TODA a validacao do servidor, CSRF incluido.

        # --- PROTECAO 2: a armadilha anti-robo ---------------------------
        if form.eh_robo:
            # Um robo preencheu o campo invisivel.
            # Respondemos a tela de sucesso normalmente: se mostrassemos erro,
            # o dono do robo ajustaria o programa e voltaria. Assim ele acredita
            # que funcionou e vai embora. Nada e gravado.
            registrar_log(
                acao="cadastro_bloqueado_honeypot",
                entidade="novo_convertido",
                detalhe="Campo invisivel preenchido - provavel robo.",
            )
            db.session.commit()
            session["cadastro_token"] = token
            return redirect(url_for("publico.sucesso"))

        # --- Gravando a alma ---------------------------------------------
        alma = NovoConvertido(
            # Bloco 1 - quem cadastrou
            cadastrante_nome=normalizar_nome(form.cadastrante_nome.data),
            cadastrante_telefone=normalizar_telefone(form.cadastrante_telefone.data),

            # Bloco 2 - dados pessoais
            nome_completo=normalizar_nome(form.nome_completo.data),
            telefone=normalizar_telefone(form.telefone.data),
            sexo=form.sexo.data,
            data_nascimento=form.data_nascimento.data,

            # Bloco 2 - endereco
            cep=normalizar_cep(form.cep.data),
            logradouro=normalizar_texto(form.logradouro.data, 150),
            numero=normalizar_texto(form.numero.data, 20),
            complemento=normalizar_texto(form.complemento.data, 100),
            bairro=normalizar_texto(form.bairro.data, 100),
            cidade=normalizar_texto(form.cidade.data, 100),
            uf=normalizar_uf(form.uf.data),

            # Bloco 3 - a conversao
            trabalho=form.trabalho.data,
            trabalho_outro=(
                normalizar_texto(form.trabalho_outro.data, 120)
                if form.trabalho.data == "outro"
                else None
            ),
            data_conversao=form.data_conversao.data,
            departamento=form.departamento.data,

            # Bloco 4 - questionario
            como_chegou=normalizar_texto(form.como_chegou.data, 2000),
            tem_conhecido=(form.tem_conhecido.data == "sim") if form.tem_conhecido.data else None,
            conhecido_nome=(
                normalizar_nome(form.conhecido_nome.data)
                if form.tem_conhecido.data == "sim"
                else None
            ),
            ja_frequentou_igreja=(
                (form.ja_frequentou_igreja.data == "sim")
                if form.ja_frequentou_igreja.data
                else None
            ),
            qual_igreja=(
                normalizar_texto(form.qual_igreja.data, 150)
                if form.ja_frequentou_igreja.data == "sim"
                else None
            ),

            # LGPD - a prova do consentimento
            consentimento_em=agora(),
            consentimento_ip=obter_ip(),

            # Status inicial: roxo no painel do Admin, esperando designacao
            status_ciclo=opcoes.STATUS_INICIAL,
        )

        # --- Responsavel legal, so se for menor de idade -----------------
        maioridade = current_app.config.get("IDADE_MAIORIDADE", 18)
        if eh_menor_de_idade(form.data_nascimento.data, maioridade):
            alma.responsavel_legal_nome = normalizar_nome(form.responsavel_legal_nome.data)
            alma.responsavel_legal_telefone = normalizar_telefone(
                form.responsavel_legal_telefone.data
            )

        db.session.add(alma)
        db.session.flush()        # gera o id e o codigo sem fechar a transacao

        registrar_log(
            acao="cadastro_publico",
            entidade="novo_convertido",
            entidade_id=alma.id,
            detalhe=f"Cadastro {alma.codigo_formatado} por {alma.cadastrante_nome}",
        )

        db.session.commit()       # grava tudo de uma vez

        # --- O token vai para a sessao, nao para a URL -------------------
        # A tela de sucesso precisa do token para montar o botao "Voltar ao
        # formulario". Guardamos na sessao (assinada e fora do alcance do
        # JavaScript) em vez de por na URL: um endereco fica no historico, no
        # cabecalho Referer e na tela de quem estiver olhando por cima do
        # ombro. Nada de novo vaza - e o mesmo token que a pessoa ja tem.
        session["cadastro_token"] = token

        # A tela de sucesso NAO recebe nenhum dado da alma (secao 5.1).
        return redirect(url_for("publico.sucesso"))

    # --- GET, ou POST que nao passou na validacao ------------------------
    return render_template(
        "publico/cadastro.html",
        form=form,
        token=token,
        maioridade=current_app.config.get("IDADE_MAIORIDADE", 18),
    )


# ===========================================================================
# ROTA 2: A TELA DE SUCESSO
# ===========================================================================
@publico.route("/cadastro/sucesso")
def sucesso():
    """
    "Cadastro realizado!" e mais nada.

    Sem nome, sem codigo, sem link para o painel (secao 5.1). Quem cadastrou
    pode ser qualquer membro da igreja - nao pode sair da tela sabendo dados de
    outras pessoas nem descobrindo que existe um sistema interno.
    """
    # --- O botao "Voltar ao formulario" ----------------------------------
    # Ele precisa abrir um formulario VAZIO, para a proxima pessoa. Antes era
    # history.back(), que devolvia a pagina anterior com tudo ainda
    # preenchido - o cadastro seguinte comecava com os dados do anterior.
    #
    # Aqui montamos um endereco de verdade, que o navegador carrega do zero.
    # O token sai da sessao, guardado no momento em que o cadastro foi salvo.
    #
    # Sem token (sessao expirada, cookie apagado) nao mostramos o botao: e
    # melhor nao ter botao do que ter um que leva a uma pagina de erro.
    token = session.get("cadastro_token")
    # direto=1: quem esta cadastrando varias pessoas seguidas ja viu a tela
    # de boas-vindas - o formulario abre direto no bloco 1.
    voltar = url_for("publico.cadastro", token=token, direto=1) if token else None

    return render_template("publico/sucesso.html", voltar=voltar)
