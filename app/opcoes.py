# -*- coding: utf-8 -*-
"""
app/opcoes.py - AS LISTAS FIXAS DO SISTEMA.

Cada campo do tipo "Enum" da especificacao vira um dicionario aqui:

    "valor_guardado_no_banco": "Texto bonito mostrado na tela"

Por que guardar o valor "feio" (culto_dominical) e nao o bonito
("Culto Dominical")?
1. O banco nunca muda de ideia. Se amanha voce quiser exibir
   "Culto de Domingo", muda so o texto da direita e NENHUM dado precisa
   ser reescrito.
2. Sem acento e sem espaco: nunca da problema de codificacao.

Estes dicionarios sao usados em TRES lugares:
  - models.py  -> monta a trava do banco (so aceita estes valores)
  - forms.py   -> monta as listas suspensas do formulario (Etapa 3)
  - templates  -> traduz o valor guardado para o texto na tela
"""

# ===========================================================================
# USUARIO
# ===========================================================================
PAPEIS = {
    "admin": "Administrador",
    "responsavel": "Responsável",
}

# ===========================================================================
# NOVO CONVERTIDO - dados pessoais
# ===========================================================================
SEXOS = {
    "M": "Masculino",
    "F": "Feminino",
}

# ===========================================================================
# NOVO CONVERTIDO - a conversao
# ===========================================================================
# Em que trabalho da igreja a pessoa aceitou Jesus.
TRABALHOS = {
    "culto_dominical": "Culto Dominical",
    "culto_ensino": "Culto de Ensino",
    "culto_ceia": "Culto da Ceia",
    "encontro_tribo": "Encontro de Tribo",
    "evangelismo_rua": "Evangelismo de Rua",
    "trabalho_preciosas": "Trabalho das Preciosas",
    "outro": "Outro",
}

# Departamento que vai acolher a pessoa.
DEPARTAMENTOS = {
    "geracao_life": "Geração Life",
    "preciosas": "Preciosas",
    "irmaos": "Irmãos",
}

# ===========================================================================
# NOVO CONVERTIDO - ciclo de vida (secao 4 da especificacao)
# ===========================================================================
STATUS_CICLO = {
    "aguardando_responsavel": "Aguardando responsável",
    "em_acompanhamento": "Em acompanhamento",
    "integrado": "Integrado",
    "frequenta_outra_igreja": "Frequenta outra igreja",
    "nao_deseja_contato": "Não deseja contato",
    "perdido_contato": "Perdeu contato",
    "mudou_cidade": "Mudou de cidade",
}

# O UNICO status que entra no semaforo colorido e aparece no painel principal.
# Todos os outros saem da contagem (regra das "Excecoes", secao 4).
STATUS_ATIVO = "em_acompanhamento"

# Status inicial de toda alma recem-cadastrada pelo formulario publico.
STATUS_INICIAL = "aguardando_responsavel"

# Sair de "em_acompanhamento" para qualquer um destes exige justificativa escrita.
STATUS_ENCERRAMENTO = [
    "integrado",
    "frequenta_outra_igreja",
    "nao_deseja_contato",
    "perdido_contato",
    "mudou_cidade",
]

# ===========================================================================
# CONTATO
# ===========================================================================
TIPOS_CONTATO = {
    "telefone": "Telefone",
    "whatsapp": "WhatsApp",
    "presencial": "Presencial",
}

# Icone de cada tipo, usado na timeline do drawer lateral (Etapa 6).
ICONES_CONTATO = {
    "telefone": "📞",
    "whatsapp": "💬",
    "presencial": "🤝",
}

RESULTADOS_CONTATO = {
    "efetivo": "Efetivo — falei com a pessoa",
    "sem_resposta": "Sem resposta",
    "recusou_contato": "Recusou o contato",
}

# O unico resultado que zera o relogio "dias_desde_contato_efetivo" (secao 4).
RESULTADO_EFETIVO = "efetivo"

# ===========================================================================
# EVENTO
# ===========================================================================
TIPOS_EVENTO = {
    "culto_dominical": "Culto Dominical",
    "culto_ensino": "Culto de Ensino",
    "culto_ceia": "Culto da Ceia",
    "encontro_tribo": "Encontro de Tribo",
    "trabalho_preciosas": "Trabalho das Preciosas",
    "outro": "Outro",
}

# ===========================================================================
# AJUDANTES
# ===========================================================================


def valores(dicionario):
    """
    Devolve so as chaves (os valores guardados no banco), em formato de lista.
    Usado no models.py para montar a trava do banco:
        db.Enum(*valores(SEXOS))  ->  db.Enum("M", "F")
    """
    return list(dicionario.keys())


def escolhas(dicionario):
    """
    Devolve pares (valor, texto) para montar listas suspensas nos formularios.
        escolhas(SEXOS)  ->  [("M", "Masculino"), ("F", "Feminino")]
    """
    return list(dicionario.items())


def rotulo(dicionario, chave, padrao="-"):
    """
    Traduz o valor guardado no banco para o texto de tela.
        rotulo(TRABALHOS, "culto_ceia")  ->  "Culto da Ceia"
    Se a chave nao existir (dado antigo, por exemplo), devolve o padrao em vez
    de quebrar a pagina.
    """
    return dicionario.get(chave, padrao)


def sugerir_departamento(sexo, idade):
    """
    Sugere o departamento a partir de sexo e idade (regra da secao 5.1).

        menor de 25 anos  -> Geracao Life
        mulher com 25+    -> Preciosas
        homem com 25+     -> Irmaos

    ATENCAO: isto e apenas uma SUGESTAO. A especificacao exige que a escolha
    seja SEMPRE confirmada manualmente por quem preenche o formulario.
    """
    if idade is None:                       # sem data de nascimento nao da para sugerir
        return None
    if idade < 25:                          # criancas, adolescentes e jovens
        return "geracao_life"
    if sexo == "F":                         # mulheres de 25 anos para cima
        return "preciosas"
    if sexo == "M":                         # homens de 25 anos para cima
        return "irmaos"
    return None                             # sexo nao informado: nao sugere nada
