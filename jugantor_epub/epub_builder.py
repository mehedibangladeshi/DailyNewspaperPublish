import html
import os
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


def build_epub(source_name, edition_date, sections_with_articles, output_path=None):
    """Assemble the day's scraped sections/articles into an epub file.

    sections_with_articles: list of (section_name, [article_dict, ...])
    article_dict keys: headline, author, display_time, image_filename,
                        image_bytes, paragraphs, summary
    """
    book = epub.EpubBook()
    book.set_identifier(str(uuid.uuid4()))
    book.set_title(f"{source_name} — {edition_date}")
    book.set_language("bn")
    book.add_author(source_name)

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

    title_page = epub.EpubHtml(
        title="প্রচ্ছদ",
        file_name="title.xhtml",
        content=(
            f"<h1 class='section-title'>{html.escape(source_name)}</h1>"
            f"<p style='text-align:center'>{html.escape(edition_date)}</p>"
        ),
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
        output_path = os.path.join(config.OUTPUT_DIR, f"jugantor-{edition_date}.epub")

    epub.write_epub(output_path, book)
    return output_path
