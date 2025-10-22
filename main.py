# main.py (單一環境最終整合版 - 已新增即時拍照功能)

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, simpledialog, messagebox
import subprocess
import sys
import os
import threading
import time
import traceback
import uuid # 新增

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

# --- 全域變數 ---
result_text_widget = None
status_label_var = None
app_window = None
image_button = None
video_button = None
live_button = None # 新增
image_preview_label = None
narration_output_widget = None
video_preview_label = None
progress_bar = None
status_bar = None 

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
             tw.configure(bg="#111827")
             label = tk.Label(tw, text=self.text, justify=tk.LEFT, background="#111827",
                              foreground="white", relief=tk.SOLID, borderwidth=1,
                              font=("Helvetica", 9), padx=6, pady=3)
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
        max_w, max_h = 480, 360
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

            if script_name == 'generate_image_ad.py':
                img_to_show = final_image_path or _last_selected_image_path
                if img_to_show and final_answer != f"[{script_type} 未返回明確答案]":
                     if app_window and app_window.winfo_exists(): 
                         app_window.after(0, show_image_and_text, img_to_show, final_answer)
                else:
                     if app_window and app_window.winfo_exists(): 
                         app_window.after(0, update_gui_safe, result_text_widget, "[提示] 未找到圖片路徑或生成結果用於顯示。")

            elif script_name == 'generate_video_ad.py':
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

def enable_buttons():
    """重新啟用主按鈕 (加入檢查)"""
    try:
        # 檢查元件是否存在
        if image_button and image_button.winfo_exists(): image_button.config(state=tk.NORMAL)
        if video_button and video_button.winfo_exists(): video_button.config(state=tk.NORMAL)
        if live_button and live_button.winfo_exists(): live_button.config(state=tk.NORMAL) # 新增
    except tk.TclError:
        pass # 視窗可能已關閉

def set_busy(is_busy: bool):
    """設定 GUI 為忙碌或空閒狀態 (加入檢查)"""
    global app_window, progress_bar, status_bar
    if not app_window or not app_window.winfo_exists() or progress_bar is None: return

    try:
        if is_busy:
            # 禁用所有按鈕
            if image_button and image_button.winfo_exists(): image_button.config(state=tk.DISABLED)
            if video_button and video_button.winfo_exists(): video_button.config(state=tk.DISABLED)
            if live_button and live_button.winfo_exists(): live_button.config(state=tk.DISABLED) # 新增
            
            if status_bar and status_bar.winfo_exists():
                progress_bar.pack(side=tk.BOTTOM, fill=tk.X, before=status_bar)
            else: 
                 progress_bar.pack(side=tk.BOTTOM, fill=tk.X)
            try: progress_bar.start(10)
            except tk.TclError: pass
            app_window.config(cursor='watch')
        else:
            # 啟用按鈕 (由 enable_buttons 函式處理)
            try: progress_bar.stop()
            except tk.TclError: pass
            progress_bar.pack_forget()
            app_window.config(cursor='')
            # enable_buttons() 會由 run_script_in_thread 的 finally 呼叫
    except tk.TclError:
        pass 

# --- 啟動流程 ---
def start_image_analysis():
    global _last_selected_image_path
    file_path = filedialog.askopenfilename(title="請選擇一張圖片", filetypes=[("Image Files", "*.png *.jpg *.jpeg *.webp *.bmp")])
    if not file_path: return

    desc = simpledialog.askstring("圖片描述", "請輸入這張圖片的描述或重點：", parent=app_window)
    if desc is None: return
    if not desc.strip():
        messagebox.showwarning("輸入錯誤", "圖片描述不能為空。", parent=app_window)
        return

    model_dir = os.path.join(".", "models", "Llama-3.2-11B-Vision-Instruct")
    if not os.path.isdir(model_dir):
         messagebox.showerror("缺少模型", f"在相對路徑 '{model_dir}' 下找不到 Llama 模型資料夾。\n請確認模型已下載並放置在正確位置。", parent=app_window)
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

    # 禁用按鈕並設定忙碌
    # try:
    #     if image_button and image_button.winfo_exists(): image_button.config(state=tk.DISABLED)
    #     if video_button and video_button.winfo_exists(): video_button.config(state=tk.DISABLED)
    #     if live_button and live_button.winfo_exists(): live_button.config(state=tk.DISABLED) # 新增
    # except tk.TclError: pass
    set_busy(True) # set_busy 會處理按鈕禁用

    args = ["--model_path", model_dir, "--image_file", file_path, "--desc", desc]
    thread = threading.Thread(target=run_script_in_thread, args=('generate_image_ad.py', '圖像', args), daemon=True)
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
    desc = simpledialog.askstring("圖片描述", "請輸入這張相片的描述或重點：", parent=app_window)
    if desc is None or not desc.strip():
        if VOICE_ENABLED: speak("取消操作")
        enable_buttons()
        return

    model_dir = os.path.join(".", "models", "Llama-3.2-11B-Vision-Instruct")
    if not os.path.isdir(model_dir):
         messagebox.showerror("缺少模型", f"在相對路徑 '{model_dir}' 下找不到 Llama 模型資料夾。")
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

    args = ["--model_path", model_dir, "--image_file", file_path, "--desc", desc]
    thread = threading.Thread(target=run_script_in_thread, args=('generate_image_ad.py', '即時圖像', args), daemon=True)
    thread.start()
    # run_script_in_thread 會在 finally 中呼叫 enable_buttons()

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
    except tk.TclError: pass


    # 建立新視窗
    _live_cam_window = tk.Toplevel(app_window)
    _live_cam_window.title("即時攝影機 - 準備拍照")
    _live_cam_window.geometry("640x640")
    
    _live_cam_label = ttk.Label(_live_cam_window, text="[正在啟動攝影機...]", anchor=tk.CENTER)
    _live_cam_label.pack(expand=True, fill="both", padx=10, pady=10)
    
    status_label = ttk.Label(_live_cam_window, text="3秒後將自動拍照", font=("Helvetica", 12, "bold"))
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


