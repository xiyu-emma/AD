# Azure TTS 設定指南

本專案已經從 Edge TTS 遷移至 Azure TTS (East Asia 區域)。

## 設定步驟

1. **取得 Azure TTS API 金鑰**
   - 前往 [Azure Portal](https://portal.azure.com)
   - 建立或使用現有的 Azure 認知服務資源
   - 在資源的「金鑰和端點」頁面取得訂閱金鑰

2. **配置專案**
   - 在專案根目錄建立 `ttsapi.txt` 檔案
   - 將您的 Azure TTS 訂閱金鑰貼入檔案中
   - 儲存檔案

   範例 `ttsapi.txt` 內容：
   ```
   your_azure_subscription_key_here
   ```

3. **區域設定**
   - 本專案已設定使用 **East Asia** (eastasia) 區域
   - 如需更改區域，請修改 `azure_tts.py` 中的 `AZURE_TTS_REGION` 變數

## 支援的語音

專案預設使用以下 Azure Neural 語音：

- **中文 (台灣)**: `zh-TW-HsiaoChenNeural`
- **英文 (美國)**: `en-US-JennyNeural`

您可以在 `voice_interface.py` 中的 `LANG_CONFIG` 修改語音設定。

如需其他語音選項，請參考 [Azure TTS 語音清單](https://learn.microsoft.com/azure/cognitive-services/speech-service/language-support?tabs=tts)。

## 注意事項

- `ttsapi.txt` 已加入 `.gitignore`，不會被提交到版本控制
- 請妥善保管您的 API 金鑰，避免洩露
- Azure TTS 為付費服務，請注意使用量和費用

## 疑難排解

如果遇到問題，請確認：

1. `ttsapi.txt` 檔案存在且包含有效的 API 金鑰
2. API 金鑰沒有多餘的空白或換行
3. 您的 Azure 訂閱處於啟用狀態
4. 網路連線正常，可以存取 Azure 服務
