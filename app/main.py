import os, sqlite3, traceback
os.environ.setdefault('KIVY_NO_ENV_CONFIG', '1')

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.metrics import dp, sp
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.properties import StringProperty

# ── COLORES ──
BG     = [0.05, 0.04, 0.04, 1]
SURF   = [0.10, 0.09, 0.08, 1]
GOLD   = [0.79, 0.66, 0.30, 1]
TEXT   = [0.91, 0.88, 0.84, 1]
MUTED  = [0.60, 0.56, 0.52, 1]
DIM    = [0.42, 0.38, 0.35, 1]
RED    = [0.55, 0.15, 0.21, 1]

# ── BASE DE DATOS ──
DB = os.path.join(os.path.expanduser('~'), 'lectorium.db')

def init_db():
    c = sqlite3.connect(DB)
    c.executescript("""
        CREATE TABLE IF NOT EXISTS stories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT DEFAULT '',
            rating INTEGER DEFAULT 0,
            added_at INTEGER DEFAULT (strftime('%s','now')),
            word_count INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS chapters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            story_id INTEGER NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
            num INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            word_count INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS progress (
            story_id INTEGER PRIMARY KEY REFERENCES stories(id) ON DELETE CASCADE,
            chapter_id INTEGER,
            scroll_pct REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT
        );
        INSERT OR IGNORE INTO settings VALUES ('theme','dark');
        INSERT OR IGNORE INTO settings VALUES ('font_size','18');
    """)
    c.commit(); c.close()

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def get_stories():
    c = db()
    rows = c.execute("""
        SELECT s.*, COUNT(ch.id) as chap_count,
               p.chapter_id, p.scroll_pct
        FROM stories s
        LEFT JOIN chapters ch ON ch.story_id=s.id
        LEFT JOIN progress p ON p.story_id=s.id
        GROUP BY s.id ORDER BY s.added_at DESC
    """).fetchall()
    c.close()
    return [dict(r) for r in rows]

def get_chapters(sid):
    c = db()
    rows = c.execute("SELECT * FROM chapters WHERE story_id=? ORDER BY num",(sid,)).fetchall()
    c.close()
    return [dict(r) for r in rows]

def save_story(title, category, chapters_data):
    c = db()
    total = sum(len(x[2].split()) for x in chapters_data)
    cur = c.execute("INSERT INTO stories (title,category,word_count) VALUES (?,?,?)",(title,category,total))
    sid = cur.lastrowid
    for num,ctitle,content in chapters_data:
        wc = len(content.split())
        c.execute("INSERT INTO chapters (story_id,num,title,content,word_count) VALUES (?,?,?,?,?)",(sid,num,ctitle,content,wc))
    c.commit(); c.close()

def add_chapter(sid, title, content):
    c = db()
    n = c.execute("SELECT COALESCE(MAX(num),0) FROM chapters WHERE story_id=?",(sid,)).fetchone()[0]
    wc = len(content.split())
    c.execute("INSERT INTO chapters (story_id,num,title,content,word_count) VALUES (?,?,?,?,?)",(sid,n+1,title,content,wc))
    c.execute("UPDATE stories SET word_count=word_count+? WHERE id=?",(wc,sid))
    c.commit(); c.close()

def delete_story(sid):
    c = db()
    c.execute("DELETE FROM stories WHERE id=?",(sid,))
    c.commit(); c.close()

def save_progress(sid, cid, pct):
    c = db()
    c.execute("INSERT OR REPLACE INTO progress VALUES (?,?,?)",(sid,cid,pct))
    c.commit(); c.close()

def get_progress(sid):
    c = db()
    r = c.execute("SELECT chapter_id,scroll_pct FROM progress WHERE story_id=?",(sid,)).fetchone()
    c.close()
    return dict(r) if r else None