# --- 語音互動迴圈 ---
def voice_interaction_loop():
    # (加入 app_window 檢查)
    if not VOICE_ENABLED: return
    time.sleep(1.5)
    if not app_window or not app_window.winfo_exists(): return
    speak("歡迎使用口述影像生成系統")
    session_active = True
    while session_active:
        if not app_window or not app_window.winfo_exists(): break
        
        # --- (修改) 增加語音指令 ---
        prompt = "請說出指令：生成圖像、生成影片、即時拍照，或 結束"
        command = voice_input(prompt)
        if not command: continue
        if not app_window or not app_window.winfo_exists(): break

        parsed = VoiceCommands.parse(command) # 假設 voice_interface 已更新
        
        # --- (修改) 處理新指令 ---
        # 假設 VoiceCommands.parse 能處理 "即時拍照" -> "live"
        if parsed == "image": app_window.after(0, start_image_analysis)
        elif parsed == "video": app_window.after(0, start_video_analysis)
        elif parsed == "live" or "拍照" in command: # 增加觸發詞
            app_window.after(0, start_live_capture)
        elif parsed == "exit":
            speak("感謝您的使用，系統即將關閉")
            if VOICE_ENABLED: audio.beep_success()
            if app_window and app_window.winfo_exists(): app_window.destroy()
            session_active = False
        else:
            speak("無法辨識指令，請重新說一次")
            if VOICE_ENABLED: audio.beep_error()

