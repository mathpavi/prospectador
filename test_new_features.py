import agent
import os

def run_tests():
    print("=== TESTING NEW FEATURES ===")
    
    # 1. Test DNS email validation
    test_emails = [
        ("mathp@hotmail.com", True),
        ("contato@google.com", True),
        ("contato@nonexistent-fake-domain-999.com", False),
        ("invalid-email-format", False)
    ]
    
    print("\n1. Testing DNS email validation:")
    for email, expected in test_emails:
        res = agent.validate_email_dns(email)
        status = "PASS" if res == expected else "FAIL"
        print(f"  [{status}] validate_email_dns('{email}') -> {res} (Expected: {expected})")
        
    # 2. Test Playwright screenshot capture
    print("\n2. Testing Playwright screenshot capture:")
    test_url = "https://example.com"
    test_filename = "test_example_screenshot.png"
    
    output_path = agent.capture_screenshot(test_url, test_filename)
    if output_path and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        print(f"  [PASS] Screenshot captured successfully at: {output_path} (Size: {os.path.getsize(output_path)} bytes)")
    else:
        print(f"  [FAIL] Failed to capture screenshot for: {test_url}")
        
    print("\n=== VERIFICATION COMPLETE ===")

if __name__ == "__main__":
    run_tests()
