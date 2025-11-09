# main.py 

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, simpledialog, messagebox
import subprocess
import sys
import os
import threading
import time
import traceback
import uuid # 新增
import queue
import sv_ttk  # Sun Valley 主題

# --- 語音功能 ---
try:
    from voice_interface import speak, voice_input, VoiceCommands, audio
    VOICE_ENABLED = True
except ImportError:
    print("[警告] voice_interface.py 未找到或導入失敗，語音功能將被禁用。")
    VOICE_ENABLED = False
    def speak(text, **kwargs): print(f"[語音模擬]: {text}")
    def voice_input(prompt, **kwargs): print(f"[語音模擬] 提示: {prompt}"); return None
    class DummyAudio:
        def beep_error(self): pass
        def beep_success(self): pass
    audio = DummyAudio()
    class DummyVoiceCommands:
        def parse(self, text): return text
    VoiceCommands = DummyVoiceCommands()
# --- 語音功能結束 ---

# --- 客製化語音功能 ---
try:
    from custom_voice import custom_voice_system
    CUSTOM_VOICE_ENABLED = True
except ImportError:
    print("[警告] custom_voice.py 未找到，客製化語音功能將被禁用。")
    CUSTOM_VOICE_ENABLED = False
    custom_voice_system = None
# --- 客製化語音功能結束 ---

# --- 全域變數 ---
result_text_widget = None
status_label_var = None
app_window = None
image_button = None
video_button = None
live_button = None # 新增
custom_voice_button = None # 新增：客製化語音按鈕
image_preview_label = None
narration_output_widget = None
video_preview_label = None
progress_bar = None
status_bar = None
gui_queue = queue.Queue() # 新增：用於執行緒安全 GUI 更新的佇列

# 暫存資訊
_last_selected_image_path = None
_current_image_tk = None
_video_cap = None
_video_after_job = None
_current_video_path = None

# --- 新增：即時攝影機全域變數 ---
_live_cam_window = None
_live_cam_label = None
_live_cam_cap = None
_live_cam_countdown_job = None
_live_cam_frame_job = None
_live_cam_tk_img = None # 確保影像被引用

# --- 新增：執行緒同步旗標 ---
_is_task_running = threading.Event()
_is_task_running.set() # 初始狀態為 "不在執行任務"


# --- 新增：模型預載入狀態 ---
_preloading_in_progress = False
_preload_completed = False
_preload_error = None
LLAMA_MODEL_DIR = os.path.join(".", "models", "Llama-3.2-11B-Vision-Instruct")

# --- GUI 輔助函式 ---

def update_gui_safe(widget, text):
    """安全地從背景執行緒更新 ScrolledText 元件"""
    if widget and app_window and app_window.winfo_exists() and widget.winfo_exists():
        try:
            widget.config(state=tk.NORMAL)
            widget.insert(tk.END, text + "\n")
            widget.see(tk.END) 
            widget.config(state=tk.DISABLED)
        except tk.TclError as e:
            print(f"更新 GUI 時發生 TclError (可能視窗已關閉): {e}")
        except Exception as e:
            print(f"更新 GUI 時發生未知錯誤: {e}")

def update_status_safe(text):
    """安全地更新狀態列文字"""
    if status_label_var and app_window and app_window.winfo_exists():
        try:
            status_label_var.set(text)
        except tk.TclError as e:
            print(f"更新狀態列時發生 TclError (可能視窗已關閉): {e}")
        except Exception as e:
            print(f"更新狀態列時發生未知錯誤: {e}")

# 簡易工具提示類別
class ToolTip:
    # (Tooltip 類別程式碼已加入 winfo_exists 檢查)
    def __init__(self, widget, text: str, delay: int = 500):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tipwindow = None
        self._id = None
        widget.bind("<Enter>", self._enter)
        widget.bind("<Leave>", self._leave)
        widget.bind("<ButtonPress>", self._leave)

    def _enter(self, event=None): self._schedule()
    def _leave(self, event=None): self._unschedule(); self._hidetip()

    def _schedule(self):
        self._unschedule()
        if self.widget.winfo_exists():
            self._id = self.widget.after(self.delay, self._showtip)

    def _unschedule(self):
        if self._id:
            try:
                if self.widget.winfo_exists():
                    self.widget.after_cancel(self._id)
            except tk.TclError: pass
            self._id = None

    def _showtip(self, event=None):
        if self.tipwindow or not self.text or not self.widget.winfo_exists():
            return
        try: bbox = self.widget.bbox("insert") if hasattr(self.widget, "bbox") else None
        except Exception: bbox = None
        x, y = (0, 0) if not bbox else (bbox[0], bbox[1] + bbox[3])
        x += self.widget.winfo_rootx() + 20
        y += self.widget.winfo_rooty() + 20

        try:
             self.tipwindow = tw = tk.Toplevel(self.widget)
             try: tw.wm_overrideredirect(1)
             except Exception: pass
             tw.configure(bg="#638FA8")
             label = tk.Label(tw, text=self.text, justify=tk.LEFT, background="#638FA8",
                              foreground="white", relief=tk.SOLID, borderwidth=1,
                              font=("Segoe UI", 9), padx=8, pady=5)
             label.pack()
             if self.widget.winfo_exists():
                 tw.wm_geometry(f"+{x}+{y}")
        except Exception as e:
            print(f"ToolTip _showtip error: {e}")
            self._hidetip() 

    def _hidetip(self):
        tw = self.tipwindow
        self.tipwindow = None
        if tw:
            try:
                if tw.winfo_exists():
                    tw.destroy()
            except Exception: pass

# --- 顯示圖片和文字 ---
def show_image_and_text(image_path: str, narration_text: str):
    """在 GUI 中顯示圖片預覽和生成的口述影像文字"""
    global _current_image_tk
    if not app_window or not app_window.winfo_exists(): return

    try:
        from PIL import Image, ImageTk
    except ImportError:
        update_gui_safe(result_text_widget, "[警告] 需要 Pillow 函式庫來顯示圖片預覽 (pip install Pillow)")
        if narration_output_widget and narration_output_widget.winfo_exists(): 
             try:
                 narration_output_widget.config(state=tk.NORMAL)
                 narration_output_widget.delete('1.0', tk.END)
                 narration_output_widget.insert(tk.END, narration_text.strip() + "\n")
                 narration_output_widget.config(state=tk.DISABLED)
             except tk.TclError: pass
        return

    if not image_preview_label or not image_preview_label.winfo_exists() or \
       not narration_output_widget or not narration_output_widget.winfo_exists():
        return

    # 顯示圖片
    try:
        img = Image.open(image_path)
        max_w, max_h = 640, 360
        img.thumbnail((max_w, max_h), Image.LANCZOS)
        _current_image_tk = ImageTk.PhotoImage(img)
        image_preview_label.config(image=_current_image_tk)
        image_preview_label.image = _current_image_tk
    except Exception as e:
        update_gui_safe(result_text_widget, f"[警告] 顯示圖片預覽失敗: {e}")
        try:
             image_preview_label.config(image='')
             image_preview_label.image = None
        except tk.TclError: pass

    # 顯示文字
    try:
        narration_output_widget.config(state=tk.NORMAL)
        narration_output_widget.delete('1.0', tk.END)
        narration_output_widget.insert(tk.END, narration_text.strip() + "\n")
        narration_output_widget.config(state=tk.DISABLED)
    except tk.TclError: pass

# --- 影片播放相關函式 ---
def stop_video_playback():
    """停止 UI 中的影片預覽"""
    global _video_cap, _video_after_job
    if _video_after_job and app_window and app_window.winfo_exists():
        try: app_window.after_cancel(_video_after_job)
        except tk.TclError: pass
        _video_after_job = None
    if _video_cap is not None:
        try: _video_cap.release()
        except Exception: pass
        _video_cap = None
    if video_preview_label and video_preview_label.winfo_exists():
        try:
             video_preview_label.config(image='')
             video_preview_label.image = None
        except tk.TclError: pass

