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
            size_hint_y=None, height=dp(56),
            padding=[dp(4), 0, dp(8), 0],
            spacing=dp(4),
        )
        with header.canvas.before:
            Color(*c(th['surface']))
            self._hdr_rect = Rectangle(pos=header.pos, size=header.size)
        header.bind(pos=lambda i, v: setattr(self._hdr_rect, 'pos', v),
                    size=lambda i, v: setattr(self._hdr_rect, 'size', v))

        back_btn = Button(
            text='‹',
            size_hint=(None, None),
            size=(dp(44), dp(44)),
            background_normal='',
            background_color=[0, 0, 0, 0],
            color=c(th['text_muted']),
            font_size=sp(24),
        )
        back_btn.bind(on_release=self.go_back)

        self.title_lbl = Label(
            text=story['title'],
            font_size=sp(14),
            color=c(th['text']),
            halign='center',
            valign='middle',
            shorten=True,
            bold=True,
        )
        self.title_lbl.bind(size=lambda i, v: setattr(i, 'text_size', v))

        # Chapter nav (only if multiple chapters)
        self.chap_nav = BoxLayout(size_hint=(None, None), size=(dp(88), dp(44)), spacing=dp(2))
        if len(chapters) > 1:
            prev_btn = Button(
                text='‹',
                size_hint=(None, None),
                size=(dp(36), dp(36)),
                background_normal='',
                background_color=c(th['surface']),
                color=c(th['gold']),
                font_size=sp(18),
            )
            prev_btn.bind(on_release=lambda x: self.change_chapter(-1))

            next_btn = Button(
                text='›',
                size_hint=(None, None),
                size=(dp(36), dp(36)),
                background_normal='',
                background_color=c(th['surface']),
                color=c(th['gold']),
                font_size=sp(18),
            )
            next_btn.bind(on_release=lambda x: self.change_chapter(1))
            self.chap_nav.add_widget(prev_btn)
            self.chap_nav.add_widget(next_btn)

        tts_btn = Button(
            text='▶',
            size_hint=(None, None),
            size=(dp(44), dp(44)),
            background_normal='',
            background_color=[0, 0, 0, 0],
            color=c(th['text_muted']),
            font_size=sp(16),
        )
        tts_btn.bind(on_release=self.toggle_tts)
        self._tts_btn = tts_btn

        header.add_widget(back_btn)
        header.add_widget(self.title_lbl)
        header.add_widget(self.chap_nav)
        header.add_widget(tts_btn)

        # Progress bar
        self.prog_bar = Widget(size_hint_y=None, height=dp(2))
        with self.prog_bar.canvas:
            Color(*c(th['border']))
            self._prog_bg = Rectangle(pos=self.prog_bar.pos, size=self.prog_bar.size)
            Color(*c(th['gold']))
            self._prog_fg = Rectangle(pos=self.prog_bar.pos, size=(0, dp(2)))
        self.prog_bar.bind(pos=self._update_prog_pos, size=self._update_prog_pos)

        # Reading area
        self.scroll = ScrollView(do_scroll_x=False)
        self.scroll.bind(scroll_y=self._on_scroll)

        self.text_lbl = Label(
            text='',
            font_size=sp(int(get_setting('font_size', 18))),
            color=c(th['text']),
            halign='left',
            valign='top',
            markup=False,
            size_hint_y=None,
            padding=[dp(20), dp(16)],
        )
        self.text_lbl.bind(
            width=lambda i, v: setattr(i, 'text_size', (v, None)),
            texture_size=lambda i, v: setattr(i, 'height', v[1]),
        )
        self.scroll.add_widget(self.text_lbl)

        # Bottom chapter nav
        self.bottom_nav = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8), padding=[dp(12), dp(8)])
        with self.bottom_nav.canvas.before:
            Color(*c(th['surface']))
            self._bn_rect = Rectangle(pos=self.bottom_nav.pos, size=self.bottom_nav.size)
        self.bottom_nav.bind(
            pos=lambda i, v: setattr(self._bn_rect, 'pos', v),
            size=lambda i, v: setattr(self._bn_rect, 'size', v),
        )
        self._build_bottom_nav(chapters)

        root.add_widget(header)
        root.add_widget(self.prog_bar)
        root.add_widget(self.scroll)
        root.add_widget(self.bottom_nav)
        self.add_widget(root)

        self._chapters = chapters
        self._render_chapter()

        # Restore scroll position
        if app.reader_scroll_pct and app.reader_scroll_pct > 0.02:
            Clock.schedule_once(lambda dt: self._restore_scroll(app.reader_scroll_pct), 0.4)

    def _build_bottom_nav(self, chapters):
        app = App.get_running_app()
        th = THEMES.get(app.current_theme, THEMES['dark'])
        self.bottom_nav.clear_widgets()
        if len(chapters) <= 1:
            return
        prev = Button(
            text='‹ Anterior',
            background_normal='', background_color=c(th['surface']),
            color=c(th['text_muted']), font_size=sp(12),
        )
        prev.bind(on_release=lambda x: self.change_chapter(-1))

        self.chap_indicator = Label(
            text=f"{self.chap_idx + 1} / {len(chapters)}",
            color=c(th['text_dim']),
            font_size=sp(12),
            halign='center',
        )
        self.chap_indicator.bind(size=lambda i, v: setattr(i, 'text_size', v))

        nxt = Button(
            text='Siguiente ›',
            background_normal='', background_color=c(th['surface']),
            color=c(th['text_muted']), font_size=sp(12),
        )
        nxt.bind(on_release=lambda x: self.change_chapter(1))

        self.bottom_nav.add_widget(prev)
        self.bottom_nav.add_widget(self.chap_indicator)
        self.bottom_nav.add_widget(nxt)

    def _render_chapter(self):
        app = App.get_running_app()
        if not self._chapters:
            return
        chap = self._chapters[self.chap_idx]
        # Format paragraphs
        lines = [l.strip() for l in chap['content'].split('\n') if l.strip()]
        text = '\n\n'.join(lines)
        header = f"── {chap['title']} ──\n\n" if len(self._chapters) > 1 else ''
        self.text_lbl.text = header + text
        self.scroll.scroll_y = 1
        self._update_prog(0)
        if hasattr(self, 'chap_indicator'):
            self.chap_indicator.text = f"{self.chap_idx + 1} / {len(self._chapters)}"
        self.title_lbl.text = App.get_running_app().current_story['title']

    def change_chapter(self, delta):
        new_idx = self.chap_idx + delta
        if 0 <= new_idx < len(self._chapters):
            self._save_progress(0)
            self.chap_idx = new_idx
            self._render_chapter()

    def _on_scroll(self, instance, value):
        # scroll_y: 1=top, 0=bottom → invert for progress
        pct = 1.0 - value
        self._update_prog(pct)
        # Debounce save
        if self._save_event:
            self._save_event.cancel()
        self._save_event = Clock.schedule_once(lambda dt: self._save_progress(pct), 1.5)

    def _save_progress(self, pct):
        if not self._chapters:
            return
        chap = self._chapters[self.chap_idx]
        save_progress(self._story_id, chap['id'], pct)

    def _restore_scroll(self, pct):
        self.scroll.scroll_y = max(0, min(1, 1.0 - pct))

    def _update_prog(self, pct):
        w = self.prog_bar.width * pct
        self._prog_fg.size = (w, dp(2))

    def _update_prog_pos(self, *a):
        self._prog_bg.pos = self.prog_bar.pos
        self._prog_bg.size = self.prog_bar.size
        pct = 1.0 - self.scroll.scroll_y
        self._prog_fg.pos = self.prog_bar.pos
        self._prog_fg.size = (self.prog_bar.width * pct, dp(2))

    def toggle_tts(self, *a):
        """Text-to-speech usando Android TTS vía pyjnius."""
        try:
            from jnius import autoclass
            if not self._tts_active:
                self._tts_active = True
                self._tts_btn.text = '⏹'
                TextToSpeech = autoclass('android.speech.tts.TextToSpeech')
                Context = autoclass('android.content.Context')
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                ctx = PythonActivity.mActivity
                text = self.text_lbl.text[:4000]  # TTS limit
                # Init TTS and speak
                def _speak(tts_instance, status):
                    if status == 0:  # SUCCESS
                        tts_instance.speak(text, 0, None, None)
                tts = TextToSpeech(ctx, _speak)
                self._tts_instance = tts
            else:
                self._tts_active = False
                self._tts_btn.text = '▶'
                if hasattr(self, '_tts_instance'):
                    self._tts_instance.stop()
        except Exception:
            # TTS not available (desktop testing)
            pass

    def go_back(self, *a):
        pct = 1.0 - self.scroll.scroll_y
        self._save_progress(pct)
        app = App.get_running_app()
        app.sm.transition = SlideTransition(direction='right')
        app.sm.current = 'library'
        app.sm.get_screen('library').refresh_list()

