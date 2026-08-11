import importlib
import logging
import sys
from datetime import date

from jugantor_epub import config, email_sender, epub_builder, images

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def build_source_edition(source_module, edition_date, source_slug=None):
    sections_with_articles = []
    total_articles = 0
    skipped = 0
    image_cache = {}

    def cached_download_image(image_url):
        if image_url not in image_cache:
            image_cache[image_url] = images.download_image(image_url)
        return image_cache[image_url]

    for slug, section_name in source_module.discover_sections():
        try:
            listing = source_module.list_articles(slug)
        except Exception as exc:
            logger.warning("Skipping section %s (%s): %s", slug, section_name, exc)
            continue

        articles = []
        for item in listing:
            try:
                detail = source_module.fetch_article(item["url"])
            except Exception as exc:
                logger.warning("Skipping article %s: %s", item.get("url"), exc)
                skipped += 1
                continue

            image_url = detail.get("image_url") or item.get("thumbnail")
            image_result = cached_download_image(image_url) if image_url else None

            articles.append(
                {
                    "section_slug": slug,
                    "headline": detail.get("headline") or item.get("headline", ""),
                    "author": detail.get("author", ""),
                    "display_time": item.get("listing_time") or detail.get("date_published", ""),
                    "paragraphs": detail.get("paragraphs") or [],
                    "summary": item.get("summary", ""),
                    "image_filename": image_result[0] if image_result else None,
                    "image_bytes": image_result[1] if image_result else None,
                }
            )

        if articles:
            sections_with_articles.append((section_name, articles))
            total_articles += len(articles)
        logger.info("Section %s: %d article(s)", section_name, len(articles))

    if total_articles == 0:
        raise RuntimeError(f"No articles were scraped for source {source_module.SOURCE_NAME!r}")

    output_path = epub_builder.build_epub(
        source_module.SOURCE_NAME, edition_date, sections_with_articles, source_slug=source_slug
    )

    logger.info(
        "Built %s: %d section(s), %d article(s), %d skipped -> %s",
        source_module.SOURCE_NAME,
        len(sections_with_articles),
        total_articles,
        skipped,
        output_path,
    )
    return output_path


def main():
    edition_date = date.today().isoformat()
    built = []
    for source_slug in config.SOURCES:
        source_module = importlib.import_module(f"jugantor_epub.sources.{source_slug}")
        try:
            output_path = build_source_edition(source_module, edition_date, source_slug)
        except Exception as exc:
            logger.error("Skipping source %s: %s", source_slug, exc)
            continue
        built.append((source_module.SOURCE_NAME, output_path))

    if not built:
        logger.error("No source produced an edition; nothing to send.")
        return 1

    if config.SEND_TO_KINDLE:
        try:
            email_sender.send_to_kindle(built, edition_date)
        except Exception as exc:
            logger.error("Failed to send combined edition to Kindle: %s", exc)
            return 1
        logger.info("Sent %d edition(s) to Kindle.", len(built))

    return 0


if __name__ == "__main__":
    sys.exit(main())
