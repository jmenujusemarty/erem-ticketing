# ⚡ RYCHLÝ START - 3 kroky do cloudu!

## 🎯 Co potřebuješ

- [ ] E-mailový účet s IMAP/SMTP
- [ ] 10 minut času
- [ ] Žádný VPS, SSH, nebo složité věci!

---

## 📋 Krok 1: Zaregistruj se na Render.com (2 min)

1. Jdi na https://render.com
2. Klikni **"Get Started"**
3. Zaregistruj se (GitHub nebo e-mail)
4. **Ověř e-mail** (dostaneš potvrzovací link)

**Nevyžaduje platební kartu!** ✅

---

## 📦 Krok 2: Nahraj kód (3 min)

### Varianta A: Máš GitHub

1. Vytvoř repozitář na https://github.com/new
2. Nahraj tam všechny soubory z této složky
3. Hotovo!

### Varianta B: Nemáš GitHub

1. Zazipuj celou složku
2. Na Render.com použij "Upload Repository"
3. Hotovo!

---

## 🚀 Krok 3: Nasaď na Render.com (5 min)

1. Na Render Dashboard klikni **"New +"** → **"Web Service"**

2. Připoj GitHub repozitář (nebo nahraj ZIP)

3. Vyplň:
   ```
   Name: reklamacni-system
   Environment: Python 3
   Build Command: pip install -r requirements.txt
   Start Command: gunicorn app:app
   Instance Type: Free
   ```

4. Přidej **Environment Variables**:
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
   ADMIN_PASSWORD = silne-heslo-123
   
   SECRET_KEY = [klikni "Generate"]
   CHECK_INTERVAL = 300
   ```

5. Klikni **"Create Web Service"**

6. Počkej ~2 minuty (Render builduje aplikaci)

7. Dostaneš URL: `https://reklamacni-system.onrender.com`

---

## ✅ Hotovo!

Otevři URL a přihlaš se:
- **Username**: `admin` (nebo co jsi dal)
- **Password**: (co jsi nastavil)

---

## 🎁 BONUS: Udrž aplikaci aktivní (2 min)

Free tier Render uspává aplikaci po 15 min. Řešení:

1. Jdi na https://cron-job.org
2. Zaregistruj se zdarma
3. Vytvoř nový cron job:
   - **URL**: `https://tvoje-app.onrender.com/health`
   - **Interval**: Každých 10 minut
4. Aktivuj!

**Aplikace už se neuspí!** 🎉

---

## 🆘 Problémy?

**Aplikace se nebuiluje?**
→ Zkontroluj, že máš všechny soubory (app.py, requirements.txt, render.yaml)

**Nefunguje přihlášení?**
→ Zkontroluj ADMIN_USERNAME a ADMIN_PASSWORD v Environment Variables

**E-maily se nekontrolují?**
→ Zkontroluj IMAP_SERVER, IMAP_EMAIL, IMAP_PASSWORD

Více v **README.md** 📖

---

**To je všechno! Teď máš systém reklamací v cloudu zdarma! 🚀**
