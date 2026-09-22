# -*- coding: utf-8 -*-
"""
run.py - PONTO DE ENTRADA PARA O SEU COMPUTADOR.

Use este arquivo apenas para testar localmente:
    python run.py

O servidor que ele liga e o servidor de desenvolvimento do Flask: pratico,
mas lento e inseguro para uso real. No PythonAnywhere quem manda e o wsgi.py.
"""

from app import create_app   # importa a fabrica de app/__init__.py

# Cria a aplicacao. Sem argumento, ela le APP_ENV do .env sozinha.
app = create_app()

# Este "if" e uma trava classica do Python: o bloco abaixo so roda quando
# voce executa "python run.py" diretamente. Se outro arquivo importar run.py,
# o servidor NAO sobe sozinho.
if __name__ == "__main__":
    app.run(
        host="127.0.0.1",  # so aceita conexao da sua propria maquina
        port=5000,         # endereco final: http://127.0.0.1:5000
        debug=True,        # recarrega ao salvar arquivo e mostra erro detalhado
    )
