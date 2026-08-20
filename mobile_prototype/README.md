# News Reels Prototype

A throwaway Flutter UI prototype exploring a reels-style (TikTok/Instagram/YouTube-like)
interaction for browsing news: full-screen cards, vertical scroll for the next story,
horizontal swipe (or tab tap) to change category. All article data is mocked — no
RSS feed or scraping backend is wired up yet. See
`../docs/superpowers/specs/2026-08-20-flutter-news-reels-prototype-design.md` for the
full design.

## Running

```bash
flutter pub get
flutter run -d emulator-5554   # or: flutter run -d <ios-simulator-id>
```

## Testing

```bash
flutter test
```

Automated tests cover the model, mock data invariants, the NewsCard image-fallback
path, and CategoryFeed's vertical paging. The end-to-end swipe/tab/scroll-memory/WebView
flow is verified manually — see Task 7 of the implementation plan.
