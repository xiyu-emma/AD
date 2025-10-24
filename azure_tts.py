import os
import html
import asyncio
from functools import lru_cache
from typing import Optional

import requests

AZURE_TTS_REGION = "eastasia"
AZURE_TTS_ENDPOINT = f"https://{AZURE_TTS_REGION}.tts.speech.microsoft.com/cognitiveservices/v1"
AZURE_TTS_OUTPUT_FORMAT = "audio-24khz-96kbitrate-mono-mp3"
AZURE_TTS_KEY_FILENAME = "ttsapi.txt"
AZURE_TTS_USER_AGENT = "NarrationGeneratorApp/1.0"

_session = requests.Session()


class AzureTTSException(Exception):
    pass


class AzureTTSConfigError(AzureTTSException):
    pass


@lru_cache(maxsize=1)
def _load_subscription_key() -> str:
    key_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), AZURE_TTS_KEY_FILENAME)
    if not os.path.exists(key_path):
        raise AzureTTSConfigError(f"找不到 '{AZURE_TTS_KEY_FILENAME}' 檔案。")

    with open(key_path, "r", encoding="utf-8") as f:
        key = f.read().strip()
    if not key:
        raise AzureTTSConfigError(f"'{AZURE_TTS_KEY_FILENAME}' 檔案內容為空。")
    return key


def _infer_locale_from_voice(voice: str) -> str:
    parts = voice.split("-")
    if len(parts) >= 2:
        return "-".join(parts[:2])
    return "zh-TW"


def _speech_rate_to_percent(speech_rate: float) -> str:
    diff = (speech_rate - 1.0) * 100.0
    diff = max(min(diff, 90.0), -90.0)
    if abs(diff) < 1e-3:
        return "0%"
    return f"{diff:+.0f}%"


def synthesize_speech_to_file(
    text: str,
    voice: str,
    output_path: str,
    speech_rate: float = 1.0,
    language: Optional[str] = None,
) -> None:
    if not text or not text.strip():
        raise AzureTTSException("文字內容不可為空。")

    key = _load_subscription_key()
    locale = language or _infer_locale_from_voice(voice)

    prosody_rate = _speech_rate_to_percent(speech_rate)
    escaped_text = html.escape(text.strip())
    ssml = (
        f"<speak version='1.0' xml:lang='{locale}'>"
        f"<voice name='{voice}' xml:lang='{locale}'>"
        f"<prosody rate='{prosody_rate}'>{escaped_text}</prosody>"
        f"</voice></speak>"
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    headers = {
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": AZURE_TTS_OUTPUT_FORMAT,
        "User-Agent": AZURE_TTS_USER_AGENT,
    }

    try:
        response = _session.post(
            AZURE_TTS_ENDPOINT,
            headers=headers,
            data=ssml.encode("utf-8"),
            timeout=45,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise AzureTTSException(f"Azure TTS 請求失敗: {exc}") from exc

    try:
        with open(output_path, "wb") as f:
            f.write(response.content)
    except OSError as exc:
        raise AzureTTSException(f"寫入語音檔案時發生錯誤: {exc}") from exc


def _run_in_executor_sync(func, *args):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return func(*args)
    else:
        return loop.run_in_executor(None, func, *args)


async def synthesize_speech_to_file_async(
    text: str,
    voice: str,
    output_path: str,
    speech_rate: float = 1.0,
    language: Optional[str] = None,
) -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        synthesize_speech_to_file,
        text,
        voice,
        output_path,
        speech_rate,
        language,
    )
