# -*- coding: utf-8 -*-
"""
app/rotas/painel.py - O PAINEL (secao 5.2).

Uma tela so, que responde de relance:
    quem esta em dia, quem esta abandonado, e quem ainda nem tem responsavel.

A REGRA DE SEGURANCA MAIS IMPORTANTE DO ARQUIVO (secao 7, item 3):
a consulta ao banco JA NASCE filtrada pelo que a pessoa pode ver. O
Responsavel nunca recebe do banco as almas dos outros - nao existe nada para
esconder na tela depois, porque nunca chegou ali.
"""

# --- IMPORTACOES ----------------------------------------------------------
from datetime import timedelta

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, abort,
    current_app,
)
from flask_login import login_required, current_user

from app.extensions import db
from app.models import NovoConvertido, Usuario, Contato, Atribuicao
from app import opcoes, semaforo as sem, auditoria
from app.seguranca import admin_necessario, dono_da_alma_necessario
from app.tempo import agora, hoje
from app.validacao import so_digitos


painel = Blueprint("painel", __name__)


# ===========================================================================
# AJUDANTE: AS DATAS DOS DOIS RELOGIOS, EM UMA CONSULTA SO
# ===========================================================================
def mapas_de_contato(ids_das_almas):
    """
    Devolve dois dicionarios:
        {id_da_alma: data do ultimo contato de qualquer tipo}
        {id_da_alma: data do ultimo contato EFETIVO}

    POR QUE ASSIM E NAO PERGUNTANDO ALMA POR ALMA?
    Com 200 almas, perguntar uma a uma daria 400 consultas ao banco e a tela
    levaria segundos para abrir. Aqui sao DUAS consultas, sempre - nao importa
    se ha 10 almas ou 10 mil. E o que se chama evitar o "problema N+1".

    O GROUP BY pede ao banco: "para cada alma, me devolva a data mais recente".
    """
    if not ids_das_almas:
        return {}, {}

    # --- Consulta 1: o ultimo contato de QUALQUER tipo -------------------
    linhas = db.session.execute(
        db.select(Contato.convertido_id, db.func.max(Contato.data_hora))
        .where(Contato.convertido_id.in_(ids_das_almas))
        .group_by(Contato.convertido_id)
    ).all()
    tentativas = {linha[0]: linha[1] for linha in linhas}

    # --- Consulta 2: o ultimo contato EFETIVO ----------------------------
    linhas = db.session.execute(
        db.select(Contato.convertido_id, db.func.max(Contato.data_hora))
        .where(
            Contato.convertido_id.in_(ids_das_almas),
            Contato.resultado == opcoes.RESULTADO_EFETIVO,
        )
        .group_by(Contato.convertido_id)
    ).all()
    efetivos = {linha[0]: linha[1] for linha in linhas}

    return tentativas, efetivos


