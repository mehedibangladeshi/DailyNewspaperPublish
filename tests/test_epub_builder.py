import shutil
import zipfile

import pytest

from jugantor_epub import epub_builder


def _sample_sections():
    return [
        (
            "প্রথম পাতা",
            [
                {
                    "section_slug": "tp-firstpage",
                    "headline": "নমুনা শিরোনাম",
                    "author": "রিপোর্টার",
                    "display_time": "১০ আগস্ট ২০২৬",
                    "paragraphs": ["প্রথম অনুচ্ছেদ।", "দ্বিতীয় অনুচ্ছেদ।"],
                    "summary": "",
                    "image_filename": None,
                    "image_bytes": None,
                }
            ],
        ),
        (
            "খেলা",
            [
                {
                    "section_slug": "tp-sports",
                    "headline": "খেলার খবর",
                    "author": "",
                    "display_time": "",
                    "paragraphs": [],
                    "summary": "সংক্ষিপ্ত বিবরণ",
                    "image_filename": None,
                    "image_bytes": None,
                }
            ],
        ),
    ]


def test_build_epub_produces_valid_zip_with_expected_content(tmp_path):
    output_path = tmp_path / "test-edition.epub"

    result_path = epub_builder.build_epub(
        "টেস্ট পত্রিকা", "2026-08-10", _sample_sections(), output_path=str(output_path)
    )

    assert result_path == str(output_path)
    assert output_path.exists()

    with zipfile.ZipFile(output_path) as zf:
        assert zf.testzip() is None
        names = zf.namelist()
        assert names[0] == "mimetype"
        assert zf.read("mimetype") == b"application/epub+zip"
        assert "EPUB/fonts/NotoSansBengali-Regular.ttf" in names

        article_files = [n for n in names if n.startswith("EPUB/tp-firstpage")]
        assert len(article_files) == 1
        content = zf.read(article_files[0]).decode("utf-8")
        assert "নমুনা শিরোনাম" in content
        assert "প্রথম অনুচ্ছেদ।" in content

        # article with no paragraphs should fall back to its summary
        sports_files = [n for n in names if n.startswith("EPUB/tp-sports")]
        sports_content = zf.read(sports_files[0]).decode("utf-8")
        assert "সংক্ষিপ্ত বিবরণ" in sports_content


def test_build_epub_embeds_image_when_present(tmp_path):
    output_path = tmp_path / "with-image.epub"
    sections = _sample_sections()
    sections[0][1][0]["image_filename"] = "abc123.jpg"
    sections[0][1][0]["image_bytes"] = b"\xff\xd8\xff\xfake-jpeg-bytes"

    epub_builder.build_epub(
        "টেস্ট পত্রিকা", "2026-08-10", sections, output_path=str(output_path)
    )

    with zipfile.ZipFile(output_path) as zf:
        assert "EPUB/images/abc123.jpg" in zf.namelist()
        article_files = [n for n in zf.namelist() if n.startswith("EPUB/tp-firstpage")]
        content = zf.read(article_files[0]).decode("utf-8")
        assert "images/abc123.jpg" in content


def test_build_epub_skips_empty_sections(tmp_path):
    output_path = tmp_path / "empty-section.epub"
    sections = _sample_sections() + [("খালি বিভাগ", [])]

    epub_builder.build_epub(
        "টেস্ট পত্রিকা", "2026-08-10", sections, output_path=str(output_path)
    )

    with zipfile.ZipFile(output_path) as zf:
        nav = zf.read("EPUB/nav.xhtml").decode("utf-8")
        assert "খালি বিভাগ" not in nav


def test_build_epub_defaults_output_path_to_config_output_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(epub_builder.config, "OUTPUT_DIR", str(tmp_path))

    result_path = epub_builder.build_epub("টেস্ট পত্রিকা", "2026-08-10", _sample_sections())

    assert result_path == str(tmp_path / "jugantor-2026-08-10.epub")
    assert (tmp_path / "jugantor-2026-08-10.epub").exists()


@pytest.mark.skipif(
    shutil.which("java") is None, reason="epubcheck requires a Java runtime"
)
def test_build_epub_passes_epubcheck(tmp_path):
    epubcheck = pytest.importorskip("epubcheck")
    output_path = tmp_path / "validated.epub"

    epub_builder.build_epub(
        "টেস্ট পত্রিকা", "2026-08-10", _sample_sections(), output_path=str(output_path)
    )

    result = epubcheck.EpubCheck(str(output_path))
    assert result.valid, result.messages
