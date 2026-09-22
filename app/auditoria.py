# -*- coding: utf-8 -*-
"""
app/auditoria.py - A CAIXA-PRETA DO SISTEMA (secao 7, item 13).

Um lugar unico para gravar "quem fez o que, quando e de onde".

POR QUE UM ARQUIVO SO PARA ISSO?
Se cada tela gravasse o log do seu jeito, uma hora alguem esqueceria. Com uma
funcao unica, basta uma linha em cada acao importante - e o formato fica igual
para todas, o que torna o log legivel.

A TABELA E SO DE ESCRITA: o sistema grava, ninguem edita, ninguem apaga.
Nao existe rota de alteracao nem de exclusao para ela.

O que a especificacao (secao 3) exige registrar:
    login e logout - designacao - transferencia - mudanca de status -
    mesclagem - exportacao Excel - LEITURA de observacao sensivel -
    criacao e desativacao de usuario
"""

# --- IMPORTACOES ----------------------------------------------------------
from flask import request, has_request_context
from flask_login import current_user

from app.extensions import db
from app.models import LogAuditoria


# ===========================================================================
# NOMES DAS ACOES
# ===========================================================================
# Constantes em vez de texto solto. Se alguem escrever "logout " com espaco,
# o relatorio de auditoria passa a ter duas acoes diferentes que sao a mesma.
LOGIN = "login"
LOGIN_FALHOU = "login_falhou"
LOGOUT = "logout"
SENHA_ALTERADA = "senha_alterada"
USUARIO_CRIADO = "usuario_criado"
USUARIO_DESATIVADO = "usuario_desativado"
USUARIO_REATIVADO = "usuario_reativado"
SENHA_REDEFINIDA = "senha_redefinida"
DESIGNAR = "designar"
TRANSFERIR = "transferir"
STATUS_ALTERADO = "status_alterado"
CONTATO_REGISTRADO = "contato_registrado"
PRESENCA_REGISTRADA = "presenca_registrada"
MESCLAGEM = "mesclagem"
EXPORTACAO_EXCEL = "exportacao_excel"
LEITURA_OBSERVACAO_SENSIVEL = "leitura_observacao_sensivel"
ACESSO_NEGADO = "acesso_negado"
CADASTRO_PUBLICO = "cadastro_publico"
CADASTRO_BLOQUEADO_HONEYPOT = "cadastro_bloqueado_honeypot"


# ===========================================================================
# DE ONDE VEIO O ACESSO
# ===========================================================================
def obter_ip():
    """
    Descobre o IP de quem esta acessando.

    No PythonAnywhere existe um servidor intermediario (proxy) na frente do
    nosso. Sem tratamento, TODO acesso pareceria vir do mesmo IP - o do proxy.
    O ProxyFix, ligado em app/__init__.py quando estamos em producao, corrige
    isso antes de a requisicao chegar aqui.
    """
    if not has_request_context():          # rodando num comando de terminal
        return "terminal"
    return request.headers.get("X-Real-IP") or request.remote_addr or "desconhecido"


def _usuario_atual_id():
    """
    Id de quem esta logado, ou None.

    None acontece em tres casos legitimos:
      - cadastro pelo formulario publico (ninguem esta logado)
      - tentativa de login que falhou (ainda nao ha usuario)
      - comandos de terminal
    """
    try:
        if current_user and current_user.is_authenticated:
            return current_user.id
    except Exception:
        pass                                # fora de um contexto de requisicao
    return None


# ===========================================================================
# A FUNCAO PRINCIPAL
# ===========================================================================
def registrar(acao, entidade=None, entidade_id=None, detalhe=None, usuario_id=None, gravar=False):
    """
    Grava uma linha no log de auditoria.

    Parametros:
        acao        - uma das constantes acima. Ex: auditoria.LOGIN
        entidade    - qual tabela foi afetada. Ex: "novo_convertido"
        entidade_id - qual linha daquela tabela (o UUID)
        detalhe     - texto livre com o antes/depois
        usuario_id  - so quando nao da para descobrir sozinho (ex: login que falhou)
        gravar      - True faz o commit na hora

    SOBRE O "gravar":
    Por padrao a linha so entra na FILA de gravacao (db.session.add). Quem
    chamou fecha a transacao com um commit unico no fim. Assim, se a acao
    principal falhar e for desfeita, o log some junto - e o log nunca conta
    uma historia que nao aconteceu.

    Use gravar=True apenas quando o log E a acao. Ex: um login que falhou -
    nao ha mais nada para gravar junto.
    """
    linha = LogAuditoria(
        usuario_id=usuario_id if usuario_id is not None else _usuario_atual_id(),
        acao=acao,
        entidade=entidade,
        entidade_id=str(entidade_id) if entidade_id else None,
        detalhe=detalhe,
        ip=obter_ip(),
    )

    db.session.add(linha)                   # coloca na fila

    if gravar:
        db.session.commit()                 # grava agora mesmo

    return linha