# ── PANTALLA BIBLIOTECA ──
class LibraryScreen(Screen):
    def on_enter(self):
        self.refresh()

    def refresh(self):
        self.clear_widgets()
        root = BoxLayout(orientation='vertical')

        # Header
        hdr = BoxLayout(size_hint_y=None, height=dp(56),
                        padding=[dp(16),dp(8)], spacing=dp(8))
        hdr.add_widget(Label(text='LECTORIUM', font_size=sp(20),
                             bold=True, color=GOLD, halign='left',
                             size_hint_x=1))
        cfg = Button(text='⚙', size_hint=(None,None), size=(dp(44),dp(44)),
                     background_normal='', background_color=[0,0,0,0],
                     color=MUTED, font_size=sp(20))
        cfg.bind(on_release=lambda x: setattr(App.get_running_app().sm,'current','settings'))
        hdr.add_widget(cfg)

        # List
        sv = ScrollView()
        gl = GridLayout(cols=1, spacing=dp(2), size_hint_y=None,
                        padding=[dp(8),dp(8)])
        gl.bind(minimum_height=gl.setter('height'))

        stories = get_stories()
        if not stories:
            gl.add_widget(Label(
                text='Tu biblioteca está vacía.\nToca  ＋ Nuevo relato',
                color=MUTED, font_size=sp(14), halign='center',
                size_hint_y=None, height=dp(160)))
        else:
            for s in stories:
                gl.add_widget(self._card(s))

        sv.add_widget(gl)

        # Bottom bar
        bar = BoxLayout(size_hint_y=None, height=dp(60),
                        padding=[dp(8),dp(8)], spacing=dp(8))
        b1 = Button(text='＋ Nuevo relato', background_normal='',
                    background_color=GOLD, color=BG,
                    font_size=sp(14), bold=True)
        b1.bind(on_release=lambda x: self._new_story())
        b2 = Button(text='📚 Serie', background_normal='',
                    background_color=SURF, color=MUTED, font_size=sp(13))
        b2.bind(on_release=lambda x: self._new_series())
        bar.add_widget(b1); bar.add_widget(b2)

        root.add_widget(hdr); root.add_widget(sv); root.add_widget(bar)
        self.add_widget(root)

    def _card(self, s):
        box = BoxLayout(orientation='vertical', size_hint_y=None,
                        height=dp(100), padding=dp(10), spacing=dp(4))
        # Title
        lbl = Label(text=s['title'], font_size=sp(15), bold=True,
                    color=TEXT, halign='left', size_hint_y=None, height=dp(24))
        lbl.bind(size=lambda i,v: setattr(i,'text_size',(v[0],None)))
        # Meta
        chaps = s.get('chap_count',0)
        words = s.get('word_count',0)
        pct = int((s.get('scroll_pct') or 0)*100)
        meta = f"{chaps} cap.  ·  {words:,} pal."
        if pct > 2: meta += f"  ·  📍{pct}%"
        ml = Label(text=meta, font_size=sp(11), color=DIM,
                   halign='left', size_hint_y=None, height=dp(18))
        ml.bind(size=lambda i,v: setattr(i,'text_size',(v[0],None)))
        # Buttons
        brow = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(6))
        ob = Button(text='Leer ›', background_normal='',
                    background_color=GOLD, color=BG,
                    font_size=sp(12), bold=True)
        sid = s['id']
        ob.bind(on_release=lambda x,s=s: self._open(s))
        ab = Button(text='+ Cap.', background_normal='',
                    background_color=SURF, color=MUTED, font_size=sp(11))
        ab.bind(on_release=lambda x,s=s: self._add_chap(s))
        db_ = Button(text='✕', background_normal='',
                     background_color=[0,0,0,0], color=RED,
                     font_size=sp(13), size_hint_x=None, width=dp(36))
        db_.bind(on_release=lambda x,sid=sid: self._delete(sid))
        brow.add_widget(ob); brow.add_widget(ab); brow.add_widget(db_)

        box.add_widget(lbl); box.add_widget(ml); box.add_widget(brow)
        return box

    def _open(self, s):
        app = App.get_running_app()
        app.current_story = s
        app.current_chapters = get_chapters(s['id'])
        prog = get_progress(s['id'])
        if prog:
            app.reader_chap = next((i for i,c in enumerate(app.current_chapters)
                                    if c['id']==prog['chapter_id']),0)
            app.reader_pct = prog['scroll_pct']
        else:
            app.reader_chap = 0; app.reader_pct = 0
        app.sm.get_screen('reader').load()
        app.sm.current = 'reader'

    def _delete(self, sid):
        delete_story(sid); self.refresh()

    def _new_story(self):
        App.get_running_app().paste_dialog(mode='single', cb=self.refresh)

    def _new_series(self):
        App.get_running_app().paste_dialog(mode='series', cb=self.refresh)

    def _add_chap(self, s):
        App.get_running_app().paste_dialog(mode='chapter', story=s, cb=self.refresh)


