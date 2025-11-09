# voice_interface.py 

import os
import re
import speech_recognition as sr
import asyncio
import nest_asyncio
import time
import pygame
import json
from datetime import datetime
import winsound
import traceback
import uuid
import html
from functools import lru_cache
from typing import Optional
import requests

# --- 語音克隆系統 ---
try:
    from voice_cloning import voice_cloning_system, XTTS_AVAILABLE
    VOICE_CLONING_ENABLED = XTTS_AVAILABLE
except ImportError:
    print("[警告] voice_cloning.py 未找到或 TTS 庫未安裝，語音克隆功能將被禁用。")
    VOICE_CLONING_ENABLED = False
    voice_cloning_system = None

# --- Azure TTS 整合開始 ---

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

# --- Azure TTS 整合結束 ---


# --------------------------------------------------------------------------
#                           【語音設定】
# --------------------------------------------------------------------------
LANG_CONFIG = {
    "zh-TW": {"voice": "zh-TW-HsiaoChenNeural", "locale": "zh-TW"},
    "en-US": {"voice": "en-US-JennyNeural", "locale": "en-US"},
}

# --------------------------------------------------------------------------
#                           【全語音UX系統】
# --------------------------------------------------------------------------
class VoiceUXSystem:
    def __init__(self):
        self.speech_rate = 1.0
        self.volume = 1.0
        self.enable_sound_cues = True
        self.beginner_mode = True
        self.load_settings()

    def load_settings(self):
        try:
            if os.path.exists("voice_settings.json"):
                with open("voice_settings.json", 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    self.speech_rate = settings.get("speech_rate", 1.0)
                    self.volume = settings.get("volume", 1.0)
                    self.beginner_mode = settings.get("beginner_mode", True)
        except Exception as e:
            print(f"讀取設定檔時發生錯誤: {e}")

    def save_settings(self):
        # (在此專案中，設定模組暫不整合，但保留函式)
        pass

voice_ux = VoiceUXSystem()

# --------------------------------------------------------------------------
#                           【音效系統】
# --------------------------------------------------------------------------
class AudioFeedback:
    @staticmethod
    def beep_success():
        if voice_ux.enable_sound_cues:
            try:
                winsound.Beep(800, 150); time.sleep(0.1); winsound.Beep(1200, 150)
            except Exception as e: print(f"播放成功音效失敗: {e}")

    @staticmethod
    def beep_error():
        if voice_ux.enable_sound_cues:
            try: winsound.Beep(300, 300)
            except Exception as e: print(f"播放錯誤音效失敗: {e}")

    @staticmethod
    def beep_listening():
        if voice_ux.enable_sound_cues:
            try: winsound.Beep(600, 100)
            except Exception as e: print(f"播放聆聽音效失敗: {e}")

audio = AudioFeedback()

# --------------------------------------------------------------------------
#                           【初始化】
# --------------------------------------------------------------------------
try:
    nest_asyncio.apply()
except RuntimeError:
    pass # 如果已經應用過，忽略錯誤

try:
    pygame.mixer.init()
    print("Pygame mixer 初始化成功。")
except pygame.error as e:
    print(f"[嚴重警告] Pygame mixer 初始化失敗: {e}")
    print("  -> 語音播放功能將無法使用。請檢查您的音訊設備或驅動程式。")
    # 可以選擇禁用語音功能或退出程式
    # sys.exit(1)

# --------------------------------------------------------------------------
#                           【核心語音功能】
# --------------------------------------------------------------------------
def detect_language(text):
    if not text: return "zh-TW" # 預設中文
    english_chars = len(re.findall(r'[a-zA-Z]', text))
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    return "en-US" if english_chars > chinese_chars else "zh-TW"

def speak(text, wait=True):
    """增強版語音輸出，包含語音克隆支援和錯誤處理"""
    if not text or not text.strip(): return
    if not pygame.mixer.get_init():
        print("[錯誤] Pygame mixer 未初始化，無法播放語音。")
        return

    # 嘗試使用語音克隆
    if VOICE_CLONING_ENABLED and voice_cloning_system:
        cloned_voice_file = _generate_cloned_voice(text)
        if cloned_voice_file and os.path.exists(cloned_voice_file):
            # 播放克隆的語音檔案
            try:
                pygame.mixer.music.load(cloned_voice_file)
                pygame.mixer.music.set_volume(voice_ux.volume)
                pygame.mixer.music.play()
                
                if wait:
                    while pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                        time.sleep(0.1)
                return
            except Exception as e:
                print(f"播放克隆語音失敗，回退到 TTS: {e}")

    # 回退到原本的 TTS 系統
    speech_rate = voice_ux.speech_rate
    lang_code = detect_language(text)
    voice = LANG_CONFIG[lang_code]["voice"]

    temp_dir = "temp_audio"
    os.makedirs(temp_dir, exist_ok=True)
    output_file = os.path.join(temp_dir, f"speech_{uuid.uuid4()}.mp3")

    async def _generate_speech():
        try:
            locale = LANG_CONFIG[lang_code].get("locale", "zh-TW")
            await synthesize_speech_to_file_async(
                text,
                voice,
                output_file,
                speech_rate=speech_rate,
                language=locale,
            )

            if not pygame.mixer.get_init():
                print("[警告] Pygame mixer 在生成語音後變為未初始化狀態。")
                return

            try:
                pygame.mixer.music.load(output_file)
                pygame.mixer.music.set_volume(voice_ux.volume)
                pygame.mixer.music.play()
            except pygame.error as pg_err:
                print(f"Pygame 載入或播放錯誤: {pg_err}")
                audio.beep_error()
                return

            if wait:
                while pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                    await asyncio.sleep(0.1)

        except AzureTTSException as e:
            print(f"語音生成錯誤 (Azure TTS): {e}")
            audio.beep_error()
        except Exception as e:
            print(f"語音生成或播放時發生未知錯誤: {e}")
            traceback.print_exc()
            audio.beep_error()
        finally:
            try:
                if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                    pygame.mixer.music.stop()
                if pygame.mixer.get_init():
                    pygame.mixer.music.unload()
            except Exception:
                pass

            await asyncio.sleep(0.2)

            if os.path.exists(output_file):
                try:
                    for _ in range(3):
                        try:
                            os.remove(output_file)
                            break
                        except PermissionError:
                            await asyncio.sleep(0.3)
                    else:
                        print(f"[警告] 無法刪除暫存語音檔 (可能仍被占用): {output_file}")
                except Exception as e:
                    print(f"[警告] 刪除暫存語音檔時發生錯誤: {e}")

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_generate_speech())
    except RuntimeError:
        try:
            asyncio.run(_generate_speech())
        except Exception as e:
            print(f"執行 asyncio.run 時出錯: {e}")


