# -*- coding: utf-8 -*-
"""
app/validacao.py - LIMPEZA E CONFERENCIA DE DADOS DIGITADOS.

Duas tarefas diferentes moram aqui:

1. NORMALIZAR  - arrumar o que a pessoa digitou.
   "(16) 9 9280-5852" e "16992805852" sao o MESMO telefone. Se guardarmos do
   jeito que veio, a busca do painel nao acha e a deteccao de duplicatas
   (secao 5.7) falha. Entao guardamos sempre so os numeros: "16992805852".

2. VALIDAR - recusar o que nao faz sentido.
   Data de nascimento no futuro, CEP com 3 digitos, nome com 1 letra.

REGRA DE OURO (secao 7, item 6): a validacao do navegador e so conveniencia
para quem digita. A validacao que VALE e esta aqui, no servidor. Um robo pode
enviar dados direto, pulando a tela inteira.
"""

# --- IMPORTACOES ----------------------------------------------------------
import re                                  # expressoes regulares: busca de padroes em texto
from wtforms.validators import ValidationError

from app.tempo import hoje


# ===========================================================================
# NORMALIZADORES - arrumam o dado antes de guardar
# ===========================================================================
def so_digitos(texto):
    """
    Devolve apenas os numeros de um texto.
        "(16) 99280-5852" -> "16992805852"
    O \\D na expressao significa "tudo que NAO e digito"; trocamos por nada.
    """
    if not texto:
        return ""
    return re.sub(r"\D", "", str(texto))


def normalizar_telefone(texto):
    """Guarda o telefone so com numeros, sem parenteses, espaco ou hifen."""
    return so_digitos(texto)


def formatar_telefone(digitos):
    """
    Caminho inverso: prepara o telefone para aparecer bonito na tela.
        "16992805852" -> "(16) 99280-5852"
        "1633334444"  -> "(16) 3333-4444"
    """
    d = so_digitos(digitos)
    if len(d) == 11:                                  # celular: 2 + 5 + 4
        return f"({d[0:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:                                  # fixo: 2 + 4 + 4
        return f"({d[0:2]}) {d[2:6]}-{d[6:]}"
    return digitos or ""                              # formato desconhecido: devolve como veio


def normalizar_cep(texto):
    """Guarda o CEP como "14015-000" (o formato que os Correios usam)."""
    d = so_digitos(texto)
    if len(d) == 8:
        return f"{d[0:5]}-{d[5:]}"
    return d or None


def normalizar_nome(texto):
    """
    Tira espacos das pontas e espacos repetidos do meio.
        "  maria   silva  " -> "maria silva"
    O .split() sem argumento quebra em qualquer quantidade de espaco, e o
    " ".join() remonta com um espaco so.
    """
    if not texto:
        return ""
    return " ".join(str(texto).split())


def normalizar_texto(texto, limite=None):
    """Limpa um campo de texto livre e, opcionalmente, corta num tamanho maximo."""
    if texto is None:
        return None
    limpo = " ".join(str(texto).split())
    if not limpo:
        return None                                    # campo vazio vira None, nao ""
    if limite:
        limpo = limpo[:limite]
    return limpo


def normalizar_uf(texto):
    """"sp" -> "SP". Duas letras maiusculas."""
    if not texto:
        return None
    return str(texto).strip().upper()[:2]


# ===========================================================================
# LISTA OFICIAL DE ESTADOS
# ===========================================================================
UFS = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
]


# ===========================================================================
# VALIDADORES DO WTForms
# ===========================================================================
# Cada classe abaixo vira uma regra que o formulario aplica sozinho.
# O WTForms chama o metodo __call__ e espera:
#   - silencio       = passou
#   - ValidationError = recusou, com a mensagem que o usuario vai ler


class TelefoneValido:
    """
    Aceita telefone brasileiro: 10 digitos (fixo) ou 11 (celular).
    Recusa "99999999999" e outros numeros com todos os digitos iguais -
    o disfarce mais comum de quem nao quer dar o telefone de verdade.
    """

    def __init__(self, mensagem=None, obrigatorio=True):
        self.mensagem = mensagem or "Telefone inválido. Digite com DDD, ex: (16) 99280-5852."
        self.obrigatorio = obrigatorio

    def __call__(self, form, campo):
        d = so_digitos(campo.data)

        if not d:                                      # campo vazio
            if self.obrigatorio:
                raise ValidationError("Informe o telefone.")
            return                                     # vazio e permitido aqui: passa

        if len(d) not in (10, 11):
            raise ValidationError(self.mensagem)

        if len(set(d)) == 1:                           # set() remove repetidos; sobrou 1 = todos iguais
            raise ValidationError("Este telefone não parece real.")

        if d[0] == "0":                                # nenhum DDD brasileiro comeca com 0
            raise ValidationError(self.mensagem)

        if len(d) == 11 and d[2] != "9":               # celular com 11 digitos tem 9 na frente
            raise ValidationError("Celular com 11 dígitos deve começar com 9 depois do DDD.")


class CepValido:
    """CEP tem exatamente 8 digitos. Campo opcional: vazio passa."""

    def __call__(self, form, campo):
        if not campo.data:
            return
        d = so_digitos(campo.data)
        if len(d) != 8:
            raise ValidationError("CEP inválido. Deve ter 8 dígitos, ex: 14015-000.")


class DataNascimentoValida:
    """
    Recusa tres absurdos:
      - data no futuro ("nasceu ano que vem")
      - mais de 120 anos ("nasceu em 1850")
      - bebe de dias, digitado por engano no lugar do ano atual
    """

    def __init__(self, idade_maxima=120):
        self.idade_maxima = idade_maxima

    def __call__(self, form, campo):
        if not campo.data:
            return                                     # a obrigatoriedade e checada por outro validador

        referencia = hoje()

        if campo.data > referencia:
            raise ValidationError("A data de nascimento não pode estar no futuro.")

        anos = referencia.year - campo.data.year
        if anos > self.idade_maxima:
            raise ValidationError(f"Data muito antiga. Confira o ano digitado.")


class DataConversaoValida:
    """A conversao nao pode estar no futuro nem ser muito antiga."""

    def __init__(self, dias_maximos=3650):             # 10 anos para tras
        self.dias_maximos = dias_maximos

    def __call__(self, form, campo):
        if not campo.data:
            return

        referencia = hoje()

        if campo.data > referencia:
            raise ValidationError("A data da conversão não pode estar no futuro.")

        if (referencia - campo.data).days > self.dias_maximos:
            raise ValidationError("Data muito antiga. Confira o ano digitado.")


class NomeValido:
    """
    Um nome de gente de verdade: pelo menos 2 caracteres e pelo menos uma letra.
    Isso barra "123", "...", "aa" e outros preenchimentos de pressa.
    """

    def __init__(self, minimo=2, exigir_sobrenome=False):
        self.minimo = minimo
        self.exigir_sobrenome = exigir_sobrenome

    def __call__(self, form, campo):
        nome = normalizar_nome(campo.data)

        if not nome:
            raise ValidationError("Este campo é obrigatório.")

        if len(nome) < self.minimo:
            raise ValidationError(f"Digite pelo menos {self.minimo} caracteres.")

        # \\p{L} nao existe no re padrao do Python, entao listamos as letras
        # acentuadas do portugues na mao.
        if not re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", nome):
            raise ValidationError("Digite um nome válido.")

        if self.exigir_sobrenome and len(nome.split(" ")) < 2:
            raise ValidationError("Digite o nome completo (nome e sobrenome).")
