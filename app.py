import os
from dotenv import load_dotenv
load_dotenv()

import logging
import requests
import pandas as pd
import io
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
from sqlalchemy import func
import re
import unicodedata
from decimal import Decimal, ROUND_HALF_UP

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['SECRET_KEY'] = 'pPC294C4P0VnybJI4' 
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

# Configuração de Banco de Dados
database_url = os.environ.get('DATABASE_URL')

if database_url:
    # Vercel/Supabase usam postgresql:// mas o SQLAlchemy as vezes pede postgresql+psycopg2://
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    # Fallback para MariaDB/MySQL local
    db_user = os.environ.get('DB_USER', 'user_fluxocapital')
    db_pass = os.environ.get('DB_PASS', '1qhnTXZDCz8P4cB7n')
    db_host = os.environ.get('DB_HOST', 'localhost')
    db_name = os.environ.get('DB_NAME', 'db_fluxocapital')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+mysqlconnector://{db_user}:{db_pass}@{db_host}/{db_name}'

# Logger detalhado para o Vercel
if os.environ.get('VERCEL'):
    logging.info(f"--- INICIANDO NO VERCEL ---")
    if database_url:
        # Obscurece a senha para o log
        safe_url = database_url.split('@')[-1] if '@' in database_url else "URL_INVALIDA"
        logging.info(f"Conexão detectada: PostgreSQL (host: {safe_url})")
    else:
        logging.error("CRÍTICO: DATABASE_URL não encontrada nas variáveis de ambiente!")

from auth import admin_required, superadmin_required, is_superadmin, is_admin_or_superadmin
from utils import get_current_wallet, get_authorized_query, log_action, log_file, actions_log_file, user_logger
import logging

# Logger para erros e avisos do sistema/login
if os.environ.get('VERCEL'):
    handlers = [logging.StreamHandler()]
else:
    handlers = [logging.FileHandler(log_file, mode='a', encoding='utf-8'), logging.StreamHandler()]

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=handlers,
    force=True 
)

from extensions import db, login_manager
from models import Usuario, Ativo, Venda, Dividendo, Categoria, Transacao, CategoriaAtivo, CategoriaProvento, Carteira, PerfilUsuario
from finance import finance_bp
from funcionarios import funcionarios_bp

db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = None
# login_manager.login_message_category = "info"
app.register_blueprint(finance_bp)
app.register_blueprint(funcionarios_bp)

# --- ERROS ---
@app.errorhandler(500)
def internal_error(error):
    logging.error(f"ERRO 500: {error}")
    import traceback
    logging.error(traceback.format_exc())
    return "Erro Interno do Servidor (500). Verifique os Logs do Vercel.", 500

# --- MODELOS --- (Movidos para models.py)
# Modelos movidos para models.py

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))


@app.before_request
def sync_wallet_from_url():
    """Sincroniza a seleção de carteira da URL para a sessão antes de cada requisição."""
    if request.endpoint and 'static' not in request.endpoint:
        if current_user and current_user.is_authenticated:
            get_current_wallet()

# --- FILTROS JINJA ---
@app.template_filter('br_format')
def br_format(value):
    if value is None: return "0,00"
    try: return "{:,.2f}".format(float(value)).replace(",", "v").replace(".", ",").replace("v", ".")
    except: return "0,00"

@app.template_filter('br_currency')
def br_currency(value):
    return br_format(value)

@app.template_filter('clean_qtd')
def clean_qtd(value):
    if value is None: return "0"
    try:
        f_val = float(value)
        if f_val.is_integer(): return str(int(f_val))
        return "{:g}".format(f_val).replace(".", ",")
    except: return value

# --- CONTEXT PROCESSOR ---
def get_last_modification_time():
    """Retorna a data e hora do arquivo mais recente modificado no projeto."""
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        max_mtime = 0
        for root, dirs, files in os.walk(base_dir):
            if any(ignore in root for ignore in ['.git', '__pycache__', 'venv', '.venv', '.vercel', 'node_modules']):
                continue
            for file in files:
                if file.endswith(('.py', '.html', '.css', '.js', '.sh', '.md')):
                    filepath = os.path.join(root, file)
                    mtime = os.path.getmtime(filepath)
                    if mtime > max_mtime:
                        max_mtime = mtime
        if max_mtime > 0:
            dt = datetime.fromtimestamp(max_mtime)
            # AWS Lambda (e Vercel) intencionalmente substitui a data de modificação 
            # de todos os arquivos no deploy para uma data fixa (geralmente 20/10/2018 ou 1980) 
            # para garantir hashes consistentes. Se a data for antiga, estamos na nuvem.
            if dt.year > 2020:
                return dt.strftime('%d/%m/%Y %H:%M')
    except Exception:
        pass
    
    # Se estivermos no Vercel (onde os arquivos caem em 2018) ou houver erro, 
    # retorna a data/hora em que a instância subiu ajustada para o fuso brasileiro (-03:00).
    if os.environ.get('VERCEL'):
        hora_brasil = datetime.utcnow() - timedelta(hours=3)
        return hora_brasil.strftime('%d/%m/%Y %H:%M') + " (Nuvem)"
    return datetime.now().strftime('%d/%m/%Y %H:%M') + " (Nuvem)"

# Calculado na inicialização da aplicação
LAST_DEPLOY_TIME = get_last_modification_time()

@app.context_processor
def inject_carteira():
    if current_user.is_authenticated:
        if is_superadmin():
            carteiras = Carteira.query.order_by(Carteira.nome).all()
        else:
            # Usuário e Admin veem apenas suas carteiras atribuídas
            user_wallets = list(current_user.carteiras)
            if not any(c.id == 1 for c in user_wallets):
                consolidada = Carteira.query.get(1)
                if consolidada:
                    user_wallets.insert(0, consolidada)
            # Ordena por nome
            user_wallets.sort(key=lambda x: x.nome)
            carteiras = user_wallets
    else:
        carteiras = []
    
    # Usa o helper para obter a seleção atual
    c_ativa = get_current_wallet()
    
    # Nome para exibição no botão
    if isinstance(c_ativa, list):
        carteira_exibicao = ", ".join(c_ativa)
        carteiras_selecionadas = c_ativa
    else:
        carteira_exibicao = c_ativa
        carteiras_selecionadas = [c_ativa] if c_ativa != 'Consolidada' else []
        
    return {
        'carteira_atual': carteira_exibicao,
        'carteiras_selecionadas': carteiras_selecionadas,
        'carteiras_disponiveis': [c.nome for c in carteiras],
        'carteiras_disponiveis_objs': carteiras,
        'carteiras_cadastro_objs': [c for c in carteiras if c.id != 1],
        'is_superadmin': is_superadmin(),
        'is_admin_or_superadmin': is_admin_or_superadmin(),
        'now_year': datetime.now().year,
        'ultima_atualizacao': LAST_DEPLOY_TIME
    }

# --- CÁLCULOS ---
def calcular_consolidado(c_ativa=None):
    if c_ativa is None:
        c_ativa = get_current_wallet()
    
    # Usa query autorizada para consolidar dados de Ativos, Vendas e Dividendos
    ativos = get_authorized_query(Ativo, c_ativa).all()
    vendas = get_authorized_query(Venda, c_ativa).all()
    divs_raw = get_authorized_query(Dividendo, c_ativa).all()
    consolidado_lista = []
    dados_grafico = {}
    pat_atual = 0.0
    tot_pago = 0.0

    for a in ativos:
        t = a.ticker
        # prioritizes the new category relationship
        cat = a.categoria_rel.nome if a.categoria_rel else (a.categoria if a.categoria else 'Ações')
        preco_banco = float(a.preco_atual) if float(a.preco_atual) > 0 else float(a.preco_compra)
        # BUG FIX: Group by BOTH ticker AND category
        item = next((x for x in consolidado_lista if x['ticker'] == t and x['categoria'] == cat), None)
        if not item:
            divs_ativo = sum(float(d.valor_total) for d in divs_raw if d.ticker == t)
            item = {'ticker': t, 'categoria': cat, 'qtd_total': 0.0, 'total_pago': 0.0, 
                    'preco_atual': preco_banco, 'pvp': a.pvp, 'total_divs_recebidos': divs_ativo}
            consolidado_lista.append(item)
        item['qtd_total'] += float(a.quantidade)
        item['total_pago'] += (float(a.quantidade) * float(a.preco_compra))
        tot_pago += (float(a.quantidade) * float(a.preco_compra))

    for d in consolidado_lista:
        d['valor_mercado'] = d['qtd_total'] * d['preco_atual']
        pat_atual += d['valor_mercado']

    for d in consolidado_lista:
        d['preco_medio'] = d['total_pago'] / d['qtd_total'] if d['qtd_total'] > 0 else 0
        d['lucro_rs'] = d['valor_mercado'] - d['total_pago']
        d['lucro_pct'] = ((d['valor_mercado'] / d['total_pago']) - 1) * 100 if d['total_pago'] > 0 else 0
        d['yoc'] = (d['total_divs_recebidos'] / d['total_pago'] * 100) if d['total_pago'] > 0 else 0
        d['dy'] = (d['total_divs_recebidos'] / d['valor_mercado'] * 100) if d['valor_mercado'] > 0 else 0
        d['peso_carteira'] = (d['valor_mercado'] / pat_atual * 100) if pat_atual > 0 else 0
        dados_grafico[d['categoria']] = dados_grafico.get(d['categoria'], 0) + d['valor_mercado']

    return consolidado_lista, dados_grafico, tot_pago, pat_atual, vendas, divs_raw

# --- ROTAS ---

@app.route('/login', methods=['GET', 'POST'])
@log_action("Login de usuário")
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        u = Usuario.query.filter_by(username=username).first()
        if u and check_password_hash(u.password, request.form['password']):
            if u.bloqueado:
                flash("Sua conta está bloqueada. Entre em contato com o administrador.", "danger")
                return render_template('login.html')
            login_user(u)
            session.permanent = True
            return redirect(url_for('index'))
        logging.warning(f"FALHA_LOGIN: {username} - IP: {request.remote_addr}")
        flash("Credenciais inválidas.", "danger")
    return render_template('login.html')

@app.route('/logout')
@login_required
@log_action("Logout de usuário")
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/perfil', methods=['GET', 'POST'])
@login_required
@log_action("Acesso/Alteração de Perfil")
def perfil():
    if request.method == 'POST':
        senha_atual = request.form.get('senha_atual')
        nova_senha = request.form.get('nova_senha')
        confirmacao = request.form.get('confirmacao')

        if not check_password_hash(current_user.password, senha_atual):
            flash("Senha atual incorreta.", "danger")
        elif nova_senha != confirmacao:
            flash("A nova senha e a confirmação não coincidem.", "danger")
        elif len(nova_senha) < 6:
            flash("A nova senha deve ter pelo menos 6 caracteres.", "warning")
        else:
            current_user.password = generate_password_hash(nova_senha, method='pbkdf2:sha256')
            db.session.commit()
            flash("Senha alterada com sucesso!", "success")
            return redirect(url_for('perfil'))
            
    return render_template('perfil.html')

