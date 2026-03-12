from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_required, current_user
from auth import admin_required, is_superadmin
from utils import log_action
from extensions import db
from models import Funcionario, FuncionarioLancamento, FolhaPagamento, Transacao, Categoria, Carteira
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
import calendar

funcionarios_bp = Blueprint('funcionarios', __name__, template_folder='templates')

INSS_RATE = Decimal('0.075')  # 7,5%


def calcular_inss(salario_bruto, inss_percent=7.5):
    """Calcula o desconto INSS baseando-se no percentual do funcionário."""
    rate = Decimal(str(inss_percent)) / Decimal('100')
    return (Decimal(str(salario_bruto)) * rate).quantize(Decimal('0.01'))


def get_carteira_ativa():
    """Helper para obter a carteira ativa (ou lista delas) priorizando a URL e depois a Sessão."""
    c_list = request.args.getlist('carteira')
    if c_list:
        if len(c_list) == 1 and c_list[0] == 'Consolidada':
            c_ativa = 'Consolidada'
        else:
            if 'Consolidada' in c_list:
                c_ativa = 'Consolidada'
            else:
                c_ativa = c_list if len(c_list) > 1 else c_list[0]
        # Persiste na sessão para que links sem parâmetros mantenham a seleção
        session['carteira_ativa'] = c_ativa
        return c_ativa
    return session.get('carteira_ativa', 'Consolidada')


def get_funcionarios_query(ativo=None):
    """
    Retorna query de Funcionario filtrada pela carteira ativa e permissões
    do usuário, espelhando a lógica de get_authorized_query em finance.py.
    """
    c_ativa = get_carteira_ativa()
    query = Funcionario.query

    if ativo is not None:
        query = query.filter_by(ativo=ativo)

    if is_superadmin():
        if c_ativa == 'Consolidada':
            return query
        c_obj = Carteira.query.filter_by(nome=c_ativa).first()
        if c_obj:
            return query.filter_by(carteira_id=c_obj.id)
        return query.filter(False)

    # Admin / Usuário: filtrar pelas carteiras atribuídas
    accessible_wallets = current_user.carteiras
    wallet_ids = [c.id for c in accessible_wallets]

    if not wallet_ids:
        return query.filter(False)

    if c_ativa == 'Consolidada':
        return query.filter(Funcionario.carteira_id.in_(wallet_ids))

    c_obj = Carteira.query.filter_by(nome=c_ativa).first()
    if c_obj and c_obj in accessible_wallets:
        return query.filter_by(carteira_id=c_obj.id)
    return query.filter(False)


def get_carteira_id_ativa():
    """Resolve o carteira_id da carteira ativa para gravação."""
    c_ativa = get_carteira_ativa()
    if c_ativa == 'Consolidada':
        # Usa a primeira carteira acessível ao usuário
        if is_superadmin():
            c = Carteira.query.first()
        else:
            wallets = current_user.carteiras
            c = wallets[0] if wallets else None
        return c.id if c else None
    c_obj = Carteira.query.filter_by(nome=c_ativa).first()
    return c_obj.id if c_obj else None


# ─── LISTAR / CADASTRAR FUNCIONÁRIOS ─────────────────────────────────────────

@funcionarios_bp.route('/funcionarios')
@login_required
def funcionarios():
    c_ativa = get_carteira_ativa()
    carteiras = Carteira.query.order_by(Carteira.nome).all()

    ativos = get_funcionarios_query(ativo=True).order_by(Funcionario.nome).all()
    inativos = get_funcionarios_query(ativo=False).order_by(Funcionario.nome).all()
    total_folha = sum(Decimal(str(f.salario_bruto)) for f in ativos)
    total_inss = sum(calcular_inss(f.salario_bruto, f.inss_percent) for f in ativos)

    return render_template(
        'funcionarios/funcionarios.html',
        ativos=ativos,
        inativos=inativos,
        total_folha=total_folha,
        total_inss=total_inss,
        carteiras=carteiras,
        c_ativa=c_ativa,
    )


