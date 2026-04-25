import sys, os, traceback

# Captura de errores al archivo
def save_error():
    err = traceback.format_exc()
    for p in ['/sdcard/Download/crash.txt', '/sdcard/crash.txt']:
        try:
            open(p, 'w').write(err)
            break
        except:
            pass

try:
    from kivy.app import App
    from kivy.uix.label import Label

    class LectoriumApp(App):
        def build(self):
            return Label(text='Lectorium OK')

    LectoriumApp().run()

except Exception:
    save_error()
