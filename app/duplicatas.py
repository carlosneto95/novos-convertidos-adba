# -*- coding: utf-8 -*-
"""
app/duplicatas.py - ENCONTRAR E JUNTAR REGISTROS REPETIDOS (secao 5.7).

POR QUE ISSO ACONTECE?
O formulario e publico e qualquer membro cadastra. Na mesma noite, tres
irmaos diferentes podem cadastrar a MESMA pessoa - cada um achando que foi o
primeiro. Sem tratamento, essa alma vira tres almas: tres responsaveis, tres
semaforos, e o relatorio de conversoes mente para cima.

COMO ACHAMOS OS REPETIDOS
Dois sinais, de forcas diferentes:

  1. TELEFONE IGUAL - sinal forte. Duas pessoas com o mesmo numero sao quase
     sempre a mesma pessoa. (Quase: mae e filho as vezes dividem o celular -
     por isso o sistema SUGERE, nunca junta sozinho.)

  2. NOME PARECIDO - sinal fraco. "Maria Aparecida Silva" e "Maria Aparecida
     da Silva" sao a mesma; "Maria Silva" e "Mario Silva" nao sao.

A REGRA DE OURO DESTE ARQUIVO:
o sistema nunca junta nada sozinho. Ele SUGERE, e um Admin confirma. Juntar
duas pessoas diferentes por engano apagaria o acompanhamento de uma delas.
"""

# --- IMPORTACOES ----------------------------------------------------------
import unicodedata
from difflib import SequenceMatcher

from app.extensions import db
from app.models import NovoConvertido, Contato, Presenca, Atribuicao
from app import opcoes, auditoria
from app.tempo import agora
from app.validacao import so_digitos


# Quanto dois nomes precisam se parecer para virarem sugestao.
# 0.86 foi escolhido testando: abaixo disso comecam a aparecer irmaos com
# sobrenome igual; acima, "da Silva" e "Silva" deixam de casar.
SEMELHANCA_MINIMA = 0.86


