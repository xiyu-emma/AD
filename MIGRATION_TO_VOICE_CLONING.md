# Migration to Voice Cloning System

## 概述
本次更新將客製化語音系統完全替換為語音克隆系統，讓用戶通過錄製一段參考音頻來克隆自己的音色進行 TTS 合成。

## 主要變更

### 1. 新文件
- **voice_cloning.py**: 語音克隆系統的核心實現
  - VoiceCloningSystem 類用於管理語音克隆
  - 支持多聲音檔案的創建和管理
  - 集成 Coqui TTS 進行 voice cloning

### 2. 修改的文件

#### main.py
- 移除 `CUSTOM_VOICE_ENABLED` 和相關導入
- 新增 `VOICE_CLONING_ENABLED` 標誌
- 用 `VoiceCloningDialog` 替換 `CustomVoiceDialog`
- 用 `open_voice_cloning_dialog()` 替換 `open_custom_voice_dialog()`
- 用 `voice_cloning_button` 替換 `custom_voice_button`
- 按鈕文本從「客製化語音設定」改為「語音克隆設定」

#### voice_interface.py
- 移除舊的客製化語音導入
- 新增語音克隆導入 (`from voice_cloning import voice_cloning_system, XTTS_AVAILABLE`)
- 修改 `speak()` 函數優先使用 `_generate_cloned_voice()`
- 用 `_generate_cloned_voice()` 替換 `_get_custom_voice_file()`
- 保留 Azure TTS 作為後備方案

#### requirements.txt
- 新增 `TTS>=0.22.0` 依賴

#### .gitignore
- 新增 `voice_clones/` 目錄
- 新增 `temp_audio/` 目錄

### 3. 保留的文件（不再使用）
- **custom_voice.py**: 保留用於參考，但不再使用

## 工作流程變更

### 舊系統 (客製化語音)
1. 用戶錄製 5 個預設文字的音頻
2. 系統根據文字內容選擇播放對應的音頻

### 新系統 (語音克隆)
1. 用戶錄製一段 2-5 秒的參考音頻
2. 系統克隆用戶的音色特徵
3. 系統使用克隆的音色進行所有 TTS 合成

## 技術架構

### 核心組件
- **TTS 模型**: Coqui TTS GLOW-TTS (multilingual/zh)
- **錄音**: PyAudio 高質量錄製
- **音頻處理**: librosa 進行標準化和清理
- **GPU 支持**: 自動檢測並使用 CUDA（如可用）

### 文件結構
```
voice_clones/
├── 克隆名稱/
│   └── reference_audio.wav
├── 克隆名稱 2/
│   └── reference_audio.wav
└── profile_settings.json
```

## 向後相容性

- 保持相同的 GUI 介面和按鈕位置
- 用戶界面更為簡化（只需一個錄音按鈕）
- 如果 TTS 庫未安裝，系統自動回退到 Azure TTS
- 語音設定自動保存，重啟應用時記憶用戶選擇

## 依賴項變更

### 新增
- `TTS>=0.22.0`: Coqui TTS 庫

### 已有且使用
- `pyaudio>=0.2.11`: 音頻錄製
- `librosa>=0.10.0`: 音頻處理
- `soundfile>=0.12.1`: 音頻 I/O
- `torch`: TTS 模型運行

## 測試建議

1. **基本功能**:
   - 創建新克隆
   - 錄製參考音頻
   - 設為預設
   - 驗證 TTS 使用克隆音色

2. **錯誤處理**:
   - 無麥克風時的行為
   - TTS 庫未安裝時的回退
   - 無效參考音頻的處理

3. **性能**:
   - 首次運行模型下載時間
   - 合成速度 (應在 2-10 秒)
   - 內存使用情況

## 遷移說明

對於現有用戶：
- 舊的 5 個預錄語音檔案將不再使用
- 需要重新進行語音克隆設置
- `custom_voices/` 目錄可安全刪除
- 新的克隆將存儲在 `voice_clones/` 目錄中

## 故障排查

- 見 VOICE_CLONING_README.md 中的故障排查部分
- 檢查 TTS 模型是否正確下載 (~500MB)
- 驗證麥克風在系統中是否正常工作
- 查看控制台輸出中的錯誤信息

---

**更新日期**: 2024年  
**系統版本**: 1.0.0
