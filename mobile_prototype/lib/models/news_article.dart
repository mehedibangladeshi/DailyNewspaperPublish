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
