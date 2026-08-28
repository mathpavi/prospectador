import unittest
import os
import sqlite3
import database
import agent_international

class TestInternationalExpatProspecting(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        # Enforce clean test db
        if os.path.exists("prospector.db"):
            # Ensure tables are migrated
            database.init_db()

    def test_database_migrations_exist(self):
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(prospects)")
        columns = [col['name'] for col in cursor.fetchall()]
        conn.close()
        
        self.assertIn('is_international', columns)
        self.assertIn('international_country', columns)
        
    def test_phone_number_cleaning(self):
        # US (DDI: 1)
        self.assertEqual(agent_international.clean_phone_international("617-456-7890", "1"), "+16174567890")
        self.assertEqual(agent_international.clean_phone_international("+1 (617) 456-7890", "1"), "+16174567890")
        
        # Portugal (DDI: 351)
        self.assertEqual(agent_international.clean_phone_international("912 345 678", "351"), "+351912345678")
        self.assertEqual(agent_international.clean_phone_international("+351 912 345 678", "351"), "+351912345678")
        
        # Brazil Expats keeping DDI 55
        self.assertEqual(agent_international.clean_phone_international("+55 (51) 99766-1506", "1"), "+5551997661506")
        
        
    def test_candidate_filtering(self):
        # 1. Valid candidate
        self.assertTrue(agent_international.is_valid_international_candidate(
            "https://orlandocleaners.com", "Orlando House Cleaning Service", "We offer top quality maid services in Orlando."
        ))
        
        # 2. Tech / Software keywords
        self.assertFalse(agent_international.is_valid_international_candidate(
            "https://piriform.com/ccleaner/download", "CCleaner - Free download", "Clean your PC of residual temp files."
        ))
        
        # 3. Brazilian site domain (.br)
        self.assertFalse(agent_international.is_valid_international_candidate(
            "https://cleanercampinas.com.br", "Cleaner Campinas - Serviços de Limpeza", "Contrate diaristas e faxineiras em Campinas."
        ))
        
        # 4. Wikipedia directories
        self.assertFalse(agent_international.is_valid_international_candidate(
            "https://en.wikipedia.org/wiki/Vacuum_cleaner", "Vacuum cleaner - Wikipedia", "A vacuum cleaner is a device..."
        ))

        
    def test_reputation_extraction(self):
        # 1. Rating with ★ icon and reviews count in parenthesis
        rating, count = agent_international.extract_reviews_and_rating(
            "★4.9 (126) · House cleaning service. Opens 8:00 AM", "Orlando Cleaners - Orlando, FL"
        )
        self.assertEqual(rating, 4.9)
        self.assertEqual(count, 126)
        
        # 2. Textual reviews count and stars matching
        rating, count = agent_international.extract_reviews_and_rating(
            "This business has 4.5 stars and 34 reviews on Google Maps", "Carlos Handyman Services"
        )
        self.assertEqual(rating, 4.5)
        self.assertEqual(count, 34)

    def test_opportunity_score_calculation(self):
        # 1. Hot Lead (Excellent reputation + sweet spot reviews + no site) -> rating 4.8, reviews 120, has_site False
        score = agent_international.calculate_opportunity_score(4.8, 120, False, False)
        self.assertEqual(score, 100) # 30 (reputation) + 30 (sweet spot) + 40 (no site) = 100
        
        # 2. Average Opportunity (Good reputation + few reviews + amateur site) -> rating 4.5, reviews 15, has_site True, is_amateur True
        score = agent_international.calculate_opportunity_score(4.5, 15, True, True)
        self.assertEqual(score, 70) # 20 (reputation) + 20 (reviews) + 30 (amateur site) = 70
        
        # 3. Low Opportunity (Few reviews + standard professional site) -> rating 4.0, reviews 5, has_site True, is_amateur False
        score = agent_international.calculate_opportunity_score(4.0, 5, True, False)
        self.assertEqual(score, 25) # 10 (reputation) + 5 (reviews) + 10 (standard site) = 25

    def test_expat_signals_detection(self):
        # 1. Common surname
        signals = agent_international.detect_brazilian_expat_signals("Contact Silva Painting LLC at info@silvapainting.com", "https://silvapainting.com")
        self.assertTrue(any("silva" in s.lower() for s in signals))
        
        # 2. Review text in Portuguese
        signals = agent_international.detect_brazilian_expat_signals("O proprietario fez um excelente trabalho, muito obrigado!", "https://localcleaning.com")
        self.assertIn("Reviews/Textos em PT", signals)
        
        # 3. Expat phrase
        signals = agent_international.detect_brazilian_expat_signals("We are a Brazilian cleaning service in Orlando. Falo português.", "https://facebook.com/cleaning")
        self.assertTrue(any("frase expat" in s.lower() for s in signals))
        
        # 4. WhatsApp DDI 55
        signals = agent_international.detect_brazilian_expat_signals("Call us at +55 51 99766-1506", "https://instagram.com/painting")
        self.assertIn("WhatsApp brasileiro (+55)", signals)

    def test_targeted_query_alone_is_not_evidence(self):
        self.assertFalse(agent_international.has_brazilian_evidence([
            "Encontrado por busca específica Brazilian"
        ]))
        self.assertTrue(agent_international.has_brazilian_evidence([
            "Frase expat: 'brazilian owned'"
        ]))

    def test_real_customer_site_signal_patterns(self):
        sunshine = agent_international.detect_brazilian_expat_signals(
            "Our founder moved from Brazil to Georgia", "https://sunshinebrazilian.com")
        casa_bela = agent_international.detect_brazilian_expat_signals(
            "Casa Bela Brazilian Tidy", "https://casabelabrazilian.com")
        number_one = agent_international.detect_brazilian_expat_signals(
            "Nome email telefone City Estado Message", "https://numberonestoneworks.com")
        self.assertTrue(agent_international.has_brazilian_evidence(sunshine))
        self.assertTrue(agent_international.has_brazilian_evidence(casa_bela))
        self.assertTrue(agent_international.has_brazilian_evidence(number_one))

        paivas = agent_international.detect_brazilian_expat_signals(
            "Desenvolvido por Paviani - Todos os direitos reservados.",
            "https://paivascleaning.com")
        total_trust = agent_international.detect_brazilian_expat_signals(
            "EXCELENTE. Com base em avaliações. Atendimento.",
            "https://totaltrustcleaning.com")
        self.assertTrue(agent_international.has_brazilian_evidence(paivas))
        self.assertTrue(agent_international.has_brazilian_evidence(total_trust))
        paviani_client = agent_international.detect_brazilian_expat_signals(
            '<a href="https://paviani.net">Paviani Digital Media</a>',
            "https://totaltrustcleaning.com")
        self.assertTrue(agent_international.has_brazilian_evidence(paviani_client))

    def test_targeted_serper_uses_one_request(self):
        from unittest.mock import patch, Mock
        with patch('requests.post') as mock_post:
            response = Mock(status_code=200)
            response.json.return_value = {"organic": [{
                "title": "Brazilian Cleaning Orlando",
                "link": "https://brazilian-clean.example",
                "snippet": "Brazilian-owned and Portuguese speaking"
            }]}
            mock_post.return_value = response
            candidates = agent_international.search_brazilian_leads_serper(
                "cleaning", "Orlando", "US", "fake-key", 10)
        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(len(candidates), 1)
        self.assertIn("brazilian", mock_post.call_args.kwargs["json"]["q"])

    def test_get_prospects_isolation(self):
        # Clear existing leads matching test names to avoid failures
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM prospects WHERE company_name LIKE 'Test Expat%'")
        conn.commit()
        conn.close()
        
        # Add normal prospect
        normal_id = database.add_prospect({
            "company_name": "Test Expat Normal",
            "website": "https://normalexpat.com",
            "segment": "Cleaning",
            "region": "Boston",
            "is_international": 0
        })
        
        # Add international prospect
        intl_id = database.add_prospect({
            "company_name": "Test Expat International",
            "website": "https://intlcleaner.com",
            "segment": "Cleaning",
            "region": "Boston - Estados Unidos",
            "is_international": 1,
            "international_country": "US"
        })
        
        # 1. Standard query should only return normal lead, NOT international lead
        normal_leads = database.get_prospects()
        normal_ids = [p['id'] for p in normal_leads]
        self.assertIn(normal_id, normal_ids)
        self.assertNotIn(intl_id, normal_ids)
        
        # 2. International query should only return international lead, NOT normal lead
        intl_leads = database.get_prospects(is_international_filter=1)
        intl_ids = [p['id'] for p in intl_leads]
        self.assertIn(intl_id, intl_ids)
        self.assertNotIn(normal_id, intl_ids)
        
        # Clean up
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM prospects WHERE id IN (?, ?)", (normal_id, intl_id))
        conn.commit()
        conn.close()

    def test_serper_mapping(self):
        from unittest.mock import patch, Mock
        
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "places": [
                    {
                        "title": "Maidpro Orlando",
                        "address": "Orlando, FL",
                        "rating": 4.8,
                        "ratingCount": 124,
                        "category": "House cleaning service",
                        "website": "https://www.maidpro.com/orlando",
                        "phoneNumber": "+1 407-555-0199"
                    }
                ]
            }
            mock_post.return_value = mock_response
            
            candidates = agent_international.search_companies_serper(
                segment="cleaning",
                city_name="Orlando",
                country_code="US",
                api_key="fake-key",
                limit=5
            )
            
            self.assertEqual(len(candidates), 1)
            c = candidates[0]
            self.assertEqual(c["url"], "https://www.maidpro.com/orlando")
            self.assertEqual(c["title"], "Maidpro Orlando")
            self.assertEqual(c["rating"], 4.8)
            self.assertEqual(c["reviews_count"], 124)
            self.assertEqual(c["phone"], "+1 407-555-0199")

    def test_serper_keeps_places_without_website(self):
        from unittest.mock import patch, Mock
        with patch('requests.post') as mock_post:
            response = Mock(status_code=200)
            response.json.return_value = {"places": [{
                "title": "Brazilian Clean Orlando", "cid": "12345",
                "phoneNumber": "+1 407-555-0100"
            }]}
            mock_post.return_value = response
            candidates = agent_international.search_companies_serper(
                "cleaning", "Orlando", "US", "fake-key", 5)
        self.assertEqual(candidates[0]["url"], "https://www.google.com/maps?cid=12345")
        self.assertTrue(candidates[0]["brazilian_query"])

    def test_gosom_row_mapping(self):
        candidate = agent_international._gosom_candidate({
            "title": "Silva Cleaning", "link": "https://maps.google.com/example",
            "phone": "+1 407 555 0101", "review_rating": "4.9",
            "review_count": "88", "emails": "hello@silvacleaning.com; sales@silvacleaning.com"
        }, brazilian_query=True)
        self.assertEqual(candidate["rating"], 4.9)
        self.assertEqual(candidate["reviews_count"], 88)
        self.assertEqual(candidate["emails"][0], "hello@silvacleaning.com")
        self.assertTrue(candidate["brazilian_query"])

    def test_gosom_api_contract(self):
        from unittest.mock import Mock
        session = Mock()
        created = Mock()
        created.json.return_value = {"id": "job-123"}
        created.raise_for_status.return_value = None
        completed = Mock()
        completed.json.return_value = {"Status": "ok"}
        completed.raise_for_status.return_value = None
        csv_result = Mock()
        csv_result.content = (
            b"input_id,title,link,website,phone,review_rating,review_count,emails\n"
            b"brazilian,Silva Cleaning,https://maps.example/1,,+14075550101,4.9,88,hello@silva.example\n"
        )
        csv_result.raise_for_status.return_value = None
        session.post.return_value = created
        session.get.side_effect = [completed, csv_result]

        candidates = agent_international.search_companies_gosom(
            "cleaning", "Orlando", "US", "http://localhost:8080", 5,
            session=session)
        payload = session.post.call_args.kwargs["json"]
        self.assertTrue(payload["email"])
        self.assertIn("#!#brazilian", payload["keywords"][1])
        self.assertEqual(candidates[0]["title"], "Silva Cleaning")
        self.assertTrue(candidates[0]["brazilian_query"])

if __name__ == '__main__':
    unittest.main()