# ===========================================================================
# A TELA DO PAINEL
# ===========================================================================
@painel.route("/painel")
@login_required
def index():
    """O painel de uma pagina so."""

    # =====================================================================
    # PASSO 1 - LER OS FILTROS DA URL
    # =====================================================================
    # Os filtros viajam na URL (?cor=vermelho&dep=preciosas). Vantagem: a
    # pessoa pode salvar o link ou mandar no grupo - "olha as criticas aqui".
    f_status = request.args.get("status", "").strip()
    f_responsavel = request.args.get("responsavel", "").strip()
    f_departamento = request.args.get("departamento", "").strip()
    f_cor = request.args.get("cor", "").strip()
    f_trabalho = request.args.get("trabalho", "").strip()
    f_periodo = request.args.get("periodo", "").strip()
    busca = request.args.get("busca", "").strip()

    # =====================================================================
    # PASSO 2 - MONTAR A CONSULTA, JA RESTRITA
    # =====================================================================
    consulta = db.select(NovoConvertido).where(
        # Duplicatas mescladas somem do painel (secao 5.7).
        NovoConvertido.mesclado_em_id.is_(None)
    )

    # ----- A TRAVA (secao 7, itens 2 e 3) --------------------------------
    # Esta linha e a diferenca entre um sistema seguro e um vazamento.
    if not current_user.eh_admin:
        consulta = consulta.where(
            NovoConvertido.responsavel_atual_id == current_user.id
        )

    # ----- Filtro: status -------------------------------------------------
    if f_status and f_status in opcoes.STATUS_CICLO:
        consulta = consulta.where(NovoConvertido.status_ciclo == f_status)
    elif f_status == "todos":
        pass                          # mostra tudo, inclusive encerradas
    else:
        # Sem filtro escolhido, o painel mostra o que importa no dia a dia:
        # quem esta em acompanhamento + quem aguarda responsavel.
        consulta = consulta.where(
            NovoConvertido.status_ciclo.in_(
                [opcoes.STATUS_ATIVO, opcoes.STATUS_INICIAL]
            )
        )

    # ----- Filtro: responsavel (so faz sentido para o Admin) -------------
    if f_responsavel and current_user.eh_admin:
        if f_responsavel == "sem_responsavel":
            consulta = consulta.where(NovoConvertido.responsavel_atual_id.is_(None))
        else:
            consulta = consulta.where(
                NovoConvertido.responsavel_atual_id == f_responsavel
            )

    # ----- Filtro: departamento ------------------------------------------
    if f_departamento and f_departamento in opcoes.DEPARTAMENTOS:
        consulta = consulta.where(NovoConvertido.departamento == f_departamento)

    # ----- Filtro: trabalho de conversao ---------------------------------
    if f_trabalho and f_trabalho in opcoes.TRABALHOS:
        consulta = consulta.where(NovoConvertido.trabalho == f_trabalho)

    # ----- Filtro: periodo de conversao ----------------------------------
    dias_periodo = {"7": 7, "30": 30, "90": 90, "365": 365}.get(f_periodo)
    if dias_periodo:
        consulta = consulta.where(
            NovoConvertido.data_conversao >= hoje() - timedelta(days=dias_periodo)
        )

    # ----- Busca por nome, telefone ou codigo -----------------------------
    if busca:
        # ilike = compara ignorando maiusculas. O % significa "qualquer coisa".
        # "%maria%" acha "Maria", "MARIA SILVA" e "Ana Maria".
        padrao = f"%{busca}%"
        condicoes = [NovoConvertido.nome_completo.ilike(padrao)]

        # Se a pessoa digitou numeros, procuramos tambem no telefone.
        # Comparamos so os digitos, porque e assim que o telefone e guardado.
        digitos = so_digitos(busca)
        if digitos:
            condicoes.append(NovoConvertido.telefone.ilike(f"%{digitos}%"))

            # Se digitou algo como "12" ou "#12", pode ser o codigo.
            try:
                condicoes.append(NovoConvertido.codigo == int(digitos))
            except (ValueError, OverflowError):
                pass

        # or_ = "qualquer uma destas condicoes serve"
        consulta = consulta.where(db.or_(*condicoes))

    # ----- Ordem ----------------------------------------------------------
    # Mais recentes primeiro: a alma nova e a que corre mais risco.
    consulta = consulta.order_by(NovoConvertido.criado_em.desc())

    # =====================================================================
    # PASSO 3 - BUSCAR E CALCULAR O SEMAFORO
    # =====================================================================
    almas = db.session.execute(consulta).scalars().all()

    ids = [a.id for a in almas]
    tentativas, efetivos = mapas_de_contato(ids)

    pares = sem.calcular_muitas(almas, tentativas, efetivos)

    # ----- Filtro: cor ----------------------------------------------------
    # A cor so existe DEPOIS do calculo, entao este filtro e aplicado aqui,
    # e nao no banco. Como a lista ja veio restrita pela permissao, nao ha
    # risco: nada que a pessoa nao possa ver passou por aqui.
    if f_cor:
        pares = [(a, s) for a, s in pares if s.cor == f_cor]

    # =====================================================================
    # PASSO 4 - OS NUMEROS DO TOPO
    # =====================================================================
    # Os KPIs contam SEM o filtro de cor, senao o cartao "criticas" mostraria
    # sempre o mesmo numero do filtro escolhido.
    pares_para_kpi = sem.calcular_muitas(almas, tentativas, efetivos)
    contagem = sem.contar_por_cor(pares_para_kpi)

    # ----- Integradas no mes (secao 5.2) ---------------------------------
    primeiro_do_mes = hoje().replace(day=1)
    consulta_integradas = db.select(db.func.count()).select_from(NovoConvertido).where(
        NovoConvertido.status_ciclo == "integrado",
        NovoConvertido.status_alterado_em >= primeiro_do_mes,
        NovoConvertido.mesclado_em_id.is_(None),
    )
    if not current_user.eh_admin:
        consulta_integradas = consulta_integradas.where(
            NovoConvertido.responsavel_atual_id == current_user.id
        )
    integradas_no_mes = db.session.scalar(consulta_integradas) or 0

    # =====================================================================
    # PASSO 5 - A FAIXA ROXA (so Admin)
    # =====================================================================
    aguardando = []
    if current_user.eh_admin:
        aguardando = db.session.execute(
            db.select(NovoConvertido)
            .where(
                NovoConvertido.status_ciclo == opcoes.STATUS_INICIAL,
                NovoConvertido.mesclado_em_id.is_(None),
            )
            .order_by(NovoConvertido.criado_em.asc())   # a mais antiga primeiro
        ).scalars().all()

    dias_mais_antiga = None
    if aguardando:
        s = sem.calcular(aguardando[0])
        dias_mais_antiga = s.dias

    # =====================================================================
    # PASSO 6 - LISTAS PARA OS FILTROS
    # =====================================================================
    responsaveis = []
    if current_user.eh_admin:
        responsaveis = db.session.execute(
            db.select(Usuario)
            .where(Usuario.ativo.is_(True))
            .order_by(Usuario.nome)
        ).scalars().all()

    return render_template(
        "painel/index.html",
        pares=pares,
        contagem=contagem,
        integradas_no_mes=integradas_no_mes,
        aguardando=aguardando,
        dias_mais_antiga=dias_mais_antiga,
        responsaveis=responsaveis,
        # devolve os filtros para a tela marcar o que esta ativo
        filtros={
            "status": f_status,
            "responsavel": f_responsavel,
            "departamento": f_departamento,
            "cor": f_cor,
            "trabalho": f_trabalho,
            "periodo": f_periodo,
            "busca": busca,
        },
        tem_filtro=any([f_status, f_responsavel, f_departamento, f_cor,
                        f_trabalho, f_periodo, busca]),
    )


