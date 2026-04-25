"""
Lectorium — Lector de relatos offline
Clon de Article Reader para Android
"""

import os, sqlite3, json, threading
os.environ.setdefault('KIVY_NO_ENV_CONFIG', '1')

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition, NoTransition
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.uix.widget import Widget
from kivy.uix.slider import Slider
from kivy.uix.togglebutton import ToggleButton
from kivy.metrics import dp, sp
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.properties import StringProperty, NumericProperty, BooleanProperty, ListProperty
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.utils import get_color_from_hex
from kivy.core.text import LabelBase
from kivy.animation import Animation

# ── COLORES ──────────────────────────────────────────────────────────────────

THEMES = {
    'dark': {
        'bg':        '#0d0b0a',
        'surface':   '#1a1714',
        'card':      '#211e1b',
        'border':    '#2e2825',
        'gold':      '#c9a84c',
        'gold_dim':  '#8a6e30',
        'text':      '#e8e0d5',
        'text_muted':'#9a8f84',
        'text_dim':  '#6b605a',
        'red':       '#8b2635',
        'accent':    '#c9a84c',
    },
    'light': {
        'bg':        '#f5f0e8',
        'surface':   '#ede8df',
        'card':      '#ffffff',
        'border':    '#d4cfc5',
        'gold':      '#8a6e30',
        'gold_dim':  '#a07840',
        'text':      '#2a2018',
        'text_muted':'#6b5a45',
        'text_dim':  '#9a8a78',
        'red':       '#8b2635',
        'accent':    '#8a6e30',
    },
    'sepia': {
        'bg':        '#f2e8d5',
        'surface':   '#e8dcc5',
        'card':      '#faf4e8',
        'border':    '#c8b898',
        'gold':      '#7a5c2a',
        'gold_dim':  '#9a7840',
        'text':      '#3a2a18',
        'text_muted':'#7a6040',
        'text_dim':  '#a08060',
        'red':       '#8b2635',
        'accent':    '#7a5c2a',
    },
}

def c(hex_color):
    """Convierte hex a lista RGBA para Kivy."""
    hex_color = hex_color.lstrip('#')
    r, g, b = (int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4))
    return [r, g, b, 1]

# ── BASE DE DATOS ─────────────────────────────────────────────────────────────

