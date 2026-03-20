# erem Design System
> Tento soubor slouží jako AI kontext. Vždy dodržuj tyto instrukce při generování jakéhokoliv HTML/CSS pro erem projekty.

---

## Pravidla — vždy dodržuj

1. **Nikdy nepíš hex hodnoty přímo** — vždy používej CSS custom properties (`var(--accent)` atd.)
2. **Vše je glassmorphism** — průhledné povrchy + `backdrop-filter: blur()`
3. **Tlačítka jsou vždy pilulky** — `border-radius: 100px`
4. **Karty mají `border-radius: 22px`** — nikdy ostrý roh
5. **Fonty: SF Pro** — `"SF Pro Display","SF Pro Text","Helvetica Neue",Helvetica,Arial,sans-serif`
6. **Antialiasing vždy** — `-webkit-font-smoothing: antialiased`
7. **Přechody jsou jemné** — `all 0.18s cubic-bezier(0.4,0,0.2,1)`
8. **Hover efekt na kartách** — `translateY(-1px)` + silnější stín
9. **Ikonky jsou Heroicons / Feather** — stroke, nikdy fill, `stroke-width: 2`
10. **Badges mají tónované pozadí** — nikdy sytý fill (max 13% opacity)

---

## Design Tokens — zkopíruj do každého projektu

```css
:root {
  /* Barvy */
  --accent:  #007AFF;   /* primární modrá */
  --green:   #34C759;   /* úspěch */
  --red:     #FF3B30;   /* chyba, nebezpečí */
  --orange:  #FF9500;   /* varování */
  --purple:  #AF52DE;   /* AI, speciální */
  --teal:    #32ADE6;   /* info, sekundární */

  /* Text */
  --text:    #0f172a;   /* hlavní */
  --text2:   #475569;   /* sekundární */
  --muted:   #94a3b8;   /* hint, placeholder */

  /* Povrchy */
  --surface:   rgba(255,255,255,0.82);
  --surface2:  rgba(255,255,255,0.62);
  --border:    rgba(255,255,255,0.76);
  --border2:   rgba(15,23,42,0.08);
  --shadow:    0 12px 40px rgba(15,23,42,0.08);
  --shadow-sm: 0 4px 16px rgba(15,23,42,0.06);

  /* Poloměry */
  --r-card: 22px;
  --r-btn:  100px;
  --r-in:   14px;
  --r-chip: 10px;

  /* Blur */
  --blur:    blur(20px) saturate(145%);
  --blur-sm: blur(14px) saturate(130%);

  /* Přechod */
  --trans: all 0.18s cubic-bezier(0.4,0,0.2,1);
}
```

---

## Background — tělo stránky

```css
body {
  font-family: "SF Pro Display","SF Pro Text","Helvetica Neue",Helvetica,Arial,sans-serif;
  -webkit-font-smoothing: antialiased;
  color: var(--text);
  background:
    radial-gradient(circle at 10% 0%, rgba(210,226,255,0.55) 0%, transparent 30%),
    radial-gradient(circle at 88% 8%, rgba(200,240,220,0.35) 0%, transparent 26%),
    linear-gradient(180deg, #f5f6fa 0%, #eef1f6 100%);
  background-attachment: fixed;
  min-height: 100dvh;
}
```

---

## Layout

```css
.page    { max-width: 1100px; margin: 0 auto; padding: 32px 24px 64px; }
.page-sm { max-width: 700px;  margin: 0 auto; padding: 32px 24px 64px; }
```

```html
<!-- Struktura každé stránky -->
<nav class="navbar">...</nav>
<div class="page">
  <div class="page-head">
    <div class="page-eyebrow">Sekce</div>
    <h1 class="page-title">Název stránky</h1>
    <p class="page-sub">Popis</p>
  </div>
  <!-- obsah -->
</div>
```

---

## Navbar

