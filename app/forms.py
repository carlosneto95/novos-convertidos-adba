# -*- coding: utf-8 -*-
"""
app/forms.py - OS FORMULARIOS.

O Flask-WTF faz tres coisas de uma vez:
  1. DESENHA os campos no HTML
  2. VALIDA o que chegou, no SERVIDOR (secao 7, item 6)
  3. PROTEGE contra CSRF, colocando um token secreto em cada formulario

Sobre o CSRF (secao 7, item 4): sem o token, um site malicioso poderia montar
um formulario escondido que envia dados para o nosso sistema usando a sessao da
vitima. Com o token, o Flask recusa qualquer envio que nao tenha vindo de uma
pagina nossa.
"""

# --- IMPORTACOES ----------------------------------------------------------
from flask_wtf import FlaskForm
from wtforms import (
    StringField,        # caixa de texto de uma linha
    TextAreaField,      # caixa de texto de varias linhas
    SelectField,        # lista suspensa
    RadioField,         # botoes de escolha unica
    DateField,          # seletor de data
    BooleanField,       # caixa de marcar
    HiddenField,        # campo invisivel (usado no honeypot)
    DateTimeLocalField, # data E hora juntas, num seletor so
    PasswordField,      # caixa de senha (mostra bolinhas)
)
from wtforms.validators import (
    DataRequired, Optional, Length, AnyOf, EqualTo, ValidationError,
)

from app import opcoes
from app.validacao import (
    TelefoneValido,
    CepValido,
    DataNascimentoValida,
    DataConversaoValida,
    NomeValido,
    UFS,
)
from app.tempo import hoje


