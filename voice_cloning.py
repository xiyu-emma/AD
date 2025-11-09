# voice_cloning.py
# Voice Cloning System using TTS with Reference Audio

import os
import threading
import queue
import time
import json
import uuid
from tkinter import messagebox
import pyaudio
import wave
import numpy as np
import soundfile as sf
import librosa
from typing import Optional, List
import traceback

XTTS_AVAILABLE = False
try:
    from TTS.api import TTS
    XTTS_AVAILABLE = True
except ImportError:
    print("[警告] TTS 庫未安裝，voice cloning 功能將被禁用。")
    TTS = None

TTS_MODEL_CANDIDATES = [
    "tts_models/multilingual/multi-dataset/xtts_v2",
    "tts_models/multilingual/multi-dataset/xtts_v1",
    "tts_models/multilingual/zh/glow-tts",
]


class VoiceCloningSystem:
    """聲音克隆系統 - 錄製參考音頻，克隆用戶音色進行 TTS 合成"""
    
    def __init__(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.voice_profiles_dir = os.path.join(base_dir, "voice_clones")
        self.current_profile = None
        self.recording = False
        self.audio_queue = queue.Queue()
        self.pa = None
        self.stream = None
        self.recorded_frames = []
        self.tts_model = None
        self.tts_model_name = None
        self.tts_device = None
        
        # 確保目錄存在
        os.makedirs(self.voice_profiles_dir, exist_ok=True)
        
        # 載入現有的語音設定
        self.load_profile_settings()
        
        # 初始化 TTS 模型
        if XTTS_AVAILABLE:
            self.initialize_tts_model()
    
    def initialize_tts_model(self):
        """初始化 TTS 模型"""
        if not XTTS_AVAILABLE:
            print("[警告] TTS 庫不可用，跳過初始化")
            return
        
        if self.tts_model is not None:
            return
        
        device_preference = "cuda" if self._has_gpu() else "cpu"
        last_error = None
        
        for model_name in TTS_MODEL_CANDIDATES:
            try:
                print(f"[語音克隆] 正在載入 TTS 模型: {model_name}...")
                tts = TTS(model_name=model_name, progress_bar=True)
                actual_device = device_preference
                
                try:
                    tts.to(device_preference)
                except AttributeError:
                    # 舊版 API 沒有 to() 函式，需要透過 gpu 參數初始化
                    if device_preference == "cuda":
                        tts = TTS(model_name=model_name, progress_bar=True, gpu=True)
                        actual_device = "cuda"
                    else:
                        actual_device = "cpu"
                except Exception as move_err:
                    if device_preference == "cuda":
                        print(f"[警告] 將模型移至 GPU 失敗: {move_err}，改用 CPU")
                        actual_device = "cpu"
                        try:
                            tts.to("cpu")
                        except Exception:
                            pass
                
                self.tts_model = tts
                self.tts_model_name = model_name
                self.tts_device = actual_device
                print(f"[語音克隆] TTS 模型已初始化: {model_name} (使用 {actual_device})")
                return
            except Exception as e:
                last_error = e
                print(f"[警告] 模型 {model_name} 初始化失敗: {e}")
        
        print(f"[錯誤] 初始化 TTS 模型失敗: {last_error}")
        self.tts_model = None
        self.tts_model_name = None
        self.tts_device = None
    
    def _has_gpu(self) -> bool:
        """檢查是否有 GPU 可用"""
        try:
            import torch
            return torch.cuda.is_available()
        except:
            return False
    
    def load_profile_settings(self):
        """載入語音設定檔"""
        try:
            settings_file = os.path.join(self.voice_profiles_dir, "profile_settings.json")
            if os.path.exists(settings_file):
                with open(settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    self.current_profile = settings.get("current_profile", None)
        except Exception as e:
            print(f"載入語音設定失敗: {e}")
    
    def save_profile_settings(self):
        """保存語音設定檔"""
        try:
            settings_file = os.path.join(self.voice_profiles_dir, "profile_settings.json")
            settings = {
                "current_profile": self.current_profile,
                "last_updated": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            with open(settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存語音設定失敗: {e}")
    
    def get_voice_profiles(self) -> List[str]:
        """獲取所有可用的語音設定檔"""
        profiles = []
        try:
            for item in os.listdir(self.voice_profiles_dir):
                if item in {"__pycache__"} or item.startswith('.'):
                    continue
                item_path = os.path.join(self.voice_profiles_dir, item)
                if os.path.isdir(item_path):
                    profiles.append(item)
        except Exception as e:
            print(f"獲取語音設定檔失敗: {e}")
        return sorted(profiles)
    
    def profile_has_reference_audio(self, profile_name: str) -> bool:
        """檢查指定語音設定檔是否已有參考音頻"""
        profile_path = os.path.join(self.voice_profiles_dir, profile_name)
        reference_audio = os.path.join(profile_path, "reference_audio.wav")
        return os.path.exists(reference_audio)
    
    def create_voice_profile(self, profile_name: str) -> bool:
        """創建新的語音設定檔目錄"""
        try:
            profile_path = os.path.join(self.voice_profiles_dir, profile_name)
            if os.path.exists(profile_path):
                messagebox.showerror("錯誤", f"語音設定檔 '{profile_name}' 已存在")
                return False
            
            os.makedirs(profile_path, exist_ok=True)
            return True
        except Exception as e:
            messagebox.showerror("錯誤", f"創建語音設定檔失敗: {e}")
            return False
    
    def start_recording(self) -> bool:
        """開始錄音"""
        if self.recording:
            return False
        
        try:
            self.pa = pyaudio.PyAudio()
            self.recorded_frames = []
            
            # 錄音參數
            FORMAT = pyaudio.paInt16
            CHANNELS = 1
            RATE = 22050  # TTS 常用的採樣率
            CHUNK = 1024
            
            self.stream = self.pa.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK
            )
            
            self.recording = True
            
            # 在背景執行緒中錄音
            def record_audio():
                while self.recording:
                    try:
                        data = self.stream.read(CHUNK, exception_on_overflow=False)
                        self.recorded_frames.append(data)
                    except Exception as e:
                        print(f"錄音錯誤: {e}")
                        break
            
            self.record_thread = threading.Thread(target=record_audio, daemon=True)
            self.record_thread.start()
            
            return True
            
        except Exception as e:
            print(f"開始錄音失敗: {e}")
            self.stop_recording()
            return False
    
    def stop_recording(self) -> Optional[str]:
        """停止錄音並返回錄音檔案路徑"""
        if not self.recording:
            return None
        
        self.recording = False
        
        try:
            FORMAT = pyaudio.paInt16
            CHANNELS = 1
            RATE = 22050
            sample_width = None
            
            if self.pa:
                try:
                    sample_width = self.pa.get_sample_size(FORMAT)
                except Exception:
                    sample_width = 2  # 預設 16-bit
            
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
                self.stream = None
            
            if self.pa:
                self.pa.terminate()
                self.pa = None
            
            # 保存錄音
            if self.recorded_frames:
                temp_filename = f"temp_recording_{uuid.uuid4()}.wav"
                temp_path = os.path.join(self.voice_profiles_dir, temp_filename)
                
                with wave.open(temp_path, 'wb') as wf:
                    wf.setnchannels(CHANNELS)
                    wf.setsampwidth(sample_width or 2)
                    wf.setframerate(RATE)
                    wf.writeframes(b''.join(self.recorded_frames))
                
                self.recorded_frames = []
                return temp_path
                
        except Exception as e:
            print(f"停止錄音失敗: {e}")
        
        return None
    
    def save_reference_audio(self, profile_name: str, audio_path: str) -> bool:
        """保存參考音頻到指定設定檔"""
        try:
            profile_path = os.path.join(self.voice_profiles_dir, profile_name)
            if not os.path.exists(profile_path):
                os.makedirs(profile_path, exist_ok=True)
            
            target_path = os.path.join(profile_path, "reference_audio.wav")
            
            # 音訊處理和優化
            self._process_audio_file(audio_path, target_path)
            
            # 清理暫存檔案
            if os.path.exists(audio_path):
                os.remove(audio_path)
            
            return True
            
        except Exception as e:
            print(f"保存參考音頻失敗: {e}")
            return False
    
    def _process_audio_file(self, input_path: str, output_path: str):
        """處理音訊檔案：標準化音量、去除靜音等"""
        try:
            # 讀取音訊
            y, sr = librosa.load(input_path, sr=22050)
            
            # 去除首尾靜音
            y, _ = librosa.effects.trim(y, top_db=20)
            
            # 標準化音量
            y = librosa.util.normalize(y)
            
            # 確保最少2秒長度（voice cloning 需要足夠長的參考音頻）
            min_length = int(2.0 * sr)
            if len(y) < min_length:
                y = np.pad(y, (0, min_length - len(y)), mode='constant')
            
            # 保存處理後的音訊
            sf.write(output_path, y, 22050, subtype='PCM_16')
            
        except Exception as e:
            print(f"處理音訊檔案失敗: {e}")
            # 如果處理失敗，直接複製原始檔案
            import shutil
            shutil.copy2(input_path, output_path)
    
    def delete_voice_profile(self, profile_name: str) -> bool:
        """刪除語音設定檔"""
        try:
            profile_path = os.path.join(self.voice_profiles_dir, profile_name)
            if os.path.exists(profile_path):
                import shutil
                shutil.rmtree(profile_path)
                
                # 如果刪除的是目前使用的設定檔，重置設定
                if self.current_profile == profile_name:
                    self.current_profile = None
                    self.save_profile_settings()
                
                return True
        except Exception as e:
            print(f"刪除語音設定檔失敗: {e}")
        return False
    
    def set_active_profile(self, profile_name: str):
        """設定目前使用的語音設定檔"""
        if profile_name in self.get_voice_profiles():
            self.current_profile = profile_name
            self.save_profile_settings()
            return True
        return False
    
    def get_reference_audio_path(self, profile_name: Optional[str] = None) -> Optional[str]:
        """獲取指定或目前使用的參考音頻路徑"""
        profile = profile_name or self.current_profile
        if not profile:
            return None
        
        profile_path = os.path.join(self.voice_profiles_dir, profile)
        reference_audio = os.path.join(profile_path, "reference_audio.wav")
        
        if os.path.exists(reference_audio):
            return reference_audio
        
        return None
    
    def synthesize_with_cloned_voice(self, text: str, output_path: str, language: str = "zh-TW") -> bool:
        """使用克隆的聲音合成語音"""
        if not XTTS_AVAILABLE:
            print("[警告] TTS 模型未安裝，無法進行語音克隆")
            return False
        
        if self.tts_model is None:
            self.initialize_tts_model()
        
        if self.tts_model is None:
            print("[警告] TTS 模型未初始化")
            return False
        
        reference_audio = self.get_reference_audio_path()
        if not reference_audio:
            print("[警告] 沒有可用的參考音頻")
            return False
        
        try:
            print(f"[語音克隆] 正在使用克隆聲音合成: {text}")
            
            # 確保輸出目錄存在
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
            
            language_code = self._map_language_code(language)
            kwargs = {
                "text": text,
                "file_path": output_path,
                "speaker_wav": reference_audio,
            }
            if language_code:
                kwargs["language"] = language_code
            
            try:
                self.tts_model.tts_to_file(**kwargs)
            except TypeError as type_err:
                error_message = str(type_err)
                if "language" in kwargs and ("language" in error_message or "unexpected keyword" in error_message):
                    print(f"[警告] 當前模型不支援 language 參數: {type_err}，將改用模型預設語言")
                    kwargs.pop("language", None)
                    self.tts_model.tts_to_file(**kwargs)
                elif "speaker_wav" in kwargs and "speaker_wav" in error_message:
                    print(f"[錯誤] 當前載入的模型不支援 speaker_wav 參數: {type_err}")
                    print("[提示] 請確保已下載 XTTS 模型以使用語音克隆功能。")
                    return False
                else:
                    raise
            
            print(f"[語音克隆] 合成完成: {output_path}")
            return True
            
        except Exception as e:
            print(f"[錯誤] 合成語音失敗: {e}")
            traceback.print_exc()
            return False
    
    def _map_language_code(self, language: str) -> str:
        """將語言代碼映射到 TTS 支持的格式"""
        if not language:
            return ""
        normalized = language.strip()
        key = normalized.replace("_", "-").lower()
        language_map = {
            "zh-tw": "zh-tw",  # 中文（臺灣）
            "zh-hant": "zh-tw",
            "zh-cn": "zh-cn",
            "zh": "zh-cn",
            "en-us": "en",
            "en-gb": "en",
            "en": "en",
        }
        return language_map.get(key, key)


# 全域語音克隆系統實例
voice_cloning_system = VoiceCloningSystem() if XTTS_AVAILABLE else None
