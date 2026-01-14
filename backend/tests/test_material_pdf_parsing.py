import unittest
from pathlib import Path

from backend.services.extraction import parse_materials_from_pdf_bytes


class MaterialPdfParsingTests(unittest.TestCase):
    def test_parse_materials_from_pdf_bytes_material_terpasang(self):
        pdf_path = Path(__file__).resolve().parents[2] / "Daftar Material Terpasang.pdf"
        if not pdf_path.exists():
            self.skipTest("Daftar Material Terpasang.pdf tidak ditemukan")

        rows, warnings = parse_materials_from_pdf_bytes(pdf_path.read_bytes(), max_rows=5000)
        self.assertEqual(warnings, [])
        self.assertEqual(len(rows), 22)

        first = rows[0]
        self.assertEqual(first["description"], "PIPE")
        self.assertEqual(first["size"], "4 Inch")
        self.assertEqual(first["quantity"], 16.0)
        self.assertEqual(first["unit"], "m")
        self.assertIn("API 5L", first["spec"])


if __name__ == "__main__":
    unittest.main()

