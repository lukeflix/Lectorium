import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:sqflite/sqflite.dart';
import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:file_picker/file_picker.dart';
import 'dart:io';

// ── COLORES ──────────────────────────────────────────────────────────────────

const Color kBg      = Color(0xFF0D0B0A);
const Color kSurface = Color(0xFF1A1714);
const Color kCard    = Color(0xFF211E1B);
const Color kBorder  = Color(0xFF2E2825);
const Color kGold    = Color(0xFFC9A84C);
const Color kGoldDim = Color(0xFF8A6E30);
const Color kText    = Color(0xFFE8E0D5);
const Color kMuted   = Color(0xFF9A8F84);
const Color kDim     = Color(0xFF6B605A);
const Color kRed     = Color(0xFF8B2635);

// Light theme
const Color kLightBg      = Color(0xFFF5F0E8);
const Color kLightSurface = Color(0xFFEDE8DF);
const Color kLightText    = Color(0xFF2A2018);
const Color kLightMuted   = Color(0xFF7A6A5A);

// Sepia theme
const Color kSepiaBg   = Color(0xFFF2E8D5);
const Color kSepiaText = Color(0xFF3A2A18);

// ── DATABASE ──────────────────────────────────────────────────────────────────

class DB {
  static Database? _db;

  static Future<Database> get instance async {
    _db ??= await _init();
    return _db!;
  }

  static Future<Database> _init() async {
    final dbPath = await getDatabasesPath();
    return openDatabase(
      p.join(dbPath, 'lectorium.db'),
      version: 1,
      onCreate: (db, version) async {
        await db.execute('''
          CREATE TABLE stories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT DEFAULT '',
            rating INTEGER DEFAULT 0,
            added_at INTEGER DEFAULT (strftime('%s','now')),
            word_count INTEGER DEFAULT 0
          )
        ''');
        await db.execute('''
          CREATE TABLE chapters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            story_id INTEGER NOT NULL,
            num INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            word_count INTEGER DEFAULT 0,
            FOREIGN KEY (story_id) REFERENCES stories(id) ON DELETE CASCADE
          )
        ''');
        await db.execute('''
          CREATE TABLE progress (
            story_id INTEGER PRIMARY KEY,
            chapter_id INTEGER,
            scroll_pct REAL DEFAULT 0,
            FOREIGN KEY (story_id) REFERENCES stories(id) ON DELETE CASCADE
          )
        ''');
      },
    );
  }

  static Future<List<Map<String, dynamic>>> getStories() async {
    final db = await instance;
    return db.rawQuery('''
      SELECT s.*, COUNT(c.id) as chap_count,
             p.chapter_id, p.scroll_pct
      FROM stories s
      LEFT JOIN chapters c ON c.story_id = s.id
      LEFT JOIN progress p ON p.story_id = s.id
      GROUP BY s.id
      ORDER BY s.added_at DESC
    ''');
  }

  static Future<List<Map<String, dynamic>>> getChapters(int storyId) async {
    final db = await instance;
    return db.query('chapters',
        where: 'story_id = ?',
        whereArgs: [storyId],
        orderBy: 'num ASC');
  }

  static Future<int> saveStory(String title, String category,
      List<Map<String, dynamic>> chapters) async {
    final db = await instance;
    int totalWords = chapters.fold(0, (s, c) => s + (c['word_count'] as int));
    final id = await db.insert('stories', {
      'title': title,
      'category': category,
      'word_count': totalWords,
      'added_at': DateTime.now().millisecondsSinceEpoch ~/ 1000,
    });
    for (final c in chapters) {
      await db.insert('chapters', {
        'story_id': id,
        'num': c['num'],
        'title': c['title'],
        'content': c['content'],
        'word_count': c['word_count'],
      });
    }
    return id;
  }

  static Future<void> addChapter(
      int storyId, String title, String content) async {
    final db = await instance;
    final result = await db.rawQuery(
        'SELECT COALESCE(MAX(num),0) as n FROM chapters WHERE story_id=?',
        [storyId]);
    final num = (result.first['n'] as int) + 1;
    final wc = content.trim().split(RegExp(r'\s+')).length;
    await db.insert('chapters', {
      'story_id': storyId,
      'num': num,
      'title': title,
      'content': content,
      'word_count': wc,
    });
    await db.rawUpdate(
        'UPDATE stories SET word_count = word_count + ? WHERE id = ?',
        [wc, storyId]);
  }

