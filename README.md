# FluxoCapital
# 📊 Sistema de Gestão de Investimentos & Finanças

Este é um ecossistema completo de gestão financeira pessoal e de investimentos, desenvolvido com **Python** e **Flask**. O sistema foi desenhado para operar num ambiente híbrido, otimizando o desenvolvimento local e em servidores remotos Linux.

## 🏗️ Arquitetura do Projeto

O sistema utiliza uma arquitetura modular baseada em **Blueprints** do Flask para separar a lógica de investimentos da lógica de finanças pessoais.

### Componentes Principais:
- **`app.py`**: Ponto de entrada da aplicação Flask. Centraliza a configuração do sistema, gestão de autenticação, rotas principais de ativos de investimento e a integração de Blueprints.
- **`auth.py`**: Utilitários de segurança e controle de acesso (RBAC). Define decoradores para restringir rotas a perfis específicos como `Admin` e `SuperAdmin`.
- **`finance.py`**: Módulo (Blueprint) dedicado ao fluxo de caixa pessoal. Gerencia transações, categorias de despesas, contas fixas e gera relatórios financeiros detalhados.
- **`funcionarios.py`**: Módulo (Blueprint) para gestão de RH. Controla o cadastro de funcionários, lançamentos de adiantamentos/descontos, processamento de folha de pagamento e recibos.
- **`models.py`**: Definição do esquema do banco de dados MariaDB/MySQL utilizando o SQLAlchemy ORM, mapeando todas as entidades do sistema.
- **`card_parser.py`**: Script de automação que utiliza `pdfplumber` para extrair dados de faturas de cartão de crédito em PDF, automatizando o lançamento de gastos.
- **`update_prices.py`**: Utilitário que consome APIs financeiras para atualizar cotações de ativos, indicadores (P/VP) e o câmbio (USD/BRL) no banco de dados.
- **`utils.py`**: Funções auxiliares compartilhadas, como a lógica de filtragem de dados por carteira ativa e autorização de consultas baseada no perfil do usuário.
- **`extensions.py`**: Centralização da inicialização das extensões do Flask (DB, LoginManager) para garantir a integridade das importações no projeto.

## 🛠️ Funcionalidades Detalhadas

### 📈 Investimentos
- **Preço Médio e Yield on Cost (YoC)**: Cálculo automático baseado no histórico de compras.
- **Cotações em Tempo Real**: Integração via API para atualização de preços e P/VP (`update_prices.py`).
- **Relatórios**: Visão de aportes mensais e evolução de proventos.

### 💳 Finanças Pessoais
- **Importação de PDF**: Lançamento automático de gastos de cartão de crédito através da leitura da fatura.
- **Despesas Fixas**: Geração automática de contas recorrentes no início de cada mês.
- **Multicarteiras**: Separação de fluxos financeiros por perfil (ex: Pessoal vs. Família) com controle de acesso granular.

### 👥 Gestão de Funcionários (RH)
- **Ciclo de Vida**: Cadastro completo de funcionários ativos e inativos, controle de admissão, CPF e dados bancários/PIX.
- **Gestão de Lançamentos**: Registro individual de adiantamentos, vales e descontos extras.
- **Folha de Pagamento**: Processamento automatizado de salários com cálculo de INSS, integração direta com o fluxo de caixa e geração de recibos.
- **Extrato do Colaborador**: Painel histórico que consolida todos os pagamentos e descontos de um funcionário ao longo do tempo.

### 📊 Relatórios e Inteligência
- **Dashboard Financeiro**: Visão consolidada de saldo, receitas e despesas com indicadores de performance mensal.
- **Relatórios Anuais e Mensais**: Tabelas detalhadas de fluxo de caixa, agrupadas por categoria e subcategoria.
- **Análise Visual**: Gráficos dinâmicos para acompanhamento de despesas por categoria e evolução patrimonial.
- **Relatório de Folha**: Resumo executivo de custos com pessoal por carteira e período.
- **Performance de Ativos**: Relatórios de Yield on Cost, preço médio e evolução de dividendos recebidos.

---

## 🔐 Segurança e Compliance

- **RBAC (Role-Based Access Control)**: Sistema de perfis de utilizador (Admin, Gestor, Familiar) para restrição de acesso a áreas sensíveis.
- **Logs de Auditoria**: Monitorização de acessos (`login_errors.log`) e ações de utilizador (`user_actions.log`).
- **Ambiente Isolado**: Dependências geridas via `venv` (Virtual Environment).

---

## 🚀 Como Iniciar

### Requisitos:
- Python 3.9+
- MariaDB / MySQL
- Dependências listadas em `requirements.txt`

### Configuração do Banco de Dados:
A aplicação vem com um banco de dados de testes em `db_fluxocapital.sql`.
As credenciais padrão da aplicação são:
- **Usuário:** `user_fluxocapital`
- **Senha:** `1qhnTXZDCz8P4cB7n`
- **Banco:** `db_fluxocapital`

Caso queira configurar automaticamente usando o padrão, basta executar o script fornecido interativamente (ele lhe pedirá apenas a senha de root do seu MySQL local):
```bash
chmod +x iniciar_banco.sh
sudo ./iniciar_banco.sh
```

*(Opcional) Caso prefira fazer manualmente via terminal:*
```bash
mysql -u root -p -e "CREATE DATABASE db_fluxocapital;"
mysql -u root -p -e "CREATE USER 'user_fluxocapital'@'localhost' IDENTIFIED BY '1qhnTXZDCz8P4cB7n';"
mysql -u root -p -e "GRANT ALL PRIVILEGES ON db_fluxocapital.* TO 'user_fluxocapital'@'localhost';"
mysql -u root -p -e "FLUSH PRIVILEGES;"
mysql -u root -p db_fluxocapital < db_fluxocapital.sql
```


### Execução Local:
Para simplificar, já fornecemos um script que cria o ambiente virtual, instala as dependências e inicia a aplicação automaticamente:
```bash
chmod +x rodar_local.sh
./rodar_local.sh
```

*(Opcional) Caso prefira realizar os passos manualmente:*
```bash
# Crie e ative seu ambiente virtual
python3 -m venv venv
source venv/bin/activate

# Instale as dependências
pip install --upgrade pip
pip install -r requirements.txt

# Execute a aplicação
python3 app.py
```

### Credenciais de Teste locais:
URL: http://localhost:5001/

Usuário: admin<br>
Senha: 8mH29DAC

### Credenciais de Teste Remotas:
URL: https://fluxocapital.duckdns.org/

Usuário: admin<br>
Senha: 8mH29DAC