def _update_video_frame():
    """讀取並顯示下一幀影片"""
    global _video_cap, _video_after_job
    if not app_window or not app_window.winfo_exists(): return

    try:
        import cv2
        from PIL import Image, ImageTk
    except ImportError:
        update_gui_safe(result_text_widget, "[警告] 需要 opencv-python 和 Pillow 才能預覽影片")
        stop_video_playback()
        return

    if _video_cap is None or not video_preview_label or not video_preview_label.winfo_exists():
         return

    ret, frame = _video_cap.read()
    if not ret:
        stop_video_playback()
        return

    try:
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame_rgb)
        max_w, max_h = 640, 360
        img.thumbnail((max_w, max_h), Image.LANCZOS)
        tk_img = ImageTk.PhotoImage(img)
        video_preview_label.config(image=tk_img)
        video_preview_label.image = tk_img

        fps = _video_cap.get(cv2.CAP_PROP_FPS) or 24.0
        delay = int(1000 / max(1.0, fps))
        if app_window and app_window.winfo_exists():
            _video_after_job = app_window.after(delay, _update_video_frame)
    except tk.TclError: 
        stop_video_playback()
    except Exception as e:
        print(f"更新影片幀時出錯: {e}")
        stop_video_playback()

def play_video_in_ui(video_path: str):
    """開始在 UI 中預覽影片"""
    global _video_cap, _current_video_path
    stop_video_playback()
    _current_video_path = video_path
    try: import cv2
    except ImportError:
        update_gui_safe(result_text_widget, "[警告] 需要 opencv-python 才能預覽影片")
        return

    _video_cap = cv2.VideoCapture(video_path)
    if not _video_cap or not _video_cap.isOpened():
        update_gui_safe(result_text_widget, f"[警告] 無法開啟影片檔案進行預覽：{video_path}")
        return

    print(f"開始預覽影片: {video_path}")
    _update_video_frame()

def open_video_external():
    """使用系統預設播放器開啟影片"""
    if not _current_video_path or not os.path.exists(_current_video_path):
        messagebox.showwarning("無法開啟", "沒有可開啟的影片檔案。請先生成影片。")
        return
    path = os.path.normpath(_current_video_path)
    try:
        print(f"嘗試開啟外部影片: {path}")
        if sys.platform.startswith('win'): os.startfile(path)
        elif sys.platform == 'darwin': subprocess.Popen(['open', path])
        else: subprocess.Popen(['xdg-open', path])
    except Exception as e:
        update_gui_safe(result_text_widget, f"[警告] 開啟外部播放器失敗：{e}")
        messagebox.showerror("開啟失敗", f"無法使用系統播放器開啟影片:\n{e}")

# --- 執行緒函式 ---
def run_script_in_thread(script_name: str, script_type: str, args: list):
    """在背景執行緒中執行腳本並將輸出傳回 GUI (已加入 winfo_exists 檢查)"""
    global _last_selected_image_path
    if app_window and app_window.winfo_exists():
        app_window.after(0, update_status_safe, f"正在執行 {script_type} 程序...")
        app_window.after(0, update_gui_safe, result_text_widget, f"\n--- 開始執行 {script_name} ---")
    if VOICE_ENABLED: speak(f"正在啟動，{script_type}口述影像生成程序")

    final_answer = f"[{script_type} 未返回明確答案]"
    final_video_path = None
    final_image_path = None
    capture_next_video_path = False

    process = None
    try:
        script_path = os.path.join(os.path.dirname(__file__), script_name)
        command = [sys.executable, script_path] + args
        print(f"執行指令: {' '.join(command)}")

        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', errors='replace', bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )

        if process.stdout:
            for line in iter(process.stdout.readline, ''):
                print(line, end='')
                if app_window and app_window.winfo_exists():
                    app_window.after(0, update_gui_safe, result_text_widget, line.strip())
                s_line = line.strip()
                if s_line.startswith("FINAL_ANSWER:"): final_answer = s_line.replace("FINAL_ANSWER:", "").strip()
                elif s_line.startswith("FINAL_VIDEO:"): final_video_path = s_line.replace("FINAL_VIDEO:", "").strip()
                elif s_line.startswith("FINAL_IMAGE:"): final_image_path = s_line.replace("FINAL_IMAGE:", "").strip()
                elif "最終影片已儲存為：" in s_line: capture_next_video_path = True
                elif capture_next_video_path and s_line: final_video_path = s_line; capture_next_video_path = False
            process.stdout.close()

        stderr_output = ""
        if process.stderr:
            stderr_output = process.stderr.read()
            process.stderr.close()

        return_code = process.wait()

        if return_code == 0:
            success_msg = f"--- {script_name} 執行成功 ---"
            print(success_msg)
            if app_window and app_window.winfo_exists():
                app_window.after(0, update_gui_safe, result_text_widget, success_msg)
                app_window.after(0, update_status_safe, f"{script_type} 完成")
            if VOICE_ENABLED: speak(f"{script_type} 處理完成")

            if script_name == 'generate_video_ad.py':
                if final_video_path and os.path.exists(final_video_path):
                    if app_window and app_window.winfo_exists():
                        app_window.after(0, play_video_in_ui, final_video_path)
                        app_window.after(0, update_gui_safe, result_text_widget, f"[提示] 影片已生成: {final_video_path}")
                else:
                    if app_window and app_window.winfo_exists():
                        app_window.after(0, update_gui_safe, result_text_widget, "[警告] 未找到生成的影片檔案路徑或檔案不存在。")

        else:
            error_msg_header = f"\n!!!!!!!!!! {script_name} 執行時發生嚴重錯誤 !!!!!!!!!!\n返回碼: {return_code}"
            error_details = stderr_output if stderr_output else "[無詳細錯誤輸出]"
            error_msg_stderr = f"\n--- 錯誤輸出 (stderr) ---\n{error_details}\n-------------------------"
            full_error_msg = error_msg_header + error_msg_stderr
            print(full_error_msg)
            if app_window and app_window.winfo_exists():
                app_window.after(0, update_gui_safe, result_text_widget, full_error_msg)
                app_window.after(0, update_status_safe, f"{script_type} 執行失敗")
            if VOICE_ENABLED: speak(f"啟動 {script_type} 處理程序時發生錯誤"); audio.beep_error()

    except FileNotFoundError:
        error_msg = f"錯誤：找不到腳本檔案 '{script_name}' 或 Python 執行檔 '{sys.executable}'"
        print(error_msg)
        if app_window and app_window.winfo_exists():
             app_window.after(0, update_gui_safe, result_text_widget, error_msg)
             app_window.after(0, update_status_safe, f"{script_type} 失敗 (找不到檔案)")
        if VOICE_ENABLED: speak(f"啟動{script_type}失敗，找不到檔案"); audio.beep_error()
    except Exception as e:
        error_msg = f"執行 {script_name} 時發生未預期的錯誤: {e}\n{traceback.format_exc()}"
        print(error_msg)
        if app_window and app_window.winfo_exists():
             app_window.after(0, update_gui_safe, result_text_widget, error_msg)
             app_window.after(0, update_status_safe, f"{script_type} 失敗 (未知錯誤)")
        if VOICE_ENABLED: speak(f"啟動{script_type}時發生未知錯誤"); audio.beep_error()
    finally:
        if process and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=1)
            except Exception as e:
                print(f"嘗試終止子程序時出錯: {e}")
            finally:
                 if process.poll() is None:
                     process.kill()

        if app_window and app_window.winfo_exists():
            app_window.after(100, enable_buttons)
            app_window.after(0, set_busy, False)
            # (新增) 任務結束後，重新啟動語音互動
            if VOICE_ENABLED:
                app_window.after(200, start_voice_interaction_thread)

# --- 客製化語音功能函式 ---
def open_custom_voice_dialog():
    """開啟客製化語音設定對話框"""
    if not CUSTOM_VOICE_ENABLED:
        messagebox.showerror("功能未啟用", "客製化語音功能未啟用，請檢查 custom_voice.py 檔案")
        return
    
    dialog = CustomVoiceDialog(app_window)
    dialog.wait_window()

