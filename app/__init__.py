# -*- coding: utf-8 -*-
"""
app/__init__.py - A FABRICA DE APLICACAO.

Este arquivo tem uma unica funcao importante: create_app().
Ela monta o sistema inteiro, peca por peca, e devolve o app pronto.

POR QUE UMA "FABRICA" E NAO UM APP SOLTO?
1. O PythonAnywhere precisa chamar uma funcao para criar o app (padrao WSGI).
2. Um dia voce pode querer criar um app de teste com banco diferente.
3. Evita que o app vire uma variavel global bagunçada.

O arquivo se chama __init__.py porque isso transforma a pasta "app" num
PACOTE Python. E por isso que em outro arquivo podemos escrever:
    from app import create_app
"""

# --- IMPORTACOES ----------------------------------------------------------
import os                                   # acesso ao sistema de arquivos
from flask import Flask, render_template, redirect, url_for, request

from config import obter_config             # seletor de ambiente do config.py
from app.extensions import (                # as pecas criadas em extensions.py
    db,
    migrate,
    login_manager,
    bcrypt,
    csrf,
    limiter,
)


def create_app(classe_config=None):
    """
    Monta e devolve a aplicacao Flask.

    Parametro:
        classe_config - opcional. Se nao informado, le APP_ENV do .env.
                        Serve para os testes automatizados injetarem outra config.
    """

    # =====================================================================
    # PASSO 1 - CRIAR O OBJETO FLASK
    # =====================================================================
    app = Flask(
        __name__,                       # diz ao Flask onde este pacote esta no disco
        instance_relative_config=True,  # habilita a pasta "instance/" para dados locais
    )

    # =====================================================================
    # PASSO 2 - CARREGAR AS CONFIGURACOES
    # =====================================================================
    # Se ninguem passou uma config, obter_config() le o APP_ENV do .env
    # e devolve DevelopmentConfig (seu PC) ou ProductionConfig (servidor).
    if classe_config is None:
        classe_config = obter_config()

    # from_object copia todos os atributos MAIUSCULOS da classe para app.config.
    # Ou seja: SECRET_KEY, PRAZO_CONTATO_DIAS, CORES_SEMAFORO etc.
    app.config.from_object(classe_config)

    # =====================================================================
    # PASSO 3 - GARANTIR QUE AS PASTAS DE DADOS EXISTEM
    # =====================================================================
    # exist_ok=True significa "se ja existir, tudo bem, nao reclame".
    os.makedirs(app.config["PASTA_INSTANCE"], exist_ok=True)   # onde fica o adba.db
    os.makedirs(app.config["PASTA_BACKUP"], exist_ok=True)     # onde caem os backups

    # =====================================================================
    # PASSO 4 - VALIDAR OS SEGREDOS
    # =====================================================================
    # Em desenvolvimento, apenas imprime um aviso no terminal.
    # Em producao, ProductionConfig.validar() derruba o app de proposito.
    problemas = classe_config.validar(app)
    for problema in problemas:                                  # percorre cada problema encontrado
        app.logger.warning("AVISO DE CONFIGURACAO: %s", problema)

    # =====================================================================
    # PASSO 5 - LIGAR AS EXTENSOES NO APP
    # =====================================================================
    # Aqui cada peca criada em extensions.py finalmente "conhece" o app.
    db.init_app(app)                                # banco de dados

    # render_as_batch=True e obrigatorio para SQLite: o SQLite nao sabe alterar
    # uma coluna existente. Com esta opcao o Alembic contorna criando uma tabela
    # nova, copiando os dados e trocando as duas - tudo sozinho.
    migrate.init_app(app, db, render_as_batch=True)
    login_manager.init_app(app)                     # controle de login
    bcrypt.init_app(app)                            # hash de senhas
    csrf.init_app(app)                              # protecao CSRF em todo POST
    limiter.init_app(app)                           # limite de requisicoes por IP

    # =====================================================================
    # PASSO 5.1 - APRESENTAR AS TABELAS AO SISTEMA
    # =====================================================================
    # Este import parece inutil ("importa e nao usa"), mas e essencial: e ele
    # que faz o Python executar app/models.py. Ao ser executado, cada classe
    # de la se registra sozinha no "db". Sem isto, o Flask-Migrate acharia que
    # o projeto nao tem nenhuma tabela e geraria uma migracao vazia.
    #
    # O import fica DENTRO da funcao, depois do db.init_app, para evitar
    # importacao circular.
    from app import models  # noqa: F401  (F401 = "importado e nao usado", de proposito)

    # =====================================================================
    # PASSO 5.15 - CONFIANCA NO PROXY (so em producao)
    # =====================================================================
    # No PythonAnywhere o sistema nao fala direto com o visitante: existe um
    # servidor intermediario (proxy) na frente. Sem este ajuste, TODO acesso
    # pareceria vir do mesmo IP - o do proxy.
    # Consequencias: o limite de 5 cadastros por hora bloquearia a igreja
    # inteira, e o IP guardado como prova do consentimento LGPD seria inutil.
    #
    # x_for=1 significa "confie em UM proxy a minha frente". Confiar em mais
    # do que existe de verdade permitiria falsificar o IP de origem.
    if not app.config.get("DEBUG"):
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # =====================================================================
    # PASSO 5.2 - REGISTRAR OS COMANDOS DE TERMINAL
    # =====================================================================
    # Habilita "flask criar-admin", "flask seed-eventos" e "flask preparar-sistema".
    from app.comandos import registrar_comandos
    registrar_comandos(app)

    # O comando "flask backup" (secao 7, item 14), num arquivo proprio.
    from app.comandos_backup import registrar_backup
    registrar_backup(app)

    # =====================================================================
    # PASSO 5.3 - FERRAMENTAS DISPONIVEIS DENTRO DOS TEMPLATES
    # =====================================================================
    # O decorador @app.context_processor injeta estes nomes em TODO template,
    # sem precisar passa-los em cada render_template.
    @app.context_processor
    def injetar_ajudantes():
        from app import opcoes
        from app import tempo
        return {
            "opcoes": opcoes,   # para traduzir "culto_ceia" -> "Culto da Ceia"
            "tempo": tempo,     # para formatar datas no padrao brasileiro
        }

    # --- FILTROS DE TEMPLATE ---------------------------------------------
    # Um "filtro" e usado com a barra vertical: {{ alma.telefone|telefone }}
    # Guardamos o telefone so com numeros ("16992805852") para a busca e a
    # deteccao de duplicatas funcionarem. Mas ninguem le assim - entao na
    # hora de EXIBIR passamos pelo filtro, que devolve "(16) 99280-5852".
    from app.validacao import formatar_telefone
    app.add_template_filter(formatar_telefone, "telefone")

    # =====================================================================
    # PASSO 5.4 - REGISTRAR AS ROTAS (Blueprints)
    # =====================================================================
    # Cada Blueprint e um bloco de URLs sobre um assunto. Registrar significa
    # "app, passe a atender estas URLs".
    from app.rotas.publico import publico
    from app.rotas.auth import auth
    from app.rotas.painel import painel
    from app.rotas.acoes import acoes
    from app.rotas.responsaveis import responsaveis
    from app.rotas.eventos import eventos
    from app.rotas.relatorios import relatorios
    from app.rotas.admin import admin

    app.register_blueprint(publico)
    app.register_blueprint(auth)
    app.register_blueprint(painel)
    app.register_blueprint(acoes)
    app.register_blueprint(responsaveis)
    app.register_blueprint(eventos)
    app.register_blueprint(relatorios)
    app.register_blueprint(admin)

    # =====================================================================
    # PASSO 6 - CABECALHOS DE SEGURANCA EM TODA RESPOSTA
    # =====================================================================
    # O decorador @app.after_request faz esta funcao rodar DEPOIS de cada
    # requisicao, logo antes da resposta sair para o navegador.
    @app.after_request
    def aplicar_cabecalhos_seguranca(resposta):
        # Impede o navegador de "adivinhar" o tipo do arquivo.
        # Bloqueia um ataque onde um .txt malicioso e executado como JavaScript.
        resposta.headers["X-Content-Type-Options"] = "nosniff"

        # Impede que outro site coloque o sistema dentro de um <iframe> invisivel
        # para enganar o usuario (ataque chamado clickjacking).
        resposta.headers["X-Frame-Options"] = "DENY"

        # Limita o que e enviado no cabecalho Referer ao navegar para fora,
        # evitando vazar a URL interna (que contem UUIDs) para sites de terceiros.
        resposta.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Desliga permissoes de hardware que o sistema nunca vai usar.
        resposta.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        return resposta                              # devolve a resposta ja carimbada

    # =====================================================================
    # PASSO 7 - A PORTA DA FRENTE  /
    # =====================================================================
    @app.route("/")
    def inicio():
        """
        Quem digita o endereco do sistema sem caminho nenhum cai aqui.
        Logado -> painel. Nao logado -> tela de entrada.
        Nao existe pagina publica na raiz: o sistema inteiro e privado,
        com a unica excecao do formulario de cadastro (que tem token proprio).
        """
        from flask_login import current_user
        if current_user.is_authenticated:
            return redirect(url_for("painel.index"))
        return redirect(url_for("auth.login"))

    # =====================================================================
    # PASSO 7.1 - TRAVA DA TROCA DE SENHA OBRIGATORIA
    # =====================================================================
    # @app.before_request roda ANTES de cada requisicao, em TODAS as rotas.
    # E o lugar certo para uma regra que vale para o sistema inteiro:
    # "enquanto a senha inicial nao for trocada, nenhuma tela abre".
    #
    # Se a regra estivesse so no login, bastaria digitar /painel na barra de
    # endereco para pular a troca.
    @app.before_request
    def exigir_troca_de_senha():
        from flask_login import current_user

        if not current_user.is_authenticated:
            return None                      # nao esta logado: nao e problema daqui
        if not current_user.deve_trocar_senha:
            return None                      # ja trocou: segue o jogo

        # Rotas liberadas durante a troca, senao a pessoa ficaria presa num
        # laco infinito de redirecionamento.
        liberadas = {"auth.trocar_senha", "auth.logout", "static"}
        if request.endpoint in liberadas:
            return None

        return redirect(url_for("auth.trocar_senha"))

    # =====================================================================
    # PASSO 8 - PAGINAS DE ERRO PERSONALIZADAS
    # =====================================================================
    # Sem isso, o Flask mostra uma tela branca feia com texto tecnico.
    # A 403 e especialmente importante: e ela que um responsavel vai ver ao
    # tentar abrir a ficha de uma alma que nao e dele (secao 7, item 2).
    @app.errorhandler(403)
    def erro_403(e):
        return render_template("erros/403.html"), 403      # 403 = proibido

    @app.errorhandler(404)
    def erro_404(e):
        return render_template("erros/404.html"), 404      # 404 = nao encontrado

    @app.errorhandler(429)
    def erro_429(e):
        """
        Limite de envios atingido (secao 7, item 7).

        Sem este tratador, o Flask-Limiter mostra uma pagina crua em ingles
        que ainda por cima REVELA o limite exato ("5 per 1 hour") - entregando
        de bandeja o numero que um atacante precisa para contornar a trava.

        Aqui a pessoa recebe uma explicacao em portugues, sabe o que fazer, e
        nao descobre qual e o limite.
        """
        return render_template("erros/429.html"), 429

    @app.errorhandler(500)
    def erro_500(e):
        db.session.rollback()   # desfaz qualquer gravacao pela metade no banco
        return render_template("erros/500.html"), 500      # 500 = erro interno

    # =====================================================================
    # PASSO 9 - DEVOLVER O APP PRONTO
    # =====================================================================
    return app
