# plugin.video.moravec

Neoficiální Kodi video plugin pro [moravec.cz](https://moravec.cz) – nezávislá žurnalistika Václava Moravce.

Umožňuje procházet a přehrávat placený obsah moravec.cz přímo z Kodi menu bez webového prohlížeče.

---

## Požadavky

| Co | Verze |
|---|---|
| Kodi | 21 (Omega) nebo novější |
| Python | 3.x (součást Kodi 21) |
| InputStream Adaptive | součást LibreELEC / Kodi |
| Předplatné moravec.cz | aktivní (nutné pro přehrávání) |

Testováno na **Raspberry Pi 5 + LibreELEC 12.x (Kodi 21 Omega)**.

---

## Instalace

### Způsob A – přes SSH (doporučeno pro LibreELEC)

```bash
# Na vývojovém PC – zabalit addon
cd /cesta/k/webkodi
bash package.sh

# Zkopírovat přímo do Kodi
scp -r plugin.video.moravec root@<IP_RPi5>:/storage/.kodi/addons/
```

Poté v Kodi: **Settings → Add-ons → My add-ons** → najít *Moravec.cz* → aktivovat.

### Způsob B – ZIP soubor

```bash
bash package.sh
# Vznikne plugin.video.moravec.zip
```

Soubor překopírovat na RPi5 (USB, síťový disk…) a v Kodi:
**Settings → Add-ons → ikona balíčku (Install from zip file)** → vybrat ZIP.

---

## Konfigurace

Po instalaci otevřít nastavení addonu:

**Settings → Add-ons → My add-ons → Video add-ons → Moravec.cz → Configure**

| Pole | Popis |
|---|---|
| E-mail | Přihlašovací e-mail použitý na moravec.cz |
| Heslo | Heslo k účtu moravec.cz |

Credentials jsou uloženy v Kodi addon userdata (šifrovaně na disku).

---

## Ovládání

```
Moravec.cz
├── Vše              ← všechna dostupná videa
├── 1:1
├── Ekonomika
├── Generace
├── Kontexty
├── PM               ← Poledne s Moravcem
├── Politici
├── Populace
└── Předplatné
    ├── [název epizody]  → přehrát
    ├── [název epizody]  → přehrát
    └── ...
```

Přehrávání probíhá přes **HLS (HTTP Live Streaming)** pomocí vestavěného `inputstream.adaptive` – automatická volba kvality (360p / 720p / 1080p) podle rychlosti připojení.

---

## Architektura

### Technologický základ

moravec.cz běží na platformě **[Tivio Studio](https://tivio.studio)** se dvěma hlavními komponentami:

```
moravec.cz (Next.js / React)
    │
    ├── Firebase Auth  ← přihlášení uživatelů
    │     tenant: XC88VmVyEGBJcBb9gQG9-tfdxu
    │
    ├── Firebase Firestore  ← metadata (videa, tagy/pořady)
    │     projekt: tivio-production
    │
    └── Cloud Function getSourceUrl  ← vygeneruje HLS URL
          region: europe-west3
          CDN: dev.streaming.tivio.studio
```

### Struktura souborů

```
plugin.video.moravec/
├── addon.xml                   Kodi metadata a závislosti
├── addon.py                    Vstupní bod + URL router
└── resources/
    ├── settings.xml            Definice nastavení (e-mail, heslo)
    ├── lib/
    │   ├── api.py              Firebase/Tivio API klient
    │   └── player.py           HLS ListItem helper
    └── language/
        └── resource.language.cs_cz/
            └── strings.po      České texty UI
```

### Tok dat

```
1. addon.py spuštěn Kodi
       │
2. _ensure_authenticated()
   ├── api.get_valid_token()  → přečte cache token
   └── pokud expiroval → api._refresh_id_token()
       pokud chybí    → api.sign_in(email, heslo)
       │
3. Navigace menu
   ├── api.get_shows()
   │     Firestore: GET /organizations/{ORG_ID}/tags
   │
   └── api.get_videos_by_tag(tag_id)  nebo  api.get_all_videos()
         Firestore: POST :runQuery
         filtr: tags ARRAY_CONTAINS <tagRef>  nebo  organizationRef == <orgRef>
       │
4. Přehrávání
   ├── api.get_stream_url(video_id)
   │     Cloud Function: POST getSourceUrl
   │     payload: { id, documentType: "video", capabilities: [{codec:"h264", protocol:"hls", encryption:"none"}] }
   │     → vrátí: { url: "https://dev.streaming.tivio.studio/v2/.../index.m3u8" }
   │
   └── player.create_hls_item(url, metadata)
         ListItem s inputstream=inputstream.adaptive
         → Kodi přehraje HLS stream
```

### Klíčové konstanty v `api.py`

| Konstanta | Hodnota | Popis |
|---|---|---|
| `FIREBASE_API_KEY` | `AIzaSyB02u...` | Veřejný Firebase API klíč (součást JS bundle) |
| `FIREBASE_PROJECT_ID` | `tivio-production` | Firebase projekt Tivio |
| `FIREBASE_TENANT_ID` | `XC88VmVy...` | Tenant ID moravec.cz v rámci Tivio |
| `ORG_ID` | `fC88VmVy...` | ID moravec organizace ve Firestore |

> **Poznámka:** `FIREBASE_API_KEY` je záměrně veřejný – Firebase bezpečnostní model ho nevyžaduje skrývat. Přístup k datům chrání Firestore Security Rules a Firebase Auth.

---

## Vývoj

### Testování bez Kodi

```bash
python3 test_api.py vas@email.cz vase-heslo
```

Výstup úspěšného testu:
```
[1/4] Přihlášení jako vas@email.cz...
      OK
[2/4] Načtení pořadů...
      OK – 8 pořadů
       - 1:1 (id: ZBeuJdE...)
       ...
[3/4] Videa pořadu '1:1'...
      OK – 3 videí
[4/4] Stream URL...
      OK – https://dev.streaming.tivio.studio/v2/.../index.m3u8
```

### Zabalení pro distribuci

```bash
bash package.sh
# → plugin.video.moravec.zip
```

### Rychlé nasazení na RPi5 při vývoji

```bash
rsync -av --exclude='*.pyc' --exclude='__pycache__' \
  plugin.video.moravec/ \
  root@<IP_RPi5>:/storage/.kodi/addons/plugin.video.moravec/
```

---

## Řešení problémů

| Chyba | Příčina | Řešení |
|---|---|---|
| `EMAIL_NOT_FOUND` | Chybí `tenantId` v auth requestu | Zkontroluj `FIREBASE_TENANT_ID` v `api.py` |
| `PERMISSION_DENIED` | Firestore Security Rules | Ujisti se, že přihlašuješ správným účtem |
| `capabilities is required` | Špatný payload pro `getSourceUrl` | Zkontroluj formát `HLS_CAPABILITIES` v `api.py` |
| Prázdný seznam pořadů | Žádné tagy s relevantním názvem | Zkontroluj `_IGNORED_TAG_NAMES` v `api.py` |
| Video se nepřehraje | `inputstream.adaptive` není aktivní | V Kodi aktivuj addon *InputStream Adaptive* |
| Přehrávání skončí okamžitě | Expirovaná session URL | Znovu klikni na video (URL má omezenou platnost) |
| Po změně hesla addon nefunguje | Refresh token zneplatněn | Viz níže – addon se zeptá automaticky |

---

## Změna hesla

Po změně hesla na moravec.cz:

1. Firebase zneplatní stávající refresh token
2. Addon detekuje selhání obnovy tokenu, smaže lokální cache (`token_cache.json`)
3. Při příštím spuštění addonu se automaticky pokusí přihlásit s credentials uloženými v Kodi nastavení
4. Pokud je v nastavení nové heslo → přihlásí se bez zásahu uživatele
5. Pokud je v nastavení staré heslo → zobrazí chybový dialog a otevře nastavení addonu

**Postup po změně hesla:**
1. Změnit heslo na [moravec.cz](https://moravec.cz)
2. V Kodi otevřít **Settings → Add-ons → My add-ons → Video add-ons → Moravec.cz → Configure**
3. Zadat nové heslo → uložit
4. Addon se přihlásí automaticky při dalším použití

---

## Omezení a rizika

- **Neoficiální addon** – Tivio Studio může kdykoli změnit API bez upozornění
- **Pouze HLS bez DRM** – videa bez šifrování; pokud Tivio nasadí Widevine povinně, bude potřeba rozšíření
- **Session URL** – vygenerovaná `.m3u8` URL je platná omezenou dobu (nelze ji uložit napořád)
- **Závislost na Firestore** – pokud Tivio zpřísní Security Rules, přestane fungovat načítání metadat

---

## Licence

GPL-3.0 – viz `addon.xml`

Tento projekt není spojen s moravec.cz, Tivio Studio ani Václavem Moravcem.