# ── PANTALLA: AJUSTES ─────────────────────────────────────────────────────────

class SettingsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.build_ui()

    def build_ui(self):
        app = App.get_running_app()
        th = THEMES.get(app.current_theme, THEMES['dark'])
        self.clear_widgets()

        root = BoxLayout(orientation='vertical')

        # Header
        header = BoxLayout(size_hint_y=None, height=dp(56), padding=[dp(4), 0, dp(16), 0])
        with header.canvas.before:
            Color(*c(th['surface']))
            self._hdr_rect = Rectangle(pos=header.pos, size=header.size)
        header.bind(pos=lambda i, v: setattr(self._hdr_rect, 'pos', v),
                    size=lambda i, v: setattr(self._hdr_rect, 'size', v))

        back_btn = Button(
            text='‹',
            size_hint=(None, None), size=(dp(44), dp(44)),
            background_normal='', background_color=[0, 0, 0, 0],
            color=c(th['text_muted']), font_size=sp(24),
        )
        back_btn.bind(on_release=self.go_back)

        ttl = Label(text='Ajustes', font_size=sp(17), bold=True, color=c(th['text']), halign='left')
        ttl.bind(size=lambda i, v: setattr(i, 'text_size', v))

        header.add_widget(back_btn)
        header.add_widget(ttl)

        # Content
        scroll = ScrollView()
        content = GridLayout(
            cols=1, spacing=dp(4),
            padding=[dp(16), dp(12)],
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter('height'))

        # ── TEMA ──
        content.add_widget(self._section_label('Tema', th))

        themes_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        for theme_id, label in [('dark','Oscuro'),('light','Claro'),('sepia','Sepia')]:
            btn = Button(
                text=label,
                background_normal='',
                background_color=c(th['gold']) if app.current_theme == theme_id else c(th['surface']),
                color=c(th['bg']) if app.current_theme == theme_id else c(th['text_muted']),
                font_size=sp(13),
            )
            tid = theme_id
            btn.bind(on_release=lambda x, t=tid: self.set_theme(t))
            themes_row.add_widget(btn)
        content.add_widget(themes_row)

        # ── TAMAÑO DE FUENTE ──
        content.add_widget(self._section_label('Tamaño de letra', th))
        font_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))

        current_size = int(get_setting('font_size', 18))
        self.font_size_lbl = Label(
            text=str(current_size),
            color=c(th['gold']),
            font_size=sp(16),
            bold=True,
            size_hint=(None, None),
            size=(dp(40), dp(44)),
            halign='center',
        )
        self.font_size_lbl.bind(size=lambda i, v: setattr(i, 'text_size', v))

        for delta, label in [(-2,'A−'), (+2,'A+')]:
            btn = Button(
                text=label,
                background_normal='', background_color=c(th['surface']),
                color=c(th['text_muted']), font_size=sp(14),
            )
            d = delta
            btn.bind(on_release=lambda x, d=d: self.change_font_size(d))
            if delta < 0:
                font_row.add_widget(btn)
                font_row.add_widget(self.font_size_lbl)
            else:
                font_row.add_widget(btn)
        content.add_widget(font_row)

        # ── PREVIEW ──
        content.add_widget(self._section_label('Vista previa', th))
        self.preview_lbl = Label(
            text='El relato comenzó en una tarde de verano, cuando los rayos del sol atravesaban las persianas...',
            font_size=sp(current_size),
            color=c(th['text']),
            halign='left',
            valign='top',
            size_hint_y=None,
            height=dp(80),
        )
        self.preview_lbl.bind(size=lambda i, v: setattr(i, 'text_size', (v[0], None)),
                              texture_size=lambda i, v: setattr(i, 'height', max(dp(80), v[1])))
        content.add_widget(self.preview_lbl)

        scroll.add_widget(content)
        root.add_widget(header)
        root.add_widget(scroll)
        self.add_widget(root)

    def _section_label(self, text, th):
        lbl = Label(
            text=text.upper(),
            font_size=sp(10),
            color=c(th['text_dim']),
            halign='left',
            size_hint_y=None,
            height=dp(32),
            bold=True,
        )
        lbl.bind(size=lambda i, v: setattr(i, 'text_size', v))
        return lbl

    def set_theme(self, theme_id):
        app = App.get_running_app()
        app.current_theme = theme_id
        set_setting('theme', theme_id)
        self.build_ui()
        app.sm.get_screen('library').build_ui()

    def change_font_size(self, delta):
        current = int(get_setting('font_size', 18))
        new_size = max(12, min(28, current + delta))
        set_setting('font_size', new_size)
        self.font_size_lbl.text = str(new_size)
        self.preview_lbl.font_size = sp(new_size)

    def go_back(self, *a):
        app = App.get_running_app()
        app.sm.transition = SlideTransition(direction='right')
        app.sm.current = 'library'

