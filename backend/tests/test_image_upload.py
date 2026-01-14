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

    def _make_tiff(self, w: int, h: int) -> bytes:
        img = Image.new("RGB", (w, h), color=(120, 130, 140))
        buf = io.BytesIO()
        img.save(buf, format="TIFF")
        return buf.getvalue()

    def _make_gif(self, w: int, h: int) -> bytes:
        img = Image.new("RGB", (w, h), color=(120, 130, 140))
        buf = io.BytesIO()
        img.save(buf, format="GIF")
        return buf.getvalue()

    def test_accepts_png_and_converts_to_png(self):
        raw = self._make_png(600, 400)
        out, w, h, mime = validate_and_convert_image_upload(
            raw,
            filename="x.png",
            content_type="image/png",
        )
        self.assertEqual((w, h), (600, 400))
        self.assertEqual(mime, "image/png")
        self.assertTrue(out.startswith(b"\x89PNG"))

    def test_accepts_jpeg_and_converts_to_png(self):
        raw = self._make_jpeg(800, 600)
        out, w, h, mime = validate_and_convert_image_upload(
            raw,
            filename="x.jpg",
            content_type="image/jpeg",
        )
        self.assertEqual((w, h), (800, 600))
        self.assertEqual(mime, "image/png")
        self.assertTrue(out.startswith(b"\x89PNG"))

    def test_rejects_small_resolution(self):
        raw = self._make_png(200, 200)
        with self.assertRaises(ValueError):
            validate_and_convert_image_upload(raw, filename="x.png", content_type="image/png")

    def test_rejects_wrong_mime(self):
        raw = self._make_png(600, 400)
        with self.assertRaises(ValueError):
            validate_and_convert_image_upload(raw, filename="x.png", content_type="application/octet-stream")

    def test_rejects_wrong_extension(self):
        raw = self._make_png(600, 400)
        with self.assertRaises(ValueError):
            validate_and_convert_image_upload(raw, filename="x.gif", content_type="image/png")

    def test_accepts_tiff_and_converts_to_png(self):
        raw = self._make_tiff(600, 400)
        out, w, h, mime = validate_and_convert_image_upload(
            raw,
            filename="x.tif",
            content_type="image/tiff",
        )
        self.assertEqual((w, h), (600, 400))
        self.assertEqual(mime, "image/png")
        self.assertTrue(out.startswith(b"\x89PNG"))

    def test_accepts_gif_and_converts_to_png(self):
        raw = self._make_gif(600, 400)
        out, w, h, mime = validate_and_convert_image_upload(
            raw,
            filename="x.gif",
            content_type="image/gif",
        )
        self.assertEqual((w, h), (600, 400))
        self.assertEqual(mime, "image/png")
        self.assertTrue(out.startswith(b"\x89PNG"))


if __name__ == "__main__":
    unittest.main()
