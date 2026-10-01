import unittest
from unittest.mock import Mock

from collector.registry import INSURERS
from scripts.casco_review import review_selected


class ReviewBatchTests(unittest.TestCase):
    def test_all_insurers_reuse_same_deterministic_review(self):
        reviewer = Mock(side_effect=lambda slug, **kwargs: {
            'insurer': slug, 'published_fields': ['total_loss'], 'documents': []})
        result = review_selected('all', apply=True, reviewer=reviewer)
        self.assertEqual(result['published_fields'], len(INSURERS))
        self.assertEqual({r['insurer'] for r in result['insurers']}, {i.slug for i in INSURERS})
        self.assertTrue(all(call.kwargs == {'apply': True, 'use_ai': False}
                            for call in reviewer.call_args_list))

    def test_all_insurers_cannot_launch_unbounded_ai_requests(self):
        with self.assertRaises(ValueError):
            review_selected('all', apply=True, ai=True, reviewer=Mock())


if __name__ == '__main__':
    unittest.main()
