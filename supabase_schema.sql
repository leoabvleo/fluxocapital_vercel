-- Conversão de db_fluxocapital.sql para PostgreSQL (Supabase)

-- 1. Tabelas sem dependências (ou poucas)
CREATE TABLE IF NOT EXISTS "carteiras" (
  "id" SERIAL PRIMARY KEY,
  "nome" varchar(50) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS "perfil_usuario" (
  "id" SERIAL PRIMARY KEY,
  "nome" varchar(50) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS "categoria_ativos" (
  "id" SERIAL PRIMARY KEY,
  "nome" varchar(50) NOT NULL UNIQUE,
  "carteira_id" integer REFERENCES "carteiras"("id") ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS "categoria_proventos" (
  "id" SERIAL PRIMARY KEY,
  "nome" varchar(50) NOT NULL UNIQUE,
  "carteira_id" integer REFERENCES "carteiras"("id") ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS "categorias" (
  "id" SERIAL PRIMARY KEY,
  "nome" varchar(50) NOT NULL UNIQUE,
  "tipo" varchar(20) NOT NULL, -- 'Receita' ou 'Despesa'
  "icone" varchar(50) DEFAULT 'bi-tag',
  "carteira_id" integer REFERENCES "carteiras"("id") ON DELETE CASCADE
);

-- 2. Tabelas de Ativos e Transações
CREATE TABLE IF NOT EXISTS "ativos" (
  "id" SERIAL PRIMARY KEY,
  "ticker" varchar(100) NOT NULL,
  "nome_ativo" varchar(100) DEFAULT NULL,
  "data_compra" date NOT NULL,
  "quantidade" numeric(18,6) NOT NULL,
  "preco_compra" numeric(15,2) NOT NULL,
  "preco_atual" numeric(15,2) DEFAULT 0.0,
  "pvp" numeric(15,2) DEFAULT NULL,
  "tipo_ativo" varchar(50) DEFAULT NULL,
  "categoria" varchar(50) DEFAULT 'Ações',
  "carteira" varchar(50) DEFAULT 'Consolidada',
  "categoria_id" integer REFERENCES "categoria_ativos"("id"),
  "carteira_id" integer REFERENCES "carteiras"("id")
);

CREATE TABLE IF NOT EXISTS "vendas" (
  "id" SERIAL PRIMARY KEY,
  "ticker" varchar(100) NOT NULL,
  "quantidade" numeric(18,6) NOT NULL,
  "preco_venda" numeric(15,2) NOT NULL,
  "preco_medio_compra" numeric(15,2) NOT NULL,
  "lucro_realizado" numeric(15,2) NOT NULL,
  "data_venda" date NOT NULL,
  "carteira" varchar(50) DEFAULT 'Consolidada',
  "carteira_id" integer REFERENCES "carteiras"("id"),
  "categoria_id" integer REFERENCES "categoria_ativos"("id")
);

CREATE TABLE IF NOT EXISTS "dividendos" (
  "id" SERIAL PRIMARY KEY,
  "ticker" varchar(100) NOT NULL,
  "valor_total" numeric(15,2) NOT NULL,
  "data_recebimento" date NOT NULL,
  "tipo" varchar(50) DEFAULT 'Dividendos',
  "carteira" varchar(50) DEFAULT 'Consolidada',
  "categoria_provento_id" integer REFERENCES "categoria_proventos"("id"),
  "carteira_id" integer REFERENCES "carteiras"("id"),
  "categoria_id" integer REFERENCES "categoria_ativos"("id")
);

CREATE TABLE IF NOT EXISTS "transacoes" (
  "id" SERIAL PRIMARY KEY,
  "data" date NOT NULL DEFAULT current_date,
  "descricao" varchar(255) NOT NULL,
  "valor" numeric(15,2) NOT NULL DEFAULT 0.0,
  "valor_previsto" numeric(15,2) DEFAULT 0.0,
  "valor_pago" numeric(15,2) DEFAULT 0.0,
  "dia_vencimento" integer DEFAULT NULL,
  "tipo" varchar(20) NOT NULL, -- 'Receita' ou 'Despesa'
  "categoria_id" integer REFERENCES "categorias"("id"),
  "carteira" varchar(50) DEFAULT 'Consolidada',
  "carteira_id" integer REFERENCES "carteiras"("id"),
  "fixa" boolean DEFAULT false,
  "pago" boolean DEFAULT true,
  "removida" boolean DEFAULT false,
  "posicao" integer DEFAULT 0
);

-- 3. Funcionários e Folha
CREATE TABLE IF NOT EXISTS "funcionarios" (
  "id" SERIAL PRIMARY KEY,
  "nome" varchar(100) NOT NULL,
  "cpf" varchar(14) UNIQUE DEFAULT NULL,
  "salario_bruto" numeric(15,2) NOT NULL DEFAULT 0.0,
  "data_admissao" date DEFAULT NULL,
  "ativo" boolean DEFAULT true,
  "carteira_id" integer REFERENCES "carteiras"("id"),
  "inss_percent" numeric(5,2) NOT NULL DEFAULT 7.50,
  "chave_pix" varchar(255) DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS "folha_pagamentos" (
  "id" SERIAL PRIMARY KEY,
  "funcionario_id" integer NOT NULL REFERENCES "funcionarios"("id"),
  "mes_referencia" varchar(7) NOT NULL, -- 'YYYY-MM'
  "valor_bruto" numeric(15,2) NOT NULL DEFAULT 0.0,
  "desconto_inss" numeric(15,2) NOT NULL DEFAULT 0.0,
  "desconto_adiantamento" numeric(15,2) NOT NULL DEFAULT 0.0,
  "outros_descontos" numeric(15,2) NOT NULL DEFAULT 0.0,
  "salario_liquido" numeric(15,2) NOT NULL DEFAULT 0.0,
  "data_pagamento" date DEFAULT NULL,
  "forma_pagamento" varchar(50) DEFAULT NULL,
  "pago" boolean DEFAULT false,
  "transacao_id" integer REFERENCES "transacoes"("id")
);

CREATE TABLE IF NOT EXISTS "funcionario_lancamentos" (
  "id" SERIAL PRIMARY KEY,
  "funcionario_id" integer NOT NULL REFERENCES "funcionarios"("id"),
  "tipo" varchar(20) NOT NULL, -- 'Adiantamento' ou 'Desconto'
  "valor" numeric(15,2) NOT NULL DEFAULT 0.0,
  "data" date NOT NULL DEFAULT current_date,
  "observacao" varchar(255) DEFAULT NULL,
  "folha_id" integer REFERENCES "folha_pagamentos"("id")
);

CREATE TABLE IF NOT EXISTS "config_financeiras_fixas" (
  "id" SERIAL PRIMARY KEY,
  "descricao" varchar(255) NOT NULL,
  "valor_estimado" numeric(15,2) DEFAULT 0.0,
  "dia_vencimento" integer DEFAULT 1,
  "tipo" varchar(20) NOT NULL DEFAULT 'Despesa',
  "categoria_id" integer REFERENCES "categorias"("id"),
  "carteira" varchar(50) DEFAULT 'Consolidada',
  "carteira_id" integer REFERENCES "carteiras"("id"),
  "ativo" boolean DEFAULT true,
  "posicao" integer DEFAULT 0
);

CREATE TABLE IF NOT EXISTS "gastos_cartao" (
  "id" SERIAL PRIMARY KEY,
  "fatura_mes" varchar(7) NOT NULL,
  "data" date NOT NULL,
  "descricao" varchar(255) NOT NULL,
  "valor" numeric(15,2) NOT NULL,
  "transacao_id" integer REFERENCES "transacoes"("id"),
  "categoria_id" integer REFERENCES "categorias"("id")
);

-- 4. Usuários e Permissões
CREATE TABLE IF NOT EXISTS "usuarios" (
  "id" SERIAL PRIMARY KEY,
  "username" varchar(50) NOT NULL UNIQUE,
  "password" varchar(255) NOT NULL,
  "data_criacao" timestamp DEFAULT current_timestamp,
  "criado_por_id" integer REFERENCES "usuarios"("id"),
  "bloqueado" boolean DEFAULT false,
  "perfil_id" integer REFERENCES "perfil_usuario"("id")
);

CREATE TABLE IF NOT EXISTS "usuario_carteira" (
  "usuario_id" integer NOT NULL REFERENCES "usuarios"("id") ON DELETE CASCADE,
  "carteira_id" integer NOT NULL REFERENCES "carteiras"("id") ON DELETE CASCADE,
  PRIMARY KEY ("usuario_id", "carteira_id")
);

-- 5. Inserção de Dados Iniciais (Opcional, baseado no dump)
-- Carteiras
INSERT INTO "carteiras" (id, nome) VALUES (1, 'Consolidada') ON CONFLICT DO NOTHING;
INSERT INTO "carteiras" (id, nome) VALUES (10, 'Carteira 1') ON CONFLICT DO NOTHING;
INSERT INTO "carteiras" (id, nome) VALUES (11, 'Carteira 2') ON CONFLICT DO NOTHING;

-- Perfis
INSERT INTO "perfil_usuario" (id, nome) VALUES (1, 'Admin') ON CONFLICT DO NOTHING;
INSERT INTO "perfil_usuario" (id, nome) VALUES (4, 'SuperAdmin') ON CONFLICT DO NOTHING;
INSERT INTO "perfil_usuario" (id, nome) VALUES (2, 'Usuário') ON CONFLICT DO NOTHING;

-- Categorias de Ativos
INSERT INTO "categoria_ativos" (id, nome) VALUES (1, 'Ações') ON CONFLICT DO NOTHING;
INSERT INTO "categoria_ativos" (id, nome) VALUES (2, 'FIIs') ON CONFLICT DO NOTHING;
INSERT INTO "categoria_ativos" (id, nome) VALUES (3, 'ETFs') ON CONFLICT DO NOTHING;
INSERT INTO "categoria_ativos" (id, nome) VALUES (4, 'BDRs') ON CONFLICT DO NOTHING;
INSERT INTO "categoria_ativos" (id, nome) VALUES (5, 'Internacional') ON CONFLICT DO NOTHING;
INSERT INTO "categoria_ativos" (id, nome) VALUES (6, 'Renda Fixa') ON CONFLICT DO NOTHING;
INSERT INTO "categoria_ativos" (id, nome) VALUES (7, 'Previdência') ON CONFLICT DO NOTHING;
INSERT INTO "categoria_ativos" (id, nome) VALUES (8, 'Cripto') ON CONFLICT DO NOTHING;

-- Categorias de Proventos
INSERT INTO "categoria_proventos" (id, nome) VALUES (1, 'Dividendos') ON CONFLICT DO NOTHING;
INSERT INTO "categoria_proventos" (id, nome) VALUES (2, 'JCP') ON CONFLICT DO NOTHING;
INSERT INTO "categoria_proventos" (id, nome) VALUES (3, 'Bonificação') ON CONFLICT DO NOTHING;
INSERT INTO "categoria_proventos" (id, nome) VALUES (4, 'Rendimentos') ON CONFLICT DO NOTHING;
INSERT INTO "categoria_proventos" (id, nome) VALUES (5, 'Juros') ON CONFLICT DO NOTHING;
INSERT INTO "categoria_proventos" (id, nome) VALUES (6, 'Amortização') ON CONFLICT DO NOTHING;
INSERT INTO "categoria_proventos" (id, nome) VALUES (8, 'Rendimentos BTC') ON CONFLICT DO NOTHING;
INSERT INTO "categoria_proventos" (id, nome) VALUES (12, 'Frações de Ações') ON CONFLICT DO NOTHING;

-- Categorias Financeiras
INSERT INTO "categorias" (id, nome, tipo, icone) VALUES (1,'Salário','Receita','bi-cash-stack') ON CONFLICT DO NOTHING;
INSERT INTO "categorias" (id, nome, tipo, icone) VALUES (2,'Dividendos','Receita','bi-graph-up-arrow') ON CONFLICT DO NOTHING;
INSERT INTO "categorias" (id, nome, tipo, icone) VALUES (3,'Outras Receitas','Receita','bi-plus-circle') ON CONFLICT DO NOTHING;
INSERT INTO "categorias" (id, nome, tipo, icone) VALUES (4,'Alimentação','Despesa','bi-cart') ON CONFLICT DO NOTHING;
INSERT INTO "categorias" (id, nome, tipo, icone) VALUES (5,'Moradia','Despesa','bi-house') ON CONFLICT DO NOTHING;
INSERT INTO "categorias" (id, nome, tipo, icone) VALUES (6,'Transporte','Despesa','bi-car-front') ON CONFLICT DO NOTHING;
INSERT INTO "categorias" (id, nome, tipo, icone) VALUES (7,'Lazer','Despesa','bi-airplane') ON CONFLICT DO NOTHING;
INSERT INTO "categorias" (id, nome, tipo, icone) VALUES (8,'Investimento','Despesa','bi-piggy-bank') ON CONFLICT DO NOTHING;
INSERT INTO "categorias" (id, nome, tipo, icone) VALUES (9,'Saúde','Despesa','bi-heart-pulse') ON CONFLICT DO NOTHING;
INSERT INTO "categorias" (id, nome, tipo, icone) VALUES (10,'Impostos','Despesa','bi-receipt') ON CONFLICT DO NOTHING;
INSERT INTO "categorias" (id, nome, tipo, icone) VALUES (11,'Outras Despesas','Despesa','bi-dash-circle') ON CONFLICT DO NOTHING;
INSERT INTO "categorias" (id, nome, tipo, icone) VALUES (12,'Telefonia/Internet','Despesa','bi-telephone') ON CONFLICT DO NOTHING;
INSERT INTO "categorias" (id, nome, tipo, icone) VALUES (13,'Cartão de Crédito','Despesa','bi-credit-card') ON CONFLICT DO NOTHING;
INSERT INTO "categorias" (id, nome, tipo, icone) VALUES (14,'Educação','Despesa','bi-book') ON CONFLICT DO NOTHING;
INSERT INTO "categorias" (id, nome, tipo, icone) VALUES (15,'Honorários','Receita','bi-cash-stack') ON CONFLICT DO NOTHING;
INSERT INTO "categorias" (id, nome, tipo, icone) VALUES (16,'Vestuário','Despesa','bi-tag') ON CONFLICT DO NOTHING;
INSERT INTO "categorias" (id, nome, tipo, icone) VALUES (17,'Casa/Decoração','Despesa','bi-tag') ON CONFLICT DO NOTHING;
INSERT INTO "categorias" (id, nome, tipo, icone) VALUES (18,'Streaming','Despesa','bi-tag') ON CONFLICT DO NOTHING;
INSERT INTO "categorias" (id, nome, tipo, icone) VALUES (19,'Compras Internet','Despesa','bi-tag') ON CONFLICT DO NOTHING;
INSERT INTO "categorias" (id, nome, tipo, icone) VALUES (20,'Beleza/Higiene','Despesa','bi-tag') ON CONFLICT DO NOTHING;
INSERT INTO "categorias" (id, nome, tipo, icone) VALUES (21,'Funcionário','Despesa','bi-tag') ON CONFLICT DO NOTHING;

-- Usuário Admin Inicial (Senha: admin123 ou a do dump)
-- Nota: Usando a senha do dump que é 'admin'
INSERT INTO "usuarios" (id, username, password, perfil_id) VALUES (1, 'admin', 'pbkdf2:sha256:1000000$Aqu4BrJZoveRIeP6$e079f8993a3ee1644485e17b111e3989b054c12417b432cf33ad2d5a3bbf4621', 4) ON CONFLICT DO NOTHING;

-- Ajustar sequências de ID (necessário no PostgreSQL após inserts manuais com ID)
SELECT setval(pg_get_serial_sequence('carteiras', 'id'), (SELECT MAX(id) FROM carteiras));
SELECT setval(pg_get_serial_sequence('perfil_usuario', 'id'), (SELECT MAX(id) FROM perfil_usuario));
SELECT setval(pg_get_serial_sequence('categoria_ativos', 'id'), (SELECT MAX(id) FROM categoria_ativos));
SELECT setval(pg_get_serial_sequence('categoria_proventos', 'id'), (SELECT MAX(id) FROM categoria_proventos));
SELECT setval(pg_get_serial_sequence('categorias', 'id'), (SELECT MAX(id) FROM categorias));
SELECT setval(pg_get_serial_sequence('usuarios', 'id'), (SELECT MAX(id) FROM usuarios));
