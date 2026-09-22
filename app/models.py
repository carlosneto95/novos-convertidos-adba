# -*- coding: utf-8 -*-
"""
app/models.py - AS 7 TABELAS DO BANCO DE DADOS.

Cada classe aqui vira uma tabela de verdade no arquivo instance/adba.db.
Cada atributo da classe vira uma coluna dessa tabela.

    class Usuario(db.Model):          ->  tabela "usuario"
        nome = db.Column(db.String)   ->  coluna "nome", do tipo texto

Isso se chama ORM (Mapeamento Objeto-Relacional): eu escrevo Python, o
SQLAlchemy traduz para SQL. A vantagem de seguranca e enorme - o SQLAlchemy
monta as consultas com "parametros", o que torna injecao de SQL praticamente
impossivel.

ORDEM DAS TABELAS neste arquivo:
    1. Usuario          - quem usa o sistema
    2. NovoConvertido   - as almas (a tabela central)
    3. Atribuicao       - historico de responsaveis
    4. Contato          - cada ligacao, zap ou conversa
    5. Evento           - cultos e encontros
    6. Presenca         - quem foi em qual culto
    7. LogAuditoria     - a caixa-preta do sistema
"""

# --- IMPORTACOES ----------------------------------------------------------
import uuid                                    # gerador de identificadores unicos
from flask_login import UserMixin              # da ao Usuario os metodos que o login espera
from sqlalchemy import event, func, UniqueConstraint, Index

from app.extensions import db, bcrypt          # o banco e o gerador de hash
from app import opcoes                         # as listas fixas (Enum)
from app.tempo import agora, hoje, calcular_idade


# ===========================================================================
# AJUDANTE: GERADOR DE ID
# ===========================================================================
def novo_uuid():
    """
    Gera um identificador como "3f2a91c4-8d7e-4b1a-9c33-5e0f7a2b6d18".

    POR QUE UUID E NAO 1, 2, 3? (secao 7, item 2 - IDOR)
    Se a URL fosse /alma/7, qualquer responsavel trocaria para /alma/8 e veria
    a ficha de outra pessoa. Com UUID isso e impossivel de adivinhar: sao
    2 elevado a 122 combinacoes.

    IMPORTANTE: o UUID sozinho NAO e a protecao. Ele so dificulta o chute.
    A protecao de verdade e a checagem no backend, que faremos na Etapa 4:
    "esta alma pertence ao responsavel logado? Se nao, 403".
    """
    return str(uuid.uuid4())


