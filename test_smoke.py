import sys
import os

print("=== SMOKE TEST INICIADO ===")
print(f"Python executando de: {sys.executable}")
print(f"Versao do Python: {sys.version}")
print(f"Diretorio de trabalho: {os.getcwd()}")
print("-----------------------------------------")

# 1. Test Database
print("1. Testando Banco de Dados SQLite...", end="")
try:
    import database
    database.init_db()
    name = database.get_setting('sender_name')
    print(f" OK (Remetente padrao: '{name}')")
except Exception as e:
    print(f" ERRO: {e}")

# 2. Test imports
print("2. Testando importacoes das dependencias...")
try:
    import flask
    print("   - Flask importado OK")
except Exception as e:
    print(f"   - Flask ERRO: {e}")

try:
    import bs4
    print("   - BeautifulSoup4 importado OK")
except Exception as e:
    print(f"   - BeautifulSoup4 ERRO: {e}")

try:
    import google.generativeai as genai
    print("   - google-generativeai importado OK")
except Exception as e:
    print(f"   - google-generativeai ERRO: {e}")

try:
    from ddgs import DDGS
    print("   - ddgs importado OK")
except ImportError:
    try:
        from duckduckgo_search import DDGS
        print("   - duckduckgo-search importado OK")
    except Exception as e:
        print(f"   - duckduckgo-search/ddgs ERRO: {e}")

# 3. Test DuckDuckGo Search (Quick Test)
print("3. Testando Conectividade & Busca DuckDuckGo...", end="")
try:
    with DDGS() as ddgs:
        results = [r for r in ddgs.text("metalurgica Caxias do Sul", max_results=2)]
    print(f" OK (Encontrados {len(results)} resultados)")
    for i, r in enumerate(results):
        print(f"   [{i+1}] Title: {r.get('title')} | Link: {r.get('href')}")
except Exception as e:
    print(f" ERRO: {e}")

print("-----------------------------------------")
print("=== FIM DO SMOKE TEST ===")