class CustomVoiceDialog:
    """客製化語音設定對話框"""
    def __init__(self, parent):
        self.parent = parent
        self.current_profile = None
        self.recording = False
        self.current_recording_path = None
        self.profile_name = None
        
        self.window = tk.Toplevel(parent)
        self.window.title("🎙️ 客製化語音設定")
        self.window.geometry("600x500")
        self.window.configure(bg="#F2D9BB")
        self.window.transient(parent)
        self.window.grab_set()
        
        # 設定視窗樣式
        style = ttk.Style()
        style.configure("Dialog.TFrame", background="#F2D9BB")
        style.configure("Dialog.TLabel", background="#F2D9BB", foreground="#2C3E50")
        style.configure("Dialog.TButton", font=("Segoe UI", 10))
        
        self.create_widgets()
        self.refresh_profiles()
        
    def create_widgets(self):
        """創建對話框元件"""
        # 標題
        title_label = tk.Label(self.window, text="🎙️ 客製化語音設定", 
                              font=("Segoe UI", 16, "bold"), 
                              fg="#376C8B", bg="#F2D9BB")
        title_label.pack(pady=20)
        
        # 說明文字
        desc_label = tk.Label(self.window, 
                            text="錄製您的聲音來替換系統的預設語音提示\n您需要錄製5個基本語音樣本",
                            font=("Segoe UI", 10), 
                            fg="#638FA8", bg="#F2D9BB")
        desc_label.pack(pady=(0, 20))
        
        # 主要框架
        main_frame = ttk.Frame(self.window, style="Dialog.TFrame")
        main_frame.pack(expand=True, fill="both", padx=20, pady=10)
        
        # 左側：語音設定檔管理
        left_frame = ttk.Frame(main_frame, style="Dialog.TFrame")
        left_frame.pack(side="left", expand=True, fill="both", padx=(0, 10))
        
        profile_label = ttk.Label(left_frame, text="語音設定檔", style="Dialog.TLabel")
        profile_label.pack(anchor="w", pady=(0, 5))
        
        # 設定檔列表
        self.profile_listbox = tk.Listbox(left_frame, height=6, font=("Segoe UI", 10))
        self.profile_listbox.pack(fill="both", expand=True, pady=(0, 10))
        self.profile_listbox.bind('<<ListboxSelect>>', self.on_profile_select)
        
        # 設定檔按鈕
        profile_btn_frame = ttk.Frame(left_frame, style="Dialog.TFrame")
        profile_btn_frame.pack(fill="x")
        
        ttk.Button(profile_btn_frame, text="新增設定檔", 
                  command=self.create_new_profile).pack(side="left", padx=(0, 5))
        ttk.Button(profile_btn_frame, text="刪除設定檔", 
                  command=self.delete_profile).pack(side="left")
        ttk.Button(profile_btn_frame, text="設為預設", 
                  command=self.set_as_default).pack(side="left", padx=(5, 0))
        
        # 右側：錄音控制
        right_frame = ttk.Frame(main_frame, style="Dialog.TFrame")
        right_frame.pack(side="right", expand=True, fill="both", padx=(10, 0))
        
        recording_label = ttk.Label(right_frame, text="語音樣本錄製", style="Dialog.TLabel")
        recording_label.pack(anchor="w", pady=(0, 5))
        
        # 錄音項目列表
        self.recording_items = [
            ("歡迎語音", "hello", "請說：歡迎使用口述影像生成系統"),
            ("系統就緒", "system_ready", "請說：系統準備就緒"),
            ("處理中", "processing", "請說：正在處理中"),
            ("完成提示", "completed", "請說：處理完成"),
            ("錯誤提示", "error", "請說：發生錯誤")
        ]
        
        # 錄音項目框架
        self.recording_frame = ttk.Frame(right_frame, style="Dialog.TFrame")
        self.recording_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        self.recording_buttons = []
        self.recording_status = []
        
        for i, (name, key, prompt) in enumerate(self.recording_items):
            item_frame = ttk.Frame(self.recording_frame, style="Dialog.TFrame")
            item_frame.pack(fill="x", pady=2)
            
            # 項目名稱
            name_label = ttk.Label(item_frame, text=name, width=12, style="Dialog.TLabel")
            name_label.pack(side="left")
            
            # 錄音按鈕
            btn = ttk.Button(item_frame, text="🎤 錄音", width=12,
                           command=lambda k=key, p=prompt: self.toggle_recording(k, p))
            btn.pack(side="left", padx=(10, 5))
            self.recording_buttons.append(btn)
            
            # 狀態標籤
            status_label = ttk.Label(item_frame, text="未錄製", width=8, 
                                   style="Dialog.TLabel", foreground="#999")
            status_label.pack(side="left")
            self.recording_status.append(status_label)
        
        # 錄音說明
        info_label = ttk.Label(right_frame, 
                             text="選擇一個設定檔後，點擊錄音按鈕開始錄製\n錄製時請清晰說出提示文字",
                             font=("Segoe UI", 9), 
                             fg="#638FA8", bg="#F2D9BB")
        info_label.pack(pady=(10, 0))
        
        # 底部按鈕
        bottom_frame = ttk.Frame(self.window, style="Dialog.TFrame")
        bottom_frame.pack(fill="x", padx=20, pady=(10, 20))
        
        ttk.Button(bottom_frame, text="關閉", 
                  command=self.window.destroy).pack(side="right")
        
        # 目前狀態
        self.status_label = ttk.Label(bottom_frame, text="請選擇或創建語音設定檔", 
                                     style="Dialog.TLabel")
        self.status_label.pack(side="left")
    
    def refresh_profiles(self):
        """刷新語音設定檔列表"""
        if not CUSTOM_VOICE_ENABLED:
            return
            
        self.profile_listbox.delete(0, tk.END)
        profiles = custom_voice_system.get_voice_profiles()
        
        for profile in profiles:
            self.profile_listbox.insert(tk.END, profile)
        
        # 如果有目前使用的設定檔，選中它
        if custom_voice_system.current_voice_profile:
            for i, profile in enumerate(profiles):
                if profile == custom_voice_system.current_voice_profile:
                    self.profile_listbox.selection_clear(0, tk.END)
                    self.profile_listbox.selection_set(i)
                    self.current_profile = profile
                    self.update_recording_status()
                    break
    
    def on_profile_select(self, event):
        """處理設定檔選擇事件"""
        selection = self.profile_listbox.curselection()
        if selection:
            self.current_profile = self.profile_listbox.get(selection[0])
            self.update_recording_status()
            self.status_label.config(text=f"已選擇設定檔：{self.current_profile}")
    
    def create_new_profile(self):
        """創建新的語音設定檔"""
        profile_name = simpledialog.askstring("新增設定檔", 
                                            "請輸入設定檔名稱：",
                                            parent=self.window)
        if profile_name and profile_name.strip():
            if custom_voice_system.create_voice_profile(profile_name.strip()):
                self.refresh_profiles()
                self.status_label.config(text=f"已創建設定檔：{profile_name.strip()}")
            else:
                messagebox.showerror("錯誤", "創建設定檔失敗")
    
    def delete_profile(self):
        """刪除選中的語音設定檔"""
        if not self.current_profile:
            messagebox.showwarning("警告", "請先選擇要刪除的設定檔")
            return
        
        if messagebox.askyesno("確認刪除", 
                             f"確定要刪除設定檔 '{self.current_profile}' 嗎？\n這將刪除所有相關的錄音檔案。",
                             parent=self.window):
            if custom_voice_system.delete_voice_profile(self.current_profile):
                self.current_profile = None
                self.refresh_profiles()
                self.status_label.config(text="設定檔已刪除")
            else:
                messagebox.showerror("錯誤", "刪除設定檔失敗")
    
    def set_as_default(self):
        """將選中的設定檔設為預設"""
        if not self.current_profile:
            messagebox.showwarning("警告", "請先選擇要設為預設的設定檔")
            return
        
        if custom_voice_system.set_active_voice_profile(self.current_profile):
            self.status_label.config(text=f"已將 '{self.current_profile}' 設為預設語音")
            if VOICE_ENABLED:
                speak("已設定客製化語音", wait=False)
        else:
            messagebox.showerror("錯誤", "設定預設語音失敗")
    
    def toggle_recording(self, sample_type: str, prompt: str):
        """切換錄音狀態"""
        if not self.current_profile:
            messagebox.showwarning("警告", "請先選擇一個語音設定檔")
            return
        
        if not self.recording:
            # 開始錄音
            self.recording = True
            self.current_sample_type = sample_type
            
            # 更新按鈕狀態
            for i, (name, key, p) in enumerate(self.recording_items):
                if key == sample_type:
                    self.recording_buttons[i].config(text="⏹️ 停止")
                    break
            
            self.status_label.config(text=f"錄音中：{prompt}")
            
            # 顯示錄音提示
            messagebox.showinfo("開始錄音", f"準備開始錄音\n\n請說：{prompt}\n\n點擊確定後開始錄音", 
                              parent=self.window)
            
            # 開始錄音
            if custom_voice_system.start_recording(callback=self.on_recording_complete):
                print(f"開始錄音：{sample_type}")
            else:
                self.recording = False
                messagebox.showerror("錯誤", "無法開始錄音，請檢查麥克風設備")
                self.reset_recording_button()
        else:
            # 停止錄音
            self.recording = False
            self.status_label.config(text="正在保存錄音...")
            
            # 停止錄音並獲取檔案路徑
            audio_path = custom_voice_system.stop_recording()
            
            if audio_path:
                self.current_recording_path = audio_path
                # 錄音完成的回調會處理保存
            else:
                messagebox.showerror("錯誤", "錄音失敗")
                self.reset_recording_button()
                self.status_label.config(text="錄音失敗")
    
    def on_recording_complete(self):
        """錄音完成回調"""
        if hasattr(self, 'current_recording_path') and self.current_recording_path:
            # 保存語音樣本
            if custom_voice_system.save_voice_sample(
                self.current_profile, 
                self.current_sample_type, 
                self.current_recording_path
            ):
                self.status_label.config(text="錄音保存成功")
                self.update_recording_status()
            else:
                messagebox.showerror("錯誤", "保存錄音失敗")
            
            self.current_recording_path = None
        
        self.reset_recording_button()
    
    def reset_recording_button(self):
        """重置錄音按鈕狀態"""
        for i, (name, key, prompt) in enumerate(self.recording_items):
            self.recording_buttons[i].config(text="🎤 錄音")
    
    def update_recording_status(self):
        """更新錄音狀態顯示"""
        if not self.current_profile:
            for status_label in self.recording_status:
                status_label.config(text="未錄製", foreground="#999")
            return
        
        profile_path = os.path.join(custom_voice_system.voice_profiles_dir, self.current_profile)
        
        for i, (name, key, prompt) in enumerate(self.recording_items):
            filename = f"{key}.wav"
            filepath = os.path.join(profile_path, filename)
            
            if os.path.exists(filepath):
                self.recording_status[i].config(text="✓ 已錄製", foreground="#4CAF50")
            else:
                self.recording_status[i].config(text="未錄製", foreground="#999")

