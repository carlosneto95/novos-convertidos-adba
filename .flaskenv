# ===========================================================================
# .flaskenv - configuracao do COMANDO "flask".
#
# Sem este arquivo, voce teria de digitar antes de cada comando:
#     set FLASK_APP=run.py
# Com ele, "flask db upgrade" e "flask criar-admin" funcionam direto.
#
# Este arquivo NAO guarda segredo nenhum - por isso pode ir para o Git.
# Os segredos continuam todos no .env.
# ===========================================================================

FLASK_APP=run.py