# ===========================================================================
# 1. USUARIO - quem faz login no sistema
# ===========================================================================
class Usuario(UserMixin, db.Model):
    """
    Admin ou Responsavel. O publico que preenche o formulario NAO tem usuario.

    UserMixin (vem antes de db.Model de proposito) entrega de graca os metodos
    que o Flask-Login exige: is_authenticated, is_active, get_id() etc.
    """

    __tablename__ = "usuario"      # nome da tabela no banco

    # --- Identificacao ---------------------------------------------------
    id = db.Column(db.String(36), primary_key=True, default=novo_uuid)
    #   String(36) porque o UUID em texto tem 36 caracteres.
    #   default=novo_uuid (sem parenteses!) -> o SQLAlchemy chama a funcao a
    #   cada linha nova. Com parenteses, todos os usuarios teriam o MESMO id.

    nome = db.Column(db.String(120), nullable=False)
    #   nullable=False significa "obrigatorio": o banco recusa linha sem nome.

    login = db.Column(db.String(60), nullable=False, unique=True, index=True)
    #   unique=True -> o banco impede dois usuarios com o mesmo login.
    #   index=True  -> o banco monta um atalho de busca; a tela de login usa isso.

    telefone = db.Column(db.String(20))

    # --- Senha -----------------------------------------------------------
    senha_hash = db.Column(db.String(255), nullable=False)
    #   Guardamos o HASH, nunca a senha (secao 7, item 1).
    #   O hash do bcrypt tem 60 caracteres; deixamos 255 por folga.

    deve_trocar_senha = db.Column(db.Boolean, nullable=False, default=True)
    #   True -> no proximo login o sistema obriga a criar uma senha nova.
    #   Comeca True para todo usuario criado pelo Admin, porque a senha inicial
    #   passa pelas maos de outra pessoa (por WhatsApp, por exemplo).

    # --- Permissao -------------------------------------------------------
    papel = db.Column(
        db.Enum(
            *opcoes.valores(opcoes.PAPEIS),        # desempacota: "admin", "responsavel"
            name="papel_usuario",                  # nome da trava no banco
            native_enum=False,                     # SQLite nao tem Enum de verdade;
            validate_strings=True,                 # vira texto + regra de validacao
        ),
        nullable=False,
        default="responsavel",
    )
    #   O papel e lido do BANCO a cada requisicao, nunca do cookie.
    #   Isso impede que alguem edite o cookie e se promova a admin.

    ativo = db.Column(db.Boolean, nullable=False, default=True)
    #   Usuario nunca e apagado, so desativado. Assim o historico de contatos
    #   dele continua fazendo sentido.

    criado_em = db.Column(db.DateTime(timezone=True), nullable=False, default=agora)

    # --- Ligacoes com outras tabelas -------------------------------------
    almas = db.relationship(
        "NovoConvertido",
        back_populates="responsavel_atual",
        foreign_keys="NovoConvertido.responsavel_atual_id",
    )
    #   usuario.almas -> lista das almas sob responsabilidade dele AGORA.
    #   foreign_keys e obrigatorio aqui porque ha mais de um caminho possivel
    #   entre as tabelas; sem isso o SQLAlchemy nao sabe qual seguir.

    contatos = db.relationship(
        "Contato",
        back_populates="responsavel",
        foreign_keys="Contato.responsavel_id",
    )

    # --- Metodos de senha -------------------------------------------------
    def definir_senha(self, senha_em_texto):
        """
        Transforma a senha digitada em hash e guarda.

        O bcrypt faz isso de proposito devagar (uns 0,3 segundo). Parece ruim,
        mas e a defesa: um invasor que roube o banco precisaria de 0,3 segundo
        POR TENTATIVA por senha. Testar uma lista de milhoes de senhas passa a
        levar anos em vez de segundos.

        O bcrypt tambem embaralha um "sal" aleatorio em cada hash. Por isso
        duas pessoas com a senha "senha123" tem hashes COMPLETAMENTE diferentes.
        """
        self.senha_hash = bcrypt.generate_password_hash(senha_em_texto).decode("utf-8")

    def conferir_senha(self, senha_em_texto):
        """
        Confere se a senha digitada bate com o hash guardado. True ou False.

        Nao existe caminho de volta: o sistema nao "descriptografa" o hash.
        Ele refaz a conta com a senha digitada e compara os resultados.
        """
        if not self.senha_hash:                    # usuario sem senha definida
            return False
        return bcrypt.check_password_hash(self.senha_hash, senha_em_texto)

    # --- Atalhos de leitura ----------------------------------------------
    @property
    def eh_admin(self):
        """Atalho para usar nos templates: {% if current_user.eh_admin %}"""
        return self.papel == "admin"

    @property
    def papel_rotulo(self):
        """"admin" -> "Administrador" (texto para a tela)."""
        return opcoes.rotulo(opcoes.PAPEIS, self.papel)

    @property
    def primeiro_nome(self):
        """"Joao Pereira da Silva" -> "Joao". Usado no cabecalho e nos cards."""
        return (self.nome or "").split(" ")[0]

    def __repr__(self):
        """Como o objeto aparece no terminal quando voce o imprime. So para depurar."""
        return f"<Usuario {self.login} ({self.papel})>"


