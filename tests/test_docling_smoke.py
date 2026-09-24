import os
import unittest
from collector.casco_document import CascoDocumentParser


@unittest.skipUnless(os.getenv("DOCLING_SMOKE") == "1", "Docling runtime integration")
class DoclingSmoke(unittest.TestCase):
    def test_real_pdf_pages_and_structure(self):
        import fitz
        pdf = fitz.open()
        pdf.new_page().insert_text((72, 72), "SECTION ONE. First physical page.")
        pdf.new_page().insert_text((72, 72), "SECTION TWO. Second physical page.")
        body = pdf.tobytes()
        pdf.close()
        result = CascoDocumentParser().parse(body)
        self.assertEqual(result.parser, "docling", result.warning)
        self.assertTrue(result.promotable)
        self.assertEqual(set(result.pages), {1, 2})
        self.assertIn("First physical page", result.pages[1])
        self.assertIn("Second physical page", result.pages[2])
        self.assertNotIn("Second physical page", result.pages[1])
        self.assertTrue(result.structure)


if __name__ == "__main__":
    unittest.main()
