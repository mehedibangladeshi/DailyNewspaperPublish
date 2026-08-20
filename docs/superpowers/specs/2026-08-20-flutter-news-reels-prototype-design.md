# Flutter News Reels Prototype — Design

## Overview & Scope

A throwaway Flutter prototype (Android + iOS) that presents news the way TikTok/Instagram/YouTube present video: full-screen, one-at-a-time cards you scroll through vertically, with horizontal swipe to change category (topic feed). This phase uses **mock article data only** — no RSS or scraping integration. The goal is to validate whether "vertical scroll = next story, horizontal swipe = change category" feels good and legible as a news-browsing interaction, before committing to a real backend.

This is a separate deliverable from the existing Python epub pipeline in this repo (different language/toolchain, different purpose — real-time browsing vs. scheduled Kindle delivery). It lives in its own project directory and does not touch `jugantor_epub/`, `main.py`, or the existing test suite.

## Categories

Fixed set, in this order: **Main, Politics, World, Bangladesh, Sports, Finance**. App launches into "Main". Category set is hardcoded for this prototype (not user-configurable).

## Architecture

- `TabController` + `TabBar` pinned at the top of the screen, always visible, showing the 6 category labels with the active one highlighted. Tapping a tab jumps directly to that category.
- A `TabBarView` fills the body beneath the tab bar. Swiping left/right anywhere in the body moves between adjacent category tabs — this is `TabBarView`'s native gesture, no custom drag-detection code needed.
- Each tab's content is a `CategoryFeed` widget wrapping a vertical `PageView.builder` of `NewsCard` widgets. One card fills the entire screen (below the tab bar); vertical drag/scroll snaps to the next/previous card in that category.
- `CategoryFeed` mixes in `AutomaticKeepAliveClientMixin` so each category's `PageController` retains its scroll position when the user swipes to another category and back — returning to "Politics" shows the same card you left, not a reset to the top.
- Tapping a card (or its "Read more" affordance) pushes `ArticleWebViewScreen`, which loads the article's URL via `webview_flutter`. The system/in-app back gesture returns to the exact feed position the user was on.

## Data Model

Mock data only, defined as a static Dart list (no network calls, no JSON parsing from a server):

```dart
class NewsArticle {
  final String id;
  final String category;   // one of: main, politics, world, bangladesh, sports, finance
  final String source;     // Jugantor | Prothom Alo | Dhaka Tribune | Ittefaq
  final String headline;
  final String snippet;    // 1-2 line summary
  final String imageUrl;
  final String articleUrl; // loaded in the WebView
}
```

The mock set covers all 6 categories, flavored with this repo's real newspaper sources (Jugantor, Prothom Alo, Dhaka Tribune, Ittefaq) so the prototype previews what real multi-source aggregation will look like. `articleUrl` values are real public article URLs (so the WebView has something real to render); `imageUrl` values may be placeholder/hotlinked images and are allowed to fail to load (see Error Handling).

"Main" category is a distinct pool of headline-style articles pulled across all sources — not a mechanical union of the other 5 categories' articles.

## Card Design

- Full-bleed background image via `Image.network`, filling the screen behind the tab bar.
- Dark gradient scrim over the bottom third of the card for text legibility.
- Bottom-anchored content, in order: source badge (small rounded pill with source name), headline (large, bold), snippet (1-2 lines), a subtle "Read more →" affordance.
- Top: the persistent `TabBar`, rendered over a translucent-to-solid app-bar background so category labels stay legible regardless of the card image behind them.

## Project Structure

New standalone Flutter project at `mobile_prototype/` in the repo root, sibling to the existing Python package — kept separate since it's a different language/toolchain and a genuinely independent deliverable. Standard Flutter app structure (`lib/main.dart`, `lib/models/`, `lib/screens/`, `lib/widgets/`, `lib/data/mock_articles.dart`).

## Error Handling & Edge Cases

- **Image load failure** (broken/mock URL): fall back to a plain gray placeholder container with a small icon — never a broken-image glitch or crash.
- **WebView load failure** (offline, bad link): show a simple in-webview error message with retry/back options; does not crash the app.
- **Empty category**: if a category's mock list is empty, show a centered "No stories yet" placeholder instead of a blank screen.

## Testing / Verification

This is a UI prototype, not a production feature — no automated test suite is the expected deliverable. Verification is a manual walkthrough on an Android emulator and/or iOS simulator covering:

1. Vertical scroll through all cards within a category.
2. Horizontal swipe between all 6 categories, in both directions.
3. Direct tab-tap navigation to a non-adjacent category.
4. Scroll-position retention: scroll partway into "Politics", swipe to "World", swipe back — confirm "Politics" resumes where left off.
5. Tap into the WebView article reader and back — confirm return to the same card.
6. A card with a deliberately broken `imageUrl` renders the placeholder instead of failing.

## Out of Scope (this phase)

- Real RSS feed or scraping integration
- Backend/API server
- Persistence or caching across app restarts
- Authentication / user accounts
- Offline support
- Analytics / telemetry
