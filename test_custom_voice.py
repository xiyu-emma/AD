#!/usr/bin/env python3
# test_custom_voice.py
"""
測試客製化語音功能的基本運作
"""

import sys
import os

def test_imports():
    """測試所有必要的導入"""
    print("測試導入...")
    
    try:
        import tkinter as tk
        print("✓ tkinter 導入成功")
    except ImportError as e:
        print(f"✗ tkinter 導入失敗: {e}")
        return False
    
    try:
        import pyaudio
        print("✓ pyaudio 導入成功")
    except ImportError as e:
        print(f"✗ pyaudio 導入失敗: {e}")
        print("  請執行: pip install pyaudio")
        return False
    
    try:
        import soundfile
        print("✓ soundfile 導入成功")
    except ImportError as e:
        print(f"✗ soundfile 導入失敗: {e}")
        print("  請執行: pip install soundfile")
        return False
    
    try:
        import librosa
        print("✓ librosa 導入成功")
    except ImportError as e:
        print(f"✗ librosa 導入失敗: {e}")
        print("  請執行: pip install librosa")
        return False
    
    try:
        from custom_voice import custom_voice_system
        print("✓ custom_voice_system 導入成功")
    except ImportError as e:
        print(f"✗ custom_voice_system 導入失敗: {e}")
        return False
    
    try:
        from voice_interface import speak, _get_custom_voice_file
        print("✓ voice_interface 函數導入成功")
    except ImportError as e:
        print(f"✗ voice_interface 函數導入失敗: {e}")
        return False
    
    return True

def test_custom_voice_system():
    """測試客製化語音系統的基本功能"""
    print("\n測試客製化語音系統...")
    
    try:
        from custom_voice import custom_voice_system
        
        # 測試獲取語音設定檔列表
        profiles = custom_voice_system.get_voice_profiles()
        print(f"✓ 獲取語音設定檔列表: {len(profiles)} 個設定檔")
        
        # 測試創建設定檔
        test_profile_name = "test_profile"
        if custom_voice_system.create_voice_profile(test_profile_name):
            print(f"✓ 創建測試設定檔: {test_profile_name}")
            
            # 測試獲取語音檔案
            voice_file = custom_voice_system.get_voice_file("hello")
            print(f"✓ 獲取語音檔案路徑: {voice_file}")
            
            # 清理測試設定檔
            custom_voice_system.delete_voice_profile(test_profile_name)
            print(f"✓ 刪除測試設定檔: {test_profile_name}")
        else:
            print("✗ 創建測試設定檔失敗")
            return False
        
        return True
        
    except Exception as e:
        print(f"✗ 測試客製化語音系統時發生錯誤: {e}")
        return False

def test_voice_interface():
    """測試語音介面的客製化功能"""
    print("\n測試語音介面...")
    
    try:
        from voice_interface import _get_custom_voice_file, CUSTOM_VOICE_ENABLED
        
        if not CUSTOM_VOICE_ENABLED:
            print("✗ 客製化語音功能未啟用")
            return False
        
        # 測試文字到語音檔案的映射
        test_cases = [
            ("歡迎使用", "hello"),
            ("系統準備就緒", "system_ready"),
            ("正在處理中", "processing"),
            ("處理完成", "completed"),
            ("發生錯誤", "error")
        ]
        
        for text, expected_type in test_cases:
            voice_file = _get_custom_voice_file(text)
            print(f"✓ 文字 '{text}' -> 語音檔案: {voice_file}")
        
        return True
        
    except Exception as e:
        print(f"✗ 測試語音介面時發生錯誤: {e}")
        return False

def main():
    """主測試函數"""
    print("開始測試客製化語音功能...\n")
    
    all_tests_passed = True
    
    # 測試導入
    if not test_imports():
        all_tests_passed = False
    
    # 測試客製化語音系統
    if not test_custom_voice_system():
        all_tests_passed = False
    
    # 測試語音介面
    if not test_voice_interface():
        all_tests_passed = False
    
    print("\n" + "="*50)
    if all_tests_passed:
        print("🎉 所有測試通過！客製化語音功能已成功整合。")
        print("\n使用說明：")
        print("1. 啟動 main.py")
        print("2. 點擊 '🎙️客製化語音設定' 按鈕")
        print("3. 創建新的語音設定檔")
        print("4. 錄製5個基本語音樣本")
        print("5. 設為預設語音")
        print("6. 享受個人化的語音體驗！")
    else:
        print("❌ 部分測試失敗，請檢查錯誤訊息並安裝必要的依賴。")
    
    return all_tests_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)