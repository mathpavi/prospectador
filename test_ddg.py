try:
    from ddgs import DDGS
    print("Sucesso: importado 'DDGS' de 'ddgs'")
except Exception as e:
    print(f"Falha ao importar de 'ddgs': {e}")
    try:
        from duckduckgo_search import DDGS
        print("Sucesso: importado 'DDGS' de 'duckduckgo_search'")
    except Exception as ex:
        print(f"Falha total de importacao: {ex}")
        sys.exit(1)

try:
    print("Realizando busca de teste...")
    with DDGS() as ddgs:
        results = list(ddgs.text("metalúrgica Caxias do Sul", max_results=5))
        print(f"Encontrados {len(results)} resultados:")
        for idx, r in enumerate(results):
            print(f"[{idx+1}] {r.get('title')} -> {r.get('href')}")
except Exception as e:
    print(f"Erro ao buscar: {e}")