```css
.navbar {
  position: sticky; top: 0; z-index: 40;
  background: rgba(255,255,255,0.72);
  backdrop-filter: var(--blur); -webkit-backdrop-filter: var(--blur);
  border-bottom: 1px solid rgba(255,255,255,0.8);
  box-shadow: 0 1px 0 rgba(15,23,42,0.06);
  padding: 0 24px; height: 60px;
  display: flex; align-items: center; gap: 8px;
}
.navbar-brand {
  font-size: 17px; font-weight: 700; color: var(--text); letter-spacing: -0.3px;
  margin-right: 8px; display: flex; align-items: center; gap: 8px;
}
.navbar-sep { width: 1px; height: 20px; background: var(--border2); margin: 0 4px; }
.nav-link {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 7px 14px; border-radius: var(--r-btn);
  font-size: 14px; font-weight: 500; color: var(--text2);
  text-decoration: none; border: none; background: transparent; cursor: pointer;
  transition: var(--trans);
}
.nav-link:hover  { background: rgba(0,122,255,0.08); color: var(--accent); }
.nav-link.active { background: rgba(0,122,255,0.1); color: var(--accent); font-weight: 600; }
.nav-spacer      { flex: 1; }
.nav-logout:hover { background: rgba(255,59,48,0.08); color: var(--red); }
```

```html
<nav class="navbar">
  <div class="navbar-brand">
    <svg><!-- ikona 24×24 --></svg>
    Název
  </div>
  <div class="navbar-sep"></div>
  <a href="/" class="nav-link active">
    <svg><!-- ikona --></svg>
    <span>Přehled</span>
  </a>
  <a href="/stats" class="nav-link">
    <svg><!-- ikona --></svg>
    <span>Statistiky</span>
  </a>
  <div class="nav-spacer"></div>
  <a href="/logout" class="nav-link nav-logout">Odhlásit</a>
</nav>
```

---

## Karty — 3 úrovně

```css
/* Hlavní karta */
.card {
  background: linear-gradient(180deg, rgba(255,255,255,0.82) 0%, rgba(255,255,255,0.68) 100%);
  backdrop-filter: var(--blur); -webkit-backdrop-filter: var(--blur);
  border: 1px solid var(--border); border-radius: var(--r-card);
  box-shadow: var(--shadow), inset 0 1px 0 rgba(255,255,255,0.65);
}

/* Měkká karta (sekce, panely) */
.card-soft {
  background: rgba(255,255,255,0.56); backdrop-filter: var(--blur-sm);
  -webkit-backdrop-filter: var(--blur-sm);
  border: 1px solid rgba(255,255,255,0.8); border-radius: var(--r-card);
  box-shadow: var(--shadow-sm);
}

/* Vnořený blok uvnitř karty */
.card-inner {
  background: rgba(255,255,255,0.55); border: 1px solid rgba(255,255,255,0.75);
  border-radius: 16px; box-shadow: 0 2px 8px rgba(15,23,42,0.04);
}
```

**Kdy použít:**
- `.card` — hlavní obsah, formuláře, detailní pohled
- `.card-soft` — vedlejší panely, sidebar sekce
- `.card-inner` — vnořené bloky, code snippety, citace uvnitř `.card`

---

## Tlačítka