# ── DIÁLOGOS ──────────────────────────────────────────────────────────────────

class PasteDialog(Popup):
    """Diálogo para pegar texto de un relato o capítulo."""
    def __init__(self, mode='single', story=None, callback=None, **kwargs):
        self.mode = mode
        self.story = story
        self.callback = callback
        app = App.get_running_app()
        th = THEMES.get(app.current_theme, THEMES['dark'])

        title_text = 'Nuevo relato' if mode == 'single' else f'Añadir capítulo'

        content = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(4))

        # Title input
        if mode == 'single':
            title_hint = Label(
                text='TÍTULO', font_size=sp(10), color=c(th['text_dim']),
                halign='left', size_hint_y=None, height=dp(22),
            )
            title_hint.bind(size=lambda i, v: setattr(i, 'text_size', v))
            self.title_input = TextInput(
                hint_text='Título del relato…',
                multiline=False,
                size_hint_y=None, height=dp(40),
                background_color=c(th['surface']),
                foreground_color=c(th['text']),
                hint_text_color=c(th['text_dim']),
                font_size=sp(14),
                padding=[dp(8), dp(8)],
            )
            content.add_widget(title_hint)
            content.add_widget(self.title_input)
        else:
            chap_label = Label(
                text=f"Añadiendo capítulo a:\n{story['title']}",
                color=c(th['gold_dim']),
                font_size=sp(13),
                halign='center',
                size_hint_y=None, height=dp(36),
            )
            chap_label.bind(size=lambda i, v: setattr(i, 'text_size', v))
            content.add_widget(chap_label)

            title_hint2 = Label(
                text='TÍTULO DEL CAPÍTULO', font_size=sp(10), color=c(th['text_dim']),
                halign='left', size_hint_y=None, height=dp(22),
            )
            title_hint2.bind(size=lambda i, v: setattr(i, 'text_size', v))
            self.title_input = TextInput(
                hint_text='Ej: Capítulo 1, Parte II…',
                multiline=False,
                size_hint_y=None, height=dp(40),
                background_color=c(th['surface']),
                foreground_color=c(th['text']),
                hint_text_color=c(th['text_dim']),
                font_size=sp(14),
                padding=[dp(8), dp(8)],
            )
            content.add_widget(title_hint2)
            content.add_widget(self.title_input)

        # Text area
        text_hint = Label(
            text='PEGA EL TEXTO AQUÍ', font_size=sp(10), color=c(th['text_dim']),
            halign='left', size_hint_y=None, height=dp(22),
        )
        text_hint.bind(size=lambda i, v: setattr(i, 'text_size', v))

        self.text_input = TextInput(
            hint_text='Mantén pulsado → Pegar…',
            multiline=True,
            background_color=c(th['surface']),
            foreground_color=c(th['text']),
            hint_text_color=c(th['text_dim']),
            font_size=sp(13),
            padding=[dp(8), dp(8)],
        )
        self.text_input.bind(text=self._on_text_change)

        self.wc_label = Label(
            text='',
            color=c(th['text_dim']),
            font_size=sp(11),
            halign='right',
            size_hint_y=None, height=dp(20),
        )
        self.wc_label.bind(size=lambda i, v: setattr(i, 'text_size', v))

        # Buttons
        btns = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        cancel_btn = Button(
            text='Cancelar',
            background_normal='', background_color=c(th['surface']),
            color=c(th['text_muted']), font_size=sp(14),
        )
        save_btn = Button(
            text='Guardar',
            background_normal='', background_color=c(th['gold']),
            color=c(th['bg']), font_size=sp(14), bold=True,
        )
        cancel_btn.bind(on_release=self.dismiss)
        save_btn.bind(on_release=self.save)

        btns.add_widget(cancel_btn)
        btns.add_widget(save_btn)

        content.add_widget(text_hint)
        content.add_widget(self.text_input)
        content.add_widget(self.wc_label)
        content.add_widget(btns)

        super().__init__(
            title=title_text,
            content=content,
            size_hint=(0.95, 0.88),
            background_color=c(th['card']),
            title_color=c(th['text']),
            separator_color=c(th['border']),
            **kwargs
        )

    def _on_text_change(self, instance, value):
        wc = len(value.split()) if value.strip() else 0
        rt = max(1, wc // 250)
        self.wc_label.text = f"{wc:,} palabras · ~{rt} min" if wc > 0 else ''

    def save(self, *a):
        text = self.text_input.text.strip()
        if not text:
            return
        title = self.title_input.text.strip()

        if self.mode == 'single':
            if not title:
                # Use first line as title
                title = text.split('\n')[0][:60].strip() or 'Relato sin título'
            save_story(title, '', [(1, title, text)])
        else:
            chap_title = title or f"Capítulo {self.story.get('chap_count', 0) + 1}"
            add_chapter(self.story['id'], chap_title, text)

        self.dismiss()
        if self.callback:
            self.callback()


class SeriesDialog(Popup):
    """Diálogo para crear un relato por capítulos (pegando uno a uno)."""
    def __init__(self, callback=None, **kwargs):
        self.callback = callback
        self._chapters = []
        app = App.get_running_app()
        th = THEMES.get(app.current_theme, THEMES['dark'])

        content = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(4))

        # Series title
        title_hint = Label(
            text='TÍTULO DEL RELATO', font_size=sp(10), color=c(th['text_dim']),
            halign='left', size_hint_y=None, height=dp(22),
        )
        title_hint.bind(size=lambda i, v: setattr(i, 'text_size', v))
        self.series_title = TextInput(
            hint_text='Nombre del relato completo…',
            multiline=False,
            size_hint_y=None, height=dp(40),
            background_color=c(th['surface']),
            foreground_color=c(th['text']),
            hint_text_color=c(th['text_dim']),
            font_size=sp(14),
            padding=[dp(8), dp(8)],
        )

        # Chapter list
        self.chap_list_label = Label(
            text='Capítulos: 0',
            color=c(th['gold_dim']),
            font_size=sp(12),
            halign='left',
            size_hint_y=None, height=dp(24),
        )
        self.chap_list_label.bind(size=lambda i, v: setattr(i, 'text_size', v))

        scroll = ScrollView(size_hint_y=0.3)
        self.chap_list_layout = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        self.chap_list_layout.bind(minimum_height=self.chap_list_layout.setter('height'))
        scroll.add_widget(self.chap_list_layout)

        # Add chapter area
        add_hint = Label(
            text='PEGAR CAPÍTULO', font_size=sp(10), color=c(th['text_dim']),
            halign='left', size_hint_y=None, height=dp(22),
        )
        add_hint.bind(size=lambda i, v: setattr(i, 'text_size', v))

        chap_row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8))
        self.chap_title_input = TextInput(
            hint_text='Título del capítulo…',
            multiline=False,
            background_color=c(th['surface']),
            foreground_color=c(th['text']),
            hint_text_color=c(th['text_dim']),
            font_size=sp(13),
            padding=[dp(8), dp(8)],
        )
        chap_row.add_widget(self.chap_title_input)

        self.chap_text = TextInput(
            hint_text='Pega el texto del capítulo aquí…',
            multiline=True,
            size_hint_y=None, height=dp(100),
            background_color=c(th['surface']),
            foreground_color=c(th['text']),
            hint_text_color=c(th['text_dim']),
            font_size=sp(12),
            padding=[dp(8), dp(8)],
        )

        add_chap_btn = Button(
            text='＋ Añadir este capítulo',
            background_normal='', background_color=c(th['surface']),
            color=c(th['gold']), font_size=sp(13),
            size_hint_y=None, height=dp(38),
        )
        add_chap_btn.bind(on_release=self.add_chapter_to_list)

        # Bottom buttons
        btns = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        cancel_btn = Button(
            text='Cancelar',
            background_normal='', background_color=c(th['surface']),
            color=c(th['text_muted']), font_size=sp(14),
        )
        save_btn = Button(
            text='Crear relato',
            background_normal='', background_color=c(th['gold']),
            color=c(th['bg']), font_size=sp(14), bold=True,
        )
        cancel_btn.bind(on_release=self.dismiss)
        save_btn.bind(on_release=self.save_series)
        btns.add_widget(cancel_btn)
        btns.add_widget(save_btn)

        content.add_widget(title_hint)
        content.add_widget(self.series_title)
        content.add_widget(self.chap_list_label)
        content.add_widget(scroll)
        content.add_widget(add_hint)
        content.add_widget(chap_row)
        content.add_widget(self.chap_text)
        content.add_widget(add_chap_btn)
        content.add_widget(btns)

        super().__init__(
            title='Relato por capítulos',
            content=content,
            size_hint=(0.95, 0.92),
            background_color=c(th['card']),
            title_color=c(th['text']),
            separator_color=c(th['border']),
            **kwargs
        )

    def add_chapter_to_list(self, *a):
        text = self.chap_text.text.strip()
        if not text:
            return
        app = App.get_running_app()
        th = THEMES.get(app.current_theme, THEMES['dark'])
        num = len(self._chapters) + 1
        title = self.chap_title_input.text.strip() or f"Capítulo {num}"
        self._chapters.append((num, title, text))

        # Show in list
        wc = len(text.split())
        row = Label(
            text=f"Cap. {num}: {title}  ({wc:,} pal.)",
            color=c(th['gold_dim']),
            font_size=sp(12),
            halign='left',
            size_hint_y=None, height=dp(28),
        )
        row.bind(size=lambda i, v: setattr(i, 'text_size', v))
        self.chap_list_layout.add_widget(row)
        self.chap_list_label.text = f"Capítulos: {len(self._chapters)}"

        self.chap_text.text = ''
        self.chap_title_input.text = ''

    def save_series(self, *a):
        if not self._chapters:
            return
        title = self.series_title.text.strip() or self._chapters[0][1]
        save_story(title, '', self._chapters)
        self.dismiss()
        if self.callback:
            self.callback()