@funcionarios_bp.route('/funcionarios/add', methods=['POST'])
@login_required
@admin_required
@log_action("Cadastro de Funcionário")
def add_funcionario():
    nome = request.form.get('nome', '').strip()
    cpf = request.form.get('cpf', '').strip() or None
    salario_str = request.form.get('salario_bruto', '0').replace('.', '').replace(',', '.')
    data_admissao_str = request.form.get('data_admissao', '')
    carteira_id = request.form.get('carteira_id') or get_carteira_id_ativa()
    inss_percent_str = request.form.get('inss_percent', '7.5').replace(',', '.')
    chave_pix = request.form.get('chave_pix', '').strip() or None

    try:
        salario = Decimal(salario_str or '0')
    except InvalidOperation:
        salario = Decimal('0')

    data_admissao = None
    if data_admissao_str:
        try:
            data_admissao = datetime.strptime(data_admissao_str, '%Y-%m-%d').date()
        except ValueError:
            pass

    func = Funcionario(
        nome=nome, cpf=cpf, salario_bruto=salario,
        data_admissao=data_admissao, carteira_id=int(carteira_id) if carteira_id else None,
        inss_percent=Decimal(inss_percent_str or '7.5'),
        chave_pix=chave_pix
    )
    db.session.add(func)
    try:
        db.session.commit()
        flash(f'Funcionário "{nome}" cadastrado com sucesso!', 'success')
    except Exception:
        db.session.rollback()
        flash('Erro ao cadastrar funcionário. CPF pode já estar em uso.', 'danger')
    return redirect(url_for('funcionarios.funcionarios'))


@funcionarios_bp.route('/funcionarios/<int:id>/toggle', methods=['POST'])
@login_required
@admin_required
@log_action("Ativação/Desativação de Funcionário")
def toggle_funcionario(id):
    func = get_funcionarios_query().filter_by(id=id).first_or_404()
    func.ativo = not func.ativo
    db.session.commit()
    status = 'ativado' if func.ativo else 'desativado'
    flash(f'Funcionário "{func.nome}" {status}.', 'success')
    return redirect(url_for('funcionarios.funcionarios'))


