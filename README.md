# 🚀 Systém správy reklamací - Webová aplikace

Automatický systém pro zpracování reklamací bez potřeby VPS nebo složité instalace!

## ✨ Co tato verze umí

✅ **Žádný VPS/SSH** - běží v cloudu zdarma  
✅ **Vlastní IMAP/SMTP** - váš e-mailový server  
✅ **SQLite databáze** - místo Google Sheets  
✅ **Admin webové rozhraní** - plná kontrola  
✅ **Automatická kontrola e-mailů** - každých 5 minut  
✅ **Potvrzení zákazníkům** - automaticky  

---

## 🎯 Nasazení na Render.com (DOPORUČENO - 10 minut)

Render.com je **zdarma** a nevyžaduje platební kartu!

### Krok 1: Vytvoř účet na Render.com

1. Jdi na https://render.com
2. Klikni na **"Get Started"** nebo **"Sign Up"**
3. Zaregistruj se pomocí **GitHub** nebo **e-mailu**

### Krok 2: Nahraj kód na GitHub

**Varianta A: Máš GitHub účet**

1. Vytvoř nový repozitář na https://github.com/new
2. Nahraj tam všechny soubory z této složky
3. Pokračuj krokem 3

**Varianta B: Nemáš GitHub** (použij ZIP upload)

Můžeš nasadit i bez GitHubu - pokračuj krokem 3 a nahraj ZIP

### Krok 3: Vytvoř Web Service na Render

1. Přihlaš se na https://dashboard.render.com
2. Klikni **"New +"** → **"Web Service"**
3. Připoj svůj GitHub repozitář (nebo nahraj ZIP)
4. Vyplň:
   - **Name**: `reklamacni-system` (nebo libovolný název)
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
   - **Instance Type**: `Free`

### Krok 4: Nastav environment variables (důležité!)

V sekci **Environment Variables** přidej:

```
IMAP_SERVER = mail.tvoje-domena.cz
IMAP_PORT = 993
IMAP_EMAIL = reklamace@tvoje-domena.cz
IMAP_PASSWORD = tvoje-heslo

SMTP_SERVER = mail.tvoje-domena.cz
SMTP_PORT = 587
SMTP_EMAIL = reklamace@tvoje-domena.cz
SMTP_PASSWORD = tvoje-heslo

ADMIN_USERNAME = admin
ADMIN_PASSWORD = tvoje-silne-heslo

SECRET_KEY = nahodny-retezec-asdfghjkl123456789
CHECK_INTERVAL = 300
```

**Poznámka:** SECRET_KEY může Render vygenerovat automaticky - klikni na "Generate" u tohoto pole.

### Krok 5: Deploy!

1. Klikni **"Create Web Service"**
2. Render začne buildovat aplikaci (zabere ~2 minuty)
3. Po dokončení dostaneš URL typu: `https://reklamacni-system.onrender.com`

### Krok 6: Přihlas se

1. Otevři URL z kroku 5
2. Přihlaš se pomocí `ADMIN_USERNAME` a `ADMIN_PASSWORD`
3. **Hotovo!** 🎉

---

## ⚠️ Důležité o FREE plánu na Render.com

**Free tier má limitace:**
- ✅ Aplikace běží **zdarma**
- ⚠️ Po **15 minutách nečinnosti** se uspí
- ⚠️ První načtení po probuzení trvá ~30 sekund
- ⚠️ Kontrola e-mailů probíhá jen když aplikace běží

**Řešení:**
1. **Použij cron-job.org** (zdarma) - pošle request každých 10 minut a udrží aplikaci aktivní
2. **Upgraduj na Starter ($7/měsíc)** - aplikace běží 24/7 bez uspávání

**Jak nastavit cron-job.org:**
1. Jdi na https://cron-job.org
2. Vytvoř účet zdarma
3. Vytvoř nový cron job:
   - URL: `https://tvoje-aplikace.onrender.com/health`
   - Interval: Každých 10 minut
4. **Hotovo!** Aplikace už se neuspí

---

## 💻 Lokální spuštění (pro testování)

Pokud chceš aplikaci nejdřív otestovat na svém počítači:

```bash
# 1. Nainstaluj závislosti
pip install -r requirements.txt

# 2. Vytvoř konfiguraci
cp .env.example .env

# 3. Uprav .env soubor s tvými údaji
nano .env  # nebo otevři v editoru

# 4. Spusť aplikaci
python app.py

# 5. Otevři prohlížeč
http://localhost:5000
```

---

## 🔧 Konfigurace

### E-mailový server (IMAP/SMTP)

Vyplň údaje tvého e-mailového serveru:

```bash
IMAP_SERVER=mail.tvoje-domena.cz  # Adresa IMAP serveru
IMAP_PORT=993                     # Port (obvykle 993)
IMAP_EMAIL=reklamace@domena.cz   # E-mail pro příjem
IMAP_PASSWORD=heslo               # Heslo k e-mailu

SMTP_SERVER=mail.tvoje-domena.cz  # Adresa SMTP serveru
SMTP_PORT=587                     # Port (587 nebo 465)
SMTP_EMAIL=reklamace@domena.cz   # E-mail pro odesílání
SMTP_PASSWORD=heslo               # Heslo
```

