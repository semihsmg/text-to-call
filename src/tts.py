from dataclasses import dataclass
from pathlib import Path

from google.cloud import texttospeech


class TTSError(Exception):
    """Raised when TTS generation fails."""
    pass


@dataclass
class TTSConfig:
    """Configuration for TTS synthesis."""
    model: str = "gemini-2.5-flash-tts"
    voice: str = "Aoede"
    language_code: str = "tr-TR"
    speaking_rate: float = 1.0
    pitch: float = 0.0


def synthesize_speech(
    text: str,
    prompt: str,
    output_path: Path,
    config: TTSConfig | None = None,
) -> Path:
    """
    Synthesize speech from text using Google Cloud Text-to-Speech with Gemini.

    Args:
        text: The text to convert to speech
        prompt: Voice styling instructions (e.g., "Read in a warm tone")
        output_path: Path where the WAV file will be saved
        config: TTS configuration (model, voice, etc.)

    Returns:
        Path to the generated WAV file

    Raises:
        TTSError: If speech synthesis fails
    """
    if config is None:
        config = TTSConfig()

    try:
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

        if not response.audio_content:
            raise TTSError("No audio data received from Cloud TTS")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "wb") as f:
            f.write(response.audio_content)

        return output_path

    except Exception as e:
        if isinstance(e, TTSError):
            raise
        raise TTSError(f"Failed to synthesize speech: {e}") from e
