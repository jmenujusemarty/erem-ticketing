# erem ticketing

Ticketovací systém pro zákaznickou podporu e-shopů. Přijímá e-maily zákazníků, vytváří tickety, analyzuje je pomocí AI a umožňuje týmu odpovídat přímo z webového rozhraní.

**Živá ukázka:** [reklamace.eremvole.cz](https://reklamace.eremvole.cz)

---

## Funkce

**Příjem a zpracování**
- Automatická kontrola IMAP schránky (každých 5 minut)
- Vytvoření ticketu z každého e-mailu zákazníka
- Automatický potvrzovací e-mail zákazníkovi (ve vlákně původního e-mailu)
- Detekce spamu a nerelevantních zpráv pomocí AI

**AI (Gemini)**
- Automatická kategorizace ticketu (Nedoručení, Poškození, Vrácení…)
- Shrnutí problému ve 12 slovech
- Detekce čísla objednávky
- Návrh odpovědi v tónu erem (tykání, neformálně, s humorem)
- Smart auto-reply pro dotazy na stav objednávky

**Správa ticketů**
- Statusy: Nová / V řešení / Vyřešeno / Zamítnuto / Spam
- Priority: Nízká / Střední / Vysoká / Kritická
- Přiřazení ticketu konkrétnímu členovi týmu
- Zákaznická historie (předchozí tickety od stejného zákazníka)
- Bulk akce (hromadné vyřešení, spam, smazání)
- Full-text vyhledávání

**Komunikace**
- Rich text editor pro odpovědi (bold, italic, links, barvy)
- Šablony odpovědí s proměnnými
- Odpovědi zůstávají ve stejném e-mailovém vlákně
- Per-user podpis admina

**Statistiky**
- Grafy počtu ticketů za 30 dní
- Breakdown statusů a kategorií
- Průměrná doba odpovědi
- Výkon jednotlivých adminů

**Přihlášení**
- Google Sign-In přes Firebase (primární)
- E-mail + heslo přes Firebase
- Záložní username/password přihlášení

---

## Technický stack

- **Backend:** Python 3.11 + Flask
- **Databáze:** SQLite (WAL mode)
- **AI:** Google Gemini 2.5 Flash
- **Auth:** Firebase Authentication
- **Email:** IMAP (příjem) + SMTP/STARTTLS (odesílání)
- **Server:** Docker + Gunicorn na Hetzner VPS
- **Reverse proxy:** Nginx (externí)

---

## Nasazení (Docker)

### Požadavky
- Docker + Docker Compose
- IMAP/SMTP e-mailový účet
- Firebase projekt (pro přihlašování)
- Google Gemini API klíč (pro AI funkce)

### 1. Klonuj repozitář

```bash
git clone https://github.com/jmenujusemarty/erem-ticketing.git
cd erem-ticketing
```

### 2. Nastav prostředí

```bash
cp .env.example .env
nano .env
```

### 3. Spusť

```bash
docker compose up -d
```

Aplikace běží na `http://localhost:5000`.

---

## Konfigurace (.env)

### Povinné

```env
# Bezpečnost
SECRET_KEY=               # min. 32 náhodných znaků — POVINNÉ
ADMIN_USERNAME=           # záložní admin login
ADMIN_PASSWORD=           # silné heslo — POVINNÉ

# E-mail (příjem)
IMAP_SERVER=mail.domena.cz
IMAP_PORT=993
IMAP_EMAIL=reklamace@domena.cz
IMAP_PASSWORD=

# E-mail (odesílání)
SMTP_SERVER=mail.domena.cz
SMTP_PORT=587
SMTP_EMAIL=reklamace@domena.cz
SMTP_PASSWORD=
SMTP_FROM_NAME=erem
```

### Volitelné

```env
# Firebase (přihlašování přes Google)
FIREBASE_API_KEY=
FIREBASE_AUTH_DOMAIN=
FIREBASE_PROJECT_ID=
FIREBASE_APP_ID=
FIREBASE_ALLOWED_EMAILS=admin@firma.cz,kolega@firma.cz

# AI
GEMINI_API_KEY=           # nebo nastav v admin rozhraní

# Interval kontroly e-mailů (sekundy, default 300)
CHECK_INTERVAL=300
```

---

## Firebase nastavení

1. Vytvoř projekt na [console.firebase.google.com](https://console.firebase.google.com)
2. Authentication → Sign-in method → povol **Google** a **Email/Password**
3. Authentication → Settings → Authorized domains → přidej svou doménu
4. Project settings → zkopíruj `apiKey`, `authDomain`, `projectId`, `appId` do `.env`
5. Do `FIREBASE_ALLOWED_EMAILS` přidej e-maily adminů (čárkou oddělené)

---

## Bezpečnost

Aplikace implementuje:

- CSRF ochrana na všech POST endpointech
- Content Security Policy hlavičky
- X-Frame-Options, HSTS, nosniff, Referrer-Policy
- Rate limiting na přihlášení (5 pokusů / 5 minut)
- Rate limiting na AI API endpointech
- Firebase JWT ověření včetně `aud` claim
- Whitelist validace statusů a formátu ticket ID
- XSS sanitizace HTML obsahu při ukládání
- Email header injection ochrana
- SMTP s ověřením TLS certifikátu
- SQLite WAL mode s 30s busy timeout
- Strukturované logování s audit trail

**Aplikace odmítne start pokud:**
- `SECRET_KEY` má méně než 32 znaků
- `ADMIN_USERNAME/ADMIN_PASSWORD` jsou výchozí `admin/admin123`

---

## Lokální vývoj

```bash
pip install -r requirements.txt
cp .env.example .env
# uprav .env
python app.py
```

---

## Struktura projektu

```
├── app.py                  # celý backend (Flask routes, IMAP, SMTP, AI)
├── templates/
│   ├── base.html           # layout, navigace, CSS design systém
│   ├── index.html          # seznam ticketů s filtry a vyhledáváním
│   ├── detail.html         # detail ticketu + konverzace + editor odpovědi
│   ├── settings.html       # nastavení systému
│   ├── stats.html          # statistiky a grafy
│   └── login.html          # přihlašovací stránka
├── data/                   # SQLite databáze (není v gitu)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## Licence

Privátní projekt — erem s. r. o.