# ===========================================================================
# FORMULARIO PUBLICO DE CADASTRO (secao 5.1)
# ===========================================================================
class CadastroPublicoForm(FlaskForm):
    """
    O formulario que qualquer membro da igreja preenche, sem login.

    A ORDEM DOS CAMPOS aqui segue a ordem dos 4 blocos da tela:
      Bloco 1 - Quem esta cadastrando
      Bloco 2 - Dados da alma
      Bloco 3 - A conversao
      Bloco 4 - Questionario
      Rodape  - LGPD
    """

    # =====================================================================
    # ARMADILHA ANTI-ROBO (honeypot) - secao 7, item 7
    # =====================================================================
    # Campo invisivel para gente, visivel para robo. Um robo preenche TUDO que
    # encontra no HTML. Se este campo chegar preenchido, sabemos que nao foi
    # uma pessoa - e descartamos o envio sem avisar o robo que fomos espertos.
    #
    # O nome "website" e proposital: e o tipo de campo que um robo de spam
    # adora preencher.
    website = HiddenField("Deixe este campo em branco")

    # =====================================================================
    # BLOCO 1 - QUEM ESTA CADASTRANDO
    # =====================================================================
    cadastrante_nome = StringField(
        "Seu nome",
        validators=[DataRequired(message="Informe seu nome."), NomeValido(minimo=3)],
        render_kw={"placeholder": "Como você se chama?", "autocomplete": "name"},
    )
    cadastrante_telefone = StringField(
        "Seu telefone",
        validators=[TelefoneValido()],
        render_kw={
            "placeholder": "(16) 99999-9999",
            "inputmode": "tel",       # celular abre o teclado numerico
            "autocomplete": "tel",
        },
    )

    # =====================================================================
    # BLOCO 2 - DADOS DA ALMA
    # =====================================================================
    nome_completo = StringField(
        "Nome completo",
        validators=[
            DataRequired(message="Informe o nome da pessoa."),
            NomeValido(minimo=3, exigir_sobrenome=True),
            Length(max=150),
        ],
        render_kw={"placeholder": "Nome e sobrenome"},
    )
    telefone = StringField(
        "Telefone / WhatsApp",
        validators=[TelefoneValido()],
        render_kw={"placeholder": "(16) 99999-9999", "inputmode": "tel"},
    )
    sexo = RadioField(
        "Sexo",
        choices=opcoes.escolhas(opcoes.SEXOS),
        validators=[DataRequired(message="Selecione o sexo.")],
    )
    data_nascimento = DateField(
        "Data de nascimento",
        validators=[DataRequired(message="Informe a data de nascimento."), DataNascimentoValida()],
    )

    # --- Endereco (preenchido sozinho pela busca de CEP) -----------------
    cep = StringField(
        "CEP",
        validators=[Optional(), CepValido()],
        render_kw={"placeholder": "00000-000", "inputmode": "numeric", "maxlength": "9"},
    )
    logradouro = StringField("Rua / Avenida", validators=[Optional(), Length(max=150)])
    numero = StringField(
        "Número",
        validators=[Optional(), Length(max=20)],
        render_kw={"placeholder": "123"},
    )
    complemento = StringField(
        "Complemento",
        validators=[Optional(), Length(max=100)],
        render_kw={"placeholder": "Apto, bloco, fundos..."},
    )
    bairro = StringField("Bairro", validators=[Optional(), Length(max=100)])
    cidade = StringField("Cidade", validators=[Optional(), Length(max=100)])
    uf = SelectField(
        "UF",
        choices=[("", "--")] + [(u, u) for u in UFS],
        validators=[Optional(), AnyOf([""] + UFS, message="Estado inválido.")],
    )

    # =====================================================================
    # BLOCO 3 - A CONVERSAO
    # =====================================================================
    trabalho = RadioField(
        "Em que trabalho a pessoa aceitou Jesus?",
        choices=opcoes.escolhas(opcoes.TRABALHOS),
        validators=[DataRequired(message="Selecione o trabalho.")],
    )
    trabalho_outro = StringField(
        "Qual?",
        validators=[Optional(), Length(max=120)],
        render_kw={"placeholder": "Descreva o trabalho"},
    )
    data_conversao = DateField(
        "Data da conversão",
        default=hoje,
        validators=[DataRequired(message="Informe a data."), DataConversaoValida()],
    )
    departamento = RadioField(
        "Departamento que vai acolher",
        choices=opcoes.escolhas(opcoes.DEPARTAMENTOS),
        validators=[DataRequired(message="Confirme o departamento.")],
    )

    # =====================================================================
    # BLOCO 4 - QUESTIONARIO
    # =====================================================================
    como_chegou = TextAreaField(
        "Como a pessoa chegou na igreja?",
        validators=[Optional(), Length(max=2000)],
        render_kw={"rows": 3, "placeholder": "Conte brevemente como ela chegou até aqui..."},
    )
    tem_conhecido = RadioField(
        "Já conhece alguém da igreja?",
        choices=[("sim", "Sim"), ("nao", "Não")],
        validators=[Optional()],
    )
    conhecido_nome = StringField(
        "Quem?",
        validators=[Optional(), Length(max=150)],
        render_kw={"placeholder": "Nome de quem ela conhece"},
    )
    ja_frequentou_igreja = RadioField(
        "Já frequentou alguma igreja evangélica?",
        choices=[("sim", "Sim"), ("nao", "Não")],
        validators=[Optional()],
    )
    qual_igreja = StringField(
        "Qual?",
        validators=[Optional(), Length(max=150)],
        render_kw={"placeholder": "Nome da igreja"},
    )

    # =====================================================================
    # RODAPE - LGPD
    # =====================================================================
    consentimento = BooleanField(
        "Autorizo o uso dos meus dados",
        validators=[DataRequired(message="É preciso autorizar o uso dos dados para concluir.")],
    )
    #   BooleanField nasce DESMARCADO. A especificacao exige exatamente isso:
    #   consentimento pre-marcado nao e consentimento.

    # --- So aparecem se a pessoa for menor de 18 -------------------------
    responsavel_legal_nome = StringField(
        "Nome do responsável legal",
        validators=[Optional(), Length(max=150)],
        render_kw={"placeholder": "Pai, mãe ou responsável"},
    )
    responsavel_legal_telefone = StringField(
        "Telefone do responsável legal",
        validators=[Optional(), TelefoneValido(obrigatorio=False)],
        render_kw={"placeholder": "(16) 99999-9999", "inputmode": "tel"},
    )
    consentimento_responsavel = BooleanField(
        "O responsável legal autoriza",
        validators=[Optional()],
    )

    # =====================================================================
    # VALIDACAO CRUZADA - regras que dependem de MAIS DE UM campo
    # =====================================================================
    def validate(self, extra_validators=None):
        """
        Roda depois que cada campo passou na sua propria validacao.

        As regras abaixo nao cabem num campo so: elas comparam campos entre si.
        Ex: "trabalho_outro e obrigatorio SE trabalho for 'outro'".

        Tudo isso acontece no SERVIDOR. A tela esconde e mostra campos por
        conveniencia, mas quem decide se o cadastro entra e este codigo.
        """
        # Primeiro deixa o WTForms validar campo por campo.
        if not super().validate(extra_validators):
            ok_campos = False
        else:
            ok_campos = True

        # --- Regra 1: trabalho "outro" exige a descricao -----------------
        if self.trabalho.data == "outro":
            if not (self.trabalho_outro.data or "").strip():
                self.trabalho_outro.errors.append("Descreva qual foi o trabalho.")
                ok_campos = False

        # --- Regra 2: "conhece alguem = sim" exige o nome ----------------
        if self.tem_conhecido.data == "sim":
            if not (self.conhecido_nome.data or "").strip():
                self.conhecido_nome.errors.append("Informe quem ela conhece.")
                ok_campos = False

        # --- Regra 3: "ja frequentou = sim" exige qual igreja ------------
        if self.ja_frequentou_igreja.data == "sim":
            if not (self.qual_igreja.data or "").strip():
                self.qual_igreja.errors.append("Informe qual igreja.")
                ok_campos = False

        # --- Regra 4: MENOR DE IDADE (secao 5.1) -------------------------
        # A regra mais importante deste formulario. Um menor de 18 nao pode
        # consentir sozinho com o tratamento dos proprios dados (LGPD, art. 14).
        from flask import current_app
        from app.tempo import eh_menor_de_idade

        maioridade = current_app.config.get("IDADE_MAIORIDADE", 18)

        if self.data_nascimento.data and eh_menor_de_idade(
            self.data_nascimento.data, maioridade
        ):
            if not (self.responsavel_legal_nome.data or "").strip():
                self.responsavel_legal_nome.errors.append(
                    "Obrigatório para menores de idade."
                )
                ok_campos = False

            if not (self.responsavel_legal_telefone.data or "").strip():
                self.responsavel_legal_telefone.errors.append(
                    "Obrigatório para menores de idade."
                )
                ok_campos = False

            if not self.consentimento_responsavel.data:
                self.consentimento_responsavel.errors.append(
                    "O responsável legal precisa autorizar."
                )
                ok_campos = False

        return ok_campos

    # =====================================================================
    # ATALHO PARA A TELA
    # =====================================================================
    @property
    def eh_robo(self):
        """True se a armadilha do honeypot foi preenchida."""
        return bool((self.website.data or "").strip())


