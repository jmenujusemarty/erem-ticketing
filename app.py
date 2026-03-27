"""
erem ticketing
Automatické zpracování reklamací z IMAP serveru se SQLite databází
"""

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, make_response, abort, g as _g
import bleach as _bleach
import imaplib
import email
from email.header import decode_header
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr, make_msgid, formatdate
import datetime
from zoneinfo import ZoneInfo
import time
import threading
import re
import os
import logging
import base64
import json as _j
import ssl as _ssl

_PRAGUE = ZoneInfo('Europe/Prague')

# ── Strukturované logování ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
_log = logging.getLogger('ticketing')

def _now():
    """Aktuální čas v pražské timezone jako string DD.MM.YYYY HH:MM."""
    return datetime.datetime.now(tz=_PRAGUE).strftime('%d.%m.%Y %H:%M')
import sqlite3
import secrets
import hashlib
from functools import wraps
from dotenv import load_dotenv
import json as _json_module

load_dotenv()

app = Flask(__name__)

# ── SECRET_KEY — odmítni start bez platného klíče ────────────────────────────
_secret = os.getenv('SECRET_KEY', '')
if not _secret or len(_secret) < 32 or _secret == 'zmenit-na-nahodny-retezec':
    raise SystemExit("FATAL: SECRET_KEY musí být nastaven v .env a mít alespoň 32 znaků náhodného textu")
app.secret_key = _secret

# ── Session security ────────────────────────────────────────────────────────
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Strict'
app.config['SESSION_COOKIE_SECURE']   = os.getenv('FLASK_ENV') != 'development'
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(days=31)

# ── CSP nonce ───────────────────────────────────────────────────────────────
@app.before_request
def _set_nonce():
    """Generuje CSP nonce pro každý request."""
    _g.csp_nonce = secrets.token_hex(16)

app.jinja_env.globals['csp_nonce'] = lambda: getattr(_g, 'csp_nonce', '')

# ── Security HTTP hlavičky ───────────────────────────────────────────────────
@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
    # HSTS — jen přes HTTPS
    if request.is_secure or request.headers.get('X-Forwarded-Proto') == 'https':
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    # CSP — nonce-based inline skripty
    nonce = getattr(_g, 'csp_nonce', '')
    csp = (
        "default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}' https://www.gstatic.com https://apis.google.com "
        "https://www.googleapis.com https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https:; "
        "connect-src 'self' https://identitytoolkit.googleapis.com https://securetoken.googleapis.com "
        "https://generativelanguage.googleapis.com; "
        "frame-src https://accounts.google.com; "
        "object-src 'none'; "
        "base-uri 'self'"
    )
    response.headers['Content-Security-Policy'] = csp
    return response

# ── Rate limiting (SQLite-backed, persistentní) ─────────────────────────────
_LOGIN_MAX    = 5    # max pokusů
_LOGIN_WINDOW = 300  # sekund (5 minut)
_API_MAX      = 20
_API_WINDOW   = 60

def _check_rate_limit(ip: str) -> bool:
    """Vrátí True pokud je IP blokována (login). Persistentní přes SQLite."""
    now = time.time()
    key = f'login:{ip}'
    try:
        conn = get_db()
        conn.execute('DELETE FROM rate_limits WHERE key=? AND ts < ?', (key, now - _LOGIN_WINDOW))
        count = conn.execute('SELECT COUNT(*) FROM rate_limits WHERE key=?', (key,)).fetchone()[0]
        if count >= _LOGIN_MAX:
            conn.close()
            return True
        conn.execute('INSERT INTO rate_limits (key, ts) VALUES (?, ?)', (key, now))
        conn.commit()
        conn.close()
    except Exception as e:
        _log.warning(f'rate_limit DB error: {e}')
    return False

def _check_api_rate_limit(key_str: str) -> bool:
    """Vrátí True pokud je klíč blokován pro API. Persistentní přes SQLite."""
    now = time.time()
    key = f'api:{key_str}'
    try:
        conn = get_db()
        conn.execute('DELETE FROM rate_limits WHERE key=? AND ts < ?', (key, now - _API_WINDOW))
        count = conn.execute('SELECT COUNT(*) FROM rate_limits WHERE key=?', (key,)).fetchone()[0]
        if count >= _API_MAX:
            conn.close()
            return True
        conn.execute('INSERT INTO rate_limits (key, ts) VALUES (?, ?)', (key, now))
        conn.commit()
        conn.close()
    except Exception as e:
        _log.warning(f'api_rate_limit DB error: {e}')
    return False

# ── CSRF ochrana ────────────────────────────────────────────────────────────
def _csrf_token() -> str:
    if '_csrf' not in session:
        session['_csrf'] = secrets.token_hex(32)
    return session['_csrf']

def _csrf_valid() -> bool:
    token = (request.form.get('_csrf_token') or
             request.headers.get('X-CSRF-Token') or '')
    return secrets.compare_digest(token, session.get('_csrf', ''))

app.jinja_env.globals['csrf_token'] = _csrf_token

# Globální CSRF ochrana pro všechny POST/PUT/DELETE/PATCH
_CSRF_EXEMPT = {'/health', '/api/firebase_auth'}

@app.before_request
def _global_csrf_check():
    if request.method not in ('POST', 'PUT', 'DELETE', 'PATCH'):
        return
    if request.path in _CSRF_EXEMPT:
        return
    if not session.get('logged_in'):
        return  # Nepřihlášení — login endpoint má vlastní ochranu
    if not _csrf_valid():
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'error': 'Neplatný CSRF token'}), 403
        flash('Neplatný požadavek (CSRF). Zkus to znovu.', 'error')
        return redirect(request.referrer or url_for('index'))

# ── HTML sanitizace (bleach whitelist) ──────────────────────────────────────
# Whitelist tagů a atributů pro bleach sanitizaci
_BLEACH_TAGS = [
    'b', 'i', 'u', 'strong', 'em', 'br', 'p', 'div', 'span',
    'a', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'blockquote', 'pre', 'code'
]
_BLEACH_ATTRS = {
    'a':    ['href', 'title', 'style'],
    'span': ['style'],
    'p':    ['style'],
    'div':  ['style'],
    'h1':   ['style'], 'h2': ['style'], 'h3': ['style'], 'h4': ['style'],
}
_BLEACH_STYLES = [
    'color', 'background-color', 'font-weight', 'font-style',
    'text-decoration', 'font-size', 'text-align'
]

def _sanitize_rich_html(content: str) -> str:
    """Povolí pouze bezpečné HTML tagy pro rich text editor (bleach whitelist)."""
    if not content:
        return content
    return _bleach.clean(
        content,
        tags=_BLEACH_TAGS,
        attributes=_BLEACH_ATTRS,
        strip=True
    )

def _sanitize_html(html: str) -> str:
    return _sanitize_rich_html(html)

def _sanitize_subject(s: str) -> str:
    """Odstraní CRLF z email předmětu — prevence header injection."""
    return re.sub(r'[\r\n\t]+', ' ', (s or '').strip())[:200]

_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')

def _validate_email(addr: str) -> bool:
    """Ověří formát e-mailové adresy — prevence header injection."""
    return bool(_EMAIL_RE.match((addr or '').strip()))

# Jinja2 3.x odstranil test 'search' — přidáme zpět
app.jinja_env.tests['search'] = lambda value, pattern: bool(re.search(pattern, str(value) if value else ''))

# ── Blokované domény (ne zákazníci) ────────────────────────────────────────
# E-maily z těchto domén jsou automaticky přeskočeny — dopravci, notifikace, systémy
BLOCKED_SENDER_DOMAINS = {
    'ppl.cz', 'ppl.com', 'dpd.com', 'dpd.cz',
    'zasilkovna.cz', 'packeta.com',
    'gls-group.eu', 'gls-czech.cz',
    'ups.com', 'fedex.com', 'dhl.com', 'dhl.de',
    'ceskaposta.cz', 'postaonline.cz',
    'mailer-daemon', 'postmaster',
    'noreply.github.com', 'notifications.google.com',
}
# Přidat vlastní domény přes env proměnnou (čárkou oddělené)
_extra_blocked = os.getenv('BLOCKED_SENDER_DOMAINS', '')
if _extra_blocked:
    BLOCKED_SENDER_DOMAINS.update(d.strip().lower() for d in _extra_blocked.split(',') if d.strip())

def _is_blocked_sender(email_addr: str) -> bool:
    """Vrátí True pokud je odesílatel z blokované domény."""
    addr = email_addr.lower()
    domain = addr.split('@')[-1] if '@' in addr else addr
    return domain in BLOCKED_SENDER_DOMAINS or any(addr.startswith(p) for p in ('mailer-daemon@', 'postmaster@'))

# Konfigurace
IMAP_SERVER = os.getenv('IMAP_SERVER')
IMAP_PORT = int(os.getenv('IMAP_PORT', 993))
IMAP_EMAIL = os.getenv('IMAP_EMAIL')
IMAP_PASSWORD = os.getenv('IMAP_PASSWORD')

SMTP_SERVER = os.getenv('SMTP_SERVER')
SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
SMTP_EMAIL = os.getenv('SMTP_EMAIL') or os.getenv('IMAP_EMAIL')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD') or os.getenv('IMAP_PASSWORD')
SMTP_FROM_NAME = os.getenv('SMTP_FROM_NAME', 'erem')

CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', 60))  # sekund

# Admin přihlášení
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')
if ADMIN_USERNAME == 'admin' and ADMIN_PASSWORD == 'admin123':
    raise SystemExit("FATAL: Změň výchozí ADMIN_USERNAME a ADMIN_PASSWORD v .env souboru")

# Databáze
DATABASE = os.getenv('DATABASE', 'complaints.db')

_last_complaint_count = 0  # pro SSE notifikace
_manual_check_lock = threading.Lock()
_complaint_count_lock = threading.Lock()

# Firebase konfigurace (web app config — není tajné, jde do frontendu)
FIREBASE_API_KEY          = os.getenv('FIREBASE_API_KEY', '')
FIREBASE_AUTH_DOMAIN      = os.getenv('FIREBASE_AUTH_DOMAIN', '')
FIREBASE_PROJECT_ID       = os.getenv('FIREBASE_PROJECT_ID', '')
FIREBASE_APP_ID           = os.getenv('FIREBASE_APP_ID', '')
# Povolené e-maily pro přihlášení přes Firebase (čárkou oddělené)
FIREBASE_ALLOWED_EMAILS   = os.getenv('FIREBASE_ALLOWED_EMAILS', '')

COMPLAINT_CATEGORIES = ['Nedoručení', 'Poškozené zboží', 'Špatný produkt', 'Vrácení peněz', 'Ostatní']