```css
.btn {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 11px 20px; border-radius: var(--r-btn);
  font-size: 14px; font-weight: 600; border: none; cursor: pointer;
  font-family: inherit; white-space: nowrap;
  transition: transform 180ms ease, box-shadow 180ms ease, opacity 180ms ease;
}
.btn:hover  { transform: translateY(-1px); }
.btn:active { transform: translateY(0); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none !important; }

/* Varianty */
.btn-primary   { background: linear-gradient(180deg,#4d6fff 0%,#3559ff 100%); color: #fff; box-shadow: 0 10px 24px rgba(53,89,255,0.26); }
.btn-secondary { background: rgba(255,255,255,0.72); color: var(--text2); border: 1px solid rgba(255,255,255,0.85); box-shadow: 0 6px 18px rgba(15,23,42,0.06); backdrop-filter: var(--blur-sm); }
.btn-green     { background: linear-gradient(180deg,#40c973 0%,#2fb55f 100%); color: #fff; box-shadow: 0 8px 20px rgba(52,199,89,0.26); }
.btn-danger    { background: rgba(255,59,48,0.1); color: var(--red); border: 1px solid rgba(255,59,48,0.15); }
.btn-purple    { background: linear-gradient(180deg,#c97bff 0%,#af52de 100%); color: #fff; box-shadow: 0 8px 20px rgba(175,82,222,0.26); }

/* Velikosti */
.btn-sm { padding: 7px 14px; font-size: 13px; }
.btn-xs { padding: 5px 10px; font-size: 12px; }
```

**Kdy použít:**
- `btn-primary` — hlavní akce (Uložit, Potvrdit)
- `btn-secondary` — vedlejší akce (Zpět, Zrušit)
- `btn-green` — odeslání, úspěšná akce (Odeslat odpověď)
- `btn-danger` — destruktivní akce (Smazat) — nikdy `btn-primary` pro mazání
- `btn-purple` — AI akce (Generovat odpověď)

---

## Badges & Chips

```css
.badge {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 4px 10px; border-radius: var(--r-chip);
  font-size: 12px; font-weight: 600;
}
.badge-dot { width: 6px; height: 6px; border-radius: 50%; }

/* Stavové varianty */
.badge-nova      { background: rgba(255,149,0,0.12);  color: #c47900; }
.badge-reseni    { background: rgba(0,122,255,0.11);  color: #0062cc; }
.badge-vyreseno  { background: rgba(52,199,89,0.13);  color: #1e8e3e; }
.badge-zamitnuto { background: rgba(255,59,48,0.11);  color: #c9302c; }
.badge-info      { background: rgba(50,173,230,0.12); color: #1a7a9e; }
```

**Vzor pro vlastní chip:**
```html
<!-- Pozadí = barva na 10-13% opacity, text = tmavší odstín stejné barvy -->
<span style="display:inline-flex;align-items:center;gap:4px;
             padding:3px 8px;border-radius:8px;font-size:11px;font-weight:600;
             background:rgba(52,199,89,0.10);color:#1e8e3e;">
  ✓ Hotovo
</span>
```

---

## Typografie

```css
/* Eyebrow — nad nadpisem stránky */
.page-eyebrow {
  font-size: 11px; font-weight: 600; letter-spacing: 0.12em;
  text-transform: uppercase; color: var(--accent); margin-bottom: 6px;
}
/* Hlavní nadpis */
.page-title { font-size: 30px; font-weight: 800; letter-spacing: -0.5px; line-height: 1.1; }
/* Podnázev */
.page-sub   { margin-top: 6px; font-size: 15px; color: var(--text2); }

/* Název sekce */
.section-title {
  font-size: 13px; font-weight: 700; letter-spacing: 0.07em;
  text-transform: uppercase; color: var(--text2); margin-bottom: 12px;
}
```

**Hierarchie (největší → nejmenší):**
| Třída/styl | Velikost | Váha | Použití |
|---|---|---|---|
| `.page-title` | 30px | 800 | Nadpis stránky |
| `h2` inline | 22px | 700 | Podsekce |
| body | 15px | 400 | Hlavní text |
| `.page-sub` | 15px | 400 | Popis pod nadpisem |
| info text | 14px | 400 | Sekundární obsah |
| `.section-title` | 13px | 700 | Popisky sekcí (uppercase) |
| hint | 13px | 400 | `var(--muted)` |
| chips/badges | 11–12px | 600 | Tagy, stavové štítky |

---

## Formuláře

