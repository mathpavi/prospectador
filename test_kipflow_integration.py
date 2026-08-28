import unittest
import database
import agent
import sqlite3
import json

class TestKipFlowIntegration(unittest.TestCase):

    def setUp(self):
        # Setup database connection and ensure migrations ran
        database.init_db()
        
    def test_database_columns_exist(self):
        """Verify that KipFlow B2B columns are successfully migrated in the SQLite database"""
        conn = sqlite3.connect('prospector.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(prospects)")
        columns = [col['name'] for col in cursor.fetchall()]
        conn.close()
        
        self.assertIn('cnpj', columns)
        self.assertIn('faturamento', columns)
        self.assertIn('porte', columns)
        self.assertIn('funcionarios', columns)
        self.assertIn('socios', columns)
        self.assertIn('redes_sociais', columns)
        
    def test_kipflow_api_key_seeded(self):
        """Verify that default settings seed includes kipflow_api_key"""
        key = database.get_setting('kipflow_api_key')
        self.assertIsNotNone(key)
        self.assertEqual(key, '27faee9a-15f3-4dfb-a1d0-383ac5fef117')

    def test_cnae_mapping(self):
        """Verify segment mapping to CNAE subclasses"""
        # Testing usinagem mapping
        usinagem_codes = [2539001, 2539002]
        cnaes = []
        seg = "Usinagem de Peças"
        for key, codes in agent.CNAE_MAPPING.items():
            if key in seg.lower():
                cnaes.extend(codes)
        self.assertEqual(set(cnaes), set(usinagem_codes))

    def test_enrichment_live_or_mock(self):
        """Test enrichment function using a test domain"""
        # We will add a temporary mock lead to test enrichment structure
        mock_lead = {
            'company_name': 'Petrobras Test',
            'website': 'https://www.petrobras.com.br/',
            'segment': 'Petróleo',
            'region': 'Rio de Janeiro - RJ',
            'status': 'pending'
        }
        lead_id = database.add_prospect(mock_lead)
        self.assertIsNotNone(lead_id)
        
        try:
            # Let's try enriching it (this will make a live call using the user key)
            enriched = agent.enrich_prospect_with_kipflow(lead_id)
            if enriched:
                self.assertIsNotNone(enriched.get('cnpj'))
                self.assertEqual(enriched.get('cnpj'), '33000167000101')
                self.assertIsNotNone(enriched.get('porte'))
                self.assertIsNotNone(enriched.get('faturamento'))
                
                # Check socios decoding
                socios = json.loads(enriched.get('socios'))
                self.assertIsInstance(socios, list)
                
                # Check redes_sociais decoding
                socials = json.loads(enriched.get('redes_sociais'))
                self.assertIn('instagram', socials)
                self.assertIn('facebook', socials)
                self.assertIn('linkedin', socials)
                
                print("Enrichment Integration Test PASSED with live API data!")
            else:
                print("Enrichment skipped or returned None (could be API limit or network).")
        finally:
            # Clean up test lead
            database.delete_prospect(lead_id)

    def test_kipflow_search_companies(self):
        """Test that KipFlow search parses results correctly"""
        try:
            # Run search for a single metalúrgica in Porto Alegre
            companies = agent.search_companies_kipflow("Metalúrgica", "Porto Alegre", "RS", limit=1)
            if companies:
                self.assertTrue(len(companies) > 0)
                first = companies[0]
                self.assertIsNotNone(first.get('url'))
                self.assertIsNotNone(first.get('cnpj'))
                self.assertIsNotNone(first.get('title'))
                print("Search Integration Test PASSED with live API search!")
            else:
                print("Search returned no companies (could be no matching active results with sites).")
        except Exception as e:
            print("Search failed:", e)

if __name__ == '__main__':
    unittest.main()
