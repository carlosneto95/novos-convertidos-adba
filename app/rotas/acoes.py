# -*- coding: utf-8 -*-
"""
app/rotas/acoes.py - AS ACOES DA FICHA LATERAL (secao 5.3).

    POST /alma/<id>/contato      registrar contato
    POST /alma/<id>/presenca     marcar presenca ou falta
    POST /alma/<id>/status       alterar o status do ciclo de vida
    POST /alma/<id>/transferir   passar para outro responsavel (so Admin)

TODAS seguem o mesmo roteiro:
    1. o decorador confere a permissao ANTES de a funcao rodar
    2. o formulario valida no SERVIDOR
    3. a acao vai para a auditoria
    4. um unico commit grava tudo junto
    5. volta ao painel com a ficha daquela alma ja aberta

SOBRE O PASSO 5:
Em vez de atualizar so um pedacinho da tela, a pagina inteira recarrega.
Parece menos moderno, mas garante que o semaforo, os contadores do topo e a
lista mostrem o MESMO estado do banco. Meia atualizacao e a origem classica
de "a tela diz uma coisa, o banco diz outra".
"""

# --- IMPORTACOES ----------------------------------------------------------
from datetime import timedelta
from urllib.parse import quote                 # prepara o texto para ir num link

from flask import Blueprint, redirect, url_for, flash, abort, current_app
from flask_login import current_user

from app.extensions import db
from app.models import NovoConvertido, Usuario, Contato, Atribuicao, Evento, Presenca
from app import opcoes, auditoria
from app.seguranca import admin_necessario, dono_da_alma_necessario
from app.tempo import agora, hoje, FUSO_BRASIL
from app.validacao import formatar_telefone, so_digitos


acoes = Blueprint("acoes", __name__)


# ===========================================================================
# AJUDANTES
# ===========================================================================
def voltar_para_ficha(alma_id):
    """Volta ao painel com a ficha daquela alma ja aberta."""
    return redirect(url_for("painel.index", ficha=alma_id))


def erros_do_formulario(form):
    """Junta as mensagens de erro numa frase so, para o aviso na tela."""
    mensagens = []
    for campo in form:
        for erro in campo.errors:
            mensagens.append(erro)
    return " ".join(mensagens) or "Confira os campos e tente de novo."


def eventos_do_periodo():
    """Cultos dos ultimos 60 dias ate hoje, do mais recente para o mais antigo."""
    dias = current_app.config.get("DIAS_JANELA_PRESENCAS", 60)
    return db.session.execute(
        db.select(Evento)
        .where(
            Evento.data >= hoje() - timedelta(days=dias),
            Evento.data <= hoje(),
            Evento.ativo.is_(True),
        )
        .order_by(Evento.data.desc())
    ).scalars().all()


# ===========================================================================
# ACAO 1: REGISTRAR CONTATO
# ===========================================================================
@acoes.route("/alma/<alma_id>/contato", methods=["POST"])
@dono_da_alma_necessario
def registrar_contato(alma_id, alma):
    """
    Grava uma ligacao, conversa de WhatsApp ou visita.

    E a acao mais importante do sistema: e ela que move os dois relogios do
    semaforo (secao 4).
      - QUALQUER contato zera o relogio da tentativa
      - so resultado="efetivo" zera o relogio do contato efetivo
    """
    from app.forms import ContatoForm

    form = ContatoForm()

    if not form.validate_on_submit():
        flash(erros_do_formulario(form), "erro")
        return voltar_para_ficha(alma.id)

    # O navegador manda a hora de Brasilia sem o fuso anexado. Anexamos aqui
    # antes de gravar - o banco guarda tudo em UTC (ver app/tempo.py).
    momento = form.data_hora.data.replace(tzinfo=FUSO_BRASIL)

    db.session.add(
        Contato(
            convertido_id=alma.id,
            responsavel_id=current_user.id,
            tipo=form.tipo.data,
            data_hora=momento,
            resultado=form.resultado.data,
            relato=(form.relato.data or "").strip()[:3000],
            criado_em=agora(),
        )
    )

    auditoria.registrar(
        acao=auditoria.CONTATO_REGISTRADO,
        entidade="novo_convertido",
        entidade_id=alma.id,
        detalhe=f"{alma.codigo_formatado} {form.tipo.data}/{form.resultado.data}",
    )

    db.session.commit()

    # A mensagem explica O QUE MUDOU no semaforo. Sem isso, o responsavel nao
    # entende por que o card continuou vermelho depois de ele registrar algo.
    if form.resultado.data == opcoes.RESULTADO_EFETIVO:
        flash(
            f"Contato com {alma.primeiro_nome} registrado. Os dois relógios zeraram.",
            "sucesso",
        )
    else:
        flash(
            "Tentativa registrada. O relógio da tentativa zerou, mas o do "
            "contato efetivo continua correndo.",
            "aviso",
        )

    return voltar_para_ficha(alma.id)