```css
.form-group  { margin-bottom: 20px; }
.form-label  { display: block; font-size: 13px; font-weight: 600; color: var(--text2); margin-bottom: 7px; }
.form-hint   { font-size: 12px; color: var(--muted); margin-top: 5px; }

.form-input, .form-select, .form-textarea {
  width: 100%; padding: 12px 16px;
  border: 1px solid rgba(15,23,42,0.12); border-radius: var(--r-in);
  font-size: 15px; font-family: inherit; color: var(--text);
  background: rgba(255,255,255,0.72);
  backdrop-filter: var(--blur-sm); -webkit-backdrop-filter: var(--blur-sm);
  transition: border 0.15s, box-shadow 0.15s; outline: none; -webkit-appearance: none;
}
.form-input:focus, .form-select:focus, .form-textarea:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(0,122,255,0.12);
  background: rgba(255,255,255,0.9);
}
.form-textarea { resize: vertical; min-height: 120px; line-height: 1.6; }
```

```html
<div class="form-group">
  <label class="form-label">Název pole</label>
  <input type="text" class="form-input" placeholder="Placeholder text">
  <div class="form-hint">Pomocný text pod polem</div>
</div>
```

---

## Alerty

```css
.alert {
  display: flex; align-items: center; gap: 10px;
  padding: 13px 16px; border-radius: 14px; font-size: 14px; font-weight: 500;
  margin-bottom: 16px;
}
.alert-success { background: rgba(52,199,89,0.10);  color: #1a7a33; border: 1px solid rgba(52,199,89,0.20); }
.alert-error   { background: rgba(255,59,48,0.09);  color: #b92d24; border: 1px solid rgba(255,59,48,0.18); }
.alert-warning { background: rgba(255,149,0,0.09);  color: #a35e00; border: 1px solid rgba(255,149,0,0.18); }
.alert-info    { background: rgba(0,122,255,0.08);  color: #0055aa; border: 1px solid rgba(0,122,255,0.15); }
```

```html
<div class="alert alert-success">
  <svg><!-- check icon --></svg>
  Zpráva odeslána.
</div>
```

---

## Stats Grid — přehled čísel

```css
.stats-grid { display: grid; grid-template-columns: repeat(4,1fr); gap: 16px; margin-bottom: 28px; }
@media(max-width:800px){ .stats-grid { grid-template-columns: repeat(2,1fr); } }
.stat-card  { padding: 20px; }
.stat-label { font-size: 11px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; color: var(--text2); margin-bottom: 8px; }
.stat-num   { font-size: 36px; font-weight: 800; letter-spacing: -1px; line-height: 1; }
.stat-sub   { font-size: 12px; color: var(--muted); margin-top: 4px; }
```

```html
<div class="stats-grid">
  <div class="card stat-card">
    <div class="stat-label">Celkem</div>
    <div class="stat-num">142</div>
    <div class="stat-sub">za celou dobu</div>
  </div>
  <!-- × 4 -->
</div>
```

---

## Info Rows — detail záznamu

```css
.info-grid { display: flex; flex-direction: column; }
.info-row  { display: grid; grid-template-columns: 160px 1fr; gap: 12px; padding: 13px 20px; border-bottom: 1px solid rgba(15,23,42,0.055); }
.info-row:last-child { border-bottom: none; }
.info-key  { font-size: 13px; font-weight: 600; color: var(--text2); }
.info-val  { font-size: 14px; color: var(--text); }
```

```html
<div class="card">
  <div class="info-grid">
    <div class="info-row">
      <div class="info-key">E-mail</div>
      <div class="info-val">zákazník@email.cz</div>
    </div>
    <div class="info-row">
      <div class="info-key">Status</div>
      <div class="info-val"><span class="badge badge-nova">Nová</span></div>
    </div>
  </div>
</div>
```

---

## List Rows — seznam položek

```css
.list-items { display: flex; flex-direction: column; gap: 10px; }
.list-row {
  display: flex; align-items: center; gap: 16px;
  padding: 16px 20px; text-decoration: none; color: inherit;
  transition: var(--trans); cursor: pointer; border-radius: var(--r-card);
}
.list-row:hover {
  transform: translateY(-1px);
  box-shadow: 0 18px 44px rgba(15,23,42,0.1), inset 0 1px 0 rgba(255,255,255,0.7);
}
```

