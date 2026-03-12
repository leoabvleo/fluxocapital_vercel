#!/bin/bash

echo "================================================="
echo "   Configuração do Banco de Dados FluxoCapital   "
echo "================================================="
echo "Este script criará o banco de dados (db_fluxocapital), o usuário padrão"
echo "(user_fluxocapital) e importará os dados de teste."
echo ""

# Detecta acesso root ao MySQL
if mysql -u root -e "exit" >/dev/null 2>&1; then
    echo "Identificado: MySQL root acessível sem senha."
    MYSQL_CMD="mysql -u root"
else
    echo "MySQL root exige senha, sudo ou acesso negado."
    echo "Dica: Em sistemas Linux/Mac, se o comando acima falhou, tente rodar este script com 'sudo ./iniciar_banco.sh'"
    echo ""
    read -s -p "Digite a senha do root do MySQL/MariaDB (ou deixe em branco para tentar sem): " MYSQL_ROOT_PASSWORD
    echo ""

    if [ -z "$MYSQL_ROOT_PASSWORD" ]; then
        MYSQL_CMD="mysql -u root"
    else
        MYSQL_CMD="mysql -u root -p$MYSQL_ROOT_PASSWORD"
    fi
fi


echo "[1/6] Recriando o banco de dados 'db_fluxocapital'..."

if ! $MYSQL_CMD -e "DROP DATABASE IF EXISTS db_fluxocapital;" 2>/dev/null; then
    echo "⚠️  Não foi possível acessar MySQL como root. Tentando com sudo..."
    MYSQL_CMD="sudo mysql -u root"
fi

$MYSQL_CMD -e "DROP DATABASE IF EXISTS db_fluxocapital;"
$MYSQL_CMD -e "CREATE DATABASE db_fluxocapital CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"


echo "[2/6] Criando o usuário 'user_fluxocapital'..."

$MYSQL_CMD -e "CREATE USER IF NOT EXISTS 'user_fluxocapital'@'localhost' IDENTIFIED BY '1qhnTXZDCz8P4cB7n';" 2>/dev/null \
|| $MYSQL_CMD -e "ALTER USER 'user_fluxocapital'@'localhost' IDENTIFIED BY '1qhnTXZDCz8P4cB7n';"


echo "[3/6] Concedendo permissões..."

$MYSQL_CMD -e "GRANT ALL PRIVILEGES ON db_fluxocapital.* TO 'user_fluxocapital'@'localhost';"


echo "[4/6] Atualizando privilégios..."

$MYSQL_CMD -e "FLUSH PRIVILEGES;"


echo "[5/6] Criando arquivo .env de configuração local..."

if [ ! -f ".env" ]; then
    echo "DB_USER=user_fluxocapital" > .env
    echo "DB_PASS=1qhnTXZDCz8P4cB7n" >> .env
    echo "DB_HOST=localhost" >> .env
    echo "DB_NAME=db_fluxocapital" >> .env
    echo "✅ Arquivo .env criado com as credenciais padrão!"
else
    echo "ℹ️  Arquivo .env já existe, mantendo as configurações atuais."
fi


echo "[6/6] Importando dados de teste do arquivo db_fluxocapital.sql..."

if [ -f "db_fluxocapital.sql" ]; then
    if $MYSQL_CMD -D db_fluxocapital < db_fluxocapital.sql; then
        echo ""
        echo "✅ Banco de dados configurado e populado com sucesso!"
    else
        echo ""
        echo "❌ Erro ao importar os dados do arquivo .sql!"
        exit 1
    fi
else
    echo "❌ Erro: Arquivo db_fluxocapital.sql não encontrado no diretório atual!"
    exit 1
fi

