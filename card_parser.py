import PyPDF2
import pdfplumber
import re
from datetime import datetime, date
from decimal import Decimal
from models import GastoCartao, Transacao, Categoria, Carteira
from extensions import db


def parse_xp_pdf(pdf_path):
    transactions = []
    total_value = Decimal('0.00')
    due_date = None
    
    with open(pdf_path, 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        
        # Extract Summary from Page 1
        page1_text = reader.pages[0].extract_text()
        
        # Find Due Date (Vencimento)
        # Looking for DD/MM/YYYY
        due_date_match = re.search(r'Vencimento\n(\d{2}/\d{2}/\d{4})', page1_text)
        if not due_date_match:
            # Fallback search
            due_date_match = re.search(r'(\d{2}/\d{2}/\d{4})', page1_text)
            
        if due_date_match:
            due_date = datetime.strptime(due_date_match.group(1), '%d/%m/%Y').date()
            
        # Find Total Value
        # Looking for something like 7.720,27
        # It's usually after "Valor do Documento" or near the end of the boleto
        total_match = re.search(r'Valor do Documento\n([\d\.,]+)', page1_text)
        if not total_match:
            # Try finding the last currency looking value in the summary part
            potential_values = re.findall(r'(\d+\.\d{3},\d{2})', page1_text)
            if potential_values:
                total_value = Decimal(potential_values[-1].replace('.', '').replace(',', '.'))
        else:
            total_value = Decimal(total_match.group(1).replace('.', '').replace(',', '.'))

        # Extract Transactions from subsequent pages
        # Format: DD/MM/YY DESCRIPTION VALUE_BRL VALUE_USD
        # Example: 11/02/26 BEMAIS SUPERMERCADOS 104,53 0,00
        
        for i in range(1, len(reader.pages)):
            text = reader.pages[i].extract_text()
            lines = text.split('\n')
            for line in lines:
                # Regex for DD/MM/YY Description Value_BRL Value_USD
                match = re.search(r'^(\d{2}/\d{2}/\d{2})\s+(.*?)\s+([\d\.,]+)\s+([\d\.,]+)$', line)
                if match:
                    t_date_str = match.group(1)
                    description = match.group(2).strip()
                    value_str = match.group(3)
                    
                    # Convert date 11/02/26 to date object
                    # We assume 20YY
                    t_date = datetime.strptime(t_date_str, '%d/%m/%y').date()
                    val = Decimal(value_str.replace('.', '').replace(',', '.'))
                    
                    transactions.append({
                        'data': t_date,
                        'descricao': description,
                        'valor': val
                    })

    return {
        'due_date': due_date,
        'total_value': total_value,
        'transactions': transactions,
        'banco': 'XP'
    }

def parse_carrefour_pdf(pdf_path):
    transactions = []
    total_value = Decimal('0.00')
    due_date = None
    
    with pdfplumber.open(pdf_path) as pdf:
        full_text = ""
        for page in pdf.pages:
            t = page.extract_text()
            if t: full_text += t + "\n"
            
        match_summary = re.search(r'R\$\s*([\d\.,]+)\s+(\d{2}/\d{2}/\d{4})', full_text)
        if match_summary:
            total_value = Decimal(match_summary.group(1).replace('.', '').replace(',', '.'))
            due_date = datetime.strptime(match_summary.group(2), '%d/%m/%Y').date()
            
        lines = full_text.split('\n')
        in_transactions = False
        for line in lines:
            if "LANÇAMENTOS NO BRASIL" in line:
                in_transactions = True
                continue
            if "TOTAL DA FATURA" in line and in_transactions:
                break
                
            if in_transactions:
                match = re.search(r'^(\d{2}/\d{2})\s+(.*?)\s+([\d\.,]+)(-)?$', line.strip())
                if match:
                    if "Pagamento" in match.group(2): continue
                    
                    t_day_month = match.group(1)
                    desc = match.group(2).strip()
                    val_str = match.group(3)
                    is_negative = match.group(4) == '-'
                    
                    val = Decimal(val_str.replace('.', '').replace(',', '.'))
                    
                    t_day, t_month = map(int, t_day_month.split('/'))
                    t_year = due_date.year if due_date else datetime.now().year
                    if due_date and due_date.month == 1 and t_month == 12:
                        t_year -= 1
                    t_date = date(t_year, t_month, t_day)
                    
                    # Store only positive expenses (or ignore refunds?)
                    if not is_negative:
                        transactions.append({
                            'data': t_date,
                            'descricao': desc,
                            'valor': val
                        })
                        
    return {
        'due_date': due_date,
        'total_value': total_value,
        'transactions': transactions,
        'banco': 'Carrefour'
    }

def detect_and_parse_pdf(pdf_path):
    # Try reading first few pages with pdfplumber to detect bank
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:3]:
                t = page.extract_text()
                if t: text += t
    except Exception:
        pass # fallback or failed
        
    if "CARREFOUR" in text.upper() or "BANCO CSF" in text.upper():
        return parse_carrefour_pdf(pdf_path)
    else:
        # Default or if it mentions XP
        return parse_xp_pdf(pdf_path)