```html
<div class="list-items">
  <a href="/detail/1" class="card list-row">
    <div style="flex:1;">
      <div style="font-weight:600;">Název položky</div>
      <div class="text-sm text-muted">Popis nebo datum</div>
    </div>
    <span class="badge badge-nova">Nová</span>
  </a>
</div>
```

---

## Tooltips

```css
[data-tip] { position: relative; }
[data-tip]::after {
  content: attr(data-tip); position: absolute;
  bottom: calc(100% + 7px); left: 50%;
  transform: translateX(-50%) translateY(4px);
  background: rgba(15,23,42,0.88); color: #fff;
  font-size: 11.5px; font-weight: 500; white-space: nowrap;
  padding: 5px 10px; border-radius: 8px; pointer-events: none;
  opacity: 0; transition: opacity 0.15s, transform 0.15s; z-index: 9999;
}
[data-tip]:hover::after { opacity: 1; transform: translateX(-50%) translateY(0); }
```

```html
<button class="btn btn-primary" data-tip="Klávesová zkratka: Ctrl+S">Uložit</button>
```

---

## Animace — vstup prvků

```css
@media(prefers-reduced-motion: no-preference) {
  .rise   { animation: rise-in 0.42s cubic-bezier(0.22,1,0.36,1) both; }
  .rise-1 { animation-delay: 0.04s; }
  .rise-2 { animation-delay: 0.08s; }
  .rise-3 { animation-delay: 0.12s; }
  .rise-4 { animation-delay: 0.16s; }
}
@keyframes rise-in {
  from { opacity: 0; transform: translateY(14px) scale(0.985); }
  to   { opacity: 1; transform: none; }
}
```

```html
<!-- Kaskádový vstup sekcí -->
<div class="card rise rise-1">První sekce</div>
<div class="card rise rise-2">Druhá sekce</div>
<div class="card rise rise-3">Třetí sekce</div>
```

---

## Loading stavy

```css
/* Spinner */
.spinner {
  width: 18px; height: 18px;
  border: 2px solid rgba(0,122,255,0.22); border-top-color: var(--accent);
  border-radius: 50%; animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* Dot pulse */
.dot-pulse { display: inline-flex; gap: 4px; align-items: center; }
.dot-pulse::before, .dot-pulse::after, .dot-pulse span {
  content: ''; width: 5px; height: 5px; border-radius: 50%; background: var(--muted);
  animation: dp-pulse 1.2s ease-in-out infinite;
}
.dot-pulse::after  { animation-delay: 0.2s; }
.dot-pulse span    { animation-delay: 0.4s; }
@keyframes dp-pulse { 0%,80%,100%{opacity:.3;transform:scale(0.8)} 40%{opacity:1;transform:scale(1)} }

/* Progress bar */
.prog-track { height: 5px; border-radius: 100px; background: rgba(15,23,42,0.08); overflow: hidden; }
.prog-fill  { height: 100%; border-radius: 100px; transition: width 0.6s ease; }
```

---

## Empty State

```css
.empty { text-align: center; padding: 64px 24px; color: var(--muted); }
.empty svg { width: 56px; height: 56px; opacity: 0.3; margin-bottom: 16px; }
.empty h3  { font-size: 18px; font-weight: 700; color: var(--text2); margin-bottom: 8px; }
.empty p   { font-size: 14px; }
```

```html
<div class="empty">
  <svg><!-- tematická ikona --></svg>
  <h3>Žádné záznamy</h3>
  <p>Zatím tu nic není.</p>
</div>
```

---

## Utility třídy

