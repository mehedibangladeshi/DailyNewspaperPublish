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