def enable_buttons():
    """重新啟用主按鈕 (加入檢查)"""
    try:
        # 檢查元件是否存在
        if image_button and image_button.winfo_exists(): image_button.config(state=tk.NORMAL)
        if video_button and video_button.winfo_exists(): video_button.config(state=tk.NORMAL)
        if live_button and live_button.winfo_exists(): live_button.config(state=tk.NORMAL) # 新增
        if custom_voice_button and custom_voice_button.winfo_exists(): custom_voice_button.config(state=tk.NORMAL) # 新增
    except tk.TclError:
        pass # 視窗可能已關閉

def set_busy(is_busy: bool):
    """設定 GUI 為忙碌或空閒狀態 (加入檢查)"""
    global app_window, progress_bar, status_bar, _is_task_running
    if not app_window or not app_window.winfo_exists() or progress_bar is None: return

    try:
        if is_busy:
            _is_task_running.clear() # 【修改】設定旗標為 "正在執行任務"
            # 禁用所有按鈕
            if image_button and image_button.winfo_exists(): image_button.config(state=tk.DISABLED)
            if video_button and video_button.winfo_exists(): video_button.config(state=tk.DISABLED)
            if live_button and live_button.winfo_exists(): live_button.config(state=tk.DISABLED) # 新增
            if custom_voice_button and custom_voice_button.winfo_exists(): custom_voice_button.config(state=tk.DISABLED) # 新增
            
            if status_bar and status_bar.winfo_exists():
                progress_bar.pack(side=tk.BOTTOM, fill=tk.X, before=status_bar)
            else:
                 progress_bar.pack(side=tk.BOTTOM, fill=tk.X)
            try: progress_bar.start(10)
            except tk.TclError: pass
            app_window.config(cursor='watch')
        else:
            _is_task_running.set() # 【修改】設定旗標為 "任務已結束"
            # 啟用按鈕 (由 enable_buttons 函式處理)
            try: progress_bar.stop()
            except tk.TclError: pass
            progress_bar.pack_forget()
            app_window.config(cursor='')
            # enable_buttons() 會由 run_script_in_thread 的 finally 呼叫
    except tk.TclError:
        pass

# --- 啟動流程 ---
def run_image_generation_in_thread(image_path: str, description: str):
    """(新) 在背景執行緒中直接呼叫圖像生成函式"""
    script_type = "圖像"
    try:
        if app_window and app_window.winfo_exists():
            app_window.after(0, update_status_safe, f"正在執行 {script_type} 程序...")
            app_window.after(0, update_gui_safe, result_text_widget, f"\n--- 開始執行圖像口述影像生成 ---")
        # 語音提示已在 voice_interaction_loop 中完成，此處不再重複

        # 直接匯入並呼叫函式
        import generate_image_ad
        final_answer, final_image_path = generate_image_ad.generate_narration_from_preloaded(
            image_file=image_path,
            user_desc=description
        )

        # --- 成功處理 ---
        success_msg = "--- 圖像口述影像生成成功 ---"
        print(success_msg)
        if app_window and app_window.winfo_exists():
            app_window.after(0, update_gui_safe, result_text_widget, success_msg)
            app_window.after(0, update_status_safe, f"{script_type} 完成")
        if VOICE_ENABLED: speak(f"{script_type} 處理完成", wait=True) # 等待說完

        if final_image_path and final_answer:
            if app_window and app_window.winfo_exists():
                app_window.after(0, show_image_and_text, final_image_path, final_answer)
        else:
            if app_window and app_window.winfo_exists():
                app_window.after(0, update_gui_safe, result_text_widget, "[提示] 未找到圖片路徑或生成結果用於顯示。")

    except Exception as e:
        # --- 錯誤處理 ---
        error_msg = f"執行圖像生成時發生未預期的錯誤: {e}\n{traceback.format_exc()}"
        print(error_msg)
        if app_window and app_window.winfo_exists():
            app_window.after(0, update_gui_safe, result_text_widget, error_msg)
            app_window.after(0, update_status_safe, f"{script_type} 失敗 (未知錯誤)")
        if VOICE_ENABLED: speak(f"啟動{script_type}時發生未知錯誤", wait=True); audio.beep_error()
    finally:
        # --- 清理 ---
        if app_window and app_window.winfo_exists():
            app_window.after(100, enable_buttons)
            app_window.after(0, set_busy, False)
            # (修改) 任務結束後，重新啟動語音互動
            if VOICE_ENABLED:
                app_window.after(200, start_voice_interaction_thread)