# ===========================================================================
# DESIGNAR RESPONSAVEL (so Admin)
# ===========================================================================
@painel.route("/alma/<alma_id>/designar", methods=["POST"])
@admin_necessario
def designar(alma_id):
    """
    Entrega uma alma a um responsavel.

    E a acao que tira a alma do ROXO e a coloca no semaforo, iniciando o
    relogio de 48h do primeiro contato (secao 4).

    Esta rota nasce na Etapa 5 (e nao na 6, como a transferencia) porque sem
    ela a faixa roxa seria so um aviso sem saida: nada sairia de "aguardando
    responsavel" e o semaforo nunca teria o que mostrar.
    """
    alma = db.session.get(NovoConvertido, alma_id)
    if alma is None:
        abort(404)

    responsavel_id = (request.form.get("responsavel_id") or "").strip()

    # --- Confere o responsavel escolhido ---------------------------------
    # Nunca confiamos no que veio do formulario: alguem poderia mandar o id
    # de um usuario desativado, ou um id inventado.
    responsavel = db.session.get(Usuario, responsavel_id) if responsavel_id else None
    if responsavel is None or not responsavel.ativo:
        flash("Selecione um responsável válido.", "erro")
        return redirect(url_for("painel.index"))

    # --- Fecha a atribuicao anterior, se houver --------------------------
    # A linha antiga NUNCA e apagada: ganha uma data de fim (secao 3).
    anterior = db.session.execute(
        db.select(Atribuicao).where(
            Atribuicao.convertido_id == alma.id,
            Atribuicao.fim.is_(None),
        )
    ).scalars().first()

    if anterior:
        anterior.fim = agora()

    # --- Abre a atribuicao nova ------------------------------------------
    db.session.add(
        Atribuicao(
            convertido_id=alma.id,
            responsavel_id=responsavel.id,
            inicio=agora(),
            motivo=(request.form.get("motivo") or "Primeira designação").strip()[:500],
            atribuido_por_id=current_user.id,
        )
    )

    # --- Atualiza a alma --------------------------------------------------
    alma.responsavel_atual_id = responsavel.id

    # designado_em e o marco zero do relogio de 48h. E por atualizar este
    # campo que a transferencia "volta o relogio", como pede a secao 4.
    alma.designado_em = agora()

    if alma.status_ciclo == opcoes.STATUS_INICIAL:
        alma.status_ciclo = opcoes.STATUS_ATIVO
        alma.status_alterado_em = agora()

    auditoria.registrar(
        acao=auditoria.DESIGNAR,
        entidade="novo_convertido",
        entidade_id=alma.id,
        detalhe=f"{alma.codigo_formatado} {alma.nome_completo} -> {responsavel.nome}",
    )

    db.session.commit()

    flash(
        f"{alma.primeiro_nome} agora é acompanhada por {responsavel.primeiro_nome}. "
        f"O prazo do primeiro contato é de 48 horas.",
        "sucesso",
    )
    return redirect(url_for("painel.index"))