# ===========================================================================
# FORMULARIO DE LOGIN (secao 5, Etapa 4)
# ===========================================================================
class LoginForm(FlaskForm):
    """
    A porta de entrada do sistema.

    Note que NAO ha validacao de "senha forte" aqui. Motivo: na hora de
    ENTRAR, a senha ou bate com o hash ou nao bate. Exigir formato no login
    so entregaria pistas sobre o formato das senhas validas.
    """

    login = StringField(
        "Login",
        validators=[
            DataRequired(message="Informe seu login."),
            Length(max=60, message="Login muito longo."),
        ],
        render_kw={
            "placeholder": "seu.login",
            "autocomplete": "username",
            "autocapitalize": "none",   # celular nao coloca maiuscula sozinho
            "autocorrect": "off",       # celular nao "corrige" o login
            "spellcheck": "false",
        },
    )

    senha = PasswordField(
        "Senha",
        validators=[
            DataRequired(message="Informe sua senha."),
            Length(max=200, message="Senha muito longa."),
        ],
        render_kw={
            "placeholder": "••••••••",
            "autocomplete": "current-password",
        },
    )

    lembrar = BooleanField("Continuar conectado neste aparelho")
    #   Mesmo marcado, a sessao expira em 8 horas (config.py, secao 7 item 9).
    #   Nao existe "para sempre": um celular esquecido no banco da igreja nao
    #   pode virar acesso permanente aos dados de ninguem.