# ── PANTALLA LECTOR ──
class ReaderScreen(Screen):
    def load(self):
        self.clear_widgets()
        app = App.get_running_app()
        s = app.current_story
        chapters = app.current_chapters
        self.chap_idx = app.reader_chap
        self._sid = s['id']
        self._chapters = chapters
        self._save_ev = None

        root = BoxLayout(orientation='vertical')

        # Header
        hdr = BoxLayout(size_hint_y=None, height=dp(52),
                        padding=[dp(4),dp(4)], spacing=dp(4))
        back = Button(text='‹', size_hint=(None,None), size=(dp(44),dp(44)),
                      background_normal='', background_color=[0,0,0,0],
                      color=MUTED, font_size=sp(26))
        back.bind(on_release=self._back)
        self.title_lbl = Label(text=s['title'], font_size=sp(14),
                               color=TEXT, bold=True, halign='center',
                               shorten=True)
        self.title_lbl.bind(size=lambda i,v: setattr(i,'text_size',v))
        hdr.add_widget(back); hdr.add_widget(self.title_lbl)

        # Scroll
        self.sv = ScrollView(do_scroll_x=False)
        self.sv.bind(scroll_y=self._on_scroll)
        self.body = Label(text='', font_size=sp(18), color=TEXT,
                          halign='left', valign='top',
                          size_hint_y=None, padding=[dp(16),dp(12)])
        self.body.bind(
            width=lambda i,v: setattr(i,'text_size',(v,None)),
            texture_size=lambda i,v: setattr(i,'height',v[1]))
        self.sv.add_widget(self.body)

        # Bottom nav
        self.bnav = BoxLayout(size_hint_y=None, height=dp(48),
                              padding=[dp(8),dp(6)], spacing=dp(8))
        self._build_bnav()

        root.add_widget(hdr)
        root.add_widget(self.sv)
        root.add_widget(self.bnav)
        self.add_widget(root)
        self._render()

        if app.reader_pct > 0.02:
            Clock.schedule_once(lambda dt: setattr(self.sv,'scroll_y',
                                max(0,1-app.reader_pct)), 0.5)

    def _build_bnav(self):
        self.bnav.clear_widgets()
        if len(self._chapters) <= 1: return
        prev = Button(text='‹ Anterior', background_normal='',
                      background_color=SURF, color=MUTED, font_size=sp(12))
        prev.bind(on_release=lambda x: self._go(-1))
        self.ci = Label(text=f"{self.chap_idx+1}/{len(self._chapters)}",
                        color=DIM, font_size=sp(12), halign='center')
        self.ci.bind(size=lambda i,v: setattr(i,'text_size',v))
        nxt = Button(text='Siguiente ›', background_normal='',
                     background_color=SURF, color=MUTED, font_size=sp(12))
        nxt.bind(on_release=lambda x: self._go(1))
        self.bnav.add_widget(prev)
        self.bnav.add_widget(self.ci)
        self.bnav.add_widget(nxt)

    def _render(self):
        if not self._chapters: return
        ch = self._chapters[self.chap_idx]
        lines = [l.strip() for l in ch['content'].split('\n') if l.strip()]
        hdr = f"── {ch['title']} ──\n\n" if len(self._chapters)>1 else ''
        self.body.text = hdr + '\n\n'.join(lines)
        self.sv.scroll_y = 1
        if hasattr(self,'ci'):
            self.ci.text = f"{self.chap_idx+1}/{len(self._chapters)}"

    def _go(self, d):
        n = self.chap_idx + d
        if 0 <= n < len(self._chapters):
            self._save(0)
            self.chap_idx = n
            self._render()
            self.sv.scroll_y = 1

    def _on_scroll(self, inst, val):
        pct = 1.0 - val
        if self._save_ev: self._save_ev.cancel()
        self._save_ev = Clock.schedule_once(lambda dt: self._save(pct), 1.5)

    def _save(self, pct):
        if not self._chapters: return
        ch = self._chapters[self.chap_idx]
        save_progress(self._sid, ch['id'], pct)

    def _back(self, *a):
        pct = 1.0 - self.sv.scroll_y
        self._save(pct)
        App.get_running_app().sm.current = 'library'