# Výchozí šablona auto-reply (erem styl — nespisovně, tykání)
DEFAULT_AUTO_REPLY_TEMPLATE = """Ahoj{customer_name}!

tvoje reklamace k nám dorazila, čteme ji, nepohřbíme ji ve složce "vyřeším později" a rozhodně ti neodpíšeme za 3 týdny se slovy "omlouváme se za pozdní odpověď". Takoví nejsme.

Reklamace c. {ticket_id}
Predmet: {subject}
Prijato: {date}

Koukáme na to a do 3-5 pracovních dnů se ozveme. Pokud se to trochu protáhne, napiš - jsme lidi, ne automat.

{admin_signature}"""


# ─── Databáze ──────────────────────────────────────────────────────────────

def get_db():
    """Získání připojení k databázi"""
    conn = sqlite3.connect(DATABASE, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=30000')  # 30s timeout
    conn.execute('PRAGMA synchronous=NORMAL')   # lepší performance s WAL
    return conn

def init_db():
    """Inicializace databáze"""
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id TEXT UNIQUE NOT NULL,
            date TEXT NOT NULL,
            customer_email TEXT NOT NULL,
            subject TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'Nová',
            notes TEXT,
            order_id TEXT,
            order_data TEXT
        )
    ''')
    # Migrace: přidej sloupce pokud chybí (pro existující DB)
    try:
        conn.execute('ALTER TABLE complaints ADD COLUMN order_id TEXT')
    except Exception:
        pass
    try:
        conn.execute('ALTER TABLE complaints ADD COLUMN order_data TEXT')
    except Exception:
        pass
    # Tabulka objednávek z e-shopu (cache / sync)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT UNIQUE NOT NULL,
            customer_email TEXT,
            customer_name TEXT,
            order_date TEXT,
            total_price TEXT,
            status TEXT,
            items TEXT,
            raw_data TEXT,
            synced_at TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS processed_emails (
            msg_id TEXT PRIMARY KEY,
            processed_at TEXT NOT NULL
        )
    ''')
    # Migrace: přidej sloupce pro AI analýzu
    try:
        conn.execute('ALTER TABLE complaints ADD COLUMN problem_summary TEXT')
    except Exception:
        pass
    try:
        conn.execute('ALTER TABLE complaints ADD COLUMN order_number TEXT')
    except Exception:
        pass
    try:
        conn.execute('ALTER TABLE complaints ADD COLUMN category TEXT')
    except Exception:
        pass
    try:
        conn.execute('ALTER TABLE complaints ADD COLUMN last_reply_at TEXT')
    except Exception:
        pass
    try:
        conn.execute('ALTER TABLE complaints ADD COLUMN customer_name TEXT')
    except Exception:
        pass
    try:
        conn.execute('ALTER TABLE complaints ADD COLUMN reminded_at TEXT')
    except Exception:
        pass
    try:
        conn.execute('ALTER TABLE complaints ADD COLUMN synced_message_ids TEXT')
    except Exception:
        pass
    try:
        conn.execute('ALTER TABLE complaints ADD COLUMN customer_unread INTEGER DEFAULT 0')
    except Exception:
        pass
    try:
        conn.execute('ALTER TABLE complaints ADD COLUMN thread_msg_id TEXT')
    except Exception:
        pass
    try:
        conn.execute('ALTER TABLE complaints ADD COLUMN thread_refs TEXT')
    except Exception:
        pass
    try:
        conn.execute('ALTER TABLE complaints ADD COLUMN auto_reply_sent INTEGER DEFAULT 0')
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE complaints ADD COLUMN priority TEXT DEFAULT 'Střední'")
    except Exception:
        pass
    try:
        conn.execute('ALTER TABLE complaints ADD COLUMN assigned_to TEXT')
    except Exception:
        pass
    # Šablony odpovědí
    conn.execute('''
        CREATE TABLE IF NOT EXISTS reply_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            body TEXT NOT NULL
        )
    ''')
    # Výchozí hodnoty konfigurace
    conn.execute('INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)', ('auto_reply_enabled', '1'))
    conn.execute('INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)', ('auto_reply_template', DEFAULT_AUTO_REPLY_TEMPLATE))
    # Migrace: nahraď starý/zastaralý template novým erem stylem
    old_row = conn.execute("SELECT value FROM config WHERE key='auto_reply_template'").fetchone()
    old_tpl = (old_row['value'] or '').strip() if old_row else ''
    if (old_tpl.startswith('Dobrý den,') or old_tpl.startswith('Čau')
            or '🎫' in old_tpl or '📌' in old_tpl or '📅' in old_tpl):
        conn.execute('UPDATE config SET value=? WHERE key=?', (DEFAULT_AUTO_REPLY_TEMPLATE, 'auto_reply_template'))
    conn.execute('INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)', ('gemini_api_key', os.getenv('GEMINI_API_KEY', '')))
    conn.execute('INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)', ('sla_days', '3'))
    conn.execute('INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)', ('admin_signature', 'Martin z eremu'))
    # Tabulka rate limitů (persistentní)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS rate_limits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL,
            ts REAL NOT NULL
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_rl_key_ts ON rate_limits(key, ts)')
    # Smaž staré záznamy (cleanup při startu)
    conn.execute('DELETE FROM rate_limits WHERE ts < ?', (time.time() - 3600,))
    conn.commit()
    global _last_complaint_count
    try:
        row = conn.execute("SELECT COUNT(*) as cnt FROM complaints WHERE status != 'Spam'").fetchone()
        _last_complaint_count = row['cnt'] if row else 0
    except Exception:
        pass
    conn.close()
    _log.info("Databáze inicializována")

def get_reply_templates():
    conn = get_db()
    templates = conn.execute('SELECT * FROM reply_templates ORDER BY name').fetchall()
    conn.close()
    return [dict(t) for t in templates]

def _enrich_sla(c, sla_days):
    """Přidá sla_cls, age_days a no_reply_delta do dict reklamace."""
    closed = any(x in (c.get('status') or '').lower() for x in ('vyřešen', 'zamítn'))
    c['sla_cls'] = None
    c['age_days'] = None
    c['no_reply_delta'] = None
    now = datetime.datetime.now(tz=_PRAGUE).replace(tzinfo=None)
    if not closed and c.get('date'):
        try:
            created = datetime.datetime.strptime(c['date'][:16], '%d.%m.%Y %H:%M')
            age = (now - created).days
            c['age_days'] = age
            if age >= sla_days:
                c['sla_cls'] = 'red'
            elif age >= max(sla_days - 1, 1):
                c['sla_cls'] = 'yellow'
            else:
                c['sla_cls'] = 'green'
        except Exception:
            pass
        try:
            ref_str = c.get('last_reply_at') or c['date']
            ref = datetime.datetime.strptime(ref_str[:16], '%d.%m.%Y %H:%M')
            delta = now - ref
            hours = int(delta.total_seconds() / 3600)
            if hours < 1:
                c['no_reply_delta'] = '<1h'
            elif hours < 24:
                c['no_reply_delta'] = f'{hours}h'
            else:
                c['no_reply_delta'] = f'{delta.days}d'
        except Exception:
            pass
    return c

def get_config(key, default=None):
    """Získání hodnoty konfigurace"""
    try:
        conn = get_db()
        row = conn.execute('SELECT value FROM config WHERE key = ?', (key,)).fetchone()
        conn.close()
        return row['value'] if row else default
    except:
        return default

