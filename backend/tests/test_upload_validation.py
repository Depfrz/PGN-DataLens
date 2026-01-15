import io
import unittest

from PIL import Image

from backend.services.extraction import convert_image_bytes_to_pdf, detect_upload_kind


class UploadValidationTests(unittest.TestCase):
    def _pdf_bytes(self) -> bytes:
        return b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"

    def _png_bytes(self, w: int = 400, h: int = 400) -> bytes:
        img = Image.new("RGB", (w, h), color=(100, 110, 120))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def _gif_bytes(self, w: int = 400, h: int = 400) -> bytes:
        img = Image.new("RGB", (w, h), color=(100, 110, 120))
        buf = io.BytesIO()
        img.save(buf, format="GIF")
        return buf.getvalue()

    def _webp_bytes(self, w: int = 400, h: int = 400) -> bytes | None:
        img = Image.new("RGB", (w, h), color=(100, 110, 120))
        buf = io.BytesIO()
        try:
            img.save(buf, format="WEBP", quality=85)
        except Exception:
            return None
        return buf.getvalue()

    def test_pdf_ok(self):
        k = detect_upload_kind(self._pdf_bytes(), filename="a.pdf", content_type="application/pdf")
        self.assertEqual(k, "pdf")

    def test_non_pdf_extension_but_pdf_content_rejected(self):
        with self.assertRaises(ValueError):
            detect_upload_kind(self._pdf_bytes(), filename="a.txt", content_type="application/pdf")

    def test_fake_pdf_extension_rejected(self):
        with self.assertRaises(ValueError):
            detect_upload_kind(b"not a pdf", filename="a.pdf", content_type="application/pdf")

    def test_pdf_content_with_no_pdf_mime_rejected(self):
        with self.assertRaises(ValueError):
            detect_upload_kind(self._pdf_bytes(), filename="a.txt", content_type="text/plain")

    def test_no_extension_pdf_detected(self):
        k = detect_upload_kind(self._pdf_bytes(), filename="upload", content_type="application/pdf")
        self.assertEqual(k, "pdf")

    def test_image_ok(self):
        k = detect_upload_kind(self._png_bytes(), filename="a.png", content_type="image/png")
        self.assertEqual(k, "image")

    def test_no_extension_image_detected(self):
        k = detect_upload_kind(self._png_bytes(), filename="upload", content_type="image/png")
        self.assertEqual(k, "image")

    def test_webp_detected_as_image_when_supported(self):
        raw = self._webp_bytes()
        if raw is None:
            self.skipTest("WEBP tidak didukung oleh Pillow pada environment ini")
        k = detect_upload_kind(raw, filename="a.webp", content_type="image/webp")
        self.assertEqual(k, "image")

    def test_gif_rejected(self):
        with self.assertRaises(ValueError):
            detect_upload_kind(self._gif_bytes(), filename="a.gif", content_type="image/gif")

    def test_convert_image_to_pdf_returns_pdf_signature(self):
        pdf = convert_image_bytes_to_pdf(self._png_bytes())
        self.assertTrue(pdf.lstrip().startswith(b"%PDF-"))


if __name__ == "__main__":
    unittest.main()
