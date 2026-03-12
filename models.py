from extensions import db
from flask_login import UserMixin
from sqlalchemy import func

class PerfilUsuario(db.Model):
    __tablename__ = 'perfil_usuario'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), nullable=False, unique=True)
    
usuario_carteira = db.Table('usuario_carteira',
    db.Column('usuario_id', db.Integer, db.ForeignKey('usuarios.id'), primary_key=True),
    db.Column('carteira_id', db.Integer, db.ForeignKey('carteiras.id'), primary_key=True)
)

class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    data_criacao = db.Column(db.DateTime, default=func.now())
    criado_por_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    bloqueado = db.Column(db.Boolean, default=False)
    perfil_id = db.Column(db.Integer, db.ForeignKey('perfil_usuario.id'), nullable=True)
    
    perfil = db.relationship('PerfilUsuario', backref=db.backref('usuarios', lazy=True))
    carteiras = db.relationship('Carteira', secondary=usuario_carteira, lazy='subquery',
                               backref=db.backref('usuarios', lazy=True))

class Ativo(db.Model):
    __tablename__ = 'ativos'
    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(100), nullable=False)
    nome_ativo = db.Column(db.String(100))
    data_compra = db.Column(db.Date, nullable=False)
    quantidade = db.Column(db.Numeric(18, 6), nullable=False)
    preco_compra = db.Column(db.Numeric(15, 2), nullable=False)
    preco_atual = db.Column(db.Numeric(15, 2), default=0.0)
    pvp = db.Column(db.Numeric(15, 2), default=None)
    tipo_ativo = db.Column(db.String(50))
    categoria = db.Column(db.String(50), default='Ações')
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria_ativos.id'), nullable=True)
    carteira = db.Column(db.String(50), default='Consolidada')
    carteira_id = db.Column(db.Integer, db.ForeignKey('carteiras.id'), nullable=True)

    categoria_rel = db.relationship('CategoriaAtivo', backref=db.backref('ativos', lazy=True))
    carteira_rel = db.relationship('Carteira', backref=db.backref('ativos', lazy=True))

class Venda(db.Model):
    __tablename__ = 'vendas'
    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(100), nullable=False)
    quantidade = db.Column(db.Numeric(18, 6), nullable=False)
    preco_venda = db.Column(db.Numeric(15, 2), nullable=False)
    preco_medio_compra = db.Column(db.Numeric(15, 2), nullable=False)
    lucro_realizado = db.Column(db.Numeric(15, 2), nullable=False)
    data_venda = db.Column(db.Date, nullable=False)
    carteira = db.Column(db.String(50), default='Consolidada')
    carteira_id = db.Column(db.Integer, db.ForeignKey('carteiras.id'), nullable=True)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria_ativos.id'), nullable=True)

    carteira_rel = db.relationship('Carteira', backref=db.backref('vendas', lazy=True))
    categoria_rel = db.relationship('CategoriaAtivo', backref=db.backref('vendas_rel', lazy=True))

class Dividendo(db.Model):
    __tablename__ = 'dividendos'
    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(100), nullable=False)
    valor_total = db.Column(db.Numeric(15, 2), nullable=False)
    data_recebimento = db.Column(db.Date, nullable=False)
    tipo = db.Column(db.String(50), default='Dividendos')
    categoria_provento_id = db.Column(db.Integer, db.ForeignKey('categoria_proventos.id'), nullable=True)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria_ativos.id'), nullable=True)
    carteira = db.Column(db.String(50), default='Consolidada')
    carteira_id = db.Column(db.Integer, db.ForeignKey('carteiras.id'), nullable=True)

    categoria_provento = db.relationship('CategoriaProvento', backref=db.backref('dividendos', lazy=True))
    categoria_rel = db.relationship('CategoriaAtivo', backref=db.backref('dividendos_rel', lazy=True))
    carteira_rel = db.relationship('Carteira', backref=db.backref('dividendos', lazy=True))

# --- NOVOS MODELOS PARA FINANÇAS ---

class Categoria(db.Model):
    __tablename__ = 'categorias'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), nullable=False, unique=True)
    tipo = db.Column(db.String(20), nullable=False) # 'Receita' ou 'Despesa'
    icone = db.Column(db.String(50), default='bi-tag')
    carteira_id = db.Column(db.Integer, db.ForeignKey('carteiras.id'), nullable=True)

    carteira_rel = db.relationship('Carteira', backref=db.backref('categorias_finance', lazy=True))

class Transacao(db.Model):
    __tablename__ = 'transacoes'
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False, default=func.current_date())
    descricao = db.Column(db.String(255), nullable=False)
    valor = db.Column(db.Numeric(15, 2), nullable=False, default=0.0) # Valor total real
    valor_previsto = db.Column(db.Numeric(15, 2), default=0.0) # "À Pagar"
    valor_pago = db.Column(db.Numeric(15, 2), default=0.0)     # "Pago"
    dia_vencimento = db.Column(db.Integer, nullable=True)
    tipo = db.Column(db.String(20), nullable=False) # 'Receita' ou 'Despesa'
    categoria_id = db.Column(db.Integer, db.ForeignKey('categorias.id'), nullable=True)
    carteira = db.Column(db.String(50), default='Consolidada')
    carteira_id = db.Column(db.Integer, db.ForeignKey('carteiras.id'), nullable=True)
    fixa = db.Column(db.Boolean, default=False)
    pago = db.Column(db.Boolean, default=True)
    removida = db.Column(db.Boolean, default=False)
    posicao = db.Column(db.Integer, default=0)
    
    categoria = db.relationship('Categoria', backref=db.backref('transacoes', lazy=True))
    carteira_rel = db.relationship('Carteira', backref=db.backref('transacoes', lazy=True))

