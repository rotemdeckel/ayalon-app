"""
איילון ביטוח — אפליקציית שליפת פוליסות
Android APK built with Kivy + Buildozer
"""

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.clock import Clock
from kivy.utils import get_color_from_hex
from kivy.core.window import Window
from kivy.metrics import dp

import threading
import json
import re
import time

# Android-specific imports (only available on device)
try:
    from jnius import autoclass
    from android.permissions import request_permissions, Permission
    ANDROID = True
except ImportError:
    ANDROID = False

try:
    import requests
    from bs4 import BeautifulSoup
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


# ── Colors ──────────────────────────────────────────
PRIMARY   = get_color_from_hex("#1a3a5c")   # כחול כהה
ACCENT    = get_color_from_hex("#e8f0fe")
WHITE     = get_color_from_hex("#ffffff")
SUCCESS   = get_color_from_hex("#2e7d32")
ERROR     = get_color_from_hex("#c62828")
TEXT      = get_color_from_hex("#1a1a2e")
LIGHT_BG  = get_color_from_hex("#f5f7fa")


# ── SMS Reader (Android) ─────────────────────────────
def read_latest_sms_android():
    """קורא SMS על Android דרך Java API"""
    if not ANDROID:
        return []
    try:
        Uri        = autoclass("android.net.Uri")
        context    = autoclass("org.kivy.android.PythonActivity").mActivity
        cr         = context.getContentResolver()
        uri        = Uri.parse("content://sms/inbox")
        cursor     = cr.query(uri, None, None, None, "date DESC")
        messages   = []
        if cursor and cursor.moveToFirst():
            for _ in range(min(5, cursor.getCount())):
                body   = cursor.getString(cursor.getColumnIndex("body"))   or ""
                sender = cursor.getString(cursor.getColumnIndex("address")) or ""
                messages.append({"body": body, "sender": sender})
                if not cursor.moveToNext():
                    break
        if cursor:
            cursor.close()
        return messages
    except Exception as e:
        return [{"body": f"SMS error: {e}", "sender": ""}]


def extract_otp(messages):
    for msg in messages:
        body = msg.get("body", "")
        if "איילון" in body or "ayalon" in body.lower() or re.search(r'\d{4,6}', body):
            match = re.search(r'\b(\d{4,6})\b', body)
            if match:
                return match.group(1)
    return None


# ── Network / Scraping ───────────────────────────────
BASE_URL = "https://clientportfolio.ayalon-ins.co.il"

