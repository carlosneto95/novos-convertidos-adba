# -*- coding: utf-8 -*-
"""
config.py - CENTRAL DE CONFIGURACAO do sistema ADBA.

Toda regra ajustavel do sistema (prazos, cores, textos da igreja) mora aqui.
Se um dia o pastor decidir que o prazo passa de 7 para 10 dias, voce muda
UMA linha neste arquivo e o sistema inteiro obedece.

REGRA DE OURO: neste arquivo nao existe senha nem chave escrita a mao.
Tudo que e segredo vem do arquivo .env, lido pela funcao load_dotenv().
"""

# --- IMPORTACOES ----------------------------------------------------------
import os                              # "os" da acesso as variaveis de ambiente do sistema
from datetime import timedelta         # timedelta = um periodo de tempo (ex: 8 horas)
from pathlib import Path               # Path trata caminhos de pasta funcionando em Windows e Linux
from dotenv import load_dotenv         # funcao que le o arquivo .env


# --- LOCALIZANDO A RAIZ DO PROJETO ----------------------------------------
# __file__ e o caminho deste proprio arquivo (config.py).
# .resolve() transforma em caminho absoluto completo.
# .parent sobe um nivel, chegando na pasta raiz "Novos Convertidos".
BASE_DIR = Path(__file__).resolve().parent

# Le o arquivo .env e joga cada linha dele para dentro das variaveis de ambiente.
# A partir daqui, os.environ.get("SECRET_KEY") funciona.
load_dotenv(BASE_DIR / ".env")


# --- AJUDANTES ------------------------------------------------------------
def _texto(nome, padrao=""):
    """Le uma variavel do .env como texto. Se nao existir, devolve o padrao."""
    valor = os.environ.get(nome)                    # busca a variavel pelo nome
    if valor is None or valor.strip() == "":        # se nao existe ou esta vazia...
        return padrao                               # ...devolve o valor padrao
    return valor.strip()                            # senao devolve sem espacos nas pontas


def _inteiro(nome, padrao):
    """Le uma variavel do .env como numero inteiro."""
    try:
        return int(os.environ.get(nome, padrao))    # tenta converter o texto para numero
    except (TypeError, ValueError):                 # se vier lixo (ex: "abc")...
        return padrao                               # ...usa o padrao em vez de quebrar o sistema