# ===========================================================================
# 2. NOVO CONVERTIDO - a alma. A tabela central do sistema.
# ===========================================================================
class NovoConvertido(db.Model):

    __tablename__ = "novo_convertido"

    # --- Identificacao ---------------------------------------------------
    id = db.Column(db.String(36), primary_key=True, default=novo_uuid)
    #   Este e o id usado em TODAS as URLs (secao 7, item 2).

    codigo = db.Column(db.Integer, unique=True, index=True)
    #   Numero sequencial APENAS para exibicao: #001, #002, #003.
    #   Facil de falar por telefone ("a alma numero doze"). NUNCA vai na URL.
    #   E preenchido sozinho - veja a funcao gerar_codigo no fim do arquivo.

    # --- Dados pessoais --------------------------------------------------
    nome_completo = db.Column(db.String(150), nullable=False, index=True)
    telefone = db.Column(db.String(20), nullable=False, index=True)
    #   index no telefone serve para a busca do painel E para achar duplicatas
    #   na tela de mesclagem (secao 5.7).

    sexo = db.Column(
        db.Enum(*opcoes.valores(opcoes.SEXOS), name="sexo", native_enum=False, validate_strings=True)
    )
    data_nascimento = db.Column(db.Date, nullable=False)
    #   Date = so a data, sem hora. Obrigatoria porque dela sai a idade, e da
    #   idade sai a regra do menor de 18 (secao 5.1).

    # --- Endereco (preenchido pela busca de CEP - ViaCEP) ----------------
    cep = db.Column(db.String(9))              # 14015-000 (8 digitos + hifen)
    logradouro = db.Column(db.String(150))     # Rua, Avenida...
    numero = db.Column(db.String(20))          # texto, nao numero: existe "123-A" e "s/n"
    complemento = db.Column(db.String(100))    # Apto 42, Fundos...
    bairro = db.Column(db.String(100))
    cidade = db.Column(db.String(100))
    uf = db.Column(db.String(2))               # SP, MG, RJ...

    # --- A conversao ------------------------------------------------------
    trabalho = db.Column(
        db.Enum(
            *opcoes.valores(opcoes.TRABALHOS),
            name="trabalho_conversao",
            native_enum=False,
            validate_strings=True,
        ),
        nullable=False,
    )
    trabalho_outro = db.Column(db.String(120))
    #   So preenchido quando trabalho == "outro". A obrigatoriedade e checada
    #   no formulario, no SERVIDOR (Etapa 3).

    data_conversao = db.Column(db.Date, nullable=False, default=hoje)

    departamento = db.Column(
        db.Enum(
            *opcoes.valores(opcoes.DEPARTAMENTOS),
            name="departamento",
            native_enum=False,
            validate_strings=True,
        ),
        nullable=False,
        index=True,
    )

    # --- Questionario -----------------------------------------------------
    como_chegou = db.Column(db.Text)
    #   Text (nao String) porque nao tem limite de tamanho: e resposta livre.
    #   ATENCAO (secao 7, item 5): este campo NUNCA pode ser exibido com |safe.

    tem_conhecido = db.Column(db.Boolean)
    conhecido_nome = db.Column(db.String(150))
    ja_frequentou_igreja = db.Column(db.Boolean)
    qual_igreja = db.Column(db.String(150))

    # --- Quem cadastrou ---------------------------------------------------
    cadastrante_nome = db.Column(db.String(150), nullable=False)
    cadastrante_telefone = db.Column(db.String(20), nullable=False)
    #   Guardar quem cadastrou permite voltar na fonte se o telefone da alma
    #   estiver errado - e desestimula cadastro de brincadeira.

    # --- LGPD (secao 5.1) -------------------------------------------------
    consentimento_em = db.Column(db.DateTime(timezone=True), nullable=False, default=agora)
    consentimento_ip = db.Column(db.String(45))
    #   45 caracteres porque um endereco IPv6 pode ser longo.
    #   Data + IP sao a prova de que o consentimento foi dado. Se a igreja for
    #   questionada, e isto que responde "quando e de onde a pessoa autorizou".

    responsavel_legal_nome = db.Column(db.String(150))
    responsavel_legal_telefone = db.Column(db.String(20))
    #   Obrigatorios apenas para menores de 18 - validado no servidor (Etapa 3).

    # --- Gestao e ciclo de vida (secao 4) --------------------------------
    status_ciclo = db.Column(
        db.Enum(
            *opcoes.valores(opcoes.STATUS_CICLO),
            name="status_ciclo",
            native_enum=False,
            validate_strings=True,
        ),
        nullable=False,
        default=opcoes.STATUS_INICIAL,
        index=True,
    )
    status_justificativa = db.Column(db.Text)
    #   Obrigatoria ao SAIR de "em_acompanhamento". Evita que uma alma seja
    #   marcada como "perdido contato" sem ninguem explicar o porque.

    status_alterado_em = db.Column(db.DateTime(timezone=True))

    responsavel_atual_id = db.Column(
        db.String(36), db.ForeignKey("usuario.id"), nullable=True, index=True
    )
    #   ForeignKey = "este campo aponta para a coluna id da tabela usuario".
    #   O banco passa a recusar um id de usuario que nao existe.
    #   nullable=True porque a alma nasce SEM responsavel (status roxo).

    designado_em = db.Column(db.DateTime(timezone=True))
    #   Marco zero do relogio de 48h do primeiro contato. Na TRANSFERENCIA
    #   este campo e atualizado - e por isso que o relogio volta a 48h (secao 4).

    mesclado_em_id = db.Column(
        db.String(36), db.ForeignKey("novo_convertido.id"), nullable=True
    )
    #   Aponta para a propria tabela. Se preenchido, esta linha e uma DUPLICATA
    #   e sai do painel - mas NUNCA e apagada do banco (secao 5.7).

    observacao_sensivel = db.Column(db.Text)
    #   Campo delicado: situacao familiar, vicio, saude mental.
    #   Visivel so ao Admin e ao responsavel ATUAL, e toda leitura vira registro
    #   de auditoria (secao 7, item 11). Nunca exibir com |safe.

    criado_em = db.Column(db.DateTime(timezone=True), nullable=False, default=agora, index=True)

    # --- Ligacoes com outras tabelas -------------------------------------
    responsavel_atual = db.relationship(
        "Usuario", back_populates="almas", foreign_keys=[responsavel_atual_id]
    )

    contatos = db.relationship(
        "Contato",
        back_populates="convertido",
        order_by="Contato.data_hora.desc()",      # mais recente primeiro (secao 5.3)
        cascade="all, delete-orphan",
    )

    presencas = db.relationship(
        "Presenca", back_populates="convertido", cascade="all, delete-orphan"
    )

    atribuicoes = db.relationship(
        "Atribuicao",
        back_populates="convertido",
        order_by="Atribuicao.inicio.desc()",
        foreign_keys="Atribuicao.convertido_id",
    )
    #   SEM cascade de proposito: o historico de responsaveis nunca some.

    duplicatas = db.relationship(
        "NovoConvertido", backref=db.backref("registro_principal", remote_side=[id])
    )
    #   Liga a alma principal as duplicatas que foram mescladas nela.

    # --- Atalhos de leitura ----------------------------------------------
    @property
    def codigo_formatado(self):
        """12 -> "#012". O formato que aparece nos cards e no WhatsApp."""
        if self.codigo is None:
            return "#---"
        return f"#{self.codigo:03d}"      # :03d = completa com zeros ate 3 digitos

    @property
    def idade(self):
        """Idade em anos completos, calculada na hora (nunca guardada no banco)."""
        return calcular_idade(self.data_nascimento)
        #   Guardar a idade seria um erro classico: ela ficaria errada no dia
        #   seguinte ao aniversario. Data de nascimento nao muda; idade muda.

    @property
    def inicial(self):
        """Primeira letra do nome, para o circulo colorido do card (secao 5.2)."""
        return (self.nome_completo or "?").strip()[:1].upper()

    @property
    def primeiro_nome(self):
        return (self.nome_completo or "").split(" ")[0]

    @property
    def trabalho_rotulo(self):
        """Traduz para a tela. Se for "outro", mostra o texto que a pessoa escreveu."""
        if self.trabalho == "outro" and self.trabalho_outro:
            return self.trabalho_outro
        return opcoes.rotulo(opcoes.TRABALHOS, self.trabalho)

    @property
    def departamento_rotulo(self):
        return opcoes.rotulo(opcoes.DEPARTAMENTOS, self.departamento)

    @property
    def status_rotulo(self):
        return opcoes.rotulo(opcoes.STATUS_CICLO, self.status_ciclo)

    @property
    def esta_em_acompanhamento(self):
        """True se a alma entra no semaforo colorido do painel (secao 4)."""
        return self.status_ciclo == opcoes.STATUS_ATIVO and self.mesclado_em_id is None

    @property
    def eh_duplicata(self):
        """True se esta linha foi mesclada em outra e deve sumir do painel."""
        return self.mesclado_em_id is not None

    @property
    def endereco_resumido(self):
        """Monta "Rua X, 123 - Centro, Ribeirao Preto/SP" pulando o que faltar."""
        partes = []
        if self.logradouro:
            rua = self.logradouro
            if self.numero:
                rua += f", {self.numero}"
            partes.append(rua)
        if self.bairro:
            partes.append(self.bairro)
        if self.cidade:
            cid = self.cidade
            if self.uf:
                cid += f"/{self.uf}"
            partes.append(cid)
        return " - ".join(partes) if partes else "Endereco nao informado"

    def __repr__(self):
        return f"<NovoConvertido {self.codigo_formatado} {self.nome_completo}>"