def do_login(id_number, on_status):
    """שולח ת"ז לאיילון — מחזיר session"""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36",
        "Accept-Language": "he-IL,he;q=0.9",
    })
    on_status("מתחבר לאתר איילון...")
    resp = session.get(f"{BASE_URL}/cp/", timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")

    csrf_input = soup.find("input", {"name": re.compile(r"csrf|token", re.I)})
    csrf = csrf_input["value"] if csrf_input else None

    on_status("שולח תעודת זהות...")
    data = {"id": id_number}
    if csrf:
        data["_token"] = csrf
    session.post(f"{BASE_URL}/cp/login", data=data, timeout=15)
    return session, csrf


def do_verify(session, otp, csrf, on_status):
    on_status("מאמת קוד SMS...")
    data = {"otp": otp, "code": otp}
    if csrf:
        data["_token"] = csrf
    resp = session.post(f"{BASE_URL}/cp/verify", data=data, timeout=15)
    return session, resp.text


def do_fetch_policies(session, on_status):
    on_status("שולף פרטי פוליסות...")
    results = []
    for url in [f"{BASE_URL}/cp/", f"{BASE_URL}/cp/policies", f"{BASE_URL}/cp/portfolio"]:
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code == 200 and len(resp.text) > 500:
                soup = BeautifulSoup(resp.text, "html.parser")
                # טבלאות
                for table in soup.find_all("table"):
                    for row in table.find_all("tr")[1:]:
                        cols = [td.get_text(strip=True) for td in row.find_all(["td","th"])]
                        if any(cols):
                            results.append(" | ".join(c for c in cols if c))
                # כרטיסים
                if not results:
                    for card in soup.find_all(class_=re.compile(r"policy|card|item|polis", re.I)):
                        t = card.get_text(" | ", strip=True)
                        if t:
                            results.append(t)
                if results:
                    break
        except Exception:
            continue
    return results


# ══════════════════════════════════════════════════════
#  מסכים
# ══════════════════════════════════════════════════════

def make_label(text, size=16, bold=False, color=None, halign="center"):
    lbl = Label(
        text=text,
        font_size=dp(size),
        bold=bold,
        color=color or TEXT,
        halign=halign,
        text_size=(None, None),
    )
    lbl.bind(size=lambda *_: setattr(lbl, "text_size", (lbl.width, None)))
    return lbl


def make_button(text, bg=PRIMARY, fg=WHITE, on_press=None):
    btn = Button(
        text=text,
        font_size=dp(15),
        bold=True,
        background_normal="",
        background_color=bg,
        color=fg,
        size_hint_y=None,
        height=dp(50),
    )
    if on_press:
        btn.bind(on_press=on_press)
    return btn


# ── מסך כניסה ────────────────────────────────────────
class LoginScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        Window.clearcolor = LIGHT_BG

        root = BoxLayout(orientation="vertical", padding=dp(30), spacing=dp(18))

        # כותרת
        root.add_widget(Label(size_hint_y=None, height=dp(40)))
        root.add_widget(make_label("🛡️ איילון ביטוח", size=26, bold=True, color=PRIMARY))
        root.add_widget(make_label("פרטי פוליסות ביטוח", size=14, color=get_color_from_hex("#555")))
        root.add_widget(Label(size_hint_y=None, height=dp(20)))

        # שדה ת"ז
        root.add_widget(make_label("תעודת זהות", size=13, halign="right", color=PRIMARY))
        self.id_input = TextInput(
            hint_text="הזן תעודת זהות",
            input_filter="int",
            multiline=False,
            font_size=dp(18),
            size_hint_y=None,
            height=dp(50),
            padding=[dp(12), dp(12)],
            halign="center",
        )
        root.add_widget(self.id_input)

        # כפתור כניסה
        root.add_widget(Label(size_hint_y=None, height=dp(10)))
        root.add_widget(make_button("כניסה לאזור האישי ←", on_press=self.on_login))

        # סטטוס
        self.status_lbl = make_label("", size=13, color=get_color_from_hex("#555"))
        root.add_widget(self.status_lbl)

        root.add_widget(Label())  # spacer
        self.add_widget(root)

        # בקש הרשאת SMS
        if ANDROID:
            request_permissions([Permission.READ_SMS, Permission.RECEIVE_SMS])

    def set_status(self, msg, color="#555555"):
        def _set(*_):
            self.status_lbl.text = msg
            self.status_lbl.color = get_color_from_hex(color)
        Clock.schedule_once(_set)

    def on_login(self, *_):
        id_num = self.id_input.text.strip()
        if len(id_num) < 8:
            self.set_status("❌ תעודת זהות לא תקינה", "#c62828")
            return
        if not REQUESTS_AVAILABLE:
            self.set_status("❌ ספריית requests לא זמינה", "#c62828")
            return

        self.set_status("מתחבר...", "#1a3a5c")
        app = App.get_running_app()
        app.id_number = id_num

        def run():
            try:
                session, csrf = do_login(id_num, self.set_status)
                app.session = session
                app.csrf    = csrf
                self.set_status("📱 SMS נשלח — ממתין לקוד...")
                Clock.schedule_once(lambda *_: setattr(
                    self.manager, "current", "otp"), 0)
            except Exception as e:
                self.set_status(f"❌ שגיאה: {e}", "#c62828")

        threading.Thread(target=run, daemon=True).start()


# ── מסך OTP ──────────────────────────────────────────
class OTPScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._polling = False

        root = BoxLayout(orientation="vertical", padding=dp(30), spacing=dp(16))
        root.add_widget(Label(size_hint_y=None, height=dp(40)))
        root.add_widget(make_label("📱 אימות SMS", size=22, bold=True, color=PRIMARY))
        root.add_widget(make_label("הזן את הקוד שקיבלת ב-SMS\nאו המתן — האפליקציה תזהה אוטומטית", size=14))
        root.add_widget(Label(size_hint_y=None, height=dp(10)))

        self.otp_input = TextInput(
            hint_text="קוד אימות",
            input_filter="int",
            multiline=False,
            font_size=dp(28),
            size_hint_y=None,
            height=dp(60),
            padding=[dp(12), dp(12)],
            halign="center",
        )
        root.add_widget(self.otp_input)

        root.add_widget(make_button("אמת קוד ←", on_press=self.on_verify))

        self.status_lbl = make_label("", size=13)
        root.add_widget(self.status_lbl)
        root.add_widget(Label())
        self.add_widget(root)

    def on_enter(self):
        self._polling = True
        threading.Thread(target=self._poll_sms, daemon=True).start()

    def on_leave(self):
        self._polling = False

    def _poll_sms(self):
        """polls SMS every 3 seconds for OTP"""
        for _ in range(20):
            if not self._polling:
                return
            time.sleep(3)
            msgs = read_latest_sms_android()
            otp  = extract_otp(msgs)
            if otp:
                def _fill(*_):
                    self.otp_input.text = otp
                    self.status_lbl.text = f"✅ זוהה אוטומטית: {otp}"
                Clock.schedule_once(_fill)
                return

    def set_status(self, msg):
        Clock.schedule_once(lambda *_: setattr(self.status_lbl, "text", msg))

    def on_verify(self, *_):
        otp = self.otp_input.text.strip()
        if len(otp) < 4:
            self.status_lbl.text = "❌ הזן קוד תקין"
            return

        self.set_status("מאמת...")
        app = App.get_running_app()

        def run():
            try:
                session, page = do_verify(app.session, otp, app.csrf, self.set_status)
                app.session = session
                policies = do_fetch_policies(session, self.set_status)
                app.policies = policies
                Clock.schedule_once(lambda *_: setattr(
                    self.manager, "current", "results"), 0)
            except Exception as e:
                self.set_status(f"❌ שגיאה: {e}")

        threading.Thread(target=run, daemon=True).start()


# ── מסך תוצאות ───────────────────────────────────────
class ResultsScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.layout = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(10))

        self.layout.add_widget(make_label("📄 פוליסות הביטוח שלך", size=20, bold=True, color=PRIMARY))

        self.scroll = ScrollView()
        self.content = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8))
        self.content.bind(minimum_height=self.content.setter("height"))
        self.scroll.add_widget(self.content)
        self.layout.add_widget(self.scroll)

        self.layout.add_widget(
            make_button("🔄 רענן", bg=get_color_from_hex("#37474f"), on_press=self.on_refresh)
        )
        self.add_widget(self.layout)

    def on_enter(self):
        self.content.clear_widgets()
        policies = App.get_running_app().policies or []

        if not policies:
            self.content.add_widget(
                make_label("⚠️ לא נמצאו פוליסות\nייתכן שמבנה האתר השתנה", size=14, color=ERROR)
            )
            return

        for i, p in enumerate(policies, 1):
            card = BoxLayout(
                orientation="vertical",
                size_hint_y=None,
                padding=dp(12),
                spacing=dp(4),
            )
            card.bind(minimum_height=card.setter("height"))

            lbl = Label(
                text=f"פוליסה {i}\n{p}",
                font_size=dp(13),
                color=TEXT,
                halign="right",
                size_hint_y=None,
            )
            lbl.bind(
                size=lambda w, *_: setattr(w, "text_size", (w.width, None)),
                texture_size=lambda w, ts: setattr(w, "height", ts[1] + dp(10)),
            )
            card.add_widget(lbl)
            self.content.add_widget(card)

    def on_refresh(self, *_):
        self.manager.current = "login"


# ══════════════════════════════════════════════════════
#  האפליקציה
# ══════════════════════════════════════════════════════
class AyalonApp(App):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.id_number = ""
        self.session   = None
        self.csrf      = None
        self.policies  = []

    def build(self):
        sm = ScreenManager()
        sm.add_widget(LoginScreen(name="login"))
        sm.add_widget(OTPScreen(name="otp"))
        sm.add_widget(ResultsScreen(name="results"))
        return sm


if __name__ == "__main__":
    AyalonApp().run()
