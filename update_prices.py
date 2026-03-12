import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime
from app import app, db, Ativo

# --- Sessão HTTP com retry automático ---
retry_strategy = Retry(
    total=3,
    connect=False,      # Não retenta erros de DNS/conexão (inútil, não muda nada)
    read=False,         # Não retenta erros de leitura
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504]  # Só retenta erros HTTP transitórios
)
adapter = HTTPAdapter(max_retries=retry_strategy)
http_session = requests.Session()
http_session.mount("https://", adapter)

def get_price(ticker, headers):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1d"
        response = http_session.get(url, headers=headers, timeout=5)
        response.raise_for_status()  # Melhoria 1: lança exceção para 4xx/5xx
        dados = response.json()
        # Melhoria 2: verificação segura de chaves antes de acessar
        if dados and 'chart' in dados and dados['chart']['result']:
            return dados['chart']['result'][0]['meta']['regularMarketPrice']
    except Exception:
        return None
    return None

def get_pvp(ticker):
    try:
        url = f"https://content.btgpactual.com/api/research/public-router/content-hub-assets/v1/asset-indicators/{ticker}?periodFilter=LAST_12_MONTHS&locale=pt-BR"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = http_session.get(url, headers=headers, timeout=5)
        response.raise_for_status()  # Melhoria 1: lança exceção para 4xx/5xx
        data = response.json()
        for cat in data.get('categories', []):
            for ind in cat.get('indicators', []):
                # O indicador pode ter nomes diferentes para Ações e FIIs
                if ind.get('indicator', {}).get('indicator') in ['PRICE_TO_BOOK_VALUE', 'PRICE_TO_BOOK_VALUE_REIT']:
                    # Pega o último valor disponível (mais recente)
                    if ind.get('data'):
                        return ind['data'][-1][1]
    except Exception:
        return None
    return None

def atualizar():
    with app.app_context():
        try:
            # Pegamos todos os ativos para agrupar por ticker
            todos_ativos = db.session.query(Ativo.ticker, Ativo.categoria).all()
            
            if not todos_ativos:
                print("Nenhum ativo encontrado.")
                return

            # Agrupa por ticker e decide a categoria predominante (ou Internacional se houver)
            tickers_map = {}
            for a in todos_ativos:
                if a.ticker not in tickers_map:
                    tickers_map[a.ticker] = a.categoria
                else:
                    # Se houver 'Internacional' entre as categorias deste ticker, prioriza
                    if a.categoria == 'Internacional':
                        tickers_map[a.ticker] = 'Internacional'

            print(f"\n--- Início da Atualização: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} ---")
            headers = {'User-Agent': 'Mozilla/5.0'}

            # 1. Buscar cotação do Dólar primeiro
            usd_brl = get_price("USDBRL=X", headers)
            if usd_brl:
                print(f"[CÂMBIO] USDBRL: R$ {usd_brl:.4f}")
            else:
                print("[CÂMBIO] Erro ao buscar dólar. Usando 5.00 como fallback.")
                usd_brl = 5.00

            for ticker, categoria in tickers_map.items():
                preco_final = None
                pvp_final = None
                
                try:
                    if categoria == 'Internacional':
                        ticker_yahoo = ticker
                        preco_raw = get_price(ticker_yahoo, headers)
                        if preco_raw:
                            preco_final = preco_raw * usd_brl
                            print(f"[{ticker}] US$ {preco_raw:.2f} -> R$ {preco_final:.2f} (Convertido)")
                    else:
                        # Ativos B3
                        ticker_yahoo = f"{ticker}.SA"
                        preco_final = get_price(ticker_yahoo, headers)
                        # Busca P/VP apenas para B3 (Ações e FIIs principalmente)
                        pvp_final = get_pvp(ticker)
                        
                        if preco_final:
                            print(f"[{ticker}] R$ {preco_final:.2f} | P/VP: {pvp_final if pvp_final else 'N/A'}")

                    if preco_final is not None:
                        update_values = {"preco_atual": preco_final}
                        if pvp_final is not None:
                            update_values["pvp"] = pvp_final
                        
                        # Melhoria 3: synchronize_session=False evita overhead do SQLAlchemy
                        db.session.query(Ativo).filter(Ativo.ticker == ticker).update(
                            update_values, synchronize_session=False
                        )

                except Exception as e:
                    print(f"[{ticker}] Erro: {e}")

            db.session.commit()
            print(f"--- Fim da Atualização ---\n")

        except Exception as e:
            print(f"Erro geral: {e}")

if __name__ == "__main__":
    atualizar()
