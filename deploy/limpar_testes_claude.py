# -*- coding: utf-8 -*-
# ===========================================================================
# limpar_testes_claude.py - REMOVE OS REGISTROS DEIXADOS PELOS MEUS TESTES
#
# Rode assim:
#   cd ~/novos-convertidos && source venv/bin/activate
#   python deploy/limpar_testes_claude.py
#
# POR QUE ELE EXISTE:
# Para provar que o botao "Cadastrar outra pessoa" devolve um formulario
# limpo, eu precisei fazer cadastros DE VERDADE no site no ar. Eles gravaram
# linhas no banco de producao. Este script tira exatamente essas linhas.
#
# POR QUE OS NOMES ESTAO ESCRITOS AQUI DENTRO:
# Para que este arquivo NAO seja uma ferramenta de apagar pessoas. Ele so
# alcanca estes tres registros; qualquer outro nome ele ignora. O sistema nao
# tem - e nao deve ter - um comando generico de exclusao: o historico de uma
# alma precisa continuar fazendo sentido (ver LGPD no DEPLOY.md).
#
# ESTE ARQUIVO E DESCARTAVEL. Depois de rodar, ele sai do repositorio.
# ===========================================================================

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from dotenv import load_dotenv
load_dotenv(os.path.join(RAIZ, ".env"))

from app import create_app                       # noqa: E402
from app.extensions import db                    # noqa: E402
from app.models import NovoConvertido            # noqa: E402

# Os tres cadastros que os meus testes criaram, e mais nada.
NOMES = [
    "Pessoa De Teste Apagar",
    "Terceira Pessoa Teste",
    "Quarta Pessoa Teste",
]

app = create_app()

with app.app_context():
    achados = NovoConvertido.query.filter(
        NovoConvertido.nome_completo.in_(NOMES)
    ).all()

    if not achados:
        print("Nada a remover - o banco ja esta limpo.")
        sys.exit(0)

    print("Vou remover %d registro(s):" % len(achados))
    for a in achados:
        # Se alguem ja tiver assumido o acompanhamento, PARAMOS. Seria sinal de
        # que o registro nao e mais so lixo de teste.
        if a.atribuicoes:
            print("  *** %s tem responsavel atribuido. NAO vou mexer. ***"
                  % a.nome_completo)
            sys.exit(1)
        print("  %s  %s  (cadastrado por %s)"
              % (a.codigo_formatado, a.nome_completo, a.cadastrante_nome))

    for a in achados:
        db.session.delete(a)       # contatos e presencas caem junto (cascade)
    db.session.commit()

    sobraram = NovoConvertido.query.filter(
        NovoConvertido.nome_completo.in_(NOMES)
    ).count()
    total = NovoConvertido.query.count()

    print("")
    print("Removidos. Sobraram %d dos de teste." % sobraram)
    print("Total de almas no banco agora: %d" % total)
    print("")
    print("As linhas de AUDITORIA dos cadastros continuam la, de proposito:")
    print("a auditoria e so-acrescimo - e ela que responde 'o que aconteceu'.")