# ===========================================================================
# 3. ATRIBUICAO - o historico de quem cuidou de quem
# ===========================================================================
class Atribuicao(db.Model):
    """
    Uma linha por periodo de responsabilidade. NUNCA se apaga uma linha daqui.

    Exemplo real:
        Maria foi designada ao Joao em 10/09  -> inicio=10/09, fim=None
        Em 25/09 transferiram para a Ana      -> a linha do Joao ganha fim=25/09
                                                 e nasce uma linha nova da Ana
    Assim o pastor sempre consegue responder "quem cuidava dela em setembro?".
    """

    __tablename__ = "atribuicao"

    id = db.Column(db.String(36), primary_key=True, default=novo_uuid)

    convertido_id = db.Column(
        db.String(36), db.ForeignKey("novo_convertido.id"), nullable=False, index=True
    )
    responsavel_id = db.Column(
        db.String(36), db.ForeignKey("usuario.id"), nullable=False, index=True
    )

    inicio = db.Column(db.DateTime(timezone=True), nullable=False, default=agora)
    fim = db.Column(db.DateTime(timezone=True), nullable=True)
    #   fim vazio (None) = esta e a atribuicao ATUAL.

    motivo = db.Column(db.Text)
    #   Por que houve a transferencia. Ex: "responsavel viajou por 2 meses".

    atribuido_por_id = db.Column(db.String(36), db.ForeignKey("usuario.id"), nullable=True)
    #   Qual Admin fez a designacao. Complementa o log de auditoria.

    # --- Ligacoes ---------------------------------------------------------
    convertido = db.relationship(
        "NovoConvertido", back_populates="atribuicoes", foreign_keys=[convertido_id]
    )
    responsavel = db.relationship("Usuario", foreign_keys=[responsavel_id])
    atribuido_por = db.relationship("Usuario", foreign_keys=[atribuido_por_id])
    #   Tres relacionamentos, dois deles apontando para "usuario". Por isso
    #   cada um precisa dizer explicitamente qual coluna usar (foreign_keys).

    @property
    def esta_ativa(self):
        return self.fim is None

    def __repr__(self):
        return f"<Atribuicao {self.convertido_id[:8]} -> {self.responsavel_id[:8]}>"


