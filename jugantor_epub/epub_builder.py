import html
import os
import re
import uuid

from ebooklib import epub

from . import config

FONT_ITEM_FILENAME = "fonts/NotoSansBengali-Regular.ttf"
# style/main.css references the font relative to its own folder (style/).
FONT_URL_FROM_STYLESHEET = "../fonts/NotoSansBengali-Regular.ttf"

STYLESHEET = """
@font-face {
    font-family: "Noto Sans Bengali";
    font-weight: normal;
    font-style: normal;
    src: url(%s);
}
body {
    font-family: "Noto Sans Bengali", sans-serif;
}
h1.section-title {
    text-align: center;
}
h2.article-headline {
    margin-bottom: 0.2em;
}
p.article-byline {
    font-size: 0.85em;
    color: #555;
    margin-top: 0;
}
img.article-image {
    max-width: 100%%;
    height: auto;
    display: block;
    margin: 0.5em auto;
}
""" % FONT_URL_FROM_STYLESHEET


def _slugify(source_name):
    """Turn a (possibly non-ASCII) source display name into a filesystem-safe
    filename fragment: collapse whitespace and characters that are unsafe in
    filenames into single dashes, otherwise leave the text (including
    non-Latin scripts like Bengali) untouched -- modern filesystems handle
    Unicode filenames fine, and this keeps names for distinct sources distinct
    without needing a transliteration table.
    """
    slug = re.sub(r'[\s/\\:*?"<>|]+', "-", source_name.strip()).strip("-")
    return slug or "edition"


def _article_html(article):
    parts = [f"<h2 class='article-headline'>{html.escape(article['headline'])}</h2>"]

    byline_bits = [b for b in (article.get("author"), article.get("display_time")) if b]
    if byline_bits:
        parts.append(f"<p class='article-byline'>{html.escape(' — '.join(byline_bits))}</p>")

    if article.get("image_filename"):
        parts.append(f"<img class='article-image' src='images/{article['image_filename']}' />")

    for paragraph in article.get("paragraphs") or [article.get("summary", "")]:
        if paragraph:
            parts.append(f"<p>{html.escape(paragraph)}</p>")

    return "\n".join(parts)


def build_epub(
    source_name,
    edition_date,
    sections_with_articles,
    output_path=None,
    source_slug=None,
    cover_image_bytes=None,
):
    """Assemble the day's scraped sections/articles into an epub file.

    sections_with_articles: list of (section_name, [article_dict, ...])
    article_dict keys: headline, author, display_time, image_filename,
                        image_bytes, paragraphs, summary
    source_slug: filesystem-safe identifier used for the default output
                 filename (e.g. the config.SOURCES entry, "jugantor"). When
                 omitted, falls back to a slugified source_name. Callers that
                 build multiple sources per run should pass distinct slugs so
                 their default output paths don't collide.
    cover_image_bytes: pre-rendered JPEG bytes (see jugantor_epub.cover) used
                        as both the epub's library-thumbnail cover and the
                        title page's image. When omitted, the title page
                        falls back to a plain text heading and no cover
                        metadata is set.
    """
    book = epub.EpubBook()
    book.set_identifier(str(uuid.uuid4()))
    book.set_title(f"{source_name} — {edition_date}")
    book.set_language("bn")
    book.add_author(source_name)
    book.add_metadata("DC", "publisher", "MHB")
    book.add_metadata("DC", "description", "Mehedi's personal news digest")

    style_item = epub.EpubItem(
        uid="style_main",
        file_name="style/main.css",
        media_type="text/css",
        content=STYLESHEET,
    )
    book.add_item(style_item)

    with open(config.FONT_PATH, "rb") as font_file:
        font_item = epub.EpubItem(
            uid="font_bengali",
            file_name=FONT_ITEM_FILENAME,
            media_type="font/ttf",
            content=font_file.read(),
        )
    book.add_item(font_item)

    if cover_image_bytes:
        book.set_cover("cover.jpg", cover_image_bytes, create_page=False)
        title_page_content = "<img src='cover.jpg' alt='cover' style='width:100%' />"
    else:
        title_page_content = (
            f"<h1 class='section-title'>{html.escape(source_name)}</h1>"
            f"<p style='text-align:center'>{html.escape(edition_date)}</p>"
        )

    title_page = epub.EpubHtml(
        title="প্রচ্ছদ",
        file_name="title.xhtml",
        content=title_page_content,
    )
    title_page.add_item(style_item)
    book.add_item(title_page)

    spine = ["nav", title_page]
    toc = []
    seen_image_filenames = set()

    for section_name, articles in sections_with_articles:
        section_chapters = []
        for index, article in enumerate(articles, start=1):
            filename = f"{article['section_slug']}_{index}.xhtml"

            if article.get("image_filename") and article["image_filename"] not in seen_image_filenames:
                image_item = epub.EpubImage(
                    uid=f"img_{article['image_filename']}",
                    file_name=f"images/{article['image_filename']}",
                    media_type="image/jpeg",
                    content=article["image_bytes"],
                )
                book.add_item(image_item)
                seen_image_filenames.add(article["image_filename"])

            chapter = epub.EpubHtml(
                title=article["headline"] or section_name,
                file_name=filename,
                content=_article_html(article),
            )
            chapter.add_item(style_item)
            book.add_item(chapter)
            spine.append(chapter)
            section_chapters.append(chapter)

        if section_chapters:
            toc.append((epub.Section(section_name), section_chapters))

    book.toc = toc
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = spine

    if output_path is None:
        os.makedirs(config.OUTPUT_DIR, exist_ok=True)
        slug = source_slug or _slugify(source_name)
        output_path = os.path.join(config.OUTPUT_DIR, f"{slug}-{edition_date}.epub")

    epub.write_epub(output_path, book)
    return output_path