# ===========================================================================
# ACAO 2: MARCAR PRESENCA
# ===========================================================================
@acoes.route("/alma/<alma_id>/presenca", methods=["POST"])
@dono_da_alma_necessario
def marcar_presenca(alma_id, alma):
    """Marca presenca ou falta num culto."""
    from app.forms import PresencaForm

    form = PresencaForm()

    # As opcoes vem do banco, entao sao preenchidas agora - e nao no forms.py.
    # Isto tambem VALIDA a escolha: um id de evento fora desta lista e
    # recusado pelo proprio WTForms, antes de chegar no banco.
    form.evento_id.choices = [(e.id, e.nome) for e in eventos_do_periodo()]

    if not form.validate_on_submit():
        flash(erros_do_formulario(form), "erro")
        return voltar_para_ficha(alma.id)

    evento = db.session.get(Evento, form.evento_id.data)
    if evento is None:
        flash("Culto não encontrado.", "erro")
        return voltar_para_ficha(alma.id)

    presente = form.presente.data == "sim"

    # Ja existe marcacao para esta alma neste culto?
    # A tabela tem UNIQUE(convertido_id, evento_id). Sem esta checagem, marcar
    # duas vezes estouraria um erro de banco na cara do usuario. Aqui, em vez
    # de quebrar, atualizamos a marcacao existente.
    registro = db.session.execute(
        db.select(Presenca).where(
            Presenca.convertido_id == alma.id,
            Presenca.evento_id == evento.id,
        )
    ).scalar_one_or_none()

    if registro:
        registro.presente = presente
        registro.registrado_por_id = current_user.id
        registro.registrado_em = agora()
        verbo = "atualizada"
    else:
        db.session.add(
            Presenca(
                convertido_id=alma.id,
                evento_id=evento.id,
                presente=presente,
                registrado_por_id=current_user.id,
                registrado_em=agora(),
            )
        )
        verbo = "registrada"

    auditoria.registrar(
        acao=auditoria.PRESENCA_REGISTRADA,
        entidade="novo_convertido",
        entidade_id=alma.id,
        detalhe=f"{evento.nome} ({evento.data}) -> {'presente' if presente else 'faltou'}",
    )

    db.session.commit()

    flash(
        f"Presença {verbo}: {alma.primeiro_nome} "
        f"{'esteve' if presente else 'faltou'} no {evento.nome}.",
        "sucesso",
    )
    return voltar_para_ficha(alma.id)


# ===========================================================================
# ACAO 3: ALTERAR STATUS
# ===========================================================================
@acoes.route("/alma/<alma_id>/status", methods=["POST"])
@dono_da_alma_necessario
def alterar_status(alma_id, alma):
    """Muda o status do ciclo de vida (integrada, mudou de cidade, etc)."""
    from app.forms import StatusForm

    form = StatusForm()

    if not form.validate_on_submit():
        flash(erros_do_formulario(form), "erro")
        return voltar_para_ficha(alma.id)

    anterior = alma.status_ciclo
    novo = form.status_ciclo.data

    if anterior == novo:
        flash("O status já era esse. Nada foi alterado.", "aviso")
        return voltar_para_ficha(alma.id)

    alma.status_ciclo = novo
    alma.status_justificativa = (form.justificativa.data or "").strip()[:2000] or None
    alma.status_alterado_em = agora()

    auditoria.registrar(
        acao=auditoria.STATUS_ALTERADO,
        entidade="novo_convertido",
        entidade_id=alma.id,
        detalhe=(
            f"status: {anterior} -> {novo} | "
            f"{alma.status_justificativa or 'sem justificativa'}"
        ),
    )

    db.session.commit()

    if novo == opcoes.STATUS_ATIVO:
        flash(f"{alma.primeiro_nome} voltou para o acompanhamento.", "sucesso")
    else:
        flash(
            f"Status alterado para {alma.status_rotulo}. "
            f"{alma.primeiro_nome} sai do semáforo e do painel principal.",
            "sucesso",
        )

    return voltar_para_ficha(alma.id)