DB_PATH = os.path.join(os.path.expanduser('~'), 'lectorium.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS stories (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT    NOT NULL,
            category    TEXT    DEFAULT '',
            rating      INTEGER DEFAULT 0,
            added_at    INTEGER DEFAULT (strftime('%s','now')),
            word_count  INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS chapters (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            story_id    INTEGER NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
            num         INTEGER NOT NULL,
            title       TEXT    NOT NULL,
            content     TEXT    NOT NULL,
            word_count  INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS progress (
            story_id    INTEGER PRIMARY KEY REFERENCES stories(id) ON DELETE CASCADE,
            chapter_id  INTEGER,
            scroll_pct  REAL    DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
        INSERT OR IGNORE INTO settings VALUES ('theme',     'dark');
        INSERT OR IGNORE INTO settings VALUES ('font_size', '18');
        INSERT OR IGNORE INTO settings VALUES ('font_name', 'Roboto');
        INSERT OR IGNORE INTO settings VALUES ('tts_speed', '1.0');
    """)
    conn.commit()
    conn.close()

def get_setting(key, default=None):
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row['value'] if row else default

def set_setting(key, value):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, str(value)))
    conn.commit()
    conn.close()

def get_all_stories():
    conn = get_db()
    rows = conn.execute("""
        SELECT s.*, COUNT(c.id) as chap_count,
               p.chapter_id, p.scroll_pct
        FROM stories s
        LEFT JOIN chapters c ON c.story_id = s.id
        LEFT JOIN progress p ON p.story_id = s.id
        GROUP BY s.id
        ORDER BY s.added_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_chapters(story_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM chapters WHERE story_id=? ORDER BY num", (story_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def save_story(title, category, chapters_data):
    """chapters_data: list of (num, title, content)"""
    conn = get_db()
    total_words = sum(len(c[2].split()) for c in chapters_data)
    cur = conn.execute(
        "INSERT INTO stories (title, category, word_count) VALUES (?,?,?)",
        (title, category, total_words)
    )
    story_id = cur.lastrowid
    for num, ctitle, content in chapters_data:
        wc = len(content.split())
        conn.execute(
            "INSERT INTO chapters (story_id, num, title, content, word_count) VALUES (?,?,?,?,?)",
            (story_id, num, ctitle, content, wc)
        )
    conn.commit()
    conn.close()
    return story_id

def add_chapter(story_id, title, content):
    conn = get_db()
    max_num = conn.execute(
        "SELECT COALESCE(MAX(num),0) FROM chapters WHERE story_id=?", (story_id,)
    ).fetchone()[0]
    wc = len(content.split())
    conn.execute(
        "INSERT INTO chapters (story_id, num, title, content, word_count) VALUES (?,?,?,?,?)",
        (story_id, max_num + 1, title, content, wc)
    )
    # Update story word count
    conn.execute(
        "UPDATE stories SET word_count = word_count + ? WHERE id=?", (wc, story_id)
    )
    conn.commit()
    conn.close()

def delete_story(story_id):
    conn = get_db()
    conn.execute("DELETE FROM stories WHERE id=?", (story_id,))
    conn.commit()
    conn.close()

def save_progress(story_id, chapter_id, scroll_pct):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO progress VALUES (?,?,?)",
        (story_id, chapter_id, scroll_pct)
    )
    conn.commit()
    conn.close()

def get_progress(story_id):
    conn = get_db()
    row = conn.execute(
        "SELECT chapter_id, scroll_pct FROM progress WHERE story_id=?", (story_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

# ── WIDGETS BASE ──────────────────────────────────────────────────────────────

class ThemedWidget:
    """Mixin para aplicar el tema activo."""
    def get_theme(self):
        app = App.get_running_app()
        return THEMES.get(app.current_theme, THEMES['dark'])

class RoundedButton(Button):
    def __init__(self, radius=8, **kwargs):
        self.radius = radius
        super().__init__(**kwargs)
        self.background_normal = ''
        self.background_color = [0, 0, 0, 0]
        self.bind(pos=self._draw, size=self._draw)

    def _draw(self, *a):
        self.canvas.before.clear()
        app = App.get_running_app()
        th = THEMES.get(app.current_theme, THEMES['dark'])
        bg = c(th['accent'])
        with self.canvas.before:
            Color(*bg)
            RoundedRectangle(pos=self.pos, size=self.size,
                             radius=[dp(self.radius)])

class CardWidget(BoxLayout):
    def __init__(self, theme_key='card', radius=10, **kwargs):
        self.theme_key = theme_key
        self.radius = radius
        super().__init__(**kwargs)
        self.bind(pos=self._draw, size=self._draw)
        Clock.schedule_once(self._draw)

    def _draw(self, *a):
        self.canvas.before.clear()
        app = App.get_running_app()
        th = THEMES.get(app.current_theme, THEMES['dark'])
        with self.canvas.before:
            Color(*c(th[self.theme_key]))
            RoundedRectangle(pos=self.pos, size=self.size,
                             radius=[dp(self.radius)])

# ── PANTALLA: BIBLIOTECA ──────────────────────────────────────────────────────

class StoryCard(CardWidget):
    def __init__(self, story, on_open, on_delete, on_add_chapter, **kwargs):
        super().__init__(
            orientation='vertical',
            padding=dp(14),
            spacing=dp(6),
            size_hint_y=None,
            height=dp(110),
            **kwargs
        )
        self.story = story
        app = App.get_running_app()
        th = THEMES.get(app.current_theme, THEMES['dark'])

        # Top row: title + delete
        top = BoxLayout(size_hint_y=None, height=dp(28), spacing=dp(8))
        title_lbl = Label(
            text=story['title'],
            font_size=sp(15),
            color=c(th['text']),
            bold=True,
            halign='left',
            valign='middle',
            shorten=True,
            shorten_from='right',
            text_size=(None, dp(28)),
        )
        title_lbl.bind(size=lambda i, v: setattr(i, 'text_size', (v[0], dp(28))))

        del_btn = Button(
            text='✕',
            size_hint=(None, None),
            size=(dp(28), dp(28)),
            background_normal='',
            background_color=c(th['red']) + [0],
            color=c(th['text_dim']),
            font_size=sp(13),
        )
        del_btn.bind(on_release=lambda x: on_delete(story['id']))

        top.add_widget(title_lbl)
        top.add_widget(del_btn)

        # Meta row
        chap_count = story.get('chap_count', 0)
        words = story.get('word_count', 0)
        read_min = max(1, words // 250)
        prog = story.get('scroll_pct', 0) or 0
        prog_pct = int(prog * 100)

        meta_lbl = Label(
            text=f"{chap_count} cap{'.' if chap_count==1 else 's.'}  ·  {words:,} pal.  ·  ~{read_min} min"
                 + (f"  ·  📍 {prog_pct}%" if prog_pct > 2 else ""),
            font_size=sp(11),
            color=c(th['text_dim']),
            halign='left',
            valign='middle',
            size_hint_y=None,
            height=dp(20),
        )
        meta_lbl.bind(size=lambda i, v: setattr(i, 'text_size', (v[0], None)))

        if story.get('category'):
            cat_lbl = Label(
                text=story['category'],
                font_size=sp(10),
                color=c(th['gold_dim']),
                halign='left',
                valign='middle',
                size_hint_y=None,
                height=dp(16),
            )
            cat_lbl.bind(size=lambda i, v: setattr(i, 'text_size', (v[0], None)))
            self.add_widget(cat_lbl)

        # Bottom row: buttons
        btns = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(8))

        open_btn = Button(
            text='Leer  ›',
            background_normal='',
            background_color=c(th['gold']),
            color=c(th['bg']),
            font_size=sp(12),
            bold=True,
            size_hint_x=0.55,
        )
        open_btn.bind(on_release=lambda x: on_open(story))

        add_btn = Button(
            text='+ Cap. TXT',
            background_normal='',
            background_color=c(th['surface']),
            color=c(th['text_muted']),
            font_size=sp(11),
            size_hint_x=0.45,
        )
        add_btn.bind(on_release=lambda x: on_add_chapter(story))

        btns.add_widget(open_btn)
        btns.add_widget(add_btn)

        self.add_widget(top)
        self.add_widget(meta_lbl)
        self.add_widget(btns)


class LibraryScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.build_ui()

    def build_ui(self):
        app = App.get_running_app()
        th = THEMES.get(app.current_theme, THEMES['dark'])
        self.clear_widgets()

        root = BoxLayout(orientation='vertical')

        # Header
        header = BoxLayout(
            size_hint_y=None, height=dp(56),
            padding=[dp(16), 0],
            spacing=dp(8),
        )
        with header.canvas.before:
            Color(*c(th['surface']))
            self._header_rect = Rectangle(pos=header.pos, size=header.size)
        header.bind(pos=lambda i, v: setattr(self._header_rect, 'pos', v),
                    size=lambda i, v: setattr(self._header_rect, 'size', v))

        title = Label(
            text='LECTORIUM',
            font_size=sp(18),
            bold=True,
            color=c(th['gold']),
            halign='left',
        )
        title.bind(size=lambda i, v: setattr(i, 'text_size', v))

        settings_btn = Button(
            text='⚙',
            size_hint=(None, None),
            size=(dp(44), dp(44)),
            background_normal='',
            background_color=[0, 0, 0, 0],
            color=c(th['text_muted']),
            font_size=sp(20),
        )
        settings_btn.bind(on_release=self.open_settings)

        header.add_widget(title)
        header.add_widget(settings_btn)

        # Story list
        scroll = ScrollView()
        self.list_layout = GridLayout(
            cols=1,
            spacing=dp(8),
            padding=[dp(12), dp(12)],
            size_hint_y=None,
        )
        self.list_layout.bind(minimum_height=self.list_layout.setter('height'))
        scroll.add_widget(self.list_layout)

        # FAB area (bottom bar)
        fab_bar = BoxLayout(
            size_hint_y=None, height=dp(64),
            padding=[dp(12), dp(8)],
            spacing=dp(8),
        )
        with fab_bar.canvas.before:
            Color(*c(th['surface']))
            self._fab_rect = Rectangle(pos=fab_bar.pos, size=fab_bar.size)
        fab_bar.bind(pos=lambda i, v: setattr(self._fab_rect, 'pos', v),
                     size=lambda i, v: setattr(self._fab_rect, 'size', v))

        new_btn = Button(
            text='＋ Cargar TXT',
            background_normal='',
            background_color=c(th['gold']),
            color=c(th['bg']),
            font_size=sp(14),
            bold=True,
            size_hint_x=0.5,
        )
        new_btn.bind(on_release=self.open_new_story)

        new_chap_btn = Button(
            text='📚 Serie',
            background_normal='',
            background_color=c(th['surface']),
            color=c(th['text_muted']),
            font_size=sp(12),
            size_hint_x=0.25,
        )
        new_chap_btn.bind(on_release=self.open_new_series)

        paste_btn = Button(
            text='📋 Pegar',
            background_normal='',
            background_color=c(th['surface']),
            color=c(th['text_muted']),
            font_size=sp(12),
            size_hint_x=0.25,
        )
        paste_btn.bind(on_release=lambda x: App.get_running_app().show_paste_dialog(
            mode='single', callback=self.refresh_list))

        fab_bar.add_widget(new_btn)
        fab_bar.add_widget(new_chap_btn)
        fab_bar.add_widget(paste_btn)

        root.add_widget(header)
        root.add_widget(scroll)
        root.add_widget(fab_bar)
        self.add_widget(root)

        Clock.schedule_once(lambda dt: self.refresh_list())

    def refresh_list(self, *a):
        app = App.get_running_app()
        th = THEMES.get(app.current_theme, THEMES['dark'])
        self.list_layout.clear_widgets()
        stories = get_all_stories()

        if not stories:
            empty = Label(
                text='Tu biblioteca está vacía.\nToca  ＋ Nuevo relato  para empezar.',
                color=c(th['text_dim']),
                font_size=sp(14),
                halign='center',
                valign='middle',
                size_hint_y=None,
                height=dp(200),
            )
            empty.bind(size=lambda i, v: setattr(i, 'text_size', v))
            self.list_layout.add_widget(empty)
            return

        for s in stories:
            card = StoryCard(
                story=s,
                on_open=self.open_reader,
                on_delete=self.confirm_delete,
                on_add_chapter=self.open_add_chapter,
            )
            self.list_layout.add_widget(card)

    def open_reader(self, story):
        app = App.get_running_app()
        app.current_story = story
        chapters = get_chapters(story['id'])
        app.current_chapters = chapters
        prog = get_progress(story['id'])
        if prog:
            app.reader_chapter_idx = next(
                (i for i, c in enumerate(chapters) if c['id'] == prog['chapter_id']), 0
            )
            app.reader_scroll_pct = prog['scroll_pct']
        else:
            app.reader_chapter_idx = 0
            app.reader_scroll_pct = 0
        app.sm.transition = SlideTransition(direction='left')
        reader = app.sm.get_screen('reader')
        reader.load_story()
        app.sm.current = 'reader'

    def confirm_delete(self, story_id):
        app = App.get_running_app()
        th = THEMES.get(app.current_theme, THEMES['dark'])

        content = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(12))
        lbl = Label(
            text='¿Eliminar este relato?\nEsta acción no se puede deshacer.',
            color=c(th['text']),
            halign='center',
        )
        lbl.bind(size=lambda i, v: setattr(i, 'text_size', v))
        btns = BoxLayout(spacing=dp(8), size_hint_y=None, height=dp(44))

        popup = Popup(
            title='Eliminar relato',
            content=content,
            size_hint=(0.85, None),
            height=dp(220),
            background_color=c(th['surface']),
            title_color=c(th['text']),
            separator_color=c(th['border']),
        )

        cancel = Button(
            text='Cancelar',
            background_normal='', background_color=c(th['surface']),
            color=c(th['text_muted']),
        )
        cancel.bind(on_release=popup.dismiss)

        ok = Button(
            text='Eliminar',
            background_normal='', background_color=c(th['red']),
            color=[1, 1, 1, 1],
        )
        def do_delete(x):
            delete_story(story_id)
            popup.dismiss()
            self.refresh_list()
        ok.bind(on_release=do_delete)

        btns.add_widget(cancel)
        btns.add_widget(ok)
        content.add_widget(lbl)
        content.add_widget(btns)
        popup.open()

    def open_new_story(self, *a):
        App.get_running_app().show_file_chooser(mode='single', callback=self.refresh_list)

    def open_new_series(self, *a):
        App.get_running_app().show_file_chooser(mode='series', callback=self.refresh_list)

    def open_add_chapter(self, story):
        App.get_running_app().show_file_chooser(mode='chapter', story=story, callback=self.refresh_list)

    def open_settings(self, *a):
        app = App.get_running_app()
        app.sm.transition = SlideTransition(direction='left')
        app.sm.current = 'settings'

# ── PANTALLA: LECTOR ──────────────────────────────────────────────────────────

class ReaderScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._tts_active = False
        self._save_event = None

    def load_story(self):
        app = App.get_running_app()
        th = THEMES.get(app.current_theme, THEMES['dark'])
        self.clear_widgets()

        story = app.current_story
        chapters = app.current_chapters
        self.chap_idx = app.reader_chapter_idx
        self._story_id = story['id']

        root = BoxLayout(orientation='vertical')

        # Header
        header = BoxLayout(
            size_hint_y=None,