# ===========================================================================
# 4. CONTATO - cada tentativa de falar com a alma
# ===========================================================================
class Contato(db.Model):
    """
    A tabela que move os dois relogios do semaforo (secao 4):
      - QUALQUER contato zera o relogio "dias_desde_ultima_tentativa"
      - so resultado="efetivo" zera o relogio "dias_desde_contato_efetivo"
    """

    __tablename__ = "contato"

    id = db.Column(db.String(36), primary_key=True, default=novo_uuid)

    convertido_id = db.Column(
        db.String(36), db.ForeignKey("novo_convertido.id"), nullable=False, index=True
    )
    responsavel_id = db.Column(
        db.String(36), db.ForeignKey("usuario.id"), nullable=False, index=True
    )

    tipo = db.Column(
        db.Enum(
            *opcoes.valores(opcoes.TIPOS_CONTATO),
            name="tipo_contato",
            native_enum=False,
            validate_strings=True,
        ),
        nullable=False,
    )

    data_hora = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    #   Quando o contato ACONTECEU (pode ser diferente de quando foi registrado:
    #   o responsavel liga de manha e registra a noite).

    resultado = db.Column(
        db.Enum(
            *opcoes.valores(opcoes.RESULTADOS_CONTATO),
            name="resultado_contato",
            native_enum=False,
            validate_strings=True,
        ),
        nullable=False,
    )

    relato = db.Column(db.Text, nullable=False)
    #   O que foi conversado. Obrigatorio - sem relato, "registrei contato"
    #   nao significa nada para quem assumir a alma depois.
    #   ATENCAO (secao 7, item 5): NUNCA exibir com |safe.

    criado_em = db.Column(db.DateTime(timezone=True), nullable=False, default=agora)
    #   Quando foi REGISTRADO no sistema. Junto com data_hora, revela se alguem
    #   esta registrando um monte de contato atrasado de uma vez so.

    # --- Ligacoes ---------------------------------------------------------
    convertido = db.relationship("NovoConvertido", back_populates="contatos")
    responsavel = db.relationship(
        "Usuario", back_populates="contatos", foreign_keys=[responsavel_id]
    )

    # --- Atalhos ----------------------------------------------------------
    @property
    def foi_efetivo(self):
        return self.resultado == opcoes.RESULTADO_EFETIVO

    @property
    def tipo_rotulo(self):
        return opcoes.rotulo(opcoes.TIPOS_CONTATO, self.tipo)

    @property
    def tipo_icone(self):
        return opcoes.ICONES_CONTATO.get(self.tipo, "•")

    @property
    def resultado_rotulo(self):
        return opcoes.rotulo(opcoes.RESULTADOS_CONTATO, self.resultado)

    def __repr__(self):
        return f"<Contato {self.tipo}/{self.resultado} em {self.data_hora}>"


