import io
import unittest

from PIL import Image

from backend.services.extraction import validate_and_convert_image_upload


class ImageUploadTests(unittest.TestCase):
    def _make_png(self, w: int, h: int) -> bytes:
        img = Image.new("RGB", (w, h), color=(120, 130, 140))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def _make_jpeg(self, w: int, h: int) -> bytes:
        img = Image.new("RGB", (w, h), color=(120, 130, 140))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return buf.getvalue()

    def _make_webp(self, w: int, h: int) -> bytes | None:
        img = Image.new("RGB", (w, h), color=(120, 130, 140))
        buf = io.BytesIO()
        try:
            img.save(buf, format="WEBP", quality=85)
        except Exception:
            return None
        return buf.getvalue()

    def test_accepts_png_and_converts_to_png(self):
        raw = self._make_png(600, 400)
        out, w, h, mime, ext = validate_and_convert_image_upload(
            raw,
            filename="x.png",
            content_type="image/png",
        )
        self.assertEqual((w, h), (600, 400))
        self.assertEqual(mime, "image/png")
        self.assertEqual(ext, ".png")
        self.assertTrue(out.startswith(b"\x89PNG"))

    def test_accepts_jpeg_and_converts_to_jpeg(self):
        raw = self._make_jpeg(800, 600)
        out, w, h, mime, ext = validate_and_convert_image_upload(
            raw,
            filename="x.jpg",
            content_type="image/jpeg",
        )
        self.assertEqual((w, h), (800, 600))
        self.assertEqual(mime, "image/jpeg")
        self.assertEqual(ext, ".jpg")
        self.assertTrue(out.startswith(b"\xff\xd8"))

    def test_accepts_small_resolution(self):
        raw = self._make_png(200, 200)
        out, w, h, mime, ext = validate_and_convert_image_upload(raw, filename="x.png", content_type="image/png")
        self.assertEqual((w, h), (200, 200))
        self.assertEqual(mime, "image/png")
        self.assertEqual(ext, ".png")
        self.assertTrue(out.startswith(b"\x89PNG"))

    def test_resizes_large_image_over_2000px(self):
        raw = self._make_png(3000, 1000)
        out, w, h, mime, ext = validate_and_convert_image_upload(raw, filename="x.png", content_type="image/png")
        self.assertEqual((w, h), (2000, 667))
        self.assertEqual(mime, "image/png")
        self.assertEqual(ext, ".png")
        self.assertTrue(out.startswith(b"\x89PNG"))

    def test_rejects_wrong_mime(self):
        raw = self._make_png(600, 400)
        with self.assertRaises(ValueError):
            validate_and_convert_image_upload(raw, filename="x.png", content_type="application/octet-stream")

    def test_rejects_wrong_extension(self):
        raw = self._make_png(600, 400)
        with self.assertRaises(ValueError):
            validate_and_convert_image_upload(raw, filename="x.gif", content_type="image/png")

    def test_accepts_webp_when_supported(self):
        raw = self._make_webp(800, 600)
        if raw is None:
            self.skipTest("WEBP tidak didukung oleh Pillow pada environment ini")
        out, w, h, mime, ext = validate_and_convert_image_upload(raw, filename="x.webp", content_type="image/webp")
        self.assertEqual((w, h), (800, 600))
        self.assertEqual(mime, "image/jpeg")
        self.assertEqual(ext, ".jpg")
        self.assertTrue(out.startswith(b"\xff\xd8"))


if __name__ == "__main__":
    unittest.main()