  static Future<void> deleteStory(int id) async {
    final db = await instance;
    await db.delete('stories', where: 'id = ?', whereArgs: [id]);
  }

  static Future<void> saveProgress(
      int storyId, int chapterId, double pct) async {
    final db = await instance;
    await db.insert(
        'progress',
        {'story_id': storyId, 'chapter_id': chapterId, 'scroll_pct': pct},
        conflictAlgorithm: ConflictAlgorithm.replace);
  }

  static Future<Map<String, dynamic>?> getProgress(int storyId) async {
    final db = await instance;
    final r = await db.query('progress',
        where: 'story_id = ?', whereArgs: [storyId]);
    return r.isEmpty ? null : r.first;
  }

  static Future<void> updateRating(int storyId, int rating) async {
    final db = await instance;
    await db.update('stories', {'rating': rating},
        where: 'id = ?', whereArgs: [storyId]);
  }
}

// ── SETTINGS ─────────────────────────────────────────────────────────────────

class Settings {
  static late SharedPreferences _prefs;

  static Future<void> init() async {
    _prefs = await SharedPreferences.getInstance();
  }

  static String get theme => _prefs.getString('theme') ?? 'dark';
  static set theme(String v) => _prefs.setString('theme', v);

  static double get fontSize => _prefs.getDouble('font_size') ?? 18.0;
  static set fontSize(double v) => _prefs.setDouble('font_size', v);
}

// ── APP ───────────────────────────────────────────────────────────────────────

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Settings.init();
  SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
  runApp(const LectoriumApp());
}

class LectoriumApp extends StatefulWidget {
  const LectoriumApp({super.key});

  static _LectoriumAppState? of(BuildContext context) =>
      context.findAncestorStateOfType<_LectoriumAppState>();

  @override
  State<LectoriumApp> createState() => _LectoriumAppState();
}

class _LectoriumAppState extends State<LectoriumApp> {
  String _theme = Settings.theme;

  void setTheme(String t) {
    setState(() => _theme = t);
    Settings.theme = t;
  }

  ThemeData get _themeData {
    switch (_theme) {
      case 'light':
        return ThemeData(
          brightness: Brightness.light,
          scaffoldBackgroundColor: kLightBg,
          colorScheme: const ColorScheme.light(
            primary: kGold,
            surface: kLightSurface,
          ),
          appBarTheme: const AppBarTheme(
            backgroundColor: kLightSurface,
            foregroundColor: kLightText,
            elevation: 0,
          ),
        );
      case 'sepia':
        return ThemeData(
          brightness: Brightness.light,
          scaffoldBackgroundColor: kSepiaBg,
          colorScheme: const ColorScheme.light(
            primary: kGoldDim,
            surface: Color(0xFFE8DCC5),
          ),
          appBarTheme: const AppBarTheme(
            backgroundColor: Color(0xFFE8DCC5),
            foregroundColor: kSepiaText,
            elevation: 0,
          ),
        );
      default: // dark
        return ThemeData(
          brightness: Brightness.dark,
          scaffoldBackgroundColor: kBg,
          colorScheme: const ColorScheme.dark(
            primary: kGold,
            surface: kSurface,
          ),
          appBarTheme: const AppBarTheme(
            backgroundColor: kSurface,
            foregroundColor: kText,
            elevation: 0,
          ),
          cardColor: kCard,
        );
    }
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Lectorium',
      debugShowCheckedModeBanner: false,
      theme: _themeData,
      initialRoute: '/',
      routes: {
        '/': (ctx) => const LibraryScreen(),
        '/settings': (ctx) => const SettingsScreen(),
      },
      onGenerateRoute: (settings) {
        if (settings.name == '/reader') {
          final args = settings.arguments as Map<String, dynamic>;
          return MaterialPageRoute(
            builder: (ctx) => ReaderScreen(
              story: args['story'],
              chapters: args['chapters'],
              initialChap: args['initialChap'] ?? 0,
              initialPct: args['initialPct'] ?? 0.0,
            ),
          );
        }
        return null;
      },
    );
  }
}

// ── LIBRARY SCREEN ────────────────────────────────────────────────────────────

class LibraryScreen extends StatefulWidget {
  const LibraryScreen({super.key});

  @override
  State<LibraryScreen> createState() => _LibraryScreenState();
}