```css
.flex            { display: flex; }
.flex-col        { flex-direction: column; }
.items-center    { align-items: center; }
.justify-between { justify-content: space-between; }
.gap-1 { gap: 4px; }   .gap-2 { gap: 8px; }   .gap-3 { gap: 12px; }  .gap-4 { gap: 16px; }
.mb-2  { margin-bottom: 8px; }  .mb-4 { margin-bottom: 16px; }  .mb-6 { margin-bottom: 24px; }
.mt-4  { margin-top: 16px; }
.p-4   { padding: 16px; }  .p-5  { padding: 20px; }  .p-6  { padding: 24px; }
.text-sm   { font-size: 13px; }  .text-xs { font-size: 11px; }
.text-muted  { color: var(--muted); }
.text-accent { color: var(--accent); }
.text-green  { color: var(--green); }
.text-red    { color: var(--red); }
.font-bold   { font-weight: 700; }
.font-mono   { font-family: "SF Mono", ui-monospace, monospace; font-size: 13px; }
.divider     { height: 1px; background: rgba(15,23,42,0.07); margin: 20px 0; }
.truncate    { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
```

---

## Responzivita

```css
@media(max-width: 640px) {
  .page, .page-sm { padding: 16px 12px 80px; }
  .navbar         { padding: 0 12px; height: 52px; }
  .navbar-brand   { font-size: 15px; }
  .navbar-sep     { display: none; }
  .nav-link       { padding: 6px 8px; font-size: 12px; }
  .page-title     { font-size: 22px; }
  .stat-num       { font-size: 28px; }
  .form-input, .form-select, .form-textarea { font-size: 16px; } /* iOS zoom prevence */
  .btn            { padding: 10px 16px; font-size: 13px; }
}
@media(max-width: 480px) {
  .nav-link span { display: none; }  /* schovat texty, zůstanou jen ikony */
  .navbar        { gap: 0; }
  .nav-link      { padding: 8px 10px; }
}
```

---

## Kompletní šablona nové stránky

```html
<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Název stránky — erem</title>
<style>
/* VLOŽIT VŠECHNY DESIGN TOKENS A CSS TŘÍDY ZE SOUBORU VÝŠE */
</style>
</head>
<body>

<nav class="navbar">
  <div class="navbar-brand">
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <!-- ikona projektu -->
    </svg>
    Název projektu
  </div>
  <div class="navbar-sep"></div>
  <a href="/" class="nav-link active">
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
      <rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>
    </svg>
    <span>Přehled</span>
  </a>
  <div class="nav-spacer"></div>
  <a href="/logout" class="nav-link nav-logout">
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
      <polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>
    </svg>
    <span>Odhlásit</span>
  </a>
</nav>

<div class="page">

  <div class="page-head rise">
    <div class="page-eyebrow">Kontext / Kategorie</div>
    <h1 class="page-title">Název stránky</h1>
    <p class="page-sub">Krátký popis nebo instrukce pro uživatele</p>
  </div>

  <!-- Stats (pokud jsou relevantní) -->
  <div class="stats-grid rise rise-1">
    <div class="card stat-card">
      <div class="stat-label">Metrika</div>
      <div class="stat-num">0</div>
      <div class="stat-sub">popis</div>
    </div>
  </div>

  <!-- Hlavní obsah -->
  <div class="card p-6 rise rise-2">
    <div class="section-title">Sekce</div>
    <!-- obsah -->
  </div>

</div>

</body>
</html>
```

---

## Barvy × kontext — rychlý přehled

| Barva | Token | Použití |
|---|---|---|
| Modrá | `--accent` | Hlavní CTA, aktivní stav, focus ring, primární info |
| Zelená | `--green` | Úspěch, vyřešeno, odeslání, potvrzení |
| Červená | `--red` | Chyba, smazání, odmítnutí, nebezpečí |
| Oranžová | `--orange` | Varování, nové položky čekající na akci |
| Fialová | `--purple` | AI funkce, speciální/premium akce |
| Teal | `--teal` | Sekundární info, neutrální notifikace |
