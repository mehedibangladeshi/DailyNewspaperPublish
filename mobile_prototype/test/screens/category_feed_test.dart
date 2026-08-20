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