class _LibraryScreenState extends State<LibraryScreen> {
  List<Map<String, dynamic>> _stories = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final stories = await DB.getStories();
    if (mounted) setState(() { _stories = stories; _loading = false; });
  }

  Future<void> _openReader(Map<String, dynamic> story) async {
    final chapters = await DB.getChapters(story['id'] as int);
    final prog = await DB.getProgress(story['id'] as int);
    int initialChap = 0;
    double initialPct = 0.0;
    if (prog != null) {
      initialChap = chapters.indexWhere(
          (c) => c['id'] == prog['chapter_id']);
      if (initialChap < 0) initialChap = 0;
      initialPct = (prog['scroll_pct'] as double?) ?? 0.0;
    }
    if (mounted) {
      await Navigator.pushNamed(context, '/reader', arguments: {
        'story': story,
        'chapters': chapters,
        'initialChap': initialChap,
        'initialPct': initialPct,
      });
      _load();
    }
  }

  Future<void> _deleteStory(int id) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: kCard,
        title: const Text('Eliminar relato',
            style: TextStyle(color: kText)),
        content: const Text('Esta acción no se puede deshacer.',
            style: TextStyle(color: kMuted)),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancelar', style: TextStyle(color: kMuted)),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Eliminar',
                style: TextStyle(color: kRed)),
          ),
        ],
      ),
    );
    if (confirm == true) {
      await DB.deleteStory(id);
      _load();
    }
  }

  void _showPasteDialog({String mode = 'single',
      Map<String, dynamic>? story}) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: kCard,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) => PasteSheet(
        mode: mode,
        story: story,
        onSaved: _load,
      ),
    );
  }

  Future<void> _pickFiles({String mode = 'single',
      Map<String, dynamic>? story}) async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['txt'],
      allowMultiple: mode != 'single',
    );
    if (result == null || result.files.isEmpty) return;

    final files = result.files;
    files.sort((a, b) => _naturalSort(a.name, b.name));

    if (mode == 'single') {
      final content = await File(files.first.path!).readAsString();
      final title = files.first.name.replaceAll('.txt', '').replaceAll('_', ' ');
      final wc = content.trim().split(RegExp(r'\s+')).length;
      await DB.saveStory(title, '', [
        {'num': 1, 'title': title, 'content': content, 'word_count': wc}
      ]);
      _load();
    } else if (mode == 'series') {
      final chapters = <Map<String, dynamic>>[];
      for (int i = 0; i < files.length; i++) {
        final content = await File(files[i].path!).readAsString();
        final title = files[i].name.replaceAll('.txt', '').replaceAll('_', ' ');
        chapters.add({
          'num': i + 1,
          'title': title,
          'content': content,
          'word_count': content.trim().split(RegExp(r'\s+')).length,
        });
      }
      final seriesTitle = _commonPrefix(files.map((f) =>
          f.name.replaceAll('.txt', '')).toList()).trim();
      if (mounted) {
        _showSeriesTitleDialog(
            seriesTitle.isNotEmpty ? seriesTitle : chapters.first['title'],
            chapters);
      }
    } else if (mode == 'chapter' && story != null) {
      for (final file in files) {
        final content = await File(file.path!).readAsString();
        final title = file.name.replaceAll('.txt', '').replaceAll('_', ' ');
        await DB.addChapter(story['id'] as int, title, content);
      }
      _load();
    }
  }

  void _showSeriesTitleDialog(
      String suggested, List<Map<String, dynamic>> chapters) {
    final ctrl = TextEditingController(text: suggested);
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: kCard,
        title: const Text('Título del relato',
            style: TextStyle(color: kText)),
        content: TextField(
          controller: ctrl,
          style: const TextStyle(color: kText),
          decoration: const InputDecoration(
            hintText: 'Nombre del relato…',
            hintStyle: TextStyle(color: kDim),
            enabledBorder: UnderlineInputBorder(
                borderSide: BorderSide(color: kBorder)),
            focusedBorder: UnderlineInputBorder(
                borderSide: BorderSide(color: kGold)),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancelar',
                style: TextStyle(color: kMuted)),
          ),
          TextButton(
            onPressed: () async {
              Navigator.pop(ctx);
              await DB.saveStory(ctrl.text.trim(), '', chapters);
              _load();
            },
            child: const Text('Crear',
                style: TextStyle(color: kGold)),
          ),
        ],
      ),
    );
  }

  String _naturalSort(String a, String b) => a.compareTo(b) <= 0 ? a : b;

  String _commonPrefix(List<String> strs) {
    if (strs.isEmpty) return '';
    String prefix = strs[0];
    for (final s in strs.skip(1)) {
      while (!s.startsWith(prefix)) {
        prefix = prefix.substring(0, prefix.length - 1);
        if (prefix.isEmpty) return '';
      }
    }
    return prefix;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('LECTORIUM',
            style: TextStyle(
                color: kGold,
                fontWeight: FontWeight.bold,
                letterSpacing: 2)),
        actions: [
          IconButton(
            icon: const Icon(Icons.settings, color: kMuted),
            onPressed: () =>
                Navigator.pushNamed(context, '/settings').then((_) => _load()),
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: kGold))
          : _stories.isEmpty
              ? _emptyState()
              : _storyList(),
      bottomNavigationBar: _bottomBar(),
    );
  }

  Widget _emptyState() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.menu_book_outlined, size: 64, color: kDim),
          const SizedBox(height: 16),
          const Text('Tu biblioteca está vacía',
              style: TextStyle(
                  color: kMuted, fontSize: 18, fontStyle: FontStyle.italic)),
          const SizedBox(height: 8),
          const Text('Carga un TXT o pega el texto de un relato',
              style: TextStyle(color: kDim, fontSize: 13)),
          const SizedBox(height: 24),
          ElevatedButton.icon(
            onPressed: () => _pickFiles(mode: 'single'),
            icon: const Icon(Icons.upload_file),
            label: const Text('Cargar TXT'),
            style: ElevatedButton.styleFrom(
              backgroundColor: kGold,
              foregroundColor: kBg,
            ),
          ),
        ],
      ),
    );
  }

  Widget _storyList() {
    return RefreshIndicator(
      color: kGold,
      onRefresh: _load,
      child: ListView.separated(
        padding: const EdgeInsets.all(12),
        itemCount: _stories.length,
        separatorBuilder: (_, __) => const SizedBox(height: 8),
        itemBuilder: (ctx, i) => _storyCard(_stories[i]),
      ),
    );
  }

  Widget _storyCard(Map<String, dynamic> s) {
    final chapCount = s['chap_count'] as int? ?? 0;
    final words = s['word_count'] as int? ?? 0;
    final readMin = (words / 250).ceil();
    final pct = ((s['scroll_pct'] as double?) ?? 0.0);
    final pctInt = (pct * 100).round();

    return Card(
      color: kCard,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: const BorderSide(color: kBorder, width: 0.5),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: () => _openReader(s),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Category + chapter badge
              Row(children: [
                if ((s['category'] as String).isNotEmpty) ...[
                  Text((s['category'] as String).toUpperCase(),
                      style: const TextStyle(
                          color: kGoldDim,
                          fontSize: 10,
                          letterSpacing: 1.5)),
                  const SizedBox(width: 8),
                ],
                if (chapCount > 1)
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      color: kRed,
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text('$chapCount caps',
                        style: const TextStyle(
                            color: Colors.white, fontSize: 10)),
                  ),
              ]),
              const SizedBox(height: 6),
              // Title
              Text(s['title'] as String,
                  style: const TextStyle(
                      color: kText,
                      fontSize: 16,
                      fontWeight: FontWeight.bold),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis),
              const SizedBox(height: 6),
              // Meta
              Text(
                '$words palabras  ·  ~$readMin min'
                '${pctInt > 2 ? '  ·  📍$pctInt%' : ''}',
                style: const TextStyle(color: kDim, fontSize: 11),
              ),
              // Progress bar
              if (pctInt > 2) ...[
                const SizedBox(height: 6),
                ClipRRect(
                  borderRadius: BorderRadius.circular(2),
                  child: LinearProgressIndicator(
                    value: pct,
                    backgroundColor: kBorder,
                    valueColor:
                        const AlwaysStoppedAnimation<Color>(kGold),
                    minHeight: 2,
                  ),
                ),
              ],
              const SizedBox(height: 10),
              // Action buttons
              Row(children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: () => _openReader(s),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: kGold,
                      side: const BorderSide(color: kGoldDim),
                      padding: const EdgeInsets.symmetric(vertical: 8),
                    ),
                    child: const Text('Leer  ›'),
                  ),
                ),
                const SizedBox(width: 8),
                OutlinedButton(
                  onPressed: () => _pickFiles(
                      mode: 'chapter', story: s),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: kMuted,
                    side: const BorderSide(color: kBorder),
                    padding: const EdgeInsets.symmetric(
                        vertical: 8, horizontal: 12),
                  ),
                  child: const Text('+ Cap.', style: TextStyle(fontSize: 12)),
                ),
                const SizedBox(width: 8),
                IconButton(
                  onPressed: () => _deleteStory(s['id'] as int),
                  icon: const Icon(Icons.delete_outline, color: kDim),
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(),
                ),
              ]),
            ],
          ),
        ),
      ),
    );
  }

  Widget _bottomBar() {
    return Container(
      color: kSurface,
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
      child: Row(children: [
        Expanded(
          flex: 5,
          child: ElevatedButton.icon(
            onPressed: () => _pickFiles(mode: 'single'),
            icon: const Icon(Icons.upload_file, size: 18),
            label: const Text('Cargar TXT'),
            style: ElevatedButton.styleFrom(
              backgroundColor: kGold,
              foregroundColor: kBg,
              padding: const EdgeInsets.symmetric(vertical: 12),
            ),
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          flex: 3,
          child: OutlinedButton(
            onPressed: () => _pickFiles(mode: 'series'),
            style: OutlinedButton.styleFrom(
              foregroundColor: kMuted,
              side: const BorderSide(color: kBorder),
              padding: const EdgeInsets.symmetric(vertical: 12),
            ),
            child: const Text('📚 Serie', style: TextStyle(fontSize: 12)),
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          flex: 3,
          child: OutlinedButton(
            onPressed: () => _showPasteDialog(),
            style: OutlinedButton.styleFrom(
              foregroundColor: kMuted,
              side: const BorderSide(color: kBorder),
              padding: const EdgeInsets.symmetric(vertical: 12),
            ),
            child: const Text('📋 Pegar', style: TextStyle(fontSize: 12)),
          ),
        ),
      ]),
    );
  }
}

// ── PASTE SHEET ───────────────────────────────────────────────────────────────

class PasteSheet extends StatefulWidget {
  final String mode;
  final Map<String, dynamic>? story;
  final VoidCallback onSaved;

  const PasteSheet(
      {super.key,
      required this.mode,
      this.story,
      required this.onSaved});

  @override
  State<PasteSheet> createState() => _PasteSheetState();
}

class _PasteSheetState extends State<PasteSheet> {
  final _titleCtrl = TextEditingController();
  final _textCtrl = TextEditingController();
  int _wordCount = 0;

  @override
  void dispose() {
    _titleCtrl.dispose();
    _textCtrl.dispose();
    super.dispose();
  }

  void _onTextChanged(String v) {
    setState(() {
      _wordCount =
          v.trim().isEmpty ? 0 : v.trim().split(RegExp(r'\s+')).length;
    });
  }

  Future<void> _save() async {
    final text = _textCtrl.text.trim();
    if (text.isEmpty) return;
    final title = _titleCtrl.text.trim().isNotEmpty
        ? _titleCtrl.text.trim()
        : text.split('\n').first.substring(0,
            text.split('\n').first.length.clamp(0, 60));
    final wc = text.split(RegExp(r'\s+')).length;

    if (widget.mode == 'single') {
      await DB.saveStory(title, '', [
        {'num': 1, 'title': title, 'content': text, 'word_count': wc}
      ]);
    } else if (widget.mode == 'chapter' && widget.story != null) {
      await DB.addChapter(widget.story!['id'] as int, title, text);
    }

    if (mounted) Navigator.pop(context);
    widget.onSaved();
  }

  @override
  Widget build(BuildContext context) {
    final isChap = widget.mode == 'chapter';
    return Padding(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).viewInsets.bottom,
      ),
      child: Container(
        padding: const EdgeInsets.all(16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Handle
            Center(
              child: Container(
                width: 36,
                height: 4,
                decoration: BoxDecoration(
                  color: kBorder,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
            const SizedBox(height: 16),
            Text(
              isChap ? 'Añadir capítulo' : 'Nuevo relato',
              style: const TextStyle(
                  color: kGold,
                  fontSize: 14,
                  fontWeight: FontWeight.bold,
                  letterSpacing: 1.5),
            ),
            if (isChap && widget.story != null) ...[
              const SizedBox(height: 4),
              Text(widget.story!['title'] as String,
                  style:
                      const TextStyle(color: kGoldDim, fontSize: 12)),
            ],
            const SizedBox(height: 12),
            TextField(
              controller: _titleCtrl,
              style: const TextStyle(color: kText),
              decoration: InputDecoration(
                hintText: isChap ? 'Título del capítulo…' : 'Título…',
                hintStyle: const TextStyle(color: kDim),
                filled: true,
                fillColor: kSurface,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(6),
                  borderSide: const BorderSide(color: kBorder),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(6),
                  borderSide: const BorderSide(color: kBorder),
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(6),
                  borderSide: const BorderSide(color: kGold),
                ),
              ),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: _textCtrl,
              onChanged: _onTextChanged,
              maxLines: 8,
              style: const TextStyle(color: kText, fontSize: 13),
              decoration: InputDecoration(
                hintText: 'Mantén pulsado → Pegar…',
                hintStyle: const TextStyle(color: kDim),
                filled: true,
                fillColor: kSurface,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(6),
                  borderSide: const BorderSide(color: kBorder),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(6),
                  borderSide: const BorderSide(color: kBorder),
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(6),
                  borderSide: const BorderSide(color: kGold),
                ),
              ),
            ),
            if (_wordCount > 0) ...[
              const SizedBox(height: 4),
              Text(
                '$_wordCount palabras  ·  ~${(_wordCount / 250).ceil()} min',
                style:
                    const TextStyle(color: kDim, fontSize: 11),
              ),
            ],
            const SizedBox(height: 12),
            Row(children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: () => Navigator.pop(context),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: kMuted,
                    side: const BorderSide(color: kBorder),
                  ),
                  child: const Text('Cancelar'),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                flex: 2,
                child: ElevatedButton(
                  onPressed: _save,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: kGold,
                    foregroundColor: kBg,
                  ),
                  child: const Text('Guardar',
                      style: TextStyle(fontWeight: FontWeight.bold)),
                ),
              ),
            ]),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
  }
}

