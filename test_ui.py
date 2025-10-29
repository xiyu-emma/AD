#!/usr/bin/env python3
"""
简单的UI测试脚本 - 用于测试Sun Valley主题的应用
"""

import tkinter as tk
from tkinter import ttk
import sv_ttk

def test_ui():
    root = tk.Tk()
    root.title("Sun Valley 主題測試")
    root.geometry("800x600")
    
    # 应用 Sun Valley 浅色主题
    sv_ttk.set_theme("light")
    
    # 创建测试组件
    main_frame = ttk.Frame(root, padding=20)
    main_frame.pack(expand=True, fill="both")
    
    # 标题
    title = ttk.Label(main_frame, text="🎙️ Sun Valley 淺色主題測試", font=("Segoe UI", 24, "bold"))
    title.pack(pady=(0, 10))
    
    subtitle = ttk.Label(main_frame, text="測試各種 UI 元件的外觀", font=("Segoe UI", 11))
    subtitle.pack(pady=(0, 20))
    
    # 分隔线
    ttk.Separator(main_frame, orient="horizontal").pack(fill="x", pady=(0, 20))
    
    # 按钮测试
    btn_frame = ttk.Frame(main_frame)
    btn_frame.pack(fill="x", pady=10)
    
    ttk.Button(btn_frame, text="🖼️ 主要按鈕").pack(side="left", expand=True, fill="x", padx=5)
    ttk.Button(btn_frame, text="🎬 次要按鈕").pack(side="left", expand=True, fill="x", padx=5)
    ttk.Button(btn_frame, text="📸 強調按鈕").pack(side="left", expand=True, fill="x", padx=5)
    
    # LabelFrame 测试
    lf1 = ttk.LabelFrame(main_frame, text="📷 測試區域 1", padding=15)
    lf1.pack(fill="both", expand=True, pady=10, side="left", padx=(0, 5))
    
    ttk.Label(lf1, text="這是一個測試標籤").pack(pady=5)
    ttk.Entry(lf1).pack(fill="x", pady=5)
    
    lf2 = ttk.LabelFrame(main_frame, text="🎬 測試區域 2", padding=15)
    lf2.pack(fill="both", expand=True, pady=10, side="left", padx=(5, 0))
    
    ttk.Label(lf2, text="另一個測試標籤").pack(pady=5)
    ttk.Checkbutton(lf2, text="測試選項").pack(pady=5)
    
    # 状态栏
    status_frame = ttk.Frame(root, padding=(10, 5))
    status_frame.pack(side=tk.BOTTOM, fill=tk.X)
    
    status_var = tk.StringVar(value="✓ 主題已成功載入")
    ttk.Label(status_frame, textvariable=status_var).pack(side=tk.LEFT)
    
    root.mainloop()

if __name__ == "__main__":
    test_ui()