**Kde najít tyto údaje?**
- Kontaktuj svého poskytovatele e-mailu
- Nebo se podívej do nastavení e-mailového klienta
- Český Hosting: podpora může pomoct

### Admin přihlášení

```bash
ADMIN_USERNAME=admin              # Tvoje uživatelské jméno
ADMIN_PASSWORD=silne-heslo-123   # Silné heslo!
```

**DŮLEŽITÉ:** Změň výchozí heslo `admin123`!

### Interval kontroly e-mailů

```bash
CHECK_INTERVAL=300  # v sekundách
# 60 = 1 minuta
# 300 = 5 minut (doporučeno)
# 600 = 10 minut
```

---

## 📊 Jak to funguje

```
┌─────────────┐
│  Zákazník   │ Pošle e-mail s reklamací
└──────┬──────┘
       │
       v
┌─────────────────┐
│  IMAP Server    │ E-mail čeká v INBOX
└──────┬──────────┘
       │
       │ Každých 5 min kontrola
       v
┌──────────────────┐
│  Tvoje aplikace  │ Běží na Render.com
│  (Render.com)    │
└──────┬───────────┘
       │
       ├──> SQLite databáze (uložení reklamace)
       │
       └──> SMTP server (potvrzení zákazníkovi)
       
       
┌──────────────────┐
│   Admin web      │ https://tvoje-app.onrender.com
│   (Ty)           │ Správa všech reklamací
└──────────────────┘
```

---

## 🎨 Webové rozhraní

### Přihlášení
`https://tvoje-app.onrender.com/login`

### Hlavní stránka
- Přehled všech reklamací
- Statistiky (Celkem, Nové, V řešení, Vyřešeno)
- Tlačítko pro manuální kontrolu e-mailů

### Detail reklamace
- Kompletní informace
- Změna statusu
- Přidání poznámek

### Statistiky
- Grafický přehled
- Procentuální rozdělení

---

## 🗄️ Databáze

Aplikace používá **SQLite** - jednoduchá databáze v souboru `complaints.db`.

**Výhody:**
- ✅ Žádná složitá konfigurace
- ✅ Automaticky se vytvoří při prvním spuštění
- ✅ Data uložená přímo v aplikaci

**Poznámka:** Na Render.com se databáze resetuje při restartu (free tier). Pro produkci doporuč uji upgrade nebo externí databázi.

---

## ⚡ Alternativní platformy

Pokud nechceš Render.com, můžeš použít:

### Railway.app
1. Jdi na https://railway.app
2. Připoj GitHub repozitář
3. Nastav environment variables
4. Deploy! ($5/měsíc credit zdarma)

### Fly.io
1. Jdi na https://fly.io
2. Nainstaluj `flyctl`
3. Spusť `fly launch`
4. Deploy! (2 GB RAM zdarma)

### Replit
1. Jdi na https://replit.com
2. Importuj z GitHub
3. Přidej secrets (environment variables)
4. Run! (Limitované v free plánu)

---

## 🔒 Bezpečnost

1. **Změň výchozí admin heslo!**
   ```bash
   ADMIN_PASSWORD=tvoje-silne-heslo-123
   ```

2. **Používej silný SECRET_KEY**
   ```bash
   SECRET_KEY=dlouhy-nahodny-retezec-xyz789abc
   ```

3. **NIKDY nesdílej .env soubor**
   - Obsahuje hesla!
   - Je v `.gitignore` (nenahraje se na GitHub)

---

## 📞 Podpora

**Problémy s nasazením?**
1. Zkontroluj environment variables na Render.com
2. Podívej se do Render.com logů (sekce "Logs")
3. Zkontroluj IMAP/SMTP údaje

**E-maily se nekontrolují?**
- Aplikace může spát (free tier) - použij cron-job.org
- Zkontroluj IMAP údaje v environment variables

**Databáze se resetuje?**
- To je normální na free tier Render.com
- Pro produkci upgrade nebo externí databáze

---

## ✅ Checklist před spuštěním

- [ ] Účet na Render.com vytvořen
- [ ] Kód nahrán na GitHub (nebo ZIP připraven)
- [ ] Web Service vytvořen na Render.com
- [ ] Environment variables vyplněny
- [ ] IMAP/SMTP údaje zkontrolovány
- [ ] Admin heslo změněno
- [ ] Aplikace nasazena
- [ ] Přihlášení funguje
- [ ] Cron-job.org nastaven (volitelné, ale doporučeno)

---

## 🎉 Hotovo!

Máš **plně funkční systém správy reklamací** běžící v cloudu **zdarma**!

**URL aplikace:** `https://tvoje-app.onrender.com`

**Přihlášení:**
- Username: `admin` (nebo co jsi nastavil)
- Password: (co jsi nastavil)

**Další kroky:**
1. Testuj aplikaci - pošli testovací e-mail
2. Nastav cron-job.org pro udržení aplikace aktivní
3. Sdílej URL s kolegy (všichni budou používat stejné admin přihlášení)

---

**Hodně štěstí! 🚀**
