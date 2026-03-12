from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import login_required, current_user
from auth import admin_required, is_superadmin
from utils import get_authorized_query, log_action
from extensions import db
from models import Transacao, Categoria, ConfigFinanceiraFixa, Ativo, Dividendo, GastoCartao, Carteira
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
import calendar
import os
from werkzeug.utils import secure_filename
from card_parser import import_card_invoice
from collections import defaultdict
from sqlalchemy import case as sa_case
import pandas as pd

 
finance_bp = Blueprint('finance', __name__, template_folder='templates')
 
def get_current_wallet():
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

def get_authorized_query(model, c_ativa):
    """Retorna uma query filtrada pelas permissões do usuário e carteira ativa.
    
    SuperAdmin: acesso irrestrito a todos os dados.
    Admin: acesso às suas carteiras atribuídas (com escrita).
    Usuário: acesso somente leitura às suas carteiras atribuídas.
    """
    query = model.query
    
    # Se c_ativa for uma lista, tratamos como múltipla seleção
    is_multi = isinstance(c_ativa, list)
    
    # SuperAdmin tem acesso total — sem filtro de carteira
    if is_superadmin():
        if c_ativa == 'Consolidada':
            return query
        
        if is_multi:
            if hasattr(model, 'carteira_id'):
                ids = [c.id for c in Carteira.query.filter(Carteira.nome.in_(c_ativa)).all()]
                return query.filter(model.carteira_id.in_(ids))
            else:
                return query.filter(model.carteira.in_(c_ativa))
        else:
            c_obj = Carteira.query.filter_by(nome=c_ativa).first()
            if c_obj:
                if hasattr(model, 'carteira_id'):
                    return query.filter_by(carteira_id=c_obj.id)
                else:
                    return query.filter_by(carteira=c_ativa)
            return query.filter(False)
    
    # Admin e Usuário: filtrar pelas carteiras atribuídas
    accessible_wallets = current_user.carteiras
    wallet_ids = [c.id for c in accessible_wallets]
    wallet_nomes = [c.nome for c in accessible_wallets]
    
    if not wallet_ids:
        return query.filter(False)
        
    if c_ativa == 'Consolidada':
        if hasattr(model, 'carteira_id'):
            return query.filter(model.carteira_id.in_(wallet_ids))
        else:
            return query.filter(model.carteira.in_(wallet_nomes))
    
    if is_multi:
        # Pega apenas as carteiras que o usuário realmente tem acesso
        final_nomes = [n for n in c_ativa if n in wallet_nomes]
        if not final_nomes:
            return query.filter(False)
        if hasattr(model, 'carteira_id'):
            final_ids = [c.id for c in accessible_wallets if c.nome in final_nomes]
            return query.filter(model.carteira_id.in_(final_ids))
        else:
            return query.filter(model.carteira.in_(final_nomes))
    else:
        # Carteira específica única
        c_obj = Carteira.query.filter_by(nome=c_ativa).first()
        if c_obj and c_obj in accessible_wallets:
            if hasattr(model, 'carteira_id'):
                return query.filter_by(carteira_id=c_obj.id)
            else:
                return query.filter_by(carteira=c_ativa)
        return query.filter(False)

def gerar_recorrentes(mes=None, ano=None, c_ativa='Consolidada'):
    """Gera as receitas e despesas fixas para o mês/ano especificado."""
    hoje = date.today()
    alvo_mes = mes or hoje.month
    alvo_ano = ano or hoje.year
    
    # Determina se é um mês no passado
    is_passado = (alvo_ano < hoje.year) or (alvo_ano == hoje.year and alvo_mes < hoje.month)
    if is_passado:
        return
        
    # Determina se é um mês estritamente no futuro (depois do mês corrente)
    is_futuro = (alvo_ano > hoje.year) or (alvo_ano == hoje.year and alvo_mes > hoje.month)
    
    inicio_mes = date(alvo_ano, alvo_mes, 1)
    fim_mes = date(alvo_ano, alvo_mes, calendar.monthrange(alvo_ano, alvo_mes)[1])
    
    config_fixas = get_authorized_query(ConfigFinanceiraFixa, c_ativa).filter_by(ativo=True).all()
    desc_ativas = {cfg.descricao: cfg for cfg in config_fixas}
    
    # Se for mês FUTURO, sincroniza transações recorrentes existentes que ainda não foram pagas
    if is_futuro:
        existentes_fixas = get_authorized_query(Transacao, c_ativa).filter(
            Transacao.fixa == True,
            Transacao.data >= inicio_mes,
            Transacao.data <= fim_mes
        ).all()
        
        for t in existentes_fixas:
            if t.descricao in desc_ativas:
                # Sincroniza dados da configuração se a transação ainda não estiver paga/concluída
                if not t.pago:
                    cfg = desc_ativas[t.descricao]
                    t.valor_previsto = cfg.valor_estimado if cfg.tipo == 'Despesa' else 0
                    t.valor_pago = cfg.valor_estimado if cfg.tipo == 'Receita' else 0
                    t.tipo = cfg.tipo
                    t.categoria_id = cfg.categoria_id
                    t.carteira = cfg.carteira
                    t.carteira_id = cfg.carteira_id
                    t.posicao = cfg.posicao
                    # t.removida = False # Descomente se quiser que reapareça automaticamente ao reativar config
            else:
                # Se a configuração foi desativada ou removida, "esconde" a transação futura não paga
                if not t.pago and not t.removida:
                    t.removida = True

    # Gera novas transações para configurações que ainda não existem no mês (independente de ser futuro ou não)
    for cfg in config_fixas:
        # Verifica existência ampla (incluindo manuais com mesma descrição ou removidas)
        exists = get_authorized_query(Transacao, c_ativa).filter(
            Transacao.descricao == cfg.descricao,
            Transacao.data >= inicio_mes,
            Transacao.data <= fim_mes
        ).first()
        
        if not exists:
            dia = min(cfg.dia_vencimento, calendar.monthrange(alvo_ano, alvo_mes)[1])
            nova = Transacao(
                data=date(alvo_ano, alvo_mes, dia),
                descricao=cfg.descricao,
                valor_previsto=cfg.valor_estimado if cfg.tipo == 'Despesa' else 0,
                valor_pago=cfg.valor_estimado if cfg.tipo == 'Receita' else 0,
                tipo=cfg.tipo,
                categoria_id=cfg.categoria_id,
                carteira=cfg.carteira,
                carteira_id=cfg.carteira_id,
                fixa=True,
                pago=False if cfg.tipo == 'Despesa' else True,
                dia_vencimento=dia,
                posicao=cfg.posicao
            )
            db.session.add(nova)
    db.session.commit()

