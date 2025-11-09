# custom_voice.py

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

# --- 語音客製化系統 ---
class CustomVoiceSystem:
    def __init__(self):
        self.voice_profiles_dir = "custom_voices"
        self.current_voice_profile = None
        self.recording = False
        self.audio_queue = queue.Queue()
        self.pa = None
        self.stream = None
        self.recorded_frames = []
        
        # 確保目錄存在
        os.makedirs(self.voice_profiles_dir, exist_ok=True)
        
        # 載入現有的語音設定
        self.load_voice_settings()
        
    def load_voice_settings(self):
        """載入語音設定檔"""
        try:
            settings_file = os.path.join(self.voice_profiles_dir, "voice_settings.json")
            if os.path.exists(settings_file):
                with open(settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    self.current_voice_profile = settings.get("current_profile", None)
        except Exception as e:
            print(f"載入語音設定失敗: {e}")
            
    def save_voice_settings(self):
        """保存語音設定檔"""
        try:
            settings_file = os.path.join(self.voice_profiles_dir, "voice_settings.json")
            settings = {
                "current_profile": self.current_voice_profile,
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
                    # 檢查是否包含必要的錄音檔案
                    if self._validate_voice_profile(item_path):
                        profiles.append(item)
        except Exception as e:
            print(f"獲取語音設定檔失敗: {e}")
        return profiles
    
    def _validate_voice_profile(self, profile_path: str) -> bool:
        """驗證語音設定檔是否完整"""
        required_files = [
            "hello.wav",
            "system_ready.wav", 
            "processing.wav",
            "completed.wav",
            "error.wav"
        ]
        for filename in required_files:
            filepath = os.path.join(profile_path, filename)
            if not os.path.exists(filepath):
                return False
        return True
    
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
            RATE = 44100
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
                RATE = 44100
                
                with wave.open(temp_path, 'wb') as wf:
                    wf.setnchannels(CHANNELS)
                    wf.setsampwidth(self.pa.get_sample_size(FORMAT))
                    wf.setframerate(RATE)
                    wf.writeframes(b''.join(self.recorded_frames))
                
                return temp_path
                
        except Exception as e:
            print(f"停止錄音失敗: {e}")
            
        return None
    
    def save_voice_sample(self, profile_name: str, sample_type: str, audio_path: str) -> bool:
        """保存語音樣本到指定設定檔"""
        try:
            profile_path = os.path.join(self.voice_profiles_dir, profile_name)
            if not os.path.exists(profile_path):
                os.makedirs(profile_path, exist_ok=True)
            
            target_filename = f"{sample_type}.wav"
            target_path = os.path.join(profile_path, target_filename)
            
            # 音訊處理和優化
            self._process_audio_file(audio_path, target_path)
            
            # 清理暫存檔案
            if os.path.exists(audio_path):
                os.remove(audio_path)
            
            return True
            
        except Exception as e:
            print(f"保存語音樣本失敗: {e}")
            return False
    
    def _process_audio_file(self, input_path: str, output_path: str):
        """處理音訊檔案：標準化音量、去除靜音等"""
        try:
            # 讀取音訊
            y, sr = librosa.load(input_path, sr=44100)
            
            # 去除首尾靜音
            y, _ = librosa.effects.trim(y, top_db=20)
            
            # 標準化音量
            y = librosa.util.normalize(y)
            
            # 如果音訊太短，進行輕微延長
            min_length = int(1.0 * sr)  # 最少1秒
            if len(y) < min_length:
                y = np.pad(y, (0, min_length - len(y)), mode='constant')
            
            # 保存處理後的音訊
            sf.write(output_path, y, sr, subtype='PCM_16')
            
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
                if self.current_voice_profile == profile_name:
                    self.current_voice_profile = None
                    self.save_voice_settings()
                
                return True
        except Exception as e:
            print(f"刪除語音設定檔失敗: {e}")
        return False
    
    def set_active_voice_profile(self, profile_name: str):
        """設定目前使用的語音設定檔"""
        if profile_name in self.get_voice_profiles():
            self.current_voice_profile = profile_name
            self.save_voice_settings()
            return True
        return False
    
    def get_voice_file(self, text_type: str) -> Optional[str]:
        """根據文字類型獲取對應的語音檔案路徑"""
        if not self.current_voice_profile:
            return None
            
        profile_path = os.path.join(self.voice_profiles_dir, self.current_voice_profile)
        
        # 文字類型到檔案名稱的映射
        file_mapping = {
            "hello": "hello.wav",
            "system_ready": "system_ready.wav",
            "processing": "processing.wav", 
            "completed": "completed.wav",
            "error": "error.wav",
            "welcome": "hello.wav",
            "success": "completed.wav",
            "failure": "error.wav"
        }
        
        filename = file_mapping.get(text_type.lower())
        if filename:
            filepath = os.path.join(profile_path, filename)
            if os.path.exists(filepath):
                return filepath
        
        return None

# 全域語音客製化系統實例
custom_voice_system = CustomVoiceSystem()