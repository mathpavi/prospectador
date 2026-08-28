import database
import agent
import sqlite3

def run_test():
    print("=== DEDUPLICATION TEST ===")
    
    # 1. Test get_registered_domain
    test_cases = [
        ("www.lupeme.com.br", "lupeme.com.br"),
        ("lupeme.com.br", "lupeme.com.br"),
        ("caldeiraria.unimetais.com.br", "unimetais.com.br"),
        ("unimetais.com.br", "unimetais.com.br"),
        ("google.com", "google.com"),
        ("sub.google.com", "google.com"),
        ("user1.wixsite.com", "wixsite.com"),
        ("wood-factory.ueniweb.com", "ueniweb.com")
    ]
    
    print("1. Testing get_registered_domain:")
    all_passed = True
    for host, expected in test_cases:
        res = database.get_registered_domain(host)
        if res == expected:
            print(f"  [PASS] {host} -> {res}")
        else:
            print(f"  [FAIL] {host} -> {res} (Expected: {expected})")
            all_passed = False
            
    # 2. Test check_domain_exists against temporary in-memory or actual DB
    print("\n2. Testing check_domain_exists in SQLite DB:")
    
    # Let's insert a couple of known test rows in the db
    # We will use check_domain_exists to see if it catches them
    # For safety, let's use the actual db's check_domain_exists but query existing leads
    # From query, we know id 3 has 'https://www.lupeme.com.br/'
    # and id 74 has 'https://caldeiraria.unimetais.com.br/'
    # and id 40 has 'https://wood-factory-moveis-sob-medida.ueniweb.com/'
    
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, website FROM prospects WHERE id IN (3, 74, 40)")
    rows = c.fetchall()
    print("  Active test rows in DB:")
    for r in rows:
        print(f"    ID: {r[0]} | Website: {r[1]}")
    conn.close()
    
    # Check 1: exact domain
    id_lupeme = database.check_domain_exists("lupeme.com.br")
    print(f"  check_domain_exists('lupeme.com.br') -> {id_lupeme} (Expected: 3)")
    
    # Check 2: subdomain lookup
    id_sub_lupeme = database.check_domain_exists("contato.lupeme.com.br")
    print(f"  check_domain_exists('contato.lupeme.com.br') -> {id_sub_lupeme} (Expected: 3)")
    
    # Check 3: root lookup of subdomain database record
    id_root_unimetais = database.check_domain_exists("unimetais.com.br")
    print(f"  check_domain_exists('unimetais.com.br') -> {id_root_unimetais} (Expected: 74)")
    
    # Check 4: shared hosting check (should NOT match distinct user)
    id_other_ueni = database.check_domain_exists("other-factory.ueniweb.com")
    print(f"  check_domain_exists('other-factory.ueniweb.com') -> {id_other_ueni} (Expected: None)")
    
    # Check 5: shared hosting check (should match exact user)
    id_same_ueni = database.check_domain_exists("wood-factory-moveis-sob-medida.ueniweb.com")
    print(f"  check_domain_exists('wood-factory-moveis-sob-medida.ueniweb.com') -> {id_same_ueni} (Expected: 40)")
    
    print("\n=== TEST COMPLETED ===")

if __name__ == "__main__":
    run_test()
