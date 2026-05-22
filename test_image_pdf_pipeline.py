from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image
from PyPDF2 import PdfReader

from harvester.fetcher import _download_images_as_single_pdf


class ImagePdfPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_download_images_as_single_pdf_writes_two_page_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            img1 = root / "page1.jpg"
            img2 = root / "page2.jpg"
            Image.new("RGB", (900, 1200), color=(255, 0, 0)).save(img1, format="JPEG")
            Image.new("RGB", (900, 1200), color=(0, 0, 255)).save(img2, format="JPEG")
            dest = root / "bulletin.pdf"

            ok = await _download_images_as_single_pdf(
                [img1.as_uri(), img2.as_uri()],
                str(dest),
            )

            self.assertTrue(ok)
            self.assertTrue(dest.exists())
            self.assertEqual(len(PdfReader(str(dest)).pages), 2)


if __name__ == "__main__":
    unittest.main()
