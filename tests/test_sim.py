import unittest

from oh_my_rtl_claw.sim.sim_parser import parse_simulation_log


class SimParserTests(unittest.TestCase):
    def test_sim_parser_pass(self):
        result = parse_simulation_log("TEST 1\nPASS\n")
        self.assertTrue(result["passed"])

    def test_sim_parser_accepts_final_pass(self):
        result = parse_simulation_log("all vectors complete\nFINAL PASS\n")
        self.assertTrue(result["passed"])

    def test_sim_parser_fail(self):
        result = parse_simulation_log("FAIL\n")
        self.assertFalse(result["passed"])

    def test_sim_parser_rejects_substring_pass(self):
        result = parse_simulation_log("BYPASS path covered\n")
        self.assertFalse(result["passed"])


if __name__ == "__main__":
    unittest.main()
