"""
OpenClaw Voice — Sarvam AI STT Client
========================================
Transcribes voice commands in Hindi, Hinglish, and Indian languages
using Sarvam AI's saaras:v3 speech-to-text model.
"""

import os
import io
import asyncio
import base64
from typing import Optional

try:
    import requests
except ImportError:
    requests = None

try:
    import sounddevice as sd
    import scipy.io.wavfile as wavfile
    import numpy as np
except ImportError:
    sd = None


class SarvamSTTClient:
    """
    Sarvam AI Speech-to-Text client.
    
    Records audio from the microphone and transcribes it using
    Sarvam AI's saaras:v3 model, which is purpose-built for Indian
    languages and handles Hindi-English code-switching naturally.
    """

    def __init__(self):
        self.api_key = os.getenv("SARVAM_API_KEY", "")
        self.model = os.getenv("SARVAM_STT_MODEL", "saaras:v3")
        self.api_url = os.getenv("SARVAM_API_URL", "https://api.sarvam.ai/speech-to-text")
        self.sample_rate = 16000  # 16 kHz for STT
        self.channels = 1

    async def record_and_transcribe(self, duration: float = 5.0) -> str:
        """
        Record audio from the microphone and transcribe it.
        
        Args:
            duration: Recording duration in seconds
            
        Returns:
            Transcribed text
        """
        audio_data = await self.record_audio(duration)
        if audio_data is None:
            return "Error: Could not record audio"

        return await self.transcribe(audio_data)

    async def record_audio(self, duration: float = 5.0) -> Optional[bytes]:
        """
        Record audio from the default microphone.
        
        Returns raw WAV bytes.
        """
        if sd is None:
            print("[Voice] sounddevice not installed")
            return None

        try:
            print(f"[Voice] Recording for {duration}s... Speak now!")

            # Record audio
            recording = await asyncio.to_thread(
                sd.rec,
                int(duration * self.sample_rate),
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype='int16',
            )
            await asyncio.to_thread(sd.wait)

            print("[Voice] Recording complete")

            # Convert to WAV bytes
            buffer = io.BytesIO()
            wavfile.write(buffer, self.sample_rate, recording)
            return buffer.getvalue()

        except Exception as e:
            print(f"[Voice] Recording error: {e}")
            return None

    async def transcribe(self, audio_data: bytes) -> str:
        """
        Send audio to Sarvam AI STT and get transcription.
        
        Args:
            audio_data: WAV audio bytes
            
        Returns:
            Transcribed text
        """
        if not self.api_key:
            return "Error: Sarvam AI API key not configured"

        if requests is None:
            return "Error: requests library not installed"

        try:
            # Sarvam AI expects multipart form data or base64
            headers = {
                "api-subscription-key": self.api_key,
            }

            # Encode audio as base64
            audio_b64 = base64.b64encode(audio_data).decode("utf-8")

            payload = {
                "model": self.model,
                "audio": audio_b64,
                "language": "auto",  # Auto-detect Hindi/English/Hinglish
            }

            response = await asyncio.to_thread(
                requests.post,
                self.api_url,
                headers=headers,
                json=payload,
                timeout=30,
            )

            if response.status_code == 200:
                result = response.json()
                transcript = result.get("transcript", "")
                language = result.get("language_code", "unknown")
                print(f"[Voice] Transcribed ({language}): {transcript}")
                return transcript
            else:
                error = response.text
                print(f"[Voice] STT API error ({response.status_code}): {error}")
                return f"Error: STT failed with status {response.status_code}"

        except Exception as e:
            print(f"[Voice] Transcription error: {e}")
            return f"Error: {e}"

    async def transcribe_file(self, file_path: str) -> str:
        """Transcribe an audio file."""
        with open(file_path, "rb") as f:
            audio_data = f.read()
        return await self.transcribe(audio_data)

    def is_available(self) -> bool:
        """Check if voice input is available."""
        return bool(self.api_key and sd is not None)
