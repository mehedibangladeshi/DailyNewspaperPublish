# Flutter News Reels Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a throwaway Flutter prototype that presents mock news articles as full-screen cards — vertical scroll advances to the next story within a category, horizontal swipe (or tab tap) switches category — to validate the reels-style browsing interaction before any real backend work.

**Architecture:** A `TabBarView` (horizontal, 6 fixed categories) whose each tab hosts an independent vertical `PageView` of full-screen `NewsCard` widgets, with per-category scroll position preserved via `AutomaticKeepAliveClientMixin`. Tapping a card pushes an in-app `WebView` screen loading the article's real URL. All article data is a static in-memory mock list — no network calls for data, only for card images and the article WebView.

**Tech Stack:** Flutter 3.44.6 (Dart 3.12), `webview_flutter` package. Targets Android emulator + iOS simulator (both already available on this machine: `emulator-5554`, iPhone 17 simulator `4D6C3415-646C-4170-B0B6-E35BE79B659F`).

## Global Constraints

- Project lives at `mobile_prototype/` in the repo root, fully separate from `jugantor_epub/`/`main.py` — different language/toolchain, independent deliverable.
- Fixed category set, exact spelling and order: `Main, Politics, World, Bangladesh, Sports, Finance`. App launches into `Main`.
- Mock sources, exact spelling: `Jugantor, Prothom Alo, Dhaka Tribune, Ittefaq`.
- `NewsArticle.articleUrl` values must be real public URLs (WebView renders something real); `NewsArticle.imageUrl` values are allowed to be broken/placeholder — at least one mock article must have a deliberately broken `imageUrl` to exercise the fallback path.
- No RSS/scraping/backend integration, no persistence across restarts, no auth, no analytics — out of scope per the spec.
- Per the spec's Testing section, this prototype's overall deliverable is verified by **manual walkthrough** on emulator/simulator, not an automated test suite. Narrow automated tests are still written where a unit is pure/deterministic and cheap to test (model class, mock data invariants, image-fallback rendering, page-swipe behavior) — but building a full automated coverage suite is explicitly not the goal; don't add tests beyond what each task specifies.

---

## File Structure

```
mobile_prototype/
  pubspec.yaml
  lib/
    main.dart                          # app entry point, MaterialApp -> HomeScreen
    models/
      news_article.dart                # NewsArticle data class
    data/
      mock_articles.dart                # static mock list + category lookup
    widgets/
      news_card.dart                    # full-screen card (image, scrim, text, badge)
    screens/
      home_screen.dart                  # TabController + TabBar + TabBarView
      category_feed.dart                # vertical PageView per category, keep-alive
      article_web_view_screen.dart      # webview_flutter reader screen
  test/
    models/
      news_article_test.dart
    data/
      mock_articles_test.dart
    widgets/
      news_card_test.dart
    screens/
      category_feed_test.dart
```

---

### Task 1: Scaffold the Flutter project