# ===========================================================================
# A FICHA DA ALMA (o "drawer" lateral) - secao 5.3
# ===========================================================================
@painel.route("/alma/<alma_id>/ficha")
@dono_da_alma_necessario
def ficha(alma_id, alma):
    """
    Devolve o conteudo da ficha lateral: dados, contatos, presencas, historico.

    POR QUE UMA ROTA SEPARADA, E NAO TUDO JUNTO NO PAINEL?
    Se o painel ja trouxesse os contatos de todas as almas, uma igreja com
    300 almas carregaria milhares de registros a cada abertura da tela - e
    99% deles nunca seriam olhados. Aqui buscamos so quando a pessoa clica.

    A SEGURANCA E O DECORADOR:
    @dono_da_alma_necessario roda ANTES desta funcao. Ele busca a alma,
    confere se ela pertence ao responsavel logado e devolve 403 se nao
    pertencer - registrando a tentativa na auditoria. Um responsavel que
    descubra o UUID de outra alma e digite esta URL recebe "Acesso nao
    autorizado", nao a ficha.
    """
    from app.models import Evento, Presenca
    from app.seguranca import pode_ver_observacao_sensivel

    # =====================================================================
    # 1. CONTATOS - a aba principal (secao 5.3)
    # =====================================================================
    # Mais recente primeiro, que e a ordem em que as pessoas leem historico.
    contatos = db.session.execute(
        db.select(Contato)
        .where(Contato.convertido_id == alma.id)
        .order_by(Contato.data_hora.desc())
    ).scalars().all()

    # =====================================================================
    # 2. PRESENCAS - os eventos dos ultimos 60 dias (secao 5.3)
    # =====================================================================
    dias_janela = current_app.config.get("DIAS_JANELA_PRESENCAS", 60)
    desde = hoje() - timedelta(days=dias_janela)

    eventos = db.session.execute(
        db.select(Evento)
        .where(
            Evento.data >= desde,
            Evento.data <= hoje(),
            Evento.ativo.is_(True),
        )
        .order_by(Evento.data.desc())
    ).scalars().all()

    # Busca de uma vez todas as presencas desta alma e monta um dicionario.
    # Assim o template consulta {evento_id: presente} sem ir ao banco em cada
    # linha - o mesmo cuidado com o "problema N+1" do resto do sistema.
    registros = db.session.execute(
        db.select(Presenca).where(Presenca.convertido_id == alma.id)
    ).scalars().all()
    mapa_presencas = {p.evento_id: p for p in registros}

    # Conta so o que foi efetivamente marcado como presente.
    total_presente = sum(1 for p in registros if p.presente)
    total_marcado = len(registros)

    # =====================================================================
    # 3. HISTORICO DE RESPONSAVEIS (secao 5.3)
    # =====================================================================
    atribuicoes = db.session.execute(
        db.select(Atribuicao)
        .where(Atribuicao.convertido_id == alma.id)
        .order_by(Atribuicao.inicio.desc())
    ).scalars().all()

    # =====================================================================
    # 4. O SEMAFORO DESTA ALMA
    # =====================================================================
    tentativas, efetivos = mapas_de_contato([alma.id])
    s = sem.calcular(alma, tentativas.get(alma.id), efetivos.get(alma.id))

    # =====================================================================
    # 5. OBSERVACAO SENSIVEL (secao 7, item 11)
    # =====================================================================
    # Visivel so ao Admin e ao responsavel ATUAL. E toda LEITURA vira
    # registro de auditoria - porque este campo guarda informacao intima.
    mostrar_observacao = pode_ver_observacao_sensivel(alma)

    if mostrar_observacao and alma.observacao_sensivel:
        auditoria.registrar(
            acao=auditoria.LEITURA_OBSERVACAO_SENSIVEL,
            entidade="novo_convertido",
            entidade_id=alma.id,
            detalhe=f"{alma.codigo_formatado} {alma.nome_completo}",
            gravar=True,
        )

    # =====================================================================
    # 6. OS FORMULARIOS DAS ACOES (Etapa 6)
    # =====================================================================
    from app.forms import ContatoForm, PresencaForm, StatusForm, TransferirForm
    from app.rotas.acoes import eventos_do_periodo, montar_relatorio_whatsapp
    from app.tempo import para_local

    form_contato = ContatoForm()
    # Ja vem preenchido com a hora de AGORA, no horario de Brasilia: quase
    # sempre e essa a resposta, e um campo pre-preenchido poupa digitacao.
    form_contato.data_hora.data = para_local(agora()).replace(second=0, microsecond=0)

    form_presenca = PresencaForm()
    eventos_para_marcar = eventos_do_periodo()
    form_presenca.evento_id.choices = [
        (e.id, f"{e.nome} — {e.data.strftime('%d/%m')}") for e in eventos_para_marcar
    ]

    form_status = StatusForm()
    form_status.status_ciclo.data = alma.status_ciclo

    form_transferir = TransferirForm()
    responsaveis_ativos = db.session.execute(
        db.select(Usuario).where(Usuario.ativo.is_(True)).order_by(Usuario.nome)
    ).scalars().all()
    form_transferir.responsavel_id.choices = [(u.id, u.nome) for u in responsaveis_ativos]

    # O texto do WhatsApp e montado NO SERVIDOR. Assim o formato fica num
    # lugar so, e o JavaScript nao precisa saber nada das regras do sistema.
    texto_whatsapp = montar_relatorio_whatsapp(
        alma, s, total_presente, len(eventos), contatos[0] if contatos else None
    )

    return render_template(
        "painel/_drawer.html",
        alma=alma,
        s=s,
        contatos=contatos,
        form_contato=form_contato,
        form_presenca=form_presenca,
        form_status=form_status,
        form_transferir=form_transferir,
        tem_eventos=bool(eventos_para_marcar),
        texto_whatsapp=texto_whatsapp,
        eventos=eventos,
        mapa_presencas=mapa_presencas,
        total_presente=total_presente,
        total_marcado=total_marcado,
        dias_janela=dias_janela,
        atribuicoes=atribuicoes,
        mostrar_observacao=mostrar_observacao,
    )
