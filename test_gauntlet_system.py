import unittest
import os
import sys

# Setup paths
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tests.gauntlet import evaluator

class TestGauntletSystem(unittest.TestCase):
    
    def test_gauntlet_run_passes(self):
        # Run the gauntlet evaluator and check if it passes the 95% threshold
        passed = evaluator.run_gauntlet()
        self.assertTrue(passed, "O Gauntlet-Loop reprovou a estabilidade global do sistema!")

if __name__ == '__main__':
    unittest.main()