# ===========================================================================
# CLASSE BASE - tudo que vale para QUALQUER ambiente
# ===========================================================================
class Config:

    # -----------------------------------------------------------------
    # 1. IDENTIDADE DA IGREJA
    #    Usada nos cabecalhos das telas e no texto legal da LGPD.
    # -----------------------------------------------------------------
    IGREJA_NOME = "ADBA"                                          # nome curto, aparece no topo das telas
    IGREJA_NOME_LEGAL = "Assembleia de Deus Ministério Belém"     # razao social, aparece no termo LGPD
    IGREJA_CNPJ = "45.275.005/0001-65"                            # CNPJ, aparece no rodape do termo
    IGREJA_TELEFONE = "(16) 99280-5852"                           # canal para pedir acesso/exclusao de dados

    # -----------------------------------------------------------------
    # 2. REGRAS DO SEMAFORO (secao 4 da especificacao)
    #    Estes numeros definem quando um card fica verde, amarelo,
    #    laranja ou vermelho. Todo o calculo acontece no BACKEND.
    # -----------------------------------------------------------------
    PRAZO_PRIMEIRO_CONTATO_HORAS = 48    # alma recem-designada: 48h para o primeiro contato
    PRAZO_CONTATO_DIAS = 7               # depois do 1o contato: no maximo 7 dias entre contatos
    PRAZO_DESIGNACAO_HORAS = 24          # meta do Admin: designar responsavel em ate 24h

    # Faixas em DIAS. O numero e o LIMITE SUPERIOR de cada cor.
    # 0 a 7 -> verde | 8 a 14 -> amarelo | 15 a 21 -> laranja | 22+ -> vermelho
    FAIXAS_SEMAFORO = {
        "verde": 7,
        "amarelo": 14,
        "laranja": 21,
    }

    # Codigos hexadecimais das cores (secao 6 da especificacao).
    # Ficam aqui para que o backend mande a cor ja pronta para o HTML.
    CORES_SEMAFORO = {
        "verde":    "#16a34a",   # em dia
        "amarelo":  "#eab308",   # atencao
        "laranja":  "#f97316",   # atrasado
        "vermelho": "#dc2626",   # critico
        "roxo":     "#9333ea",   # aguardando responsavel (so o Admin ve)
    }

    # -----------------------------------------------------------------
    # 3. REGRAS DE NEGOCIO E PRIVACIDADE
    # -----------------------------------------------------------------
    # True = campo "observacao sensivel" so aparece para o Admin e para o
    # responsavel ATUAL daquela alma. Toda leitura vira registro de auditoria.
    OBSERVACAO_SENSIVEL_RESTRITA = True

    # Idade a partir da qual a pessoa assina sozinha o termo LGPD.
    # Abaixo disso, o formulario exige nome e telefone do responsavel legal.
    IDADE_MAIORIDADE = 18

    # Quantos dias de eventos o comando "flask seed-eventos" gera para frente.
    DIAS_AGENDA_EVENTOS = 90

    # Janela de presencas exibida no drawer lateral (secao 5.3).
    DIAS_JANELA_PRESENCAS = 60

    # -----------------------------------------------------------------
    # 4. SEGREDOS - vem do .env, NUNCA escritos aqui
    # -----------------------------------------------------------------
    SECRET_KEY = _texto("SECRET_KEY")          # assina o cookie de sessao
    CADASTRO_TOKEN = _texto("CADASTRO_TOKEN")  # parte secreta da URL publica /cadastro/<token>

    # Credenciais do admin inicial, lidas pelo comando "flask criar-admin".
    ADMIN_NOME = _texto("ADMIN_NOME", "Administrador")
    ADMIN_LOGIN = _texto("ADMIN_LOGIN", "admin")
    ADMIN_SENHA_INICIAL = _texto("ADMIN_SENHA_INICIAL", "")

    # -----------------------------------------------------------------
    # 5. BANCO DE DADOS
    # -----------------------------------------------------------------
    # Se DATABASE_URL existir no .env, usa ela (permite trocar para PostgreSQL
    # no futuro SEM alterar uma linha de codigo).
    # Se estiver vazia, monta o caminho do SQLite em instance/adba.db.
    SQLALCHEMY_DATABASE_URI = _texto(
        "DATABASE_URL",
        "sqlite:///" + str(BASE_DIR / "instance" / "adba.db"),
    )

    # Desliga um recurso antigo do SQLAlchemy que so consome memoria.
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # pool_pre_ping testa a conexao antes de usar: evita erro de "conexao morta".
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # -----------------------------------------------------------------
    # 6. SESSAO E COOKIE (secao 7, item 9)
    # -----------------------------------------------------------------
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)  # login expira em 8 horas
    SESSION_COOKIE_HTTPONLY = True   # JavaScript NAO le o cookie -> barra roubo de sessao por XSS
    SESSION_COOKIE_SAMESITE = "Lax"  # navegador nao manda o cookie vindo de outro site -> barra CSRF
    SESSION_COOKIE_SECURE = True     # cookie so viaja em HTTPS (sobrescrito no ambiente local)
    SESSION_COOKIE_NAME = "adba_sessao"
    REMEMBER_COOKIE_HTTPONLY = True  # mesma protecao para o cookie "lembrar de mim"
    REMEMBER_COOKIE_SECURE = True
    REMEMBER_COOKIE_DURATION = timedelta(hours=8)

    # --- Quando o sistema NAO mora na raiz do dominio --------------------
    # No PythonAnywhere este sistema divide o endereco com outros dois, cada
    # um sob um prefixo: /demandas, /fechamento e /adba. Um dominio = um
    # pote de cookies compartilhado, entao dois cuidados aqui:
    #
    #   1. SESSION_COOKIE_NAME ja e proprio ("adba_sessao"), e nao "session".
    #      Com o nome padrao do Flask, logar aqui SOBRESCREVERIA o cookie dos
    #      outros dois sistemas e derrubaria a sessao de quem estivesse neles.
    #
    #   2. O PATH do cookie limita para QUAIS enderecos o navegador envia o
    #      cookie. Sem isso ele vale "/" e nossa sessao viaja junto de toda
    #      requisicao aos outros sistemas, sem necessidade nenhuma.
    #
    # URL_PREFIXO vem do .env e precisa ser IGUAL ao prefixo usado no arquivo
    # WSGI (ver deploy/bloco_wsgi_adba.py). Vazio = sistema na raiz.
    #
    # ATENCAO: prefixo errado aqui faz o login falhar EM SILENCIO - o
    # navegador guarda o cookie e simplesmente nunca o devolve.
    URL_PREFIXO = _texto("URL_PREFIXO", "").rstrip("/")
    SESSION_COOKIE_PATH = URL_PREFIXO or "/"
    REMEMBER_COOKIE_PATH = URL_PREFIXO or "/"

    # -----------------------------------------------------------------
    # 7. PROTECAO CSRF (secao 7, item 4)
    # -----------------------------------------------------------------
    WTF_CSRF_ENABLED = True     # liga o token anti-CSRF em TODOS os formularios
    WTF_CSRF_TIME_LIMIT = None  # o token vale enquanto a sessao viver (evita erro em form longo)

    # -----------------------------------------------------------------
    # 8. LIMITE DE REQUISICOES (secao 7, itens 7 e 10)
    # -----------------------------------------------------------------
    RATELIMIT_STORAGE_URI = "memory://"   # contador na memoria (suficiente no PythonAnywhere)
    RATELIMIT_HEADERS_ENABLED = False     # nao revela os limites nos cabecalhos da resposta

    # --- Limite do formulario publico ---------------------------------
    # A especificacao sugeria "5 por hora". Na pratica isso e POUCO DEMAIS,
    # por um motivo que so aparece no uso real:
    #
    #   NO WI-FI DA IGREJA, TODO MUNDO SAI PELO MESMO IP.
    #
    # O limite e por IP. Entao 5/hora nao significa "5 cadastros por pessoa":
    # significa 5 para a igreja INTEIRA. Numa noite de muitas conversoes, com
    # tres irmaos cadastrando ao mesmo tempo, o sexto cadastro seria recusado
    # - e uma alma de verdade ficaria de fora.
    #
    # 30 por hora acomoda uma noite cheia. O limite diario de 100 continua
    # sendo a trava contra quem tentar inundar o sistema.
    #
    # A defesa principal contra robo NAO e este numero: e o honeypot (o campo
    # invisivel) somado ao token secreto na URL. Isto aqui e so o ultimo freio.
    LIMITE_CADASTRO_PUBLICO = _texto("LIMITE_CADASTRO_PUBLICO", "30 per hour;100 per day")

    # --- Limite do login ------------------------------------------------
    # Aqui o raciocinio e o OPOSTO: o login e a porta da casa, e quem erra a
    # senha 5 vezes em 15 minutos provavelmente esta chutando. Como so quem
    # ACERTA nao gasta tentativa (ver app/rotas/auth.py), um usuario legitimo
    # praticamente nunca encosta neste limite.
    LIMITE_LOGIN = _texto("LIMITE_LOGIN", "5 per 15 minutes")

    # -----------------------------------------------------------------
    # 9. TAMANHO MAXIMO DE REQUISICAO
    # -----------------------------------------------------------------
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024  # recusa qualquer envio acima de 2 MB

    # -----------------------------------------------------------------
    # 10. PASTAS DE TRABALHO
    # -----------------------------------------------------------------
    BASE_DIR = BASE_DIR                       # raiz do projeto
    PASTA_BACKUP = BASE_DIR / "backups"       # destino do comando "flask backup"
    PASTA_INSTANCE = BASE_DIR / "instance"    # onde mora o arquivo adba.db

    # -----------------------------------------------------------------
    # 11. APARENCIA
    # -----------------------------------------------------------------
    COR_PRIMARIA = "#0f4c5c"   # azul-marca escuro (secao 6)

    @staticmethod
    def validar(app):
        """Checagem feita quando o app sobe. Avisa cedo em vez de falhar tarde."""
        problemas = []                                        # comeca com a lista vazia
        if not app.config.get("SECRET_KEY"):                  # sem chave secreta o login nao e seguro
            problemas.append("SECRET_KEY ausente no .env")
        if not app.config.get("CADASTRO_TOKEN"):              # sem token a URL publica nao existe
            problemas.append("CADASTRO_TOKEN ausente no .env")
        return problemas                                      # devolve a lista para quem chamou