# ===========================================================================
# COMPARACAO DE NOMES
# ===========================================================================
def normalizar_para_comparar(nome):
    """
    Deixa o nome "pelado" para a comparacao: minusculo, sem acento, sem
    palavrinhas de ligacao.

        "Maria Aparecida da Silva"  ->  "maria aparecida silva"
        "MARIA APARECIDA SILVA"     ->  "maria aparecida silva"

    Sem isso, essas duas nunca casariam - e sao a mesma pessoa.
    """
    if not nome:
        return ""

    # NFD separa a letra do acento ("á" vira "a" + acento); depois jogamos
    # fora tudo que for "marca de acento" (categoria Mn).
    texto = unicodedata.normalize("NFD", str(nome).lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")

    # "da", "de", "dos"... nao ajudam a distinguir ninguem.
    ligacoes = {"da", "de", "do", "das", "dos", "e"}
    palavras = [p for p in texto.split() if p not in ligacoes]

    return " ".join(palavras)


def primeiro_nome(nome):
    """A primeira palavra do nome, ja normalizada."""
    partes = normalizar_para_comparar(nome).split()
    return partes[0] if partes else ""


def mesmo_primeiro_nome(nome_a, nome_b, minimo=0.9):
    """
    O primeiro nome das duas fichas e praticamente o mesmo?

    POR QUE ESTA TRAVA EXISTE:
    "Maria Silva" e "Mario Silva" batem 91% na comparacao do nome inteiro -
    acima do nosso limite. Mas sao duas pessoas diferentes, provavelmente de
    sexos diferentes. O sobrenome igual e comprido puxa a nota para cima e
    esconde a diferenca que importa: o primeiro nome.

    Exigindo que o PRIMEIRO NOME tambem case, "Maria" x "Mario" (80%) cai
    fora, enquanto erros de digitacao de verdade - "Joana" x "Joanna" (89%) -
    continuam sendo pegos.
    """
    a = primeiro_nome(nome_a)
    b = primeiro_nome(nome_b)
    if not a or not b:
        return False
    if a == b:
        return True
    return SequenceMatcher(None, a, b).ratio() >= minimo


def semelhanca(nome_a, nome_b):
    """
    Devolve de 0 a 1 o quanto dois nomes se parecem.

    O SequenceMatcher compara as duas palavras letra a letra e mede quanto
    elas tem em comum. E a mesma ideia do corretor ortografico.
    """
    a = normalizar_para_comparar(nome_a)
    b = normalizar_para_comparar(nome_b)

    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    return SequenceMatcher(None, a, b).ratio()


# ===========================================================================
# ENCONTRAR OS CANDIDATOS
# ===========================================================================
def encontrar_duplicatas():
    """
    Devolve a lista de pares suspeitos, do mais provavel para o menos.

    Cada item:
        {
          "principal": a alma mais ANTIGA (a que sobrevive na mesclagem),
          "duplicata": a mais nova,
          "motivo": "telefone" ou "nome",
          "forca": 0 a 1,
          "explicacao": frase para a tela
        }
    """
    # Duplicatas ja mescladas saem da busca: senao o sistema sugeriria
    # eternamente juntar o que ja foi juntado.
    almas = db.session.execute(
        db.select(NovoConvertido)
        .where(NovoConvertido.mesclado_em_id.is_(None))
        .order_by(NovoConvertido.criado_em.asc())
    ).scalars().all()

    pares = {}   # a chave impede o mesmo par de aparecer duas vezes

    # --- SINAL 1: telefone igual ------------------------------------------
    por_telefone = {}
    for a in almas:
        d = so_digitos(a.telefone)
        if len(d) >= 10:                     # ignora telefone incompleto
            por_telefone.setdefault(d, []).append(a)

    for telefone, grupo in por_telefone.items():
        if len(grupo) < 2:
            continue
        # O grupo ja vem ordenado por data (a consulta ordenou). O primeiro
        # e o mais antigo e sera o principal.
        principal = grupo[0]
        for duplicata in grupo[1:]:
            chave = (principal.id, duplicata.id)
            pares[chave] = {
                "principal": principal,
                "duplicata": duplicata,
                "motivo": "telefone",
                "forca": 1.0,
                "explicacao": "Mesmo telefone",
            }

    # --- SINAL 2: nome parecido -------------------------------------------
    # Comparamos cada alma com as seguintes (nunca com as anteriores), para
    # nao medir o mesmo par duas vezes.
    for i, a in enumerate(almas):
        for b in almas[i + 1:]:
            chave = (a.id, b.id)
            if chave in pares:               # o telefone ja pegou este par
                continue

            s = semelhanca(a.nome_completo, b.nome_completo)
            if s < SEMELHANCA_MINIMA:
                continue

            # A trava do primeiro nome (ver mesmo_primeiro_nome).
            # Sem ela, "Maria Silva" e "Mario Silva" virariam sugestao.
            if not mesmo_primeiro_nome(a.nome_completo, b.nome_completo):
                continue

            # Sexos declarados diferentes derrubam a suspeita por nome.
            # Pelo TELEFONE a suspeita continua valendo (mae e filho dividem
            # o numero), mas por nome parecido nao ha por que insistir.
            if a.sexo and b.sexo and a.sexo != b.sexo:
                continue

            pares[chave] = {
                "principal": a,              # a mais antiga
                "duplicata": b,
                "motivo": "nome",
                "forca": s,
                "explicacao": (
                    "Nome idêntico" if s >= 0.999
                    else f"Nome muito parecido ({round(s * 100)}%)"
                ),
            }

    # Mais provaveis primeiro.
    return sorted(pares.values(), key=lambda p: p["forca"], reverse=True)


# ===========================================================================
# JUNTAR DOIS REGISTROS
# ===========================================================================
# Campos que a mesclagem pode "puxar" da duplicata quando o principal esta
# com eles vazios. Um irmao cadastrou sem endereco, o outro cadastrou com -
# nao faz sentido jogar fora a informacao boa.
CAMPOS_COMPLEMENTARES = [
    "telefone", "sexo", "cep", "logradouro", "numero", "complemento",
    "bairro", "cidade", "uf", "como_chegou", "conhecido_nome", "qual_igreja",
    "responsavel_legal_nome", "responsavel_legal_telefone",
]


def mesclar(principal, duplicata, usuario_id=None):
    """
    Junta a duplicata dentro do registro principal.

    O QUE ACONTECE, EM ORDEM:
      1. os contatos da duplicata passam para o principal
      2. as presencas passam - resolvendo choque quando as duas foram ao
         mesmo culto
      3. o historico de responsaveis passa
      4. os campos vazios do principal sao preenchidos com os da duplicata
      5. a duplicata e MARCADA como mesclada - e NUNCA apagada (secao 5.7)

    POR QUE NAO APAGAR?
    Tres motivos. Se a mesclagem tiver sido um engano, da para desfazer.
    O registro guarda quem cadastrou e quando - parte da prova de
    consentimento da LGPD. E apagar quebraria as chaves do banco.

    Devolve um resumo do que foi movido, para a mensagem na tela.
    """
    if principal.id == duplicata.id:
        raise ValueError("Não dá para mesclar um registro com ele mesmo.")

    if duplicata.mesclado_em_id is not None:
        raise ValueError("Este registro já foi mesclado antes.")

    resumo = {"contatos": 0, "presencas": 0, "presencas_descartadas": 0,
              "atribuicoes": 0, "campos": []}

    # --- 1. CONTATOS ------------------------------------------------------
    contatos = db.session.execute(
        db.select(Contato).where(Contato.convertido_id == duplicata.id)
    ).scalars().all()
    for c in contatos:
        c.convertido_id = principal.id
        resumo["contatos"] += 1

    # --- 2. PRESENCAS -----------------------------------------------------
    # A tabela tem UNIQUE(convertido_id, evento_id). Se as duas fichas foram
    # marcadas no MESMO culto, mover a segunda estouraria o banco. Entao:
    #   - o principal ja tem registro daquele culto? fundimos os dois
    #     (se qualquer um diz "presente", vale presente)
    #   - nao tem? a presenca simplesmente muda de dono
    presencas_do_principal = {
        p.evento_id: p
        for p in db.session.execute(
            db.select(Presenca).where(Presenca.convertido_id == principal.id)
        ).scalars().all()
    }

    presencas = db.session.execute(
        db.select(Presenca).where(Presenca.convertido_id == duplicata.id)
    ).scalars().all()

    for p in presencas:
        existente = presencas_do_principal.get(p.evento_id)
        if existente:
            # Presenca vence falta: se um irmao marcou que ela esteve, ela
            # esteve - o outro pode simplesmente nao ter visto.
            if p.presente and not existente.presente:
                existente.presente = True
            db.session.delete(p)
            resumo["presencas_descartadas"] += 1
        else:
            p.convertido_id = principal.id
            resumo["presencas"] += 1

    # --- 3. HISTORICO DE RESPONSAVEIS -------------------------------------
    atribuicoes = db.session.execute(
        db.select(Atribuicao).where(Atribuicao.convertido_id == duplicata.id)
    ).scalars().all()
    for a in atribuicoes:
        a.convertido_id = principal.id
        # Uma atribuicao da duplicata que estava ABERTA precisa ser fechada:
        # o principal ja tem o proprio responsavel atual, e duas atribuicoes
        # abertas ao mesmo tempo quebrariam a logica do "responsavel de agora".
        if a.fim is None:
            a.fim = agora()
        resumo["atribuicoes"] += 1

    # --- 4. COMPLETAR OS CAMPOS VAZIOS ------------------------------------
    for campo in CAMPOS_COMPLEMENTARES:
        valor_principal = getattr(principal, campo, None)
        valor_duplicata = getattr(duplicata, campo, None)
        if not valor_principal and valor_duplicata:
            setattr(principal, campo, valor_duplicata)
            resumo["campos"].append(campo)

    # Se o principal nao tem responsavel e a duplicata tem, aproveita.
    if not principal.responsavel_atual_id and duplicata.responsavel_atual_id:
        principal.responsavel_atual_id = duplicata.responsavel_atual_id
        principal.designado_em = duplicata.designado_em or agora()
        if principal.status_ciclo == opcoes.STATUS_INICIAL:
            principal.status_ciclo = opcoes.STATUS_ATIVO
            principal.status_alterado_em = agora()
        resumo["campos"].append("responsavel")

    # A observacao sensivel NAO e juntada automaticamente (secao 7, item 11):
    # ela so existe se alguem a escreveu com intencao. Se as duas fichas
    # tiverem, o Admin decide depois, lendo as duas.

    # --- 5. MARCAR A DUPLICATA -------------------------------------------
    duplicata.mesclado_em_id = principal.id

    auditoria.registrar(
        acao=auditoria.MESCLAGEM,
        entidade="novo_convertido",
        entidade_id=principal.id,
        detalhe=(
            f"{duplicata.codigo_formatado} ({duplicata.nome_completo}) "
            f"mesclada em {principal.codigo_formatado} ({principal.nome_completo}) | "
            f"contatos={resumo['contatos']} presencas={resumo['presencas']} "
            f"atribuicoes={resumo['atribuicoes']}"
        ),
        usuario_id=usuario_id,
    )

    return resumo
