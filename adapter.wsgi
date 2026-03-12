
import sys
import os
import logging

# Set production environment variables
os.environ['DB_TYPE'] = 'mysql'
os.environ['DB_USER'] = 'user_fluxocapital'
os.environ['DB_PASS'] = '1qhnTXZDCz8P4cB7n'
os.environ['DB_HOST'] = 'localhost'
os.environ['DB_NAME'] = 'db_fluxocapital'

# Configura o log de erros
logging.basicConfig(stream=sys.stderr)

# Caminho do projeto
sys.path.insert(0, "/var/www/fluxocapital_public")

# Importa o app do arquivo app.py
from app import app as application