def _generate_cloned_voice(text: str) -> Optional[str]:
    """使用克隆的聲音生成語音檔案"""
    if not VOICE_CLONING_ENABLED or not voice_cloning_system:
        return None
    
    # 檢查是否有啟用的語音設定檔
    if not voice_cloning_system.current_profile:
        return None
    
    try:
        temp_dir = "temp_audio"
        os.makedirs(temp_dir, exist_ok=True)
        output_file = os.path.join(temp_dir, f"cloned_voice_{uuid.uuid4()}.wav")
        
        # 檢測語言
        lang_code = detect_language(text)
        
        # 使用克隆的聲音合成
        success = voice_cloning_system.synthesize_with_cloned_voice(
            text=text,
            output_path=output_file,
            language=lang_code
        )
        
        if success and os.path.exists(output_file):
            return output_file
        
    except Exception as e:
        print(f"[錯誤] 生成克隆語音失敗: {e}")
        traceback.print_exc()
    
    return None


def voice_input(prompt, timeout=15):
    """統一的語音輸入介面"""
    if voice_ux.beginner_mode:
        speak(prompt + "。聆聽中，請在提示音後說話")
    else:
        speak(prompt)

    audio.beep_listening()
    result = recognize_speech(timeout)

    if result and result not in ["timeout", "error", "unknown"]:
        audio.beep_success()
        return result

    # 提供更具體的失敗原因
    if result == "timeout":
        speak("沒有聽到聲音，請再說一次")
    elif result == "unknown":
        speak("聽不清楚，請大聲一點")
    else: # "error" 或 None
        speak("語音辨識時發生錯誤，請檢查麥克風或網路連線。")
    audio.beep_error()
    return None

def recognize_speech(timeout=15):
    """核心語音辨識"""
    r = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            # print("正在調整環境噪音...") # 調試用
            r.adjust_for_ambient_noise(source, duration=0.5)
            # print("請開始說話...") # 調試用
            # 使用 listen_in_background 可能更適合 GUI，但 listen 較簡單
            audio_data = r.listen(source, timeout=timeout, phrase_time_limit=10)
            # print("正在辨識...") # 調試用
            text = r.recognize_google(audio_data, language="zh-TW")
            print(f"辨識到: {text.strip()}")
            return text.strip()
    except sr.WaitTimeoutError:
        print("語音輸入超時。")
        return "timeout"
    except sr.UnknownValueError:
        print("Google Speech Recognition 無法理解音訊。")
        return "unknown"
    except sr.RequestError as e:
        print(f"無法從 Google Speech Recognition 服務請求結果: {e}")
        return "error"
    except Exception as e:
        print(f"麥克風或語音辨識時發生未知錯誤: {e}")
        traceback.print_exc()
        return "error"

# --------------------------------------------------------------------------
#                           【快捷指令系統】
# --------------------------------------------------------------------------
class VoiceCommands:
    COMMANDS = {
        # 主選單操作指令
        "生成圖像": "image", "圖像": "image", "圖片": "image",
        "生成影片": "video", "影片": "video",
        # 系統指令
        "結束": "exit", "離開": "exit", "掰掰": "exit",
    }

    @classmethod
    def parse(cls, text):
        if not text: return None
        text_lower = text.lower().strip()
        # 優先完全匹配或包含關鍵字
        for key, value in cls.COMMANDS.items():
            # 使用 lower() 比較確保不分大小寫
            if key.lower() in text_lower:
                print(f"指令解析: '{text}' -> '{value}' (匹配 '{key}')")
                return value
        print(f"指令解析: '{text}' -> 未匹配到關鍵字，返回原文")
        return text # 如果沒有匹配，回傳原始文字 (已轉小寫並去除空白)