@app.route('/registrar', methods=['GET', 'POST'])
@login_required
@admin_required
@log_action("Gestão de Usuários")
def registrar():
    """Gestão de usuários. Admin pode gerenciar Usuários. SuperAdmin pode gerenciar tudo."""
    
    def _pode_gerir(target_user):
        """Verifica se o usuário atual pode gerir o target_user."""
        if is_superadmin():
            return True  # SuperAdmin pode gerir qualquer um
        # Admin NÃO pode gerir SuperAdmin nem outros Admins
        if target_user and target_user.perfil:
            if target_user.perfil.nome in ('SuperAdmin', 'Admin'):
                return False
        return True

    def _carteiras_permitidas():
        """Retorna as carteiras que o usuário atual pode atribuir a outros usuários."""
        if is_superadmin():
            return Carteira.query.all()
        # Admin só pode atribuir suas próprias carteiras
        return list(current_user.carteiras)

    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'cadastrar':
            username = request.form.get('username')
            password = request.form.get('password')
            confirmacao = request.form.get('confirmacao')
            perfil_id = request.form.get('perfil_id')
            selected_carteiras = request.form.getlist('carteiras')
            
            # Validar: Admin só pode criar usuários com perfil Usuário
            perfil_novo = PerfilUsuario.query.get(perfil_id)
            if not is_superadmin() and perfil_novo and perfil_novo.nome in ('SuperAdmin', 'Admin'):
                flash("Você não tem permissão para criar usuários com esse perfil.", "danger")
                return redirect(url_for('registrar'))

            if password != confirmacao:
                flash("As senhas não coincidem.", "danger")
            elif len(password) < 6:
                flash("A senha deve ter pelo menos 6 caracteres.", "warning")
            elif Usuario.query.filter_by(username=username).first():
                flash("Este nome de usuário já existe.", "warning")
            else:
                hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
                novo_usuario = Usuario(
                    username=username, 
                    password=hashed_pw,
                    perfil_id=perfil_id,
                    criado_por_id=current_user.id
                )
                if selected_carteiras:
                    # Filtrar apenas carteiras que o usuário atual tem permissão de atribuir
                    ids_permitidos = {c.id for c in _carteiras_permitidas()}
                    carteiras_validas = [
                        Carteira.query.get(int(cid))
                        for cid in selected_carteiras
                        if int(cid) in ids_permitidos
                    ]
                    novo_usuario.carteiras = [c for c in carteiras_validas if c]
                
                db.session.add(novo_usuario)
                db.session.commit()
                flash(f"Usuário {username} cadastrado com sucesso!", "success")
        
        elif action == 'reset_password':
            user_id = request.form.get('user_id')
            nova_senha = request.form.get('nova_senha')
            user_to_reset = Usuario.query.get(user_id)
            if not _pode_gerir(user_to_reset):
                flash("Você não tem permissão para alterar a senha deste usuário.", "danger")
                return redirect(url_for('registrar'))
            if user_to_reset and len(nova_senha) >= 6:
                user_to_reset.password = generate_password_hash(nova_senha, method='pbkdf2:sha256')
                db.session.commit()
                flash(f"Senha de {user_to_reset.username} alterada com sucesso!", "success")
            else:
                flash("Erro ao alterar senha. Mínimo 6 caracteres.", "danger")
        
        elif action == 'toggle_block':
            user_id = request.form.get('user_id')
            user_to_toggle = Usuario.query.get(user_id)
            if not _pode_gerir(user_to_toggle):
                flash("Você não tem permissão para bloquear este usuário.", "danger")
                return redirect(url_for('registrar'))
            if user_to_toggle:
                if user_to_toggle.id == current_user.id:
                    flash("Você não pode bloquear sua própria conta.", "warning")
                else:
                    user_to_toggle.bloqueado = not user_to_toggle.bloqueado
                    db.session.commit()
                    status = "bloqueado" if user_to_toggle.bloqueado else "desbloqueado"
                    flash(f"Usuário {user_to_toggle.username} {status}!", "success")
        
        elif action == 'update_perfil':
            user_id = request.form.get('user_id')
            novo_perfil_id = request.form.get('perfil_id')
            user_to_update = Usuario.query.get(user_id)
            # Verificar permissão sobre o usuário alvo
            if not _pode_gerir(user_to_update):
                flash("Você não tem permissão para alterar o perfil deste usuário.", "danger")
                return redirect(url_for('registrar'))
            # Verificar permissão sobre o perfil destino
            perfil_destino = PerfilUsuario.query.get(novo_perfil_id)
            if not is_superadmin() and perfil_destino and perfil_destino.nome in ('SuperAdmin', 'Admin'):
                flash("Você não tem permissão para atribuir esse perfil.", "danger")
                return redirect(url_for('registrar'))
            if user_to_update:
                user_to_update.perfil_id = novo_perfil_id
                db.session.commit()
                flash(f"Perfil de {user_to_update.username} alterado com sucesso!", "success")
        
        elif action == 'update_user_carteiras':
            user_id = request.form.get('user_id')
            selected_carteiras = request.form.getlist('carteiras')
            user_to_update = Usuario.query.get(user_id)
            if not _pode_gerir(user_to_update):
                flash("Você não tem permissão para alterar as carteiras deste usuário.", "danger")
                return redirect(url_for('registrar'))
            if user_to_update:
                # Filtrar apenas carteiras que o usuário atual tem permissão de atribuir
                ids_permitidos = {c.id for c in _carteiras_permitidas()}
                # Para SuperAdmin: atribui exatamente o selecionado
                # Para Admin: atribui apenas a intersecção das selecionadas com as suas próprias
                if is_superadmin():
                    user_to_update.carteiras = [
                        Carteira.query.get(int(cid)) for cid in selected_carteiras
                    ]
                else:
                    # Mantém carteiras que o admin não controla (de outros admins)
                    carteiras_fora_do_admin = [c for c in user_to_update.carteiras if c.id not in ids_permitidos]
                    carteiras_selecionadas_validas = [
                        Carteira.query.get(int(cid))
                        for cid in selected_carteiras
                        if int(cid) in ids_permitidos
                    ]
                    user_to_update.carteiras = carteiras_fora_do_admin + [c for c in carteiras_selecionadas_validas if c]
                db.session.commit()
                flash(f"Carteiras de {user_to_update.username} atualizadas!", "success")
                    
        return redirect(url_for('registrar'))

    usuarios = Usuario.query.all()
    # SuperAdmin vê todos os perfis; Admin vê apenas 'Usuário' para criar
    if is_superadmin():
        perfis = PerfilUsuario.query.order_by(PerfilUsuario.nome).all()
        perfis_criacao = [p for p in perfis if p.nome != 'SuperAdmin']  # Não criar outro SuperAdmin via UI
    else:
        perfis = PerfilUsuario.query.order_by(PerfilUsuario.nome).all()
        perfis_criacao = [p for p in perfis if p.nome == 'Usuário']
    
    # Admin só enxerga/atribui as próprias carteiras no formulário
    carteiras_formulario = _carteiras_permitidas()

    return render_template(
        'registrar.html',
        usuarios=usuarios,
        perfis=perfis,
        perfis_criacao=perfis_criacao,
        carteiras_disponiveis_objs=carteiras_formulario,
    )

@app.route('/')
@login_required
def index():
    consolidado_lista, dados_grafico, tot_pago, pat_atual, vendas, divs_raw = calcular_consolidado()
    val_rs = pat_atual - tot_pago
    val_pct = (val_rs / tot_pago * 100) if tot_pago > 0 else 0
    t_vendas = sum(float(v.lucro_realizado) for v in vendas)
    t_divs = sum(float(d.valor_total) for d in divs_raw)
    g_totais = t_vendas + t_divs
    
    # NOVO: Cálculo da porcentagem de ganhos totais sobre o valor investido
    g_totais_pct = (g_totais / tot_pago * 100) if tot_pago > 0 else 0
    
    # NOVO: Percentuais individuais para Vendas e Dividendos
    lucro_vendas_pct = (t_vendas / tot_pago * 100) if tot_pago > 0 else 0
    dividendos_pct = (t_divs / tot_pago * 100) if tot_pago > 0 else 0
    
    # Agrupar ativos por categoria
    categorias_agrupadas = {}
    ordem_categorias = ['Ações', 'FIIs', 'ETFs', 'BDRs', 'Renda Fixa', 'Internacional']
    icones_categorias = {
        'Ações': 'bi-shield-check',
        'FIIs': 'bi-building',
        'ETFs': 'bi-globe2',
        'BDRs': 'bi-box-arrow-in-down-right',
        'Renda Fixa': 'bi-file-earmark-lock',
        'Internacional': 'bi-airplane',
        'Previdência': 'bi-piggy-bank',
        'Cripto': 'bi-currency-bitcoin'
    }
    
    for d in consolidado_lista:
        cat = d['categoria']
        if cat not in categorias_agrupadas:
            categorias_agrupadas[cat] = {
                'nome': cat,
                'icone': icones_categorias.get(cat, 'bi-tag'),
                'ativos': [],
                'total_valor_mercado': 0.0,
                'total_investido': 0.0,
                'total_lucro_rs': 0.0,
                'total_proventos': 0.0,
            }
        categorias_agrupadas[cat]['ativos'].append(d)
        categorias_agrupadas[cat]['total_valor_mercado'] += d['valor_mercado']
        categorias_agrupadas[cat]['total_investido'] += d['total_pago']
        categorias_agrupadas[cat]['total_lucro_rs'] += d['lucro_rs']
        categorias_agrupadas[cat]['total_proventos'] += d.get('total_divs_recebidos', 0)
    
    for cat_data in categorias_agrupadas.values():
        inv = cat_data['total_investido']
        vm = cat_data['total_valor_mercado']
        prov = cat_data['total_proventos']
        cat_data['total_lucro_pct'] = ((vm / inv) - 1) * 100 if inv > 0 else 0
        cat_data['yoc_categoria'] = (prov / inv * 100) if inv > 0 else 0
        cat_data['dy_categoria'] = (prov / vm * 100) if vm > 0 else 0
        cat_data['peso_carteira'] = (vm / pat_atual * 100) if pat_atual > 0 else 0
        cat_data['qtd_ativos'] = len(cat_data['ativos'])
    
    # Ordenar categorias
    categorias_ordenadas = []
    for cat_nome in ordem_categorias:
        if cat_nome in categorias_agrupadas:
            categorias_ordenadas.append(categorias_agrupadas[cat_nome])
    # Adicionar categorias que não estão na ordem predefinida
    for cat_nome, cat_data in categorias_agrupadas.items():
        if cat_nome not in ordem_categorias:
            categorias_ordenadas.append(cat_data)
    
    return render_template('index.html', 
                           consolidado_lista=consolidado_lista,
                           categorias_agrupadas=categorias_ordenadas,
                           dados_grafico=dados_grafico, 
                           total_pago=tot_pago, 
                           patrimonio_atual=pat_atual, 
                           valorizacao_total_rs=val_rs, 
                           valorizacao_total_percent=val_pct, 
                           total_lucro_vendas=t_vendas, 
                           lucro_vendas_pct=lucro_vendas_pct,
                           total_dividendos=t_divs, 
                           dividendos_pct=dividendos_pct,
                           ganhos_totais_rs=g_totais, 
                           ganhos_totais_pct=g_totais_pct, 
                           hoje=datetime.now().strftime('%Y-%m-%d'))


@app.route('/analise')
@login_required
def analise():
    c_ativa = get_current_wallet()
    _, dados_grafico, _, pat_atual, _, _ = calcular_consolidado(c_ativa)
    return render_template('analise.html', dados_grafico=dados_grafico, patrimonio_atual=pat_atual)

@app.route('/analise/<ticker>')
@login_required
def detalhe_ativo(ticker):
    c_ativa = get_current_wallet()
    
    # 1. Informações básicas do ativo (lotes atuais) usando query autorizada
    q_lotes = get_authorized_query(Ativo, c_ativa).filter_by(ticker=ticker)
    lotes = q_lotes.order_by(Ativo.data_compra.desc()).all()
    
    if not lotes:
        flash(f"Ativo {ticker} não encontrado na carteira {c_ativa}.", "warning")
        return redirect(url_for('index'))
    
    preco_atual = float(lotes[0].preco_atual)
    pvp = lotes[0].pvp
    nome_ativo = lotes[0].nome_ativo or ticker
    
    # 2. Histórico de Proventos usando query autorizada
    q_prov = get_authorized_query(Dividendo, c_ativa).filter_by(ticker=ticker)
    proventos_raw = q_prov.order_by(Dividendo.data_recebimento.asc()).all()
    
    # 3. Processamento de Aportes para a tabela detalhada
    aportes_detalhe = []
    total_investido_atual = 0.0
    total_qtd_atual = 0.0
    for l in lotes:
        qtd = float(l.quantidade)
        pc = float(l.preco_compra)
        investido = qtd * pc
        valor_atual_mercado = qtd * preco_atual
        valorizacao = valor_atual_mercado - investido
        valorizacao_pct = (valorizacao / investido * 100) if investido > 0 else 0
        
        aportes_detalhe.append({
            'data': l.data_compra,
            'qtd': qtd,
            'preco_compra': pc,
            'investido': investido,
            'valorizacao': valorizacao,
            'valorizacao_pct': valorizacao_pct
        })
        total_investido_atual += investido
        total_qtd_atual += qtd

    # 4. Cálculo de Proventos Mensais e DYC Histórico
    # Para cada provento, precisamos saber quanto o usuário tinha investido NAQUELA DATA
    # Como não temos uma tabela de "ordens completa" (apenas Ativos e Vendas),
    # vamos usar os lotes atuais e as vendas para reconstruir a posição histórica.
    # NO ENTANTO, para simplificar e focar no que o usuário vê (lotes atuais), 
    # vamos calcular o Yield on Cost sobre o PM atual para os proventos recentes.
    # Mas o ideal é somar o que ele tinha na data.
    
    historico_detalhado = []
    # Vendas do ativo usando query autorizada
    q_vendas = get_authorized_query(Venda, c_ativa).filter_by(ticker=ticker)
    vendas = q_vendas.all()
    
    for p in proventos_raw:
        dt_p = p.data_recebimento
        # Quantidade que ele tinha na data: (Soma Ativos comprados antes) + (Soma Vendas efetuadas DEPOIS)
        # Na verdade, a lógica é: ordens de compra antes da data - ordens de venda antes da data.
        # Mas não temos as ordens de compra originais de ativos já vendidos.
        # Vamos usar uma aproximação baseada nos lotes que ainda existem + se houver registros de vendas.
        
        # Simplificação: Usar o PM e Qtd que ele tem hoje se for FII estável, 
        # ou tentar filtrar compras anteriores.
        
        qtd_na_data = sum(float(l.quantidade) for l in lotes if l.data_compra <= dt_p)
        # Adiciona as que ele vendeu DEPOIS dessa data (pois na data ele ainda as tinha)
        qtd_na_data += sum(float(v.quantidade) for v in vendas if v.data_venda > dt_p)
        
        # Valor investido na data (Custo de aquisição das cotas que ele tinha)
        # Usaremos o PM atual dos lotes existentes como base de custo.
        investido_na_data = sum(float(l.quantidade) * float(l.preco_compra) for l in lotes if l.data_compra <= dt_p)
        investido_na_data += sum(float(v.quantidade) * float(v.preco_medio_compra) for v in vendas if v.data_venda > dt_p)
        
        valor_total_recebido = float(p.valor_total)
        div_por_cota = valor_total_recebido / qtd_na_data if qtd_na_data > 0 else 0
        dyc = (valor_total_recebido / investido_na_data * 100) if investido_na_data > 0 else 0
        p_valor_atual = (valor_total_recebido / (qtd_na_data * preco_atual) * 100) if (qtd_na_data > 0 and preco_atual > 0) else 0

        historico_detalhado.append({
            'data': dt_p,
            'div_cota': div_por_cota,
            'qtd': qtd_na_data,
            'investido': investido_na_data,
            'valor_total': valor_total_recebido,
            'dyc': dyc,
            'p_valor_atual': p_valor_atual,
            'tipo': p.tipo
        })

    # 5. Resumo Anual
    resumo_anual = {}
    for h in historico_detalhado:
        ano = h['data'].year
        if ano not in resumo_anual:
            resumo_anual[ano] = {'ano': ano, 'proventos': 0.0, 'investido_medio': 0.0, 'count': 0}
        resumo_anual[ano]['proventos'] += h['valor_total']
        resumo_anual[ano]['investido_medio'] += h['investido']
        resumo_anual[ano]['count'] += 1

    resumo_anual_lista = []
    total_geral_proventos = 0.0
    for ano in sorted(resumo_anual.keys(), reverse=True):
        item = resumo_anual[ano]
        inv_medio = item['investido_medio'] / item['count']
        item['yoc_ano'] = (item['proventos'] / inv_medio * 100) if inv_medio > 0 else 0
        item['p_valor_atual_ano'] = (item['proventos'] / (total_qtd_atual * preco_atual) * 100) if (total_qtd_atual > 0 and preco_atual > 0) else 0
        resumo_anual_lista.append(item)
        total_geral_proventos += item['proventos']

    # Obter lista apenas dos ativos atuais na carteira usando query autorizada
    q_tickers = get_authorized_query(Ativo, c_ativa).with_entities(Ativo.ticker)
    tickers_ativos = q_tickers.distinct().all()
    todos_tickers = sorted([t[0] for t in tickers_ativos])

    prev_ticker = None
    next_ticker = None
    if ticker in todos_tickers:
        idx = todos_tickers.index(ticker)
        if idx > 0:
            prev_ticker = todos_tickers[idx - 1]
        if idx < len(todos_tickers) - 1:
            next_ticker = todos_tickers[idx + 1]

    return render_template('detalhe_ativo.html', 
                           ticker=ticker, 
                           nome_ativo=nome_ativo,
                           preco_atual=preco_atual,
                           pvp=pvp,
                           aportes=aportes_detalhe,
                           historico=historico_detalhado[::-1], # Mais recentes primeiro
                           resumo_anual=resumo_anual_lista,
                           total_geral_proventos=total_geral_proventos,
                           total_qtd_atual=total_qtd_atual,
                           total_investido_atual=total_investido_atual,
                           todos_tickers=todos_tickers,
                           prev_ticker=prev_ticker,
                           next_ticker=next_ticker)


