# FluxoCapital
# 📊 Sistema de Gestão de Investimentos & Finanças

Este é um ecossistema completo de gestão financeira pessoal e de investimentos, desenvolvido com **Python** e **Flask**. O sistema opera de forma híbrida: **MariaDB/MySQL** para desenvolvimento local e **PostgreSQL (Supabase)** para produção em nuvem (**Vercel**).

---

## 🚀 Novas Atualizações: Deploy em Produção

Agora o sistema conta com integração contínua e deploy automático.

### 🔗 URL de Testes (Vercel)
**[https://fluxocapital-vercel.vercel.app/](https://fluxocapital-vercel.vercel.app/)**

### 🔑 Credenciais de Acesso (Produção):
- **Usuário:** `admin`
- **Senha:** `8mH29DAC`

---

## 🏗️ Arquitetura do Projeto

O sistema utiliza uma arquitetura modular baseada em **Blueprints** do Flask para separar a lógica de investimentos da lógica de finanças pessoais.

### Componentes Principais:
- **`app.py`**: Ponto de entrada da aplicação. Suporta múltiplos bancos de dados (PostgreSQL/MySQL).
- **`auth.py`**: Utilitários de segurança e controle de acesso (RBAC).
- **`finance.py`**: Módulo (Blueprint) para gestão de fluxo de caixa pessoal e relatórios.
- **`funcionarios.py`**: Módulo (Blueprint) para gestão de RH e Folha de Pagamento.
- **`models.py`**: Definição do esquema do banco de dados utilizando SQLAlchemy ORM.
- **`supabase_schema.sql`**: Esquema otimizado para **PostgreSQL/Supabase** (Produção).
- **`db_fluxocapital.sql`**: Dump original para **MariaDB/MySQL** (Desenvolvimento Local).

---

## 🛠️ Funcionalidades Detalhadas

### 📈 Investimentos
- **Preço Médio e Yield on Cost (YoC)**: Cálculo automático baseado no histórico.
- **Cotações em Tempo Real**: Integração via API para atualização de preços e P/VP.
- **Multicarteiras**: Visões independentes (Ex: Pessoal, Família, etc).

### 💳 Finanças Pessoais
- **Importação de PDF**: Leitura automática de faturas de cartão de crédito.
- **Despesas Fixas**: Geração automática recorrente.
- **Fluxo de Caixa**: Visão detalhada de "À Pagar" vs "Pago".

### 👥 Gestão de Funcionários (RH)
- **Folha de Pagamento**: Processamento automatizado com cálculo de INSS.
- **Recibos**: Geração de comprovantes e integração com o financeiro.

---

## ⚙️ Configuração do Banco de Dados

### 🔵 Produção (Vercel + Supabase)
1. Crie um projeto no **Supabase**.
2. Execute o conteúdo de `supabase_schema.sql` no SQL Editor do Supabase.
3. No Vercel, adicione a variável de ambiente `DATABASE_URL` com a string de conexão do PostgreSQL.

### 🟢 Local (MariaDB / MySQL)
Basta executar o script de inicialização automática:
```bash
chmod +x iniciar_banco.sh
./iniciar_banco.sh
```

---

## 💻 Execução Local

```bash
chmod +x rodar_local.sh
./rodar_local.sh
```

Acesse: [http://localhost:5001](http://localhost:5001)

---

## 🔐 Segurança e Auditoria
- **RBAC**: Controle de acesso baseado em funções.
- **Logs**: Registros detalhados em `login_errors.log` e `user_actions.log`.
- **Vercel**: Ambiente seguro com HTTPS automático.