# ── SELECTOR DE ARCHIVOS TXT ──────────────────────────────────────────────────

class FileChooserPopup(Popup):
    """
    Selector de archivos TXT nativo de Kivy.
    - mode='single'  → carga un TXT como relato nuevo
    - mode='series'  → carga múltiples TXT como capítulos de un relato nuevo
    - mode='chapter' → añade TXT(s) como capítulos a un relato existente
    """
    def __init__(self, mode='single', story=None, callback=None, **kwargs):
        self.mode = mode
        self.story = story
        self.callback = callback
        app = App.get_running_app()
        th = THEMES.get(app.current_theme, THEMES['dark'])

        from kivy.uix.filechooser import FileChooserListView

        content = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(8))

        # Título informativo
        mode_labels = {
            'single':  'Selecciona un TXT',
            'series':  'Selecciona los TXT (uno o varios capítulos)',
            'chapter': f"Añadir capítulo(s) a: {story['title'] if story else ''}",
        }
        info = Label(
            text=mode_labels[mode],
            color=c(th['text_muted']),
            font_size=sp(13),
            size_hint_y=None,
            height=dp(32),
            halign='left',
        )
        info.bind(size=lambda i, v: setattr(i, 'text_size', v))

        # Selector de archivos — arranca en /sdcard para acceso fácil
        start_path = '/sdcard'
        if not os.path.exists(start_path):
            start_path = os.path.expanduser('~')

        multiselect = (mode in ('series', 'chapter'))

        self.chooser = FileChooserListView(
            path=start_path,
            filters=['*.txt', '*.TXT'],
            multiselect=multiselect,
            dirselect=False,
        )
        # Estilo mínimo del chooser
        self.chooser.background_color = c(th['surface'])

        # Campo de título (solo para relato nuevo individual)
        self.title_input = None
        if mode == 'single':
            row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8))
            lbl = Label(
                text='Título:',
                color=c(th['text_dim']),
                font_size=sp(12),
                size_hint=(None, None),
                size=(dp(50), dp(40)),
                halign='right',
            )
            lbl.bind(size=lambda i, v: setattr(i, 'text_size', v))
            self.title_input = TextInput(
                hint_text='(se usa el nombre del archivo si se deja vacío)',
                multiline=False,
                background_color=c(th['surface']),
                foreground_color=c(th['text']),
                hint_text_color=c(th['text_dim']),
                font_size=sp(13),
                padding=[dp(8), dp(8)],
            )
            row.add_widget(lbl)
            row.add_widget(self.title_input)
            content.add_widget(row)

        # Nombre de la serie (solo para mode='series')
        self.series_input = None
        if mode == 'series':
            row2 = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8))
            lbl2 = Label(
                text='Título serie:',
                color=c(th['text_dim']),
                font_size=sp(12),
                size_hint=(None, None),
                size=(dp(80), dp(40)),
                halign='right',
            )
            lbl2.bind(size=lambda i, v: setattr(i, 'text_size', v))
            self.series_input = TextInput(
                hint_text='Título del relato completo…',
                multiline=False,
                background_color=c(th['surface']),
                foreground_color=c(th['text']),
                hint_text_color=c(th['text_dim']),
                font_size=sp(13),
                padding=[dp(8), dp(8)],
            )
            row2.add_widget(lbl2)
            row2.add_widget(self.series_input)
            content.add_widget(row2)

        # Botones
        btns = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))

        cancel_btn = Button(
            text='Cancelar',
            background_normal='', background_color=c(th['surface']),
            color=c(th['text_muted']), font_size=sp(14),
        )
        cancel_btn.bind(on_release=self.dismiss)

        load_btn = Button(
            text='Cargar',
            background_normal='', background_color=c(th['gold']),
            color=c(th['bg']), font_size=sp(14), bold=True,
        )
        load_btn.bind(on_release=self.load_files)

        btns.add_widget(cancel_btn)
        btns.add_widget(load_btn)

        content.add_widget(info)
        content.add_widget(self.chooser)
        content.add_widget(btns)

        super().__init__(
            title='Cargar TXT',
            content=content,
            size_hint=(0.95, 0.9),
            background_color=c(th['card']),
            title_color=c(th['text']),
            separator_color=c(th['border']),
            **kwargs
        )

    def _read_txt(self, path):
        """Lee un archivo TXT con detección de encoding."""
        for enc in ('utf-8', 'utf-8-sig', 'latin-1', 'cp1252'):
            try:
                with open(path, 'r', encoding=enc) as f:
                    return f.read()
            except (UnicodeDecodeError, OSError):
                continue
        return ''

    def _name_from_path(self, path):
        """Extrae nombre limpio del nombre de archivo."""
        base = os.path.basename(path)
        name = os.path.splitext(base)[0]
        # Quitar prefijo numérico tipo "01 - ", "Cap01_"
        import re
        name = re.sub(r'^[\d]+[\s\.\-_]+', '', name)
        return name.replace('_', ' ').replace('-', ' ').strip() or base

    def _natural_sort_key(self, path):
        """Ordena por número natural (Cap1 < Cap2 < Cap10)."""
        import re
        name = os.path.basename(path)
        parts = re.split(r'(\d+)', name)
        return [int(p) if p.isdigit() else p.lower() for p in parts]

    def load_files(self, *a):
        selected = self.chooser.selection
        if not selected:
            return

        # Ordenar por nombre natural
        selected = sorted(selected, key=self._natural_sort_key)

        if self.mode == 'single':
            path = selected[0]
            content = self._read_txt(path)
            if not content:
                return
            title = (self.title_input.text.strip()
                     if self.title_input else '') or self._name_from_path(path)
            save_story(title, '', [(1, title, content)])
            self.dismiss()
            if self.callback:
                self.callback()

        elif self.mode == 'series':
            chapters_data = []
            for i, path in enumerate(selected, 1):
                content = self._read_txt(path)
                if content:
                    chap_title = self._name_from_path(path)
                    chapters_data.append((i, chap_title, content))
            if not chapters_data:
                return
            # Título de la serie
            series_title = (self.series_input.text.strip()
                            if self.series_input else '')
            if not series_title:
                # Intentar prefijo común de los nombres de archivo
                names = [self._name_from_path(p) for p in selected]
                series_title = _common_prefix(names) or self._name_from_path(selected[0])
            save_story(series_title, '', chapters_data)
            self.dismiss()
            if self.callback:
                self.callback()

        elif self.mode == 'chapter':
            for path in selected:
                content = self._read_txt(path)
                if content:
                    chap_title = self._name_from_path(path)
                    add_chapter(self.story['id'], chap_title, content)
            self.dismiss()
            if self.callback:
                self.callback()


