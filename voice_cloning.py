# voice_cloning.py
# Voice Cloning System using TTS with Reference Audio

import os
import threading
import queue
import time
import json
import uuid
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import pyaudio
import wave
import numpy as np
import soundfile as sf
import librosa
from typing import Optional, Dict, List
import traceback

XTTS_AVAILABLE = False
try:
    from TTS.api import TTS
    XTTS_AVAILABLE = True
except ImportError:
    print("[警告] TTS 庫未安裝，voice cloning 功能將被禁用。")
    TTS = None


class VoiceCloningSystem:
    """聲音克隆系統 - 錄製參考音頻，克隆用戶音色進行 TTS 合成"""
    
    def __init__(self):
        self.voice_profiles_dir = "voice_clones"
        self.current_profile = None
        self.recording = False
        self.audio_queue = queue.Queue()
        self.pa = None
        self.stream = None
        self.recorded_frames = []
        self.tts_model = None
        
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
        
        try:
            print("[語音克隆] 正在初始化 TTS 模型...")
            device = "cuda" if self._has_gpu() else "cpu"
            self.tts_model = TTS(
                model_name="tts_models/multilingual/zh/glow-tts",
                progress_bar=True,
                gpu=(device == "cuda")
            )
            print(f"[語音克隆] TTS 模型已初始化 (使用 {device})")
        except Exception as e:
            print(f"[錯誤] 初始化 TTS 模型失敗: {e}")
            self.tts_model = None
    
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
                item_path = os.path.join(self.voice_profiles_dir, item)
                if os.path.isdir(item_path) and item != "__pycache__":
                    # 檢查是否包含參考音頻檔案
                    if self._validate_profile(item_path):
                        profiles.append(item)
        except Exception as e:
            print(f"獲取語音設定檔失敗: {e}")
        return profiles
    
    def _validate_profile(self, profile_path: str) -> bool:
        """驗證語音設定檔是否有效"""
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
    
    def start_recording(self, callback=None):
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
                
                if callback:
                    callback()
            
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
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
            
            if self.pa:
                self.pa.terminate()
            
            # 保存錄音
            if self.recorded_frames:
                temp_filename = f"temp_recording_{uuid.uuid4()}.wav"
                temp_path = os.path.join(self.voice_profiles_dir, temp_filename)
                
                FORMAT = pyaudio.paInt16
                CHANNELS = 1
                RATE = 22050
                
                with wave.open(temp_path, 'wb') as wf:
                    wf.setnchannels(CHANNELS)
                    wf.setsampwidth(self.pa.get_sample_size(FORMAT))
                    wf.setframerate(RATE)
                    wf.writeframes(b''.join(self.recorded_frames))
                
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
    
    def get_reference_audio_path(self) -> Optional[str]:
        """獲取目前使用的參考音頻路徑"""
        if not self.current_profile:
            return None
        
        profile_path = os.path.join(self.voice_profiles_dir, self.current_profile)
        reference_audio = os.path.join(profile_path, "reference_audio.wav")
        
        if os.path.exists(reference_audio):
            return reference_audio
        
        return None
    
    def synthesize_with_cloned_voice(self, text: str, output_path: str, language: str = "zh-TW") -> bool:
        """使用克隆的聲音合成語音"""
        if not XTTS_AVAILABLE or not self.tts_model:
            print("[警告] TTS 模型未初始化")
            return False
        
        reference_audio = self.get_reference_audio_path()
        if not reference_audio:
            print("[警告] 沒有可用的參考音頻")
            return False
        
        try:
            print(f"[語音克隆] 正在使用克隆聲音合成: {text}")
            
            # 確保輸出目錄存在
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # 使用 speaker_wav 參數進行 voice cloning
            self.tts_model.tts_to_file(
                text=text,
                file_path=output_path,
                speaker_wav=reference_audio,
                language=self._map_language_code(language)
            )
            
            print(f"[語音克隆] 合成完成: {output_path}")
            return True
            
        except Exception as e:
            print(f"[錯誤] 合成語音失敗: {e}")
            traceback.print_exc()
            return False
    
    def _map_language_code(self, language: str) -> str:
        """將語言代碼映射到 TTS 支持的格式"""
        language_map = {
            "zh-TW": "zh-cn",  # 中文 (簡體/繁體)
            "zh-CN": "zh-cn",
            "en-US": "en",
            "en": "en",
            "zh": "zh-cn"
        }
        return language_map.get(language, language)


# 全域語音克隆系統實例
voice_cloning_system = VoiceCloningSystem() if XTTS_AVAILABLE else None