# --- GUI 建立 ---
def create_gui():
    global result_text_widget, status_label_var, app_window
    global image_button, video_button, live_button # 新增 live_button
    global progress_bar
    global image_preview_label, narration_output_widget, video_preview_label
    global status_bar 

    root = tk.Tk()
    app_window = root
    root.title("口述影像生成系統")
    root.geometry("1000x780")
    root.minsize(900, 680)

    # --- 主題與色彩 ---
    style = ttk.Style()
    try: style.theme_use("clam")
    except Exception: pass
    ACCENT, ACCENT_HOVER, BG, TEXT, SUBTEXT, BORDER = "#4F46E5", "#4338CA", "#F8FAFC", "#111827", "#6B7280", "#E5E7EB"
    try: root.configure(background=BG)
    except tk.TclError: pass

    # --- 設定元件樣式 ---
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=TEXT, font=("Helvetica", 10))
    style.configure("Header.TLabel", background=BG, foreground=TEXT, font=("Helvetica", 20, "bold"))
    style.configure("SubHeader.TLabel", background=BG, foreground=SUBTEXT, font=("Helvetica", 11))
    style.configure("TLabelFrame", background=BG, foreground=TEXT, bordercolor=BORDER, relief=tk.SOLID, borderwidth=1)
    style.configure("TLabelFrame.Label", background=BG, foreground=TEXT, font=("Helvetica", 11, "bold"))
    style.configure("TButton", font=("Helvetica", 12), padding=(12, 10), borderwidth=1)
    style.configure("Primary.TButton", background=ACCENT, foreground="white", relief=tk.FLAT)
    style.map("Primary.TButton", background=[("active", ACCENT_HOVER), ("disabled", "#9CA3AF")], foreground=[("disabled", "#E5E7EB")])
    style.configure("Secondary.TButton", background="#E5E7EB", foreground=TEXT, relief=tk.FLAT)
    style.map("Secondary.TButton", background=[("active", "#D1D5DB")])
    style.configure("Warning.TButton", background="#DC2626", foreground="white", relief=tk.FLAT) # 新增紅色按鈕
    style.map("Warning.TButton", background=[("active", "#B91C1C"), ("disabled", "#9CA3AF")], foreground=[("disabled", "#E5E7EB")])
    style.configure("Horizontal.TProgressbar", troughcolor=BORDER, background=ACCENT)
    style.configure("Status.TLabel", background="#1F2937", foreground="#D1D5DB", font=("Consolas", 9))

    # --- 主要容器 ---
    main_frame = ttk.Frame(root, padding=20)
    main_frame.pack(expand=True, fill="both")

    # --- 標題區 ---
    header_label = ttk.Label(main_frame, text="口述影像生成系統", style="Header.TLabel")
    header_label.pack(anchor="w")
    subheader_label = ttk.Label(main_frame, text="為視障者生成圖像與影片的口述影像旁白", style="SubHeader.TLabel")
    subheader_label.pack(anchor="w", pady=(0, 15))

    # --- 功能按鈕區 (修改) ---
    btn_frame = ttk.Frame(main_frame)
    btn_frame.pack(fill="x", pady=(5, 10))
    
    image_button = ttk.Button(btn_frame, text="🖼️ 生成圖像口述影像", command=start_image_analysis, style="Primary.TButton")
    image_button.pack(side="left", expand=True, fill="x", padx=(0, 5)) # 修改 padding
    
    video_button = ttk.Button(btn_frame, text="🎬 生成口述影像旁白", command=start_video_analysis, style="Primary.TButton")
    video_button.pack(side="left", expand=True, fill="x", padx=5) # 修改 padding
    
    # 新增按鈕
    live_button = ttk.Button(btn_frame, text="📸 生成即時口述影像", command=start_live_capture, style="Primary.TButton")
    live_button.pack(side="left", expand=True, fill="x", padx=(5, 0)) # 修改 padding

    # --- 工具提示 (修改) ---
    try:
        ToolTip(image_button, "點擊以上傳單張圖片並輸入描述，\n使用 Llama 模型生成口述影像。")
        ToolTip(video_button, "點擊以選擇影片檔案，\n使用 Gemini 模型自動生成口述影像。")
        ToolTip(live_button, "點擊開啟攝影機，\n倒數3秒後自動拍照並生成口述影像。") # 新增
    except Exception as e: print(f"無法建立工具提示: {e}")

    # --- 視覺輸出區 ---
    output_area_frame = ttk.Frame(main_frame)
    output_area_frame.pack(expand=True, fill="both", pady=10)
    image_output_frame = ttk.LabelFrame(output_area_frame, text="圖像結果預覽", labelanchor="n", padding=10)
    image_output_frame.pack(side="left", expand=True, fill="both", padx=(0, 10))
    image_preview_label = ttk.Label(image_output_frame, text="[此處顯示圖片預覽]", anchor=tk.CENTER, background=BORDER) 
    image_preview_label.pack(fill="x", pady=(5, 10))
    ttk.Label(image_output_frame, text="生成的口述影像:", font=("Helvetica", 10, "bold")).pack(anchor="w", pady=(5,2))
    narration_output_widget = scrolledtext.ScrolledText(image_output_frame, wrap=tk.WORD, height=6, state=tk.DISABLED, font=("Helvetica", 10), relief=tk.SOLID, borderwidth=1, bd=1)
    narration_output_widget.pack(expand=True, fill="both")

    video_output_frame = ttk.LabelFrame(output_area_frame, text="影片結果預覽", labelanchor="n", padding=10)
    video_output_frame.pack(side="left", expand=True, fill="both", padx=(10, 0))
    video_preview_label = ttk.Label(video_output_frame, text="[此處顯示影片預覽]", anchor=tk.CENTER, background=BORDER) 
    video_preview_label.pack(fill="x", pady=(5, 10))
    open_external_btn = ttk.Button(video_output_frame, text="▶️ 在系統播放器中開啟", command=open_video_external, style="Secondary.TButton")
    open_external_btn.pack(pady=(5, 5))
    try: ToolTip(open_external_btn, "使用系統預設播放器開啟生成的影片檔案")
    except Exception: pass

    # --- 執行日誌輸出區 ---
    result_frame = ttk.LabelFrame(main_frame, text="執行日誌", labelanchor="n", padding=10)
    result_frame.pack(expand=True, fill="both", pady=(10, 0))
    result_text_widget = scrolledtext.ScrolledText(result_frame, wrap=tk.WORD, height=10, state=tk.DISABLED, font=("Consolas", 9), relief=tk.SOLID, borderwidth=1, bd=1, background="#F9FAFB", foreground="#374151")
    result_text_widget.pack(expand=True, fill="both")

    # --- 狀態列與進度列 ---
    status_label_var = tk.StringVar(value="準備就緒")
    status_bar = ttk.Label(root, textvariable=status_label_var, anchor=tk.W, padding=(8, 5), style="Status.TLabel")
    status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    progress_bar = ttk.Progressbar(root, mode="indeterminate", style="Horizontal.TProgressbar")

    return root

# --- 程式主進入點 ---
if __name__ == "__main__":
    app_window = create_gui()

    if VOICE_ENABLED:
        voice_thread = threading.Thread(target=voice_interaction_loop, daemon=True)
        voice_thread.start()
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