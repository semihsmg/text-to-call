import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import requests


UPLOAD_URL = "https://api.netgsm.com.tr/voicesms/upload"
SEND_URL = "https://api.netgsm.com.tr/voicesms/send"
REPORT_URL = "https://api.netgsm.com.tr/voicesms/report"

TERMINAL_STATUSES = {1, 2, 3, 4, 5, 6, 7, 8, 9}

STATUS_MESSAGES = {
    0: "waiting",
    1: "answered",
    2: "no-answer",
    3: "unreachable",
    4: "insufficient-balance",
    5: "cancelled",
    6: "failed",
    7: "busy",
    8: "invalid-number",
    9: "expired",
}


class CallerError(Exception):
    """Raised when call operations fail."""
    pass


@dataclass
class CallResult:
    """Result of a phone call."""
    job_id: str
    status: str
    status_code: int | None = None


def format_turkish_phone(phone: str) -> str:
    """
    Format a Turkish phone number for Netgsm (without + prefix).

    Accepts:
    - +905551234567 (E.164)
    - 05551234567 (common Turkish)
    - 5551234567 (without leading zero)
    - 905551234567 (country code without +)

    Returns:
        Phone number in format 905551234567

    Raises:
        ValueError: If phone format is invalid
    """
    digits = re.sub(r'\D', '', phone)

    if digits.startswith('90') and len(digits) == 12:
        return digits
    elif digits.startswith('0') and len(digits) == 11:
        return f'9{digits}'
    elif len(digits) == 10 and digits.startswith('5'):
        return f'90{digits}'
    else:
        raise ValueError(
            f"Invalid Turkish phone format: {phone}. "
            "Expected formats: +905551234567, 05551234567, 5551234567, 905551234567"
        )


class NetgsmCaller:
    """Handles Netgsm operations for making voice calls."""

    def __init__(
        self,
        username: str,
        password: str,
        ring_time: int = 25,
        message_filter: int = 0,
        time_window: int = 60,
    ):
        self.username = username
        self.password = password
        self.ring_time = ring_time
        self.message_filter = message_filter
        self.time_window = time_window
        self._audio_id: str | None = None

    def upload_audio(self, audio_path: Path) -> str:
        """
        Upload audio file to Netgsm.

        Returns:
            Audio ID for use in voice messages
        """
        with open(audio_path, 'rb') as f:
            response = requests.post(
                UPLOAD_URL,
                data={
                    'username': self.username,
                    'password': self.password,
                },
                files={'dosya': (audio_path.name, f, 'audio/wav')},
            )

        result = response.text.strip()

        if result in ('10', '20', '30', '40'):
            error_messages = {
                '10': "File upload failed",
                '20': "Invalid file extension (only .wav allowed)",
                '30': "Invalid credentials or API access denied",
                '40': "File size exceeds 4MB limit",
            }
            raise CallerError(error_messages[result])

        self._audio_id = result
        return self._audio_id

    def make_call(self, audio_id: str, to_phone: str) -> str:
        """
        Initiate a voice call using uploaded audio.

        Returns:
            Job ID (bulkid) for tracking
        """
        formatted_phone = format_turkish_phone(to_phone)

        now = datetime.now()
        stop_time = now + timedelta(minutes=self.time_window)

        xml_payload = f"""<?xml version='1.0' encoding='UTF-8'?>
<mainbody>
    <header>
        <usercode>{self.username}</usercode>
        <password>{self.password}</password>
        <startdate>{now.strftime('%d%m%Y')}</startdate>
        <starttime>{now.strftime('%H%M')}</starttime>
        <stopdate>{stop_time.strftime('%d%m%Y')}</stopdate>
        <stoptime>{stop_time.strftime('%H%M')}</stoptime>
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
            SEND_URL,
            data=xml_payload.encode('utf-8'),
            headers={'Content-Type': 'application/xml; charset=utf-8'},
        )

        result = response.text.strip()
        parts = result.split()

        if len(parts) >= 1:
            code = parts[0]

            if code in ('30', '40', '45', '70'):
                error_messages = {
                    '30': "Invalid credentials or API access denied",
                    '40': "Audio file not found",
                    '45': "Phone number not provided",
                    '70': "Invalid request parameters",
                }
                raise CallerError(error_messages[code])

            if code in ('00', '01', '02') and len(parts) >= 2:
                return parts[1]

            if code.isdigit() and len(code) > 2:
                return code

        raise CallerError(f"Unexpected response from Netgsm: {result}")

    def poll_call_status(
        self,
        job_id: str,
        timeout: int = 120,
        interval: int = 30,
        status_callback=None,
    ) -> CallResult:
        """
        Poll call status until terminal state or timeout.

        Args:
            job_id: The job ID (bulkid) to monitor
            timeout: Maximum seconds to wait
            interval: Seconds between polls (min 30 due to rate limit)
            status_callback: Optional callback(status) for status updates

        Returns:
            CallResult with final status
        """
        start_time = time.time()
        last_status = None

        interval = max(interval, 30)

        while time.time() - start_time < timeout:
            response = requests.get(
                REPORT_URL,
                params={
                    'usercode': self.username,
                    'password': self.password,
                    'bulkid': job_id,
                    'type': '0',
                },
            )

            result = response.text.strip()

            if result in ('30', '60', '80', '100'):
                if result == '60':
                    time.sleep(interval)
                    continue
                elif result == '80':
                    time.sleep(interval)
                    continue

                error_messages = {
                    '30': "Invalid credentials",
                    '100': "System error",
                }
                raise CallerError(error_messages.get(result, f"Error: {result}"))

            parts = result.split()
            if len(parts) >= 3:
                try:
                    status_code = int(parts[2])
                    status_str = STATUS_MESSAGES.get(status_code, f"unknown-{status_code}")

                    if status_str != last_status:
                        last_status = status_str
                        if status_callback:
                            status_callback(status_str)

                    if status_code in TERMINAL_STATUSES:
                        return CallResult(
                            job_id=job_id,
                            status=status_str,
                            status_code=status_code,
                        )
                except (ValueError, IndexError):
                    pass

            time.sleep(interval)

        return CallResult(
            job_id=job_id,
            status='timeout',
            status_code=None,
        )

    def cleanup(self) -> None:
        """Cleanup resources (no-op for Netgsm as we keep audio files)."""
        self._audio_id = None
