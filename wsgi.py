# -*- coding: utf-8 -*-
"""
wsgi.py - PONTO DE ENTRADA DO SERVIDOR DE VERDADE (PythonAnywhere).

O PythonAnywhere nao executa "python run.py". Ele procura um arquivo com uma
variavel chamada "application" e conversa com ela pelo padrao WSGI.

Na Etapa 10 voce vai apontar o arquivo WSGI do PythonAnywhere para ca.
"""

import sys                       # permite mexer na lista de pastas que o Python enxerga
from pathlib import Path         # tratamento de caminhos

# Descobre a pasta onde este arquivo esta (a raiz do projeto).
RAIZ = Path(__file__).resolve().parent

# Coloca a raiz na frente da lista de busca do Python.
# Sem isso, o servidor nao encontra o pacote "app" nem o "config".
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

# --- CARREGAR OS SEGREDOS ANTES DE CRIAR O APP ---------------------------
# Esta linha e ESSENCIAL no servidor e facil de esquecer.
#
# No seu computador, o "flask" e o "python run.py" leem o .env sozinhos.
# O servidor do PythonAnywhere NAO: ele so chama este arquivo. Sem carregar
# o .env aqui, o app subiria sem SECRET_KEY, sem CADASTRO_TOKEN e sem
# APP_ENV=production - ou seja, em modo de depuracao, mostrando o codigo na
# tela a qualquer erro.
#
# Com APP_ENV=production, a propria classe ProductionConfig recusa subir se
# faltar algum segredo. Melhor o site nao abrir do que abrir inseguro.
from dotenv import load_dotenv    # noqa: E402
load_dotenv(RAIZ / ".env")

from app import create_app       # noqa: E402  (import depois do sys.path, de proposito)

# O nome "application" e obrigatorio: e exatamente ele que o servidor procura.
application = create_app()