# ===========================================================================
# ACAO 4: TRANSFERIR RESPONSAVEL (so Admin)
# ===========================================================================
@acoes.route("/alma/<alma_id>/transferir", methods=["POST"])
@admin_necessario
def transferir(alma_id):
    """
    Passa a alma para outro responsavel.

    A REGRA DAS 48 HORAS (secao 4):
    ao atualizar designado_em, o relogio do primeiro contato volta a correr do
    zero - o novo responsavel tem 48h para se apresentar. Mas o historico de
    contatos NAO e apagado: continua inteiro na aba Contatos.
    """
    from app.forms import TransferirForm

    alma = db.session.get(NovoConvertido, alma_id)
    if alma is None:
        abort(404)

    form = TransferirForm()
    ativos = db.session.execute(
        db.select(Usuario).where(Usuario.ativo.is_(True)).order_by(Usuario.nome)
    ).scalars().all()
    form.responsavel_id.choices = [(u.id, u.nome) for u in ativos]

    if not form.validate_on_submit():
        flash(erros_do_formulario(form), "erro")
        return voltar_para_ficha(alma.id)

    novo = db.session.get(Usuario, form.responsavel_id.data)
    if novo is None or not novo.ativo:
        flash("Selecione um responsável válido.", "erro")
        return voltar_para_ficha(alma.id)

    if novo.id == alma.responsavel_atual_id:
        flash("Essa alma já é acompanhada por essa pessoa.", "aviso")
        return voltar_para_ficha(alma.id)

    anterior = alma.responsavel_atual

    # --- Fecha a atribuicao anterior. A linha NUNCA e apagada (secao 3) ---
    aberta = db.session.execute(
        db.select(Atribuicao).where(
            Atribuicao.convertido_id == alma.id,
            Atribuicao.fim.is_(None),
        )
    ).scalars().first()
    if aberta:
        aberta.fim = agora()

    db.session.add(
        Atribuicao(
            convertido_id=alma.id,
            responsavel_id=novo.id,
            inicio=agora(),
            motivo=(form.motivo.data or "").strip()[:1000],
            atribuido_por_id=current_user.id,
        )
    )

    alma.responsavel_atual_id = novo.id
    alma.designado_em = agora()   # <- e esta linha que volta o relogio a 48h

    # --- A observacao sensivel (secao 7, item 11) ------------------------
    # NAO e repassada automaticamente. Se o Admin nao marcar a caixa, o campo
    # e apagado: o novo responsavel comeca sem aquela informacao intima.
    observacao_apagada = False
    if not form.manter_observacao.data and alma.observacao_sensivel:
        alma.observacao_sensivel = None
        observacao_apagada = True

    auditoria.registrar(
        acao=auditoria.TRANSFERIR,
        entidade="novo_convertido",
        entidade_id=alma.id,
        detalhe=(
            f"{alma.codigo_formatado}: "
            f"{anterior.nome if anterior else 'ninguem'} -> {novo.nome} | "
            f"motivo: {form.motivo.data} | "
            f"observacao sensivel: {'apagada' if observacao_apagada else 'mantida'}"
        ),
    )

    db.session.commit()

    aviso = (
        f"{alma.primeiro_nome} agora é acompanhada por {novo.primeiro_nome}. "
        f"O relógio voltou para 48 horas."
    )
    if observacao_apagada:
        aviso += " A observação sensível NÃO foi repassada."
    flash(aviso, "sucesso")

    return voltar_para_ficha(alma.id)


# ===========================================================================
# A MENSAGEM DE BOAS-VINDAS PELO WHATSAPP (secao 5.3)
# ===========================================================================
# Antes este botao montava um RELATORIO interno (status, presencas, cor do
# semaforo) para circular entre lideres. Agora o objetivo e outro: e a
# primeira mensagem que o RESPONSAVEL manda para a propria alma, se
# apresentando.

# .weekday() devolve 0 (segunda) ate 6 (domingo) - esta lista segue a mesma ordem.
DIAS_DA_SEMANA = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


def proximos_cultos(quantidade=2):
    """Os proximos cultos ativos, de HOJE (inclusive) em diante, do mais perto ao mais longe."""
    return db.session.execute(
        db.select(Evento)
        .where(Evento.data >= hoje(), Evento.ativo.is_(True))
        .order_by(Evento.data, Evento.nome)
        .limit(quantidade)
    ).scalars().all()


