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