def _common_prefix(strings):
    """Prefijo común de una lista de strings."""
    if not strings:
        return ''
    prefix = strings[0]
    for s in strings[1:]:
        while not s.startswith(prefix):
            prefix = prefix[:-1]
            if not prefix:
                return ''
    return prefix.strip(' -_')


# ── APP PRINCIPAL ─────────────────────────────────────────────────────────────

class LectoriumApp(App):
    current_theme = StringProperty('dark')
    current_story = None
    current_chapters = []
    reader_chapter_idx = 0
    reader_scroll_pct = 0.0

    def build(self):
        init_db()
        self.current_theme = get_setting('theme', 'dark')
        th = THEMES.get(self.current_theme, THEMES['dark'])
        Window.clearcolor = c(th['bg'])

        self.sm = ScreenManager(transition=SlideTransition())
        self.sm.add_widget(LibraryScreen(name='library'))
        self.sm.add_widget(ReaderScreen(name='reader'))
        self.sm.add_widget(SettingsScreen(name='settings'))
        self.sm.current = 'library'
        return self.sm

    def show_file_chooser(self, mode='single', story=None, callback=None):
        dlg = FileChooserPopup(mode=mode, story=story, callback=callback)
        dlg.open()

    def show_paste_dialog(self, mode='single', story=None, callback=None):
        dlg = PasteDialog(mode=mode, story=story, callback=callback)
        dlg.open()

    def show_series_dialog(self, callback=None):
        dlg = SeriesDialog(callback=callback)
        dlg.open()

    def on_pause(self):
        return True  # Mantener estado en background

    def on_resume(self):
        pass


if __name__ == '__main__':
    LectoriumApp().run()


# Sobrescribir el bloque principal con captura de errores
import sys
_original_excepthook = sys.excepthook
def _crash_handler(exc_type, exc_value, exc_tb):
    import traceback
    error = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    for path in ['/sdcard/lectorium_crash.txt', '/sdcard/Download/lectorium_crash.txt']:
        try:
            with open(path, 'w') as f:
                f.write(error)
            break
        except:
            pass
    _original_excepthook(exc_type, exc_value, exc_tb)
sys.excepthook = _crash_handler
