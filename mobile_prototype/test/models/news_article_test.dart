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