@finance_bp.route('/financas')
@login_required
def dashboard():
    hoje = date.today()
    mes_selecionado = int(request.args.get('mes', hoje.month))
    ano_selecionado = int(request.args.get('ano', hoje.year))
    c_ativa = get_current_wallet()
    gerar_recorrentes(mes_selecionado, ano_selecionado, c_ativa)
    
    inicio_mes = date(ano_selecionado, mes_selecionado, 1)
    fim_mes = date(ano_selecionado, mes_selecionado, calendar.monthrange(ano_selecionado, mes_selecionado)[1])
    
    # Filtra transações pelo período e exclui as que foram "removidas" (soft delete) usando query autorizada
    query = get_authorized_query(Transacao, c_ativa).filter(
        Transacao.data >= inicio_mes, 
        Transacao.data <= fim_mes,
        Transacao.removida == False
    )
    
    ordem_posicao = sa_case((Transacao.posicao == 0, 1), else_=0)
    transacoes = query.order_by(ordem_posicao, Transacao.posicao.asc(), Transacao.data.asc(), Transacao.id.asc()).all()
    categorias = Categoria.query.all()
    
    receitas_list = [t for t in transacoes if t.tipo == 'Receita']
    despesas_list = [t for t in transacoes if t.tipo == 'Despesa']
    
    receitas_num = sum(Decimal(t.valor_pago if t.valor_pago > 0 else t.valor) for t in receitas_list)
    despesas_pagas = sum(Decimal(t.valor_pago) for t in despesas_list)
    despesas_total_previsto = sum(Decimal(t.valor_previsto) for t in despesas_list)
    despesas_pendentes = sum(Decimal(t.valor_previsto) for t in despesas_list if t.valor_pago == 0)
    
    # Busca proventos do mês
    # Filtra dividendos do mês usando query autorizada
    query_divs = get_authorized_query(Dividendo, c_ativa).filter(
        Dividendo.data_recebimento >= inicio_mes,
        Dividendo.data_recebimento <= fim_mes
    )
    proventos_mes = query_divs.all()
    proventos_total = sum(Decimal(str(p.valor_total)) for p in proventos_mes)

    # Mês traduzido
    meses_br = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    mes_str = f"{meses_br[mes_selecionado-1]} / {ano_selecionado}"

    return render_template('finance/dashboard.html', 
                           receitas_list=receitas_list,
                           despesas_list=despesas_list,
                           categorias=categorias,
                           receitas=receitas_num,
                           despesas_pagas=despesas_pagas,
                           despesas_total_previsto=despesas_total_previsto,
                           despesas_pendentes=despesas_pendentes,
                           proventos_total=proventos_total,
                           saldo=receitas_num + proventos_total - despesas_pagas,
                           hoje=hoje.strftime('%Y-%m-%d'),
                           mes_atual=mes_str,
                           mes_sel=mes_selecionado,
                           ano_sel=ano_selecionado,
                           meses_br=meses_br)

@finance_bp.route('/financas/transacao/update_valor', methods=['POST'])
@login_required
@admin_required
@log_action("Atualização de Transação")
def update_valor():
    t_id = request.form.get('id')
    campo = request.form.get('campo') # 'valor_previsto', 'valor_pago', 'data' ou 'descricao'
    valor = request.form.get('valor')
    
    t = Transacao.query.get_or_404(t_id)
    
    if campo == 'data':
        t.data = datetime.strptime(valor, '%Y-%m-%d').date()
        t.dia_vencimento = t.data.day
    elif campo == 'descricao':
        t.descricao = valor
    elif campo == 'posicao':
        try:
            t.posicao = int(valor or 0)
        except ValueError:
            t.posicao = 0
    else:
        # Limpeza robusta: remove "R$", espaços e pontos (milhar), troca vírgula por ponto
        valor_clean = valor.replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.')
        try:
            val_decimal = Decimal(valor_clean or 0)
        except (InvalidOperation, ValueError):
            val_decimal = Decimal(0)

        setattr(t, campo, val_decimal)
        
        # Se pagou, marca como pago e atualiza valor total real
        if campo == 'valor_pago' and val_decimal > 0:
            t.pago = True
            t.valor = val_decimal
            t.valor_previsto = 0
        elif campo == 'valor_pago' and val_decimal == 0:
            t.pago = False
            t.valor = 0

    # Captura mês e ano para redirecionar de volta ao mesmo período
    mes_sel = request.form.get('mes_sel')
    ano_sel = request.form.get('ano_sel')

    db.session.commit()
    return redirect(url_for('finance.dashboard', mes=mes_sel, ano=ano_sel))

@finance_bp.route('/financas/transacao/add', methods=['POST'])
@login_required
@admin_required
@log_action("Adição de Transação")
def add_transacao():
    data_str = request.form.get('data')
    descricao = request.form.get('descricao')
    valor = request.form.get('valor').replace(',', '.')
    tipo = request.form.get('tipo')
    categoria_id = request.form.get('categoria_id')
    carteira = session.get('carteira_ativa', 'Consolidada')
    c_obj = Carteira.query.filter_by(nome=carteira).first()
    c_id = c_obj.id if c_obj else None
    
    posicao = int(request.form.get('posicao', 0))
    
    val_num = Decimal(valor or 0)
    nova_transacao = Transacao(
        data=datetime.strptime(data_str, '%Y-%m-%d').date(),
        descricao=descricao,
        valor=val_num,
        valor_previsto=val_num if tipo == 'Despesa' else 0,
        valor_pago=val_num if tipo == 'Receita' else 0,
        tipo=tipo,
        categoria_id=categoria_id if categoria_id else None,
        carteira=carteira,
        carteira_id=c_id,
        pago=True if tipo == 'Receita' else False,
        dia_vencimento=datetime.strptime(data_str, '%Y-%m-%d').date().day,
        posicao=posicao
    )
    
    # Captura mês e ano para redirecionar de volta ao mesmo período
    mes_sel = request.form.get('mes_sel')
    ano_sel = request.form.get('ano_sel')

    db.session.add(nova_transacao)
    db.session.commit()
    flash('Transação adicionada!', 'success')
    return redirect(url_for('finance.dashboard', mes=mes_sel, ano=ano_sel))

