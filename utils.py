import os
import logging
from functools import wraps
from datetime import datetime
from flask import request, session
from flask_login import current_user
from auth import is_superadmin, is_admin_or_superadmin
from extensions import db
from models import Carteira

# --- CONFIGURAÇÃO DE LOG ---
base_dir = os.path.abspath(os.path.dirname(__file__))
log_file = os.path.join(base_dir, 'login_errors.log')
actions_log_file = os.path.join(base_dir, 'user_actions.log')

# Logger dedicado para ações do usuário
user_logger = logging.getLogger('user_actions')
user_logger.setLevel(logging.INFO)
if not user_logger.handlers:
    if os.environ.get('VERCEL'):
        action_handler = logging.StreamHandler()
    else:
        action_handler = logging.FileHandler(actions_log_file, mode='a', encoding='utf-8')
    action_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
    user_logger.addHandler(action_handler)

def log_action(message_template):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Evita importar modelos no topo para prevenir circular imports
            from models import Usuario, Ativo, Venda, Dividendo
            
            # Captura informações ANTES da execução (deleções e logout)
            pre_username = current_user.username if (current_user and current_user.is_authenticated) else None
            pre_details = []
            is_deletion = f.__name__.startswith('deletar') or f.__name__.startswith('delete')
            
            if is_deletion and 'id' in kwargs:
                item_id = kwargs['id']
                try:
                    if 'venda' in f.__name__:
                        v = Venda.query.get(item_id)
                        if v: pre_details.append(f"Ticker: {v.ticker}")
                    elif 'dividendo' in f.__name__ or 'provento' in f.__name__:
                        d = Dividendo.query.get(item_id)
                        if d: pre_details.append(f"Ticker: {d.ticker}")
                    elif 'lancamento' in f.__name__:
                        from models import FuncionarioLancamento
                        l = FuncionarioLancamento.query.get(item_id)
                        if l: pre_details.append(f"Func: {l.funcionario.nome}, Tipo: {l.tipo}, Valor: {l.valor}")
                    elif 'funcionario' in f.__name__:
                        from models import Funcionario
                        func = Funcionario.query.get(item_id)
                        if func: pre_details.append(f"Nome: {func.nome}")
                    elif 'transacao' in f.__name__:
                        from models import Transacao
                        t = Transacao.query.get(item_id)
                        if t: pre_details.append(f"Desc: {t.descricao}, Valor: {t.valor or t.valor_pago or t.valor_previsto}")
                    else: # Ativo
                        a = Ativo.query.get(item_id)
                        if a: pre_details.append(f"Ticker: {a.ticker}")
                except Exception as e:
                    logging.error(f"Erro pre-log deleção: {e}")
                
                if not pre_details:
                    pre_details.append(f"ID: {item_id}")

            # Executa a função
            response = f(*args, **kwargs)

            # Logar somente após execução bem sucedida (ou conforme regras)
            try:
                # Logar POSTs, deleções, logouts ou ações específicas de pagamento/fechamento
                action_names = ['logout', 'fechar', 'pagar', 'pago', 'reabrir']
                should_log = request.method == 'POST' or is_deletion or any(name in f.__name__ for name in action_names)
                
                if should_log:
                    # Determina o nome do usuário (trata logout e falha de login)
                    authenticated = (current_user and current_user.is_authenticated)
                    username = pre_username or (current_user.username if authenticated else request.form.get('username') or "Anônimo")
                    ip = request.remote_addr

                    # Status para Login
                    msg = message_template
                    if f.__name__ == 'login' and request.method == 'POST':
                        msg += " [SUCESSO]" if authenticated else " [FALHA]"
                    
                    details = []
                    details.extend(pre_details)
                    
                    # Campos do formulário (apenas se for POST)
                    if request.method == 'POST':
                        # Captura filename se houver arquivo no request
                        if request.files:
                            for file_key in request.files:
                                f_obj = request.files[file_key]
                                if f_obj and f_obj.filename:
                                    details.append(f"arquivo: {f_obj.filename}")

                        # Lista expandida de campos para logar
                        keys_to_log = ['id', 'ticker', 'quantidade', 'preco_compra', 'cambio', 'categoria', 
                                       'data', 'valor', 'tipo', 'username', 'action', 'user_id', 
                                       'nova_senha', 'tipo_relatorio', 'nome', 'cpf', 'salario_bruto',
                                       'observacao', 'forma_pagamento', 'campo', 'descricao', 'posicao']
                        
                        for key in keys_to_log:
                            val = request.form.get(key)
                            if val:
                                if key == 'user_id' or (key == 'id' and 'usuario' in f.__name__):
                                    try:
                                        from models import Usuario
                                        target_user = Usuario.query.get(val)
                                        if target_user:
                                            details.append(f"usuario_alvo: {target_user.username}")
                                            continue
                                    except: pass
                                
                                if key == 'nova_senha' or 'password' in key: val = "********"
                                details.append(f"{key}: {val}")
                    
                    detail_str = f" ({', '.join(details)})" if details else ""
                    user_logger.info(f"USUÁRIO: {username} | AÇÃO: {msg}{detail_str} | IP: {ip}")
            except Exception as e:
                # Loga erro no log do sistema para debug, mas não quebra a requisição do usuário
                logging.error(f"Erro no log_action para {f.__name__}: {e}")
                
            return response
        return decorated_function
    return decorator

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
    
    # Se c_ativa for uma lista, tratamos a consolidação dessas carteiras
    if isinstance(c_ativa, list):
        if is_superadmin():
            if 'Consolidada' in c_ativa:
                return query
            
            c_objs = Carteira.query.filter(Carteira.nome.in_(c_ativa)).all()
            c_ids = [c.id for c in c_objs]
            if hasattr(model, 'carteira_id'):
                return query.filter(model.carteira_id.in_(c_ids))
            else:
                return query.filter(model.carteira.in_(c_ativa))
        else:
            # Filtra apenas pelas carteiras que o usuário tem acesso
            acessivel = [c.nome for c in current_user.carteiras]
            permitidas = [nome for nome in c_ativa if nome in acessivel]
            
            if not permitidas:
                return query.filter(False)
            
            c_objs = Carteira.query.filter(Carteira.nome.in_(permitidas)).all()
            c_ids = [c.id for c in c_objs]
            
            if hasattr(model, 'carteira_id'):
                return query.filter(model.carteira_id.in_(c_ids))
            else:
                return query.filter(model.carteira.in_(permitidas))

    # SuperAdmin tem acesso total — sem filtro de carteira
    if is_superadmin():
        if c_ativa != 'Consolidada':
            c_obj = Carteira.query.filter_by(nome=c_ativa).first()
            if c_obj:
                if hasattr(model, 'carteira_id'):
                    return query.filter_by(carteira_id=c_obj.id)
                else:
                    return query.filter_by(carteira=c_ativa)
            return query.filter(False)
        return query  # 'Consolidada' = todos os dados para SuperAdmin
    
    if c_ativa == 'Consolidada':
        # Admin e Usuário: filtrar pelas carteiras atribuídas
        wallet_ids = [c.id for c in current_user.carteiras]
        if wallet_ids:
            if hasattr(model, 'carteira_id'):
                return query.filter(model.carteira_id.in_(wallet_ids))
            else:
                wallet_nomes = [c.nome for c in current_user.carteiras]
                return query.filter(model.carteira.in_(wallet_nomes))
        return query.filter(False)
    else:
        # Carteira específica
        c_obj = Carteira.query.filter_by(nome=c_ativa).first()
        if c_obj:
            # Verifica se o usuário tem acesso a essa carteira
            if not is_admin_or_superadmin() or (current_user.perfil and current_user.perfil.nome == 'Admin'):
                if c_obj not in current_user.carteiras:
                    return query.filter(False)
            
            if hasattr(model, 'carteira_id'):
                return query.filter_by(carteira_id=c_obj.id)
            else:
                return query.filter_by(carteira=c_ativa)
        else:
            return query.filter(False)
    return query
