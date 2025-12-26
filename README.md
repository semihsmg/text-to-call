# Text-to-Call

A CLI application that automatically calls patients to notify them about their medical reports. Converts text messages to speech using Google Cloud Text-to-Speech (Gemini) and delivers them via Netgsm phone calls.

## Features

- Dynamic message generation with patient/hospital placeholders
- Text-to-Speech using Google Cloud TTS with Gemini models
- Voice styling via natural language prompts
- Automated phone calls via Netgsm Voice API
- Auto-formatting for Turkish phone numbers
- Real-time call status polling
- Centralized configuration via `config.json`
- Dry-run mode for testing without making calls

## Prerequisites

- Python 3.14+
- Google Cloud account with Text-to-Speech API enabled
- Netgsm account with API access

## Installation

1. Clone the repository:

```bash
git clone <repository-url>
cd text-to-call
```

2. Create and activate a virtual environment:

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3.14 -m venv venv
source venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

### Google Cloud Setup

1. Install [Google Cloud CLI](https://cloud.google.com/sdk/docs/install)
2. Login and set up Application Default Credentials:

```bash
# Login to Google Cloud
gcloud auth login

# Set your project (create one at console.cloud.google.com if needed)
gcloud config set project YOUR_PROJECT_ID

# Enable Cloud Text-to-Speech API
gcloud services enable texttospeech.googleapis.com

# Set up Application Default Credentials
gcloud auth application-default login
```

3. A browser opens for authentication. After login, credentials are stored locally.

### Environment Variables

Create a `.env` file in the project root (copy from `.env.example`):

```bash
cp .env.example .env
```

Required variables:

```bash
# Google Cloud uses ADC (no env var needed)
# Netgsm credentials
NETGSM_USERNAME=850xxxxxxx
NETGSM_PASSWORD=your_api_password
```

### Netgsm Setup

1. Create a Netgsm account at [netgsm.com.tr](https://www.netgsm.com.tr)
2. Enable API access from your account settings
3. Get your username (subscriber number) and API password
4. Ensure you have sufficient credit for voice calls

### Application Configuration

Edit `config.json` to customize the message template, voice prompt, and call settings:

```json
{
  "template": {
    "message": "Sayın {name}, {hospital} hastanesinden arıyoruz...",
    "prompt": "Read in a warm, calm, and professional tone..."
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

#### Call Settings

| Setting | Description | Default |
| --- | --- | --- |
| `poll_interval` | Seconds between status checks (min 30) | 30 |
| `poll_timeout` | Max seconds to wait for call completion | 120 |
| `ring_time` | How long phone rings before giving up (10-30) | 25 |
| `filter` | Message type: 0=informational, 11=commercial | 0 |
| `time_window` | Minutes for call scheduling window | 60 |

## Usage

### Basic Usage

```bash
python main.py \
  --name "Ahmet Yılmaz" \
  --phone "+905551234567" \
  --report-type "MR" \
  --hospital "Özel Sağlık Hastanesi"
```

### With Optional Parameters

```bash
python main.py \
  --name "Ayşe Demir" \
  --phone "+905559876543" \
  --report-type "Kan Tahlili" \
  --hospital "Merkez Hastanesi" \
  --doctor "Dr. Mehmet Öz" \
  --date "26 Aralık 2024"
```

### Custom Voice Style

Override the voice prompt or voice name from config:

```bash
python main.py \
  --name "Mehmet Kaya" \
  --phone "+905551112233" \
  --report-type "Tomografi" \
  --hospital "Şifa Hastanesi" \
  --voice "Puck" \
  --prompt "Read in a cheerful and energetic tone"
```

### Dry Run (Test TTS Only)

Generate audio without making a call:

```bash
python main.py \
  --name "Test User" \
  --phone "+905551234567" \
  --report-type "MR" \
  --hospital "Test Hastanesi" \
  --dry-run
```

### Phone Number Formats

The following Turkish phone formats are accepted and auto-converted:

- `+905551234567` (E.164)
- `05551234567` (common Turkish format)
- `5551234567` (without leading zero)
- `905551234567` (country code without +)

## CLI Arguments

| Argument | Required | Description |
| --- | --- | --- |
| `--name` | Yes | Patient's full name |
| `--phone` | Yes | Phone number (auto-formatted) |
| `--report-type` | Yes | Type of medical report |
| `--hospital` | Yes | Hospital name |
| `--doctor` | No | Doctor's name |
| `--date` | No | Report ready date |
| `--prompt` | No | Override voice style prompt from config |
| `--voice` | No | Override TTS voice name (e.g., Aoede, Puck, Kore) |
| `--dry-run` | No | Generate audio only, no call |

## Template Placeholders

| Placeholder | Required | Example |
| --- | --- | --- |
| `{name}` | Yes | Ahmet Yılmaz |
| `{hospital}` | Yes | Özel Sağlık Hastanesi |
| `{report_type}` | Yes | MR, Tomografi, Kan Tahlili |
| `{date}` | No | 26 Aralık 2024 |
| `{doctor}` | No | Dr. Mehmet Öz |

## Project Structure

```text
text-to-call/
├── .env                      # Environment variables (git-ignored)
├── .env.example              # Template for .env
├── .gitignore
├── config.json               # Application configuration
├── requirements.txt
├── README.md
├── CLAUDE.md                 # Implementation guide
├── main.py                   # CLI entry point
├── src/
│   ├── __init__.py
│   ├── tts.py                # Cloud TTS module
│   ├── caller.py             # Netgsm calling module
│   └── template.py           # Message template engine
└── output/                   # Generated audio files (git-ignored)
```

## Exit Codes

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | General error / invalid arguments |
| 2 | Environment validation failed |
| 3 | TTS generation failed |
| 4 | Audio upload failed |
| 5 | Call failed (busy/no-answer/error) |

## Call Status Codes

| Status | Description |
| --- | --- |
| answered | Call was answered successfully |
| no-answer | Recipient didn't answer |
| busy | Line was busy |
| unreachable | Could not reach the number |
| failed | Call failed to connect |
| invalid-number | Phone number is invalid |
| timeout | Polling timed out |

## Troubleshooting

### "Could not automatically determine credentials"

Set up Application Default Credentials:

```bash
gcloud auth application-default login
```

### "Configuration file not found"

Ensure `config.json` exists in the project root with valid JSON.

### "Unknown placeholder in template"

Only these placeholders are allowed: `{name}`, `{hospital}`, `{report_type}`, `{date}`, `{doctor}`

### "Invalid credentials or API access denied"

Check your Netgsm credentials in `.env` and ensure API access is enabled in your Netgsm account.

### "File size exceeds 4MB limit"

Netgsm has a 4MB limit for audio files. Try shortening your message or adjusting TTS settings.

## Available Voices

The following voices are available for Gemini TTS:

- **Aoede** - Breezy, warm tone (default)
- **Puck** - Upbeat, energetic
- **Kore** - Clear, professional
- And many more...

## Netgsm API Notes

- Audio files must be WAV format (max 4MB)
- Minimum 1 hour scheduling window required by API
- Status polling limited to 2 requests per minute
- Ring time configurable between 10-30 seconds
