# Prototype Real Data — Design

## Overview & Scope

Replace the Flutter prototype's hand-written mock article list with real scraped news: real headlines, real images (or a sensible fallback), and real article URLs, pulled from this repo's existing 5 source scrapers (Jugantor, Prothom Alo, Dhaka Tribune, Daily Star, Ittefaq). Staleness is explicitly acceptable — this is a one-time (or manually re-run) data snapshot, not a live feed. The app also gains a visible "today's date" at the top, independent of when the data snapshot was generated.

This does not add a backend, live network fetching of articles, or any persistence beyond the existing image/WebView network calls the prototype already makes.

## Data Generation (Python)

A new script, `scripts/generate_prototype_data.py`, reuses the existing source-module contract (`discover_sections()` → `list_articles(slug, edition_date)` → `fetch_article(url)`) the same way `main.py` does, imported dynamically per `config.SOURCES` slug (`jugantor`, `prothomalo`, `dhakatribune`, `dailystar`, `ittefaq`).

**Per-source error isolation:** matching this repo's existing principle, a source that fails entirely (e.g. Dhaka Tribune/Ittefaq's known Cloudflare block — confirmed to affect only GitHub Actions' hosted-runner IPs, not local/residential runs, so this script running locally is expected to succeed for all 5 sources under normal conditions) is skipped with a warning; the script still produces output from whatever sources succeeded.

**Category assignment:**
- **Main**: the first section returned by each source's `discover_sections()` (its front page/top listing) contributes headline-style articles tagged `category: "main"`, independent of keyword classification.
- **Politics / World / Bangladesh / Sports / Finance**: every other scraped article is classified by keyword-matching its headline text and section name against a bilingual (English + Bengali) keyword list per category (e.g. sports: "cricket", "football", "খেলা"; finance: "economy", "stock", "market", "অর্থনীতি", "ব্যবসা"). An article matching no category's keywords is dropped, not forced into one.

**Volume:** caps at roughly 8-12 articles per category (pooled across whichever sources have matches), so each category's vertical feed feels substantial without an excessive scrape run.

**Image fallback:** when a scraped article has no image (`fetch_article()`'s `image_url` is empty), the script fills `imageUrl` with that source's existing `get_cover_logo_url()` (the same masthead logo already used for epub covers) — old or generic is fine per the "even if old, doesn't matter" requirement.

**Output**, written to `mobile_prototype/assets/articles.json`:

```json
{
  "generated_at": "2026-08-20",
  "articles": [
    {
      "id": "jugantor-<hash-or-slug>",
      "category": "politics",
      "source": "Jugantor",
      "headline": "...",
      "snippet": "...",
      "imageUrl": "https://...",
      "articleUrl": "https://..."
    }
  ]
}
```

`snippet` is derived from the article's existing summary/first-paragraph text (`item.get("summary")` or the first entry of `detail.get("paragraphs")`), truncated to a couple of lines. `id` is a stable per-article identifier (e.g. a slug derived from the source name and article URL) so re-running the script doesn't need to preserve object identity — the Flutter side treats the whole list as replaceable data.

Regenerating data is a manual step: re-run the script, then rebuild/hot-restart the Flutter app so the updated asset is picked up.

## Flutter Integration

- `mobile_prototype/assets/articles.json` is declared as a bundled asset in `pubspec.yaml`.
- `lib/data/mock_articles.dart` is replaced by `lib/data/article_repository.dart`, exposing:
  - `List<NewsArticle> parseArticles(String jsonString)` — pure JSON-to-model parsing, unit-testable against a small hand-written fixture string (not the live generated file, keeping tests deterministic/offline).
  - `List<NewsArticle> articlesForCategory(List<NewsArticle> all, String category)` — same filtering behavior as before, now taking the loaded list as a parameter instead of closing over a module-level const.
- `main()` becomes `async`: it awaits `rootBundle.loadString('assets/articles.json')` and `parseArticles(...)` before calling `runApp()`, so the widget tree builds with real data already in memory — no loading spinner/`FutureBuilder` needed in the UI for this prototype.
- `HomeScreen` takes the loaded `List<NewsArticle>` as a constructor parameter (passed down from `main()`) instead of importing a global mock list, and each `CategoryFeed` is built from `articlesForCategory(articles, category)`.
- Existing data-invariant tests (category coverage, "main is a distinct pool," broken-image marker present, non-mutation) are rewritten against `parseArticles()` + a fixture JSON string, since those invariants no longer hold universally over live-scraped content — the fixture keeps them meaningful and deterministic.

## Today's Date Display

The `AppBar`'s `title:` slot (currently empty, since the `TabBar` already moved to `bottom:` in the earlier full-bleed fix) shows today's actual device date, formatted like "Thu, Aug 20" via `DateTime.now()` — always "today" regardless of when the JSON snapshot was generated.

## Error Handling & Edge Cases

- A category with zero matched real articles (e.g. a slow news day for Finance) still shows the existing "No stories yet" placeholder — no change needed to `CategoryFeed`.
- `parseArticles()` skips (rather than crashes on) a malformed entry in the JSON — a prototype data-generation bug shouldn't take down the whole app.
- If `assets/articles.json` is missing or fails to load, `main()` falls back to an empty article list rather than crashing, and every category shows "No stories yet."

## Out of Scope

- Live/on-device fetching of articles (no backend call from the phone).
- Automatic/scheduled regeneration of the data snapshot.
- Manual per-source section-to-category mapping tables (keyword classification is heuristic and can misclassify; acceptable for a prototype).