def start_image_analysis(is_voice_command: bool = False):
    global _last_selected_image_path
    
    # --- 檢查模型是否已預載入 ---
    if not _preload_completed:
        msg = "模型仍在預載入中，請稍候..." if _preloading_in_progress else "模型預載入失敗，無法執行圖像分析。"
        if is_voice_command:
            speak(msg)
        else:
            messagebox.showinfo("請稍候", msg, parent=app_window)
        if _preload_error:
             update_gui_safe(result_text_widget, f"[錯誤] {_preload_error}")
        return

    if is_voice_command:
        speak("請手動選擇圖片檔案，並輸入描述。")

    file_path = filedialog.askopenfilename(title="請選擇一張圖片", filetypes=[("Image Files", "*.png *.jpg *.jpeg *.webp *.bmp")])
    if not file_path:
        if is_voice_command: speak("操作已取消")
        return

    desc = simpledialog.askstring("圖片描述", "請輸入這張圖片的描述或重點：", parent=app_window)
    if desc is None:
        if is_voice_command: speak("操作已取消")
        return
    if not desc.strip():
        messagebox.showwarning("輸入錯誤", "圖片描述不能為空。", parent=app_window)
        return

    _last_selected_image_path = file_path

    # 清理舊輸出
    if result_text_widget and result_text_widget.winfo_exists():
        try: result_text_widget.config(state=tk.NORMAL); result_text_widget.delete('1.0', tk.END); result_text_widget.config(state=tk.DISABLED)
        except tk.TclError: pass
    if narration_output_widget and narration_output_widget.winfo_exists():
        try: narration_output_widget.config(state=tk.NORMAL); narration_output_widget.delete('1.0', tk.END); narration_output_widget.config(state=tk.DISABLED)
        except tk.TclError: pass
    if image_preview_label and image_preview_label.winfo_exists():
        try: image_preview_label.config(image=''); image_preview_label.image = None
        except tk.TclError: pass
    stop_video_playback()

    set_busy(True)

    # 使用新的執行緒函式
    thread = threading.Thread(target=run_image_generation_in_thread, args=(file_path, desc), daemon=True)
    thread.start()

def start_video_analysis():
    file_path = filedialog.askopenfilename(
        title="請選擇一個影片", 
        filetypes=[("Video Files", "*.mp4 *.avi *.mov *.mkv")]
    )
    if not file_path: return

    desc = simpledialog.askstring("影片摘要", "請輸入這段影片的摘要或重點：", parent=app_window)
    if desc is None: return
    if not desc.strip():
        messagebox.showwarning("輸入錯誤", "影片摘要不能為空。", parent=app_window)
        return
        
    if result_text_widget and result_text_widget.winfo_exists():
        try: result_text_widget.config(state=tk.NORMAL); result_text_widget.delete('1.0', tk.END); result_text_widget.config(state=tk.DISABLED)
        except tk.TclError: pass
    if narration_output_widget and narration_output_widget.winfo_exists():
        try: narration_output_widget.config(state=tk.NORMAL); narration_output_widget.delete('1.0', tk.END); narration_output_widget.config(state=tk.DISABLED)
        except tk.TclError: pass
    if image_preview_label and image_preview_label.winfo_exists():
        try: image_preview_label.config(image=''); image_preview_label.image = None
        except tk.TclError: pass
    stop_video_playback()

    # 禁用按鈕並設定忙碌
    # try:
    #     if image_button and image_button.winfo_exists(): image_button.config(state=tk.DISABLED)
    #     if video_button and video_button.winfo_exists(): video_button.config(state=tk.DISABLED)
    #     if live_button and live_button.winfo_exists(): live_button.config(state=tk.DISABLED) # 新增
    # except tk.TclError: pass
    set_busy(True) # set_busy 會處理按鈕禁用

    args = ["--video_file", file_path, "--summary", desc]
    
    thread = threading.Thread(target=run_script_in_thread, args=('generate_video_ad.py', '影片', args), daemon=True)
    thread.start()

# --- 新增：即時攝影機相關函式 ---

def stop_live_capture():
    """(新增) 停止即時攝影機畫面並清理資源"""
    global _live_cam_cap, _live_cam_window, _live_cam_countdown_job, _live_cam_frame_job
    
    if _live_cam_countdown_job:
        try: app_window.after_cancel(_live_cam_countdown_job)
        except tk.TclError: pass
        _live_cam_countdown_job = None
        
    if _live_cam_frame_job:
        try: app_window.after_cancel(_live_cam_frame_job)
        except tk.TclError: pass
        _live_cam_frame_job = None

    if _live_cam_cap:
        try: _live_cam_cap.release()
        except Exception: pass
        _live_cam_cap = None
        
    if _live_cam_window:
        try: 
            if _live_cam_window.winfo_exists():
                _live_cam_window.destroy()
        except tk.TclError: pass
        _live_cam_window = None

def _update_live_frame():
    """(新增) 抓取並顯示即時攝影機畫面"""
    global _live_cam_frame_job, _live_cam_cap, _live_cam_label, _live_cam_tk_img
    
    if _live_cam_cap is None or not _live_cam_cap.isOpened():
        return # 攝影機已被釋放

    try:
        import cv2
        from PIL import Image, ImageTk
    except ImportError:
        stop_live_capture()
        messagebox.showerror("缺少套件", "需要 OpenCV 和 Pillow 來使用攝影機功能。")
        enable_buttons()
        return

    ret, frame = _live_cam_cap.read()
    if ret:
        try:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb)
            img.thumbnail((640, 480), Image.LANCZOS)
            _live_cam_tk_img = ImageTk.PhotoImage(img)
            
            if _live_cam_label and _live_cam_label.winfo_exists():
                _live_cam_label.config(image=_live_cam_tk_img)
                _live_cam_label.image = _live_cam_tk_img
            
            # 安排下一幀
            _live_cam_frame_job = app_window.after(30, _update_live_frame)
        except Exception as e:
            print(f"更新即時畫面時出錯: {e}")
            stop_live_capture() # 出錯時停止
            enable_buttons()
    else:
        stop_live_capture() # 讀取失敗時停止
        enable_buttons()

def run_countdown(count):
    """(新增) 在 GUI 執行緒中執行語音倒數"""
    global _live_cam_countdown_job
    
    # 檢查視窗是否還在
    if not _live_cam_window or not _live_cam_window.winfo_exists():
        stop_live_capture() # 視窗被關閉，停止一切
        return

    if count > 0:
        if VOICE_ENABLED: speak(str(count))
        else: print(f"倒數: {count}")
        _live_cam_countdown_job = app_window.after(1000, run_countdown, count - 1)
    else:
        if VOICE_ENABLED: speak("拍照")
        else: print("拍照")
        _live_cam_countdown_job = None
        capture_photo_and_proceed()

def capture_photo_and_proceed():
    """(新增) 執行拍照、儲存，並觸發分析"""
    global _last_selected_image_path, _live_cam_cap
    
    if _live_cam_cap is None or not _live_cam_cap.isOpened():
        messagebox.showwarning("錯誤", "攝影機未開啟，無法拍照。")
        stop_live_capture()
        enable_buttons()
        return
        
    try:
        import cv2
    except ImportError:
        messagebox.showerror("缺少套件", "需要 OpenCV (cv2) 來拍照。")
        stop_live_capture()
        enable_buttons()
        return

    ret, frame = _live_cam_cap.read()
    
    # 拍照後立刻停止
    stop_live_capture()

    if not ret:
        messagebox.showerror("拍照失敗", "無法從攝影機擷取影像。")
        if VOICE_ENABLED: speak("拍照失敗")
        enable_buttons()
        return

    # --- 儲存檔案 ---
    try:
        save_dir = os.path.join(os.path.dirname(__file__), "captures")
        os.makedirs(save_dir, exist_ok=True)
        file_name = f"live_capture_{uuid.uuid4()}.jpg"
        file_path = os.path.join(save_dir, file_name)
        
        cv2.imwrite(file_path, frame)
        print(f"影像已儲存至: {file_path}")
    except Exception as e:
        messagebox.showerror("儲存失敗", f"無法儲存拍攝的相片: {e}")
        if VOICE_ENABLED: speak("儲存相片失敗")
        enable_buttons()
        return

    # --- 觸發分析 (類似 start_image_analysis) ---
    # --- 檢查模型是否已預載入 ---
    if not _preload_completed:
        msg = "模型仍在預載入中，請稍候..." if _preloading_in_progress else "模型預載入失敗，無法執行即時分析。"
        messagebox.showinfo("請稍候", msg, parent=app_window)
        if _preload_error:
             update_gui_safe(result_text_widget, f"[錯誤] {_preload_error}")
        enable_buttons() # 重新啟用按鈕
        return

    desc = simpledialog.askstring("圖片描述", "請輸入這張相片的描述或重點：", parent=app_window)
    if desc is None or not desc.strip():
        if VOICE_ENABLED: speak("取消操作")
        enable_buttons()
        return

    _last_selected_image_path = file_path

    # 清理舊輸出
    if result_text_widget and result_text_widget.winfo_exists():
        try: result_text_widget.config(state=tk.NORMAL); result_text_widget.delete('1.0', tk.END); result_text_widget.config(state=tk.DISABLED)
        except tk.TclError: pass
    
    # 在主視窗顯示剛拍的相片
    show_image_and_text(file_path, f"正在為 {file_name} 生成口述影像...")

    set_busy(True) # 禁用按鈕並顯示進度條

    # (修改) 直接使用新的執行緒函式，利用預載入的模型
    thread = threading.Thread(target=run_image_generation_in_thread, args=(file_path, desc), daemon=True)
    thread.start()