# ===========================================================================
# FORMULARIO DE TROCA DE SENHA
# ===========================================================================
class TrocarSenhaForm(FlaskForm):
    """
    Usado em dois momentos:
      1. Troca OBRIGATORIA no primeiro login (a senha inicial passou pelas
         maos de outra pessoa, por WhatsApp ou papel - entao ja nasceu
         comprometida).
      2. Troca voluntaria, quando a pessoa quiser.
    """

    senha_atual = PasswordField(
        "Senha atual",
        validators=[DataRequired(message="Informe a senha atual.")],
        render_kw={"placeholder": "A senha que voce usa hoje",
                   "autocomplete": "current-password"},
    )

    senha_nova = PasswordField(
        "Nova senha",
        validators=[
            DataRequired(message="Informe a nova senha."),
            Length(min=8, max=200, message="A nova senha precisa ter pelo menos 8 caracteres."),
        ],
        render_kw={"placeholder": "Pelo menos 8 caracteres",
                   "autocomplete": "new-password"},
    )

    senha_confirmacao = PasswordField(
        "Repita a nova senha",
        validators=[
            DataRequired(message="Repita a nova senha."),
            # EqualTo compara com outro campo do mesmo formulario.
            # Pedir duas vezes evita que a pessoa se tranque para fora do
            # sistema por causa de um erro de digitacao que ela nao viu.
            EqualTo("senha_nova", message="As duas senhas nao sao iguais."),
        ],
        render_kw={"placeholder": "Digite de novo", "autocomplete": "new-password"},
    )

    def validate(self, extra_validators=None):
        """Regras que comparam campos entre si."""
        if not super().validate(extra_validators):
            return False

        # A nova senha precisa ser DIFERENTE da atual. Sem isso, a troca
        # obrigatoria do primeiro login viraria teatro: a pessoa digitaria a
        # mesma senha tres vezes e nada mudaria.
        if self.senha_atual.data == self.senha_nova.data:
            self.senha_nova.errors.append("A nova senha precisa ser diferente da atual.")
            return False

        # Barra as senhas mais obvias do mundo. Nao e uma lista completa - e
        # so o basico para impedir "senha123" e "12345678".
        proibidas = {
            "12345678", "123456789", "1234567890", "senha123", "senha1234",
            "password", "adba1234", "igreja123", "admin123", "qwertyui",
            "11111111", "00000000", "abcd1234",
        }
        if (self.senha_nova.data or "").lower().strip() in proibidas:
            self.senha_nova.errors.append(
                "Esta senha e facil demais de adivinhar. Escolha outra."
            )
            return False

        return True


# ===========================================================================
# ETAPA 6 - AS ACOES DA FICHA LATERAL (secao 5.3)
# ===========================================================================

