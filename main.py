import argparse
import importlib
import logging
import os
import sys
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from jugantor_epub import config, cover, email_sender, epub_builder, images, opds_publish, send_tracker

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DHAKA_TZ = ZoneInfo("Asia/Dhaka")


@contextmanager
def _null_context():
    yield None


def build_source_edition(source_module, edition_date, source_slug=None):
    sections_with_articles = []
    total_articles = 0
    skipped = 0
    raw_bytes_cache = {}

    def cached_fetch_image_bytes(image_url):
        if image_url not in raw_bytes_cache:
            raw_bytes_cache[image_url] = images.fetch_image_bytes(image_url)
        return raw_bytes_cache[image_url]

    for slug, section_name in source_module.discover_sections():
        try:
            listing = source_module.list_articles(slug, edition_date)
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
            raw_bytes = cached_fetch_image_bytes(image_url) if image_url else None

            articles.append(
                {
                    "section_slug": slug,
                    "headline": detail.get("headline") or item.get("headline", ""),
                    "author": detail.get("author", ""),
                    "display_time": item.get("listing_time") or detail.get("date_published", ""),
                    "paragraphs": detail.get("paragraphs") or [],
                    "summary": item.get("summary", ""),
                    "image_url": image_url,
                    "_raw_bytes": raw_bytes,
                }
            )

        if articles:
            sections_with_articles.append((section_name, articles))
            total_articles += len(articles)
        logger.info("Section %s: %d article(s)", section_name, len(articles))

    if total_articles == 0:
        raise RuntimeError(f"No articles were scraped for source {source_module.SOURCE_NAME!r}")

    all_articles = [article for _, articles in sections_with_articles for article in articles]
    _encode_article_images(all_articles, config.IMAGE_MAX_WIDTH, config.IMAGE_JPEG_QUALITY)

    try:
        cover_image_bytes = cover.render_cover(
            source_module.SOURCE_NAME,
            source_module.format_date(edition_date),
            source_module.get_cover_logo_url(),
            source_module.COVER_ACCENT_COLOR,
            prepare_logo=getattr(source_module, "prepare_logo_image", None),
        )
    except Exception as exc:
        logger.warning("Could not render cover for %s: %s", source_module.SOURCE_NAME, exc)
        cover_image_bytes = None

    output_path = epub_builder.build_epub(
        source_module.SOURCE_NAME,
        edition_date,
        sections_with_articles,
        source_slug=source_slug,
        cover_image_bytes=cover_image_bytes,
    )

    output_path = _rebuild_if_oversized(
        source_module,
        edition_date,
        sections_with_articles,
        source_slug,
        cover_image_bytes,
        output_path,
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


def _encode_article_images(articles, max_width, quality):
    for article in articles:
        raw_bytes = article["_raw_bytes"]
        image = images.decode_image(raw_bytes) if raw_bytes is not None else None
        if image is not None:
            filename, data = images.encode_image(image, article["image_url"], max_width, quality)
            article["image_filename"] = filename
            article["image_bytes"] = data
        else:
            article["image_filename"] = None
            article["image_bytes"] = None


def _rebuild_if_oversized(
    source_module, edition_date, sections_with_articles, source_slug, cover_image_bytes, output_path
):
    try:
        size = os.path.getsize(output_path)
    except OSError as exc:
        logger.debug("Could not stat %s to check size: %s", output_path, exc)
        return output_path

    if size <= email_sender.GMAIL_MAX_ATTACHMENT_BYTES:
        return output_path

    all_articles = [article for _, articles in sections_with_articles for article in articles]

    logger.info(
        "%s built oversized (%d bytes over %d); re-encoding images at fallback settings and rebuilding",
        source_module.SOURCE_NAME,
        size,
        email_sender.GMAIL_MAX_ATTACHMENT_BYTES,
    )
    try:
        _encode_article_images(all_articles, config.IMAGE_MAX_WIDTH_FALLBACK, config.IMAGE_JPEG_QUALITY_FALLBACK)
        output_path = epub_builder.build_epub(
            source_module.SOURCE_NAME,
            edition_date,
            sections_with_articles,
            source_slug=source_slug,
            cover_image_bytes=cover_image_bytes,
        )
    except Exception as exc:
        logger.warning(
            "Could not rebuild %s with fallback image settings, keeping oversized build: %s",
            source_module.SOURCE_NAME,
            exc,
        )

    return output_path


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Build (and optionally send) newspaper editions.")
    parser.add_argument(
        "--source",
        action="append",
        choices=config.SOURCES,
        dest="sources",
        help="Build only this source; repeat to select several. Defaults to all of config.SOURCES.",
    )
    return parser.parse_args(argv)


def main(sources=None):
    sources = sources or config.SOURCES

    edition_date = datetime.now(DHAKA_TZ).date().isoformat()

    built_count = 0
    sent_count = 0
    size_skipped_count = 0
    build_failures = 0
    send_failures = 0

    sender = email_sender.KindleSender() if config.SEND_TO_KINDLE else None

    with sender if sender is not None else _null_context():
        for source_slug in sources:
            source_module = importlib.import_module(f"jugantor_epub.sources.{source_slug}")
            try:
                output_path = build_source_edition(source_module, edition_date, source_slug)
            except Exception as exc:
                logger.error("Skipping source %s: %s", source_slug, exc)
                build_failures += 1
                continue
            built_count += 1

            if sender is not None:
                try:
                    sent = sender.send(source_module.SOURCE_NAME, output_path, edition_date)
                except Exception as exc:
                    logger.error("Failed to send Kindle email for %s: %s", source_module.SOURCE_NAME, exc)
                    send_failures += 1
                    continue
                if sent:
                    sent_count += 1
                    send_tracker.mark_sent(config.GH_PAGES_DIR, source_slug, edition_date)
                else:
                    size_skipped_count += 1

    if built_count == 0:
        logger.error("No source produced an edition; nothing to send.")
        return 1

    logger.info(
        "Run summary: %d built, %d sent, %d size-skipped, %d build failure(s), %d send failure(s)",
        built_count,
        sent_count,
        size_skipped_count,
        build_failures,
        send_failures,
    )

    exit_code = 1 if send_failures else 0

    if config.PUBLISH_OPDS:
        try:
            opds_publish.publish_catalog(config.GH_PAGES_DIR, config.OUTPUT_DIR, edition_date)
        except Exception as exc:
            logger.error("Failed to publish OPDS catalog: %s", exc)
            exit_code = 1
        else:
            logger.info("Published OPDS catalog to %s", config.GH_PAGES_DIR)

    return exit_code


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    sys.exit(main(args.sources))
