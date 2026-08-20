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
