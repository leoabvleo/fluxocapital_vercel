#!/bin/bash

# Script automatizado para configurar e rodar o FluxoCapital localmente

echo "================================================="
echo "      Iniciando FluxoCapital (Local)             "
echo "================================================="

# Muda para o diretório do script
cd "$(dirname "$0")"

# 1. Verifica/Cria ambiente virtual (venv)
if [ ! -d "venv" ]; then
    echo "📦 Criando ambiente virtual (venv)..."
    python3 -m venv venv
fi

# 2. Ativa o ambiente virtual
echo "🔋 Ativando ambiente virtual..."
source venv/bin/activate

# 3. Verifica/Instala dependências
echo "🛠️  Verificando dependências..."
./venv/bin/pip install --upgrade pip > /dev/null
./venv/bin/pip install -r requirements.txt | grep -v 'already satisfied'

# 4. Verifica se o banco já foi configurado (.env existe)
if [ ! -f ".env" ]; then
    echo ""
    echo "🚨 ATENÇÃO: O arquivo .env não foi encontrado!"
    echo "💡 Lembre-se de rodar './iniciar_banco.sh' primeiro para configurar o banco de dados."
    echo ""
fi

# 5. Roda a aplicação
echo ""
echo "🚀 Iniciando o sistema..."
echo "📡 Acesse: http://localhost:5001"
echo "Credenciais de Teste:"
echo "Usuário: admin"
echo "Senha: 8mH29DAC"
echo "================================================="
echo ""

# Usa o python do venv diretamente para evitar problemas de ativação
./venv/bin/python3 app.py
