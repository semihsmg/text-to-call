# CLAUDE.md - Text-to-Call Implementation Guide

## Project Overview

CLI demo application that calls patients to notify them about medical reports. Converts text to speech using Google Cloud Text-to-Speech (Gemini) and delivers via Netgsm phone call.

**Scope:** Single phone number, dynamic message generation, no database.

---

## Technical Stack

| Component | Technology | Details |
| --- | --- | --- |
| Language | Python | 3.14 |
| TTS Engine | Google Cloud TTS | Gemini models with prompt support |
| TTS Model | gemini-2.5-flash-tts | Configurable in config.json |
| TTS Voice | Aoede | Breezy tone, Turkish |
| Voice Calls | Netgsm | Voice SMS API |
| Audio Hosting | Netgsm | Upload via API |
| Configuration | config.json | Centralized settings |
| Secrets | python-dotenv | `.env` file |

---

## Architecture

```
CLI (main.py)
    │
    ▼
┌─────────────────────┐
│  Load config.json   │  Template, TTS settings, call settings
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│  Template Engine    │  Replace {name}, {hospital}, etc.
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│  Cloud TTS (Gemini) │  Text + Prompt → WAV file
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│  Netgsm Upload      │  Upload WAV → get audio ID
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│  Netgsm Call        │  Initiate call → Poll status
└─────────────────────┘
    │
    ▼
📞 Patient receives call
```

---

## Implementation Decisions

### TTS API: Google Cloud Text-to-Speech

**Decision:** Use Cloud TTS API instead of Generative AI API.
**Rationale:** Dedicated `prompt` field for voice styling, explicit language/encoding control, better suited for production use.

**Features used:**

- `prompt` field for natural language voice direction
- `speaking_rate` and `pitch` controls
- Explicit `language_code` (tr-TR)
- LINEAR16 audio encoding for WAV output

### Configuration: Centralized config.json

**Decision:** All settings in a single `config.json` file (committed to repo).
**Rationale:** Single source of truth, easy to modify without code changes.

**Structure:**

```json
{
  "template": {
    "message": "...",
    "prompt": "..."
  },
  "tts": {
    "model": "gemini-2.5-flash-tts",
    "voice": "Aoede",
    "language_code": "tr-TR",
    "speaking_rate": 1.0,
    "pitch": 0
  },
  "call": {
    "poll_interval": 30,
    "poll_timeout": 120,
    "ring_time": 25,
    "filter": 0,
    "time_window": 60
  }
}
```

### CLI Overrides

**Decision:** Only `--prompt` and `--voice` are overridable via CLI.
**Rationale:** Message template is fixed in config; only voice styling needs runtime flexibility.

### Voice Provider: Netgsm

**Decision:** Use Netgsm for voice calls instead of Twilio.
**Rationale:** Twilio doesn't support Turkey-based calling; Netgsm is a local provider with better Turkey support.

**API Endpoints:**

- Upload: `https://api.netgsm.com.tr/voicesms/upload`
- Send: `https://api.netgsm.com.tr/voicesms/send`
- Report: `https://api.netgsm.com.tr/voicesms/report`

**Behavior:**

- Upload WAV file (max 4MB) to get audio ID
- Send voice message using audio ID
- Poll status every 30 seconds (API rate limit: 2/min)
- Keep audio on Netgsm (no cleanup API available)

### Phone Number Handling: Auto-format

**Decision:** Accept multiple Turkish phone formats, auto-convert for Netgsm.
**Rationale:** Better UX, reduces user errors.

**Accepted formats:**

- `+905551234567` → `905551234567`
- `05551234567` → `905551234567`
- `5551234567` → `905551234567`
- `905551234567` → `905551234567`

### Template Handling: Strict Validation

**Decision:** Error on missing required placeholders AND unknown placeholders.
**Rationale:** Fail fast, prevent malformed messages from being sent.

**Required placeholders:** `{name}`, `{hospital}`
**Optional placeholders:** `{report_type}`, `{date}`, `{doctor}`

### Call Status: Poll Until Completion

**Decision:** Poll call status (30s interval, 120s timeout).
**Rationale:** User needs feedback on whether call was successful.

**Status Codes:**

