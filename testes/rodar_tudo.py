# -*- coding: utf-8 -*-
"""
testes/rodar_tudo.py - RODA TODAS AS VERIFICACOES DO PROJETO.

    python testes/rodar_tudo.py

Rode isto ANTES de subir qualquer mudanca para o servidor. Se algo aqui
falhar, alguma protecao parou de funcionar.
"""
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")

AQUI = os.path.dirname(os.path.abspath(__file__))

SUITES = [
    ("Banco de dados",        "teste_etapa2.py"),
    ("Formulario publico",    "teste_etapa3.py"),
    ("Autenticacao",          "teste_etapa4.py"),
    ("Painel e semaforo",     "teste_etapa5.py"),
    ("Ficha lateral",         "teste_ficha.py"),
    ("Acoes da ficha",        "teste_acoes.py"),
    ("Responsaveis e eventos", "teste_etapa7.py"),
    ("Relatorios e Excel",    "teste_etapa8.py"),
    ("Mesclagem e backup",    "teste_etapa9.py"),
    ("REVISAO DE SEGURANCA",  "revisao_seguranca.py"),
]

print("=" * 66)
print("  VERIFICACAO COMPLETA DO SISTEMA")
print("=" * 66)

total = 0
quebrou = []

for nome, arquivo in SUITES:
    r = subprocess.run(
        [sys.executable, os.path.join(AQUI, arquivo)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    linha = ""
    for l in (r.stdout or "").splitlines():
        if "passaram" in l:
            linha = l.strip()
    n = 0
    for pedaco in linha.split():
        if pedaco.isdigit():
            n = int(pedaco)
            break
    total += n
    estado = "OK " if r.returncode == 0 else "FALHOU"
    print(f"  [{estado}] {nome:24s} {linha}")
    if r.returncode != 0:
        quebrou.append((nome, r.stdout))

print("=" * 66)
if quebrou:
    print(f"  {total} verificacoes | {len(quebrou)} SUITE(S) COM FALHA")
    for nome, saida in quebrou:
        print(f"\n--- {nome} ---")
        for l in saida.splitlines():
            if "FALHA" in l:
                print("   ", l.strip())
else:
    print(f"  {total} verificacoes, tudo passando")
print("=" * 66)

sys.exit(1 if quebrou else 0)