**Files:**
- Create: `mobile_prototype/` (via `flutter create`)
- Modify: `mobile_prototype/test/widget_test.dart` (delete — it tests the default counter app, which we're replacing)

**Interfaces:**
- Produces: a runnable Flutter project at `mobile_prototype/` targeting Android + iOS, with `webview_flutter` added to `pubspec.yaml`. Later tasks add files under `lib/` and `test/` inside this project.

- [ ] **Step 1: Create the Flutter project**

```bash
cd /Users/mehedihasan/Documents/project/dailyNewspaper
flutter create --platforms=android,ios --org com.dailynewspaper mobile_prototype
```

- [ ] **Step 2: Remove the default counter-app test (it will fail once main.dart changes)**

```bash
rm mobile_prototype/test/widget_test.dart
```

- [ ] **Step 3: Add the webview_flutter dependency**

```bash
cd mobile_prototype
flutter pub add webview_flutter
```

- [ ] **Step 4: Verify the scaffold builds and analyzes cleanly**

Run: `cd mobile_prototype && flutter analyze`
Expected: `No issues found!`

- [ ] **Step 5: Commit**

```bash
cd /Users/mehedihasan/Documents/project/dailyNewspaper
git add mobile_prototype
git commit -m "chore: scaffold Flutter news-reels prototype project"
```

---

### Task 2: NewsArticle model

**Files:**
- Create: `mobile_prototype/lib/models/news_article.dart`
- Test: `mobile_prototype/test/models/news_article_test.dart`

**Interfaces:**
- Produces: `class NewsArticle` with fields `id, category, source, headline, snippet, imageUrl, articleUrl` (all `String`, all required, all final), a standard `const` constructor. Later tasks (mock data, NewsCard, CategoryFeed) construct and consume this class exactly.

- [ ] **Step 1: Write the failing test**

```dart
// mobile_prototype/test/models/news_article_test.dart
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile_prototype/models/news_article.dart';

void main() {
  test('NewsArticle stores all fields as provided', () {
    const article = NewsArticle(
      id: 'a1',
      category: 'politics',
      source: 'Jugantor',
      headline: 'Sample headline',
      snippet: 'Sample snippet text.',
      imageUrl: 'https://example.com/image.jpg',
      articleUrl: 'https://example.com/article',
    );

    expect(article.id, 'a1');
    expect(article.category, 'politics');
    expect(article.source, 'Jugantor');
    expect(article.headline, 'Sample headline');
    expect(article.snippet, 'Sample snippet text.');
    expect(article.imageUrl, 'https://example.com/image.jpg');
    expect(article.articleUrl, 'https://example.com/article');
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mobile_prototype && flutter test test/models/news_article_test.dart`
Expected: FAIL — `Target of URI doesn't exist: 'package:mobile_prototype/models/news_article.dart'`

- [ ] **Step 3: Write the model**

```dart
// mobile_prototype/lib/models/news_article.dart
class NewsArticle {
  final String id;
  final String category;
  final String source;
  final String headline;
  final String snippet;
  final String imageUrl;
  final String articleUrl;

  const NewsArticle({
    required this.id,
    required this.category,
    required this.source,
    required this.headline,
    required this.snippet,
    required this.imageUrl,
    required this.articleUrl,
  });
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mobile_prototype && flutter test test/models/news_article_test.dart`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add mobile_prototype/lib/models/news_article.dart mobile_prototype/test/models/news_article_test.dart
git commit -m "feat: add NewsArticle model"
```

---

### Task 3: Mock article data

**Files:**
- Create: `mobile_prototype/lib/data/mock_articles.dart`
- Test: `mobile_prototype/test/data/mock_articles_test.dart`

**Interfaces:**
- Consumes: `NewsArticle` from Task 2 (`package:mobile_prototype/models/news_article.dart`).
- Produces: `const List<NewsArticle> mockArticles` and `List<NewsArticle> articlesForCategory(String category)` (filters `mockArticles` by `category`, returns a new list, does not mutate `mockArticles`). `CategoryFeed` (Task 6) and `HomeScreen` (Task 7) consume `articlesForCategory`.

- [ ] **Step 1: Write the failing tests**

```dart
// mobile_prototype/test/data/mock_articles_test.dart
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile_prototype/data/mock_articles.dart';

const categories = ['main', 'politics', 'world', 'bangladesh', 'sports', 'finance'];

void main() {
  test('every fixed category has at least 2 mock articles', () {
    for (final category in categories) {
      final articles = articlesForCategory(category);
      expect(
        articles.length,
        greaterThanOrEqualTo(2),
        reason: 'category "$category" should have at least 2 mock articles',
      );
    }
  });

  test('main category is a distinct pool, not a union of the other categories', () {
    final mainIds = articlesForCategory('main').map((a) => a.id).toSet();
    final otherIds = categories
        .where((c) => c != 'main')
        .expand((c) => articlesForCategory(c))
        .map((a) => a.id)
        .toSet();

    expect(mainIds.intersection(otherIds), isEmpty);
  });

  test('at least one mock article has a deliberately broken imageUrl', () {
    final broken = mockArticles.where((a) => a.imageUrl.contains('broken-image'));
    expect(broken, isNotEmpty);
  });

  test('articlesForCategory does not mutate the shared mock list', () {
    final before = mockArticles.length;
    articlesForCategory('politics').clear();
    expect(mockArticles.length, before);
  });
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd mobile_prototype && flutter test test/data/mock_articles_test.dart`
Expected: FAIL — `mock_articles.dart` doesn't exist yet

- [ ] **Step 3: Write the mock data**

Populate with at least 2 articles per category (12+ total), sources rotating through Jugantor/Prothom Alo/Dhaka Tribune/Ittefaq, real public `articleUrl`s, and one article with `imageUrl` containing the literal substring `broken-image` to mark the deliberately-broken case:

```dart
// mobile_prototype/lib/data/mock_articles.dart
import '../models/news_article.dart';

const List<NewsArticle> mockArticles = [
  NewsArticle(
    id: 'main-1',
    category: 'main',
    source: 'Jugantor',
    headline: 'Parliament reconvenes for winter session',
    snippet: 'Lawmakers return to the capital as the winter session opens today.',
    imageUrl: 'https://picsum.photos/seed/main1/1080/1920',
    articleUrl: 'https://en.wikipedia.org/wiki/Jatiya_Sangsad',
  ),
  NewsArticle(
    id: 'main-2',
    category: 'main',
    source: 'Prothom Alo',
    headline: 'Dhaka traffic authority unveils new signal plan',
    snippet: 'A pilot program aims to cut average commute times across the city.',
    imageUrl: 'https://picsum.photos/seed/main2/1080/1920',
    articleUrl: 'https://en.wikipedia.org/wiki/Dhaka',
  ),
  NewsArticle(
    id: 'politics-1',
    category: 'politics',
    source: 'Dhaka Tribune',
    headline: 'Election commission announces revised schedule',
    snippet: 'The updated timeline pushes key dates back by two weeks.',
    imageUrl: 'https://picsum.photos/seed/politics1/1080/1920',
    articleUrl: 'https://en.wikipedia.org/wiki/Elections_in_Bangladesh',
  ),
  NewsArticle(
    id: 'politics-2',
    category: 'politics',
    source: 'Ittefaq',
    headline: 'Opposition leaders meet to discuss coalition talks',
    snippet: 'Sources say a joint statement is expected later this week.',
    imageUrl: 'https://broken-image.invalid/politics2.jpg',
    articleUrl: 'https://en.wikipedia.org/wiki/Politics_of_Bangladesh',
  ),
  NewsArticle(
    id: 'world-1',
    category: 'world',
    source: 'Jugantor',
    headline: 'Global summit opens with climate pledges',
    snippet: 'Delegates from over 100 countries gathered for the opening session.',
    imageUrl: 'https://picsum.photos/seed/world1/1080/1920',
    articleUrl: 'https://en.wikipedia.org/wiki/United_Nations_Climate_Change_conference',
  ),
  NewsArticle(
    id: 'world-2',
    category: 'world',
    source: 'Prothom Alo',
    headline: 'Trade talks resume between two major economies',
    snippet: 'Negotiators say a framework agreement could be reached by year end.',
    imageUrl: 'https://picsum.photos/seed/world2/1080/1920',
    articleUrl: 'https://en.wikipedia.org/wiki/International_trade',
  ),
  NewsArticle(
    id: 'bangladesh-1',
    category: 'bangladesh',
    source: 'Dhaka Tribune',
    headline: 'Flood relief efforts expand in northern districts',
    snippet: 'Volunteers and local authorities coordinate aid distribution.',
    imageUrl: 'https://picsum.photos/seed/bd1/1080/1920',
    articleUrl: 'https://en.wikipedia.org/wiki/Geography_of_Bangladesh',
  ),
  NewsArticle(
    id: 'bangladesh-2',
    category: 'bangladesh',
    source: 'Ittefaq',
    headline: 'New metro rail extension approved',
    snippet: 'The extension is expected to reduce congestion in the eastern corridor.',
    imageUrl: 'https://picsum.photos/seed/bd2/1080/1920',
    articleUrl: 'https://en.wikipedia.org/wiki/Dhaka_Metro_Rail',
  ),
  NewsArticle(
    id: 'sports-1',
    category: 'sports',
    source: 'Jugantor',
    headline: 'National cricket team names squad for tour',
    snippet: 'The selectors made two changes ahead of the upcoming series.',
    imageUrl: 'https://picsum.photos/seed/sports1/1080/1920',
    articleUrl: 'https://en.wikipedia.org/wiki/Bangladesh_national_cricket_team',
  ),
  NewsArticle(
    id: 'sports-2',
    category: 'sports',
    source: 'Prothom Alo',
    headline: 'Local football league season kicks off',
    snippet: 'Defending champions open with a home fixture this weekend.',
    imageUrl: 'https://picsum.photos/seed/sports2/1080/1920',
    articleUrl: 'https://en.wikipedia.org/wiki/Football_in_Bangladesh',
  ),
  NewsArticle(
    id: 'finance-1',
    category: 'finance',
    source: 'Dhaka Tribune',
    headline: 'Central bank holds interest rates steady',
    snippet: 'Policymakers cite easing inflation as the main factor.',
    imageUrl: 'https://picsum.photos/seed/finance1/1080/1920',
    articleUrl: 'https://en.wikipedia.org/wiki/Bangladesh_Bank',
  ),
  NewsArticle(
    id: 'finance-2',
    category: 'finance',
    source: 'Ittefaq',
    headline: 'Stock market closes higher on strong earnings',
    snippet: 'Gains were led by the banking and textile sectors.',
    imageUrl: 'https://picsum.photos/seed/finance2/1080/1920',
    articleUrl: 'https://en.wikipedia.org/wiki/Dhaka_Stock_Exchange',
  ),
];

List<NewsArticle> articlesForCategory(String category) {
  return mockArticles.where((a) => a.category == category).toList();
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd mobile_prototype && flutter test test/data/mock_articles_test.dart`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add mobile_prototype/lib/data/mock_articles.dart mobile_prototype/test/data/mock_articles_test.dart
git commit -m "feat: add mock article dataset"
```

---

### Task 4: NewsCard widget

**Files:**
- Create: `mobile_prototype/lib/widgets/news_card.dart`
- Test: `mobile_prototype/test/widgets/news_card_test.dart`

**Interfaces:**
- Consumes: `NewsArticle` from Task 2.
- Produces: `class NewsCard extends StatelessWidget` with constructor `NewsCard({required NewsArticle article, ImageProvider Function(String url)? imageProviderBuilder, super.key})`. `imageProviderBuilder` defaults to `(url) => NetworkImage(url)` and exists solely so tests can inject a failing provider without real network access. `CategoryFeed` (Task 6) consumes `NewsCard` with just `article:`.

- [ ] **Step 1: Write the failing tests**

```dart
// mobile_prototype/test/widgets/news_card_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile_prototype/models/news_article.dart';
import 'package:mobile_prototype/widgets/news_card.dart';

const article = NewsArticle(
  id: 'a1',
  category: 'politics',
  source: 'Jugantor',
  headline: 'Test headline',
  snippet: 'Test snippet text.',
  imageUrl: 'https://example.com/image.jpg',
  articleUrl: 'https://example.com/article',
);

// Synchronously fails to load, so errorBuilder fires without any real network I/O.
class FailingImageProvider extends ImageProvider<FailingImageProvider> {
  @override
  Future<FailingImageProvider> obtainKey(ImageConfiguration configuration) =>
      SynchronousFuture(this);

  @override
  ImageStreamCompleter loadImage(FailingImageProvider key, ImageDecoderCallback decode) {
    return OneFrameImageStreamCompleter(
      Future<ImageInfo>.error(Exception('simulated image load failure')),
    );
  }
}

void main() {
  testWidgets('renders headline, source, and snippet', (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: NewsCard(
        article: article,
        imageProviderBuilder: (_) => FailingImageProvider(),
      ),
    ));
    await tester.pump();

    expect(find.text('Test headline'), findsOneWidget);
    expect(find.text('Jugantor'), findsOneWidget);
    expect(find.text('Test snippet text.'), findsOneWidget);
  });

  testWidgets('falls back to a placeholder icon when the image fails to load', (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: NewsCard(
        article: article,
        imageProviderBuilder: (_) => FailingImageProvider(),
      ),
    ));
    await tester.pump();

    expect(find.byIcon(Icons.broken_image_outlined), findsOneWidget);
  });
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd mobile_prototype && flutter test test/widgets/news_card_test.dart`
Expected: FAIL — `news_card.dart` doesn't exist yet

- [ ] **Step 3: Write the widget**

```dart
// mobile_prototype/lib/widgets/news_card.dart
import 'package:flutter/material.dart';

import '../models/news_article.dart';

class NewsCard extends StatelessWidget {
  final NewsArticle article;
  final ImageProvider Function(String url) imageProviderBuilder;

  NewsCard({
    super.key,
    required this.article,
    ImageProvider Function(String url)? imageProviderBuilder,
  }) : imageProviderBuilder = imageProviderBuilder ?? ((url) => NetworkImage(url));

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        Image(
          image: imageProviderBuilder(article.imageUrl),
          fit: BoxFit.cover,
          errorBuilder: (context, error, stackTrace) => Container(
            color: Colors.grey.shade800,
            alignment: Alignment.center,
            child: const Icon(
              Icons.broken_image_outlined,
              color: Colors.white54,
              size: 64,
            ),
          ),
        ),
        DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [Colors.transparent, Colors.black.withOpacity(0.85)],
              stops: const [0.5, 1.0],
            ),
          ),
        ),
        Align(
          alignment: Alignment.bottomLeft,
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.15),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(
                    article.source,
                    style: const TextStyle(color: Colors.white, fontSize: 12),
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  article.headline,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 24,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  article.snippet,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: Colors.white70, fontSize: 15),
                ),
                const SizedBox(height: 8),
                const Text(
                  'Read more →',
                  style: TextStyle(color: Colors.white, fontWeight: FontWeight.w600),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd mobile_prototype && flutter test test/widgets/news_card_test.dart`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add mobile_prototype/lib/widgets/news_card.dart mobile_prototype/test/widgets/news_card_test.dart
git commit -m "feat: add NewsCard widget with image-fallback handling"
```

---

### Task 5: Article WebView screen

**Files:**
- Create: `mobile_prototype/lib/screens/article_web_view_screen.dart`

**Interfaces:**
- Consumes: nothing from earlier tasks beyond the `webview_flutter` package added in Task 1.
- Produces: `class ArticleWebViewScreen extends StatefulWidget` with constructor `ArticleWebViewScreen({required String articleUrl, super.key})`. `HomeScreen`/`NewsCard` tap handling (Task 7) navigates to this via `Navigator.push(context, MaterialPageRoute(builder: (_) => ArticleWebViewScreen(articleUrl: article.articleUrl)))`.

No automated test for this task — `webview_flutter` requires platform channels that don't run under `flutter test`'s widget test harness. Verified manually as part of Task 7's end-to-end walkthrough.

- [ ] **Step 1: Write the screen**

```dart
// mobile_prototype/lib/screens/article_web_view_screen.dart
import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

class ArticleWebViewScreen extends StatefulWidget {
  final String articleUrl;

  const ArticleWebViewScreen({super.key, required this.articleUrl});

  @override
  State<ArticleWebViewScreen> createState() => _ArticleWebViewScreenState();
}

class _ArticleWebViewScreenState extends State<ArticleWebViewScreen> {
  late final WebViewController _controller;
  bool _hasError = false;

  @override
  void initState() {
    super.initState();
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(
        NavigationDelegate(
          onWebResourceError: (error) => setState(() => _hasError = true),
        ),
      )
      ..loadRequest(Uri.parse(widget.articleUrl));
  }

  void _retry() {
    setState(() => _hasError = false);
    _controller.loadRequest(Uri.parse(widget.articleUrl));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: BackButton(onPressed: () => Navigator.of(context).pop()),
      ),
      body: _hasError
          ? Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Text('Couldn\'t load this article.'),
                  const SizedBox(height: 12),
                  ElevatedButton(onPressed: _retry, child: const Text('Retry')),
                ],
              ),
            )
          : WebViewWidget(controller: _controller),
    );
  }
}
```

- [ ] **Step 2: Verify it analyzes cleanly**

Run: `cd mobile_prototype && flutter analyze`
Expected: `No issues found!`

- [ ] **Step 3: Commit**

```bash
git add mobile_prototype/lib/screens/article_web_view_screen.dart
git commit -m "feat: add article WebView reader screen"
```

---

### Task 6: CategoryFeed (vertical paging per category)

**Files:**
- Create: `mobile_prototype/lib/screens/category_feed.dart`
- Test: `mobile_prototype/test/screens/category_feed_test.dart`

**Interfaces:**
- Consumes: `NewsArticle` (Task 2), `NewsCard` (Task 4), `ArticleWebViewScreen` (Task 5).
- Produces: `class CategoryFeed extends StatefulWidget` with constructor `CategoryFeed({required String category, required List<NewsArticle> articles, super.key})`. Mixes in `AutomaticKeepAliveClientMixin` so its scroll position survives being swapped out of view inside a `TabBarView`. `HomeScreen` (Task 7) consumes it as `CategoryFeed(category: category, articles: articlesForCategory(category))`, one per tab, wrapped so `AutomaticKeepAliveClientMixin` can do its job (a `TabBarView` keeps its children's `State` alive across tab switches as long as each child opts in via the mixin — no extra wrapper needed beyond that).

- [ ] **Step 1: Write the failing test**

```dart
// mobile_prototype/test/screens/category_feed_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile_prototype/models/news_article.dart';
import 'package:mobile_prototype/screens/category_feed.dart';

