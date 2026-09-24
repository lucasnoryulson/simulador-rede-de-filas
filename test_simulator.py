import unittest
from pathlib import Path

from simulator import load_config, run_simulation


class ValidationModelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).with_name("modelo_validacao.yml")
        cls.env, cls.runs = run_simulation(load_config(path))

    def test_global_time(self):
        self.assertAlmostEqual(self.env.total_time, 50736.0338, places=4)

    def test_losses(self):
        self.assertEqual(self.env.queues["Q1"].losses, 0)
        self.assertEqual(self.env.queues["Q2"].losses, 39)
        self.assertEqual(self.env.queues["Q3"].losses, 11664)

    def test_random_count(self):
        self.assertEqual(self.runs, 1)
        self.assertEqual(self.env.randoms_consumed_per_run, [100000])

    def test_selected_state_times(self):
        self.assertAlmostEqual(self.env.queues["Q1"].state_times[0], 20271.3289, places=4)
        self.assertAlmostEqual(self.env.queues["Q2"].state_times[5], 351.6956, places=4)
        self.assertAlmostEqual(self.env.queues["Q3"].state_times[10], 32145.1085, places=4)


if __name__ == "__main__":
    unittest.main()