# ===========================================================================
# 5. EVENTO - cultos, encontros e trabalhos
# ===========================================================================
class Evento(db.Model):
    """
    Os cultos de domingo e terca nascem sozinhos pelo comando "flask seed-eventos".
    Eventos pontuais (uma vigilia, um congresso) so o Admin cadastra.
    """

    __tablename__ = "evento"

    id = db.Column(db.String(36), primary_key=True, default=novo_uuid)

    nome = db.Column(db.String(150), nullable=False)

    tipo = db.Column(
        db.Enum(
            *opcoes.valores(opcoes.TIPOS_EVENTO),
            name="tipo_evento",
            native_enum=False,
            validate_strings=True,
        ),
        nullable=False,
    )

    data = db.Column(db.Date, nullable=False, index=True)

    recorrente = db.Column(db.Boolean, nullable=False, default=False)
    #   True = nasceu do seed automatico (todo domingo / toda terca).
    #   Serve para o seed saber o que ele mesmo criou e nao duplicar.

    criado_por_id = db.Column(db.String(36), db.ForeignKey("usuario.id"), nullable=True)
    #   Vazio quando foi o seed automatico que criou.

    ativo = db.Column(db.Boolean, nullable=False, default=True)
    #   Culto cancelado vira ativo=False em vez de ser apagado - as presencas
    #   ja registradas continuam existindo.

    criado_em = db.Column(db.DateTime(timezone=True), nullable=False, default=agora)

    # --- Ligacoes ---------------------------------------------------------
    criado_por = db.relationship("Usuario", foreign_keys=[criado_por_id])
    presencas = db.relationship(
        "Presenca", back_populates="evento", cascade="all, delete-orphan"
    )

    # --- Travas -----------------------------------------------------------
    __table_args__ = (
        UniqueConstraint("tipo", "data", name="evento_unico_por_tipo_e_data"),
        #   Impede dois "Culto Dominical" no mesmo domingo. E esta trava que
        #   deixa o comando "flask seed-eventos" ser rodado quantas vezes
        #   quiser sem encher o banco de repetidos.
    )

    @property
    def tipo_rotulo(self):
        return opcoes.rotulo(opcoes.TIPOS_EVENTO, self.tipo)

    def __repr__(self):
        return f"<Evento {self.nome} {self.data}>"


