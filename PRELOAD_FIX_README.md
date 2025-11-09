# LLaMA 模型預載入修復說明

## 問題分析

### 原始錯誤
```
[預載入] 開始預載入 LLaMA 模型和 RAG 資料庫...
[預載入] 發生錯誤: main thread is not in main loop
ImportError: DLL load failed while importing _imaging: 找不到指定的模組。
RuntimeError: main thread is not in main loop
```

### 根本原因

1. **PIL DLL 加載失敗** (`ImportError: DLL load failed while importing _imaging`)
   - Pillow 的 C++ 擴展 (`_imaging`) 無法加載
   - 可能原因：Pillow 版本不兼容、缺失系統依賴、環境配置問題

2. **Tkinter 線程安全違規** (`RuntimeError: main thread is not in main loop`)
   - `generate_image_ad.py` 在模塊導入時嘗試創建 Tkinter messagebox
   - 預載入在後台線程中執行
   - Tkinter 只能在主線程中調用 → 導致運行時錯誤

## 實施的修復方案

### 1. PIL 延遲導入 (generate_image_ad.py)

**之前：** 在模塊頂部導入 PIL
```python
from PIL import Image  # 在模塊載入時立即執行
```

**之後：** 使用延遲導入
```python
_PIL_Image = None

def get_pil_image():
    """延遲導入 PIL Image - 只在實際使用時才導入"""
    global _PIL_Image
    if _PIL_Image is None:
        try:
            from PIL import Image as PILImage
            _PIL_Image = PILImage
        except ImportError as e:
            error_msg = f"無法導入 PIL Image: {e}\n請確保 Pillow 已正確安裝..."
            print(f"[嚴重錯誤] {error_msg}", file=sys.stderr)
            raise RuntimeError(error_msg)
    return _PIL_Image
```

**優點：**
- PIL 只在實際需要時導入（不在預載入初期）
- DLL 問題延遲到實際使用圖片時
- 允許預載入即使 PIL 可能有問題

### 2. 移除 Tkinter messagebox 在非主線程的使用

**之前：** ImportError 捕獲中有 messagebox
```python
except ImportError as e:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(...)  # 在後台線程中呼叫 → 錯誤！
    sys.exit(1)
```

**之後：** 只使用 stderr 輸出
```python
except ImportError as e:
    print(f"[嚴重錯誤] 缺少必要的套件: {e}", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)
```

**優點：**
- 避免 Tkinter 線程安全問題
- 錯誤信息仍然通過 stderr 輸出
- 主線程可以通過 subprocess 的 stderr 捕獲錯誤

### 3. 改進主線程的錯誤處理 (main.py)

**之前：** 通用的 Exception 捕獲
```python
except Exception as e:
    print(f"[預載入] 發生錯誤: {e}")
    _preload_error = str(e)
```

**之後：** 分類捕獲不同的異常類型
```python
except ImportError as e:
    print(f"[預載入] 模組導入錯誤: {e}")
    _preload_error = f"導入錯誤: {e}"
    # 通過佇列安全地更新 GUI
    gui_queue.put(lambda: update_gui_safe(result_text_widget, f"[警告] {error_msg}..."))

except RuntimeError as e:
    print(f"[預載入] 運行時錯誤: {e}")
    _preload_error = f"運行時錯誤: {e}"
    
except Exception as e:
    # 其他異常
    print(f"[預載入] 發生未預期的錯誤: {e}")
```

**優點：**
- 更詳細的錯誤分類
- 便於診斷問題
- 所有 GUI 更新通過佇列進行（線程安全）

### 4. 詳細的進度日誌

**添加了中間步驟的日誌：**
```python
print("[預載入] 正在導入 generate_image_ad 模組...")
print("[預載入] 正在調用 preload_resources 函式...")
```

**優點：**
- 易於追蹤預載入進度
- 快速定位問題發生位置

## Pillow DLL 問題的診斷和解決

如果依然遇到 PIL DLL 加載失敗，請嘗試以下解決方案：

### 方案 1: 重新安裝 Pillow
```bash
pip uninstall Pillow
pip install --upgrade Pillow
```

### 方案 2: 使用特定版本
```bash
pip install Pillow==10.0.0
```

### 方案 3: 檢查系統依賴（Windows）
```bash
# 確保已安裝 Visual C++ Redistributable
# 可從以下網址下載：
# https://support.microsoft.com/en-us/help/2977003/
```

### 方案 4: 使用 Conda（如果使用 Conda 環境）
```bash
conda install -c conda-forge pillow
```

### 方案 5: 檢查環境變量（Windows）
```bash
# 檢查 PYTHONPATH 是否包含正確的路徑
set PYTHONPATH
```

## 測試預載入流程

### 直接測試預載入
```bash
python generate_image_ad.py --model_path ./models/Llama-3.2-11B-Vision-Instruct --preload
```

### 測試完整流程
```bash
python main.py
# 應用啟動時會自動嘗試預載入模型
```

## 備註

- 預載入失敗不會阻止應用運行，只是無法使用快速模式
- 若預載入成功，後續圖像生成會更快
- 所有詳細的錯誤信息都會輸出到控制台
- 如果使用後台執行，查看 stdout 和 stderr 輸出進行診斷

## 相關檔案修改

1. **generate_image_ad.py**
   - 移除模塊頂部的 PIL 導入
   - 實現 `get_pil_image()` 延遲導入函數
   - 所有使用 PIL Image 的地方調用 `get_pil_image()`

2. **main.py**
   - 增強 `preload_llama_and_db()` 的錯誤處理
   - 分類捕獲不同的異常
   - 添加中間步驟的日誌記錄

3. **requirements.txt**
   - 無改變（Pillow 依然在列表中）
   - 建議 Pillow>=10.0.0