def categorizar_gasto(descricao, categorias_db):
    desc = descricao.upper()
    
    # Keyword mapping
    mapa_categorias = {
        'Combustível': ['IPIRANGA', 'PETROBRAS', 'SHELL', 'ALE'],
        'Alimentação': ['SUPERMERCADO', 'IFOOD', 'UBER EATS', 'ZEDELIVERY', 'RESTAURANTE', 'LANCHONETE', 'PADARIA', 'BEMAIS', 'MERCADO', 'BURGER', 'PIZZA', 'DOCERIA', 'BOLOS', 'IFD*BR', 'MENOR PRECO', 'PANIFICADORA', 'DELIVERY', 'PBFOODCOMERCIODE', 'MANGA DOCE', 'GRAO FORNERIA', 'MANGAI PB', 'DANIEL PEREIRA DE CARV', 'CARREFOUR JPE LJ 274', 'REDE COMPRAS AEROCLUBE', 'CAPPTA *SABOR DA FRUTA', 'JOAO PESSOA DRIVE', 'PDV*FAVO DE MEL', 'BM BESSA LTDA', 'LA CIARLINI', 'MP*PICACHADEOURO', 'SABOR DE BOLO', 'PITTSBURG - MOSSORO', 'TWMCANOA', 'CANTINHODASARDENH', 'MOSSORO SHOPPING', 'LUCASCRISTALFREIR', 'MP*COCOBURGUER', 'CHEGA MAIS BEACH LOUN', 'MP*ADEGAEPEIXARI', 'LOUISYBUFFET', 'LOJAS AMERICANAS', '4017 SAM S BESSA', 'REI DAS CARNES', 'PAO DE ACUCAR-1284', 'MP*CALDODECANA', 'POMAR NATURAL', 'BONA S MANAIRA', 'SPOLETO MAG SHOPP', 'CANTINAJARDIM', 'FN LISBOA BISTRO LTDA', 'MERCADINHO SAO SEBASTI', 'CONVENIENCIA SULA', 'ESQUINA DO PAO', 'DOM CARLOS BUFFET', 'CGB COMERCIO E SE', 'CASA SERTANEJA RETAO', 'JIM.COM* 38157929 HELDER', 'ALICETORTAS', 'ALEXANDRE R PESSOA FILH', 'GRILETTO SHOP MANAIRA', 'IFD*TMLA COMERCIO ALIMENT'],
        'Transporte': ['UBER', '99APP', '99 TAXI', 'METRO', 'BILHETE', 'MOBILIDADE', 'POSTO', 'VALET SIGMA JP LTDA', 'JOAO PESSOA DRIVE', 'MP*KINGWASH', 'EC *SHELLBOX', 'REVENDEDORADE', 'EPAR ESTACIONAMEN'],
        'Saúde/Farmácia': ['FARMACIA', 'DROGASIL', 'PAGUE MENOS', 'SAO JOAO', 'RAIA', 'DROGARIA', 'HOSPITAL', 'CLINICA','REDEPHARMA'],
        'Assinaturas/Serviços': ['NETFLIX', 'SPOTIFY', 'AMAZON', 'PRIME', 'HBO', 'DISNEY', 'GLOBO', 'APPLE', 'GOOGLE', 'MICROSOFT'],
        'Lazer': ['CINEMA', 'TEATRO', 'SHOW', 'INGRESSO', 'HOTEL', 'BAR', 'CHEGA MAIS BEACH LOUN', 'CINEPOLIS MANAIRA', 'SHOPPING CENTER MANAIR'],
        'Moradia': ['FERREIRACOSTA', 'FERREIRA COSTA'],
        'Outras Despesas': ['JANEIDE','TOP BRASIL', 'BRAZIL COMERCIO E IMPOR', 'ESTOK DISTRIB E', "VIVARA", 'CASA TUDO','BOTOCLINICSERVICO', 'SPUK', 'FREITAS VAREJO ', 'AMAZON','COLCHOES' , 'JANEIDE JOAO PESS', 'DANIEL PEREIRA DE CARV', 'MARIA CAROLINE BRANDAO', 'ELANEMORAES', 'WILLIAMALVES', 'ALDEMIRCOSTAROLIM', 'HOBBY BICHOS', 'CITY PET RESORT', 'MP*HERNAN', 'TSALEACH COMERCIO DE', 'CAROLINNE', 'REDEBACK', 'MAG - MAG SHOPPING', 'CARLOS MATEUS ALV', 'MARIADACONCEICAO', '42185333CAMILA'],
        'Telefonia/Internet': ['INTERNET'],
        'Casa/Decoração': ['FERREIRACOSTACOM', 'BRAZIL COMERCIO E IMPOR', 'FERREIRA COSTA', 'ESTOK DISTRIB E', 'CASA TUDO', 'FREITAS VAREJO', 'TOP BRASIL', 'CASA TUDO', 'CASA TUDO LOJA 7', 'FREITAS VAREJO', 'COLCHOES ORTOBOM PE', 'PRECOLANDIA', 'TOP BRASIL', 'CASA TUDO', 'FERREIRA COSTA'],
        'Vestuário': ['AREZZO TAMBIA', 'SPUK', 'BROOMER', 'JIM.COM POLO CLUB', 'EMANUELLE CAV 023'],
        'Saúde': ['BOTOCLINICSERVICO', 'UNIMED JOAO PESSOA'],
        'Streaming': ['GLOBO GLOBOPLAY', 'NETFLIX.COM', 'DL*GOOGLE YOUTUB'],
        'Compras Internet': ['AMAZON BR']
    }
    
    # Iterate to find match
    for nome_cat, keywords in mapa_categorias.items():
        if any(kw in desc for kw in keywords):
            # Try to find this category in DB
            for c in categorias_db:
                if c.nome.upper() == nome_cat.upper() or c.nome.upper() in nome_cat.upper():
                    return c.id
            
    # Default to Outros if nothing matches
    for c in categorias_db:
        if c.nome.upper() == 'OUTROS':
            return c.id
            
    return None

