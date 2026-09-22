# -*- coding: utf-8 -*-
"""
app/comandos_exemplo.py - DADOS DE MENTIRA PARA TESTAR O PAINEL.

    flask dados-exemplo            cria
    flask dados-exemplo --apagar   remove

POR QUE ISSO EXISTE?
Um painel vazio nao prova nada. Para conferir se o semaforo pinta as cores
certas, e preciso ter almas em situacoes diferentes: uma em dia, uma atrasada,
uma critica, uma sem responsavel. Criar isso a mao levaria meia hora e daria
errado.

SEGURANCA DESTE COMANDO:
Todo registro criado aqui leva a marca "EXEMPLO" no campo cadastrante_nome e
o telefone comeca com 1699000. Assim o comando --apagar remove EXATAMENTE o que
ele criou, sem chance de encostar em dados de pessoas de verdade.
"""

import random
from datetime import timedelta

import click
from flask.cli import with_appcontext

from app.extensions import db
from app.comandos import _ok, _aviso, _titulo


# A marca que identifica todo registro de mentira.
MARCA = "EXEMPLO"

# Prefixo dos telefones inventados (nenhum telefone real comeca assim aqui).
PREFIXO_TELEFONE = "1699000"   # + 4 digitos = 11 no total (celular valido)


@click.command("dados-exemplo")
@click.option("--apagar", is_flag=True, help="Apaga os dados de exemplo em vez de criar.")
@with_appcontext
def dados_exemplo(apagar):
    """Cria almas ficticias para voce VER o semaforo funcionando."""

    from app.models import Usuario, NovoConvertido, Contato, Atribuicao
    from app.tempo import agora, hoje
    from app import opcoes

    # =====================================================================
    # MODO APAGAR
    # =====================================================================
    if apagar:
        _titulo("Apagando os dados de exemplo")

        almas = db.session.execute(
            db.select(NovoConvertido).where(NovoConvertido.cadastrante_nome == MARCA)
        ).scalars().all()

        for alma in almas:
            # Apaga primeiro o que DEPENDE da alma. Se tentassemos apagar a
            # alma antes, o banco recusaria: ha contatos apontando para ela.
            db.session.execute(db.delete(Contato).where(Contato.convertido_id == alma.id))
            db.session.execute(db.delete(Atribuicao).where(Atribuicao.convertido_id == alma.id))
            db.session.delete(alma)

        usuarios = db.session.execute(
            db.select(Usuario).where(Usuario.login.in_(["joao.exemplo", "ana.exemplo"]))
        ).scalars().all()
        for u in usuarios:
            db.session.delete(u)

        db.session.commit()
        _ok(f"{len(almas)} alma(s) e {len(usuarios)} usuario(s) de exemplo apagados.")
        return

    # =====================================================================
    # MODO CRIAR
    # =====================================================================
    _titulo("Criando dados de exemplo")

    # --- 1. Dois responsaveis ficticios ----------------------------------
    responsaveis = []
    for login, nome in [("joao.exemplo", "Joao Pereira"), ("ana.exemplo", "Ana Lima")]:
        u = db.session.execute(
            db.select(Usuario).where(Usuario.login == login)
        ).scalar_one_or_none()

        if u is None:
            u = Usuario(
                nome=nome, login=login, papel="responsavel",
                ativo=True, deve_trocar_senha=True,
                telefone=PREFIXO_TELEFONE + "0000",
            )
            u.definir_senha("exemplo123")
            db.session.add(u)
        responsaveis.append(u)

    db.session.flush()   # gera os ids sem fechar a transacao
    _ok("2 responsaveis de exemplo prontos (login joao.exemplo / ana.exemplo, senha exemplo123)")

    # --- 2. As almas, uma para cada situacao do semaforo -----------------
    # Cada linha e:
    #   nome, sexo, dias desde a designacao,
    #   dias desde a ultima tentativa (None = nunca tentaram),
    #   dias desde o ultimo contato efetivo (None = nunca conseguiram),
    #   o que deve aparecer na tela
    ROTEIRO = [
        ("Maria Aparecida Silva",  "F", 30,   2,    2, "VERDE - contato ha 2 dias"),
        ("Jose Carlos Oliveira",   "M", 45,   1,    1, "VERDE - contato ontem"),
        ("Joana Beatriz Souza",    "F", 14,   5,    5, "VERDE - dentro do prazo"),
        ("Bruno Cesar Nogueira",   "M",  1, None, None, "VERDE - designado ontem, prazo de 48h correndo"),
        ("Pedro Henrique Costa",   "M", 60,  10,   10, "AMARELO - 10 dias sem contato"),
        ("Lucia Helena Martins",   "F", 40,   3, None, "VERMELHO com icone 'nao responde' - tentam sempre, ela nunca atende"),
        ("Roberto Alves Pereira",  "M", 90,  18,   18, "LARANJA - 18 dias"),
        ("Fernanda Dias Rocha",    "F", 50,  25,   25, "VERMELHO - 25 dias, critico"),
        ("Antonio Marcos Lima",    "M", 35, None, None, "VERMELHO - 35 dias e ninguem tentou"),
        ("Carla Regina Fernandes", "F",  3, None, None, "VERDE com alerta - 3 dias sem contato, prazo de 48h estourado"),
    ]

    # Lista de trabalhos sem o "outro" (que exigiria preencher trabalho_outro).
    trabalhos = [t for t in opcoes.TRABALHOS.keys() if t != "outro"]

    criadas = 0
    for i, (nome, sexo, dias_desig, dias_tent, dias_efet, descricao) in enumerate(ROTEIRO):

        ja_existe = db.session.execute(
            db.select(NovoConvertido).where(NovoConvertido.nome_completo == nome)
        ).scalar_one_or_none()
        if ja_existe:
            continue

        responsavel = responsaveis[i % len(responsaveis)]
        idade = [17, 22, 28, 34, 41, 55, 19, 63, 30, 26][i]
        nascimento = hoje().replace(year=hoje().year - idade)

        alma = NovoConvertido(
            nome_completo=nome,
            telefone=f"{PREFIXO_TELEFONE}{1000 + i}",
            sexo=sexo,
            data_nascimento=nascimento,
            cidade="Ribeirao Preto", uf="SP", bairro="Centro",
            trabalho=trabalhos[i % len(trabalhos)],
            data_conversao=hoje() - timedelta(days=dias_desig),
            departamento=opcoes.sugerir_departamento(sexo, idade) or "irmaos",
            como_chegou="Registro de exemplo, criado para testar o painel.",
            cadastrante_nome=MARCA,
            cadastrante_telefone=PREFIXO_TELEFONE + "0000",
            consentimento_em=agora() - timedelta(days=dias_desig),
            consentimento_ip="127.0.0.1",
            status_ciclo=opcoes.STATUS_ATIVO,
            status_alterado_em=agora() - timedelta(days=dias_desig),
            responsavel_atual_id=responsavel.id,
            designado_em=agora() - timedelta(days=dias_desig),
            criado_em=agora() - timedelta(days=dias_desig),
        )
        db.session.add(alma)
        db.session.flush()        # precisa do id da alma para os contatos

        db.session.add(
            Atribuicao(
                convertido_id=alma.id,
                responsavel_id=responsavel.id,
                inicio=agora() - timedelta(days=dias_desig),
                motivo="Designacao de exemplo",
            )
        )

        # --- Os contatos que movem os dois relogios ----------------------
        if dias_tent is not None:

            # Se o ultimo efetivo e mais antigo que a ultima tentativa,
            # criamos DOIS contatos: um efetivo antigo e uma tentativa
            # recente sem resposta. E esse par que produz o icone 🚫.
            if dias_efet is not None and dias_efet != dias_tent:
                db.session.add(Contato(
                    convertido_id=alma.id, responsavel_id=responsavel.id,
                    tipo="telefone",
                    data_hora=agora() - timedelta(days=dias_efet),
                    resultado="efetivo",
                    relato="Conversa de exemplo: contou como chegou na igreja.",
                    criado_em=agora() - timedelta(days=dias_efet),
                ))

            db.session.add(Contato(
                convertido_id=alma.id, responsavel_id=responsavel.id,
                tipo=["telefone", "whatsapp", "presencial"][i % 3],
                data_hora=agora() - timedelta(days=dias_tent),
                resultado="efetivo" if dias_efet == dias_tent else "sem_resposta",
                relato="Registro de exemplo.",
                criado_em=agora() - timedelta(days=dias_tent),
            ))

        criadas += 1
        click.echo(f"       {alma.codigo_formatado} {nome:24s} {descricao}")

    # --- 3. Tres almas esperando responsavel (o ROXO) --------------------
    roxas = 0
    for i, (nome, sexo, horas, idade) in enumerate([
        ("Vanessa Oliveira Ramos", "F", 4, 19),
        ("Marcelo Tadeu Brito", "M", 30, 26),
        ("Simone Aparecida Cruz", "F", 72, 38),
    ]):
        ja_existe = db.session.execute(
            db.select(NovoConvertido).where(NovoConvertido.nome_completo == nome)
        ).scalar_one_or_none()
        if ja_existe:
            continue

        db.session.add(NovoConvertido(
            nome_completo=nome,
            telefone=f"{PREFIXO_TELEFONE}{2000 + i}",
            sexo=sexo,
            data_nascimento=hoje().replace(year=hoje().year - idade),
            cidade="Ribeirao Preto", uf="SP",
            trabalho="culto_dominical",
            data_conversao=hoje(),
            departamento=opcoes.sugerir_departamento(sexo, idade) or "irmaos",
            cadastrante_nome=MARCA,
            cadastrante_telefone=PREFIXO_TELEFONE + "0000",
            consentimento_em=agora() - timedelta(hours=horas),
            consentimento_ip="127.0.0.1",
            status_ciclo=opcoes.STATUS_INICIAL,   # o roxo
            criado_em=agora() - timedelta(hours=horas),
        ))
        roxas += 1
        click.echo(f"       ROXO  {nome:24s} aguardando ha {horas}h")

    db.session.commit()

    _ok(f"{criadas} alma(s) em acompanhamento e {roxas} aguardando responsavel.")
    _aviso("Sao dados INVENTADOS. Para apagar tudo: flask dados-exemplo --apagar")
