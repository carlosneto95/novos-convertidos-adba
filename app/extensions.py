# -*- coding: utf-8 -*-
"""
app/extensions.py - as "pecas soltas" do sistema.

POR QUE ESTE ARQUIVO EXISTE?
Imagine que o arquivo A precise do B, e o B precise do A. O Python entra num
looping e quebra ("importacao circular"). E o erro numero 1 de quem comeca
em Flask.

A solucao classica: criar as extensoes AQUI, desligadas de qualquer app.
Depois, o arquivo __init__.py liga cada uma no app com .init_app(app).
Assim ninguem precisa importar ninguem em circulo.
"""

# --- IMPORTACOES ----------------------------------------------------------
from sqlalchemy import MetaData                # guarda o "mapa" das tabelas
from flask_sqlalchemy import SQLAlchemy        # conversa com o banco de dados
from flask_migrate import Migrate              # altera tabelas sem perder dados
from flask_login import LoginManager           # controla quem esta logado
from flask_bcrypt import Bcrypt                # transforma senha em hash
from flask_wtf.csrf import CSRFProtect         # protecao CSRF global
from flask_limiter import Limiter              # limita requisicoes por IP
from flask_limiter.util import get_remote_address  # descobre o IP de quem chamou


# --- AS PECAS -------------------------------------------------------------
# Cada linha cria a peca "vazia". Ela ainda nao sabe de qual app faz parte.

# --- PADRAO DE NOMES DAS TRAVAS DO BANCO ---------------------------------
# Toda trava do banco (chave primaria, chave estrangeira, campo unico, regra de
# validacao) tem um nome. Se deixarmos o banco inventar esses nomes, eles saem
# diferentes a cada vez - e o SQLite NAO consegue alterar uma trava sem saber o
# nome dela. Na pratica: a primeira migracao funcionaria, e a segunda quebraria.
#
# Esta convencao fixa o padrao de uma vez. Ex: a chave estrangeira de
# "contato.convertido_id" vai se chamar sempre "fk_contato_convertido_id_novo_convertido".
CONVENCAO_DE_NOMES = MetaData(
    naming_convention={
        "ix": "ix_%(column_0_label)s",                      # indice (busca rapida)
        "uq": "uq_%(table_name)s_%(column_0_name)s",        # campo unico
        "ck": "ck_%(table_name)s_%(constraint_name)s",      # regra de validacao
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",  # chave estrangeira
        "pk": "pk_%(table_name)s",                          # chave primaria
    }
)

db = SQLAlchemy(metadata=CONVENCAO_DE_NOMES)
# db e o objeto central do banco. Cada tabela e uma classe que herda de
# db.Model. Ex: class Usuario(db.Model)

migrate = Migrate()
# migrate cuida das migracoes (Alembic). Permite rodar "flask db upgrade"
# e mudar a estrutura do banco sem apagar os dados que ja existem.

login_manager = LoginManager()
# login_manager guarda o usuario logado na sessao e protege rotas.

bcrypt = Bcrypt()
# bcrypt gera o hash da senha. bcrypt.generate_password_hash("senha123")
# devolve algo como "$2b$12$Xh...". Esse processo NAO tem volta: nem voce,
# nem eu, nem um invasor consegue ler a senha original a partir do hash.

csrf = CSRFProtect()
# csrf protege TODOS os formularios, inclusive o publico (secao 7, item 4).
# Sem o token correto, o Flask recusa o POST com erro 400.

limiter = Limiter(
    key_func=get_remote_address,   # a "chave" do contador e o IP de quem chamou
    default_limits=[],             # sem limite global; cada rota declara o seu
    storage_uri="memory://",       # contador na memoria (sobrescrito pelo config.py)
)
# limiter serve para dois casos da secao 7:
#   item 7  -> 5 cadastros por hora por IP no formulario publico
#   item 10 -> 5 tentativas de login por 15 minutos por IP


# --- CONFIGURACAO DO LOGIN MANAGER ---------------------------------------
# Estas opcoes nao dependem do app, entao podem ser definidas aqui mesmo.

login_manager.login_view = "auth.login"
# Se alguem sem login tentar abrir /painel, o Flask redireciona para a rota
# chamada "login" dentro do blueprint "auth". (Sera criada na Etapa 4.)

login_manager.login_message = "Faça login para acessar esta página."
login_manager.login_message_category = "aviso"   # categoria usada para colorir o alerta na tela

login_manager.session_protection = "strong"
# "strong" faz o Flask-Login invalidar a sessao se o IP ou o navegador mudarem
# no meio do caminho - sinal classico de cookie roubado.


@login_manager.user_loader
def carregar_usuario(usuario_id):
    """
    O Flask-Login guarda no cookie APENAS o id do usuario - nunca o nome,
    nunca o papel, nunca a senha. A cada requisicao ele chama esta funcao
    passando esse id, e nos buscamos a pessoa no banco.

    Por que isso importa para a seguranca?
    O papel ('admin' ou 'responsavel') e lido do BANCO a cada requisicao.
    Se estivesse guardado no cookie, um invasor poderia tentar alterar o
    valor para virar admin. Do jeito atual, isso e impossivel.

    O import acontece DENTRO da funcao, e nao no topo do arquivo, para evitar
    importacao circular: app/models.py precisa do "db" que esta aqui em cima.
    """
    try:
        from app.models import Usuario          # a tabela de usuarios (criada na Etapa 2)
    except ImportError:
        return None                             # Etapa 1: models.py ainda nao existe

    if not usuario_id:                          # cookie vazio ou corrompido
        return None

    usuario = db.session.get(Usuario, usuario_id)   # busca pela chave primaria (UUID)

    # Trava extra: um usuario desativado pelo Admin perde o acesso na hora,
    # mesmo que o cookie de sessao dele ainda esteja valido.
    if usuario is None or not usuario.ativo:
        return None

    return usuario
