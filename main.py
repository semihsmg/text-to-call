#!/usr/bin/env python3
"""
Text-to-Call CLI Application

Automatically calls patients to notify them about their medical reports.
Uses Google Cloud Text-to-Speech (Gemini) for speech synthesis and Netgsm for phone calls.
"""

import argparse
import json
import os
import signal
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from src.template import TemplateError, validate_template, render_template
from src.tts import synthesize_speech, TTSConfig, TTSError
from src.caller import NetgsmCaller, CallerError, format_turkish_phone


EXIT_SUCCESS = 0
EXIT_GENERAL_ERROR = 1
EXIT_ENV_ERROR = 2
EXIT_TTS_ERROR = 3
EXIT_UPLOAD_ERROR = 4
EXIT_CALL_ERROR = 5

CONFIG_FILE = Path("config.json")


class GracefulExit(Exception):
    """Raised when user requests graceful exit."""
    pass


class ConfigError(Exception):
    """Raised when configuration is invalid."""
    pass


_caller: NetgsmCaller | None = None
_current_job_id: str | None = None


def signal_handler(signum, frame):
    """Handle CTRL+C gracefully."""
    raise GracefulExit()


def print_status(icon: str, message: str) -> None:
    """Print a status message with icon."""
    print(f"{icon} {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    print(f"✗ Error: {message}", file=sys.stderr)


def load_config() -> dict:
    """
    Load configuration from config.json.

    Raises:
        ConfigError: If config file is missing or invalid
    """
    if not CONFIG_FILE.exists():
        raise ConfigError(f"Configuration file not found: {CONFIG_FILE}")

    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigError(f"Invalid JSON in {CONFIG_FILE}: {e}")

    required_sections = ['template', 'tts', 'call']
    for section in required_sections:
        if section not in config:
            raise ConfigError(f"Missing '{section}' section in {CONFIG_FILE}")

    if 'message' not in config['template']:
        raise ConfigError("Missing 'template.message' in config")
    if 'prompt' not in config['template']:
        raise ConfigError("Missing 'template.prompt' in config")

    return config


def validate_environment() -> dict[str, str]:
    """
    Validate required environment variables.

    Google Cloud credentials are auto-detected via ADC (Application Default Credentials).
    Run 'gcloud auth application-default login' to set up ADC.

    Returns:
        Dict of validated environment variables

    Raises:
        SystemExit with EXIT_ENV_ERROR if validation fails
    """
    netgsm_vars = [
        'NETGSM_USERNAME',
        'NETGSM_PASSWORD',
    ]

    env = {}
    missing = []

    for var in netgsm_vars:
        value = os.getenv(var)
        if not value:
            missing.append(var)
        else:
            env[var] = value

    if missing:
        print_error(f"Missing environment variable(s): {', '.join(missing)}")
        print("Please set them in your .env file or environment.")
        sys.exit(EXIT_ENV_ERROR)

    return env


def create_parser() -> argparse.ArgumentParser:
    """Create CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Call patients to notify them about their medical reports.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --name "Ahmet Yılmaz" --phone "+905551234567" \\
    --hospital "Özel Sağlık Hastanesi"

  python main.py --name "Test User" --phone "05551234567" \\
    --hospital "Test Hastanesi" --dry-run

  python main.py --name "Ayşe Demir" --phone "+905559876543" \\
    --hospital "Merkez Hastanesi" --report-type "Tomografi" \\
    --voice "Puck" --prompt "Read in a cheerful tone"
        """,
    )

    parser.add_argument(
        "--name",
        required=True,
        help="Patient's full name",
    )
    parser.add_argument(
        "--phone",
        required=True,
        help="Patient's phone number (Turkish formats accepted)",
    )
    parser.add_argument(
        "--report-type",
        dest="report_type",
        help="Type of medical report (e.g., MR, Tomografi, Kan Tahlili) (optional)",
    )
    parser.add_argument(
        "--hospital",
        required=True,
        help="Hospital name",
    )
    parser.add_argument(
        "--doctor",
        help="Doctor's name (optional)",
    )
    parser.add_argument(
        "--date",
        help="Report ready date (optional)",
    )
    parser.add_argument(
        "--prompt",
        help="Override voice style prompt from config",
    )
    parser.add_argument(
        "--voice",
        help="Override TTS voice name from config (e.g., Aoede, Puck, Kore)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate audio only, don't make call",
    )

    return parser