@funcionarios_bp.route('/funcionarios/<int:id>/edit', methods=['POST'])
@login_required
@admin_required
@log_action("Edição de Funcionário")
def edit_funcionario(id):
    func = get_funcionarios_query().filter_by(id=id).first_or_404()
    nome = request.form.get('nome', '').strip()
    cpf = request.form.get('cpf', '').strip() or None
    salario_str = request.form.get('salario_bruto', '0').replace('.', '').replace(',', '.')
    data_admissao_str = request.form.get('data_admissao', '')
    carteira_id = request.form.get('carteira_id')
    inss_percent_str = request.form.get('inss_percent', '7.5').replace(',', '.')
    chave_pix = request.form.get('chave_pix', '').strip() or None

    if nome:
        func.nome = nome
    func.cpf = cpf
    if carteira_id:
        func.carteira_id = int(carteira_id)
    try:
        func.salario_bruto = Decimal(salario_str or '0')
    except InvalidOperation:
        pass
    if data_admissao_str:
        try:
            func.data_admissao = datetime.strptime(data_admissao_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    
    try:
        func.inss_percent = Decimal(inss_percent_str or '7.5')
        func.chave_pix = chave_pix
    except InvalidOperation:
        pass

    try:
        db.session.commit()
        flash('Dados do funcionário atualizados!', 'success')
    except Exception:
        db.session.rollback()
        flash('Erro ao atualizar funcionário.', 'danger')
    return redirect(url_for('funcionarios.funcionarios'))


# ─── LANÇAMENTOS (ADIANTAMENTOS / DESCONTOS) ─────────────────────────────────

@funcionarios_bp.route('/funcionarios/<int:id>/lancamentos')
@login_required
def lancamentos(id):
    hoje = date.today()
    mes_sel = int(request.args.get('mes', hoje.month))
    ano_sel = int(request.args.get('ano', hoje.year))

    # Garante que o funcionário pertence à carteira ativa do usuário
    func = get_funcionarios_query().filter_by(id=id).first_or_404()

    inicio = date(ano_sel, mes_sel, 1)
    fim = date(ano_sel, mes_sel, calendar.monthrange(ano_sel, mes_sel)[1])

    lancamentos_list = FuncionarioLancamento.query.filter(
        FuncionarioLancamento.funcionario_id == id,
        FuncionarioLancamento.data >= inicio,
        FuncionarioLancamento.data <= fim,
    ).order_by(FuncionarioLancamento.data.asc()).all()

    total_adiantamentos = sum(
        Decimal(str(l.valor)) for l in lancamentos_list if l.tipo == 'Adiantamento'
    )
    total_descontos = sum(
        Decimal(str(l.valor)) for l in lancamentos_list if l.tipo == 'Desconto'
    )

    meses_br = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

    return render_template(
        'funcionarios/lancamentos.html',
        func=func,
        lancamentos=lancamentos_list,
        total_adiantamentos=total_adiantamentos,
        total_descontos=total_descontos,
        mes_sel=mes_sel,
        ano_sel=ano_sel,
        hoje=hoje.strftime('%Y-%m-%d'),
        meses_br=meses_br,
    )


@funcionarios_bp.route('/funcionarios/<int:id>/extrato')
@login_required
def extrato(id):
    func = get_funcionarios_query().filter_by(id=id).first_or_404()
    # Apenas adiantamentos do funcionário
    lancamentos_todos = FuncionarioLancamento.query.filter_by(funcionario_id=id, tipo='Adiantamento').all()
    
    movimentacoes = []
    saldo_devedor = Decimal('0')
    
    for l in lancamentos_todos:
        # 1. Adiciona o lançamento (Adiantamento/Desconto)
        movimentacoes.append({
            'data': l.data,
            'descricao': l.tipo.upper(),
            'obs': l.observacao,
            'valor': Decimal(str(l.valor)),
            'pago': False
        })
        saldo_devedor += Decimal(str(l.valor))
        
        # 2. Se já foi pago (folha processada e PAGA), adiciona o "desconto"
        if l.folha_id and l.folha_rel.pago:
            data_pg = l.folha_rel.data_pagamento or date.today()
            # Formata mes_referencia de YYYY-MM para MM/YYYY
            partes = l.folha_rel.mes_referencia.split('-')
            mes_ref_fmt = f"{partes[1]}/{partes[0]}" if len(partes) == 2 else l.folha_rel.mes_referencia
            
            movimentacoes.append({
                'data': data_pg,
                'descricao': f'LIQUIDAÇÃO FOLHA ({mes_ref_fmt})',
                'obs': f'Descontado no pagamento de salário',
                'valor': -Decimal(str(l.valor)),
                'pago': True
            })
            saldo_devedor -= Decimal(str(l.valor))

    # Ordena as movimentações por data
    movimentacoes.sort(key=lambda x: x['data'])
    
    return render_template(
        'funcionarios/extrato.html',
        func=func,
        movimentacoes=movimentacoes,
        saldo_devedor=saldo_devedor,
        hoje=date.today()
    )


@funcionarios_bp.route('/funcionarios/<int:id>/lancamentos/add', methods=['POST'])
@login_required
@admin_required
@log_action("Lançamento deRH")
def add_lancamento(id):
    func = get_funcionarios_query().filter_by(id=id).first_or_404()
    tipo = request.form.get('tipo', 'Adiantamento')
    valor_str = request.form.get('valor', '0').replace('.', '').replace(',', '.')
    data_str = request.form.get('data', '')
    obs = request.form.get('observacao', '').strip() or None
    mes_sel = request.args.get('mes', date.today().month)
    ano_sel = request.args.get('ano', date.today().year)

    try:
        valor = Decimal(valor_str or '0')
    except InvalidOperation:
        valor = Decimal('0')

    data_lanc = date.today()
    if data_str:
        try:
            data_lanc = datetime.strptime(data_str, '%Y-%m-%d').date()
        except ValueError:
            pass

    lanc = FuncionarioLancamento(
        funcionario_id=func.id, tipo=tipo, valor=valor, data=data_lanc, observacao=obs,
    )
    db.session.add(lanc)
    db.session.commit()
    flash(f'{tipo} de R$ {valor:,.2f} registrado para {func.nome}.', 'success')

    if request.args.get('redirect') == 'folha':
        return redirect(url_for('funcionarios.folha', mes=mes_sel, ano=ano_sel))
    return redirect(url_for('funcionarios.lancamentos', id=id, mes=mes_sel, ano=ano_sel))


@funcionarios_bp.route('/funcionarios/lancamentos/<int:id>/edit', methods=['POST'])
@login_required
@admin_required
@log_action("Edição de Lançamento RH")
def edit_lancamento(id):
    lanc = FuncionarioLancamento.query.get_or_404(id)
    # Garante que o funcionário pertence à carteira ativa
    get_funcionarios_query().filter_by(id=lanc.funcionario_id).first_or_404()
    
    if lanc.folha_id:
        flash('Este lançamento já foi processado e não pode ser editado.', 'danger')
        return redirect(url_for('funcionarios.lancamentos', id=lanc.funcionario_id))

    tipo = request.form.get('tipo')
    valor_str = request.form.get('valor', '0').replace('.', '').replace(',', '.')
    data_str = request.form.get('data', '')
    obs = request.form.get('observacao', '').strip() or None
    
    try:
        lanc.valor = Decimal(valor_str or '0')
        lanc.tipo = tipo
        if data_str:
            lanc.data = datetime.strptime(data_str, '%Y-%m-%d').date()
        lanc.observacao = obs
        db.session.commit()
        flash('Lançamento atualizado!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao atualizar: {str(e)}', 'danger')
        
    mes_sel = request.args.get('mes', date.today().month)
    ano_sel = request.args.get('ano', date.today().year)
    return redirect(url_for('funcionarios.lancamentos', id=lanc.funcionario_id, mes=mes_sel, ano=ano_sel))


@funcionarios_bp.route('/funcionarios/lancamentos/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
@log_action("Exclusão de Lançamento RH")
def delete_lancamento(id):
    lanc = FuncionarioLancamento.query.get_or_404(id)
    # Verifica que o funcionário pertence à carteira acessível
    get_funcionarios_query().filter_by(id=lanc.funcionario_id).first_or_404()
    func_id = lanc.funcionario_id
    mes_sel = request.args.get('mes', date.today().month)
    ano_sel = request.args.get('ano', date.today().year)
    db.session.delete(lanc)
    db.session.commit()
    flash('Lançamento removido.', 'success')
    return redirect(url_for('funcionarios.lancamentos', id=func_id, mes=mes_sel, ano=ano_sel))


# ─── FOLHA DE PAGAMENTO ───────────────────────────────────────────────────────

@funcionarios_bp.route('/funcionarios/folha')
@login_required
def folha():
    hoje = date.today()
    mes_sel = int(request.args.get('mes', hoje.month))
    ano_sel = int(request.args.get('ano', hoje.year))
    mes_ref = f'{ano_sel:04d}-{mes_sel:02d}'

    inicio = date(ano_sel, mes_sel, 1)
    fim = date(ano_sel, mes_sel, calendar.monthrange(ano_sel, mes_sel)[1])

    # Funcionários ativos da carteira ativa
    funcionarios_ativos = get_funcionarios_query(ativo=True).order_by(Funcionario.nome).all()

    dados_folha = []
    for func in funcionarios_ativos:
        folha_existente = FolhaPagamento.query.filter_by(
            funcionario_id=func.id, mes_referencia=mes_ref,
        ).first()

        if folha_existente:
            lances = FuncionarioLancamento.query.filter_by(folha_id=folha_existente.id).all()
            dados_folha.append({
                'func': func, 
                'folha': folha_existente, 
                'preview': False,
                'lances': lances
            })
        else:
            # Busca lançamentos pendentes (folha_id é NULL) até o final do mês selecionado
            pendentes = FuncionarioLancamento.query.filter(
                FuncionarioLancamento.funcionario_id == func.id,
                FuncionarioLancamento.folha_id == None,
                FuncionarioLancamento.data <= fim,
            ).all()
            
            adiantamentos = [l for l in pendentes if l.tipo == 'Adiantamento']
            descontos_extras = [l for l in pendentes if l.tipo == 'Desconto']

            valor_bruto = Decimal(str(func.salario_bruto))
            desc_inss = calcular_inss(valor_bruto, func.inss_percent)
            desc_adiant = sum(Decimal(str(l.valor)) for l in adiantamentos)
            desc_extras = sum(Decimal(str(l.valor)) for l in descontos_extras)
            liquido = valor_bruto - desc_inss - desc_adiant - desc_extras

            dados_folha.append({
                'func': func, 'folha': None, 'preview': True,
                'valor_bruto': valor_bruto, 'desconto_inss': desc_inss,
                'desconto_adiantamento': desc_adiant, 'outros_descontos': desc_extras,
                'salario_liquido': liquido,
                'lances': pendentes
            })

    total_bruto = sum(
        (d['folha'].valor_bruto if d['folha'] else d['valor_bruto']) for d in dados_folha
    )
    total_liquido = sum(
        (d['folha'].salario_liquido if d['folha'] else d['salario_liquido']) for d in dados_folha
    )
    total_inss = sum(
        (d['folha'].desconto_inss if d['folha'] else d['desconto_inss']) for d in dados_folha
    )
    total_pago = sum(
        (d['folha'].salario_liquido if d['folha'] and d['folha'].pago else Decimal('0'))
        for d in dados_folha
    )
    folha_fechada = any(d['folha'] is not None for d in dados_folha)

    meses_br = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

    return render_template(
        'funcionarios/folha.html',
        dados_folha=dados_folha,
        mes_sel=mes_sel, ano_sel=ano_sel, mes_ref=mes_ref,
        total_bruto=total_bruto, total_liquido=total_liquido, total_pago=total_pago,
        folha_fechada=folha_fechada,
        hoje=hoje.strftime('%Y-%m-%d'),
        meses_br=meses_br,
    )


@funcionarios_bp.route('/funcionarios/folha/fechar', methods=['POST'])
@login_required
@admin_required
@log_action("Fechamento de Folha de Pagamento")
def fechar_folha():
    mes_sel = int(request.form.get('mes', date.today().month))
    ano_sel = int(request.form.get('ano', date.today().year))
    mes_ref = f'{ano_sel:04d}-{mes_sel:02d}'

    inicio = date(ano_sel, mes_sel, 1)
    fim = date(ano_sel, mes_sel, calendar.monthrange(ano_sel, mes_sel)[1])

    # Somente funcionários da carteira ativa
    funcionarios_ativos = get_funcionarios_query(ativo=True).all()
    criados = 0
    atualizados = 0

    for func in funcionarios_ativos:
        folha_existente = FolhaPagamento.query.filter_by(funcionario_id=func.id, mes_referencia=mes_ref).first()
        
        if folha_existente and folha_existente.pago:
            continue

        # Busca o que já está vinculado ou o que ainda está pendente até a data fim
        existing_lances = []
        if folha_existente:
            existing_lances = FuncionarioLancamento.query.filter_by(folha_id=folha_existente.id).all()
            
        new_lances = FuncionarioLancamento.query.filter(
            FuncionarioLancamento.funcionario_id == func.id,
            FuncionarioLancamento.folha_id == None,
            FuncionarioLancamento.data <= fim
        ).all()
        
        all_lances = existing_lances + new_lances
        adiantamentos = [l for l in all_lances if l.tipo == 'Adiantamento']
        descontos_extras = [l for l in all_lances if l.tipo == 'Desconto']

        valor_bruto = Decimal(str(func.salario_bruto))
        desc_inss = calcular_inss(valor_bruto, func.inss_percent)
        desc_adiant = sum(Decimal(str(l.valor)) for l in adiantamentos)
        desc_extras = sum(Decimal(str(l.valor)) for l in descontos_extras)
        liquido = valor_bruto - desc_inss - desc_adiant - desc_extras

        if folha_existente:
            folha_existente.valor_bruto = valor_bruto
            folha_existente.desconto_inss = desc_inss
            folha_existente.desconto_adiantamento = desc_adiant
            folha_existente.outros_descontos = desc_extras
            folha_existente.salario_liquido = liquido
            folha_obj = folha_existente
            atualizados += 1
        else:
            nova_folha = FolhaPagamento(
                funcionario_id=func.id, mes_referencia=mes_ref,
                valor_bruto=valor_bruto, desconto_inss=desc_inss,
                desconto_adiantamento=desc_adiant, outros_descontos=desc_extras,
                salario_liquido=liquido, pago=False,
            )
            db.session.add(nova_folha)
            db.session.flush() # Para garantir que temos o ID
            folha_obj = nova_folha
            criados += 1
            
        # Vincula novos lançamentos à folha (os que já estavam vinculados permanecem)
        for l in new_lances:
            l.folha_id = folha_obj.id

    db.session.commit()
    if criados or atualizados:
        msg = f'Folha de {mes_ref} processada.'
        if criados: msg += f' {criados} novos.'
        if atualizados: msg += f' {atualizados} atualizados.'
        flash(msg, 'success')
    else:
        flash('A folha deste mês já está fechada e paga.', 'info')
    return redirect(url_for('funcionarios.folha', mes=mes_sel, ano=ano_sel))


@funcionarios_bp.route('/funcionarios/folha/reabrir', methods=['POST'])
@login_required
@admin_required
@log_action("Reabertura de Folha de Pagamento")
def reabrir_folha():
    mes_sel = int(request.form.get('mes', date.today().month))
    ano_sel = int(request.form.get('ano', date.today().year))
    mes_ref = f'{ano_sel:04d}-{mes_sel:02d}'

    # Somente funcionários da carteira ativa
    funcionarios_ativos = get_funcionarios_query(ativo=True).all()
    func_ids = [f.id for f in funcionarios_ativos]

    # Busca folhas que serão removidas
    folhas_reabrir = FolhaPagamento.query.filter(
        FolhaPagamento.mes_referencia == mes_ref,
        FolhaPagamento.funcionario_id.in_(func_ids),
        FolhaPagamento.pago == False
    ).all()
    
    removidos = 0
    for f_obj in folhas_reabrir:
        # Desvincula lançamentos (voltando-os para o estado pendente)
        FuncionarioLancamento.query.filter_by(folha_id=f_obj.id).update({'folha_id': None}, synchronize_session=False)
        db.session.delete(f_obj)
        removidos += 1

    db.session.commit()
    if removidos:
        flash(f'Folha de {mes_ref} reaberta! {removidos} registro(s) agora estão em modo rascunho.', 'success')
    else:
        flash('Não foram encontrados registros pendentes para reabrir. (Registros já pagos não podem ser reabertos automaticamente)', 'info')
    
    return redirect(url_for('funcionarios.folha', mes=mes_sel, ano=ano_sel))


@funcionarios_bp.route('/funcionarios/folha/<int:id>/pagar', methods=['POST'])
@login_required
@admin_required
@log_action("Pagamento de Salário")
def pagar_folha(id):
    folha_obj = FolhaPagamento.query.get_or_404(id)
    # Verifica que o funcionário pertence à carteira acessível
    get_funcionarios_query().filter_by(id=folha_obj.funcionario_id).first_or_404()

    mes_ref = folha_obj.mes_referencia
    ano_sel, mes_sel = mes_ref.split('-')

    if folha_obj.pago:
        flash('Esta folha já foi marcada como paga.', 'info')
        return redirect(url_for('funcionarios.folha', mes=mes_sel, ano=ano_sel))

    hoje = date.today()
    forma_pg = request.form.get('forma_pagamento', 'Transferência')
    
    folha_obj.pago = True
    folha_obj.data_pagamento = hoje
    folha_obj.forma_pagamento = forma_pg

    try:
        cat_func = Categoria.query.filter(
            Categoria.nome.ilike('%funcionário%')
        ).first() or Categoria.query.filter(
            Categoria.nome.ilike('%funcionario%')
        ).first()

        nome_func = folha_obj.funcionario.nome
        carteira_rel = folha_obj.funcionario.carteira_rel
        carteira_id = carteira_rel.id if carteira_rel else None
        carteira_nome = carteira_rel.nome if carteira_rel else 'Consolidada'

        # Busca transação existente para evitar duplicidade (ex: recorrente pendente)
        dia_u = calendar.monthrange(int(ano_sel), int(mes_sel))[1]
        inicio_m = date(int(ano_sel), int(mes_sel), 1)
        fim_m = date(int(ano_sel), int(mes_sel), dia_u)
        desc_busca = f'Salário – {nome_func}'
        
        trans_existente = Transacao.query.filter(
            Transacao.descricao == desc_busca,
            Transacao.data >= inicio_m,
            Transacao.data <= fim_m,
            Transacao.carteira_id == carteira_id,
            Transacao.removida == False
        ).first()

        if trans_existente:
            trans_existente.pago = True
            trans_existente.data = hoje
            trans_existente.valor = folha_obj.salario_liquido
            trans_existente.valor_pago = folha_obj.salario_liquido
            trans_existente.valor_previsto = 0
            folha_obj.transacao_id = trans_existente.id
        else:
            nova_transacao = Transacao(
                data=hoje,
                descricao=desc_busca,
                valor=folha_obj.salario_liquido,
                valor_previsto=0,
                valor_pago=folha_obj.salario_liquido,
                tipo='Despesa',
                categoria_id=cat_func.id if cat_func else None,
                carteira_id=carteira_id,
                carteira=carteira_nome,
                pago=True,
                fixa=False,
            )
            db.session.add(nova_transacao)
            db.session.flush()
            folha_obj.transacao_id = nova_transacao.id

        db.session.commit()
        flash(f'Salário de {nome_func} pago! Transação registrada na carteira.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao registrar pagamento: {str(e)}', 'danger')

    return redirect(url_for('funcionarios.folha', mes=mes_sel, ano=ano_sel))


@funcionarios_bp.route('/funcionarios/folha/<int:id>/desfazer_pagamento', methods=['POST'])
@login_required
@admin_required
@log_action("Estorno de Pagamento de Salário")
def desfazer_pagamento(id):
    folha_obj = FolhaPagamento.query.get_or_404(id)
    get_funcionarios_query().filter_by(id=folha_obj.funcionario_id).first_or_404()

    mes_ref = folha_obj.mes_referencia
    ano_sel, mes_sel = mes_ref.split('-')

    if not folha_obj.pago:
        flash('Esta folha ainda não foi paga.', 'info')
        return redirect(url_for('funcionarios.folha', mes=mes_sel, ano=ano_sel))

    if folha_obj.transacao_id:
        transacao = Transacao.query.get(folha_obj.transacao_id)
        if transacao:
            db.session.delete(transacao)
        folha_obj.transacao_id = None

    folha_obj.pago = False
    folha_obj.data_pagamento = None
    db.session.commit()
    flash(f'Pagamento de {folha_obj.funcionario.nome} desfeito.', 'warning')
    return redirect(url_for('funcionarios.folha', mes=mes_sel, ano=ano_sel))


@funcionarios_bp.route('/funcionarios/folha/relatorio')
@login_required
def relatorio_folha():
    hoje = date.today()
    mes_sel = int(request.args.get('mes', hoje.month))
    ano_sel = int(request.args.get('ano', hoje.year))
    mes_ref = f'{ano_sel:04d}-{mes_sel:02d}'
    c_ativa = get_carteira_ativa()

    inicio = date(ano_sel, mes_sel, 1)
    fim = date(ano_sel, mes_sel, calendar.monthrange(ano_sel, mes_sel)[1])

    funcionarios_ativos = get_funcionarios_query(ativo=True).order_by(Funcionario.nome).all()

    dados_folha = []
    for func in funcionarios_ativos:
        folha_existente = FolhaPagamento.query.filter_by(
            funcionario_id=func.id, mes_referencia=mes_ref,
        ).first()

        if folha_existente:
            # Pega lançamentos VINCULADOS a esta folha
            lances = FuncionarioLancamento.query.filter_by(folha_id=folha_existente.id).all()
            
            dados_folha.append({
                'func': func, 
                'folha': folha_existente, 
                'preview': False,
                'lancamentos_adiantamento': [l for l in lances if l.tipo == 'Adiantamento'],
                'lancamentos_desconto': [l for l in lances if l.tipo == 'Desconto']
            })
        else:
            # Preview: pega lançamentos PENDENTES até a data fim
            lances = FuncionarioLancamento.query.filter(
                FuncionarioLancamento.funcionario_id == func.id,
                FuncionarioLancamento.folha_id == None,
                FuncionarioLancamento.data <= fim,
            ).all()

            valor_bruto = Decimal(str(func.salario_bruto))
            desc_inss = calcular_inss(valor_bruto, func.inss_percent)
            desc_adiant = sum(Decimal(str(l.valor)) for l in lances if l.tipo == 'Adiantamento')
            desc_extras = sum(Decimal(str(l.valor)) for l in lances if l.tipo == 'Desconto')
            liquido = valor_bruto - desc_inss - desc_adiant - desc_extras

            dados_folha.append({
                'func': func, 'folha': None, 'preview': True,
                'valor_bruto': valor_bruto, 'desconto_inss': desc_inss,
                'desconto_adiantamento': desc_adiant, 'outros_descontos': desc_extras,
                'salario_liquido': liquido,
                'lancamentos_adiantamento': [l for l in lances if l.tipo == 'Adiantamento'],
                'lancamentos_desconto': [l for l in lances if l.tipo == 'Desconto']
            })

    total_bruto = sum((d['folha'].valor_bruto if d['folha'] else d['valor_bruto']) for d in dados_folha)
    total_liquido = sum((d['folha'].salario_liquido if d['folha'] else d['salario_liquido']) for d in dados_folha)
    
    meses_br = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

    return render_template(
        'funcionarios/relatorio_folha.html',
        dados_folha=dados_folha,
        mes_sel=mes_sel, ano_sel=ano_sel, 
        mes_ref=mes_ref, c_ativa=c_ativa,
        total_bruto=total_bruto, total_liquido=total_liquido,
        meses_br=meses_br, hoje=hoje
    )