def import_card_invoice(pdf_path, carteira='Consolidada'):
    data = detect_and_parse_pdf(pdf_path)

    
    if not data['due_date'] or not data['transactions']:
        return False, "Não foi possível extrair dados da fatura."

    # Create month reference YYYY-MM
    fatura_mes = data['due_date'].strftime('%Y-%m')
    
    # Check if a transaction for this card already exists
    # Description "Fatura Cartão {Banco} - {fatura_mes}"
    descricao_fatura = f"Fatura Cartão {data.get('banco', 'XP')} - {fatura_mes}"

    
    transacao = Transacao.query.filter_by(descricao=descricao_fatura, data=data['due_date']).first()
    is_update = bool(transacao)
    
    if not transacao:
        # Find "Cartão" category or similar
        categoria = Categoria.query.filter(Categoria.nome.like('%Cartão%')).first()
        if not categoria:
             # Default to "Lazer" or something if not found, or create?
             categoria = Categoria.query.filter_by(nome='Outros').first()
        
        c_obj = Carteira.query.filter_by(nome=carteira).first()
        c_id = c_obj.id if c_obj else None

        transacao = Transacao(
            data=data['due_date'],
            descricao=descricao_fatura,
            valor=data['total_value'],
            valor_previsto=data['total_value'],
            valor_pago=0,
            tipo='Despesa',
            categoria_id=categoria.id if categoria else None,
            carteira=carteira,
            carteira_id=c_id,
            pago=False,
            dia_vencimento=data['due_date'].day
        )
        db.session.add(transacao)
        db.session.flush() # Get ID
    
    # Clear existing items for this specific invoice to avoid duplication
    GastoCartao.query.filter_by(fatura_mes=fatura_mes, transacao_id=transacao.id).delete()
    
    # Fetch all categories to avoid hitting DB in loop
    todas_categorias = Categoria.query.all()
    
    for item in data['transactions']:
        cat_id = categorizar_gasto(item['descricao'], todas_categorias)
        
        gasto = GastoCartao(
            fatura_mes=fatura_mes,
            data=item['data'],
            descricao=item['descricao'],
            valor=item['valor'],
            transacao_id=transacao.id,
            categoria_id=cat_id
        )
        db.session.add(gasto)
    
    db.session.commit()
    if is_update:
        return True, "Fatura já importada anteriormente! Total: R$ 0.00"
    else:
        return True, f"Fatura de {fatura_mes} importada com sucesso! Total: R$ {data['total_value']}"

if __name__ == "__main__":
    # Test import
    import sys
    import os
    from app import app
    with app.app_context():
        success, msg = import_card_invoice(os.path.join(os.path.dirname(__file__), "templates", "cartao-XP.pdf"))
        print(msg)

def update_map_categoria(categoria_nome, descricao):
    import re
    import os
    filepath = os.path.join(os.path.dirname(__file__), 'card_parser.py')
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return

    new_kw = descricao.upper().strip()
    new_kw = re.sub(r'\s*-\s*PARCELA\s*\d+/\d+', '', new_kw).strip()
    
    pattern = r"(['\"]" + re.escape(categoria_nome) + r"['\"]\s*:\s*\[)([^\]]*)(\])"
    match = re.search(pattern, content, flags=re.IGNORECASE)
    
    if match:
        def repl(m):
            prefix = m.group(1)
            items = m.group(2)
            suffix = m.group(3)
            # Check se keyword já está mapeada
            if f"'{new_kw}'" in items or f'"{new_kw}"' in items:
                return m.group(0)
            
            if items.strip():
                return f"{prefix}{items}, '{new_kw}'{suffix}"
            else:
                return f"{prefix}'{new_kw}'{suffix}"
        
        new_content = re.sub(pattern, repl, content, flags=re.IGNORECASE)
    else:
        # Categoria não existe no mapa, então adiciona no final do dict
        dict_end_pattern = r"(mapa_categorias\s*=\s*\{.*?)(\n\s*\})"
        def repl_end(m):
            return m.group(1) + f",\n        '{categoria_nome}': ['{new_kw}']" + m.group(2)
        
        new_content = re.sub(dict_end_pattern, repl_end, content, flags=re.DOTALL)

    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
