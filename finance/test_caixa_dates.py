from datetime import date
from django.test import SimpleTestCase
from .bank_classification import caixa_operation_date


class CaixaOperationDateTests(SimpleTestCase):
    def infer(self, description='ON 369092994 0610', bank_date='2026-10-07'):
        return caixa_operation_date({'description':description,'bank_date':bank_date},'369092994')

    def test_same_day_weekend_window_and_year_boundary(self):
        self.assertEqual(self.infer(bank_date='2026-10-06'),date(2026,10,6))
        self.assertEqual(self.infer(bank_date='2026-10-13'),date(2026,10,6))
        self.assertEqual(self.infer('ON 369092994 3112','2027-01-02'),date(2026,12,31))
        self.assertEqual(self.infer('ON 369092994 2902','2024-03-01'),date(2024,2,29))

    def test_invalid_future_old_and_ambiguous_descriptions_stay_pending(self):
        for description,bank_date in [
            ('ON 369092994 3102','2026-03-01'),
            ('ON 369092994 0810','2026-10-07'),
            ('ON 369092994 0610','2026-10-14'),
            ('ON 369092994 2902','2026-03-01'),
            ('ON 369092994 0610 ON 369092994 0510','2026-10-07'),
            ('Transfer 369092994 0610','2026-10-07'),
            ('ON 3690929949 0610','2026-10-07'),
            ('ON 369092994 0610','invalid'),
        ]:
            with self.subTest(description=description,bank_date=bank_date):
                self.assertIsNone(self.infer(description,bank_date))
