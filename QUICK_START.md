# 快速開始指南 - UI 主題更新

## 🚀 快速啟動

### 1. 安裝依賴
```bash
pip install -r requirements.txt
```

主要新增依賴：
- `sv-ttk>=2.6.0` - Sun Valley ttk 主題

### 2. 執行應用程式
```bash
python main.py
```

### 3. 體驗新 UI
應用程式啟動後，您將看到：
- 🎙️ 現代化的標題和副標題
- 🖼️ 🎬 📸 三個主要功能按鈕
- 📷 🎬 兩個預覽區域（圖像和影片）
- 📋 執行日誌區域
- ✓ 狀態列

## 📖 文檔

### 主要文檔
1. **UI_THEME_README.md** - 主題系統詳細說明
2. **CHANGELOG_UI_THEME.md** - 完整更新日誌
3. **UI_COMPARISON.md** - 改進前後對比

### 代碼示例

#### 應用主題
```python
import sv_ttk

# 應用淺色主題
sv_ttk.set_theme("light")

# 如需深色主題（未來支援）
# sv_ttk.set_theme("dark")
```

#### 自定義樣式
```python
style = ttk.Style()

# 配置標題樣式
style.configure("Header.TLabel", 
    font=("Segoe UI", 28, "bold"))

# 配置按鈕樣式
style.configure("Primary.TButton", 
    font=("Segoe UI", 12, "bold"), 
    padding=(18, 14))
```

#### 使用樣式
```python
# 標題
title_label = ttk.Label(
    parent, 
    text="🎙️ 口述影像生成系統",
    style="Header.TLabel"
)

# 按鈕
action_button = ttk.Button(
    parent,
    text="🖼️ 生成圖像口述影像",
    command=callback,
    style="Primary.TButton"
)
```

## 🎨 可用樣式

### 標籤樣式
- `Header.TLabel` - 主標題 (28pt, 粗體)
- `SubHeader.TLabel` - 副標題 (11pt)
- `SectionTitle.TLabel` - 區段標題 (11pt, 粗體)
- `Status.TLabel` - 狀態文字 (10pt)

### 按鈕樣式
- `Primary.TButton` - 主要操作（深色背景）
- `Secondary.TButton` - 次要操作（淺色背景）
- `Accent.TButton` - 強調操作（特殊顏色）

### 容器樣式
- `Card.TLabelframe` - 卡片式容器
- `Card.TLabelframe.Label` - 卡片標題

## 🔧 常見問題

### Q: 如何切換到深色模式？
A: 修改 `main.py` 中的 `create_gui()` 函式：
```python
sv_ttk.set_theme("dark")  # 改為 "dark"
```

### Q: 主題沒有正確應用？
A: 確保：
1. 已安裝 `sv-ttk` 套件
2. 在創建所有元件之前調用 `sv_ttk.set_theme()`
3. 使用 ttk 元件而非標準 tkinter 元件

### Q: 如何自定義顏色？
A: Sun Valley 主題的顏色是內建的，如需完全自定義，可：
1. 使用 `style.configure()` 覆蓋特定樣式
2. 使用 `style.map()` 自定義狀態顏色
3. 創建自己的自定義樣式

### Q: ScrolledText 顏色不匹配？
A: ScrolledText 是標準 tkinter 元件，需手動配置：
```python
style = ttk.Style()
bg_color = style.lookup("TLabel", "background") or "#fafafa"
fg_color = style.lookup("TLabel", "foreground") or "#1c1c1c"

text_widget = scrolledtext.ScrolledText(
    parent,
    bg=bg_color,
    fg=fg_color,
    relief=tk.FLAT,
    borderwidth=0
)
```

## 📱 測試

### 簡單測試
```bash
python test_ui.py
```

這會啟動一個簡化版的 UI 來測試主題是否正確載入。

### 功能測試
1. 啟動完整應用程式：`python main.py`
2. 測試三個主要功能按鈕
3. 檢查預覽區域顯示
4. 驗證執行日誌輸出
5. 確認狀態列更新

## 🌟 主要特色

### 視覺改進
- ✨ 現代化、專業的外觀
- ✨ 一致的視覺語言
- ✨ 更好的色彩對比
- ✨ 優化的間距和布局

### 技術改進
- 🔧 使用專業主題系統
- 🔧 移除硬編碼顏色
- 🔧 更易於維護
- 🔧 支援主題切換

### 使用體驗
- 🎯 清晰的功能分區
- 🎯 直觀的視覺層次
- 🎯 豐富的視覺反饋
- 🎯 無障礙設計考量

## 📚 進階主題

### 動態主題切換
```python
def toggle_theme():
    current = sv_ttk.get_theme()
    new_theme = "dark" if current == "light" else "light"
    sv_ttk.set_theme(new_theme)
```

### 系統主題偵測（需要額外套件）
```bash
pip install darkdetect
```

```python
import darkdetect
import sv_ttk

# 根據系統設定應用主題
system_theme = darkdetect.theme()  # 返回 "Light" 或 "Dark"
sv_ttk.set_theme(system_theme.lower())
```

### Windows 11 標題欄優化（需要額外套件）
```bash
pip install pywinstyles
```

```python
import pywinstyles
import sys

def apply_theme_to_titlebar(root):
    version = sys.getwindowsversion()
    
    if version.major == 10 and version.build >= 22000:
        # Windows 11
        color = "#1c1c1c" if sv_ttk.get_theme() == "dark" else "#fafafa"
        pywinstyles.change_header_color(root, color)
    elif version.major == 10:
        # Windows 10
        style = "dark" if sv_ttk.get_theme() == "dark" else "normal"
        pywinstyles.apply_style(root, style)
```

## 🤝 貢獻

如有任何問題或建議，歡迎：
1. 查看文檔（UI_THEME_README.md）
2. 檢查更新日誌（CHANGELOG_UI_THEME.md）
3. 參考比較文檔（UI_COMPARISON.md）

## 📝 授權

Sun Valley ttk theme 使用 MIT 授權。
詳見：https://github.com/rdbende/Sun-Valley-ttk-theme

## 🔗 相關連結

- [Sun Valley GitHub](https://github.com/rdbende/Sun-Valley-ttk-theme)
- [Sun Valley Wiki](https://github.com/rdbende/Sun-Valley-ttk-theme/wiki)
- [PyPI 套件](https://pypi.org/project/sv-ttk/)
- [ttk 文檔](https://docs.python.org/3/library/tkinter.ttk.html)