const articles = [
  NewsArticle(
    id: 'p1',
    category: 'politics',
    source: 'Jugantor',
    headline: 'First headline',
    snippet: 'First snippet.',
    imageUrl: 'https://example.com/1.jpg',
    articleUrl: 'https://example.com/article1',
  ),
  NewsArticle(
    id: 'p2',
    category: 'politics',
    source: 'Ittefaq',
    headline: 'Second headline',
    snippet: 'Second snippet.',
    imageUrl: 'https://example.com/2.jpg',
    articleUrl: 'https://example.com/article2',
  ),
];

void main() {
  testWidgets('vertical drag advances to the next article in the category', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: CategoryFeed(category: 'politics', articles: articles),
    ));
    await tester.pump();

    expect(find.text('First headline'), findsOneWidget);
    expect(find.text('Second headline'), findsNothing);

    await tester.drag(find.byType(CategoryFeed), const Offset(0, -600));
    await tester.pumpAndSettle();

    expect(find.text('First headline'), findsNothing);
    expect(find.text('Second headline'), findsOneWidget);
  });

  testWidgets('shows a placeholder when the category has no articles', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: CategoryFeed(category: 'finance', articles: []),
    ));
    await tester.pump();

    expect(find.text('No stories yet'), findsOneWidget);
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mobile_prototype && flutter test test/screens/category_feed_test.dart`
Expected: FAIL — `category_feed.dart` doesn't exist yet

- [ ] **Step 3: Write the widget**

```dart
// mobile_prototype/lib/screens/category_feed.dart
import 'package:flutter/material.dart';