def start_live_capture():
    """(新增) 開啟即時攝影機視窗並開始倒數"""
    global _live_cam_window, _live_cam_label, _live_cam_cap
    
    # 停止其他播放
    stop_video_playback()
    stop_live_capture() # 確保前一個已關閉

    try:
        import cv2
    except ImportError:
        messagebox.showerror("缺少套件", "需要 OpenCV (cv2) 來使用攝影機功能。")
        return

    _live_cam_cap = cv2.VideoCapture(0) # 嘗試開啟預設攝影機
    if not _live_cam_cap or not _live_cam_cap.isOpened():
        messagebox.showerror("攝影機錯誤", "找不到攝影機，或無法開啟。")
        if VOICE_ENABLED: speak("找不到攝影機")
        if _live_cam_cap: _live_cam_cap.release()
        _live_cam_cap = None
        return

    # 禁用主視窗按鈕
    set_busy(True) 
    # 但我們要重新啟用按鈕，因為 set_busy 會在 run_script_in_thread 結束後才重設
    # 這裡我們手動禁用
    try:
        if image_button: image_button.config(state=tk.DISABLED)
        if video_button: video_button.config(state=tk.DISABLED)
        if live_button: live_button.config(state=tk.DISABLED)
        if custom_voice_button: custom_voice_button.config(state=tk.DISABLED)
    except tk.TclError: pass


    # 建立新視窗
    _live_cam_window = tk.Toplevel(app_window)
    _live_cam_window.title("即時攝影機 - 準備拍照")
    _live_cam_window.geometry("640x640")
    _live_cam_window.configure(bg="#F2D9BB")
    
    _live_cam_label = ttk.Label(_live_cam_window, text="[正在啟動攝影機...]", anchor=tk.CENTER, background="#F2D9BB")
    _live_cam_label.pack(expand=True, fill="both", padx=10, pady=10)
    
    status_label = ttk.Label(_live_cam_window, text="3秒後將自動拍照", font=("Segoe UI", 12, "bold"), 
                             foreground="#376C8B", background="#F2D9BB")
    status_label.pack(pady=5)

    # 綁定視窗關閉事件
    _live_cam_window.protocol("WM_DELETE_WINDOW", lambda: (
        stop_live_capture(), 
        enable_buttons() # 手動關閉視窗時，要重新啟用按鈕
    ))

    # 啟動畫面更新
    _update_live_frame()
    
    # 啟動倒數
    run_countdown(3)
# --- 預載入模型與資料庫功能 ---
def preload_llama_and_db():
    """在背景執行緒中預載入 LLaMA 模型和資料庫，並透過佇列與主執行緒通訊"""
    global _preloading_in_progress, _preload_completed, _preload_error

    if _preload_completed or _preloading_in_progress:
        return

    _preloading_in_progress = True
    model_dir = LLAMA_MODEL_DIR

    if not os.path.isdir(model_dir):
        print(f"[預載入] 找不到模型資料夾 {model_dir}，跳過預載入。")
        _preload_error = f"找不到模型資料夾: {model_dir}"
        _preloading_in_progress = False
        # 注意：此處無法安全地更新 GUI，因為 app_window 可能尚未建立
        return

    print(f"[預載入] 開始預載入 LLaMA 模型和 RAG 資料庫...")
    # 將 GUI 更新操作放入佇列，而不是直接呼叫
    gui_queue.put(lambda: update_status_safe("正在預載入模型..."))

    try:
        import generate_image_ad
        resources = generate_image_ad.preload_resources(model_dir)

        if resources:
            print("[預載入] LLaMA 模型和 RAG 資料庫預載入完成！")
            _preload_completed = True
            # 將成功訊息的 GUI 更新放入佇列
            gui_queue.put(lambda: update_status_safe("模型預載入完成，準備就緒"))
            gui_queue.put(lambda: update_gui_safe(result_text_widget, "[系統] LLaMA 模型和 RAG 資料庫已預先載入，可快速執行圖像口述影像生成。"))
        else:
            print("[預載入] 預載入失敗。")
            _preload_error = "預載入資源返回 None"
            # 將失敗訊息的 GUI 更新放入佇列
            gui_queue.put(lambda: update_status_safe("模型預載入失敗"))
    except Exception as e:
        print(f"[預載入] 發生錯誤: {e}")
        traceback.print_exc()
        _preload_error = str(e)
        # 將錯誤訊息的 GUI 更新放入佇列
        gui_queue.put(lambda: update_status_safe("模型預載入發生錯誤"))
        gui_queue.put(lambda: update_gui_safe(result_text_widget, f"[警告] 模型預載入失敗: {e}"))
    finally:
        _preloading_in_progress = False

# --- 新增：GUI 佇列處理函式 ---
def process_gui_queue():
    """處理來自背景執行緒的 GUI 更新請求"""
    try:
        while not gui_queue.empty():
            try:
                # 從佇列中取出函式並執行
                callback = gui_queue.get_nowait()
                callback()
            except queue.Empty:
                pass # 佇列為空，無需處理
            except Exception as e:
                print(f"處理 GUI 佇列時發生錯誤: {e}")
    finally:
        # 安排下一次檢查
        if app_window and app_window.winfo_exists():
            app_window.after(100, process_gui_queue)


# --- 語音互動迴圈 ---
def start_voice_interaction_thread():
    """(新) 啟動一個新的語音互動執行緒"""
    if not VOICE_ENABLED or not app_window or not app_window.winfo_exists():
        return
    # 確保之前的任務旗標已重設
    if _is_task_running.is_set():
        voice_thread = threading.Thread(target=voice_interaction_loop, daemon=True)
        voice_thread.start()
    else:
        print("[警告] 上一個任務尚未完全結束 (_is_task_running 未設定)，暫不啟動新語音迴圈。")


def voice_interaction_loop():
    """(修改) 語音互動迴圈，執行一次指令後即結束"""
    if not VOICE_ENABLED or not app_window or not app_window.winfo_exists():
        return
    
    # 檢查是否有其他任務正在執行
    if not _is_task_running.is_set():
        print("[語音迴圈] 偵測到任務正在執行，本次語音互動取消。")
        return

    time.sleep(0.5) # 避免任務剛結束馬上又啟動的衝突
    
    # 詢問指令
    prompt = "請說出指令：生成圖像、生成影片、即時拍照，或 結束"
    command = voice_input(prompt)
    if not command or not app_window.winfo_exists():
        # 如果沒有指令或視窗已關閉，重新啟動自己以繼續監聽
        app_window.after(100, start_voice_interaction_thread)
        return

    parsed = VoiceCommands.parse(command)
    
    action_triggered = False
    if parsed == "image":
        speak("正在啟動圖像口述影像生成程序。", wait=True)
        app_window.after(0, lambda: start_image_analysis(is_voice_command=True))
        action_triggered = True
    elif parsed == "video":
        speak("正在啟動影片口述影像生成程序，請稍後片刻。", wait=True)
        app_window.after(0, start_video_analysis)
        action_triggered = True
    elif parsed == "live" or "拍照" in command:
        speak("正在啟動即時拍照功能。", wait=True)
        app_window.after(0, start_live_capture)
        action_triggered = True
    elif parsed == "exit":
        speak("感謝您的使用，系統即將關閉")
        if VOICE_ENABLED: audio.beep_success()
        if app_window and app_window.winfo_exists():
            app_window.after(0, app_window.destroy)
    else:
        speak("無法辨識指令，請重新說一次")
        if VOICE_ENABLED: audio.beep_error()
        # 如果指令無效，重新啟動自己以繼續監聽
        app_window.after(100, start_voice_interaction_thread)

    # 如果觸發了有效操作，此執行緒的任務就完成了
    # 新的語音執行緒將在任務結束時由 finally 區塊啟動
    if action_triggered:
        print(f"[語音迴圈] 指令 '{parsed}' 已觸發，此語音執行緒結束。")

