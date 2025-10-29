# UI 主題說明 - Sun Valley ttk Theme

## 概述

本專案已整合 [Sun Valley ttk theme](https://github.com/rdbende/Sun-Valley-ttk-theme) 來美化使用者介面。Sun Valley 是一個現代化的 ttk 主題，提供淺色和深色模式，靈感來自 Windows 11 的設計語言。

## 主題特色

- ✨ **現代化設計**：乾淨、簡潔的視覺風格
- 🎨 **淺色模式**：預設使用淺色主題，適合長時間使用
- 📱 **響應式佈局**：支援視窗縮放和最大化
- 🎯 **一致性**：所有 ttk 元件都自動應用主題樣式

## 安裝依賴

主題已通過 PyPI 安裝：

```bash
pip install sv-ttk
```

## 使用方式

在 `main.py` 中，主題通過以下方式應用：

```python
import sv_ttk

# 在創建 GUI 後應用淺色主題
sv_ttk.set_theme("light")
```

## 自定義樣式

除了基礎的 Sun Valley 主題外，我們還添加了以下自定義樣式增強：

### 標題樣式
- `Header.TLabel` - 大標題 (28pt, 粗體)
- `SubHeader.TLabel` - 副標題 (11pt)
- `SectionTitle.TLabel` - 區段標題 (11pt, 粗體)

### 按鈕樣式
- `Primary.TButton` - 主要操作按鈕 (12pt, 粗體, 較大 padding)
- `Secondary.TButton` - 次要操作按鈕 (11pt, 中等 padding)
- `Accent.TButton` - 強調按鈕 (11pt, 粗體)

### 容器樣式
- `Card.TLabelframe` - 卡片式標籤框架 (邊框加強)
- `Card.TLabelframe.Label` - 標籤框架的標題 (12pt, 粗體)

### 其他
- `Status.TLabel` - 狀態列標籤 (10pt, padding 優化)

## UI 元件改進

### 改進前的問題
- 使用硬編碼的顏色常數
- 手動配置每個元件的樣式
- 不一致的視覺效果
- 較難維護

### 改進後的優點
- ✅ 專業的主題系統
- ✅ 自動處理顏色和樣式
- ✅ 一致的使用者體驗
- ✅ 易於維護和擴展
- ✅ 支援主題切換（可擴展為深色模式）

## 主要變更

1. **移除自定義主題常數**
   - 刪除所有 `THEME_*` 顏色常數
   - 移除手動樣式配置代碼

2. **整合 Sun Valley 主題**
   - 導入 `sv_ttk` 模組
   - 應用 `light` 主題
   - 保留必要的自定義樣式增強

3. **UI 元件優化**
   - 使用 emoji 圖示增強視覺識別
   - 添加分隔線提升版面結構
   - 優化間距和 padding
   - 改進狀態列顯示

4. **字體統一**
   - 統一使用 `Segoe UI` 字體家族
   - 確保跨平台一致性
   - 優化可讀性

## 切換主題（可選）

如果需要切換到深色模式，只需修改 `create_gui()` 函式中的：

```python
sv_ttk.set_theme("light")  # 改為 "dark"
```

## 注意事項

- Sun Valley 主題只作用於 `ttk` 元件
- 標準 `tkinter` 元件（如 `scrolledtext.ScrolledText`）需要額外配置
- 在 Windows 11 上可以進一步優化標題欄顏色（參考 Sun Valley 文檔）

## 參考資源

- [Sun Valley ttk Theme GitHub](https://github.com/rdbende/Sun-Valley-ttk-theme)
- [Sun Valley 使用文檔](https://github.com/rdbende/Sun-Valley-ttk-theme/wiki/Usage-with-Python)
- [PyPI 套件](https://pypi.org/project/sv-ttk/)