// ── READER SCREEN ─────────────────────────────────────────────────────────────

class ReaderScreen extends StatefulWidget {
  final Map<String, dynamic> story;
  final List<Map<String, dynamic>> chapters;
  final int initialChap;
  final double initialPct;

  const ReaderScreen({
    super.key,
    required this.story,
    required this.chapters,
    required this.initialChap,
    required this.initialPct,
  });

  @override
  State<ReaderScreen> createState() => _ReaderScreenState();
}

class _ReaderScreenState extends State<ReaderScreen> {
  late int _chapIdx;
  late ScrollController _scroll;
  double _fontSize = 18;
  bool _settingsOpen = false;
  bool _showResume = false;

  @override
  void initState() {
    super.initState();
    _chapIdx = widget.initialChap;
    _fontSize = Settings.fontSize;
    _scroll = ScrollController();
    _scroll.addListener(_onScroll);

    if (widget.initialPct > 0.02) {
      _showResume = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        Future.delayed(const Duration(milliseconds: 500), () {
          if (_scroll.hasClients) {
            _scroll.jumpTo(
                widget.initialPct * _scroll.position.maxScrollExtent);
          }
        });
      });
    }
  }

  @override
  void dispose() {
    _scroll.removeListener(_onScroll);
    _scroll.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (!_scroll.hasClients) return;
    final max = _scroll.position.maxScrollExtent;
    if (max <= 0) return;
    final pct = _scroll.offset / max;
    final chap = widget.chapters[_chapIdx];
    DB.saveProgress(widget.story['id'] as int, chap['id'] as int, pct);
  }

  double get _progressValue {
    if (!_scroll.hasClients || _scroll.position.maxScrollExtent <= 0)
      return 0;
    return (_scroll.offset / _scroll.position.maxScrollExtent).clamp(0.0, 1.0);
  }

  void _goChapter(int delta) {
    final next = _chapIdx + delta;
    if (next < 0 || next >= widget.chapters.length) return;
    final chap = widget.chapters[_chapIdx];
    DB.saveProgress(widget.story['id'] as int, chap['id'] as int, 0);
    setState(() {
      _chapIdx = next;
      _showResume = false;
    });
    _scroll.jumpTo(0);
  }

  String _formatContent(String content) {
    final lines = content
        .split('\n')
        .map((l) => l.trim())
        .where((l) => l.isNotEmpty)
        .toList();
    return lines.join('\n\n');
  }

  @override
  Widget build(BuildContext context) {
    final chap = widget.chapters[_chapIdx];
    final hasMultiChap = widget.chapters.length > 1;
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios, size: 20),
          onPressed: () => Navigator.pop(context),
        ),
        title: Text(
          widget.story['title'] as String,
          style: const TextStyle(fontSize: 14, fontWeight: FontWeight.bold),
          overflow: TextOverflow.ellipsis,
        ),
        actions: [
          if (hasMultiChap) ...[
            IconButton(
              icon: const Icon(Icons.chevron_left),
              onPressed: _chapIdx > 0 ? () => _goChapter(-1) : null,
            ),
            Text('${_chapIdx + 1}/${widget.chapters.length}',
                style: const TextStyle(color: kMuted, fontSize: 12)),
            IconButton(
              icon: const Icon(Icons.chevron_right),
              onPressed: _chapIdx < widget.chapters.length - 1
                  ? () => _goChapter(1)
                  : null,
            ),
          ],
          IconButton(
            icon: const Icon(Icons.text_fields, size: 20),
            onPressed: () =>
                setState(() => _settingsOpen = !_settingsOpen),
          ),
        ],
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(2),
          child: AnimatedBuilder(
            animation: _scroll,
            builder: (ctx, _) => LinearProgressIndicator(
              value: _progressValue,
              backgroundColor: kBorder,
              valueColor: const AlwaysStoppedAnimation<Color>(kGold),
              minHeight: 2,
            ),
          ),
        ),
      ),
      body: Column(
        children: [
          // Resume banner
          if (_showResume)
            MaterialBanner(
              backgroundColor: kGold,
              content: Text(
                '📍 Continuar — ${hasMultiChap ? 'Cap.${_chapIdx + 1} · ' : ''}${((widget.initialPct) * 100).round()}% leído',
                style: const TextStyle(
                    color: kBg, fontWeight: FontWeight.bold),
              ),
              actions: [
                TextButton(
                  onPressed: () => setState(() => _showResume = false),
                  child: const Text('✕',
                      style: TextStyle(color: kBg)),
                ),
              ],
            ),

          // Font size controls
          if (_settingsOpen)
            Container(
              color: kSurface,
              padding: const EdgeInsets.symmetric(
                  horizontal: 16, vertical: 8),
              child: Row(children: [
                const Text('Tamaño',
                    style: TextStyle(color: kMuted, fontSize: 13)),
                const Spacer(),
                IconButton(
                  icon: const Text('A−',
                      style: TextStyle(color: kMuted, fontSize: 14)),
                  onPressed: () {
                    setState(() => _fontSize =
                        (_fontSize - 1).clamp(12.0, 28.0));
                    Settings.fontSize = _fontSize;
                  },
                ),
                Text('${_fontSize.round()}',
                    style: const TextStyle(
                        color: kGold, fontWeight: FontWeight.bold)),
                IconButton(
                  icon: const Text('A+',
                      style: TextStyle(color: kMuted, fontSize: 14)),
                  onPressed: () {
                    setState(() => _fontSize =
                        (_fontSize + 1).clamp(12.0, 28.0));
                    Settings.fontSize = _fontSize;
                  },
                ),
              ]),
            ),

          // Content
          Expanded(
            child: SingleChildScrollView(
              controller: _scroll,
              padding: const EdgeInsets.fromLTRB(20, 20, 20, 40),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Chapter title
                  if (hasMultiChap) ...[
                    Text(
                      'Capítulo ${_chapIdx + 1}',
                      style: TextStyle(
                          color: kGoldDim,
                          fontSize: 11,
                          letterSpacing: 2),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      chap['title'] as String,
                      style: TextStyle(
                          color: kMuted,
                          fontSize: _fontSize * 0.85,
                          fontStyle: FontStyle.italic),
                    ),
                    const Divider(color: kBorder, height: 32),
                  ],

                  // Body
                  Text(
                    _formatContent(chap['content'] as String),
                    style: TextStyle(
                      color: isDark ? kText : kLightText,
                      fontSize: _fontSize,
                      height: 1.85,
                      fontFamily: 'serif',
                    ),
                  ),

                  // Bottom chapter nav
                  if (hasMultiChap) ...[
                    const SizedBox(height: 32),
                    const Divider(color: kBorder),
                    const SizedBox(height: 16),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        if (_chapIdx > 0)
                          OutlinedButton(
                            onPressed: () => _goChapter(-1),
                            style: OutlinedButton.styleFrom(
                              foregroundColor: kMuted,
                              side: const BorderSide(color: kBorder),
                            ),
                            child: const Text('‹ Anterior'),
                          )
                        else
                          const SizedBox(),
                        Text('${_chapIdx + 1} / ${widget.chapters.length}',
                            style: const TextStyle(
                                color: kDim, fontSize: 12)),
                        if (_chapIdx < widget.chapters.length - 1)
                          OutlinedButton(
                            onPressed: () => _goChapter(1),
                            style: OutlinedButton.styleFrom(
                              foregroundColor: kMuted,
                              side: const BorderSide(color: kBorder),
                            ),
                            child: const Text('Siguiente ›'),
                          )
                        else
                          const SizedBox(),
                      ],
                    ),
                  ],
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ── SETTINGS SCREEN ───────────────────────────────────────────────────────────

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  String _theme = Settings.theme;
  double _fontSize = Settings.fontSize;

  void _setTheme(String t) {
    setState(() => _theme = t);
    Settings.theme = t;
    LectoriumApp.of(context)?.setTheme(t);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Ajustes'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios, size: 20),
          onPressed: () => Navigator.pop(context),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // Theme
          const Text('TEMA',
              style: TextStyle(
                  color: kDim, fontSize: 11, letterSpacing: 2)),
          const SizedBox(height: 8),
          Row(children: [
            for (final t in [
              ('dark', '🌙 Oscuro'),
              ('light', '☀️ Claro'),
              ('sepia', '📜 Sepia'),
            ])
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 3),
                  child: OutlinedButton(
                    onPressed: () => _setTheme(t.$1),
                    style: OutlinedButton.styleFrom(
                      backgroundColor:
                          _theme == t.$1 ? kGold : Colors.transparent,
                      foregroundColor: _theme == t.$1 ? kBg : kMuted,
                      side: BorderSide(
                          color: _theme == t.$1 ? kGold : kBorder),
                      padding: const EdgeInsets.symmetric(vertical: 10),
                    ),
                    child: Text(t.$2,
                        style: const TextStyle(fontSize: 12)),
                  ),
                ),
              ),
          ]),

          const SizedBox(height: 24),
          const Text('TAMAÑO DE LETRA',
              style: TextStyle(
                  color: kDim, fontSize: 11, letterSpacing: 2)),
          const SizedBox(height: 8),
          Row(children: [
            IconButton(
              icon: const Text('A−',
                  style: TextStyle(color: kMuted, fontSize: 16)),
              onPressed: () {
                setState(
                    () => _fontSize = (_fontSize - 1).clamp(12.0, 28.0));
                Settings.fontSize = _fontSize;
              },
            ),
            Expanded(
              child: Slider(
                value: _fontSize,
                min: 12,
                max: 28,
                divisions: 16,
                activeColor: kGold,
                inactiveColor: kBorder,
                label: '${_fontSize.round()} sp',
                onChanged: (v) {
                  setState(() => _fontSize = v);
                  Settings.fontSize = v;
                },
              ),
            ),
            IconButton(
              icon: const Text('A+',
                  style: TextStyle(color: kMuted, fontSize: 16)),
              onPressed: () {
                setState(
                    () => _fontSize = (_fontSize + 1).clamp(12.0, 28.0));
                Settings.fontSize = _fontSize;
              },
            ),
            SizedBox(
              width: 40,
              child: Text('${_fontSize.round()}',
                  style: const TextStyle(
                      color: kGold, fontWeight: FontWeight.bold),
                  textAlign: TextAlign.center),
            ),
          ]),

          const SizedBox(height: 8),
          // Preview
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: kSurface,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: kBorder),
            ),
            child: Text(
              'El relato comenzó en una tarde de verano, cuando los rayos del sol atravesaban las persianas y llenaban la habitación de una luz dorada...',
              style: TextStyle(
                  color: kText, fontSize: _fontSize, height: 1.8),
            ),
          ),

          const SizedBox(height: 32),
          const Divider(color: kBorder),
          const SizedBox(height: 16),
          const Center(
            child: Text('Lectorium v1.0',
                style: TextStyle(color: kDim, fontSize: 12)),
          ),
        ],
      ),
    );
  }
}