# --- GUI 建立 ---
def create_gui():
    global result_text_widget, status_label_var, app_window
    global image_button, video_button, live_button # 新增 live_button
    global custom_voice_button # 新增客製化語音按鈕
    global progress_bar
    global image_preview_label, narration_output_widget, video_preview_label
    global status_bar 

    root = tk.Tk()
    app_window = root
    root.title("口述影像生成系統 - Audio Description Generator")
    root.geometry("1200x900")
    root.minsize(1000, 800)
    
    # 啟動時最大化視窗
    try:
        root.state('zoomed')  # Windows
    except:
        try:
            root.attributes('-zoomed', True)  # Linux
        except:
            pass  # macOS 會使用 geometry 設定

    # --- 應用 Sun Valley 淺色主題 ---
    sv_ttk.set_theme("light")
    
    
    # --- 自定義配色方案 ---
    COLOR_BG_MAIN = "#F2D9BB"        # 主背景 - 淺米色
    COLOR_BG_CARD = "#FFF9F0"        # 卡片背景 - 更淺的米白色
    COLOR_PRIMARY = "#376C8B"        # 主要顏色 - 深藍色
    COLOR_SECONDARY = "#638FA8"      # 次要顏色 - 中藍灰色
    COLOR_ACCENT = "#FF5757"         # 強調顏色 - 珊瑚紅
    COLOR_TEXT_DARK = "#2C3E50"      # 深色文字
    COLOR_TEXT_LIGHT = "#FFFFFF"     # 淺色文字
    # --- 自定義樣式增強 ---
    style = ttk.Style()
    
    # 獲取主題顏色
    bg_color = COLOR_BG_CARD
    fg_color = COLOR_TEXT_DARK
    
    # 設定主背景色
    root.configure(bg=COLOR_BG_MAIN)
    
    # 配置 Frame 背景
    style.configure("TFrame", background=COLOR_BG_MAIN)
    style.configure("TLabel", background=COLOR_BG_MAIN, foreground=COLOR_TEXT_DARK)
    
    # 標題樣式
    style.configure("Header.TLabel", font=("Segoe UI", 28, "bold"), 
                    foreground=COLOR_PRIMARY, background=COLOR_BG_MAIN)
    style.configure("SubHeader.TLabel", font=("Segoe UI", 11), 
                    foreground=COLOR_SECONDARY, background=COLOR_BG_MAIN)
    
    # 區段標題樣式
    style.configure("SectionTitle.TLabel", font=("Segoe UI", 11, "bold"), 
                    foreground=COLOR_PRIMARY, background=COLOR_BG_CARD)
    
    # 按鈕增強樣式
    style.configure("Primary.TButton", 
                    font=("Segoe UI", 12, "bold"), 
                    padding=(18, 14),
                    foreground=COLOR_TEXT_DARK,
                    background=COLOR_PRIMARY,
                    borderwidth=0,
                    relief="flat")
    style.map("Primary.TButton",
              foreground=[("!active", COLOR_TEXT_DARK), ("pressed", COLOR_TEXT_DARK), ("active", COLOR_TEXT_DARK), ("hover", COLOR_TEXT_DARK)],
              background=[("!active", COLOR_PRIMARY), ("pressed", COLOR_SECONDARY), ("active", COLOR_SECONDARY), ("hover", COLOR_SECONDARY)])
    
    style.configure("Secondary.TButton", 
                    font=("Segoe UI", 11), 
                    padding=(12, 10),
                    foreground=COLOR_TEXT_LIGHT,
                    background=COLOR_SECONDARY,
                    borderwidth=0,
                    relief="flat")
    style.map("Secondary.TButton",
              foreground=[("!active", COLOR_TEXT_LIGHT), ("pressed", COLOR_TEXT_LIGHT), ("active", COLOR_TEXT_LIGHT), ("hover", COLOR_TEXT_LIGHT)],
              background=[("!active", COLOR_SECONDARY), ("pressed", COLOR_PRIMARY), ("active", COLOR_PRIMARY), ("hover", COLOR_PRIMARY)])
    
    style.configure("Accent.TButton", 
                    font=("Segoe UI", 11, "bold"),
                    foreground=COLOR_TEXT_LIGHT,
                    background=COLOR_ACCENT,
                    borderwidth=0,
                    relief="flat")
    style.map("Accent.TButton",
              foreground=[("!active", COLOR_TEXT_LIGHT), ("pressed", COLOR_TEXT_LIGHT), ("active", COLOR_TEXT_LIGHT), ("hover", COLOR_TEXT_LIGHT)],
              background=[("!active", COLOR_ACCENT), ("pressed", "#FF7777"), ("active", "#FF7777"), ("hover", "#FF7777")])
    
    
    # LabelFrame 樣式
    style.configure("Card.TLabelframe", borderwidth=2, relief="solid", 
                    background=COLOR_BG_CARD, bordercolor=COLOR_SECONDARY)
    style.configure("Card.TLabelframe.Label", font=("Segoe UI", 12, "bold"), 
                    foreground=COLOR_PRIMARY, background=COLOR_BG_CARD)
    
    # 狀態列樣式
    style.configure("Status.TLabel", font=("Segoe UI", 10), padding=(8, 5),
                    background=COLOR_BG_MAIN, foreground=COLOR_TEXT_DARK)
    
    # Separator 樣式
    style.configure("TSeparator", background=COLOR_SECONDARY)


    # --- 主要容器 ---
    main_frame = ttk.Frame(root, padding=28)
    main_frame.pack(expand=True, fill="both")

    # --- 標題區 ---
    header_frame = ttk.Frame(main_frame)
    header_frame.pack(fill="x", pady=(0, 20))
    
    header_label = tk.Label(header_frame, text="🎙️口述影像生成系統",
                           font=("Segoe UI", 28, "bold"), fg=COLOR_PRIMARY, bg=COLOR_BG_MAIN)
    header_label.pack(anchor="w", fill="x")
    subheader_label = tk.Label(header_frame, text="為視障者生成圖像與影片的口述影像旁白 - AI-Powered Audio Description Generator",
                              font=("Segoe UI", 11), fg=COLOR_SECONDARY, bg=COLOR_BG_MAIN)
    subheader_label.pack(anchor="w", fill="x", pady=(5, 0))
    
    separator = ttk.Separator(header_frame, orient="horizontal")
    separator.pack(fill="x", pady=(15, 0))

    # --- 主要功能按鈕區 ---
    btn_frame = ttk.Frame(main_frame)
    btn_frame.pack(fill="x", pady=(15, 10))
    
    image_button = tk.Button(btn_frame, text="🖼️生成圖像口述影像", command=start_image_analysis,
                             font=("Segoe UI", 12, "bold"), bg=COLOR_PRIMARY, fg=COLOR_TEXT_LIGHT,
                             activebackground=COLOR_SECONDARY, activeforeground=COLOR_TEXT_LIGHT,
                             relief=tk.FLAT, borderwidth=0, padx=18, pady=14, cursor="hand2")
    image_button.pack(side="left", expand=True, fill="x", padx=(0, 6))
    
    video_button = tk.Button(btn_frame, text="🎬生成口述影像旁白", command=start_video_analysis,
                             font=("Segoe UI", 12, "bold"), bg=COLOR_PRIMARY, fg=COLOR_TEXT_LIGHT,
                             activebackground=COLOR_SECONDARY, activeforeground=COLOR_TEXT_LIGHT,
                             relief=tk.FLAT, borderwidth=0, padx=18, pady=14, cursor="hand2")
    video_button.pack(side="left", expand=True, fill="x", padx=6)
    
    # 新增按鈕
    live_button = tk.Button(btn_frame, text="📸生成即時口述影像", command=start_live_capture,
                            font=("Segoe UI", 12, "bold"), bg=COLOR_PRIMARY, fg=COLOR_TEXT_LIGHT,
                            activebackground=COLOR_SECONDARY, activeforeground=COLOR_TEXT_LIGHT,
                            relief=tk.FLAT, borderwidth=0, padx=18, pady=14, cursor="hand2")
    live_button.pack(side="left", expand=True, fill="x", padx=(6, 0))

    # --- 客製化語音按鈕區 ---
    custom_btn_frame = ttk.Frame(main_frame)
    custom_btn_frame.pack(fill="x", pady=(0, 20))
    
    custom_voice_button = tk.Button(custom_btn_frame, text="🎙️客製化語音設定", command=open_custom_voice_dialog,
                                    font=("Segoe UI", 11, "bold"), bg=COLOR_ACCENT, fg=COLOR_TEXT_LIGHT,
                                    activebackground="#FF7777", activeforeground=COLOR_TEXT_LIGHT,
                                    relief=tk.FLAT, borderwidth=0, padx=20, pady=12, cursor="hand2")
    custom_voice_button.pack(fill="x")

    # --- 工具提示 (修改) ---
    try:
        ToolTip(image_button, "點擊以上傳單張圖片並輸入描述，\n使用 Llama 模型生成口述影像。")
        ToolTip(video_button, "點擊以選擇影片檔案，\n使用 Gemini 模型自動生成口述影像。")
        ToolTip(live_button, "點擊開啟攝影機，\n倒數3秒後自動拍照並生成口述影像。") # 新增
        ToolTip(custom_voice_button, "錄製您的聲音來替換系統的預設語音提示\n創建個人化的語音體驗") # 新增
    except Exception as e: print(f"無法建立工具提示: {e}")

    # --- 視覺輸出區 ---
    output_area_frame = ttk.Frame(main_frame)
    output_area_frame.pack(expand=True, fill="both", pady=(0, 10))
    
    # 使用 grid 佈局確保兩個預覽區域完全平分空間
    output_area_frame.columnconfigure(0, weight=1, uniform="preview")
    output_area_frame.columnconfigure(1, weight=1, uniform="preview")
    output_area_frame.rowconfigure(0, weight=1)
    
    # 圖像結果預覽 - 左半邊
    image_output_frame = ttk.LabelFrame(output_area_frame, text="📷圖像結果預覽", labelanchor="n", padding=15, style="Card.TLabelframe")
    image_output_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
    
    image_preview_label = tk.Label(image_output_frame, text="[此處顯示圖片預覽]", anchor=tk.CENTER,
                                    bg=COLOR_BG_CARD, fg=COLOR_SECONDARY, font=("Segoe UI", 10),
                                    relief=tk.SOLID, borderwidth=1, highlightbackground=COLOR_SECONDARY,
                                    highlightthickness=1, padx=10, pady=40)
    image_preview_label.pack(expand=True, fill="both", pady=(0, 10))
    
    section_label = ttk.Label(image_output_frame, text="✍️生成的口述影像:", style="SectionTitle.TLabel")
    section_label.pack(anchor="w", pady=(5,2))
    
    narration_output_widget = scrolledtext.ScrolledText(
        image_output_frame,
        wrap=tk.WORD,
        height=8,
        state=tk.DISABLED,
        font=("Segoe UI", 11),
        relief=tk.SOLID,
        borderwidth=1,
        bg=bg_color,
        fg=fg_color,
        highlightthickness=0,
        highlightbackground=COLOR_SECONDARY,
        highlightcolor=COLOR_SECONDARY,
    )
    narration_output_widget.pack(expand=True, fill="both", pady=(5, 0))

    # 影片結果預覽 - 右半邊
    video_output_frame = ttk.LabelFrame(output_area_frame, text="🎬 影片結果預覽", labelanchor="n", padding=15, style="Card.TLabelframe")
    video_output_frame.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
    
    video_preview_label = tk.Label(video_output_frame, text="[此處顯示影片預覽]", anchor=tk.CENTER,
                                    bg=COLOR_BG_CARD, fg=COLOR_SECONDARY, font=("Segoe UI", 10),
                                    relief=tk.SOLID, borderwidth=1, highlightbackground=COLOR_SECONDARY,
                                    highlightthickness=1, padx=10, pady=40)
    video_preview_label.pack(expand=True, fill="both", pady=(0, 10))
    
    open_external_btn = ttk.Button(video_output_frame, text="▶️ 在系統播放器中開啟", command=open_video_external, style="Accent.TButton")
    open_external_btn.pack(pady=(5, 5))
    try: ToolTip(open_external_btn, "使用系統預設播放器開啟生成的影片檔案")
    except Exception: pass

    # --- 執行日誌輸出區 (已根據要求移除) ---
    # log_frame = ttk.LabelFrame(main_frame, text="📋 執行日誌", labelanchor="n", padding=15, style="Card.TLabelframe")
    # log_frame.pack(fill="both", pady=(10, 0), ipady=5)
    
    # result_text_widget = scrolledtext.ScrolledText(
    #     log_frame,
    #     wrap=tk.WORD,
    #     height=8,
    #     state=tk.DISABLED,
    #     font=("Consolas", 9),
    #     relief=tk.FLAT,
    #     borderwidth=0,
    #     bg=bg_color,
    #     fg=fg_color,
    # )
    # result_text_widget.pack(expand=True, fill="both")

    # --- 狀態列與進度列 ---
    status_frame = ttk.Frame(root, relief=tk.FLAT, padding=(0, 2))
    status_frame.pack(side=tk.BOTTOM, fill=tk.X)
    
    status_label_var = tk.StringVar(value="✓ 準備就緒 - Ready")
    status_bar = ttk.Label(status_frame, textvariable=status_label_var, anchor=tk.W, style="Status.TLabel")
    status_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)
    
    
    # Progressbar 樣式
    style.configure("TProgressbar", troughcolor=COLOR_BG_CARD, background=COLOR_SECONDARY, 
                    bordercolor=COLOR_SECONDARY, lightcolor=COLOR_PRIMARY, darkcolor=COLOR_PRIMARY)
    progress_bar = ttk.Progressbar(root, mode="indeterminate")

    # --- 啟動 GUI 佇列處理 ---
    root.after(100, process_gui_queue)

    return root

# --- 程式主進入點 ---
if __name__ == "__main__":
    app_window = create_gui()

    # --- 啟動模型預載入 ---
    preload_thread = threading.Thread(target=preload_llama_and_db, daemon=True)
    preload_thread.start()

    if VOICE_ENABLED:
        # 第一次啟動
        intro_text = (
            "歡迎使用口述影像生成系統。本系統能為視障者，"
            "將圖像與影片，轉換為生動的語音口述旁白。"
            "您可以選擇生成單張圖像的描述、為影片全自動產生口述影像，"
            "或是使用即時拍照功能，捕捉當下畫面並生成描述。"
            "系統正在初始化，請稍候片刻，馬上為您準備就緒。"
        )
        speak(intro_text, wait=True)
        start_voice_interaction_thread()
    else:
        update_status_safe("語音功能未啟用")

    # 綁定關閉視窗事件
    app_window.protocol("WM_DELETE_WINDOW", lambda: (
        stop_video_playback(),
        stop_live_capture(), # 新增
        app_window.destroy()
    ))

    app_window.mainloop()

    # 清理資源
    stop_video_playback()
    stop_live_capture() # 新增
    print("應用程式已關閉。")