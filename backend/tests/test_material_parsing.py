import unittest

from backend.services.extraction import parse_materials


class MaterialParsingTests(unittest.TestCase):
    def test_parse_materials_merges_name_with_size_only_lines(self):
        text = """
        BALL VALVE
        4\"\n
        2 PCS
        """
        rows = parse_materials(text, max_rows=10)
        self.assertGreaterEqual(len(rows), 1)
        self.assertEqual(rows[0]["description"], "BALL VALVE")
        self.assertEqual(rows[0]["size"], "4 Inch")
        self.assertEqual(rows[0]["quantity"], 2.0)
        self.assertEqual(rows[0]["unit"], "pcs")

    def test_parse_materials_qty_and_unit_can_be_split(self):
        text = """
        GASKET
        4\"\n
        2
        PCS
        """
        rows = parse_materials(text, max_rows=10)
        self.assertEqual(rows[0]["description"], "GASKET")
        self.assertEqual(rows[0]["size"], "4 Inch")
        self.assertEqual(rows[0]["quantity"], 2.0)
        self.assertEqual(rows[0]["unit"], "pcs")

    def test_parse_materials_supports_fraction_inches(self):
        text = "ELBOW 5/8\" 10 PCS"
        rows = parse_materials(text, max_rows=10)
        self.assertEqual(rows[0]["description"], "ELBOW")
        self.assertEqual(rows[0]["size"], "5/8 Inch")
        self.assertEqual(rows[0]["quantity"], 10.0)
        self.assertEqual(rows[0]["unit"], "pcs")

    def test_parse_materials_dedupes_identical_rows(self):
        text = """
        GASKET\n
        4\"\n
        GASKET\n
        4\"\n
        """
        rows = parse_materials(text, max_rows=10)
        self.assertEqual(len(rows), 1)

    def test_parse_materials_splits_name_and_spec_by_comma(self):
        text = "PIPE, API 5L Gr.B, ERW, SCH.40, BE (ASME B36.10M) 4\" 10 PCS"
        rows = parse_materials(text, max_rows=10)
        self.assertEqual(rows[0]["description"], "PIPE")
        self.assertIn("API 5L", rows[0]["spec"])

    def test_parse_materials_keeps_multiword_name_without_spec_markers(self):
        text = "BALL VALVE 4\" 2 PCS"
        rows = parse_materials(text, max_rows=10)
        self.assertEqual(rows[0]["description"], "BALL VALVE")

    def test_parse_materials_accepts_description_only_lines(self):
        text = """
        DESCRIPTION
        PIPE, API 5L Gr.B, ERW, SCH.40, BE (ASME B36.10M)
        GASKET, CL.150, SPWD, METALIC, GRAPHITE FILLER
        """
        rows = parse_materials(text, max_rows=10)
        self.assertEqual(rows[0]["description"], "PIPE")
        self.assertIsNone(rows[0]["size"])
        self.assertIsNone(rows[0]["quantity"])
        self.assertEqual(rows[1]["description"], "GASKET")

    def test_parse_materials_parses_material_terpasang_table_rows(self):
        text = """
        MATERIAL TERPASANG
        ITEM QTY. UNIT SIZE DESCRIPTION
        1 16 M 4\" PIPE, API 5L Gr.B, ERW, SCH.40, BE (ASME B36.10M)
        2 0.2 M 1\" PIPE, API 5L Gr.B, SEAMLESS, SCH.40, BE (ASME B36.10M)
        3 1 EA - PATOK GAS TYPE A
        """
        rows = parse_materials(text, max_rows=20)
        self.assertEqual(rows[0]["description"], "PIPE")
        self.assertEqual(rows[0]["quantity"], 16.0)
        self.assertEqual(rows[0]["unit"], "m")
        self.assertEqual(rows[0]["size"], "4 Inch")
        self.assertIn("API 5L", rows[0]["spec"])
        self.assertEqual(rows[1]["quantity"], 0.2)
        self.assertEqual(rows[2]["description"], "PATOK GAS TYPE A")
        self.assertEqual(rows[2]["unit"], "ea")
        self.assertIsNone(rows[2]["size"])

    def test_parse_materials_parses_spaced_columns_layout(self):
        text = """
        Item                 Size      Qty   Unit
        Pipe                 4\"        16    M
        90 derajat Elbow LR  4\"        4     EA
        Weld O-Let           12\"x4\"    1     EA
        Ball Valve           4\"        1     EA
        Flance               2\"        2     EA
        """
        rows = parse_materials(text, max_rows=20)
        self.assertEqual(rows[0]["description"], "Pipe")
        self.assertEqual(rows[0]["size"], "4 Inch")
        self.assertEqual(rows[0]["quantity"], 16.0)
        self.assertEqual(rows[0]["unit"], "m")
        self.assertEqual(rows[2]["description"], "Weld O-Let")
        self.assertEqual(rows[2]["size"], '12"x4"')


if __name__ == "__main__":
    unittest.main()
