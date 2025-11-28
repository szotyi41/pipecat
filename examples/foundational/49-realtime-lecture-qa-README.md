# Valós idejű előadás felvétel és Q&A rendszer

Ez a példa egy komplett megoldást mutat arra, hogyan lehet:
- ✅ Valós időben felvenni egy előadást mikrofonon keresztül
- ✅ Automatikusan átírni a beszédet (Google Speech-to-Text)
- ✅ Elmenteni az átíratot fájlba
- ✅ Egy chat interfészen keresztül kérdezni az elhangzottakról (Google Gemini LLM)

## Működés

A rendszer két üzemmódban működik egyidejűleg:

### 1. Audio mód (valós idejű felvétel)
- Mikrofonon keresztül beszélsz
- A Google STT átírja a beszédet
- Az átírat automatikusan mentődik `lecture_transcript.txt` fájlba
- A rendszer tud rád reagálni (opcionális)

### 2. Chat mód (kérdezés)
- A terminálban tudsz kérdéseket írni
- A rendszer az elhangzott előadás átírata alapján válaszol
- Bármikor lekérheted a teljes átíratot is

## Telepítés és konfiguráció

### 1. Környezeti változók beállítása

Hozz létre egy `.env` fájlt a projekt gyökerében:

```bash
# Google Gemini API kulcs (LLM-hez)
GOOGLE_API_KEY=your-gemini-api-key-here

# Google Cloud credentials (STT és TTS-hez)
GOOGLE_TEST_CREDENTIALS=your-google-cloud-credentials-json-here
```

### 2. Google Cloud beállítások

A Google Speech-to-Text használatához szükséged lesz:
- Egy Google Cloud projekttel
- Speech-to-Text API engedélyezve
- Service account credentials (JSON formátumban)

A `GOOGLE_TEST_CREDENTIALS` lehet:
- Egy JSON string (a teljes credentials fájl tartalma)
- Vagy egy fájl elérési útja

### 3. Google Gemini API kulcs

Szerezz egy API kulcsot itt: https://makersuite.google.com/app/apikey

## Használat

### Indítás

```bash
# Aktiváld a virtual environmentet
source .venv/bin/activate

# Futtasd a scriptet
python examples/foundational/49-realtime-lecture-qa.py
```

### Választható transport módok

A script támogatja a következő transport módokat:

```bash
# WebRTC (alapértelmezett, böngészős)
python examples/foundational/49-realtime-lecture-qa.py

# Daily
python examples/foundational/49-realtime-lecture-qa.py --transport daily

# Twilio
python examples/foundational/49-realtime-lecture-qa.py --transport twilio
```

### Munkafolyamat

1. **Indítás után** kapsz egy URL-t (WebRTC esetén)
2. **Nyisd meg a böngészőben** és add meg a mikrofon engedélyt
3. **Kezdd el az előadást** - minden átíródik automatikusan
4. **Közben a terminálban** már tudsz kérdéseket írni!

### Chat parancsok

A terminálban a következő parancsokat használhatod:

```bash
# Kérdés feltevése
❓ Kérdésed: Miről szólt az előadás eleje?

# Teljes átírat lekérése
❓ Kérdésed: transcript

# Kilépés a chat módból
❓ Kérdésed: quit
```

## Példa használat

```
🎤 Előadás felvevő és Q&A rendszer indítása...
✅ Kliens csatlakozott - előadás felvétel elkezdődött
💡 Az előadás automatikusan átíródik, a chat ablakban pedig kérdezhetsz róla!

📝 [2025-11-27 19:30:15] user: Sziasztok, ma a Pipecat keretrendszerről fogok beszélni...
📝 [2025-11-27 19:30:20] assistant: Rendben, figyelek!

💬 Chat mód aktiválva!
❓ Kérdésed: Miről szól a Pipecat?
🤔 Válasz generálása...
💡 Válasz: A Pipecat egy keretrendszer valós idejű hang- és multimodális botok készítésére...
```

## Fájlok

A script a következő fájlokat hozza létre:

- `lecture_transcript.txt` - Az előadás teljes átírata timestamp-ekkel

## Testreszabás

### Nyelv váltása

Magyar nyelvre van beállítva alapértelmezetten, de könnyen változtatható:

```python
# Angolra váltás
stt = GoogleSTTService(
    params=GoogleSTTService.InputParams(languages=Language.EN_US, model="chirp_3"),
    # ...
)

tts = GoogleTTSService(
    voice_id="en-US-Chirp3-HD-Charon",
    params=GoogleTTSService.InputParams(language=Language.EN_US),
    # ...
)
```

### Rendszer prompt módosítása

A `messages` listában a `system` szerepű üzenetet módosíthatod:

```python
messages = [
    {
        "role": "system",
        "content": "Az általad definiált viselkedés...",
    },
]
```

## Hibaelhárítás

### "Cannot import GoogleSTTService"
- Ellenőrizd, hogy a `pipecat` megfelelő verziója van telepítve
- Futtasd: `pip install -U pipecat-ai[google]`

### "Authentication error"
- Ellenőrizd a `GOOGLE_TEST_CREDENTIALS` és `GOOGLE_API_KEY` értékét
- Győződj meg róla, hogy a Google Cloud API-k engedélyezve vannak

### A mikrofon nem működik
- Add meg a böngésző mikrofon engedélyét
- Ellenőrizd, hogy a transport helyesen van konfigurálva

## Architektúra

```
┌─────────────────┐
│   Mikrofon      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Google STT     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Transcript     │
│  Manager        │
└────────┬────────┘
         │
         ├────► lecture_transcript.txt
         │
         ▼
┌─────────────────┐      ┌─────────────────┐
│  Chat Input     │─────►│  Google Gemini  │
└─────────────────┘      └────────┬────────┘
                                  │
                                  ▼
                         ┌─────────────────┐
                         │  Válasz         │
                         └─────────────────┘
```

## További példák

Nézd meg a többi foundational példát:
- `07n-interruptible-google.py` - Egyszerű beszélgetős bot Google szolgáltatásokkal
- `28-transcription-processor.py` - Transcript kezelés részletesen
- `15-text-qa-chat.py` - Egyszerű Q&A rendszer szöveges tudásbázissal
