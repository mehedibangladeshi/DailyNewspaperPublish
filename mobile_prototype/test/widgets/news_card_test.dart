import 'package:flutter/foundation.dart';
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