def set_config(key, value):
    """Uložení hodnoty konfigurace"""
    conn = get_db()
    conn.execute('INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()

def get_admin_signature(email=None):
    """Vrátí podpis správce pro daného uživatele, nebo globální výchozí."""
    if email:
        sig = get_config(f'admin_signature:{email}', None)
        if sig is not None:
            return sig
    return get_config('admin_signature', 'Martin z eremu')


# ─── E-mailové funkce ──────────────────────────────────────────────────────

_ticket_id_lock = threading.Lock()

def generate_ticket_id():
    """Generování sekvenčního ticket ID (RK-0001, RK-0002, …) — thread-safe."""
    with _ticket_id_lock:
        try:
            conn = get_db()
            row = conn.execute(
                "SELECT MAX(CAST(REPLACE(ticket_id,'RK-','') AS INTEGER)) as max_n "
                "FROM complaints WHERE ticket_id GLOB 'RK-[0-9]*'"
            ).fetchone()
            n = (row['max_n'] if row and row['max_n'] else 0) + 1
            conn.close()
            return f"RK-{n:04d}"
        except Exception:
            import random
            return f"RK-{random.randint(1000,9999)}"

def decode_email_subject(subject):
    """Dekódování předmětu e-mailu"""
    if subject is None:
        return "Bez předmětu"
    decoded_parts = decode_header(subject)
    decoded_subject = ""
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            try:
                decoded_subject += part.decode(encoding or 'utf-8')
            except:
                decoded_subject += part.decode('utf-8', errors='ignore')
        else:
            decoded_subject += part
    return decoded_subject

def get_email_body(msg):
    """Extrakce těla e-mailu"""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                try:
                    body = part.get_payload(decode=True).decode()
                    break
                except:
                    pass
    else:
        try:
            body = msg.get_payload(decode=True).decode()
        except:
            body = "Nepodařilo se dekódovat obsah"
    return body[:1000]

def strip_email_quote(body):
    """Odstraní citovanou část e-mailu (řádky s >, 'On ... wrote:', '--' signatury)."""
    lines = body.splitlines()
    result = []
    for line in lines:
        stripped = line.strip()
        # Zastav na řádku "On ... wrote:" nebo "> "
        if re.match(r'^On .{10,} wrote:$', stripped):
            break
        if stripped.startswith('>'):
            break
        # Zastav na oddělovači signatury e-mailového klienta
        if stripped in ('--', '___', '---'):
            break
        result.append(line)
    return '\n'.join(result).strip()


def save_to_db(ticket_id, customer_email, subject, body, customer_name=None, status='Nová', msg_id=None, references=None):
    """Uložení reklamace do databáze"""
    try:
        conn = get_db()
        now = _now()
        # Ulož msg_id do synced_message_ids, aby sync_history neznovu-přidal původní e-mail
        synced = _json_module.dumps([msg_id]) if msg_id else None
        conn.execute(
            'INSERT INTO complaints (ticket_id, date, customer_email, subject, description, status, customer_name, thread_msg_id, thread_refs, synced_message_ids) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (ticket_id, now, customer_email, subject, body, status, customer_name, msg_id, references, synced)
        )
        conn.commit()
        conn.close()
        global _last_complaint_count
        with _complaint_count_lock:
            _last_complaint_count += 1
        return True
    except Exception as e:
        _log.error(f"Chyba při ukládání do DB: {e}")
        return False

def _plain_to_html(text):
    """Převede plain text na HTML (escape + zachování odřádkování)."""
    import html as _html_mod
    return '<br>'.join(_html_mod.escape(line) for line in (text or '').splitlines())

def _strip_html(html):
    """Odstraní HTML tagy — pro plain-text fallback. <br> → newline, <p>/<div> → newline."""
    text = re.sub(r'<br\s*/?>', '\n', html or '')
    text = re.sub(r'</(p|div)>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    return text.strip()

def send_email(to_email, subject, body_text, signature_html=None, body_html=None, in_reply_to=None, references=None):
    """
    Odeslání e-mailu přes SMTP.
    body_html: hotový HTML obsah těla (z rich-text editoru).
    signature_html: HTML podpis přidaný za tělo.
    Pokud je body_html nebo signature_html, pošle multipart/alternative (plain + HTML).
    Jinak pošle plain text.
    """
    subject = _sanitize_subject(subject)
    if not _validate_email(to_email):
        _log.error(f"send_email: neplatná e-mailová adresa odmítnuta: '{str(to_email)[:80]}'")
        return False
    try:
        if signature_html or body_html:
            # HTML část: buď přímý HTML z editoru, nebo konverze z plain textu
            html_content = body_html if body_html else _plain_to_html(body_text)
            plain_fallback = body_text if body_text else _strip_html(body_html or '')
            if signature_html:
                full_html = (
                    '<div style="font-family:Helvetica Neue,Helvetica,Arial,sans-serif;'
                    'font-size:15px;line-height:1.6;color:#1a1a1a;">'
                    f'{html_content}'
                    '<br><br>'
                    '<div style="border-top:1px solid #e5e7eb;margin-top:16px;padding-top:12px;'
                    'font-size:13px;color:#6b7280;">'
                    f'{signature_html}'
                    '</div></div>'
                )
                plain_sig = _strip_html(signature_html)
                plain_full = f"{plain_fallback}\n\n{plain_sig}" if plain_sig else plain_fallback
            else:
                full_html = (
                    '<div style="font-family:Helvetica Neue,Helvetica,Arial,sans-serif;'
                    'font-size:15px;line-height:1.6;color:#1a1a1a;">'
                    f'{html_content}'
                    '</div>'
                )
                plain_full = plain_fallback
            outer = MIMEMultipart('mixed')
            outer['From'] = formataddr((SMTP_FROM_NAME, SMTP_EMAIL))
            outer['To'] = to_email
            outer['Subject'] = subject
            outer['Date'] = formatdate(localtime=False)
            outer['Message-Id'] = make_msgid(domain=SMTP_EMAIL.split('@')[-1] if SMTP_EMAIL and '@' in SMTP_EMAIL else 'eremvole.cz')
            outer['X-erem-Sent'] = '1'
            if in_reply_to:
                outer['In-Reply-To'] = in_reply_to
            if references:
                outer['References'] = references
            alt = MIMEMultipart('alternative')
            alt.attach(MIMEText(plain_full, 'plain', 'utf-8'))
            alt.attach(MIMEText(full_html, 'html', 'utf-8'))
            outer.attach(alt)
            msg = outer
        else:
            msg = MIMEMultipart()
            msg['From'] = formataddr((SMTP_FROM_NAME, SMTP_EMAIL))
            msg['To'] = to_email
            msg['Subject'] = subject
            msg['Date'] = formatdate(localtime=False)
            msg['Message-Id'] = make_msgid(domain=SMTP_EMAIL.split('@')[-1] if SMTP_EMAIL and '@' in SMTP_EMAIL else 'eremvole.cz')
            msg['X-erem-Sent'] = '1'
            if in_reply_to:
                msg['In-Reply-To'] = in_reply_to
            if references:
                msg['References'] = references
            msg.attach(MIMEText(body_text, 'plain', 'utf-8'))
        _tls_ctx = _ssl.create_default_context()
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30)
        try:
            server.ehlo()
            server.starttls(context=_tls_ctx)
            server.ehlo()
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.send_message(msg)
        finally:
            try:
                server.quit()
            except Exception:
                pass
        return True
    except Exception as e:
        _log.error(f"Chyba při odesílání e-mailu: {e}")
        return False

def send_confirmation_email(to_email, ticket_id, subject, customer_name=None, force=False):
    """Odeslání automatického potvrzení. force=True ignoruje přepínač auto-reply."""
    if not force and get_config('auto_reply_enabled', '1') != '1':
        return False
    template = get_config('auto_reply_template', DEFAULT_AUTO_REPLY_TEMPLATE)
    now = _now()
    name_part = f' {customer_name}' if customer_name else ''
    sig_html = get_config('admin_signature', 'Martin z eremu')

    # Načti threading hlavičky z DB aby odpověď byla součástí vlákna
    in_reply_to = None
    references = None
    try:
        tc = get_db()
        row = tc.execute('SELECT thread_msg_id, thread_refs FROM complaints WHERE ticket_id=?', (ticket_id,)).fetchone()
        tc.close()
        if row:
            in_reply_to = row['thread_msg_id'] or None
            references  = row['thread_refs']   or None
    except Exception:
        pass

    # Předmět jako "Re: původní předmět" pro zachování vlákna
    reply_subject = subject if subject.lower().startswith('re:') else f'Re: {subject}'

    is_html = '<' in template
    if is_html:
        sig_for_tpl = sig_html
        formatted = template.format(ticket_id=ticket_id, subject=subject, date=now,
                                    customer_name=name_part, admin_signature=sig_for_tpl)
        formatted = formatted.replace('\r\n', '<br>').replace('\r', '<br>').replace('\n', '<br>')
        plain_fallback = re.sub(r'<br\s*/?>', '\n', _strip_html(formatted))
        ok = send_email(to_email, reply_subject, plain_fallback, body_html=formatted,
                        in_reply_to=in_reply_to, references=references)
    else:
        sig_plain = re.sub(r'<br\s*/?>', '\n', _strip_html(sig_html))
        formatted = template.format(ticket_id=ticket_id, subject=subject, date=now,
                                    customer_name=name_part, admin_signature=sig_plain)
        ok = send_email(to_email, reply_subject, formatted, body_html=_plain_to_html(formatted),
                        in_reply_to=in_reply_to, references=references)
    if ok:
        try:
            c = get_db()
            c.execute('UPDATE complaints SET auto_reply_sent=1 WHERE ticket_id=?', (ticket_id,))
            c.commit(); c.close()
        except Exception:
            pass
    return ok

def extract_name_from_header(from_header):
    """Extrahuje jméno odesílatele z From hlavičky, např. 'Jan Novák <jan@example.com>' → 'Jan Novák'"""
    if not from_header:
        return None
    # Dekóduj encoded-words
    parts = decode_header(from_header)
    decoded = ''
    for part, enc in parts:
        if isinstance(part, bytes):
            decoded += part.decode(enc or 'utf-8', errors='ignore')
        else:
            decoded += part
    # Extrahuj část před < pokud existuje
    m = re.match(r'^"?([^"<]+)"?\s*<', decoded.strip())
    if m:
        name = m.group(1).strip().strip('"')
        if name and '@' not in name:
            return name
    return None

def _parse_email_date(date_str):
    """Parsuje Date header emailu na 'DD.MM.YYYY HH:MM'."""
    from email.utils import parsedate_to_datetime
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.strftime('%d.%m.%Y %H:%M')
    except Exception:
        return _now()

def _subjects_related(subj1, subj2):
    """Vrátí True pokud jsou předměty emailů ve stejném vláknu."""
    def clean(s):
        return re.sub(r'^(re\s*:|fwd?\s*:|předmět\s*:)\s*', '', (s or '').lower().strip())
    c1, c2 = clean(subj1), clean(subj2)
    return bool(c1 and c2 and (c1 in c2 or c2 in c1 or c1 == c2))

def _find_sent_folder(mail):
    """Najde složku Odeslaných zpráv na IMAP serveru."""
    try:
        status, folders = mail.list()
        if status != 'OK':
            return None
        raw = '\n'.join(
            (f.decode() if isinstance(f, bytes) else f) for f in folders
        ).lower()
        candidates = ['Sent', 'Sent Messages', 'Sent Items', 'INBOX.Sent',
                      'Odeslan\xe1 po\u0161ta', 'Odeslan\xe9', 'Sent Mail',
                      '[Gmail]/Sent Mail', 'INBOX.Odeslan\xe9']
        for name in candidates:
            if name.lower() in raw:
                return name
    except Exception:
        pass
    return None

def sync_ticket_emails(ticket_id):
    """
    Synchronizuje historii e-mailové konverzace z IMAP.
    Prohledá INBOX (zákazník → nám) i SENT (my → zákazník),
    filtruje podle ticket ID nebo podobného předmětu,
    deduplikuje přes Message-ID a přidá nové zprávy do notes.
    Vrací (počet_nových, chyba_nebo_None).
    """
    conn = get_db()
    ticket = conn.execute('SELECT * FROM complaints WHERE ticket_id=?', (ticket_id,)).fetchone()
    conn.close()
    if not ticket:
        return 0, 'Ticket nenalezen'

    customer_email = ticket['customer_email']
    original_subject = ticket['subject'] or ''
    current_notes = ticket['notes'] or ''

    try:
        synced_ids = set(_json_module.loads(ticket['synced_message_ids'])) \
            if ticket['synced_message_ids'] else set()
    except Exception:
        synced_ids = set()

    new_entries = []
    new_message_ids = set()

    mail = None
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(IMAP_EMAIL, IMAP_PASSWORD)

        def _fetch_folder(folder_name, search_criterion, msg_type, author_label):
            try:
                if mail.select(folder_name)[0] != 'OK':
                    return
                status, msgs = mail.search(None, search_criterion)
                if status != 'OK':
                    return
                for eid in msgs[0].split():
                    s2, md = mail.fetch(eid, '(RFC822)')
                    if s2 != 'OK':
                        continue
                    msg = email.message_from_bytes(md[0][1])
                    msg_id = (msg.get('Message-ID') or '').strip()
                    if msg_id in synced_ids:
                        continue
                    subj = decode_email_subject(msg.get('Subject', ''))
                    if ticket_id not in subj and not _subjects_related(subj, original_subject):
                        continue
                    body = get_email_body(msg)
                    if not body.strip():
                        continue
                    # Odstraň citované části (řádky >) pro čistý výpis
                    if msg_type == 'customer':
                        body = strip_email_quote(body)
                    if not body.strip():
                        continue
                    date_str = _parse_email_date(msg.get('Date', ''))
                    new_entries.append({
                        'type': msg_type,
                        'time': date_str,
                        'author': author_label,
                        'text': body[:800],
                        'msg_id': msg_id,
                    })
                    if msg_id:
                        new_message_ids.add(msg_id)
            except Exception as fe:
                _log.warning(f"sync folder {folder_name}: {fe}")

        # Zprávy od zákazníka — INBOX
        _fetch_folder('INBOX', f'(FROM "{customer_email}")', 'customer', customer_email)

        # Naše odeslané — SENT
        sent = _find_sent_folder(mail)
        if sent:
            _fetch_folder(sent, f'(TO "{customer_email}")', 'reply', 'erem tým')

    except Exception as e:
        return 0, f'IMAP chyba: {e}'
    finally:
        if mail:
            try:
                mail.close()
            except Exception:
                pass
            try:
                mail.logout()
            except Exception:
                pass

    if not new_entries:
        return 0, 'Žádné nové zprávy k synchronizaci'

    # Seřaď chronologicky a vlož do notes
    new_entries.sort(key=lambda x: x['time'])
    for entry in new_entries:
        if entry['type'] == 'customer':
            note = f"[{entry['time']}] 📨 Odpověď zákazníka ({entry['author']}):\n{entry['text']}"
        else:
            note = f"[{entry['time']}] 📤 Odeslaná odpověď zákazníkovi:\n{entry['text']}"
        current_notes = (current_notes + '\n' + note).strip()

    all_synced = synced_ids | new_message_ids
    conn = get_db()
    conn.execute(
        'UPDATE complaints SET notes=?, synced_message_ids=? WHERE ticket_id=?',
        (current_notes, _json_module.dumps(list(all_synced)), ticket_id)
    )
    conn.commit()
    conn.close()
    _log.info(f"Sync {ticket_id}: přidáno {len(new_entries)} zpráv")
    return len(new_entries), None


def find_ticket_in_email(subject, references='', in_reply_to=''):
    """Zkusí najít ticket ID v předmětu nebo reply headers."""
    # Hledej v předmětu: [#RK-0001] nebo #RK-0001 nebo RK-0001
    m = re.search(r'RK-[\w]+', subject or '')
    if m:
        return m.group(0)
    # Hledej v references
    for header in (references, in_reply_to):
        if not header:
            continue
        m = re.search(r'RK-[\w]+', header)
        if m:
            return m.group(0)
    return None


def append_customer_reply(ticket_id, customer_email, body, timestamp, incoming_msg_id=None, incoming_refs=None):
    """Přidá odpověď zákazníka do konverzace ticketu."""
    conn = get_db()
    ticket = conn.execute('SELECT notes, status, thread_refs, subject, customer_name FROM complaints WHERE ticket_id=?', (ticket_id,)).fetchone()
    if not ticket:
        conn.close()
        return False
    current_notes = ticket['notes'] or ''
    clean_body = strip_email_quote(body)[:800]
    note = f"[{timestamp}] 📨 Odpověď zákazníka ({customer_email}):\n{clean_body}"
    new_notes = f"{current_notes}\n{note}".strip()
    # Pokud byl ticket vyřešen, přesuň zpět do řešení
    new_status = ticket['status']
    if new_status in ('Vyřešeno', 'Zamítnuto'):
        new_status = 'V řešení'
    # Aktualizuj thread references
    existing_refs = ticket['thread_refs'] or ''
    if incoming_msg_id and incoming_msg_id not in existing_refs:
        new_refs = (existing_refs + ' ' + incoming_msg_id).strip()
    else:
        new_refs = existing_refs
    conn.execute('UPDATE complaints SET notes=?, status=?, last_reply_at=?, customer_unread=1, thread_msg_id=?, thread_refs=? WHERE ticket_id=?',
                 (new_notes, new_status, timestamp, incoming_msg_id or ticket.get('thread_msg_id'), new_refs, ticket_id))
    conn.commit()
    conn.close()
    _log.info(f"Odpověď zákazníka přidána do {ticket_id}")
    # Admin notifikace
    try:
        notify_email = get_config('admin_notify_email', '')
        if notify_email:
            customer_name = ticket['customer_name'] or customer_email
            subject_text = ticket['subject'] or ''
            preview = clean_body[:200] + ('…' if len(clean_body) > 200 else '')
            notify_body = (
                f"Zákazník {customer_name} ({customer_email}) odpověděl na ticket {ticket_id}.\n\n"
                f"Předmět: {subject_text}\n\n"
                f"Zpráva:\n{preview}\n\n"
                f"Pro zobrazení ticketu se přihlaste do systému."
            )
            send_email(notify_email,
                       f"[erem ticketing] Nová odpověď zákazníka — {ticket_id}",
                       notify_body)
    except Exception as _ne:
        _log.warning(f"Admin notifikace selhala: {_ne}")
    return True


def _get_processed_msg_ids():
    """Vrátí set Message-ID již zpracovaných e-mailů."""
    try:
        conn = get_db()
        rows = conn.execute('SELECT msg_id FROM processed_emails').fetchall()
        conn.close()
        return set(r['msg_id'] for r in rows)
    except Exception:
        return set()

def _mark_msg_id_processed(msg_id):
    """Přidá Message-ID do zpracovaných (uloží do DB)."""
    if not msg_id:
        return
    try:
        conn = get_db()
        conn.execute(
            'INSERT OR IGNORE INTO processed_emails (msg_id, processed_at) VALUES (?, ?)',
            (msg_id, _now())
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

def check_emails():
    """Kontrola nových e-mailů na IMAP serveru.
    Prohledává posledních 30 dní (bez ohledu na přečtení) a deduplikuje přes Message-ID.
    """
    mail = None
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(IMAP_EMAIL, IMAP_PASSWORD)
        mail.select('INBOX')

        # Hledej e-maily za poslední 30 dní — přečtené i nepřečtené
        since = (datetime.datetime.now(tz=_PRAGUE) - datetime.timedelta(days=30)).strftime('%d-%b-%Y')
        status, messages = mail.search(None, f'SINCE {since}')

        processed_ids = _get_processed_msg_ids()

        if status == 'OK':
            email_ids = messages[0].split()
            for email_id in email_ids:
                status, msg_data = mail.fetch(email_id, '(RFC822)')
                if status != 'OK':
                    continue
                msg = email.message_from_bytes(msg_data[0][1])
                msg_id = (msg.get('Message-ID') or '').strip()

                # Přeskoč pokud jsme ho už zpracovali
                if msg_id and msg_id in processed_ids:
                    continue

                from_header = msg.get('From', '')
                from_match = re.search(r'[\w\.\-+]+@[\w\.-]+', from_header)
                from_addr = from_match.group(0).lower() if from_match else ''
                # Přeskoč pouze naše vlastní odeslané e-maily — identifikujeme je přes X-erem-Sent header
                # (ne podle From adresy, aby zákazníci se stejnou doménou nebyli blokováni)
                if msg.get('X-erem-Sent') == '1':
                    if msg_id:
                        _mark_msg_id_processed(msg_id)
                    continue

                # Přeskoč e-maily od dopravců a notifikačních systémů
                if _is_blocked_sender(from_addr):
                    if msg_id:
                        _mark_msg_id_processed(msg_id)
                    _log.info(f"Blokován odesílatel: {from_addr}")
                    continue

                email_match = re.search(r'[\w\.-]+@[\w\.-]+', from_header)
                customer_email = email_match.group(0) if email_match else from_header
                customer_name = extract_name_from_header(from_header)
                subj = decode_email_subject(msg.get('Subject'))
                references = msg.get('References', '')
                in_reply_to = msg.get('In-Reply-To', '')
                existing_ticket = find_ticket_in_email(subj, references, in_reply_to)
                body = get_email_body(msg)
                timestamp = _now()

                if existing_ticket:
                    append_customer_reply(existing_ticket, customer_email, body, timestamp, incoming_msg_id=msg_id, incoming_refs=references)
                else:
                    # Sestav References pro nový ticket
                    new_refs = references + (' ' + msg_id if msg_id else '') if references else msg_id or ''
                    ticket_id = generate_ticket_id()
                    if save_to_db(ticket_id, customer_email, subj, body, customer_name=customer_name,
                                  msg_id=msg_id, references=new_refs.strip()):
                        threading.Thread(
                            target=analyze_complaint,
                            args=(ticket_id, subj, body, customer_email, customer_name, True),
                            daemon=True
                        ).start()
                        _log.info(f"Uložena zpráva: {ticket_id} od {customer_email}")

                if msg_id:
                    _mark_msg_id_processed(msg_id)

    except Exception as e:
        _log.error(f"Chyba při kontrole e-mailů: {e}")
    finally:
        if mail:
            try:
                mail.close()
            except Exception:
                pass
            try:
                mail.logout()
            except Exception:
                pass

def email_checker_loop():
    """Nekonečná smyčka pro pravidelnou kontrolu e-mailů"""
    while True:
        _log.info(f"Kontroluji e-maily... {_now()}")
        check_emails()
        time.sleep(CHECK_INTERVAL)

def start_email_checker():
    checker_thread = threading.Thread(target=email_checker_loop, daemon=True)
    checker_thread.start()


# ─── Připomínky ────────────────────────────────────────────────────────────

def send_reminders():
    """Pošle e-mail adminovi o ticketech bez vyřešení déle než reminder_days dní."""
    try:
        reminder_days = int(get_config('reminder_days', '0'))
        if reminder_days <= 0:
            return
        admin_email = get_config('admin_email', '') or SMTP_EMAIL
        if not admin_email:
            return
        conn = get_db()
        cutoff = (datetime.datetime.now(tz=_PRAGUE).replace(tzinfo=None) - datetime.timedelta(days=reminder_days)).strftime('%d.%m.%Y %H:%M')
        # Najdi otevřené tickety starší než limit bez připomínky
        rows = conn.execute(
            "SELECT ticket_id, subject, customer_email, date FROM complaints "
            "WHERE status NOT IN ('Vyřešeno','Zamítnuto','Spam') "
            "AND reminded_at IS NULL"
        ).fetchall()
        to_remind = []
        for row in rows:
            try:
                created = datetime.datetime.strptime(row['date'][:16], '%d.%m.%Y %H:%M')
                age = (datetime.datetime.now(tz=_PRAGUE).replace(tzinfo=None) - created).days
                if age >= reminder_days:
                    to_remind.append(dict(row))
            except Exception:
                pass
        conn.close()
        if not to_remind:
            return
        lines = '\n'.join([f"- [{r['ticket_id']}] {r['subject']} ({r['customer_email']}) — {r['date'][:10]}" for r in to_remind])
        body = f"Připomínka: {len(to_remind)} nevyřešených reklamací starších než {reminder_days} dní:\n\n{lines}\n\nhttps://reklamace.eremvole.cz"
        if send_email(admin_email, f"⏰ Připomínka: {len(to_remind)} nevyřešených reklamací", body):
            conn2 = get_db()
            now_str = _now()
            for r in to_remind:
                conn2.execute("UPDATE complaints SET reminded_at=? WHERE ticket_id=?", (now_str, r['ticket_id']))
            conn2.commit()
            conn2.close()
            _log.info(f"Odeslána připomínka pro {len(to_remind)} ticketů")
    except Exception as e:
        _log.warning(f"Chyba při odesílání připomínek: {e}")


def reminder_loop():
    """Kontrola připomínek každou hodinu."""
    while True:
        time.sleep(3600)
        send_reminders()


# ─── Gemini AI ─────────────────────────────────────────────────────────────

def _send_status_auto_reply(ticket_id, customer_email, customer_name, subject):
    """Odešle automatickou odpověď na dotaz o stavu."""
    try:
        sig_html = get_config('admin_signature', 'Martin z eremu')
        name = customer_name or 'zákazníku'
        first_name = name.split()[0] if name and ' ' in name else name
        body = f"""Čau {first_name},

díky za zprávu! Tvůj ticket {ticket_id} máme a koukneme na to co nejdřív.

Jakmile budeme mít novinky, ozveme se. Kdyby bylo cokoliv, napiš nám."""
        send_email(customer_email, f"Re: {subject} [#{ticket_id}]", body, signature_html=sig_html)
        _log.info(f"Auto-reply (status inquiry) odesláno pro {ticket_id}")
    except Exception as e:
        _log.warning(f"Auto-reply selhalo: {e}")


def analyze_complaint(ticket_id, subject, description, customer_email='', customer_name_hint=None, send_confirmation=False):
    """
    Gemini analýza nové reklamace:
    - spam filtr (is_complaint)
    - extrahuje číslo objednávky, jméno zákazníka
    - kategorizuje a navrhuje krátký popis problému
    Výsledky ukládá přímo do DB.
    """
    import json as _json
    api_key = get_config('gemini_api_key', '')
    if not api_key:
        # Bez AI: pokud send_confirmation, pošli potvrzení rovnou
        if send_confirmation:
            send_confirmation_email(customer_email, ticket_id, subject, customer_name_hint)
        return

    try:
        from google import genai
        from google.genai import types as genai_types

        client = genai.Client(api_key=api_key)

        categories_str = ', '.join(COMPLAINT_CATEGORIES)
        prompt = f"""Czech e-shop support system. Analyze this incoming email and return ONLY valid JSON.

From name hint: {customer_name_hint or 'unknown'}
Subject: {subject}
Body: {description[:800]}

Return exactly this JSON (no markdown, no extra text):
{{"is_complaint": true, "customer_name": "Jan Novák or null", "category": "Nedoručení", "order_number": "12345 or null", "problem_summary": "short Czech description max 12 words", "auto_reply_type": "status_inquiry or null", "priority": "medium"}}

Rules:
- is_complaint: true ONLY if real customer complaint about a product/order they actually purchased (delivery, damage, wrong item, refund, warranty). Mark false (spam) if: marketing email, newsletter, auto-reply, out-of-office, dubious/suspicious products (diet patches, weight loss, supplements, MLM, casino, loans, adult content, software licenses), or anything unrelated to a real e-shop order
- customer_name: extract from From header or email signature; null if not found
- category: one of [{categories_str}]; null if is_complaint=false
- order_number: look for #12345, č.obj., objednávka, order patterns; null if not found
- problem_summary: concise Czech description of core issue; null if is_complaint=false
- auto_reply_type: "status_inquiry" ONLY if customer is just asking about status of existing order/complaint and no action is needed — set null for all real complaints needing resolution
- priority: one of "low", "medium", "high", "critical" based on urgency. critical=safety issue or very angry customer demanding legal action; high=damaged goods, long overdue delivery, refund required; medium=normal complaint; low=minor issue or question
- Return ONLY the JSON object"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            config=genai_types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=256,
                thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
            ),
            contents=prompt,
        )

        raw = response.text.strip()
        raw = re.sub(r'```(?:json)?', '', raw).strip()

        _priority_map = {'low': 'Nízká', 'medium': 'Střední', 'high': 'Vysoká', 'critical': 'Kritická'}

        is_complaint = True
        extracted_name = customer_name_hint
        category = None
        order_number = None
        problem_summary = None
        auto_reply_type = None
        priority_en = None

        try:
            data = _json.loads(raw)
            is_complaint = bool(data.get('is_complaint', True))
            extracted_name = data.get('customer_name') or customer_name_hint
            category = data.get('category') or None
            order_number = data.get('order_number') or None
            problem_summary = data.get('problem_summary') or None
            auto_reply_type = data.get('auto_reply_type') or None
            priority_en = data.get('priority') or None
        except Exception:
            m_complaint = re.search(r'"is_complaint"\s*:\s*(true|false)', raw)
            m_name = re.search(r'"customer_name"\s*:\s*(?:"([^"]*?)"|null)', raw)
            m_cat = re.search(r'"category"\s*:\s*(?:"([^"]*?)"|null)', raw)
            m_order = re.search(r'"order_number"\s*:\s*(?:"([^"]*?)"|null)', raw)
            m_summary = re.search(r'"problem_summary"\s*:\s*(?:"([^"]*?)"|null)', raw)
            m_auto = re.search(r'"auto_reply_type"\s*:\s*(?:"([^"]*?)"|null)', raw)
            m_prio = re.search(r'"priority"\s*:\s*(?:"([^"]*?)"|null)', raw)
            if m_complaint:
                is_complaint = m_complaint.group(1) == 'true'
            if m_name and m_name.group(1):
                extracted_name = m_name.group(1)
            if m_cat and m_cat.group(1):
                category = m_cat.group(1)
            if m_order and m_order.group(1):
                order_number = m_order.group(1)
            if m_summary and m_summary.group(1):
                problem_summary = m_summary.group(1)
            if m_auto and m_auto.group(1):
                auto_reply_type = m_auto.group(1)
            if m_prio and m_prio.group(1):
                priority_en = m_prio.group(1)

        priority_cz = _priority_map.get((priority_en or '').lower(), None)

        # Ulož výsledky do DB
        conn = get_db()
        if is_complaint:
            if priority_cz:
                conn.execute(
                    'UPDATE complaints SET order_number=?, problem_summary=?, category=?, customer_name=?, priority=? WHERE ticket_id=?',
                    (order_number, problem_summary, category, extracted_name, priority_cz, ticket_id)
                )
            else:
                conn.execute(
                    'UPDATE complaints SET order_number=?, problem_summary=?, category=?, customer_name=? WHERE ticket_id=?',
                    (order_number, problem_summary, category, extracted_name, ticket_id)
                )
        else:
            conn.execute(
                'UPDATE complaints SET status=?, customer_name=? WHERE ticket_id=?',
                ('Spam', extracted_name, ticket_id)
            )
        conn.commit()
        conn.close()

        if is_complaint:
            _log.info(f"AI analýza {ticket_id}: kategorie={category}, objednávka={order_number}, jméno={extracted_name}")
            if send_confirmation:
                send_confirmation_email(customer_email, ticket_id, subject, extracted_name)
            # Auto-reply na jednoduché dotazy o stavu
            if auto_reply_type == 'status_inquiry' and customer_email and get_config('smart_auto_reply_enabled', '0') == '1':
                _send_status_auto_reply(ticket_id, customer_email, extracted_name, subject)
        else:
            _log.info(f"Spam detekován: {ticket_id} — přesunuto do spamu")

    except Exception as e:
        _log.error(f"AI analýza {ticket_id} selhala: {e}")
        # Pokud analýza selže, pošli potvrzení aby zákazník nedostal nic
        if send_confirmation:
            send_confirmation_email(customer_email, ticket_id, subject, customer_name_hint)


def analyze_pending_complaints():
    """Zpracuje všechny reklamace bez AI analýzy na pozadí."""
    try:
        conn = get_db()
        pending = conn.execute(
            'SELECT ticket_id, subject, description FROM complaints WHERE problem_summary IS NULL'
        ).fetchall()
        conn.close()
        for row in pending:
            analyze_complaint(row['ticket_id'], row['subject'], row['description'] or '', send_confirmation=False)
            time.sleep(0.5)  # Rate-limit
    except Exception as e:
        _log.warning(f"analyze_pending: {e}")


def get_gemini_suggestion(subject, description, customer_email, customer_name=None, admin_email=None, conversation=None):
    """Vygenerování návrhu odpovědi pomocí Gemini AI — reaguje na poslední zprávu zákazníka v kontextu celé konverzace."""
    api_key = get_config('gemini_api_key', '')
    if not api_key:
        return None, "Gemini API klíč není nastaven. Přidej ho v Nastavení."
    try:
        from google import genai
        from google.genai import types as genai_types
        client = genai.Client(api_key=api_key)
        system_prompt = """Jsi zákaznická podpora e-shopu erem. Piš jako mladej sympatickej kluk — nespisovně, s tykáním, přátelsky a s lehkým humorem. Nejsi robot, jsi člověk.

Pravidla:
- Vždy tykej, žádné vykání
- Začni "Čau," nebo "Ahoj," nebo oslovi jménem pokud ho znáš
- Piš hovorově a přirozeně — jako bys psal kamarádovi, ale řešíš problém
- Projev pochopení lidsky, ne firemně (např. "To je průser, omlouvám se za to" místo "Lítostivě konstatujeme")
- Navrhni konkrétní řešení nebo napiš že se ozveš
- Max 80 slov, krátce a k věci
- Nepřidávej podpis ani rozloučení — to doplní systém automaticky
- Nevymýšlej fakta — pokud nevíš, napiš že se ozveš co nejdřív"""

        name_str = f"{customer_name} ({customer_email})" if customer_name else customer_email

        # Sestav historii konverzace pro kontext
        if conversation and len(conversation) > 1:
            conv_lines = []
            for msg in conversation:
                if msg['type'] == 'customer':
                    conv_lines.append(f"[ZÁKAZNÍK {msg['time']}]: {msg['text']}")
                elif msg['type'] == 'reply':
                    conv_lines.append(f"[PODPORA {msg['time']}]: {msg['text']}")
            # Poslední zpráva zákazníka
            last_customer = next(
                (msg for msg in reversed(conversation) if msg['type'] == 'customer'), None
            )
            last_msg = last_customer['text'] if last_customer else description
            conv_context = '\n\n'.join(conv_lines)
            user_message = f"""Zákazník: {name_str}
Předmět: {subject}

=== CELÁ KONVERZACE ===
{conv_context}

=== NAPIŠ ODPOVĚĎ NA POSLEDNÍ ZPRÁVU ZÁKAZNÍKA ===
{last_msg}

Oslovi zákazníka jménem pokud ho znáš. Navazuj na předchozí komunikaci."""
        else:
            user_message = f"""Zákazník {name_str} zaslal zprávu:

Předmět: {subject}

{description}

Napiš odpověď zákazníkovi. Oslovi zákazníka jménem pokud ho znáš."""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            config=genai_types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.5,
                max_output_tokens=512,
                thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
            ),
            contents=user_message,
        )
        return response.text, None
    except ImportError:
        return None, "Knihovna google-genai není nainstalována."
    except Exception as e:
        return None, f"Chyba Gemini API: {str(e)}"


# ─── Firebase Auth ─────────────────────────────────────────────────────────

def _decode_jwt_payload(token: str) -> dict:
    """Dekóduje JWT payload bez ověření podpisu."""
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return {}
        payload = parts[1]
        payload += '=' * (4 - len(payload) % 4)
        return _j.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}

def _verify_firebase_token(id_token):
    """
    Ověří Firebase ID token přes Google Identity Toolkit REST API.
    Nepotřebuje firebase-admin ani service account.
    Vrátí dict s uživatelskými daty nebo None při chybě.
    """
    if not FIREBASE_API_KEY or not id_token:
        return None
    try:
        import urllib.request as _urlreq
        url = f'https://identitytoolkit.googleapis.com/v1/accounts:lookup?key={FIREBASE_API_KEY}'
        payload = _json_module.dumps({'idToken': id_token}).encode()
        req = _urlreq.Request(url, data=payload, headers={'Content-Type': 'application/json'})
        with _urlreq.urlopen(req, timeout=8) as resp:
            data = _json_module.loads(resp.read())
            users = data.get('users', [])
            if users:
                # Ověř že token byl vydán pro náš projekt
                jwt_payload = _decode_jwt_payload(id_token)
                token_aud = jwt_payload.get('aud', '')
                if not FIREBASE_PROJECT_ID:
                    _log.error("FIREBASE_PROJECT_ID není nastaven — nelze ověřit JWT audience. Auth odmítnuta.")
                    return None
                if token_aud != FIREBASE_PROJECT_ID:
                    _log.warning(f"Firebase JWT audience mismatch: got '{token_aud[:20]}...', expected project ID")
                    return None
                return users[0]  # {'email': ..., 'localId': ..., 'displayName': ...}
    except Exception as e:
        _log.error(f"FIREBASE_AUTH_FAIL: {e}")
    return None


# ─── Inicializace ──────────────────────────────────────────────────────────

init_db()
start_email_checker()
# Zpracuj existující reklamace bez AI analýzy (po startu na pozadí)
threading.Thread(target=analyze_pending_complaints, daemon=True).start()
threading.Thread(target=reminder_loop, daemon=True).start()


# ─── Autentizace ───────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/api/firebase_auth', methods=['POST'])
def api_firebase_auth():
    """Ověří Firebase ID token, zkontroluje povolené e-maily a vytvoří session."""
    data = request.get_json(silent=True) or {}
    id_token = data.get('idToken', '').strip()
    if not id_token:
        return jsonify({'error': 'Chybí token'}), 400

    user = _verify_firebase_token(id_token)
    if not user:
        return jsonify({'error': 'Neplatný nebo expirovaný token'}), 401

    email = (user.get('email') or '').strip().lower()

    # Kontrola povolených e-mailů
    if FIREBASE_ALLOWED_EMAILS:
        allowed = [e.strip().lower() for e in FIREBASE_ALLOWED_EMAILS.split(',') if e.strip()]
        if email not in allowed:
            return jsonify({'error': f'Přístup odepřen pro {email}. Kontaktuj administrátora.'}), 403

    session['logged_in'] = True
    session['username'] = user.get('displayName') or email
    session['email'] = email
    session.permanent = True
    _log.info(f"FIREBASE_LOGIN email={email}")
    return jsonify({'ok': True})


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
        if _check_rate_limit(ip):
            _log.warning(f"RATE_LIMIT ip={ip}")
            flash('Příliš mnoho pokusů. Zkus to za chvíli.', 'error')
            return render_template('login.html',
                firebase_enabled=bool(FIREBASE_API_KEY),
                firebase_api_key=FIREBASE_API_KEY,
                firebase_auth_domain=FIREBASE_AUTH_DOMAIN,
                firebase_project_id=FIREBASE_PROJECT_ID,
                firebase_app_id=FIREBASE_APP_ID,
            ), 429
        if not _csrf_valid():
            flash('Neplatný požadavek. Zkus to znovu.', 'error')
            return redirect(url_for('login'))
        username = request.form.get('username')
        password = request.form.get('password')
        if secrets.compare_digest(str(username), str(ADMIN_USERNAME)) and secrets.compare_digest(str(password), str(ADMIN_PASSWORD)):
            session['logged_in'] = True
            session['username'] = username
            session.permanent = True
            _log.info(f"LOGIN_OK ip={ip} user={username}")
            flash('Úspěšně přihlášen!', 'success')
            return redirect(url_for('index'))
        else:
            _log.warning(f"LOGIN_FAIL ip={ip}")
            flash('Nesprávné přihlašovací údaje!', 'error')
    return render_template('login.html',
        firebase_enabled=bool(FIREBASE_API_KEY),
        firebase_api_key=FIREBASE_API_KEY,
        firebase_auth_domain=FIREBASE_AUTH_DOMAIN,
        firebase_project_id=FIREBASE_PROJECT_ID,
        firebase_app_id=FIREBASE_APP_ID,
    )

@app.route('/logout')
def logout():
    session.clear()
    flash('Odhlášen', 'success')
    return redirect(url_for('login'))


# ─── Hlavní routy ──────────────────────────────────────────────────────────

@app.route('/')
@login_required
def index():
    conn = get_db()
    all_raw = conn.execute('SELECT * FROM complaints ORDER BY date DESC').fetchall()
    conn.close()
    sla_days = int(get_config('sla_days', '3'))
    complaints_all = []
    spam_all = []
    for c in all_raw:
        d = dict(c)
        if (d.get('status') or '').lower() == 'spam':
            spam_all.append(d)
        else:
            complaints_all.append(_enrich_sla(d, sla_days))
    complaints      = complaints_all[:10]
    spam_list       = spam_all[:10]
    complaints_total = len(complaints_all)
    spam_total       = len(spam_all)
    current_email = session.get('email', '')
    return render_template('index.html',
                           complaints=complaints, complaints_total=complaints_total,
                           spam_list=spam_list, spam_total=spam_total,
                           sla_days=sla_days, categories=COMPLAINT_CATEGORIES,
                           current_email=current_email)

def parse_conversation(complaint_dict):
    """Sestaví chronologický seznam zpráv z původního e-mailu + poznámek."""
    items = []
    # 1. Původní zpráva zákazníka
    items.append({
        'type': 'customer',
        'time': complaint_dict.get('date', ''),
        'author': complaint_dict.get('customer_name') or complaint_dict.get('customer_email', ''),
        'text': strip_email_quote(complaint_dict.get('description', '') or ''),
    })
    # 2. Parsuj poznámky
    notes = complaint_dict.get('notes') or ''
    if notes:
        # Každý záznam začíná [DD.MM.YYYY HH:MM]
        parts = re.split(r'(\[\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}\])', notes)
        i = 1
        while i < len(parts) - 1:
            timestamp = parts[i].strip('[]')
            content = parts[i + 1].strip()
            if '📤 Odeslaná odpověď zákazníkovi:' in content:
                text = content.replace('📤 Odeslaná odpověď zákazníkovi:', '').strip()
                items.append({'type': 'reply', 'time': timestamp, 'author': 'erem tým', 'text': text})
            elif '📨 Odpověď zákazníka' in content:
                m = re.search(r'Odpověď zákazníka \(([^)]+)\):\n(.+)', content, re.DOTALL)
                author = m.group(1) if m else 'zákazník'
                text = strip_email_quote((m.group(2).strip() if m else content))
                if text:
                    items.append({'type': 'customer', 'time': timestamp, 'author': author, 'text': text})
            elif content:
                items.append({'type': 'note', 'time': timestamp, 'author': 'interní', 'text': content})
            i += 2
    return items


@app.route('/complaint/<ticket_id>')
@login_required
def complaint_detail(ticket_id):
    if not re.match(r'^RK-\d{1,6}$', ticket_id):
        abort(404)
    conn = get_db()
    complaint = conn.execute('SELECT * FROM complaints WHERE ticket_id = ?', (ticket_id,)).fetchone()
    if not complaint:
        conn.close()
        flash('Ticket nenalezen', 'error')
        return redirect(url_for('index'))
    # Označit odpověď zákazníka jako přečtenou
    if complaint['customer_unread']:
        conn.execute('UPDATE complaints SET customer_unread=0 WHERE ticket_id=?', (ticket_id,))
        conn.commit()
    # Předchozí tickety stejného zákazníka
    customer_email = complaint['customer_email']
    prev_tickets = conn.execute(
        'SELECT ticket_id, date, subject, status FROM complaints '
        'WHERE customer_email=? AND ticket_id!=? ORDER BY date DESC LIMIT 5',
        (customer_email, ticket_id)
    ).fetchall()
    conn.close()
    d = dict(complaint)
    d['customer_unread'] = 0  # zobrazujeme jako přečtené
    conversation = parse_conversation(d)
    admin_signature = get_admin_signature(session.get('email'))
    # Seznam adminů z env
    admin_list = [e.strip() for e in FIREBASE_ALLOWED_EMAILS.split(',') if e.strip()] if FIREBASE_ALLOWED_EMAILS else []
    return render_template('detail.html', complaint=d, conversation=conversation,
                           admin_signature=admin_signature,
                           admin_list=admin_list,
                           prev_tickets=[dict(t) for t in prev_tickets])

@app.route('/update_status/<ticket_id>', methods=['POST'])
@login_required
def update_status(ticket_id):
    if not re.match(r'^RK-\d{1,6}$', ticket_id):
        abort(404)
    new_status = request.form.get('status')
    VALID_STATUSES = {'Nová', 'V řešení', 'Vyřešeno', 'Zamítnuto', 'Spam'}
    if new_status and new_status not in VALID_STATUSES:
        flash('Neplatný status', 'error')
        return redirect(url_for('complaint_detail', ticket_id=ticket_id))
    notes = request.form.get('notes', '')
    category = request.form.get('category', '').strip()
    priority = request.form.get('priority', '').strip()
    conn = get_db()
    complaint = conn.execute('SELECT notes FROM complaints WHERE ticket_id = ?', (ticket_id,)).fetchone()
    if complaint:
        conn.execute('UPDATE complaints SET status = ? WHERE ticket_id = ?', (new_status, ticket_id))
        if category:
            conn.execute('UPDATE complaints SET category = ? WHERE ticket_id = ?', (category, ticket_id))
        if priority in ('Nízká', 'Střední', 'Vysoká', 'Kritická'):
            conn.execute('UPDATE complaints SET priority = ? WHERE ticket_id = ?', (priority, ticket_id))
        if notes:
            current_notes = complaint['notes'] or ''
            timestamp = _now()
            new_notes = f"{current_notes}\n[{timestamp}] {notes}".strip()
            conn.execute('UPDATE complaints SET notes = ? WHERE ticket_id = ?', (new_notes, ticket_id))
        conn.commit()
        flash('Status aktualizován', 'success')
    conn.close()
    return redirect(url_for('complaint_detail', ticket_id=ticket_id))


@app.route('/assign_ticket/<ticket_id>', methods=['POST'])
@login_required
def assign_ticket(ticket_id):
    if not re.match(r'^RK-\d{1,6}$', ticket_id):
        abort(404)
    assigned_to = request.form.get('assigned_to', '').strip()
    conn = get_db()
    conn.execute('UPDATE complaints SET assigned_to = ? WHERE ticket_id = ?', (assigned_to or None, ticket_id))
    conn.commit()
    conn.close()
    flash(f'Ticket přiřazen: {assigned_to}' if assigned_to else 'Přiřazení odstraněno', 'success')
    return redirect(url_for('complaint_detail', ticket_id=ticket_id))


@app.route('/bulk_action', methods=['POST'])
@login_required
def bulk_action():
    ticket_ids = request.form.getlist('ticket_ids[]')
    action = request.form.get('action', '')
    if not ticket_ids:
        flash('Žádné tickety nebyly vybrány', 'error')
        return redirect(url_for('index'))
    # Validace ticket_id formátu v bulk akci
    ticket_ids = [tid for tid in ticket_ids if re.match(r'^RK-\d{1,6}$', tid)]
    if not ticket_ids:
        flash('Žádné platné tickety nebyly vybrány', 'error')
        return redirect(url_for('index'))
    _log.warning(f"BULK_ACTION action={action} count={len(ticket_ids)} by={session.get('email')}")
    conn = get_db()
    if action == 'resolve':
        for tid in ticket_ids:
            conn.execute("UPDATE complaints SET status='Vyřešeno' WHERE ticket_id=?", (tid,))
        conn.commit()
        flash(f'Vyřešeno {len(ticket_ids)} ticketů', 'success')
    elif action == 'spam':
        for tid in ticket_ids:
            conn.execute("UPDATE complaints SET status='Spam' WHERE ticket_id=?", (tid,))
        conn.commit()
        flash(f'{len(ticket_ids)} ticketů označeno jako spam', 'success')
    elif action == 'delete':
        for tid in ticket_ids:
            conn.execute("DELETE FROM complaints WHERE ticket_id=?", (tid,))
        conn.commit()
        flash(f'Smazáno {len(ticket_ids)} ticketů', 'success')
    else:
        flash('Neznámá akce', 'error')
    conn.close()
    return redirect(url_for('index'))

@app.route('/mark_spam/<ticket_id>', methods=['POST'])
@login_required
def mark_spam(ticket_id):
    if not re.match(r'^RK-\d{1,6}$', ticket_id):
        abort(404)
    conn = get_db()
    conn.execute('UPDATE complaints SET status=? WHERE ticket_id=?', ('Spam', ticket_id))
    conn.commit()
    conn.close()
    flash('Přesunuto do spamu', 'success')
    return redirect(url_for('index'))

@app.route('/unmark_spam/<ticket_id>', methods=['POST'])
@login_required
def unmark_spam(ticket_id):
    if not re.match(r'^RK-\d{1,6}$', ticket_id):
        abort(404)
    conn = get_db()
    conn.execute('UPDATE complaints SET status=? WHERE ticket_id=?', ('Nová', ticket_id))
    conn.commit()
    conn.close()
    flash('Obnoveno jako nový ticket', 'success')
    return redirect(url_for('complaint_detail', ticket_id=ticket_id))

@app.route('/delete_ticket/<ticket_id>', methods=['POST'])
@login_required
def delete_ticket(ticket_id):
    if not re.match(r'^RK-\d{1,6}$', ticket_id):
        abort(404)
    _log.warning(f"DELETE_TICKET id={ticket_id} by={session.get('email')}")
    conn = get_db()
    conn.execute('DELETE FROM complaints WHERE ticket_id=?', (ticket_id,))
    conn.commit()
    conn.close()
    flash(f'Ticket {ticket_id} byl smazán', 'success')
    return redirect(url_for('index'))

@app.route('/resend_confirmation/<ticket_id>', methods=['POST'])
@login_required
def resend_confirmation(ticket_id):
    if not re.match(r'^RK-\d{1,6}$', ticket_id):
        abort(404)
    conn = get_db()
    t = conn.execute('SELECT * FROM complaints WHERE ticket_id=?', (ticket_id,)).fetchone()
    conn.close()
    if not t:
        flash('Ticket nenalezen', 'error')
        return redirect(url_for('index'))
    ok = send_confirmation_email(t['customer_email'], ticket_id, t['subject'], t['customer_name'], force=True)
    if ok:
        flash(f'Potvrzení odesláno na {t["customer_email"]}', 'success')
    else:
        flash('Odeslání selhalo — zkontroluj SMTP nastavení nebo je auto-reply vypnuto', 'error')
    return redirect(url_for('complaint_detail', ticket_id=ticket_id))

_manual_check_running = False

@app.route('/manual_check')
@login_required
def manual_check():
    global _manual_check_running
    if _check_api_rate_limit(session.get('email', 'anon')):
        flash('Příliš mnoho požadavků, zkus za chvíli.', 'error')
        return redirect(url_for('index'))
    with _manual_check_lock:
        if _manual_check_running:
            flash('Kontrola již probíhá…', 'info')
            return redirect(url_for('index'))
        _manual_check_running = True

    def _run():
        global _manual_check_running
        try:
            check_emails()
        finally:
            with _manual_check_lock:
                _manual_check_running = False

    threading.Thread(target=_run, daemon=True).start()
    flash('Kontrola e-mailů spuštěna', 'success')
    return redirect(url_for('index'))

@app.route('/stats')
@login_required
def stats():
    conn = get_db()
    now = datetime.datetime.now(tz=_PRAGUE).replace(tzinfo=None)
    today_str = now.strftime('%d.%m.%Y')
    week_start = (now - datetime.timedelta(days=now.weekday())).strftime('%d.%m.%Y')
    month_start = now.strftime('01.%m.%Y')

    all_rows = conn.execute('SELECT * FROM complaints').fetchall()

    stats_data = {
        'total': 0, 'total_today': 0, 'total_week': 0, 'total_month': 0,
        'nova': 0, 'v_reseni': 0, 'vyreseno': 0, 'zamitnuto': 0, 'spam': 0,
        'avg_response_hours': None,
    }
    response_times = []

    for c in all_rows:
        d = dict(c)
        status = (d.get('status') or '').lower()
        stats_data['total'] += 1
        date_str = (d.get('date') or '')[:10]
        if date_str == today_str:
            stats_data['total_today'] += 1
        if date_str >= week_start[:10]:
            stats_data['total_week'] += 1
        if date_str >= month_start[:10]:
            stats_data['total_month'] += 1
        if 'spam' in status:
            stats_data['spam'] += 1
        elif 'nová' in status or 'nova' in status:
            stats_data['nova'] += 1
        elif 'vyřešen' in status or 'vyreseno' in status:
            stats_data['vyreseno'] += 1
            # Průměrná doba odpovědi (jen vyřešené s last_reply_at)
            if d.get('last_reply_at') and d.get('date'):
                try:
                    t_start = datetime.datetime.strptime(d['date'][:16], '%d.%m.%Y %H:%M')
                    t_end = datetime.datetime.strptime(d['last_reply_at'][:16], '%d.%m.%Y %H:%M')
                    diff_h = (t_end - t_start).total_seconds() / 3600
                    if diff_h >= 0:
                        response_times.append(diff_h)
                except Exception:
                    pass
        elif 'zamítn' in status or 'zamitn' in status:
            stats_data['zamitnuto'] += 1
        elif 'řešen' in status or 'resen' in status:
            stats_data['v_reseni'] += 1

    if response_times:
        avg_h = sum(response_times) / len(response_times)
        if avg_h < 24:
            stats_data['avg_response_hours'] = f'{avg_h:.1f} hod'
        else:
            stats_data['avg_response_hours'] = f'{avg_h/24:.1f} dní'

    # Top 5 kategorií
    cat_rows = conn.execute(
        "SELECT category, COUNT(*) as cnt FROM complaints "
        "WHERE category IS NOT NULL AND category != '' AND status != 'Spam' "
        "GROUP BY category ORDER BY cnt DESC LIMIT 5"
    ).fetchall()
    top_categories = [{'name': r['category'], 'count': r['cnt']} for r in cat_rows]

    # Tickety za posledních 30 dní (GROUP BY datum)
    thirty_days_ago = (now - datetime.timedelta(days=29)).strftime('%d.%m.%Y')
    daily_rows = conn.execute(
        "SELECT substr(date,1,10) as day, COUNT(*) as cnt FROM complaints "
        "WHERE date >= ? AND status != 'Spam' GROUP BY day ORDER BY day",
        (thirty_days_ago,)
    ).fetchall()
    # Sestavíme plný seznam 30 dní
    daily_labels = []
    daily_counts = []
    for i in range(29, -1, -1):
        day = (now - datetime.timedelta(days=i)).strftime('%d.%m.%Y')
        daily_labels.append(day[:5])  # DD.MM
        cnt = 0
        for r in daily_rows:
            if r['day'] == day:
                cnt = r['cnt']
                break
        daily_counts.append(cnt)

    # Výkon adminů (assigned_to)
    admin_rows = conn.execute(
        "SELECT assigned_to, COUNT(*) as total, "
        "SUM(CASE WHEN status='Vyřešeno' THEN 1 ELSE 0 END) as resolved "
        "FROM complaints WHERE assigned_to IS NOT NULL AND assigned_to != '' "
        "GROUP BY assigned_to ORDER BY resolved DESC"
    ).fetchall()
    admin_perf = [{'name': r['assigned_to'], 'total': r['total'], 'resolved': r['resolved']} for r in admin_rows]

    conn.close()
    return render_template('stats.html', stats=stats_data,
                           top_categories=top_categories,
                           daily_labels=daily_labels,
                           daily_counts=daily_counts,
                           admin_perf=admin_perf)


# ─── Nastavení ─────────────────────────────────────────────────────────────

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        auto_reply_enabled = '1' if request.form.get('auto_reply_enabled') == '1' else '0'
        auto_reply_template = _sanitize_rich_html(request.form.get('auto_reply_template', DEFAULT_AUTO_REPLY_TEMPLATE))
        gemini_api_key = request.form.get('gemini_api_key', '').strip()
        sla_days = request.form.get('sla_days', '3').strip()
        set_config('auto_reply_enabled', auto_reply_enabled)
        set_config('auto_reply_template', auto_reply_template)
        if gemini_api_key:
            set_config('gemini_api_key', gemini_api_key)
        if sla_days.isdigit() and 1 <= int(sla_days) <= 90:
            set_config('sla_days', sla_days)
        reminder_days = request.form.get('reminder_days', '0').strip()
        if reminder_days.isdigit() and 0 <= int(reminder_days) <= 365:
            set_config('reminder_days', reminder_days)
        admin_email = request.form.get('admin_email', '').strip()
        if admin_email:
            set_config('admin_email', admin_email)
        smart_auto_reply = '1' if request.form.get('smart_auto_reply_enabled') == '1' else '0'
        set_config('smart_auto_reply_enabled', smart_auto_reply)
        admin_signature = _sanitize_rich_html(request.form.get('admin_signature', '').strip())
        if admin_signature:
            _sig_key = f'admin_signature:{session["email"]}' if session.get('email') else 'admin_signature'
            set_config(_sig_key, admin_signature)
        admin_notify_email = request.form.get('admin_notify_email', '').strip()
        set_config('admin_notify_email', admin_notify_email)
        flash('Nastavení uloženo', 'success')
        return redirect(url_for('settings'))

    config = {
        'auto_reply_enabled': get_config('auto_reply_enabled', '1') == '1',
        'auto_reply_template': get_config('auto_reply_template', DEFAULT_AUTO_REPLY_TEMPLATE),
        'gemini_api_key': get_config('gemini_api_key', ''),
        'sla_days': get_config('sla_days', '3'),
        'reply_templates': get_reply_templates(),
        'reminder_days': get_config('reminder_days', '0'),
        'admin_email': get_config('admin_email', ''),
        'smart_auto_reply_enabled': get_config('smart_auto_reply_enabled', '0') == '1',
        'admin_signature': get_admin_signature(session.get('email')),
        'admin_notify_email': get_config('admin_notify_email', ''),
    }
    return render_template('settings.html', config=config)


# ─── Odpověď zákazníkovi ───────────────────────────────────────────────────

@app.route('/send_reply/<ticket_id>', methods=['POST'])
@login_required
def send_reply(ticket_id):
    """Odeslání manuální odpovědi zákazníkovi"""
    if not re.match(r'^RK-\d{1,6}$', ticket_id):
        abort(404)
    reply_html = request.form.get('reply_html', '').strip()
    reply_text = request.form.get('reply_text', '').strip()
    # Zjisti plain text pro validaci a logování
    plain_text = _strip_html(reply_html) if reply_html else reply_text
    if not plain_text and not reply_html:
        flash('Zpráva nesmí být prázdná', 'error')
        return redirect(url_for('complaint_detail', ticket_id=ticket_id))

    conn = get_db()
    complaint = conn.execute('SELECT * FROM complaints WHERE ticket_id = ?', (ticket_id,)).fetchone()
    conn.close()

    if not complaint:
        flash('Ticket nenalezen', 'error')
        return redirect(url_for('index'))

    subject = f"Re: {complaint['subject']} [#{ticket_id}]"
    thread_msg_id = complaint['thread_msg_id'] if 'thread_msg_id' in complaint.keys() else None
    thread_refs = complaint['thread_refs'] if 'thread_refs' in complaint.keys() else None
    # Podpis je předvyplněn v editoru (reply_html ho již obsahuje) — nepředáváme zvlášť
    if send_email(complaint['customer_email'], subject, plain_text, body_html=reply_html or None,
                  in_reply_to=thread_msg_id, references=thread_refs):
        # Zaloguj odeslanou odpověď do poznámek
        conn = get_db()
        current_notes = complaint['notes'] or ''
        timestamp = _now()
        note = f"[{timestamp}] 📤 Odeslaná odpověď zákazníkovi:\n{plain_text}"
        new_notes = f"{current_notes}\n{note}".strip()
        # Pokud je ticket Nová, přesuň do V řešení
        new_status = complaint['status']
        if new_status == 'Nová':
            new_status = 'V řešení'
        conn.execute('UPDATE complaints SET notes=?, last_reply_at=?, status=? WHERE ticket_id=?',
                     (new_notes, timestamp, new_status, ticket_id))
        conn.commit()
        conn.close()
        flash('Odpověď byla odeslána zákazníkovi', 'success')
    else:
        flash('Chyba při odesílání odpovědi', 'error')

    return redirect(url_for('complaint_detail', ticket_id=ticket_id))


# ─── Gemini API endpoint ────────────────────────────────────────────────────

@app.route('/api/suggest_reply/<ticket_id>', methods=['POST'])
@login_required
def suggest_reply(ticket_id):
    """Návrh odpovědi pomocí Gemini AI"""
    if not re.match(r'^RK-\d{1,6}$', ticket_id):
        abort(404)
    if _check_api_rate_limit(session.get('email', 'anon')):
        return jsonify({'error': 'Příliš mnoho požadavků, zkus za chvíli'}), 429
    conn = get_db()
    complaint = conn.execute('SELECT * FROM complaints WHERE ticket_id = ?', (ticket_id,)).fetchone()
    conn.close()

    if not complaint:
        return jsonify({'error': 'Ticket nenalezen'}), 404

    # Sestav plnou konverzaci pro kontext AI
    conversation = parse_conversation(dict(complaint))

    suggestion, error = get_gemini_suggestion(
        subject=complaint['subject'],
        description=complaint['description'] or '',
        customer_email=complaint['customer_email'],
        customer_name=complaint['customer_name'] if 'customer_name' in complaint.keys() else None,
        admin_email=session.get('email'),
        conversation=conversation,
    )

    if error:
        return jsonify({'error': error}), 400

    return jsonify({'suggestion': suggestion})


# ─── Šablony odpovědí ───────────────────────────────────────────────────────

@app.route('/api/more_tickets')
@login_required
def api_more_tickets():
    """Vrátí dalších N ticketů jako JSON pro AJAX načítání."""
    kind = request.args.get('kind', 'tickets')   # 'tickets' nebo 'spam'
    try:
        offset = max(0, int(request.args.get('offset', 10)))
        limit  = min(50, max(1, int(request.args.get('limit', 10))))
    except (ValueError, TypeError):
        return jsonify({'error': 'Neplatné parametry'}), 400
    sla_days = int(get_config('sla_days', '3'))

    conn = get_db()
    all_raw = conn.execute('SELECT * FROM complaints ORDER BY date DESC').fetchall()
    conn.close()

    items = []
    for c in all_raw:
        d = dict(c)
        is_spam = (d.get('status') or '').lower() == 'spam'
        if kind == 'spam' and is_spam:
            items.append(d)
        elif kind == 'tickets' and not is_spam:
            items.append(_enrich_sla(d, sla_days))

    batch = items[offset:offset + limit]
    total = len(items)
    has_more = (offset + limit) < total

    return jsonify({
        'items': batch,
        'has_more': has_more,
        'next_offset': offset + limit,
        'total': total,
    })

@app.route('/api/templates')
@login_required
def api_templates():
    return jsonify(get_reply_templates())

@app.route('/settings/templates/add', methods=['POST'])
@login_required
def add_template():
    name = request.form.get('tpl_name', '').strip()
    body = request.form.get('tpl_body', '').strip()
    if name and body:
        conn = get_db()
        conn.execute('INSERT INTO reply_templates (name, body) VALUES (?, ?)', (name, body))
        conn.commit()
        conn.close()
        flash('Šablona přidána', 'success')
    else:
        flash('Vyplňte název i text šablony', 'error')
    return redirect(url_for('settings') + '#templates')

@app.route('/settings/templates/delete/<int:template_id>', methods=['POST'])
@login_required
def delete_template(template_id):
    conn = get_db()
    conn.execute('DELETE FROM reply_templates WHERE id = ?', (template_id,))
    conn.commit()
    conn.close()
    flash('Šablona smazána', 'success')
    return redirect(url_for('settings') + '#templates')


# ─── AI analýza ─────────────────────────────────────────────────────────────

@app.route('/api/analyze/<ticket_id>', methods=['POST'])
@login_required
def api_analyze(ticket_id):
    """Spustí AI analýzu jedné reklamace."""
    if not re.match(r'^RK-\d{1,6}$', ticket_id):
        abort(404)
    conn = get_db()
    complaint = conn.execute('SELECT * FROM complaints WHERE ticket_id=?', (ticket_id,)).fetchone()
    conn.close()
    if not complaint:
        return jsonify({'error': 'Nenalezeno'}), 404
    threading.Thread(
        target=analyze_complaint,
        args=(ticket_id, complaint['subject'], complaint['description'] or ''),
        daemon=True
    ).start()
    return jsonify({'status': 'started'})


@app.route('/api/analyze_all', methods=['POST'])
@login_required
def api_analyze_all():
    """Spustí AI analýzu všech dosud nezpracovaných reklamací."""
    threading.Thread(target=analyze_pending_complaints, daemon=True).start()
    return jsonify({'status': 'started'})


# ─── Health check ───────────────────────────────────────────────────────────

@app.route('/health')
def health():
    return jsonify({'status': 'ok'}), 200


# ─── Polling — Push notifikace ──────────────────────────────────────────────

@app.route('/api/events')
@login_required
def sse_events():
    """Polling endpoint — vrátí počet ticketů a počet nepřečtených odpovědí zákazníků"""
    conn = get_db()
    unread = conn.execute('SELECT COUNT(*) FROM complaints WHERE customer_unread=1').fetchone()[0]
    conn.close()
    return jsonify({'count': _last_complaint_count, 'unread': unread})


@app.route('/api/sync_history/<ticket_id>', methods=['POST'])
@login_required
def api_sync_history(ticket_id):
    """Synchronizuje e-mailovou historii konverzace z IMAP"""
    if not re.match(r'^RK-\d{1,6}$', ticket_id):
        abort(404)
    count, error = sync_ticket_emails(ticket_id)
    if error and count == 0:
        return jsonify({'error': error}), 400
    return jsonify({'synced': count,
                    'message': f'Synchronizováno {count} nových zpráv'})


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