# ===========================================================================
# AMBIENTE LOCAL - o seu computador
# ===========================================================================
class DevelopmentConfig(Config):
    DEBUG = True                    # mostra o erro detalhado na tela e recarrega ao salvar arquivo
    SESSION_COOKIE_SECURE = False   # ATENCAO: em http://localhost nao existe HTTPS;
    REMEMBER_COOKIE_SECURE = False  # se ficasse True, o login simplesmente nao funcionaria local.


# ===========================================================================
# AMBIENTE DE PRODUCAO - PythonAnywhere
# ===========================================================================
class ProductionConfig(Config):
    DEBUG = False                   # NUNCA True em producao: vazaria codigo e variaveis na tela
    SESSION_COOKIE_SECURE = True    # cookie so trafega criptografado
    REMEMBER_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = "https"

    @staticmethod
    def validar(app):
        """Em producao, faltar segredo nao e aviso: e parada obrigatoria."""
        problemas = Config.validar(app)          # reaproveita a checagem da classe base
        if problemas:                            # se sobrou qualquer problema...
            raise RuntimeError(                  # ...derruba o app na hora, de proposito
                "Configuracao invalida para producao: " + "; ".join(problemas)
            )
        return []


# ===========================================================================
# SELETOR - traduz o texto APP_ENV do .env para a classe correta
# ===========================================================================
AMBIENTES = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
}


def obter_config():
    """Le APP_ENV do .env e devolve a classe de configuracao correspondente."""
    nome = _texto("APP_ENV", "development").lower()   # le o ambiente, em minusculas
    return AMBIENTES.get(nome, DevelopmentConfig)     # se vier algo estranho, assume o modo local