@app.route('/aportes')
@login_required
def aportes():
    c_ativa = get_current_wallet()
    # Filtra aportes (ativos) usando query autorizada
    query = get_authorized_query(Ativo, c_ativa)
    
    ativos = query.order_by(Ativo.data_compra.desc()).all()
    # Fetch all asset categories for the template
    categorias_ativos = CategoriaAtivo.query.order_by(CategoriaAtivo.nome).all()
    return render_template('aportes.html', ativos=ativos, 
                           categoria_ativos=categorias_ativos,
                           hoje=datetime.now().strftime('%Y-%m-%d'))

@app.route('/vendas_historico')
@login_required
def vendas_historico():
    c_ativa = get_current_wallet()
    query = get_authorized_query(Venda, c_ativa)
    vendas = query.order_by(Venda.data_venda.desc()).all()
    categoria_ativos = CategoriaAtivo.query.order_by(CategoriaAtivo.nome).all()
    return render_template('vendas.html', vendas=vendas, categoria_ativos=categoria_ativos)

@app.route('/proventos')
@login_required
def proventos():
    c_ativa = get_current_wallet()
    
    # Obtém mapeamento de ticker para categoria_id usando query autorizada
    q_sub = get_authorized_query(Ativo, c_ativa).with_entities(Ativo.ticker, Ativo.categoria_id)
    subquery = q_sub.distinct().subquery()
    
    # Join the subquery with CategoriaAtivo to get the name
    q_divs = get_authorized_query(Dividendo, c_ativa).with_entities(Dividendo, CategoriaAtivo.nome)
        
    divs = q_divs.outerjoin(
        subquery, Dividendo.ticker == subquery.c.ticker
    ).outerjoin(
        CategoriaAtivo, subquery.c.categoria_id == CategoriaAtivo.id
    ).order_by(Dividendo.data_recebimento.desc()).all()
    
    # Prepara lista para o template com a categoria injetada
    dividendos_com_categoria = []
    for d, cat_nome in divs:
        # Fallback to the string field if no relationship exists (legacy)
        if not cat_nome:
            ativo_obj = Ativo.query.filter_by(ticker=d.ticker).first()
            if ativo_obj:
                cat_nome = ativo_obj.categoria or 'Outros'
            else:
                cat_nome = 'Outros'
                
        d.categoria_nome = cat_nome
        dividendos_com_categoria.append(d)
        
    categorias_proventos = CategoriaProvento.query.order_by(CategoriaProvento.nome).all()
    categoria_ativos = CategoriaAtivo.query.order_by(CategoriaAtivo.nome).all()
    return render_template('proventos.html', 
                           dividendos=dividendos_com_categoria, 
                           hoje=datetime.now().strftime('%Y-%m-%d'),
                           categorias_proventos=categorias_proventos,
                           categoria_ativos=categoria_ativos)

@app.route('/selecionar_carteira/<carteira>')
@login_required
def selecionar_carteira(carteira):
    # Check if carteira exists in DB
    c_obj = Carteira.query.filter_by(nome=carteira).first()
    if c_obj or carteira == 'Consolidada':
        # SuperAdmin pode acessar qualquer carteira sem restrição
        if not is_superadmin():
            # Admin e Usuário: somente suas carteiras atribuídas
            if not is_admin_or_superadmin() and carteira != 'Consolidada':
                if c_obj not in current_user.carteiras:
                    flash("Você não tem permissão para acessar esta carteira.", "danger")
                    return redirect(request.referrer or url_for('index'))
            elif current_user.perfil and current_user.perfil.nome == 'Admin' and carteira != 'Consolidada':
                if c_obj not in current_user.carteiras:
                    flash("Você não tem permissão para acessar esta carteira.", "danger")
                    return redirect(request.referrer or url_for('index'))
                    
        session['carteira_ativa'] = carteira
        flash(f"Carteira '{carteira}' selecionada.", "info")
    return redirect(request.referrer or url_for('index'))

@app.route('/relatorios', methods=['GET', 'POST'])
@login_required
@log_action("Geração de Relatórios")
def relatorios():
    # Se veio do form, usa ela. Senão usa a da sessão.
    c_ativa = request.form.get('carteira_sel', get_current_wallet())
    
    # Tickers e Tipos únicos para os filtros usando a query autorizada
    q_t_div = get_authorized_query(Dividendo, c_ativa).with_entities(Dividendo.ticker)
    q_t_ativos = get_authorized_query(Ativo, c_ativa).with_entities(Ativo.ticker)
        
    tickers_div = q_t_div.distinct().all()
    tickers_ativos = q_t_ativos.distinct().all()
    tickers = sorted(list(set([t[0] for t in tickers_div] + [t[0] for t in tickers_ativos])))
    
    q_tipos = get_authorized_query(Dividendo, c_ativa).with_entities(Dividendo.tipo).distinct()
    tipos = q_tipos.order_by(Dividendo.tipo).all()
    tipos = [t[0] for t in tipos]

    categorias_ativos = CategoriaAtivo.query.order_by(CategoriaAtivo.nome).all()
    
    resultados_proventos = None
    resultados_custodia = None
    
    filtros = {
        'tipo_relatorio': request.form.get('tipo_relatorio', 'proventos'),
        'data_inicio': request.form.get('data_inicio', ''),
        'data_fim': request.form.get('data_fim', ''),
        'ticker': request.form.get('ticker', ''),
        'tipo': request.form.get('tipo', ''),
        'categoria_id': request.form.get('categoria_id', ''),
        'carteira_sel': c_ativa
    }
    
    if request.method == 'POST':
        data_inicio_obj = datetime.strptime(filtros['data_inicio'], '%Y-%m-%d').date() if filtros['data_inicio'] else None
        data_fim_obj = datetime.strptime(filtros['data_fim'], '%Y-%m-%d').date() if filtros['data_fim'] else datetime.now().date()

        if filtros['tipo_relatorio'] == 'proventos':
            query = get_authorized_query(Dividendo, c_ativa).with_entities(
                Dividendo.ticker,
                Dividendo.tipo,
                func.sum(Dividendo.valor_total).label('total')
            )
            
            if filtros['data_inicio']:
                query = query.filter(Dividendo.data_recebimento >= data_inicio_obj)
            if filtros['data_fim']:
                query = query.filter(Dividendo.data_recebimento <= data_fim_obj)
            if filtros['ticker'] and filtros['ticker'] != 'TODOS':
                query = query.filter(Dividendo.ticker == filtros['ticker'])
            if filtros['tipo'] and filtros['tipo'] != 'TODOS':
                query = query.filter(Dividendo.tipo == filtros['tipo'])
            if filtros['categoria_id'] and filtros['categoria_id'] != 'TODOS':
                query = query.filter(Dividendo.categoria_id == int(filtros['categoria_id']))
                
            resultados_raw = query.group_by(Dividendo.ticker, Dividendo.tipo).order_by(Dividendo.ticker, Dividendo.tipo).all()
            
            resultados_proventos = []
            lotes_all = get_authorized_query(Ativo, c_ativa).all()
            vendas_all = get_authorized_query(Venda, c_ativa).all()

            for r in resultados_raw:
                ticker = r.ticker
                # Buscar o nome da categoria para exibição
                div_ref = Dividendo.query.filter_by(ticker=ticker).first()
                cat_nome = div_ref.categoria_rel.nome if div_ref and div_ref.categoria_rel else 'Ações'
                
                # Calcular a quantidade em custódia na data_fim
                qtd_na_data = sum(float(l.quantidade) for l in lotes_all if l.ticker == ticker and l.data_compra <= data_fim_obj)
                qtd_na_data += sum(float(v.quantidade) for v in vendas_all if v.ticker == ticker and v.data_venda > data_fim_obj)
                
                resultados_proventos.append({
                    'ticker': ticker,
                    'tipo': r.tipo,
                    'categoria_nome': cat_nome,
                    'total': r.total,
                    'qtd_custodia': qtd_na_data
                })
        
        elif filtros['tipo_relatorio'] == 'custodia':
            lotes_all_q = get_authorized_query(Ativo, c_ativa)
            vendas_all_q = get_authorized_query(Venda, c_ativa)

            if filtros['categoria_id'] and filtros['categoria_id'] != 'TODOS':
                lotes_all_q = lotes_all_q.filter(Ativo.categoria_id == int(filtros['categoria_id']))
                vendas_all_q = vendas_all_q.filter(Venda.categoria_id == int(filtros['categoria_id']))

            lotes_all = lotes_all_q.all()
            vendas_all = vendas_all_q.all()
            
            todos_tickers = set([l.ticker for l in lotes_all] + [v.ticker for v in vendas_all])
            if filtros['ticker'] and filtros['ticker'] != 'TODOS':
                todos_tickers = [filtros['ticker']]
                
            resultados_custodia = []
            
            for ticker in sorted(todos_tickers):
                lotes_ticker = [l for l in lotes_all if l.ticker == ticker and l.data_compra <= data_fim_obj]
                
                # Buscar categoria (de qualquer lote do ticker)
                cat_nome = 'Ações'
                if lotes_ticker:
                    cat_nome = lotes_ticker[0].categoria_rel.nome if lotes_ticker[0].categoria_rel else 'Ações'
                else:
                    v_ticker = [v for v in vendas_all if v.ticker == ticker]
                    if v_ticker:
                        cat_nome = v_ticker[0].categoria_rel.nome if v_ticker[0].categoria_rel else 'Ações'
                
                if data_inicio_obj:
                    lotes_ticker = [l for l in lotes_ticker if l.data_compra >= data_inicio_obj]
                
                qtd_na_data = sum(float(l.quantidade) for l in lotes_ticker)
                custo_na_data = sum(float(l.quantidade) * float(l.preco_compra) for l in lotes_ticker)
                
                vendas_posteriores_a_data_fim = [v for v in vendas_all if v.ticker == ticker and v.data_venda > data_fim_obj]
                
                qtd_na_data += sum(float(v.quantidade) for v in vendas_posteriores_a_data_fim)
                custo_na_data += sum(float(v.quantidade) * float(v.preco_medio_compra) for v in vendas_posteriores_a_data_fim)
                
                if qtd_na_data > 0 or custo_na_data > 0:
                    resultados_custodia.append({
                        'ticker': ticker,
                        'categoria_nome': cat_nome,
                        'qtd_custodia': qtd_na_data,
                        'custo_compra': custo_na_data
                    })
        
    return render_template('relatorios.html', 
                           tickers=tickers, 
                           tipos=tipos, 
                           categorias_ativos=categorias_ativos,
                           resultados_proventos=resultados_proventos, 
                           resultados_custodia=resultados_custodia, 
                           filtros=filtros, 
                           now_date=datetime.now().strftime('%d/%m/%Y %H:%M'))

# --- OPERAÇÕES ---

@app.route('/vender', methods=['POST'])
@login_required
@admin_required
@log_action("Venda de Ativo")
def vender():
    ticker = request.form.get('ticker')
    qtd_v = float(request.form.get('quantidade'))
    preco_v = float(request.form.get('preco_venda'))
    data_v = datetime.strptime(request.form.get('data_venda'), '%Y-%m-%d')
    c_id = request.form.get('carteira_id')
    c_venda = request.form.get('carteira')
    
    if c_id:
        c_obj = Carteira.query.get(c_id)
        if c_obj:
            c_venda = c_obj.nome
    
    if not c_id and c_venda:
        c_obj = Carteira.query.filter_by(nome=c_venda).first()
        c_id = c_obj.id if c_obj else None
    
    if not c_venda:
        c_venda = 'Consolidada'
        
    q_lotes = Ativo.query.filter_by(ticker=ticker)
    if c_venda != 'Consolidada':
        q_lotes = q_lotes.filter_by(carteira=c_venda)
    lotes = q_lotes.order_by(Ativo.data_compra.asc()).all()
    
    total_qtd = sum(float(l.quantidade) for l in lotes)
    if total_qtd >= qtd_v:
        pm = sum(float(l.quantidade) * float(l.preco_compra) for l in lotes) / total_qtd
        lucro = (preco_v - pm) * qtd_v
        
        c_id = request.form.get('carteira_id')
        if not c_id:
            c_obj = Carteira.query.filter_by(nome=c_venda).first()
            c_id = c_obj.id if c_obj else None

        db.session.add(Venda(
            ticker=ticker, 
            quantidade=qtd_v, 
            preco_venda=preco_v, 
            preco_medio_compra=pm, 
            lucro_realizado=lucro, 
            data_venda=data_v, 
            carteira=c_venda,
            carteira_id=c_id,
            categoria_id=lotes[0].categoria_id if lotes else None
        ))
        rest = qtd_v
        for l in lotes:
            if rest <= 0: break
            if float(l.quantidade) <= rest:
                rest -= float(l.quantidade); db.session.delete(l)
            else:
                l.quantidade = float(l.quantidade) - rest; rest = 0
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/cadastrar', methods=['POST'])
@login_required
@admin_required
@log_action("Compra de Ativo")
def cadastrar():
    cambio = float(request.form.get('cambio', 1.0))
    p_compra = float(request.form.get('preco_compra')) * cambio
    cat_id = request.form.get('categoria_id')
    # If categoria_id is not provided, try to find by name (legacy support or if sent as string)
    if not cat_id:
        cat_nome = request.form.get('categoria')
        cat_obj = CategoriaAtivo.query.filter_by(nome=cat_nome).first()
        if cat_obj:
            cat_id = cat_obj.id
    
    c_id = request.form.get('carteira_id')
    c_nome = request.form.get('carteira')
    
    if c_id:
        c_obj = Carteira.query.get(c_id)
        if c_obj:
            c_nome = c_obj.nome
    
    if not c_id and c_nome:
        c_obj = Carteira.query.filter_by(nome=c_nome).first()
        c_id = c_obj.id if c_obj else None
    
    if not c_nome:
        c_nome = 'Consolidada'

    db.session.add(Ativo(
        ticker=request.form.get('ticker'), 
        categoria_id=cat_id, 
        categoria=request.form.get('categoria'), # keep legacy field for now
        data_compra=datetime.strptime(request.form.get('data'), '%Y-%m-%d'), 
        quantidade=float(request.form.get('quantidade')), 
        preco_compra=p_compra, 
        preco_atual=p_compra, 
        carteira=c_nome,
        carteira_id=c_id
    ))
    db.session.commit()
    return redirect(url_for('aportes'))