import '../models/news_article.dart';
import '../widgets/news_card.dart';
import 'article_web_view_screen.dart';

class CategoryFeed extends StatefulWidget {
  final String category;
  final List<NewsArticle> articles;

  const CategoryFeed({super.key, required this.category, required this.articles});

  @override
  State<CategoryFeed> createState() => _CategoryFeedState();
}

class _CategoryFeedState extends State<CategoryFeed>
    with AutomaticKeepAliveClientMixin<CategoryFeed> {
  final PageController _pageController = PageController();

  @override
  bool get wantKeepAlive => true;

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);

    if (widget.articles.isEmpty) {
      return const Center(child: Text('No stories yet'));
    }

    return PageView.builder(
      controller: _pageController,
      scrollDirection: Axis.vertical,
      itemCount: widget.articles.length,
      itemBuilder: (context, index) {
        final article = widget.articles[index];
        return GestureDetector(
          onTap: () => Navigator.of(context).push(
            MaterialPageRoute(
              builder: (_) => ArticleWebViewScreen(articleUrl: article.articleUrl),
            ),
          ),
          child: NewsCard(article: article),
        );
      },
    );
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mobile_prototype && flutter test test/screens/category_feed_test.dart`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add mobile_prototype/lib/screens/category_feed.dart mobile_prototype/test/screens/category_feed_test.dart
git commit -m "feat: add CategoryFeed vertical paging screen"
```