@finance_bp.route('/financas/transacao/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
@log_action("Exclusão de Transação")
def delete_transacao(id):
    t = Transacao.query.get_or_404(id)
    
    # Captura mês e ano para redirecionar de volta ao mesmo período
    mes_sel = request.args.get('mes')
    ano_sel = request.args.get('ano')
    
    # Em vez de deletar fisicamente, marcamos como removida (Soft Delete)
    # Isso impede que o gerar_recorrentes a recrie automaticamente.
    t.removida = True
    
    db.session.commit()
    flash('Removido!', 'success')
    return redirect(url_for('finance.dashboard', mes=mes_sel, ano=ano_sel))

@finance_bp.route('/financas/relatorio/anual')
@login_required
def relatorio_anual():
    ano = int(request.args.get('ano', date.today().year))
    filtro = request.args.get('filtro', 'tudo')  # tudo, receitas, despesas, aportes
    c_ativa = get_current_wallet()
    # Para consistência com o template que espera c_list
    c_list = request.args.getlist('carteira')
    if not c_list and c_ativa != 'Consolidada':
        c_list = [c_ativa] if not isinstance(c_ativa, list) else c_ativa
    
    # Busca todas as transações do ano que não foram removidas usando query autorizada
    query = get_authorized_query(Transacao, c_ativa).filter(
        db.extract('year', Transacao.data) == ano,
        Transacao.removida == False
    )
    
    ordem_posicao = sa_case((Transacao.posicao == 0, 1), else_=0)
    transacoes = query.order_by(ordem_posicao, Transacao.posicao.asc(), Transacao.data.asc(), Transacao.id.asc()).all()
    
    # Busca todos os lotes de ativos (aportes) do ano para a seção INVESTIMENTOS usando query autorizada
    query_ativos = get_authorized_query(Ativo, c_ativa).filter(db.extract('year', Ativo.data_compra) == ano)
    lotes_ano = query_ativos.all()

    # Busca todos os proventos (Dividendos) do ano para a seção RECEITAS usando query autorizada
    query_divs = get_authorized_query(Dividendo, c_ativa).filter(db.extract('year', Dividendo.data_recebimento) == ano)
    proventos_ano = query_divs.all()
    
    # Estruturas para o relatório
    receitas_por_desc = defaultdict(lambda: defaultdict(Decimal))
    despesas_por_desc = defaultdict(lambda: defaultdict(Decimal))
    totais_receita = defaultdict(Decimal)
    totais_despesa = defaultdict(Decimal)
    totais_investimento = defaultdict(Decimal)
    
    # Agrega aportes (Investimentos) via modelo Ativo
    investimentos_por_desc = defaultdict(lambda: defaultdict(Decimal))
    for l in lotes_ano:
        mes_v = l.data_compra.month
        valor_aporte = Decimal(str(l.quantidade)) * Decimal(str(l.preco_compra))
        investimentos_por_desc[l.ticker][mes_v] += valor_aporte
        totais_investimento[mes_v] += valor_aporte

    # Agrega proventos (Mercado Financeiro) como Receita na categoria "Investimentos"
    for p in proventos_ano:
        mes_p = p.data_recebimento.month
        val_p = Decimal(str(p.valor_total))
        receitas_por_desc["Proventos Recebidos"][mes_p] += val_p
        totais_receita[mes_p] += val_p

    for t in transacoes:
        mes = t.data.month
        # Limpa descrição para evitar duplicados por espaços extras
        desc = t.descricao.strip() if t.descricao else "Sem Descrição"
        
        # Normaliza faturas de cartão para agrupar por nome do cartão (remove o sufixo de data)
        if desc.startswith("Fatura Cartão") and " - 202" in desc:
            desc = desc.split(" - 202")[0]
        
        if t.tipo == 'Receita':
            val = Decimal(t.valor_pago if t.valor_pago > 0 else t.valor)
            receitas_por_desc[desc][mes] += val
            totais_receita[mes] += val
        else:
            # Não somamos categoria 8 aqui pois agora pegamos do modelo Ativo diretamente
            if t.categoria_id != 8:
                # Mudança para somar o PAGO no relatório histórico, conforme feedback
                val_pago = Decimal(t.valor_pago or 0)
                despesas_por_desc[desc][mes] += val_pago
                totais_despesa[mes] += val_pago
                
    # Ordenar receitas por volume total anual e FILTRAR linhas zeradas
    descricoes_receita = sorted(
        [d for d in receitas_por_desc.keys() if sum(receitas_por_desc[d].values()) > 0], 
        key=lambda d: sum(receitas_por_desc[d].values()), 
        reverse=True
    )

    # Obter descrições de despesas recorrentes para ordenação (em maiúsculo para matching robusto)
    descricoes_recorrentes = {cfg.descricao.upper() for cfg in ConfigFinanceiraFixa.query.filter_by(tipo='Despesa').all()}
    
    def is_recorrente(desc):
        d_upper = desc.strip().upper()
        if d_upper in descricoes_recorrentes:
            return True
            
        # Caso especial para Faturas de Cartão - matching por palavras-chave
        if d_upper.startswith("FATURA CARTÃO"):
            # Remove o "FATURA" e quebra em palavras (ex: "CARTÃO", "XP")
            words = d_upper.replace("FATURA ", "").split()
            for rec in descricoes_recorrentes:
                # Se todas as palavras (CARTÃO + NOME) estiverem na descrição da config
                if all(w in rec for w in words):
                    return True
        
        # Fallback: se a descrição da config estiver contida na descrição da transação
        for rec in descricoes_recorrentes:
            if rec in d_upper:
                return True
                
        return False

    # Separar despesas em recorrentes e outras
    despesas_rec = sorted([d for d in despesas_por_desc.keys() if is_recorrente(d) and sum(despesas_por_desc[d].values()) > 0])
    despesas_outras = sorted([d for d in despesas_por_desc.keys() if not is_recorrente(d) and sum(despesas_por_desc[d].values()) > 0])
    descricoes_despesa = despesas_rec + despesas_outras
    
    # Ordenar ativos de investimento em ordem alfabética
    ativos_investimento = sorted([a for a in investimentos_por_desc.keys() if sum(investimentos_por_desc[a].values()) > 0])

    meses_nomes = ["JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO", "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"]
    
    # Preparar dados para o template
    if is_superadmin():
        todas_carteiras = Carteira.query.order_by(Carteira.nome).all()
    else:
        todas_carteiras = current_user.carteiras

    # String para exibir no relatório
    if isinstance(c_ativa, list):
        carteira_exibicao = ", ".join(c_ativa)
    else:
        carteira_exibicao = c_ativa

    return render_template('finance/report_annual.html',
                           ano=ano,
                           filtro=filtro,
                           meses_nomes=meses_nomes,
                           receitas_por_desc=receitas_por_desc,
                           despesas_por_desc=despesas_por_desc,
                           investimentos_por_desc=investimentos_por_desc,
                           descricoes_receita=descricoes_receita,
                           descricoes_despesa=descricoes_despesa,
                           ativos_investimento=ativos_investimento,
                           totais_receita=totais_receita,
                           totais_despesa=totais_despesa,
                           totais_investimento=totais_investimento,
                           carteira_atual=carteira_exibicao,
                           carteiras_selecionadas=c_list if c_list else ([c_ativa] if c_ativa != 'Consolidada' else []),
                           todas_carteiras=todas_carteiras,
                           hoje_full=datetime.now().strftime('%d/%m/%Y %H:%M'))

@finance_bp.route('/financas/relatorio/mensal')
@login_required
def relatorio_mensal():
    hoje = date.today()
    mes_sel = int(request.args.get('mes', hoje.month))
    ano_sel = int(request.args.get('ano', hoje.year))
    filtro = request.args.get('filtro', 'tudo') # tudo, receitas, despesas, aportes
    c_ativa = get_current_wallet()
    # Para consistência com o template que espera c_list
    c_list = request.args.getlist('carteira')
    if not c_list and c_ativa != 'Consolidada':
        c_list = [c_ativa] if not isinstance(c_ativa, list) else c_ativa
    
    inicio_mes = date(ano_sel, mes_sel, 1)
    fim_mes = date(ano_sel, mes_sel, calendar.monthrange(ano_sel, mes_sel)[1])
    
    # 1. Busca Transações (Receitas e Despesas)
    query_trans = get_authorized_query(Transacao, c_ativa).filter(
        Transacao.data >= inicio_mes,
        Transacao.data <= fim_mes,
        Transacao.removida == False
    )
    ordem_posicao = sa_case((Transacao.posicao == 0, 1), else_=0)
    transacoes = query_trans.order_by(ordem_posicao, Transacao.posicao.asc(), Transacao.data.asc(), Transacao.id.asc()).all()
    
    receitas_list = [t for t in transacoes if t.tipo == 'Receita']
    despesas_list = [t for t in transacoes if t.tipo == 'Despesa']
    
    # 2. Busca Proventos (Receita Financeira)
    query_divs = get_authorized_query(Dividendo, c_ativa).filter(
        Dividendo.data_recebimento >= inicio_mes,
        Dividendo.data_recebimento <= fim_mes
    )
    proventos_list = query_divs.order_by(Dividendo.data_recebimento.asc()).all()
    
    # 3. Busca Aportes (Investimentos)
    query_ativos = get_authorized_query(Ativo, c_ativa).filter(
        Ativo.data_compra >= inicio_mes,
        Ativo.data_compra <= fim_mes
    )
    aportes_list = query_ativos.order_by(Ativo.data_compra.asc()).all()
    
    # Totais
    total_receitas = sum(Decimal(t.valor_pago if t.valor_pago > 0 else t.valor) for t in receitas_list)
    total_proventos = sum(Decimal(str(p.valor_total)) for p in proventos_list)
    total_despesas_prev = sum(Decimal(t.valor_previsto) for t in despesas_list)
    total_despesas_pago = sum(Decimal(t.valor_pago) for t in despesas_list)
    total_aportes = sum(Decimal(str(a.quantidade)) * Decimal(str(a.preco_compra)) for a in aportes_list)
    
    meses_br = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    
    # Preparar dados para o template
    if is_superadmin():
        todas_carteiras = Carteira.query.order_by(Carteira.nome).all()
    else:
        todas_carteiras = current_user.carteiras

    # String para exibir no relatório
    if isinstance(c_ativa, list):
        carteira_exibicao = ", ".join(c_ativa)
    else:
        carteira_exibicao = c_ativa

    return render_template('finance/report_monthly.html',
                           mes_sel=mes_sel,
                           ano_sel=ano_sel,
                           filtro=filtro,
                           receitas_list=receitas_list,
                           despesas_list=despesas_list,
                           proventos_list=proventos_list,
                           aportes_list=aportes_list,
                           total_receitas=total_receitas,
                           total_proventos=total_proventos,
                           total_despesas_prev=total_despesas_prev,
                           total_despesas_pago=total_despesas_pago,
                           total_aportes=total_aportes,
                           meses_br=meses_br,
                           carteira_atual=carteira_exibicao,
                           carteiras_selecionadas=c_list if c_list else ([c_ativa] if c_ativa != 'Consolidada' else []),
                           todas_carteiras=todas_carteiras,
                           hoje_full=datetime.now().strftime('%d/%m/%Y %H:%M'))

@finance_bp.route('/financas/config_fixas')
@login_required
def config_fixas():
    c_ativa = get_current_wallet()
    
    # Busca todas as configurações fixas da carteira ativa usando query autorizada
    query = get_authorized_query(ConfigFinanceiraFixa, c_ativa)
    
    config_list = query.order_by(ConfigFinanceiraFixa.tipo.desc(), ConfigFinanceiraFixa.posicao.asc(), ConfigFinanceiraFixa.dia_vencimento.asc()).all()
    categorias = Categoria.query.all()
    
    return render_template('finance/config_fixas.html', 
                           config_list=config_list, 
                           categorias=categorias)

@finance_bp.route('/financas/config_fixas/add', methods=['POST'])
@login_required
@admin_required
@log_action("Adição de Configuração Fixa")
def add_config_fixa():
    descricao = request.form.get('descricao')
    valor_estimado = request.form.get('valor_estimado').replace(',', '.')
    dia_vencimento = int(request.form.get('dia_vencimento', 1))
    tipo = request.form.get('tipo', 'Despesa')
    categoria_id = request.form.get('categoria_id')
    posicao = int(request.form.get('posicao', 0))
    c_ativa = session.get('carteira_ativa', 'Consolidada')
    c_obj = Carteira.query.filter_by(nome=c_ativa).first()
    
    nova = ConfigFinanceiraFixa(
        descricao=descricao,
        valor_estimado=Decimal(valor_estimado or 0),
        dia_vencimento=dia_vencimento,
        tipo=tipo,
        categoria_id=categoria_id if categoria_id else None,
        carteira=c_ativa,
        carteira_id=c_obj.id if c_obj else None,
        ativo=True,
        posicao=posicao
    )
    
    db.session.add(nova)
    db.session.commit()
    flash('Configuração recorrente adicionada!', 'success')
    return redirect(url_for('finance.config_fixas'))

@finance_bp.route('/financas/config_fixas/update', methods=['POST'])
@login_required
@admin_required
@log_action("Atualização de Configuração Fixa")
def update_config_fixa():
    cfg_id = request.form.get('id')
    campo = request.form.get('campo')
    valor = request.form.get('valor')
    
    cfg = ConfigFinanceiraFixa.query.get_or_404(cfg_id)
    
    if campo == 'valor_estimado':
        valor_clean = valor.replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.')
        try:
            val_decimal = Decimal(valor_clean or 0)
        except (InvalidOperation, ValueError):
            val_decimal = Decimal(0)
        cfg.valor_estimado = val_decimal
    elif campo == 'dia_vencimento':
        cfg.dia_vencimento = int(valor or 1)
    elif campo == 'descricao':
        cfg.descricao = valor
    elif campo == 'tipo':
        cfg.tipo = valor
    elif campo == 'categoria_id':
        cfg.categoria_id = int(valor) if valor else None
    elif campo == 'ativo':
        cfg.ativo = (valor == 'true')
    elif campo == 'posicao':
        cfg.posicao = int(valor or 0)
    
    db.session.commit()
    return redirect(url_for('finance.config_fixas'))

@finance_bp.route('/financas/config_fixas/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
@log_action("Exclusão de Configuração Fixa")
def delete_config_fixa(id):
    cfg = ConfigFinanceiraFixa.query.get_or_404(id)
    db.session.delete(cfg)
    db.session.commit()
    flash('Configuração removida!', 'success')
    return redirect(url_for('finance.config_fixas'))
@finance_bp.route('/financas/categorias')
@login_required
def categorias():
    # Admin vê globais + as de suas carteiras
    if is_superadmin():
        categorias_all = Categoria.query.order_by(Categoria.tipo.asc(), Categoria.nome.asc()).all()
    else:
        wallet_ids = [c.id for c in current_user.carteiras]
        categorias_all = Categoria.query.filter(
            (Categoria.carteira_id.is_(None)) | (Categoria.carteira_id.in_(wallet_ids))
        ).order_by(Categoria.tipo.asc(), Categoria.nome.asc()).all()
        
    return render_template('finance/categorias.html', categorias=categorias_all)

@finance_bp.route('/financas/categorias/add', methods=['POST'])
@login_required
@admin_required
@log_action("Adição de Categoria")
def add_categoria():
    nome = request.form.get('nome')
    tipo = request.form.get('tipo', 'Despesa')
    icone = request.form.get('icone', 'bi-tag')
    
    if not icone.startswith('bi-'):
        icone = 'bi-tag'
    
    try:
        nova = Categoria(nome=nome, tipo=tipo, icone=icone)
        
        # Se for Admin, vincula a uma carteira que o usuário possui
        if not is_superadmin():
            c_ativa = session.get('carteira_ativa', 'Consolidada')
            c_obj = Carteira.query.filter_by(nome=c_ativa).first()
            
            # Se estiver em 'Consolidada' ou em uma carteira que não possui, usa a primeira disponível
            if c_ativa == 'Consolidada' or not c_obj or c_obj not in current_user.carteiras:
                if current_user.carteiras:
                    nova.carteira_id = current_user.carteiras[0].id
            else:
                nova.carteira_id = c_obj.id

        db.session.add(nova)
        db.session.commit()
        flash('Categoria adicionada com sucesso!', 'success')
    except Exception:
        db.session.rollback()
        flash('Erro ao adicionar categoria: Talvez o nome já exista.', 'danger')
        
    return redirect(url_for('finance.categorias'))

@finance_bp.route('/financas/categorias/update', methods=['POST'])
@login_required
@admin_required
@log_action("Atualização de Categoria")
def update_categoria():
    cat_id = request.form.get('id')
    campo = request.form.get('campo')
    valor = request.form.get('valor')
    
    cat = Categoria.query.get_or_404(cat_id)
    
    # Verifica permissão
    if cat.carteira_id is None:
        if not is_superadmin():
            flash("Apenas SuperAdmins podem alterar categorias globais.", "danger")
            return redirect(url_for('finance.categorias'))
    elif not is_superadmin() and cat.carteira_id not in [c.id for c in current_user.carteiras]:
        flash("Você não tem permissão para alterar esta categoria.", "danger")
        return redirect(url_for('finance.categorias'))

    try:
        if campo == 'nome':
            cat.nome = valor
        elif campo == 'tipo':
            cat.tipo = valor
        elif campo == 'icone':
            cat.icone = valor if valor.startswith('bi-') else 'bi-tag'
            
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash('Erro ao atualizar categoria.', 'danger')
        
    return redirect(url_for('finance.categorias'))

@finance_bp.route('/financas/categorias/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
@log_action("Exclusão de Categoria")
def delete_categoria(id):
    cat = Categoria.query.get_or_404(id)
    
    # Verifica permissão
    if cat.carteira_id is None:
        if not is_superadmin():
            flash("Apenas SuperAdmins podem remover categorias globais.", "danger")
            return redirect(url_for('finance.categorias'))
    elif not is_superadmin() and cat.carteira_id not in [c.id for c in current_user.carteiras]:
        flash("Você não tem permissão para remover esta categoria.", "danger")
        return redirect(url_for('finance.categorias'))

    try:
        db.session.delete(cat)
        db.session.commit()
        flash('Categoria removida!', 'success')
    except Exception:
        db.session.rollback()
        flash('Não é possível remover categoria em uso.', 'warning')
        
    return redirect(url_for('finance.categorias'))

@finance_bp.route('/financas/cartao/import', methods=['POST'])
@login_required
@admin_required
@log_action("Importação de Fatura de Cartão")
def import_cartao():
    if 'file' not in request.files:
        flash('Nenhum arquivo enviado', 'danger')
        return redirect(url_for('finance.dashboard'))
    
    file = request.files['file']
    if file.filename == '':
        flash('Nenhum arquivo selecionado', 'danger')
        return redirect(url_for('finance.dashboard'))
    
    if file:
        filename = secure_filename(file.filename)
        # Create temp folder if not exists
        temp_dir = os.path.join('/tmp', 'uploads')
        os.makedirs(temp_dir, exist_ok=True)
        filepath = os.path.join(temp_dir, filename)
        file.save(filepath)
        
        try:
            success, message = import_card_invoice(filepath)
            if success:
                flash(message, 'success')
            else:
                flash(message, 'danger')
        except Exception as e:
            flash(f'Erro ao processar PDF: {str(e)}', 'danger')
        finally:
            if os.path.exists(filepath):
                os.remove(filepath)
                
    return redirect(url_for('finance.dashboard'))

@finance_bp.route('/financas/despesas/import', methods=['POST'])
@login_required
@admin_required
def import_despesas():
    """Importa transações de um arquivo Excel (.xlsx) para a tabela transacoes.
    
    Colunas esperadas no Excel:
    - DESCRIÇÃO (ou DESCRICAO): texto da transação
    - valor_pago (ou VALOR_PAGO / VALOR PAGO): valor pago
    - DATA PAGAMENTO (ou DATA): data no formato DD/MM/YY ou DD/MM/YYYY
    - TIPO: 'Despesa' ou 'Receita'
    - Carteira: nome da carteira (opcional; usa a sessão como fallback)
    """
    if 'arquivo' not in request.files:
        flash('Nenhum arquivo enviado', 'danger')
        return redirect(url_for('finance.dashboard'))

    file = request.files['arquivo']
    if file.filename == '':
        flash('Nenhum arquivo selecionado', 'danger')
        return redirect(url_for('finance.dashboard'))

    filename_lower = file.filename.lower()
    if not filename_lower.endswith('.xlsx'):
        flash('Apenas arquivos .xlsx são aceitos nessa importação', 'danger')
        return redirect(url_for('finance.dashboard'))

    try:
        df = pd.read_excel(file, header=0)
        # Normaliza nomes de colunas: strip + uppercase
        df.columns = [str(c).strip() for c in df.columns]

        # Mapeia colunas para nomes canônicos (case-insensitive / acento-tolerante)
        col_map = {}
        for col in df.columns:
            col_upper = col.upper().replace(' ', '_').replace('-', '_')
            if col_upper.startswith('DESCRI') or col_upper == 'DESCRI_O':
                col_map['descricao'] = col
            elif col_upper.startswith('VALOR') or col_upper == 'VALOR_PAGO':
                col_map['valor_pago'] = col
            elif col_upper.startswith('DATA'):
                col_map['data'] = col
            elif col_upper == 'TIPO':
                col_map['tipo'] = col
            elif col_upper == 'CARTEIRA':
                col_map['carteira'] = col
            elif col_upper == 'CATEGORIA':
                col_map['categoria'] = col

        # Fallback por posição (caso o cabeçalho não seja detectado)
        cols_list = list(df.columns)
        if len(cols_list) >= 5:
            if 'descricao' not in col_map: col_map['descricao'] = cols_list[0]
            if 'valor_pago' not in col_map: col_map['valor_pago'] = cols_list[1]
            if 'data'      not in col_map: col_map['data']      = cols_list[2]
            if 'tipo'      not in col_map: col_map['tipo']      = cols_list[3]
            if 'carteira'  not in col_map: col_map['carteira']  = cols_list[4]
            if len(cols_list) >= 6:
                if 'categoria' not in col_map: col_map['categoria'] = cols_list[5]

        if 'descricao' not in col_map or 'data' not in col_map:
            flash('Arquivo inválido: não foi possível identificar as colunas DESCRIÇÃO e DATA.', 'danger')
            return redirect(url_for('finance.dashboard'))

        registros = []
        erros = 0

        for _, row in df.iterrows():
            try:
                descricao = str(row.get(col_map['descricao'], '')).strip()
                if not descricao or descricao.upper() in ('NAN', 'NONE', ''):
                    continue

                # Converte data
                data_val = row.get(col_map['data'])
                if pd.isna(data_val) or str(data_val).strip() == '':
                    continue
                if isinstance(data_val, datetime):
                    data_obj = data_val.date()
                else:
                    data_str = str(data_val).strip()
                    for fmt in ('%d/%m/%y', '%d/%m/%Y', '%Y-%m-%d'):
                        try:
                            data_obj = datetime.strptime(data_str, fmt).date()
                            break
                        except ValueError:
                            continue
                    else:
                        data_obj = pd.to_datetime(data_str, dayfirst=True).date()

                # Converte valor
                valor_raw = Decimal('0')
                if 'valor_pago' in col_map:
                    val_raw = row.get(col_map['valor_pago'], 0)
                    if pd.notna(val_raw):
                        if isinstance(val_raw, (int, float)):
                            valor_raw = Decimal(str(val_raw))
                        else:
                            val_str = str(val_raw).strip().replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.')
                            try:
                                valor_raw = Decimal(val_str)
                            except Exception:
                                valor_raw = Decimal('0')

                # Tipo da transação
                tipo = 'Despesa'
                if 'tipo' in col_map:
                    tipo_val = str(row.get(col_map['tipo'], 'Despesa')).strip()
                    if tipo_val in ('Receita', 'Despesa'):
                        tipo = tipo_val

                # Carteira (nome como string — resolve no salvar)
                carteira_nome = ''
                if 'carteira' in col_map:
                    cart_val = str(row.get(col_map['carteira'], '')).strip()
                    if cart_val and cart_val.upper() not in ('NAN', 'NONE', ''):
                        carteira_nome = cart_val

                # Categoria (nome como string — resolve no salvar)
                categoria_nome = ''
                if 'categoria' in col_map:
                    cat_val = str(row.get(col_map['categoria'], '')).strip()
                    if cat_val and cat_val.upper() not in ('NAN', 'NONE', ''):
                        categoria_nome = cat_val

                registros.append({
                    'descricao':    descricao,
                    'valor':        str(valor_raw),
                    'data':         data_obj.strftime('%Y-%m-%d'),
                    'tipo':         tipo,
                    'carteira':     carteira_nome,
                    'categoria':    categoria_nome,
                })

            except Exception:
                erros += 1
                continue

        if not registros:
            flash(f'Nenhuma transação identificada no arquivo.{(" (" + str(erros) + " linhas com erro)") if erros else ""}', 'warning')
            return redirect(url_for('finance.dashboard'))

        session['import_despesas_preview'] = registros
        if erros:
            flash(f'{erros} linha(s) ignoradas por erro de formato.', 'warning')
        return redirect(url_for('finance.confirmar_despesas'))

    except Exception as e:
        flash(f'Erro ao processar arquivo: {str(e)}', 'danger')

    return redirect(url_for('finance.dashboard'))


@finance_bp.route('/financas/despesas/confirmar')
@login_required
def confirmar_despesas():
    registros = session.get('import_despesas_preview', [])
    if not registros:
        flash('Nenhuma importação de despesas pendente.', 'warning')
        return redirect(url_for('finance.dashboard'))

    categorias = Categoria.query.order_by(Categoria.tipo.asc(), Categoria.nome.asc()).all()
    carteiras  = Carteira.query.order_by(Carteira.nome.asc()).all()

    return render_template(
        'finance/confirmar_despesas.html',
        registros=registros,
        categorias=categorias,
        carteiras=carteiras,
    )


@finance_bp.route('/financas/despesas/salvar_confirmacao', methods=['POST'])
@login_required
@admin_required
def salvar_confirmacao_despesas():
    try:
        descricoes  = request.form.getlist('descricao[]')
        valores     = request.form.getlist('valor[]')
        datas       = request.form.getlist('data[]')
        tipos       = request.form.getlist('tipo[]')
        carteiras_f = request.form.getlist('carteira[]')
        categorias_f = request.form.getlist('categoria[]')
        excluir     = request.form.getlist('excluir[]')   # índices base-0

        carteiras_cache = {c.nome: c for c in Carteira.query.all()}
        categorias_cache = {c.nome.upper(): c.id for c in Categoria.query.all()}
        c_sessao_nome = session.get('carteira_ativa', 'Consolidada')
        c_sessao_obj  = carteiras_cache.get(c_sessao_nome)

        count     = 0
        ignorados = 0

        for i in range(len(descricoes)):
            if str(i) in excluir:
                ignorados += 1
                continue

            try:
                descricao  = descricoes[i].strip()
                data_obj   = datetime.strptime(datas[i], '%Y-%m-%d').date()
                valor_raw  = Decimal(valores[i].replace(',', '.'))
                tipo       = tipos[i].strip() if i < len(tipos) else 'Despesa'
                cart_nome  = carteiras_f[i].strip() if i < len(carteiras_f) else ''
                cat_nome   = categorias_f[i].strip() if i < len(categorias_f) else ''

                # Resolve carteira
                c_nome = c_sessao_nome
                c_id   = c_sessao_obj.id if c_sessao_obj else None
                if cart_nome:
                    c_obj = carteiras_cache.get(cart_nome)
                    if c_obj:
                        c_nome = c_obj.nome
                        c_id   = c_obj.id

                # Resolve categoria
                cat_id = None
                if cat_nome:
                    cat_id = categorias_cache.get(cat_nome.upper())

                nova = Transacao(
                    data=data_obj,
                    descricao=descricao,
                    valor=valor_raw,
                    valor_previsto=Decimal('0'),
                    valor_pago=valor_raw,
                    tipo=tipo,
                    categoria_id=cat_id,
                    carteira=c_nome,
                    carteira_id=c_id,
                    pago=True,
                    dia_vencimento=data_obj.day,
                )
                db.session.add(nova)
                count += 1

            except Exception:
                ignorados += 1
                continue

        db.session.commit()
        session.pop('import_despesas_preview', None)

        msg_ign = f' ({ignorados} ignorados)' if ignorados > 0 else ''
        if count > 0:
            flash(f'Sucesso! {count} transações importadas.{msg_ign}', 'success')
        else:
            flash(f'Nenhuma transação importada.{msg_ign}', 'info')

    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao salvar: {str(e)}', 'danger')

    return redirect(url_for('finance.dashboard'))

@finance_bp.route('/financas/cartao/detalhes/<fatura_mes>/<int:transacao_id>')
@login_required
def detalhes_cartao(fatura_mes, transacao_id):
    itens = GastoCartao.query.filter_by(fatura_mes=fatura_mes, transacao_id=transacao_id).order_by(GastoCartao.data.asc()).all()
    if not itens:
        flash('Detalhes não encontrados para esta fatura.', 'warning')
        return redirect(url_for('finance.dashboard'))
    
    total = sum(item.valor for item in itens)
    
    transacao = Transacao.query.get(transacao_id)
    cartao_nome = transacao.descricao.split(' - ')[0] if transacao else "Fatura Cartão"
    
    # Mês traduzido
    ano, mes = fatura_mes.split('-')
    meses_br = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    mes_nome = f"{meses_br[int(mes)-1]} / {ano}"
    
    categorias = Categoria.query.order_by(Categoria.nome.asc()).all()
    
    return render_template('finance/card_details.html', itens=itens, total=total, mes_nome=mes_nome, fatura_mes=fatura_mes, cartao_nome=cartao_nome, categorias=categorias)

@finance_bp.route('/financas/cartao/update_item_categoria', methods=['POST'])
@login_required
@admin_required
def update_item_categoria():
    data = request.get_json()
    item_id = data.get('item_id')
    categoria_id = data.get('categoria_id')
    
    item = GastoCartao.query.get_or_404(item_id)
    if categoria_id:
        item.categoria_id = categoria_id
        categoria = Categoria.query.get(categoria_id)
        if categoria:
            from card_parser import update_map_categoria
            update_map_categoria(categoria.nome, item.descricao)
    else:
        item.categoria_id = None
        
    db.session.commit()
    return jsonify({'success': True, 'message': 'Categoria atualizada e regra adicionada.'})

@finance_bp.route('/financas/graficos')

@login_required
def graficos():
    hoje = date.today()
    mes_sel = int(request.args.get('mes', hoje.month))
    ano_sel = int(request.args.get('ano', hoje.year))
    
    meses_br = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    
    if mes_sel == 0:
        mes_str = f"Ano Todo - {ano_sel}"
    else:
        mes_str = f"{meses_br[mes_sel-1]} / {ano_sel}"
    
    return render_template('finance/graficos.html',
                           mes_sel=mes_sel,
                           ano_sel=ano_sel,
                           mes_atual=mes_str,
                           meses_br=meses_br)

@finance_bp.route('/api/financas/dados_graficos')
@login_required
def dados_graficos():
    mes_sel = int(request.args.get('mes', date.today().month))
    ano_sel = int(request.args.get('ano', date.today().year))
    c_ativa = get_current_wallet()
    
    # Definir período de busca
    if mes_sel == 0:
        # Ano Todo
        inicio_periodo = date(ano_sel, 1, 1)
        fim_periodo = date(ano_sel, 12, 31)
    else:
        # Mês Específico
        inicio_periodo = date(ano_sel, mes_sel, 1)
        fim_periodo = date(ano_sel, mes_sel, calendar.monthrange(ano_sel, mes_sel)[1])
    
    # --- DESPESAS POR CATEGORIA ---
    # Para o gráfico de pizza, se for 'Ano Todo' no ano atual, limitamos até hoje para não pegar projeções futuras
    hoje = date.today()
    fim_busca_pie = fim_periodo
    if mes_sel == 0 and ano_sel == hoje.year:
        fim_busca_pie = hoje

    # Filtro de Despesas usando query autorizada
    query_despesas = get_authorized_query(Transacao, c_ativa).filter(
        Transacao.data >= inicio_periodo,
        Transacao.data <= fim_busca_pie,
        Transacao.tipo == 'Despesa',
        Transacao.removida == False
    )
    
    despesas_trans = query_despesas.all()
    despesas_cat = defaultdict(Decimal)
    for t in despesas_trans:
        nome_cat = t.categoria.nome if t.categoria else "Sem Categoria"
        valor = Decimal(t.valor_pago if t.valor_pago > 0 else t.valor_previsto)
        despesas_cat[nome_cat] += valor
        
    despesas_pie = [[cat, float(val)] for cat, val in despesas_cat.items() if val > 0]
    despesas_pie.sort(key=lambda x: x[1], reverse=True)
    
    # --- RECEITAS POR CATEGORIA --- usando query autorizada
    query_receitas = get_authorized_query(Transacao, c_ativa).filter(
        Transacao.data >= inicio_periodo,
        Transacao.data <= fim_periodo,
        Transacao.tipo == 'Receita',
        Transacao.removida == False
    )
        
    receitas_trans = query_receitas.all()
    receitas_cat = defaultdict(Decimal)
    for t in receitas_trans:
        nome_cat = t.categoria.nome if t.categoria else "Salário/Outros"
        valor = Decimal(t.valor_pago if t.valor_pago > 0 else t.valor)
        receitas_cat[nome_cat] += valor
        
    # Adicionar Proventos do período usando query autorizada
    query_divs = get_authorized_query(Dividendo, c_ativa).filter(
        Dividendo.data_recebimento >= inicio_periodo,
        Dividendo.data_recebimento <= fim_periodo
    )
    proventos_periodo = query_divs.all()
    proventos_total = sum(Decimal(str(p.valor_total)) for p in proventos_periodo)
    
    if proventos_total > 0:
        receitas_cat["Mercado Financeiro (Proventos)"] += proventos_total
        
    receitas_pie = [[cat, float(val)] for cat, val in receitas_cat.items() if val > 0]
    receitas_pie.sort(key=lambda x: x[1], reverse=True)
    
    # --- EVOLUÇÃO (Sempre mostra os 12 meses do ano selecionado) ---
    evolution_data = []
    
    for m in range(1, 13):
        d_inicio = date(ano_sel, m, 1)
        d_fim = date(ano_sel, m, calendar.monthrange(ano_sel, m)[1])
        
        # Receitas usando query autorizada
        q_rec = get_authorized_query(Transacao, c_ativa).filter(Transacao.data >= d_inicio, Transacao.data <= d_fim, Transacao.tipo == 'Receita', Transacao.removida == False)
        tot_rec = sum(Decimal(t.valor_pago if t.valor_pago > 0 else t.valor) for t in q_rec.all())
        
        q_div = get_authorized_query(Dividendo, c_ativa).filter(Dividendo.data_recebimento >= d_inicio, Dividendo.data_recebimento <= d_fim)
        tot_div = sum(Decimal(str(p.valor_total)) for p in q_div.all())
        
        # Despesas usando query autorizada
        q_desp = get_authorized_query(Transacao, c_ativa).filter(Transacao.data >= d_inicio, Transacao.data <= d_fim, Transacao.tipo == 'Despesa', Transacao.removida == False)
        tot_desp = sum(Decimal(t.valor_pago or 0) for t in q_desp.all())
        
        meses_curtos = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
        evolution_data.append([meses_curtos[m-1], float(tot_rec + tot_div), float(tot_desp)])
        
    # --- GASTOS CARTÃO POR CATEGORIA ---
    if mes_sel == 0:
        query_cartoes = GastoCartao.query.filter(GastoCartao.fatura_mes.like(f"{ano_sel}-%"))
    else:
        mes_fatura = f"{ano_sel}-{mes_sel:02d}"
        query_cartoes = GastoCartao.query.filter_by(fatura_mes=mes_fatura)
        
    # Cartão usando join com Transacao e query autorizada de Transacao para filtro de carteira
    if c_ativa == 'Consolidada':
        if current_user.perfil and current_user.perfil.nome != 'Admin':
            wallet_ids = [c.id for c in current_user.carteiras]
            query_cartoes = query_cartoes.join(Transacao).filter(Transacao.carteira_id.in_(wallet_ids)) if wallet_ids else query_cartoes.join(Transacao).filter(False)
    else:
        c_obj = Carteira.query.filter_by(nome=c_ativa).first()
        if c_obj:
            if current_user.perfil and current_user.perfil.nome != 'Admin' and c_obj not in current_user.carteiras:
                query_cartoes = query_cartoes.join(Transacao).filter(False)
            else:
                query_cartoes = query_cartoes.join(Transacao).filter(Transacao.carteira_id == c_obj.id)
        else:
            query_cartoes = query_cartoes.join(Transacao).filter(False)
        
    cartoes_itens = query_cartoes.all()
    cartoes_cat = defaultdict(Decimal)
    for g in cartoes_itens:
        nome_cat = g.categoria.nome if g.categoria else "Sem Categoria"
        cartoes_cat[nome_cat] += Decimal(g.valor)
        
    cartoes_pie = [[cat, float(val)] for cat, val in cartoes_cat.items() if val > 0]
    cartoes_pie.sort(key=lambda x: x[1], reverse=True)
    
    return jsonify({
        'despesas_pie': despesas_pie,
        'receitas_pie': receitas_pie,
        'cartoes_pie': cartoes_pie,
        'evolution': evolution_data
    })