# ===========================================================================
# 6. PRESENCA - quem esteve em qual culto
# ===========================================================================
class Presenca(db.Model):
    """
    Uma linha por par (alma, evento).

    Guardamos tambem a AUSENCIA (presente=False), e nao so a presenca. Faltou
    tres domingos seguidos e um sinal pastoral tao importante quanto ter ido.
    """

    __tablename__ = "presenca"

    id = db.Column(db.String(36), primary_key=True, default=novo_uuid)

    convertido_id = db.Column(
        db.String(36), db.ForeignKey("novo_convertido.id"), nullable=False, index=True
    )
    evento_id = db.Column(
        db.String(36), db.ForeignKey("evento.id"), nullable=False, index=True
    )

    presente = db.Column(db.Boolean, nullable=False, default=False)

    registrado_por_id = db.Column(db.String(36), db.ForeignKey("usuario.id"), nullable=False)
    registrado_em = db.Column(db.DateTime(timezone=True), nullable=False, default=agora)

    # --- Ligacoes ---------------------------------------------------------
    convertido = db.relationship("NovoConvertido", back_populates="presencas")
    evento = db.relationship("Evento", back_populates="presencas")
    registrado_por = db.relationship("Usuario", foreign_keys=[registrado_por_id])

    # --- Travas -----------------------------------------------------------
    __table_args__ = (
        UniqueConstraint("convertido_id", "evento_id", name="presenca_unica_por_evento"),
        #   Exigido pela especificacao: UNIQUE(convertido_id, evento_id).
        #   Impede marcar a mesma pessoa duas vezes no mesmo culto - o que
        #   inflaria o relatorio de retencao (secao 5.6).
    )

    def __repr__(self):
        marca = "presente" if self.presente else "ausente"
        return f"<Presenca {self.convertido_id[:8]} {marca}>"


# ===========================================================================
# 7. LOG DE AUDITORIA - a caixa-preta do sistema
# ===========================================================================
class LogAuditoria(db.Model):
    """
    Tabela SO DE ESCRITA (secao 7, item 13): o sistema grava, ninguem edita e
    ninguem apaga. Nao existe rota de alteracao nem de exclusao para ela.

    O que e obrigatorio registrar (secao 3):
      login e logout - designacao - transferencia - mudanca de status -
      mesclagem - exportacao Excel - LEITURA de observacao sensivel -
      criacao e desativacao de usuario.

    Por que registrar ate a LEITURA da observacao sensivel? Porque esse campo
    guarda informacao intima de alguem. Se um dia vazar, a igreja precisa saber
    quem abriu, quando e de qual endereco.
    """

    __tablename__ = "log_auditoria"

    id = db.Column(db.String(36), primary_key=True, default=novo_uuid)

    usuario_id = db.Column(db.String(36), db.ForeignKey("usuario.id"), nullable=True, index=True)
    #   nullable=True porque nem toda acao tem dono: um cadastro pelo formulario
    #   publico ou uma tentativa de login que falhou nao tem usuario logado.

    acao = db.Column(db.String(60), nullable=False, index=True)
    #   Ex: "login", "designar", "transferir", "ler_observacao_sensivel".

    entidade = db.Column(db.String(60))          # qual tabela foi afetada
    entidade_id = db.Column(db.String(36))       # qual linha daquela tabela

    detalhe = db.Column(db.Text)
    #   Texto livre com o antes/depois. Ex: "status: em_acompanhamento -> integrado".

    ip = db.Column(db.String(45))
    criado_em = db.Column(db.DateTime(timezone=True), nullable=False, default=agora, index=True)

    usuario = db.relationship("Usuario", foreign_keys=[usuario_id])

    def __repr__(self):
        return f"<Log {self.acao} {self.criado_em}>"