---

### Task 7: HomeScreen and app entry point

**Files:**
- Create: `mobile_prototype/lib/screens/home_screen.dart`
- Modify: `mobile_prototype/lib/main.dart`

**Interfaces:**
- Consumes: `articlesForCategory` (Task 3), `CategoryFeed` (Task 6).
- Produces: `class HomeScreen extends StatefulWidget` with a `TabController` of length 6 over the fixed category list; `main.dart`'s `MaterialApp` uses `HomeScreen` as `home`. This is the last piece wiring everything together — no further task depends on its interface.

No automated test for this task (it composes already-tested pieces via `TabController`/`TabBarView`, which is straightforward wiring). Verified manually per the steps below, matching the spec's Testing section.

- [ ] **Step 1: Write HomeScreen**

```dart
// mobile_prototype/lib/screens/home_screen.dart
import 'package:flutter/material.dart';

import '../data/mock_articles.dart';
import 'category_feed.dart';

const List<({String label, String key})> kCategories = [
  (label: 'Main', key: 'main'),
  (label: 'Politics', key: 'politics'),
  (label: 'World', key: 'world'),
  (label: 'Bangladesh', key: 'bangladesh'),
  (label: 'Sports', key: 'sports'),
  (label: 'Finance', key: 'finance'),
];

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> with SingleTickerProviderStateMixin {
  late final TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: kCategories.length, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: TabBar(
          controller: _tabController,
          isScrollable: true,
          tabs: kCategories.map((c) => Tab(text: c.label)).toList(),
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: kCategories
            .map((c) => CategoryFeed(
                  key: PageStorageKey(c.key),
                  category: c.key,
                  articles: articlesForCategory(c.key),
                ))
            .toList(),
      ),
    );
  }
}
```

