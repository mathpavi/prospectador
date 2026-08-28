import unittest
import json
from datetime import datetime, timedelta
import os
import sys

# Setup paths
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import database
import app

class TestAutomationSystem(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        database.init_db()

    def setUp(self):
        # Clear settings for a clean state
        database.save_settings({
            'autopilot_sender_enabled': '0',
            'autopilot_sender_interval_min': '20',
            'autopilot_sender_start_hour': '8',
            'autopilot_sender_end_hour': '18',
            'autopilot_sender_days': '1,2,3,4,5',
            'autopilot_auto_approve': '0'
        })

    def test_commercial_hours_calculation(self):
        now = datetime.now()
        current_day = now.weekday() + 1
        current_hour = now.hour
        
        # 1. Setup settings to strictly match current time
        database.save_settings({
            'autopilot_sender_days': str(current_day),
            'autopilot_sender_start_hour': str(current_hour),
            'autopilot_sender_end_hour': str(current_hour + 1)
        })
        
        ok, msg = app.check_commercial_hours()
        self.assertTrue(ok, f"Should be valid commercial hours. Reason: {msg}")
        
        # 2. Setup settings to exclude current day
        wrong_day = 1 if current_day != 1 else 2
        database.save_settings({
            'autopilot_sender_days': str(wrong_day)
        })
        ok, msg = app.check_commercial_hours()
        self.assertFalse(ok, "Should fail because it is not an allowed day")
        
        # 3. Setup settings to exclude current hour
        database.save_settings({
            'autopilot_sender_days': str(current_day),
            'autopilot_sender_start_hour': str((current_hour + 2) % 24),
            'autopilot_sender_end_hour': str((current_hour + 3) % 24)
        })
        ok, msg = app.check_commercial_hours()
        self.assertFalse(ok, "Should fail because it is outside commercial hours range")

    def test_sending_interval_check(self):
        # 1. No last sent timestamp - should be True
        database.save_settings({'autopilot_last_email_sent_at': ''})
        ok, msg = app.check_sending_interval()
        self.assertTrue(ok)
        
        # 2. Last sent 30 minutes ago, interval is 20 - should be True
        past_time = (datetime.now() - timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S')
        database.save_settings({
            'autopilot_last_email_sent_at': past_time,
            'autopilot_sender_interval_min': '20'
        })
        ok, msg = app.check_sending_interval()
        self.assertTrue(ok)
        
        # 3. Last sent 5 minutes ago, interval is 20 - should be False
        recent_time = (datetime.now() - timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')
        database.save_settings({
            'autopilot_last_email_sent_at': recent_time,
            'autopilot_sender_interval_min': '20'
        })
        ok, msg = app.check_sending_interval()
        self.assertFalse(ok)

    def test_auto_approval_on_insert(self):
        # 1. With auto approve disabled
        database.save_settings({'autopilot_auto_approve': '0'})
        lead_data_1 = {
            'company_name': 'Test Lead No Approve',
            'website': 'https://noapprove.com',
            'segment': 'Test',
            'region': 'Test Region',
            'status': 'pending',
            'contact_email': 'test@noapprove.com'
        }
        lead_id_1 = database.add_prospect(lead_data_1)
        lead_1 = database.get_prospect(lead_id_1)
        self.assertEqual(lead_1['status'], 'pending')
        
        # Cleanup
        conn = database.get_db_connection()
        conn.cursor().execute("DELETE FROM prospects WHERE id = ?", (lead_id_1,))
        conn.commit()
        conn.close()

        # 2. With auto approve enabled
        database.save_settings({'autopilot_auto_approve': '1'})
        lead_data_2 = {
            'company_name': 'Test Lead Auto Approve',
            'website': 'https://autoapprove.com',
            'segment': 'Test',
            'region': 'Test Region',
            'status': 'pending',
            'contact_email': 'test@autoapprove.com'
        }
        lead_id_2 = database.add_prospect(lead_data_2)
        lead_2 = database.get_prospect(lead_id_2)
        self.assertEqual(lead_2['status'], 'approved')
        
        # Cleanup
        conn = database.get_db_connection()
        conn.cursor().execute("DELETE FROM prospects WHERE id = ?", (lead_id_2,))
        conn.commit()
        conn.close()

if __name__ == '__main__':
    print("=== STARTING AUTOPILOT AND AUTOMATION TESTS ===")
    unittest.main()