@app.route('/receber_dividendo', methods=['POST'])
@login_required
@admin_required
@log_action("Recebimento de Provento")
def receber_dividendo():
    tipo_prov = request.form.get('tipo', 'Dividendos')
    cambio = float(request.form.get('cambio', 1.0))
    valor_unitario = float(request.form.get('valor'))
    valor_convertido = valor_unitario * cambio
    cat_ativo_id = request.form.get('categoria_id')
    
    # Se não foi fornecido manualmente, tenta buscar pelo ticker
    if not cat_ativo_id:
        ativo_ref = Ativo.query.filter_by(ticker=request.form.get('ticker')).first()
        if ativo_ref:
            cat_ativo_id = ativo_ref.categoria_id
    
    # Busca o ID da categoria pelo nome
    cat_prov = CategoriaProvento.query.filter_by(nome=tipo_prov).first()
    cat_prov_id = cat_prov.id if cat_prov else None
    
    c_id = request.form.get('carteira_id')
    c_nome = request.form.get('carteira')
    
    if c_id:
        c_obj = Carteira.query.get(c_id)
        if c_obj:
            c_nome = c_obj.nome
    
    if not c_id and c_nome:
        c_obj = Carteira.query.filter_by(nome=c_nome).first()
        c_id = c_obj.id if c_obj else None
        
    if not c_nome:
        c_nome = 'Consolidada'

    db.session.add(Dividendo(
        ticker=request.form.get('ticker'), 
        valor_total=valor_convertido, 
        data_recebimento=datetime.strptime(request.form.get('data_div'), '%Y-%m-%d'),
        tipo=tipo_prov,
        categoria_provento_id=cat_prov_id,
        categoria_id=cat_ativo_id,
        carteira=c_nome,
        carteira_id=c_id
    ))
    db.session.commit()
    return redirect(url_for('proventos'))

# --- EXCLUSÕES ---

@app.route('/deletar/<int:id>')
@login_required
@log_action("Exclusão de Ativo")
def deletar(id):
    db.session.delete(Ativo.query.get_or_404(id)); db.session.commit()
    return redirect(url_for('aportes'))