class ContatoForm(FlaskForm):
    """
    Registrar um contato com a alma.

    E o formulario mais importante do acompanhamento: e ele que move os dois
    relogios do semaforo (secao 4).
      - QUALQUER contato zera o relogio da tentativa
      - so resultado="efetivo" zera o relogio do contato efetivo
    """

    tipo = RadioField(
        "Como foi o contato?",
        choices=opcoes.escolhas(opcoes.TIPOS_CONTATO),
        validators=[DataRequired(message="Selecione o tipo de contato.")],
    )

    data_hora = DateTimeLocalField(
        "Quando aconteceu?",
        format="%Y-%m-%dT%H:%M",     # o formato que o seletor do navegador usa
        validators=[DataRequired(message="Informe quando o contato aconteceu.")],
    )
    #   Quando ACONTECEU, nao quando foi digitado. O responsavel liga de manha
    #   e registra a noite - e a data da ligacao que vale para o semaforo.

    resultado = RadioField(
        "O que aconteceu?",
        choices=opcoes.escolhas(opcoes.RESULTADOS_CONTATO),
        validators=[DataRequired(message="Selecione o resultado.")],
    )

    relato = TextAreaField(
        "O que foi conversado?",
        validators=[
            DataRequired(message="Escreva um relato, mesmo que curto."),
            Length(min=3, max=3000, message="O relato precisa ter pelo menos 3 caracteres."),
        ],
        render_kw={"rows": 3, "placeholder": "Ex: Ela contou que está bem e vai vir no culto de domingo."},
    )
    #   Obrigatorio de proposito. "Registrei contato" sem relato nao diz nada
    #   para quem assumir a alma daqui a seis meses.
    #   ATENCAO (secao 7, item 5): NUNCA exibir este campo com |safe.

    def validate_data_hora(self, campo):
        """A data do contato nao pode estar no futuro."""
        from app.tempo import agora, garantir_utc, FUSO_BRASIL
        from datetime import timedelta

        if not campo.data:
            return

        # O navegador manda a hora local (Brasilia) sem fuso anexado.
        # Anexamos o fuso da igreja antes de comparar, senao a conta erra 3h.
        momento = campo.data.replace(tzinfo=FUSO_BRASIL)

        # 5 minutos de folga: o relogio do computador pode estar adiantado.
        if momento > agora() + timedelta(minutes=5):
            raise ValidationError("O contato não pode estar no futuro.")

        if momento < agora() - timedelta(days=365 * 2):
            raise ValidationError("Data muito antiga. Confira o ano.")


class PresencaForm(FlaskForm):
    """Marcar se a alma esteve num culto."""

    evento_id = SelectField(
        "Em qual culto?",
        validators=[DataRequired(message="Selecione o culto.")],
    )
    #   As opcoes sao preenchidas na rota, com os cultos do periodo - nao aqui,
    #   porque dependem do banco e mudam a cada dia.

    presente = RadioField(
        "Ela esteve presente?",
        choices=[("sim", "Sim, esteve presente"), ("nao", "Não, faltou")],
        validators=[DataRequired(message="Informe se esteve presente.")],
    )
    #   Guardamos a FALTA tambem, nao so a presenca. Faltar tres domingos
    #   seguidos e um sinal pastoral tao importante quanto comparecer.


class StatusForm(FlaskForm):
    """Alterar o status do ciclo de vida da alma (secao 4)."""

    status_ciclo = SelectField(
        "Novo status",
        choices=opcoes.escolhas(opcoes.STATUS_CICLO),
        validators=[DataRequired(message="Selecione o novo status.")],
    )

    justificativa = TextAreaField(
        "Por quê?",
        validators=[Optional(), Length(max=2000)],
        render_kw={"rows": 2, "placeholder": "Ex: Foi batizada e já participa do grupo de jovens."},
    )

    def validate(self, extra_validators=None):
        """Sair de 'em acompanhamento' exige justificativa (secao 3)."""
        if not super().validate(extra_validators):
            return False

        # Encerrar o acompanhamento de alguem e uma decisao pastoral seria.
        # Sem justificativa escrita, ninguem consegue auditar depois por que
        # aquela alma saiu do radar.
        if self.status_ciclo.data in opcoes.STATUS_ENCERRAMENTO:
            if not (self.justificativa.data or "").strip():
                self.justificativa.errors.append(
                    "Explique o motivo. Encerrar o acompanhamento exige justificativa."
                )
                return False

        return True


class TransferirForm(FlaskForm):
    """
    Passar a alma para outro responsavel (so Admin).

    IMPORTANTE (secao 4): a transferencia VOLTA O RELOGIO para 48 horas,
    porque o novo responsavel precisa se apresentar. Mas o historico de
    contatos permanece inteiro e visivel.
    """

    responsavel_id = SelectField(
        "Novo responsável",
        validators=[DataRequired(message="Selecione o novo responsável.")],
    )

    motivo = TextAreaField(
        "Motivo da transferência",
        validators=[
            DataRequired(message="Explique por que está transferindo."),
            Length(min=3, max=1000),
        ],
        render_kw={"rows": 2, "placeholder": "Ex: O responsável atual vai viajar por dois meses."},
    )

    manter_observacao = BooleanField("Repassar a observação sensível ao novo responsável")
    #   NAO vem marcado, de proposito (secao 7, item 11): a observacao
    #   sensivel nao e repassada automaticamente. O Admin decide, caso a caso.