class ConfigFinanceiraFixa(db.Model):
    __tablename__ = 'config_financeiras_fixas'
    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(255), nullable=False)
    valor_estimado = db.Column(db.Numeric(15, 2), default=0.0)
    dia_vencimento = db.Column(db.Integer, default=1)
    tipo = db.Column(db.String(20), nullable=False, default='Despesa') # 'Receita' ou 'Despesa'
    categoria_id = db.Column(db.Integer, db.ForeignKey('categorias.id'), nullable=True)
    carteira = db.Column(db.String(50), default='Consolidada')
    carteira_id = db.Column(db.Integer, db.ForeignKey('carteiras.id'), nullable=True)
    ativo = db.Column(db.Boolean, default=True)
    posicao = db.Column(db.Integer, default=0)

    carteira_rel = db.relationship('Carteira', backref=db.backref('config_fixas', lazy=True))

class GastoCartao(db.Model):
    __tablename__ = 'gastos_cartao'
    id = db.Column(db.Integer, primary_key=True)
    fatura_mes = db.Column(db.String(7), nullable=False) # 'YYYY-MM'
    data = db.Column(db.Date, nullable=False)
    descricao = db.Column(db.String(255), nullable=False)
    valor = db.Column(db.Numeric(15, 2), nullable=False)
    transacao_id = db.Column(db.Integer, db.ForeignKey('transacoes.id'), nullable=True)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categorias.id'), nullable=True)
    
    transacao = db.relationship('Transacao', backref=db.backref('itens_cartao', lazy=True, cascade="all, delete-orphan"))
    categoria = db.relationship('Categoria')

class CategoriaAtivo(db.Model):
    __tablename__ = 'categoria_ativos'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), nullable=False, unique=True)
    carteira_id = db.Column(db.Integer, db.ForeignKey('carteiras.id'), nullable=True)

    carteira_rel = db.relationship('Carteira', backref=db.backref('categorias_ativos_rel', lazy=True))

class CategoriaProvento(db.Model):
    __tablename__ = 'categoria_proventos'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), nullable=False, unique=True)
    carteira_id = db.Column(db.Integer, db.ForeignKey('carteiras.id'), nullable=True)

    carteira_rel = db.relationship('Carteira', backref=db.backref('categorias_proventos_rel', lazy=True))

class Carteira(db.Model):
    __tablename__ = 'carteiras'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), nullable=False, unique=True)


# --- MÓDULO FUNCIONÁRIOS ---

class Funcionario(db.Model):
    __tablename__ = 'funcionarios'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cpf = db.Column(db.String(14), unique=True, nullable=True)
    salario_bruto = db.Column(db.Numeric(15, 2), nullable=False, default=0.0)
    data_admissao = db.Column(db.Date, nullable=True)
    ativo = db.Column(db.Boolean, default=True)
    carteira_id = db.Column(db.Integer, db.ForeignKey('carteiras.id'), nullable=True)
    inss_percent = db.Column(db.Numeric(5, 2), nullable=False, default=7.5)
    chave_pix = db.Column(db.String(255), nullable=True)

    carteira_rel = db.relationship('Carteira', backref=db.backref('funcionarios', lazy=True))
    lancamentos = db.relationship('FuncionarioLancamento', backref=db.backref('funcionario', lazy=True), lazy='dynamic', cascade='all, delete-orphan')
    folhas = db.relationship('FolhaPagamento', backref=db.backref('funcionario', lazy=True), lazy='dynamic', cascade='all, delete-orphan')



class FuncionarioLancamento(db.Model):
    __tablename__ = 'funcionario_lancamentos'
    id = db.Column(db.Integer, primary_key=True)
    funcionario_id = db.Column(db.Integer, db.ForeignKey('funcionarios.id'), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # 'Adiantamento' ou 'Desconto'
    valor = db.Column(db.Numeric(15, 2), nullable=False, default=0.0)
    data = db.Column(db.Date, nullable=False, default=func.current_date())
    observacao = db.Column(db.String(255), nullable=True)
    folha_id = db.Column(db.Integer, db.ForeignKey('folha_pagamentos.id'), nullable=True)

    folha_rel = db.relationship('FolhaPagamento', backref=db.backref('lancamentos_vinc', lazy='dynamic'))


class FolhaPagamento(db.Model):
    __tablename__ = 'folha_pagamentos'
    id = db.Column(db.Integer, primary_key=True)
    funcionario_id = db.Column(db.Integer, db.ForeignKey('funcionarios.id'), nullable=False)
    mes_referencia = db.Column(db.String(7), nullable=False)  # 'YYYY-MM'
    valor_bruto = db.Column(db.Numeric(15, 2), nullable=False, default=0.0)
    desconto_inss = db.Column(db.Numeric(15, 2), nullable=False, default=0.0)
    desconto_adiantamento = db.Column(db.Numeric(15, 2), nullable=False, default=0.0)
    outros_descontos = db.Column(db.Numeric(15, 2), nullable=False, default=0.0)
    salario_liquido = db.Column(db.Numeric(15, 2), nullable=False, default=0.0)
    data_pagamento = db.Column(db.Date, nullable=True)
    forma_pagamento = db.Column(db.String(50), nullable=True)
    pago = db.Column(db.Boolean, default=False)
    transacao_id = db.Column(db.Integer, db.ForeignKey('transacoes.id'), nullable=True)

    transacao = db.relationship('Transacao', backref=db.backref('folha_pagamento', uselist=False))