# ===========================================================================
# 8. CONTADOR - a "maquininha de senha" do codigo sequencial
# ===========================================================================
class Contador(db.Model):
    """
    Tabela de apoio com UMA linha so, que guarda o ultimo numero entregue.

    POR QUE ISSO EXISTE?
    O codigo de exibicao (#001, #002) precisa ser sequencial, mas o
    autoincremento do SQLite so funciona na chave primaria - e a nossa chave
    primaria e o UUID.

    A PRIMEIRA TENTATIVA (ERRADA) foi perguntar "qual o maior codigo hoje?" e
    somar 1. Isso quebra: se duas almas forem gravadas na mesma operacao, as
    duas perguntam ANTES de qualquer gravacao, as duas recebem a mesma resposta
    e as duas viram #001 - o banco recusa a segunda com erro.

    A SOLUCAO CORRETA e esta tabela funcionando como a maquininha de senha da
    padaria: cada um PUXA um numero, e a maquina ja avanca sozinha. Como o
    UPDATE acontece dentro da transacao do banco, dois pedidos simultaneos nunca
    recebem o mesmo numero.
    """

    __tablename__ = "contador"

    nome = db.Column(db.String(60), primary_key=True)
    #   Qual contador e este. Hoje so existe um ("codigo_convertido"), mas a
    #   tabela ja nasce pronta para outros, se um dia precisarmos.

    valor = db.Column(db.Integer, nullable=False, default=0)
    #   O ultimo numero entregue.

    def __repr__(self):
        return f"<Contador {self.nome}={self.valor}>"


# Nome do contador usado pelas almas.
CONTADOR_CODIGO = "codigo_convertido"


# ===========================================================================
# GERADOR AUTOMATICO DO CODIGO SEQUENCIAL (#001, #002, #003...)
# ===========================================================================
@event.listens_for(NovoConvertido, "before_insert")
def gerar_codigo(mapper, connection, alvo):
    """
    Roda sozinho ANTES de cada alma nova ser gravada, e "puxa uma senha".

    Os tres passos:
      1. UPDATE contador SET valor = valor + 1   -> avanca a maquininha
      2. Se nao existia linha nenhuma, cria ja sincronizada com o banco atual
      3. SELECT valor                            -> le o numero que saiu

    Tudo isso roda na MESMA transacao da gravacao da alma. Se a gravacao for
    desfeita, o contador volta junto.
    """
    if alvo.codigo is not None:            # ja veio com codigo (ex: importacao) -> respeita
        return

    tabela = Contador.__table__            # a tabela "crua", sem passar pelo ORM

    # --- Passo 1: avancar a maquininha -----------------------------------
    resultado = connection.execute(
        tabela.update()
        .where(tabela.c.nome == CONTADOR_CODIGO)
        .values(valor=tabela.c.valor + 1)
        #   valor=tabela.c.valor + 1 vira "SET valor = valor + 1" no SQL.
        #   A soma acontece DENTRO do banco, nao no Python - e por isso que
        #   dois pedidos simultaneos nao se atrapalham.
    )

    # --- Passo 2: primeira vez? ------------------------------------------
    # rowcount = quantas linhas o UPDATE acertou. Zero significa que a linha do
    # contador ainda nao existe (banco recem-criado, ou dados importados).
    if resultado.rowcount == 0:
        maior_existente = connection.execute(
            db.select(func.coalesce(func.max(NovoConvertido.codigo), 0))
        ).scalar() or 0
        #   COALESCE troca "nada" por 0, cobrindo o banco vazio.
        #   Comecar do maior codigo ja existente evita repetir numero se o
        #   sistema for migrado de outro lugar.
        connection.execute(
            tabela.insert().values(nome=CONTADOR_CODIGO, valor=maior_existente + 1)
        )

    # --- Passo 3: ler o numero que saiu ----------------------------------
    alvo.codigo = connection.execute(
        db.select(tabela.c.valor).where(tabela.c.nome == CONTADOR_CODIGO)
    ).scalar()


# ===========================================================================
# INDICE COMPOSTO PARA O PAINEL
# ===========================================================================
Index(
    "ix_painel_status_responsavel",
    NovoConvertido.status_ciclo,
    NovoConvertido.responsavel_atual_id,
)
# A consulta mais usada do sistema e "me traga as almas em acompanhamento DESTE
# responsavel" (secao 5.2). Este indice junta as duas colunas num atalho unico,
# deixando o painel rapido mesmo com milhares de almas cadastradas.