def main() -> int:
    """Main entry point."""
    global _caller, _current_job_id

    signal.signal(signal.SIGINT, signal_handler)

    load_dotenv()

    try:
        config = load_config()
    except ConfigError as e:
        print_error(str(e))
        return EXIT_GENERAL_ERROR

    parser = create_parser()
    args = parser.parse_args()

    try:
        env = validate_environment()
    except SystemExit:
        raise

    template = config['template']['message']
    prompt = args.prompt or config['template']['prompt']

    tts_config = TTSConfig(
        model=config['tts']['model'],
        voice=args.voice or config['tts']['voice'],
        language_code=config['tts']['language_code'],
        speaking_rate=config['tts']['speaking_rate'],
        pitch=config['tts']['pitch'],
    )

    call_config = config['call']
    poll_interval = call_config.get('poll_interval', 30)
    poll_timeout = call_config.get('poll_timeout', 120)
    ring_time = call_config.get('ring_time', 25)
    message_filter = call_config.get('filter', 0)
    time_window = call_config.get('time_window', 60)

    values = {
        'name': args.name,
        'hospital': args.hospital,
    }
    if args.report_type:
        values['report_type'] = args.report_type
    if args.doctor:
        values['doctor'] = args.doctor
    if args.date:
        values['date'] = args.date

    try:
        validate_template(template, values)
    except TemplateError as e:
        print_error(str(e))
        return EXIT_GENERAL_ERROR

    message = render_template(template, values)
    print_status("✓", f"Message generated ({len(message)} chars)")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    audio_path = output_dir / f"call_{timestamp}.wav"

    try:
        synthesize_speech(message, prompt, audio_path, tts_config)
        print_status("✓", f"Audio synthesized ({audio_path})")
    except TTSError as e:
        print_error(str(e))
        return EXIT_TTS_ERROR

    if args.dry_run:
        print_status("ℹ", "Dry run mode - skipping call")
        return EXIT_SUCCESS

    try:
        format_turkish_phone(args.phone)
    except ValueError as e:
        print_error(str(e))
        return EXIT_GENERAL_ERROR

    _caller = NetgsmCaller(
        username=env['NETGSM_USERNAME'],
        password=env['NETGSM_PASSWORD'],
        ring_time=ring_time,
        message_filter=message_filter,
        time_window=time_window,
    )

    try:
        audio_id = _caller.upload_audio(audio_path)
        print_status("✓", f"Audio uploaded to Netgsm (ID: {audio_id})")
    except CallerError as e:
        print_error(f"Failed to upload audio: {e}")
        return EXIT_UPLOAD_ERROR

    try:
        _current_job_id = _caller.make_call(audio_id, args.phone)
        print_status("✓", f"Call initiated (Job ID: {_current_job_id})")

        def status_callback(status: str) -> None:
            print_status("⏳", f"Call status: {status}")

        result = _caller.poll_call_status(
            _current_job_id,
            timeout=poll_timeout,
            interval=poll_interval,
            status_callback=status_callback,
        )

        _caller.cleanup()

        if result.status == 'answered':
            print_status("✓", "Call completed - answered")
            return EXIT_SUCCESS
        elif result.status == 'timeout':
            print_status("⚠", "Call polling timed out - call may still be in progress")
            return EXIT_CALL_ERROR
        else:
            print_status("✗", f"Call ended with status: {result.status}")
            return EXIT_CALL_ERROR

    except GracefulExit:
        print()
        print_status("⚠", "Interrupted by user")
        if _current_job_id:
            print_status("ℹ", f"Job {_current_job_id} may still be in progress")
        if _caller:
            _caller.cleanup()
        return EXIT_GENERAL_ERROR

    except CallerError as e:
        print_error(f"Call failed: {e}")
        if _caller:
            _caller.cleanup()
        return EXIT_CALL_ERROR


if __name__ == "__main__":
    sys.exit(main())
