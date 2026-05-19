from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ocr.build_bulletin_viewer import generate_viewer_page


class OcrBulletinViewerTests(unittest.TestCase):
    def test_generate_viewer_page_builds_latest_copy_and_sorted_archive(self) -> None:
        sample_ocr = """<!DOCTYPE html>
<html><body><div class="scrollable-viewer">
<h2>Page 1</h2>
<p>Call <a href="tel:+3531234567">0123 4567</a></p>
<p>Email <a href="mailto:test@example.com">test@example.com</a></p>
</div></body></html>
"""
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            ocr_path = tmp_path / 'bulletin-2026-05-19.html'
            ocr_path.write_text(sample_ocr, encoding='utf-8')
            bulletins_dir = tmp_path / 'docs' / 'bulletins'
            output_path = bulletins_dir / 'derry-2026-05-19.html'
            latest_output_path = bulletins_dir / 'derry-latest.html'

            generate_viewer_page('derry', '2026-05-19', ocr_path, output_path, latest_output_path, bulletins_dir)

            generated = output_path.read_text(encoding='utf-8')
            self.assertIn('DERRY DIOCESE BIG BULLETIN', generated)
            self.assertIn('../mega_pdf/derry_mega_bulletin.pdf', generated)
            self.assertIn('PAGE 1', generated)
            self.assertIn('mailto:test@example.com', generated)
            self.assertIn('Parishes With Working Bulletin Links', generated)
            self.assertEqual(generated, latest_output_path.read_text(encoding='utf-8'))

            newer_ocr = tmp_path / 'bulletin-2026-05-26.html'
            newer_ocr.write_text(sample_ocr.replace('Page 1', 'Page 2'), encoding='utf-8')
            generate_viewer_page(
                'down_and_connor',
                '2026-05-26',
                newer_ocr,
                bulletins_dir / 'down_and_connor-2026-05-26.html',
                bulletins_dir / 'down_and_connor-latest.html',
                bulletins_dir,
            )

            archive = (bulletins_dir / 'index.html').read_text(encoding='utf-8')
            self.assertLess(archive.index('2026-05-26'), archive.index('2026-05-19'))
            self.assertIn('down_and_connor-latest.html', archive)
            self.assertIn('derry-latest.html', archive)


if __name__ == '__main__':
    unittest.main()