- [ ] **Step 2: Wire it into main.dart**

```dart
// mobile_prototype/lib/main.dart
import 'package:flutter/material.dart';

import 'screens/home_screen.dart';

void main() {
  runApp(const NewsReelsApp());
}

class NewsReelsApp extends StatelessWidget {
  const NewsReelsApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'News Reels Prototype',
      theme: ThemeData(colorSchemeSeed: Colors.red, useMaterial3: true),
      home: const HomeScreen(),
    );
  }
}
```

- [ ] **Step 3: Verify it analyzes cleanly**

Run: `cd mobile_prototype && flutter analyze`
Expected: `No issues found!`

- [ ] **Step 4: Run the full automated test suite**

Run: `cd mobile_prototype && flutter test`
Expected: all tests from Tasks 2, 3, 4, 6 PASS

- [ ] **Step 5: Manual walkthrough on the Android emulator**

```bash
flutter run -d emulator-5554
```

Confirm each of these (matches the spec's Testing/Verification section):
1. App launches into the "Main" tab.
2. Vertical scroll (swipe up/down) moves through all cards within a category.
3. Horizontal swipe on the card body moves to the adjacent category tab, in both directions, across all 6 categories.
4. Tapping a non-adjacent tab (e.g. "Main" → "Finance" directly) jumps straight there.
5. Scroll partway into "Politics", swipe to "World", swipe back to "Politics" — it resumes where you left off (not reset to the first card).
6. Tap a card — the WebView opens and loads the real article URL; back button returns to the same card in the feed.
7. Locate the article with a `broken-image` `imageUrl` (politics-2, "Opposition leaders meet to discuss coalition talks") and confirm it shows the gray placeholder icon instead of a broken image.

- [ ] **Step 6: Repeat the manual walkthrough on the iOS simulator**

```bash
flutter run -d 4D6C3415-646C-4170-B0B6-E35BE79B659F
```

Confirm the same 7 points above.

- [ ] **Step 7: Commit**

```bash
git add mobile_prototype/lib/screens/home_screen.dart mobile_prototype/lib/main.dart
git commit -m "feat: wire HomeScreen tabs and category feeds into the app"
```

---

### Task 8: Prototype README

**Files:**
- Create: `mobile_prototype/README.md`

**Interfaces:** none — documentation only.

- [ ] **Step 1: Write the README**

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add mobile_prototype/README.md
git commit -m "docs: add mobile_prototype README"
```