# ===========================================================================
# ETAPA 7 - RESPONSAVEIS E EVENTOS
# ===========================================================================

class UsuarioForm(FlaskForm):
    """
    Criar um usuario do sistema (so Admin) - secao 5.4.

    Note que NAO ha campo de senha. A senha e SORTEADA pelo sistema e
    mostrada uma unica vez na tela. Motivo: senha escolhida por quem cria
    costuma virar "igreja123" para todo mundo. Sorteada, cada um recebe uma
    diferente - e o sistema ainda obriga a troca no primeiro login.
    """

    nome = StringField(
        "Nome completo",
        validators=[
            DataRequired(message="Informe o nome."),
            NomeValido(minimo=3, exigir_sobrenome=True),
            Length(max=120),
        ],
        render_kw={"placeholder": "Nome e sobrenome"},
    )

    login = StringField(
        "Login de acesso",
        validators=[
            DataRequired(message="Informe o login."),
            Length(min=3, max=60, message="O login precisa ter de 3 a 60 caracteres."),
        ],
        render_kw={
            "placeholder": "joao.pereira",
            "autocapitalize": "none",
            "autocorrect": "off",
            "spellcheck": "false",
        },
    )

    telefone = StringField(
        "Telefone",
        validators=[TelefoneValido(obrigatorio=False)],
        render_kw={"placeholder": "(16) 99999-9999", "inputmode": "tel"},
    )

    papel = RadioField(
        "O que esta pessoa poderá fazer?",
        choices=opcoes.escolhas(opcoes.PAPEIS),
        default="responsavel",
        validators=[DataRequired(message="Escolha o papel.")],
    )

    def validate_login(self, campo):
        """
        O login precisa ser simples e unico.

        Aceitamos letras, numeros, ponto, hifen e sublinhado. Espaco e acento
        ficam de fora: sao a maior fonte de "nao consigo entrar" - a pessoa
        digita "joão" onde foi cadastrado "joao" e nunca descobre o motivo.
        """
        import re as _re
        from app.extensions import db
        from app.models import Usuario

        valor = (campo.data or "").strip().lower()

        if not _re.fullmatch(r"[a-z0-9._-]+", valor):
            raise ValidationError(
                "Use apenas letras sem acento, números, ponto, hífen ou sublinhado."
            )

        existente = db.session.execute(
            db.select(Usuario).where(db.func.lower(Usuario.login) == valor)
        ).scalar_one_or_none()

        if existente:
            raise ValidationError("Já existe um usuário com este login.")


class EventoForm(FlaskForm):
    """Cadastrar um evento pontual - so Admin (secao 5.5)."""

    nome = StringField(
        "Nome do evento",
        validators=[
            DataRequired(message="Informe o nome do evento."),
            Length(min=3, max=150),
        ],
        render_kw={"placeholder": "Ex: Vigília de Oração"},
    )

    tipo = SelectField(
        "Tipo",
        choices=opcoes.escolhas(opcoes.TIPOS_EVENTO),
        validators=[DataRequired(message="Escolha o tipo.")],
    )

    data = DateField(
        "Data",
        validators=[DataRequired(message="Informe a data.")],
    )

    def validate_data(self, campo):
        """Recusa datas absurdas, para tras ou para a frente demais."""
        from datetime import timedelta
        from app.tempo import hoje

        if not campo.data:
            return

        if campo.data < hoje() - timedelta(days=365):
            raise ValidationError("Data muito antiga. Confira o ano.")

        if campo.data > hoje() + timedelta(days=730):
            raise ValidationError("Data muito distante. Confira o ano.")