# ── PANTALLA AJUSTES ──
class SettingsScreen(Screen):
    def on_enter(self):
        self.clear_widgets()
        root = BoxLayout(orientation='vertical')
        hdr = BoxLayout(size_hint_y=None, height=dp(52),
                        padding=[dp(4),dp(4)])
        back = Button(text='‹', size_hint=(None,None), size=(dp(44),dp(44)),
                      background_normal='', background_color=[0,0,0,0],
                      color=MUTED, font_size=sp(26))
        back.bind(on_release=lambda x: setattr(
            App.get_running_app().sm,'current','library'))
        ttl = Label(text='Ajustes', font_size=sp(17), bold=True,
                    color=TEXT, halign='left')
        ttl.bind(size=lambda i,v: setattr(i,'text_size',v))
        hdr.add_widget(back); hdr.add_widget(ttl)
        content = Label(text='Ajustes — próximamente',
                        color=MUTED, font_size=sp(14))
        root.add_widget(hdr); root.add_widget(content)
        self.add_widget(root)


# ── DIÁLOGO PEGAR ──
class PasteDialog(Popup):
    def __init__(self, mode='single', story=None, cb=None, **kw):
        self.mode = mode; self.story = story; self.cb = cb
        content = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(8))
        self.title_in = TextInput(hint_text='Título…', multiline=False,
                                  size_hint_y=None, height=dp(40),
                                  background_color=SURF,
                                  foreground_color=TEXT, font_size=sp(14))
        self.text_in = TextInput(hint_text='Pega el texto aquí…',
                                 multiline=True,
                                 background_color=SURF,
                                 foreground_color=TEXT, font_size=sp(13))
        btns = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        cancel = Button(text='Cancelar', background_normal='',
                        background_color=SURF, color=MUTED)
        save = Button(text='Guardar', background_normal='',
                      background_color=GOLD, color=BG, bold=True)
        cancel.bind(on_release=self.dismiss)
        save.bind(on_release=self._save)
        btns.add_widget(cancel); btns.add_widget(save)
        content.add_widget(self.title_in)
        content.add_widget(self.text_in)
        content.add_widget(btns)
        super().__init__(title='Nuevo relato' if mode=='single' else
                         ('Nueva serie' if mode=='series' else 'Añadir capítulo'),
                         content=content, size_hint=(0.95,0.88))

    def _save(self, *a):
        text = self.text_in.text.strip()
        if not text: return
        title = self.title_in.text.strip() or text.split('\n')[0][:60]
        if self.mode == 'single':
            save_story(title, '', [(1, title, text)])
        elif self.mode == 'series':
            save_story(title, '', [(1, title, text)])
        else:
            add_chapter(self.story['id'], title, text)
        self.dismiss()
        if self.cb: self.cb()


# ── APP ──
class LectoriumApp(App):
    current_story = None
    current_chapters = []
    reader_chap = 0
    reader_pct = 0.0

    def build(self):
        init_db()
        Window.clearcolor = BG
        self.sm = ScreenManager(transition=SlideTransition())
        self.sm.add_widget(LibraryScreen(name='library'))
        self.sm.add_widget(ReaderScreen(name='reader'))
        self.sm.add_widget(SettingsScreen(name='settings'))
        return self.sm

    def paste_dialog(self, mode='single', story=None, cb=None):
        PasteDialog(mode=mode, story=story, cb=cb).open()

    def on_pause(self): return True

if __name__ == '__main__':
    LectoriumApp().run()