def linha_da_agenda(evento):
    """
    Uma linha da agenda. Ex: "• Domingo, 28/09 — Culto Dominical, às 18h".

    O horario vem do config.py (HORARIOS_CULTOS), pelo TIPO do culto. Se o
    tipo nao tiver horario cadastrado, a linha sai sem ele - melhor faltar a
    hora do que mandar uma hora errada.
    """
    dia = DIAS_DA_SEMANA[evento.data.weekday()]
    linha = f"• {dia}, {evento.data.strftime('%d/%m')} — {evento.nome}"
    horario = current_app.config.get("HORARIOS_CULTOS", {}).get(evento.tipo)
    if horario:
        linha += f", às {horario}"
    return linha


def montar_mensagem_boas_vindas(alma, remetente, cultos):
    """
    Monta a mensagem que o responsavel manda para o novo convertido.
    Os asteriscos viram NEGRITO no WhatsApp.

    Parametros:
        alma      - o NovoConvertido que vai RECEBER a mensagem
        remetente - o Usuario que se apresenta (o responsavel da alma)
        cultos    - a lista de Evento da agenda (os proximos 2)

    A ordem segue o pedido: parabens e boas-vindas primeiro, depois quem
    esta falando, a data e o culto da conversao, a disposicao (e a visita),
    a agenda, o convite e, por fim, "salva meu numero".
    """
    # A palavra muda com o sexo. Detalhe pequeno que faz o texto soar humano.
    bem_vindo = "bem-vinda" if alma.sexo == "F" else "bem-vindo"

    # "no Culto Dominical", "no Encontro de Tribo"... funciona para todos os
    # trabalhos da lista. O "outro" e texto livre (ex: "Batismo nas aguas"):
    # ai vai entre parenteses, para a frase nao ficar torta.
    data = alma.data_conversao.strftime("%d/%m/%Y")
    if alma.trabalho == "outro":
        quando = f"No dia {data} ({alma.trabalho_rotulo})"
    else:
        quando = f"No dia {data}, no {alma.trabalho_rotulo}"

    igreja = current_app.config.get("IGREJA_NOME_LEGAL", "Assembleia de Deus")

    linhas = [
        f"A Paz do Senhor, {alma.primeiro_nome}!",
        "",
        f"Antes de tudo: *parabéns pela decisão mais importante da sua vida!* 🙌 "
        f"Seja muito {bem_vindo} à família!",
        "",
        f"Aqui é {remetente.primeiro_nome}, da *{igreja}*. "
        f"{quando}, você aceitou Jesus — e o céu fez festa por isso! 🎉",
        "",
        "A partir de agora eu vou caminhar com você nessa nova fase. Estou à "
        "disposição para o que precisar: conversar, orar junto, tirar dúvidas. "
        "Se quiser, posso fazer uma *visita* na sua casa — é só me dizer o "
        "melhor dia e horário.",
    ]

    if cultos:
        linhas += ["", "📅 *Nossos próximos cultos:*"]
        linhas += [linha_da_agenda(e) for e in cultos]
        linhas += [
            "",
            "Quero muito te receber em um desses cultos! Me conta qual fica "
            "melhor pra você, que eu vou estar te esperando. 🙏",
        ]
    else:
        # Agenda vazia (ninguem rodou o "flask seed-eventos"): o convite
        # continua, so sem as datas.
        linhas += [
            "",
            "Quero muito te receber no nosso próximo culto! Me chama que eu "
            "te passo os dias e horários. 🙏",
        ]

    numero = f" — {formatar_telefone(remetente.telefone)}" if remetente.telefone else ""
    linhas += ["", f"📲 *Não esquece de salvar meu número:* {remetente.nome}{numero}"]

    return "\n".join(linhas)


def link_whatsapp(telefone, texto):
    """
    O endereco que abre o WhatsApp JA na conversa com a alma e com o texto
    escrito - o responsavel so confere e aperta enviar.

    O wa.me exige o numero com o codigo do pais (55) e so com digitos. Se o
    telefone nao tiver o tamanho de um numero brasileiro (10 ou 11 digitos),
    devolve None e a tela mostra so o botao de copiar.
    """
    digitos = so_digitos(telefone)
    if len(digitos) not in (10, 11):
        return None
    return f"https://wa.me/55{digitos}?text={quote(texto)}"
