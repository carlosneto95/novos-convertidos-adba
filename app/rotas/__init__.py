# -*- coding: utf-8 -*-
"""
app/rotas/ - PACOTE DAS ROTAS (as URLs do sistema).

Cada arquivo desta pasta e um "Blueprint": um bloco de URLs sobre um assunto.
Isso evita um arquivo gigante e deixa cada etapa mexendo em um lugar so:

    publico.py       -> /cadastro/<token>          (Etapa 3)
    auth.py          -> /login, /logout            (Etapa 4)
    painel.py        -> /painel e o drawer lateral (Etapas 5 e 6)
    responsaveis.py  -> /responsaveis              (Etapa 7)
    eventos.py       -> /eventos                   (Etapa 7)
    relatorios.py    -> /relatorios e o Excel      (Etapa 8)
    admin.py         -> /mesclagem                 (Etapa 9)

Na Etapa 1 a pasta esta vazia de proposito: ainda nao ha rota de verdade.
"""