@app.route('/editar_aporte', methods=['POST'])
@login_required
@admin_required
@log_action("Edição de Aporte")
def editar_aporte():
    try:
        id_aporte = request.form.get('id')
        categoria = request.form.get('categoria')
        carteira = request.form.get('carteira')
        data_compra = datetime.strptime(request.form.get('data'), '%Y-%m-%d')
        quantidade = float(request.form.get('quantidade'))
        cambio = float(request.form.get('cambio', 1.0))
        preco_unit_raw = float(request.form.get('preco_compra'))
        
        # O preço final no banco é sempre em R$
        preco_compra_final = preco_unit_raw * cambio
        
        aporte = Ativo.query.get_or_404(id_aporte)
        cat_id = request.form.get('categoria_id')
        if cat_id:
            aporte.categoria_id = cat_id
            # Also update the string field for consistency during transition
            cat_obj = CategoriaAtivo.query.get(cat_id)
            if cat_obj:
                aporte.categoria = cat_obj.nome
        else:
            aporte.categoria = categoria
            
        aporte.carteira_id = request.form.get('carteira_id')
        c_obj = Carteira.query.get(aporte.carteira_id) if aporte.carteira_id else None
        if c_obj:
            aporte.carteira = c_obj.nome
        else:
            aporte.carteira = carteira
            
        if not aporte.carteira:
            aporte.carteira = 'Consolidada'
            
        aporte.data_compra = data_compra
        aporte.quantidade = quantidade
        aporte.preco_compra = preco_compra_final
        
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Erro ao editar aporte (ID: {request.form.get('id')}): {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/editar_venda', methods=['POST'])
@login_required
@admin_required
@log_action("Edição de Venda")
def editar_venda():
    try:
        id_venda = request.form.get('id')
        data_venda = datetime.strptime(request.form.get('data'), '%Y-%m-%d')
        quantidade = float(request.form.get('quantidade'))
        preco_venda = float(request.form.get('preco_venda'))
        preco_medio_compra = float(request.form.get('preco_medio_compra'))
        
        lucro_realizado = (preco_venda - preco_medio_compra) * quantidade
        
        venda = Venda.query.get_or_404(id_venda)
        venda.data_venda = data_venda
        venda.quantidade = quantidade
        venda.preco_venda = preco_venda
        venda.preco_medio_compra = preco_medio_compra
        venda.lucro_realizado = lucro_realizado
        venda.carteira_id = request.form.get('carteira_id')
        venda.categoria_id = request.form.get('categoria_id')
        c_obj = Carteira.query.get(venda.carteira_id) if venda.carteira_id else None
        if c_obj:
            venda.carteira = c_obj.nome
        else:
            venda.carteira = request.form.get('carteira', venda.carteira)
        
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Erro ao editar venda (ID: {request.form.get('id')}): {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/deletar_venda/<int:id>')
@login_required
@log_action("Exclusão de Venda")
def deletar_venda(id):
    venda = Venda.query.get_or_404(id)
    try:
        estorno = Ativo(
            ticker=venda.ticker, 
            quantidade=venda.quantidade, 
            preco_compra=venda.preco_medio_compra, 
            preco_atual=venda.preco_medio_compra, 
            data_compra=venda.data_venda, 
            carteira=venda.carteira,
            carteira_id=venda.carteira_id
        )
        db.session.add(estorno); db.session.delete(venda); db.session.commit()
    except Exception as e:
        db.session.rollback(); logging.error(f"Erro estorno: {e}")
    return redirect(url_for('vendas_historico'))

@app.route('/editar_dividendo', methods=['POST'])
@login_required
@admin_required
@log_action("Edição de Provento")
def editar_dividendo():
    try:
        id_div = request.form.get('id')
        data_recebimento = datetime.strptime(request.form.get('data'), '%Y-%m-%d')
        valor_total = float(request.form.get('valor'))
        tipo = request.form.get('tipo')
        
        dividendo = Dividendo.query.get_or_404(id_div)
        dividendo.data_recebimento = data_recebimento
        dividendo.valor_total = valor_total
        dividendo.tipo = tipo
        
        cat_ativo_id = request.form.get('categoria_id')
        if cat_ativo_id:
            dividendo.categoria_id = cat_ativo_id
        
        # Atualiza a categoria pelo nome
        cat_prov = CategoriaProvento.query.filter_by(nome=tipo).first()
        if cat_prov:
            dividendo.categoria_provento_id = cat_prov.id
            
        dividendo.carteira_id = request.form.get('carteira_id')
        c_obj = Carteira.query.get(dividendo.carteira_id) if dividendo.carteira_id else None
        if c_obj:
            dividendo.carteira = c_obj.nome
        else:
            dividendo.carteira = request.form.get('carteira', dividendo.carteira)
        
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Erro ao editar provento (ID: {request.form.get('id')}): {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/deletar_dividendo/<int:id>')
@login_required
@log_action("Exclusão de Provento")
def deletar_dividendo(id):
    db.session.delete(Dividendo.query.get_or_404(id)); db.session.commit()
    return redirect(url_for('proventos'))

@app.route('/importar_proventos', methods=['POST'])
@login_required
@admin_required
@log_action("Importação de Proventos")
def importar_proventos():
    if 'arquivo' not in request.files:
        flash("Arquivo não enviado.", "warning")
        return redirect(url_for('proventos'))
    
    file = request.files['arquivo']
    if file.filename == '':
        flash("Nenhum arquivo selecionado.", "warning")
        return redirect(url_for('proventos'))
    
    # Captura a carteira selecionada no formulário de importação
    carteira_id_form = request.form.get('carteira_id', '')
    if carteira_id_form:
        # Grava na sessão para usar no salvar_confirmacao_proventos
        session['import_carteira_id'] = int(carteira_id_form)
    else:
        # Usa a carteira ativa da sessão como fallback
        c_ativa = get_current_wallet()
        c_obj = Carteira.query.filter_by(nome=c_ativa).first()
        session['import_carteira_id'] = c_obj.id if c_obj else None
    
    filename = file.filename.lower()
    if not (filename.endswith('.csv') or filename.endswith('.xlsx')):
        flash("Envie um arquivo .csv ou .xlsx", "danger")
        return redirect(url_for('proventos'))

    try:
        if filename.endswith('.csv'):
            # --- Lógica CSV Original ---
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            df = pd.read_csv(stream)
            df.columns = [c.strip().upper() for c in df.columns]
            
            colunas_necessarias = ['ATIVO', 'TIPO', 'DATA', 'VALOR']
            if not all(col in df.columns for col in colunas_necessarias):
                 flash(f"CSV inválido. Colunas necessárias: {', '.join(colunas_necessarias)}", "danger")
                 return redirect(url_for('proventos'))
            
            # Converte para lista de dicionários padrão para unificar processamento
            registros = []
            # Aceita várias grafias possíveis para a coluna de categoria do ativo
            col_cat_ativo = next((c for c in df.columns if c.replace(' ', '').replace('_', '') in
                                  ['CATEGORIAATIVO', 'CATATIVO', 'CATEGORIA', 'CATEGORIAATIVOS']), None)
            for _, row in df.iterrows():
                try:
                    data_str = str(row['DATA']).strip()
                    try:
                        dt = datetime.strptime(data_str, '%d/%m/%Y').date()
                    except:
                        dt = datetime.strptime(data_str, '%Y-%m-%d').date()
                    
                    valor_str = str(row['VALOR']).strip()
                    valor_raw = float(valor_str.replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.'))
                    
                    cat_ativo_nome = ''
                    if col_cat_ativo:
                        v = str(row.get(col_cat_ativo, '')).strip()
                        if v.upper() not in ('', 'NAN', 'NONE'):
                            cat_ativo_nome = v
                    
                    registros.append({
                        'ticker': str(row['ATIVO']).strip().upper(),
                        'tipo': str(row['TIPO']).strip(),
                        'data': dt.strftime('%Y-%m-%d'),
                        'valor': round(valor_raw, 2),
                        'categoria_ativo_nome': cat_ativo_nome
                    })
                except: continue

        else:
            # Lógica EXCEL — tenta detectar o formato automaticamente
            df_raw = pd.read_excel(file, header=None)
            
            # --- Tentativa 1: Formato simples (ATIVO, TIPO, DATA, VALOR) ---
            # Verifica se alguma das primeiras linhas tem as colunas esperadas
            simple_header_idx = -1
            colunas_simples = {'ATIVO', 'TIPO', 'DATA', 'VALOR'}
            for idx, row in df_raw.head(10).iterrows():
                cols_upper = {str(v).strip().upper() for v in row.values if pd.notna(v)}
                if colunas_simples.issubset(cols_upper):
                    simple_header_idx = idx
                    break
            
            if simple_header_idx != -1:
                # Formato simples: re-lê com o cabeçalho correto
                df = df_raw.iloc[simple_header_idx + 1:].copy()
                df.columns = [str(v).strip().upper() for v in df_raw.iloc[simple_header_idx].values]
                df = df.dropna(how='all')
                
                registros = []
                # Aceita várias grafias possíveis para a coluna de categoria do ativo
                col_cat_ativo = next((c for c in df.columns if isinstance(c, str) and
                                      c.replace(' ', '').replace('_', '').upper() in
                                      ['CATEGORIAATIVO', 'CATATIVO', 'CATEGORIA', 'CATEGORIAATIVOS']), None)
                for _, row in df.iterrows():
                    try:
                        ativo_val = str(row.get('ATIVO', '')).strip()
                        if not ativo_val or ativo_val.upper() == 'NAN':
                            continue
                        
                        data_val = row.get('DATA', '')
                        if pd.isna(data_val) or str(data_val).strip() == '':
                            continue
                        if isinstance(data_val, datetime):
                            dt = data_val.date()
                        else:
                            data_str = str(data_val).strip()
                            try:
                                dt = datetime.strptime(data_str, '%d/%m/%Y').date()
                            except:
                                dt = pd.to_datetime(data_str).date()
                        
                        valor_val = row.get('VALOR', 0)
                        if isinstance(valor_val, (int, float)):
                            valor_raw = float(valor_val)
                        else:
                            valor_str = str(valor_val).strip()
                            valor_raw = float(valor_str.replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.'))
                        
                        cat_ativo_nome = ''
                        if col_cat_ativo:
                            v = str(row.get(col_cat_ativo, '')).strip()
                            if v.upper() not in ('', 'NAN', 'NONE'):
                                cat_ativo_nome = v

                        registros.append({
                            'ticker': ativo_val.upper(),
                            'tipo': str(row.get('TIPO', 'Dividendos')).strip(),
                            'data': dt.strftime('%Y-%m-%d'),
                            'valor': round(valor_raw, 2),
                            'categoria_ativo_nome': cat_ativo_nome
                        })
                    except:
                        continue
                
                if not registros:
                    flash("Nenhum provento identificado no arquivo Excel.", "info")
                    return redirect(url_for('proventos'))
                
                session['import_preview'] = registros
                return redirect(url_for('confirmar_proventos'))
            
            # --- Tentativa 2: Formato Clear/XP (extrato com cabeçalho dinâmico) ---
            df = df_raw
            
            # Encontra o índice da linha de cabeçalho
            header_idx = -1
            for idx, row in df.iterrows():
                if 'Movimentação' in str(row.values) and 'Lançamento' in str(row.values):
                    header_idx = idx
                    break
            
            if header_idx == -1:
                flash("Formato de Excel não reconhecido. Use o formato simples (ATIVO, TIPO, DATA, VALOR) ou o extrato da Clear/XP.", "danger")
                return redirect(url_for('proventos'))
            
            def normalize_text(text):
                if not isinstance(text, str): return ""
                return "".join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn').upper()

            # Termos que NÃO são tickers
            ignore_words = {
                'TAXA', 'INTERMEDIACAO', 'DOADOR', 'DEBITO', 'CREDITO', 'RENDIMENTO', 
                'REMUNERACAO', 'CLIENTES', 'CBLC', 'IRRF', 'BOLSA', 'OPERACOES', 
                'S/', 'DE', 'REEMBOLSO', 'EVENTO', 'REF.', 'S', 'CAPITAL', 'JUROS',
                'FRACOES', 'ACOES'
            }
            
            registros_brutos = []
            
            # Começa o processamento a partir da linha seguinte à do cabeçalho
            for i in range(header_idx + 1, len(df)):
                row = df.iloc[i]
                try:
                    if pd.isna(row[1]) or pd.isna(row[5]):
                        continue
                    
                    desc = normalize_text(row[3])
                    data = row[1]
                    
                    if not isinstance(data, datetime) and str(data) != 'nan':
                        try:
                            data = pd.to_datetime(data).to_pydatetime()
                        except:
                            continue
                    
                    if pd.isna(data): continue
                    
                    valor = float(row[5])
                    ticker = None
                    tipo = "Dividendos"
                    
                    if "JUROS S/ CAPITAL" in desc:
                        tipo = "JCP"
                        partes = desc.split("CLIENTES ")
                        if len(partes) > 1 and partes[1].split(): ticker = partes[1].split()[0]
                    
                    elif "RENDIMENTO DE BTC" in desc or "REMUNERACAO BTC" in desc or "TAXA DE INTERMEDIACAO DOADOR" in desc:
                        tipo = "Rendimentos BTC"
                        words = re.findall(r'\b[A-Z]{4}[0-9]*\b', desc)
                        for w in words:
                            if w not in ignore_words:
                                ticker = w
                                break
                    
                    elif "FRACOES" in desc:
                        tipo = "Frações de Ações"
                        # Prioridade 1: Tentar encontrar ticker pelo padrão (4 letras + números)
                        words = re.findall(r'\b[A-Z]{4}[0-9]*\b', desc)
                        for w in words:
                            if w not in ignore_words:
                                ticker = w
                                break
                        
                        # Prioridade 2: Se não encontrar pelo padrão, tenta extrair após termos-chave
                        if not ticker:
                            for termo in ["ACOES ", "FRACOES "]:
                                partes = desc.split(termo)
                                if len(partes) > 1:
                                    # Pega todas as palavras após o termo e procura o primeiro não ignorado
                                    splitted = partes[1].split()
                                    for t_cand in splitted:
                                        if t_cand not in ignore_words:
                                            ticker = t_cand
                                            break
                                    if ticker: break
                    
                    elif "DIVIDENDOS" in desc or "RENDIMENTO" in desc:
                        tipo = "Dividendos"
                        # Clear: DIVIDENDOS DE CLIENTES ITSA4...
                        # XP: RENDIMENTOS DE CLIENTES TRXF11...
                        partes = desc.split("CLIENTES ")
                        if len(partes) > 1 and partes[1].split():
                            ticker = partes[1].split()[0]
                        else:
                            # Fallback common regex
                            words = re.findall(r'\b[A-Z]{4}[0-9]*\b', desc)
                            for w in words:
                                if w not in ignore_words:
                                    ticker = w
                                    break
                    
                    elif "RESTITUICAO DE CAPITAL" in desc:
                        tipo = "Restituição"
                        partes = desc.split("CLIENTES ")
                        if len(partes) > 1 and partes[1].split(): ticker = partes[1].split()[0]
                    
                    elif "CREDITO DE REEMBOLSO" in desc:
                        tipo = "Rendimentos"
                        words = re.findall(r'\b[A-Z]{4}[0-9]*\b', desc)
                        for w in words:
                            if w not in ignore_words:
                                ticker = w
                                break
                        if not ticker and desc.split(): ticker = desc.split()[-1]

                    if ticker:
                        ticker = ticker.strip().upper()
                        
                        # Normalização de FIIs: 12 e 13 (direitos/frações) viram 11
                        if ticker.endswith(("12", "13")):
                            ticker = ticker[:-2] + "11"

                        # FIIs (geralmente finais 11) são 'Rendimentos'
                        if tipo == "Dividendos" and ticker.endswith("11"):
                            tipo = "Rendimentos"

                        registros_brutos.append({
                            'ticker': ticker,
                            'tipo': tipo,
                            'data': data.date(),
                            'valor': valor
                        })
                except:
                    continue

            df_agg = pd.DataFrame(registros_brutos)
            if df_agg.empty:
                flash("Nenhum provento identificado no arquivo.", "info")
                return redirect(url_for('proventos'))
                
            # --- Ajuste de Tickers Inconsistentes (ex: ABEV vs ABEV3) ---
            # Para cada (data, tipo), se houver um ticker que é prefixo de outro mais longo, 
            # unificamos no mais longo (o que tem o número).
            def unificar_tickers(group):
                if len(group) <= 1: return group
                # Ordena por tamanho descendente para pegar o 'ABEV3' antes do 'ABEV'
                g_sorted = group.sort_values(by='ticker', key=lambda x: x.str.len(), ascending=False)
                tickers = g_sorted['ticker'].unique()
                mapping = {}
                for i, t_long in enumerate(tickers):
                    for t_short in tickers[i+1:]:
                        if t_long.startswith(t_short) and len(t_long) > len(t_short):
                            mapping[t_short] = t_long
                if mapping:
                    group['ticker'] = group['ticker'].replace(mapping)
                return group

            df_agg = df_agg.groupby(['data', 'tipo'], group_keys=False).apply(unificar_tickers)

            df_agg = df_agg.groupby(['ticker', 'data', 'tipo'], as_index=False)['valor'].sum()
            
            registros = []
            for item in df_agg.to_dict('records'):
                registros.append({
                    'ticker': item['ticker'],
                    'tipo': item['tipo'],
                    'data': item['data'].strftime('%Y-%m-%d'),
                    'valor': round(float(item['valor']), 2)
                })

        # --- Redirecionar para Confirmação ---
        if not registros:
            flash("Nenhum provento identificado no arquivo.", "info")
            return redirect(url_for('proventos'))
            
        session['import_preview'] = registros
        return redirect(url_for('confirmar_proventos'))
        
    except Exception as e:
        logging.error(f"Erro na importação: {e}")
        flash(f"Erro ao processar arquivo: {str(e)}", "danger")
        
    return redirect(url_for('proventos'))

@app.route('/importar_aportes', methods=['POST'])
@login_required
@admin_required
@log_action("Importação de Aportes")
def importar_aportes():
    if 'arquivo' not in request.files:
        flash("Arquivo não enviado.", "warning")
        return redirect(url_for('aportes'))
    
    file = request.files['arquivo']
    if file.filename == '':
        flash("Nenhum arquivo selecionado.", "warning")
        return redirect(url_for('aportes'))
    
    filename = file.filename.lower()
    if not (filename.endswith('.csv') or filename.endswith('.xlsx')):
        flash("Envie um arquivo .csv ou .xlsx", "danger")
        return redirect(url_for('aportes'))

    try:
        if filename.endswith('.csv'):
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            df = pd.read_csv(stream)
            df.columns = [c.strip().upper() for c in df.columns]
        else:
            df = pd.read_excel(file)
            df.columns = [c.strip().upper() for c in df.columns]

        colunas_necessarias = ['ATIVO', 'TIPO', 'DATA', 'VALOR']
        if not all(col in df.columns for col in colunas_necessarias):
            flash(f"Arquivo inválido. Colunas necessárias: {', '.join(colunas_necessarias)}", "danger")
            return redirect(url_for('aportes'))
        
        registros = []
        for _, row in df.iterrows():
            try:
                data_str = str(row['DATA']).strip()
                try:
                    dt = datetime.strptime(data_str, '%d/%m/%Y').date()
                except:
                    dt = pd.to_datetime(data_str).date()
                
                valor_str = str(row['VALOR']).strip()
                if isinstance(row['VALOR'], (int, float)):
                    valor_raw = float(row['VALOR'])
                else:
                    valor_raw = float(valor_str.replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.'))
                
                registros.append({
                    'ticker': str(row['ATIVO']).strip().upper(),
                    'categoria': str(row['TIPO']).strip(),
                    'data': dt.strftime('%Y-%m-%d'),
                    'valor': round(valor_raw, 2)
                })
            except: continue

        if not registros:
            flash("Nenhum aporte identificado no arquivo.", "info")
            return redirect(url_for('aportes'))
            
        session['import_aportes_preview'] = registros
        return redirect(url_for('confirmar_aportes'))
        
    except Exception as e:
        logging.error(f"Erro na importação de aportes: {e}")
        flash(f"Erro ao processar arquivo: {str(e)}", "danger")
        
    return redirect(url_for('aportes'))

@app.route('/confirmar_aportes')
@login_required
def confirmar_aportes():
    registros = session.get('import_aportes_preview', [])
    if not registros:
        flash("Nenhuma importação de aporte pendente.", "warning")
        return redirect(url_for('aportes'))
    
    categorias_ativos = CategoriaAtivo.query.order_by(CategoriaAtivo.nome).all()
    return render_template('confirmar_proventos.html', registros=registros, is_aporte=True, categorias_ativos=categorias_ativos)

@app.route('/salvar_confirmacao_aportes', methods=['POST'])
@login_required
@admin_required
def salvar_confirmacao_aportes():
    try:
        tickers = request.form.getlist('ticker[]')
        categorias = request.form.getlist('tipo[]')
        datas = request.form.getlist('data[]')
        valores = request.form.getlist('valor[]')
        excluir = request.form.getlist('excluir[]')

        c_ativa = get_current_wallet()
        c_obj = Carteira.query.filter_by(nome=c_ativa).first()
        c_id = c_obj.id if c_obj else None
        
        count = 0
        duplicados = 0
        
        for i in range(len(tickers)):
            if str(i) in excluir:
                continue
            
            ticker = tickers[i].strip().upper()
            cat_nome = categorias[i].strip()
            data_aporte = datetime.strptime(datas[i], '%Y-%m-%d').date()
            valor_aporte = Decimal(valores[i].replace(',', '.'))
            
            # Verificação de Duplicidade: mesmo ticker, data, valor e carteira
            existente = Ativo.query.filter_by(
                ticker=ticker,
                data_compra=data_aporte,
                preco_compra=valor_aporte,
                carteira=c_ativa
            ).first()

            if existente:
                duplicados += 1
                continue

            cat_obj = CategoriaAtivo.query.filter_by(nome=cat_nome).first()
            cat_id = cat_obj.id if cat_obj else None
            
            db.session.add(Ativo(
                ticker=ticker,
                categoria_id=cat_id,
                categoria=cat_nome,
                data_compra=data_aporte,
                quantidade=1.0,
                preco_compra=valor_aporte,
                preco_atual=valor_aporte,
                carteira=c_ativa,
                carteira_id=c_id
            ))
            count += 1
            
        db.session.commit()
        session.pop('import_aportes_preview', None)
        
        msg_duplicados = f" ({duplicados} duplicados ignorados)" if duplicados > 0 else ""
        if count > 0:
            flash(f"Sucesso! {count} aportes importados.{msg_duplicados}", "success")
        else:
            flash(f"Nenhum novo aporte importado.{msg_duplicados}", "info")
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Erro ao salvar aportes: {e}")
        flash(f"Erro ao salvar aportes: {str(e)}", "danger")
        
    return redirect(url_for('aportes'))

@app.route('/confirmar_proventos')
@login_required
def confirmar_proventos():
    registros = session.get('import_preview', [])
    if not registros:
        flash("Nenhuma importação pendente.", "warning")
        return redirect(url_for('proventos'))
    
    categorias_proventos = CategoriaProvento.query.order_by(CategoriaProvento.nome).all()
    categorias_ativos = CategoriaAtivo.query.order_by(CategoriaAtivo.nome).all()

    # Tenta pré-selecionar a categoria do ativo para cada registro
    for reg in registros:
        # Se já veio do arquivo (categoria_ativo_nome preenchida), usa ela
        cat_nome_arquivo = reg.get('categoria_ativo_nome', '')
        if cat_nome_arquivo and not reg.get('categoria_ativo_id'):
            cat_obj = CategoriaAtivo.query.filter(
                db.func.lower(CategoriaAtivo.nome) == cat_nome_arquivo.lower()
            ).first()
            reg['categoria_ativo_id'] = cat_obj.id if cat_obj else None
            reg['categoria_ativo_nome'] = cat_obj.nome if cat_obj else cat_nome_arquivo
        elif not reg.get('categoria_ativo_id'):
            # Fallback: busca pelo último ativo cadastrado com esse ticker
            ativo_ref = Ativo.query.filter_by(ticker=reg['ticker']).order_by(Ativo.data_compra.desc()).first()
            reg['categoria_ativo_id'] = ativo_ref.categoria_id if ativo_ref else None
            reg['categoria_ativo_nome'] = ativo_ref.categoria if ativo_ref else ''

    return render_template('confirmar_proventos.html',
                           registros=registros,
                           categorias_proventos=categorias_proventos,
                           categorias_ativos=categorias_ativos)

@app.route('/salvar_confirmacao_proventos', methods=['POST'])
@login_required
@admin_required
def salvar_confirmacao_proventos():
    try:
        # Pega os dados enviados pelo formulário
        tickers = request.form.getlist('ticker[]')
        tipos = request.form.getlist('tipo[]')
        datas = request.form.getlist('data[]')
        valores = request.form.getlist('valor[]')
        categorias_ativo = request.form.getlist('categoria_ativo[]')
        excluir = request.form.getlist('excluir[]') # Índices para excluir

        c_ativa = get_current_wallet()
        # Prioriza a carteira definida durante a importação do arquivo
        import_carteira_id = session.get('import_carteira_id')
        if import_carteira_id:
            c_obj = Carteira.query.get(import_carteira_id)
            c_id = import_carteira_id
            c_ativa = c_obj.nome if c_obj else c_ativa
        else:
            c_obj = Carteira.query.filter_by(nome=c_ativa).first()
            c_id = c_obj.id if c_obj else None

        registros_finais = []
        for i in range(len(tickers)):
            # Se o índice i estiver na lista de exclusão, pula
            if str(i) in excluir:
                continue

            cat_ativo_val = categorias_ativo[i].strip() if i < len(categorias_ativo) else ''
            registros_finais.append({
                'ticker': tickers[i].strip().upper(),
                'tipo': tipos[i].strip(),
                'data': datetime.strptime(datas[i], '%Y-%m-%d').date(),
                'valor': Decimal(valores[i].replace(',', '.')),
                'categoria_ativo': cat_ativo_val
            })

        count = 0
        duplicados = 0
        tickers_importados = set()
        
        # Mapeamento de categorias de proventos para otimizar busca no loop
        cat_prov_map = {c.nome: c.id for c in CategoriaProvento.query.all()}
        # Mapeamento de categorias de ativos (id -> id, nome -> id)
        cat_ativo_map = {c.nome: c.id for c in CategoriaAtivo.query.all()}
        cat_ativo_id_map = {str(c.id): c.id for c in CategoriaAtivo.query.all()}
        # Cache de categoria por ticker (busca no ativo cadastrado)
        ticker_cat_cache = {}
        
        for reg in registros_finais:
            # Verificação de Duplicidade
            existente = Dividendo.query.filter_by(
                ticker=reg['ticker'],
                tipo=reg['tipo'],
                data_recebimento=reg['data'],
                valor_total=reg['valor'],
                carteira_id=c_id
            ).first()

            if existente:
                duplicados += 1
                continue
            
            # Resolve categoria_id do ativo
            cat_id = None
            cat_ativo_val = reg.get('categoria_ativo', '')
            if cat_ativo_val:
                # Tenta pelo ID numérico primeiro, depois pelo nome
                cat_id = cat_ativo_id_map.get(cat_ativo_val) or cat_ativo_map.get(cat_ativo_val)
            
            if not cat_id:
                # Fallback: busca pela última compra do ticker na tabela de ativos
                ticker_key = reg['ticker']
                if ticker_key not in ticker_cat_cache:
                    ativo_ref = Ativo.query.filter_by(ticker=ticker_key).order_by(Ativo.data_compra.desc()).first()
                    ticker_cat_cache[ticker_key] = ativo_ref.categoria_id if ativo_ref else None
                cat_id = ticker_cat_cache[ticker_key]

            db.session.add(Dividendo(
                ticker=reg['ticker'],
                tipo=reg['tipo'],
                categoria_provento_id=cat_prov_map.get(reg['tipo']),
                categoria_id=cat_id,
                data_recebimento=reg['data'],
                valor_total=reg['valor'],
                carteira=c_ativa,
                carteira_id=c_id
            ))
            count += 1
            tickers_importados.add(reg['ticker'])
            
        db.session.commit()
        session.pop('import_preview', None)
        
        msg_duplicados = f" ({duplicados} duplicados ignorados)" if duplicados > 0 else ""
        if count > 0:
            tickers_str = ", ".join(sorted(tickers_importados))
            msg = f"Sucesso! {count} proventos importados: {tickers_str}.{msg_duplicados}"
            user_logger.info(f"USUÁRIO: {current_user.username} | AÇÃO: Conclusão de Importação | DETALHES: {msg} | IP: {request.remote_addr}")
        else:
            msg = f"Nenhum novo provento importado.{msg_duplicados}"
            user_logger.info(f"USUÁRIO: {current_user.username} | AÇÃO: Conclusão de Importação | DETALHES: {msg} | IP: {request.remote_addr}")

        flash(msg, "success" if count > 0 else "info")
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Erro ao salvar confirmação: {e}")
        flash(f"Erro ao salvar proventos: {str(e)}", "danger")

    return redirect(url_for('proventos'))

@app.route('/atualizar_preco_manual', methods=['POST'])
@login_required
@admin_required
def atualizar_preco_manual():
    ticker = request.form.get('ticker'); novo_p = float(request.form.get('preco_atual'))
    for a in Ativo.query.filter_by(ticker=ticker).all(): a.preco_atual = novo_p
    db.session.commit(); return redirect(url_for('index'))

# --- CATEGORIAS DE ATIVOS ---

@app.route('/categorias_ativos')
@login_required
def categorias_ativos():
    # Admin vê globais + as de suas carteiras
    if is_superadmin():
        categorias = CategoriaAtivo.query.order_by(CategoriaAtivo.nome).all()
    else:
        wallet_ids = [c.id for c in current_user.carteiras]
        categorias = CategoriaAtivo.query.filter(
            (CategoriaAtivo.carteira_id.is_(None)) | (CategoriaAtivo.carteira_id.in_(wallet_ids))
        ).order_by(CategoriaAtivo.nome).all()
        
    return render_template('categorias_ativos.html', categorias=categorias)

@app.route('/categorias_ativos/add', methods=['POST'])
@login_required
@admin_required
@log_action("Adicionar Categoria de Ativo")
def add_categoria_ativo():
    nome = request.form.get('nome')
    if nome:
        if not CategoriaAtivo.query.filter_by(nome=nome).first():
            nova = CategoriaAtivo(nome=nome)
            
            # Se for Admin, vincula a uma carteira que o usuário possui
            if not is_superadmin():
                c_ativa = get_current_wallet()
                c_obj = Carteira.query.filter_by(nome=c_ativa).first()
                
                # Se estiver em 'Consolidada' ou em uma carteira que não possui, usa a primeira disponível
                if c_ativa == 'Consolidada' or not c_obj or c_obj not in current_user.carteiras:
                    if current_user.carteiras:
                        nova.carteira_id = current_user.carteiras[0].id
                else:
                    nova.carteira_id = c_obj.id
            
            db.session.add(nova)
            db.session.commit()
            flash(f"Categoria '{nome}' adicionada com sucesso!", "success")
        else:
            flash(f"Categoria '{nome}' já existe.", "warning")
    return redirect(url_for('categorias_ativos'))

@app.route('/categorias_ativos/update', methods=['POST'])
@login_required
@admin_required
@log_action("Atualizar Categoria de Ativo")
def update_categoria_ativo():
    cat_id = request.form.get('id')
    novo_nome = request.form.get('valor')
    cat = CategoriaAtivo.query.get(cat_id)
    
    if cat:
        # Verifica permissão: Somente SuperAdmin altera GLOBAL. Admin altera se for de sua carteira.
        if cat.carteira_id is None:
            if not is_superadmin():
                flash("Apenas SuperAdmins podem alterar categorias globais.", "danger")
                return redirect(url_for('categorias_ativos'))
        elif not is_superadmin() and cat.carteira_id not in [c.id for c in current_user.carteiras]:
            flash("Você não tem permissão para alterar esta categoria.", "danger")
            return redirect(url_for('categorias_ativos'))

        if novo_nome:
            old_nome = cat.nome
            cat.nome = novo_nome
            db.session.commit()
            flash(f"Categoria '{old_nome}' alterada para '{novo_nome}'.", "success")
    return redirect(url_for('categorias_ativos'))

@app.route('/categorias_ativos/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
@log_action("Deletar Categoria de Ativo")
def delete_categoria_ativo(id):
    cat = CategoriaAtivo.query.get(id)
    if cat:
        # Verifica permissão: Somente SuperAdmin deleta GLOBAL.
        if cat.carteira_id is None:
            if not is_superadmin():
                flash("Apenas SuperAdmins podem remover categorias globais.", "danger")
                return redirect(url_for('categorias_ativos'))
        elif not is_superadmin() and cat.carteira_id not in [c.id for c in current_user.carteiras]:
            flash("Você não tem permissão para remover esta categoria.", "danger")
            return redirect(url_for('categorias_ativos'))

        nome = cat.nome
        db.session.delete(cat)
        db.session.commit()
        flash(f"Categoria '{nome}' removida com sucesso!", "success")
    return redirect(url_for('categorias_ativos'))

# --- CATEGORIAS DE PROVENTOS ---

@app.route('/categoria_proventos')
@login_required
def categoria_proventos():
    # Admin vê globais + as de suas carteiras
    if is_superadmin():
        categorias = CategoriaProvento.query.order_by(CategoriaProvento.nome).all()
    else:
        wallet_ids = [c.id for c in current_user.carteiras]
        categorias = CategoriaProvento.query.filter(
            (CategoriaProvento.carteira_id.is_(None)) | (CategoriaProvento.carteira_id.in_(wallet_ids))
        ).order_by(CategoriaProvento.nome).all()
        
    return render_template('categoria_proventos.html', categorias=categorias)

@app.route('/categoria_proventos/add', methods=['POST'])
@login_required
@admin_required
@log_action("Adicionar Categoria de Provento")
def add_categoria_provento():
    nome = request.form.get('nome')
    if nome:
        if not CategoriaProvento.query.filter_by(nome=nome).first():
            nova = CategoriaProvento(nome=nome)
            
            # Se for Admin, vincula a uma carteira que o usuário possui
            if not is_superadmin():
                c_ativa = get_current_wallet()
                c_obj = Carteira.query.filter_by(nome=c_ativa).first()
                
                # Se estiver em 'Consolidada' ou em uma carteira que não possui, usa a primeira disponível
                if c_ativa == 'Consolidada' or not c_obj or c_obj not in current_user.carteiras:
                    if current_user.carteiras:
                        nova.carteira_id = current_user.carteiras[0].id
                else:
                    nova.carteira_id = c_obj.id

            db.session.add(nova)
            db.session.commit()
            flash(f"Categoria '{nome}' adicionada com sucesso!", "success")
        else:
            flash(f"Categoria '{nome}' já existe.", "warning")
    return redirect(url_for('categoria_proventos'))

@app.route('/categoria_proventos/update', methods=['POST'])
@login_required
@admin_required
@log_action("Atualizar Categoria de Provento")
def update_categoria_provento():
    cat_id = request.form.get('id')
    novo_nome = request.form.get('valor')
    cat = CategoriaProvento.query.get(cat_id)
    
    if cat:
        # Verifica permissão
        if cat.carteira_id is None:
            if not is_superadmin():
                flash("Apenas SuperAdmins podem alterar categorias globais.", "danger")
                return redirect(url_for('categoria_proventos'))
        elif not is_superadmin() and cat.carteira_id not in [c.id for c in current_user.carteiras]:
            flash("Você não tem permissão para alterar esta categoria.", "danger")
            return redirect(url_for('categoria_proventos'))

        if novo_nome:
            old_nome = cat.nome
            cat.nome = novo_nome
            db.session.commit()
            flash(f"Categoria '{old_nome}' alterada para '{novo_nome}'.", "success")
    return redirect(url_for('categoria_proventos'))

@app.route('/categoria_proventos/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
@log_action("Deletar Categoria de Provento")
def delete_categoria_provento(id):
    cat = CategoriaProvento.query.get(id)
    if cat:
        # Verifica permissão
        if cat.carteira_id is None:
            if not is_superadmin():
                flash("Apenas SuperAdmins podem remover categorias globais.", "danger")
                return redirect(url_for('categoria_proventos'))
        elif not is_superadmin() and cat.carteira_id not in [c.id for c in current_user.carteiras]:
            flash("Você não tem permissão para remover esta categoria.", "danger")
            return redirect(url_for('categoria_proventos'))

        nome = cat.nome
        db.session.delete(cat)
        db.session.commit()
        flash(f"Categoria '{nome}' removida com sucesso!", "success")
    return redirect(url_for('categoria_proventos'))

# --- CARTEIRAS ---

@app.route('/carteiras')
@login_required
def carteiras():
    # Fetch carteiras to manage
    if is_superadmin():
        carteiras_list = Carteira.query.order_by(Carteira.nome).all()
    else:
        # Admin vê apenas suas carteiras
        carteiras_list = sorted(list(current_user.carteiras), key=lambda x: x.nome)
    
    return render_template('carteiras.html', carteiras=carteiras_list)

@app.route('/carteiras/add', methods=['POST'])
@login_required
@admin_required
@log_action("Adicionar Carteira")
def add_carteira():
    nome = request.form.get('nome')
    if nome:
        if not Carteira.query.filter_by(nome=nome).first():
            nova = Carteira(nome=nome)
            db.session.add(nova)
            
            # Se for Admin (não SuperAdmin), vincula a nova carteira ao criador
            if not is_superadmin():
                current_user.carteiras.append(nova)
                
            db.session.commit()
            flash(f"Carteira '{nome}' adicionada com sucesso!", "success")
        else:
            flash(f"Carteira '{nome}' já existe.", "warning")
    return redirect(url_for('carteiras'))

@app.route('/carteiras/update', methods=['POST'])
@login_required
@admin_required
@log_action("Atualizar Carteira")
def update_carteira():
    c_id = request.form.get('id')
    novo_nome = request.form.get('valor')
    c = Carteira.query.get(c_id)
    
    if c:
        # Verifica permissão
        if not is_superadmin() and c not in current_user.carteiras:
            flash("Você não tem permissão para alterar esta carteira.", "danger")
            return redirect(url_for('carteiras'))

        if novo_nome:
            old_nome = c.nome
            # Check if new name already exists
            existente = Carteira.query.filter_by(nome=novo_nome).first()
            if existente and existente.id != int(c_id):
                flash(f"Já existe uma carteira com o nome '{novo_nome}'.", "danger")
            else:
                c.nome = novo_nome
                db.session.commit()
                flash(f"Carteira '{old_nome}' alterada para '{novo_nome}'.", "success")
    return redirect(url_for('carteiras'))

@app.route('/carteiras/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
@log_action("Deletar Carteira")
def delete_carteira(id):
    c = Carteira.query.get(id)
    if c:
        # Verifica permissão
        if not is_superadmin() and c not in current_user.carteiras:
            flash("Você não tem permissão para remover esta carteira.", "danger")
            return redirect(url_for('carteiras'))

        nome = c.nome
        # Prevent deletion of 'Consolidada' if it's considered system default (optional)
        if nome == 'Consolidada':
            flash("A carteira 'Consolidada' é protegida e não pode ser removida.", "danger")
            return redirect(url_for('carteiras'))
            
        # Check if there are assets linked
        has_assets = Ativo.query.filter_by(carteira_id=id).first()
        if has_assets:
            flash(f"Não é possível remover a carteira '{nome}' pois existem ativos vinculados a ela.", "danger")
        else:
            # Remove associações de usuários antes de deletar a carteira
            # (Opcional dependendo da configuração de cascade, mas garante limpeza)
            c.usuarios = [] 
            db.session.delete(c)
            db.session.commit()
            flash(f"Carteira '{nome}' removida com sucesso!", "success")
    return redirect(url_for('carteiras'))

# --- APIs GRÁFICOS ---

@app.route('/dados_comparativos')
@login_required
def dados_comparativos():
    import requests
    import pandas as pd
    from datetime import datetime

    BRAPI_TOKEN = "agUUa4zyvQRm9PK7YCm9QL"
    
    try:
        # 1. Busca os dados (Exemplo com ITSA4 e IBOV)
        url = f"https://brapi.dev/api/quote/ITSA4,%5EBVSP?range=3mo&interval=1d&token={BRAPI_TOKEN}"
        res = requests.get(url, timeout=15)
        dados_api = res.json().get('results', [])
        
        # 2. Usaremos o Pandas para garantir que a linha do tempo seja perfeita
        df_principal = pd.DataFrame()

        for ativo in dados_api:
            symbol = ativo['symbol']
            hist = ativo.get('historicalDataPrice', [])
            if hist:
                df_temp = pd.DataFrame(hist)
                # Converter timestamp para data real
                df_temp['date'] = pd.to_datetime(df_temp['date'], unit='s').dt.normalize()
                df_temp = df_temp.set_index('date')
                
                # Calcular rentabilidade acumulada (começando em 0%)
                preco_inicial = df_temp['close'].iloc[0]
                df_temp[symbol] = ((df_temp['close'] / preco_inicial) - 1) * 100
                
                if df_principal.empty:
                    df_principal = df_temp[[symbol]]
                else:
                    df_principal = df_principal.join(df_temp[[symbol]], how='outer')

        # 3. O SEGREDO: Ordenar pelo índice de data e preencher buracos (feriados)
        df_principal = df_principal.sort_index().ffill().fillna(0)

        # 4. Preparar colunas para o Google Charts
        tickers = [col for col in df_principal.columns]
        colunas_json = ["Data"] + tickers
        
        rows_json = []
        for dt, row in df_principal.iterrows():
            # Aqui a data vira texto APENAS para exibição, mas já está na ordem certa
            linha = [dt.strftime('%d/%m')]
            for t in tickers:
                linha.append(round(float(row[t]), 2))
            rows_json.append(linha)

        return jsonify({"cols": colunas_json, "rows": rows_json})

    except Exception as e:
        return jsonify({"cols": ["Data"], "rows": [], "error": str(e)})

@app.route('/dados_desempenho_carteira')
@login_required
def dados_desempenho_carteira():
    BRAPI_TOKEN = "agUUa4zyvQRm9PK7YCm9QL"
    selected_ticker = request.args.get('ticker')
    periodo = request.args.get('periodo', '6mo')

    # Mapeamento de período
    range_map = {
        '1mo':  '1mo',
        '3mo':  '3mo',
        '6mo':  '6mo',
        '1y':   '1y',
        'ytd':  '1y',  # filtrado em Python
    }
    api_range = range_map.get(periodo, '6mo')

    # 1. Obter Ativos de Renda Variável (fora do try para garantir retorno parcial no selector se o resto falhar)
    try:
        c_ativa = get_current_wallet()
        query_rv = get_authorized_query(Ativo, c_ativa).filter(Ativo.categoria.in_(['Ações', 'FIIs', 'BDRs', 'ETFs']))
        ativos_rv = query_rv.all()
        tickers_disponiveis = sorted(list(set([a.ticker for a in ativos_rv])))
    except Exception as e:
        logging.error(f"Erro ao listar tickers: {e}")
        return jsonify({"cols": [], "rows": [], "error": "Erro ao acessar banco de dados", "tickers": []})

    if not tickers_disponiveis:
        return jsonify({"cols": [], "rows": [], "tickers": []})

    try:
        # 1.1 Obter Proventos (para Total Return)
        query_divs = get_authorized_query(Dividendo, c_ativa)
        proventos_all = query_divs.all()

        # Determinar quais ativos buscar e rótulo do gráfico
        is_category = False
        cat_filter = []
        
        if selected_ticker == 'cat_acoes':
            cat_filter = ['Ações', 'BDRs', 'ETFs']
            label_principal = "Ações (incl. BDR/ETF)"
            is_category = True
            tickers_to_fetch = sorted(list(set([a.ticker for a in ativos_rv if a.categoria in cat_filter])))
        elif selected_ticker == 'cat_fiis':
            cat_filter = ['FIIs']
            label_principal = "FIIs"
            is_category = True
            tickers_to_fetch = sorted(list(set([a.ticker for a in ativos_rv if a.categoria in cat_filter])))
        elif selected_ticker and selected_ticker != 'carteira' and selected_ticker != 'TODOS':
            # Verifica se o usuário tem acesso ao ticker filtrando pela query autorizada
            exists = get_authorized_query(Ativo, c_ativa).filter_by(ticker=selected_ticker).first()
            if not exists:
                tickers_to_fetch = []
            else:
                tickers_to_fetch = [selected_ticker]
            label_principal = selected_ticker
        else:
            tickers_to_fetch = tickers_disponiveis
            label_principal = "Carteira"

        # 2. Buscar Dados Históricos (Ativos + Benchmarks)
        # Usamos XFIX11 como proxy para o IFIX
        # Usamos LFTS11 como proxy para o CDI
        # Usamos IMAB11 como proxy para o IMA-B
        all_tickers = list(set(tickers_to_fetch + ["^BVSP", "IFIX", "XFIX11", "LFTS11", "IMAB11"]))
        url = f"https://brapi.dev/api/quote/{','.join(all_tickers)}?range={api_range}&interval=1d&token={BRAPI_TOKEN}"
        res = requests.get(url, timeout=20)
        dados_api = res.json().get('results', [])
        
        df_precos = pd.DataFrame()
        benchmark_map = {
            "^BVSP": "IBOV", 
            "IFIX": "IFIX", "IFIX.SA": "IFIX", "XFIX11": "IFIX",
            "LFTS11": "CDI",
            "IMAB11": "IMA-B"
        }
        
        for ativo in dados_api:
            symbol = ativo.get('symbol', '')
            requested_symbol = ativo.get('requested_symbol', symbol) # Alguns retornam symbol diferente
            hist = ativo.get('historicalDataPrice', [])
            if hist:
                df_temp = pd.DataFrame(hist)
                df_temp['date'] = pd.to_datetime(df_temp['date'], unit='s').dt.normalize()
                df_temp = df_temp.set_index('date')
                
                # Usamos o solicitado ou mapeado para as colunas
                col_name = symbol
                if requested_symbol in benchmark_map: col_name = benchmark_map[requested_symbol]
                elif symbol in benchmark_map: col_name = benchmark_map[symbol]
                
                # Controle de Qualidade: Não sobrescrever histórico longo por um curto
                if col_name in ["IBOV", "IFIX", "CDI", "IMA-B"] and col_name in df_precos.columns:
                    if len(hist) < len(df_precos[col_name].dropna()):
                        logging.info(f"Pulando {symbol} para {col_name} pois ja temos melhor historico.")
                        continue
                
                df_precos[col_name] = df_temp['close']

        df_precos = df_precos.sort_index().ffill().dropna(how='all')
        if df_precos.empty:
            logging.warning("BRAPI retornou dados vazios para os tickers solicitados.")
            return jsonify({"cols": [], "rows": [], "tickers": tickers_disponiveis, "error": "API de cotações não retornou dados para o período."})

        # 3. Calcular Performance
        df_performance = pd.DataFrame(index=df_precos.index)
        
        if selected_ticker and selected_ticker not in ['carteira', 'cat_acoes', 'cat_fiis', 'TODOS']:
            # Performance de UM Ativo Único
            q_lotes = get_authorized_query(Ativo, c_ativa).filter_by(ticker=selected_ticker)
            q_vendas = get_authorized_query(Venda, c_ativa).filter_by(ticker=selected_ticker)
            lotes = q_lotes.all()
            vendas = q_vendas.all()
            tickers_group = [selected_ticker]
        else:
            # Reconstruir Grupo Histórico (Carteira Completa ou Categoria)
            if is_category:
                q_lotes = get_authorized_query(Ativo, c_ativa).filter(Ativo.categoria.in_(cat_filter))
                q_vendas = get_authorized_query(Venda, c_ativa).filter(Venda.ticker.in_(tickers_to_fetch))
                lotes = q_lotes.all()
                vendas = q_vendas.all()
                tickers_group = tickers_to_fetch
            else:
                q_lotes = get_authorized_query(Ativo, c_ativa).filter(Ativo.categoria.in_(['Ações', 'FIIs', 'BDRs', 'ETFs']))
                q_vendas = get_authorized_query(Venda, c_ativa)
                lotes = q_lotes.all()
                vendas = q_vendas.all()
                tickers_group = tickers_disponiveis
            
        # 4. Cálculo de Performance (Unificado com Proventos)
        if selected_ticker and selected_ticker not in ['carteira', 'cat_acoes', 'cat_fiis']:
            # Time-Weighted Return (Price-based) para Ativo Único
            # Isso evita distorções por aportes/vendas (mudanças no PM)
            if selected_ticker in df_precos.columns:
                series = df_precos[selected_ticker].dropna()
                if not series.empty:
                    p_inicial = series.iloc[0]
                    # Nota: Para ações, o ideal seria somar Proventos_por_Cota, mas aqui 
                    # usamos a variação do preço que já atende ETFs como BOVA11.
                    df_performance['Selecionado'] = ((df_precos[selected_ticker] / p_inicial) - 1) * 100
                else:
                    df_performance['Selecionado'] = 0
            else:
                df_performance['Selecionado'] = 0
        else:
            # Money-Weighted Return (Baseado no Custo) para Carteira/Categoria
            proventos_grupo = [p for p in proventos_all if p.ticker in tickers_group]
            df_hist_val = pd.DataFrame(index=df_precos.index)
            df_hist_val['Valor_Mercado'] = 0.0
            df_hist_val['Custo_Aquisicao'] = 0.0
            df_hist_val['Proventos_Acumulados'] = 0.0

            for date in df_hist_val.index:
                total_dia = 0.0
                custo_dia = 0.0
                for t in tickers_group:
                    qtd_na_data = sum(float(l.quantidade) for l in lotes if l.ticker == t and l.data_compra <= date.date())
                    qtd_na_data += sum(float(v.quantidade) for v in vendas if v.ticker == t and v.data_venda > date.date())
                    
                    custo_na_data = sum(float(l.quantidade) * float(l.preco_compra) for l in lotes if l.ticker == t and l.data_compra <= date.date())
                    custo_na_data += sum(float(v.quantidade) * float(v.preco_medio_compra) for v in vendas if v.ticker == t and v.data_venda > date.date())
                    
                    if t in df_precos.columns:
                        preco = df_precos.loc[date, t]
                        if not pd.isna(preco):
                            total_dia += (qtd_na_data * float(preco))
                            custo_dia += custo_na_data

                prov_na_data = sum(float(p.valor_total) for p in proventos_grupo if p.data_recebimento <= date.date())
                
                df_hist_val.loc[date, 'Valor_Mercado'] = total_dia
                df_hist_val.loc[date, 'Custo_Aquisicao'] = custo_dia
                df_hist_val.loc[date, 'Proventos_Acumulados'] = prov_na_data

            # Total Return: (Valor Mercado + Proventos) / Custo - 1
            df_performance['Selecionado'] = (((df_hist_val['Valor_Mercado'] + df_hist_val['Proventos_Acumulados']) / df_hist_val['Custo_Aquisicao']) - 1) * 100
            df_performance['Selecionado'] = df_performance['Selecionado'].fillna(0)

            # Normalizar para o início do período (começar em 0%)
            if not df_performance['Selecionado'].empty:
                p_inicial_sel = 1 + (df_performance['Selecionado'].iloc[0] / 100)
                if p_inicial_sel != 0:
                    df_performance['Selecionado'] = (((1 + (df_performance['Selecionado'] / 100)) / p_inicial_sel) - 1) * 100

        # Benchmarks Safely
        for b in ["IBOV", "IFIX", "CDI", "IMA-B"]:
            if b in df_precos.columns:
                series = df_precos[b].dropna()
                if not series.empty:
                    p_inicial = series.iloc[0]
                    df_performance[b] = ((df_precos[b] / p_inicial) - 1) * 100
                else:
                    df_performance[b] = 0
            else:
                df_performance[b] = 0

        # IPCA Estimado
        dias = (df_performance.index - df_performance.index[0]).days
        df_performance['IPCA'] = (1.00013 ** dias - 1) * 100

        df_performance = df_performance.ffill().fillna(0)

        # Filtro YTD: manter só a partir de 1 de janeiro do ano corrente
        if periodo == 'ytd':
            inicio_ano = pd.Timestamp(df_performance.index[0].year, 1, 1)
            df_performance = df_performance[df_performance.index >= inicio_ano]

        # 5. Formatar para Google Charts
        cols = ["Data", label_principal, "IBOV", "IFIX", "IPCA", "CDI", "IMA-B"]
        rows = []
        for dt, row in df_performance.iterrows():
            linha = [dt.strftime('%d/%m')]
            linha.append(round(float(row.iloc[0]), 2)) # Selecionado ou Carteira
            linha.append(round(float(row.get('IBOV', 0)), 2))
            linha.append(round(float(row.get('IFIX', 0)), 2))
            linha.append(round(float(row.get('IPCA', 0)), 2))
            linha.append(round(float(row.get('CDI', 0)), 2))
            linha.append(round(float(row.get('IMA-B', 0)), 2))
            rows.append(linha)

        return jsonify({"cols": cols, "rows": rows, "tickers": tickers_disponiveis, "periodo": periodo})

    except Exception as e:
        import traceback
        logging.error(f"Erro desempenho: {e}\n{traceback.format_exc()}")
        return jsonify({
            "cols": [], 
            "rows": [], 
            "error": f"Erro interno: {str(e)}", 
            "tickers": tickers_disponiveis
        })


#######

@app.route('/dados_dividendos_mensais')
@login_required
def dados_dividendos_mensais():
    from sqlalchemy import func
    c_ativa = get_current_wallet()
    
    # MySQL/MariaDB: date_format(data, '%Y-%m') usando query autorizada
    query = get_authorized_query(Dividendo, c_ativa).with_entities(
        func.date_format(Dividendo.data_recebimento, '%Y-%m').label('m'), 
        func.sum(Dividendo.valor_total)
    )
        
    res = query.group_by('m').order_by('m').all()
        
    rows = [[datetime.strptime(r[0], '%Y-%m').strftime('%b/%y'), float(r[1])] for r in res]
    return jsonify({"rows": rows})

@app.route('/dados_proventos_ano')
@login_required
def dados_proventos_ano():
    c_ativa = get_current_wallet()
    # MySQL/MariaDB: date_format(data, '%Y') usando query autorizada
    query = get_authorized_query(Dividendo, c_ativa).with_entities(
        func.date_format(Dividendo.data_recebimento, '%Y').label('y'), 
        func.sum(Dividendo.valor_total)
    )
        
    res = query.group_by('y').order_by('y').all()
    
    rows = [[str(r[0]), float(r[1])] for r in res]
    return jsonify({"rows": rows})

@app.route('/dados_proventos_categoria')
@login_required
def dados_proventos_categoria():
    c_ativa = get_current_wallet()
    # Obtém mapeamento de ticker para categoria
    # Como um ticker pode ter sido comprado em datas diferentes com categorias potencialmente diferentes (embora improvável)
    # pegamos a categoria mais recente definida para cada ticker.
    q_sub = get_authorized_query(Ativo, c_ativa).with_entities(Ativo.ticker, Ativo.categoria)
    subquery = q_sub.distinct().subquery()
    
    # Agrupa dividendos por categoria baseando-se no ticker usando query autorizada
    query_res = get_authorized_query(Dividendo, c_ativa).with_entities(
        subquery.c.categoria,
        func.sum(Dividendo.valor_total)
    ).join(
        subquery, Dividendo.ticker == subquery.c.ticker
    )
        
    res = query_res.group_by(subquery.c.categoria).all()
    
    # Formata para Google Charts: [['Categoria', Valor], ...]
    rows = []
    for cat, total in res:
        rows.append([cat if cat else 'Outros', float(total)])
        
    return jsonify({"rows": rows})

@app.route('/dados_proventos_categoria_tempo')
@login_required
def dados_proventos_categoria_tempo():
    """
    Retorna proventos agrupados por período (mês ou ano) e por categoria do ativo.
    Parâmetro: modo=mensal (padrão) ou modo=anual
    """
    modo = request.args.get('modo', 'mensal')
    c_ativa = get_current_wallet()

    # Mapeamento ticker -> categoria usando query autorizada
    q_ativos = get_authorized_query(Ativo, c_ativa).with_entities(Ativo.ticker, Ativo.categoria).distinct()
    ativos = q_ativos.all()
    ticker_cat = {}
    for ticker, categoria in ativos:
        if ticker not in ticker_cat:
            ticker_cat[ticker] = categoria or 'Outros'

    # Buscar todos os proventos usando query autorizada
    q_div = get_authorized_query(Dividendo, c_ativa)
    todos = q_div.all()

    # Agregar por período e categoria
    from collections import defaultdict
    agregado = defaultdict(lambda: defaultdict(float))
    periodos_set = set()
    categorias_set = set()

    for d in todos:
        if modo == 'anual':
            periodo = str(d.data_recebimento.year)
        else:
            periodo = d.data_recebimento.strftime('%Y-%m')
        cat = ticker_cat.get(d.ticker, 'Outros')
        agregado[periodo][cat] += float(d.valor_total)
        periodos_set.add(periodo)
        categorias_set.add(cat)

    periodos = sorted(periodos_set)
    categorias = sorted(categorias_set)

    # Formatar rótulos dos períodos
    if modo == 'mensal':
        labels = [datetime.strptime(p, '%Y-%m').strftime('%b/%y') for p in periodos]
    else:
        labels = periodos

    # Montar rows: [período, val_cat1, val_cat2, ...]
    rows = []
    for p, label in zip(periodos, labels):
        row = [label]
        for cat in categorias:
            row.append(round(agregado[p].get(cat, 0.0), 2))
        rows.append(row)

    return jsonify({"rows": rows, "categorias": categorias})

@app.route('/dados_aportes_tempo')
@login_required
def dados_aportes_tempo():
    """
    Retorna aportes (quantidade * preco_compra) agrupados por período e por categoria.
    Parâmetro: modo=mensal (padrão) ou modo=anual
    """
    from collections import defaultdict
    modo = request.args.get('modo', 'mensal')
    c_ativa = get_current_wallet()

    # Lotes do ativo usando query autorizada
    q_lotes = get_authorized_query(Ativo, c_ativa)
    lotes = q_lotes.all()

    agregado = defaultdict(lambda: defaultdict(float))
    periodos_set = set()
    categorias_set = set()

    for l in lotes:
        if modo == 'anual':
            periodo = str(l.data_compra.year)
        else:
            periodo = l.data_compra.strftime('%Y-%m')
        cat = l.categoria or 'Outros'
        valor = float(l.quantidade) * float(l.preco_compra)
        agregado[periodo][cat] += valor
        periodos_set.add(periodo)
        categorias_set.add(cat)

    periodos = sorted(periodos_set)
    categorias = sorted(categorias_set)

    if modo == 'mensal':
        labels = [datetime.strptime(p, '%Y-%m').strftime('%b/%y') for p in periodos]
    else:
        labels = periodos

    rows = []
    for p, label in zip(periodos, labels):
        row = [label]
        for cat in categorias:
            row.append(round(agregado[p].get(cat, 0.0), 2))
        rows.append(row)

    return jsonify({"rows": rows, "categorias": categorias})

@app.route('/dados_dy_yoc')
@login_required
def dados_dy_yoc():
    """
    Retorna por período e por categoria: YoC (%) e, globalmente, o resumo por categoria
    com custo, valor de mercado, proventos totais, YoC% e DY%.
    """
    from collections import defaultdict
    modo = request.args.get('modo', 'mensal')

    categorias_rv = ['Ações', 'FIIs']
    c_ativa = get_current_wallet()
    # Ativos de RV usando query autorizada
    q_rv = get_authorized_query(Ativo, c_ativa).filter(Ativo.categoria.in_(categorias_rv))
    ativos_rv = q_rv.all()

    # Custo e mercado por categoria + mapeamento ticker->categoria
    cat_custo   = defaultdict(float)
    cat_mercado = defaultdict(float)
    ticker_cat  = {}
    for a in ativos_rv:
        cat = a.categoria or 'Outros'
        cat_custo[cat]   += float(a.quantidade) * float(a.preco_compra)
        cat_mercado[cat] += float(a.quantidade) * float(a.preco_atual)
        if a.ticker not in ticker_cat:
            ticker_cat[a.ticker] = cat

    tickers_rv = set(ticker_cat.keys())
    q_div = get_authorized_query(Dividendo, c_ativa).filter(Dividendo.ticker.in_(list(tickers_rv)))
    dividendos_rv = q_div.all() if tickers_rv else []

    # Agregar proventos por período x categoria
    prov_pc  = defaultdict(lambda: defaultdict(float))  # [periodo][cat]
    cat_total_prov = defaultdict(float)
    periodos_set = set()

    for d in dividendos_rv:
        cat = ticker_cat.get(d.ticker, 'Outros')
        periodo = str(d.data_recebimento.year) if modo == 'anual' else d.data_recebimento.strftime('%Y-%m')
        prov_pc[periodo][cat] += float(d.valor_total)
        cat_total_prov[cat]   += float(d.valor_total)
        periodos_set.add(periodo)

    # Apenas categorias que têm dados de proventos
    cats_com_dados = sorted(set(cat for cats in prov_pc.values() for cat in cats if cat in categorias_rv))
    if not cats_com_dados:
        cats_com_dados = [c for c in categorias_rv if cat_custo.get(c, 0) > 0]

    periodos = sorted(periodos_set)
    labels = [datetime.strptime(p, '%Y-%m').strftime('%b/%y') for p in periodos] if modo == 'mensal' else periodos

    # Rows para o gráfico de linhas: [label, yoc_cat1, yoc_cat2, ...]
    rows = []
    for p, label in zip(periodos, labels):
        row = [label]
        for cat in cats_com_dados:
            prov  = prov_pc[p].get(cat, 0.0)
            custo = cat_custo.get(cat, 0)
            yoc   = round(prov / custo * 100, 4) if custo > 0 else 0
            row.append(yoc)
        rows.append(row)

    # Resumo por categoria (acumulado de todos os períodos)
    resumo = []
    for cat in cats_com_dados:
        custo  = cat_custo.get(cat, 0)
        merc   = cat_mercado.get(cat, 0)
        prov_t = cat_total_prov.get(cat, 0)
        resumo.append({
            "categoria":   cat,
            "custo":       round(custo, 2),
            "mercado":     round(merc, 2),
            "proventos":   round(prov_t, 2),
            "yoc":         round(prov_t / custo  * 100, 2) if custo  > 0 else 0,
            "dy":          round(prov_t / merc   * 100, 2) if merc   > 0 else 0,
            "valorizacao": round(merc - custo, 2),
            "valorizacao_pct": round((merc / custo - 1) * 100, 2) if custo > 0 else 0,
        })

    return jsonify({"rows": rows, "categorias": cats_com_dados, "resumo": resumo})

@app.route('/dados_patrimonio_ano')
@login_required
def dados_patrimonio_ano():
    c_ativa = get_current_wallet()
    # 1. Obter todos os anos relevantes usando query autorizada
    q_a = get_authorized_query(Ativo, c_ativa).with_entities(func.date_format(Ativo.data_compra, '%Y'))
    q_v = get_authorized_query(Venda, c_ativa).with_entities(func.date_format(Venda.data_venda, '%Y'))
        
    anos_ativos = q_a.distinct().all()
    anos_vendas = q_v.distinct().all()
    
    todos_anos = sorted(list(set([int(a[0]) for a in anos_ativos if a[0]] + [int(a[0]) for a in anos_vendas if a[0]])))
    
    if not todos_anos:
        return jsonify({"rows": []})

    # 2. Dados brutos para cálculo
    # Dados brutos para cálculo usando query autorizada
    q_l = get_authorized_query(Ativo, c_ativa)
    q_vend = get_authorized_query(Venda, c_ativa)
    q_d = get_authorized_query(Dividendo, c_ativa)
        
    lotes = q_l.all()
    vendas = q_vend.all()
    proventos = q_d.all()
    
    rows = []
    for ano in todos_anos:
        data_limite = datetime(ano, 12, 31)
        
        # Valor Investido = Ativos atuais comprados até o ano + Vendas realizadas DEPOIS do ano
        investido = sum(float(l.quantidade) * float(l.preco_compra) for l in lotes if l.data_compra <= data_limite.date())
        investido += sum(float(v.quantidade) * float(v.preco_medio_compra) for v in vendas if v.data_venda > data_limite.date())
        
        # Proventos recebidos naquele ano específico
        data_inicio = datetime(ano, 1, 1).date()
        proventos_ano = sum(float(p.valor_total) for p in proventos if data_inicio <= p.data_recebimento <= data_limite.date())
        
        rows.append([str(ano), round(investido, 2), round(proventos_ano, 2)])
        
    return jsonify({"rows": rows})

@app.route('/dados_detalhe/<ticker>')
@login_required
def dados_detalhe(ticker):
    modo = request.args.get('modo', 'mensal')
    c_ativa = get_current_wallet()
    
    # Informações básicas para cálculos usando query autorizada
    q_lotes = get_authorized_query(Ativo, c_ativa).filter_by(ticker=ticker)
    q_vendas = get_authorized_query(Venda, c_ativa).filter_by(ticker=ticker)
    q_prov = get_authorized_query(Dividendo, c_ativa).filter_by(ticker=ticker)
        
    lotes = q_lotes.order_by(Ativo.data_compra.asc()).all()
    vendas = q_vendas.all()
    proventos = q_prov.order_by(Dividendo.data_recebimento.asc()).all()
    
    if not lotes and not vendas and not proventos:
        return jsonify({"success": False, "error": "Sem dados para este ticker"}), 404

    preco_atual = float(lotes[0].preco_atual) if lotes else 0.0
    
    # 2. Reconstrução histórica de Aportes
    aportes_agregado = {} # {periodo: valor_investido}
    
    for l in lotes:
        dt = l.data_compra
        periodo = dt.strftime('%Y-%m') if modo == 'mensal' else str(dt.year)
        val = float(l.quantidade) * float(l.preco_compra)
        aportes_agregado[periodo] = aportes_agregado.get(periodo, 0.0) + val
        
    # No caso de aportes, queremos mostrar o quanto foi investido naquele mês específico
    # Já temos isso no dicionário acima.
    
    # 3. Reconstrução histórica de Proventos e Yields
    proventos_agregado = {} # {periodo: {'total': 0, 'dy': 0, 'yoc': 0}}
    
    for p in proventos:
        dt_p = p.data_recebimento
        periodo = dt_p.strftime('%Y-%m') if modo == 'mensal' else str(dt_p.year)
        
        if periodo not in proventos_agregado:
            proventos_agregado[periodo] = {'total': 0.0, 'investido_medio': 0.0, 'count': 0}
            
        # Reconstruir posição na data do provento
        qtd_na_data = sum(float(l.quantidade) for l in lotes if l.data_compra <= dt_p)
        qtd_na_data += sum(float(v.quantidade) for v in vendas if v.data_venda > dt_p)
        
        investido_na_data = sum(float(l.quantidade) * float(l.preco_compra) for l in lotes if l.data_compra <= dt_p)
        investido_na_data += sum(float(v.quantidade) * float(v.preco_medio_compra) for v in vendas if v.data_venda > dt_p)
        
        valor_total = float(p.valor_total)
        proventos_agregado[periodo]['total'] += valor_total
        proventos_agregado[periodo]['investido_medio'] += investido_na_data
        proventos_agregado[periodo]['count'] += 1

    # 4. Formatação Final
    # Obter todos os períodos relevantes
    periodos_set = set(aportes_agregado.keys()) | set(proventos_agregado.keys())
    periodos_sorted = sorted(list(periodos_set))
    
    rows_dividendos = []
    rows_aportes = []
    
    for p in periodos_sorted:
        label = p
        if modo == 'mensal':
            try:
                label = datetime.strptime(p, '%Y-%m').strftime('%b/%y')
            except: pass
            
        # Dados de Dividendos
        d_data = proventos_agregado.get(p, {'total': 0.0, 'investido_medio': 0.0, 'count': 0})
        total_p = d_data['total']
        inv_medio = d_data['investido_medio'] / d_data['count'] if d_data['count'] > 0 else 0
        
        # YoC: Provento / Custo de Aquisição na época
        yoc = (total_p / inv_medio * 100) if inv_medio > 0 else 0
        
        # DY: Provento / Valor de Mercado Atual (como aproximação para histórico)
        # Na verdade, para o histórico, o ideal seria o preço na data, mas não temos.
        # Vamos usar o preco_atual como base para a linha de "DY sobre valor atual"
        qtd_periodo = total_qtd_lotes_na_periodo(lotes, vendas, p, modo)
        dy = (total_p / (qtd_periodo * preco_atual) * 100) if (preco_atual > 0 and qtd_periodo > 0) else 0
        
        rows_dividendos.append([label, round(total_p, 2), round(yoc, 4), round(dy, 4)])
        
        # Dados de Aportes
        total_a = aportes_agregado.get(p, 0.0)
        rows_aportes.append([label, round(total_a, 2)])
        
    return jsonify({
        "ticker": ticker,
        "dividendos": rows_dividendos,
        "aportes": rows_aportes
    })

def total_qtd_lotes_na_periodo(lotes, vendas, periodo, modo):
    # Função auxiliar para pegar a qtd que ele tinha no final do período
    if modo == 'anual':
        dt_limite = datetime(int(periodo), 12, 31).date()
    else:
        # Último dia do mês
        ano, mes = map(int, periodo.split('-'))
        if mes == 12:
            dt_limite = datetime(ano, 12, 31).date()
        else:
            dt_limite = (datetime(ano, mes + 1, 1) - timedelta(days=1)).date()
            
    qtd = sum(float(l.quantidade) for l in lotes if l.data_compra <= dt_limite)
    qtd += sum(float(v.quantidade) for v in vendas if v.data_venda > dt_limite)
    return qtd

if __name__ == '__main__':
    # Porta 5001 para evitar conflito com AirPlay no macOS (que usa a 5000)
    app.run(debug=True, port=5001)