| Code | Status | Description |
| --- | --- | --- |
| 0 | waiting | Waiting to be answered |
| 1 | answered | Call was answered |
| 2 | no-answer | Not answered |
| 3 | unreachable | Cannot reach |
| 4 | insufficient-balance | Account balance issue |
| 5 | cancelled | Call cancelled |
| 6 | failed | Call failed |
| 7 | busy | Line busy |
| 8 | invalid-number | Invalid phone number |
| 9 | expired | Call expired |

### Error Handling: Moderate

**Decision:** Validate inputs, meaningful error messages, graceful failures.
**Rationale:** Balance between robustness and demo simplicity.

- Strict config.json validation on startup
- Strict env var validation (ADC + Netgsm)
- Graceful CTRL+C handling during poll
- No retry logic (report failure and exit)

---

## Exit Codes

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | General error / invalid arguments / config error |
| 2 | Environment validation failed |
| 3 | TTS generation failed |
| 4 | Audio upload failed |
| 5 | Call failed (busy/no-answer/error) |

---

## Project Structure

```text
text-to-call/
├── .env                      # Environment variables (git-ignored)
├── .env.example              # Template for .env
├── .gitignore
├── config.json               # Application configuration (committed)
├── requirements.txt
├── README.md
├── CLAUDE.md                 # This file
├── main.py                   # CLI entry point
├── src/
│   ├── __init__.py
│   ├── tts.py                # Cloud TTS module
│   ├── caller.py             # Netgsm calling module
│   └── template.py           # Message template engine
└── output/                   # Generated audio files (git-ignored)
```

---

## CLI Reference

| Argument | Required | Description |
| --- | --- | --- |
| `--name` | Yes | Patient's full name |
| `--phone` | Yes | Phone number (auto-formatted) |
| `--report-type` | No | Type of medical report |
| `--hospital` | Yes | Hospital name |
| `--doctor` | No | Doctor's name |
| `--date` | No | Report ready date |
| `--prompt` | No | Override voice prompt from config |
| `--voice` | No | Override voice name from config |
| `--dry-run` | No | Generate audio only, no call |

---

## Code Patterns

### TTS Module (src/tts.py)

```python
from google.cloud import texttospeech

def synthesize_speech(text: str, prompt: str, output_path: Path, config: TTSConfig) -> Path:
    client = texttospeech.TextToSpeechClient()

    synthesis_input = texttospeech.SynthesisInput(
        text=text,
        prompt=prompt,
    )

    voice = texttospeech.VoiceSelectionParams(
        language_code=config.language_code,
        name=config.voice,
        model_name=config.model,
    )

    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16,
        speaking_rate=config.speaking_rate,
        pitch=config.pitch,
    )

    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config,
    )

    with open(output_path, "wb") as f:
        f.write(response.audio_content)

    return output_path
```

### Netgsm Caller (src/caller.py)

```python
import requests

class NetgsmCaller:
    def upload_audio(self, audio_path: Path) -> str:
        response = requests.post(
            "https://api.netgsm.com.tr/voicesms/upload",
            data={'username': self.username, 'password': self.password},
            files={'dosya': (audio_path.name, f, 'audio/wav')},
        )
        return response.text.strip()  # Returns audio ID

    def make_call(self, audio_id: str, to_phone: str) -> str:
        xml_payload = f"""<?xml version='1.0' encoding='UTF-8'?>
        <mainbody>
            <header>
                <usercode>{self.username}</usercode>
                <password>{self.password}</password>
                <startdate>{start_date}</startdate>
                <starttime>{start_time}</starttime>
                <stopdate>{stop_date}</stopdate>
                <stoptime>{stop_time}</stoptime>
                <key>0</key>
                <filter>{self.message_filter}</filter>
                <ringtime>{self.ring_time}</ringtime>
            </header>
            <body>
                <audioid>{audio_id}</audioid>
                <no>{formatted_phone}</no>
            </body>
        </mainbody>"""
        response = requests.post(
            "https://api.netgsm.com.tr/voicesms/send",
            data=xml_payload.encode('utf-8'),
            headers={'Content-Type': 'application/xml; charset=utf-8'},
        )
        # Returns "00 123456" where 123456 is job ID
        return job_id
```

---

## Environment Variables

Google Cloud uses Application Default Credentials (ADC):

```bash
gcloud auth application-default login
```

Required in `.env`:

```bash
NETGSM_USERNAME=850xxxxxxx
NETGSM_PASSWORD=your_api_password
```

---

## File Generation

Auto-create on startup:

- `output/` directory

Git-ignored files:

- `.env`
- `output/`
