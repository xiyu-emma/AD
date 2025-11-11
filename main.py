# main.py 

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, simpledialog, messagebox
import subprocess
import sys
import os
import threading
import time
import traceback
import uuid
import queue
import sv_ttk  # Sun Valley 主題

# --- 語音功能 ---
try:
    from voice_interface import speak, voice_input, VoiceCommands, audio
    VOICE_ENABLED = True
except ImportError:
    print("[警告] voice_interface.py 未找到或導入失敗,語音功能將被禁用。")
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
live_button = None
image_preview_label = None
narration_output_widget = None
video_preview_label = None
progress_bar = None
status_bar = None
gui_queue = queue.Queue()

# 暫存資訊
_last_selected_image_path = None
_current_image_tk = None
_video_cap = None
_video_after_job = None
_current_video_path = None

# --- 即時攝影機全域變數 ---
_live_cam_window = None
_live_cam_label = None
_live_cam_cap = None
_live_cam_countdown_job = None
_live_cam_frame_job = None
_live_cam_tk_img = None

# --- 執行緒同步旗標 ---
_is_task_running = threading.Event()
_is_task_running.set()

# --- 語音互動控制旗標 ---
_voice_interaction_enabled = True

# --- 語音引擎實例 (用於強制停止) ---
_voice_engine = None

# --- 模型預載入狀態 ---
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

def force_stop_speaking():
    """強制停止當前的語音播放"""
    global _voice_engine
    try:
        # 嘗試停止 pyttsx3 引擎
        if _voice_engine:
            _voice_engine.stop()
        
        # 如果有其他語音引擎實例，也嘗試停止
        try:
            import pyttsx3
            if hasattr(pyttsx3, '_activeEngines'):
                for engine in list(pyttsx3._activeEngines.values()):
                    try:
                        engine.stop()
                    except:
                        pass
        except:
            pass
            
        print("[語音] 已強制停止語音播放")
    except Exception as e:
        print(f"[警告] 停止語音時發生錯誤: {e}")

# 簡易工具提示類別
class ToolTip:
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
        update_gui_safe(result_text_widget, f"[警告] 無法開啟影片檔案進行預覽:{video_path}")
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
        update_gui_safe(result_text_widget, f"[警告] 開啟外部播放器失敗:{e}")
        messagebox.showerror("開啟失敗", f"無法使用系統播放器開啟影片:\n{e}")

# --- 執行緒函式 ---
def run_script_in_thread(script_name: str, script_type: str, args: list, is_voice_command: bool = False):
    """在背景執行緒中執行腳本並將輸出傳回 GUI"""
    global _last_selected_image_path, _voice_interaction_enabled
    
    if app_window and app_window.winfo_exists():
        app_window.after(0, update_status_safe, f"正在執行 {script_type} 程序...")
        app_window.after(0, update_gui_safe, result_text_widget, f"\n--- 開始執行 {script_name} ---")
    if VOICE_ENABLED: speak(f"正在啟動,{script_type}口述影像生成程序")

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
                elif "最終影片已儲存為:" in s_line: capture_next_video_path = True
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
        error_msg = f"錯誤:找不到腳本檔案 '{script_name}' 或 Python 執行檔 '{sys.executable}'"
        print(error_msg)
        if app_window and app_window.winfo_exists():
             app_window.after(0, update_gui_safe, result_text_widget, error_msg)
             app_window.after(0, update_status_safe, f"{script_type} 失敗 (找不到檔案)")
        if VOICE_ENABLED: speak(f"啟動{script_type}失敗,找不到檔案"); audio.beep_error()
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
            # 任務結束後重新啟用語音互動
            _voice_interaction_enabled = True
            if VOICE_ENABLED and is_voice_command:
                app_window.after(200, start_voice_interaction_thread)

def enable_buttons():
    """重新啟用主按鈕"""
    try:
        if image_button and image_button.winfo_exists(): image_button.config(state=tk.NORMAL)
        if video_button and video_button.winfo_exists(): video_button.config(state=tk.NORMAL)
        if live_button and live_button.winfo_exists(): live_button.config(state=tk.NORMAL)
    except tk.TclError:
        pass

def set_busy(is_busy: bool):
    """設定 GUI 為忙碌或空閒狀態"""
    global app_window, progress_bar, status_bar, _is_task_running
    if not app_window or not app_window.winfo_exists() or progress_bar is None: return

    try:
        if is_busy:
            _is_task_running.clear()
            if image_button and image_button.winfo_exists(): image_button.config(state=tk.DISABLED)
            if video_button and video_button.winfo_exists(): video_button.config(state=tk.DISABLED)
            if live_button and live_button.winfo_exists(): live_button.config(state=tk.DISABLED)
            
            if status_bar and status_bar.winfo_exists():
                progress_bar.pack(side=tk.BOTTOM, fill=tk.X, before=status_bar)
            else:
                 progress_bar.pack(side=tk.BOTTOM, fill=tk.X)
            try: progress_bar.start(10)
            except tk.TclError: pass
            app_window.config(cursor='watch')
        else:
            _is_task_running.set()
            try: progress_bar.stop()
            except tk.TclError: pass
            progress_bar.pack_forget()
            app_window.config(cursor='')
    except tk.TclError:
        pass

# --- 啟動流程 ---
def run_image_generation_in_thread(image_path: str, description: str, is_voice_command: bool = False):
    """在背景執行緒中直接呼叫圖像生成函式"""
    global _voice_interaction_enabled
    script_type = "圖像"
    try:
        if app_window and app_window.winfo_exists():
            app_window.after(0, update_status_safe, f"正在執行 {script_type} 程序...")
            app_window.after(0, update_gui_safe, result_text_widget, f"\n--- 開始執行圖像口述影像生成 ---")

        import generate_image_ad
        final_answer, final_image_path = generate_image_ad.generate_narration_from_preloaded(
            image_file=image_path,
            user_desc=description
        )

        success_msg = "--- 圖像口述影像生成成功 ---"
        print(success_msg)
        if app_window and app_window.winfo_exists():
            app_window.after(0, update_gui_safe, result_text_widget, success_msg)
            app_window.after(0, update_status_safe, f"{script_type} 完成")
        
        # === 修改重點：先顯示圖片和文字，再朗讀 ===
        
        # 1. 先在畫面上顯示圖片和口述影像文字
        if final_image_path and final_answer:
            if app_window and app_window.winfo_exists():
                app_window.after(0, show_image_and_text, final_image_path, final_answer)
                print("[顯示] 圖片和口述影像已顯示在畫面上")
        else:
            if app_window and app_window.winfo_exists():
                app_window.after(0, update_gui_safe, result_text_widget, "[提示] 未找到圖片路徑或生成結果用於顯示。")
        
        # 2. 等待一小段時間讓 GUI 更新完成
        time.sleep(0.5)
        
        # 3. 再使用 TTS 語音朗讀口述影像內容
        if VOICE_ENABLED: 
            speak(f"{script_type} 處理完成", wait=True)
            # 朗讀圖像口述影像內容
            if final_answer:
                print("[語音] 開始朗讀口述影像內容")
                speak(final_answer, wait=True)
                print("[語音] 口述影像朗讀完成")

    except Exception as e:
        error_msg = f"執行圖像生成時發生未預期的錯誤: {e}\n{traceback.format_exc()}"
        print(error_msg)
        if app_window and app_window.winfo_exists():
            app_window.after(0, update_gui_safe, result_text_widget, error_msg)
            app_window.after(0, update_status_safe, f"{script_type} 失敗 (未知錯誤)")
        if VOICE_ENABLED: speak(f"啟動{script_type}時發生未知錯誤", wait=True); audio.beep_error()
    finally:
        if app_window and app_window.winfo_exists():
            app_window.after(100, enable_buttons)
            app_window.after(0, set_busy, False)
            # 任務結束後重新啟用語音互動
            _voice_interaction_enabled = True
            if VOICE_ENABLED and is_voice_command:
                app_window.after(200, start_voice_interaction_thread)



def start_image_analysis(is_voice_command: bool = False):
    global _last_selected_image_path, _voice_interaction_enabled
    
    # === 第一步：立即禁用語音並停止播放 ===
    _voice_interaction_enabled = False
    force_stop_speaking()
    print(f"[圖像分析] 語音已停止，is_voice_command={is_voice_command}")
    
    if not _preload_completed:
        msg = "模型仍在預載入中,請稍候..." if _preloading_in_progress else "模型預載入失敗,無法執行圖像分析。"
        if is_voice_command:
            speak(msg)
        else:
            messagebox.showinfo("請稍候", msg, parent=app_window)
        if _preload_error:
             update_gui_safe(result_text_widget, f"[錯誤] {_preload_error}")
        _voice_interaction_enabled = True  # 失敗時恢復語音
        return

    if is_voice_command:
        speak("請手動選擇圖片檔案,並輸入描述。")

    file_path = filedialog.askopenfilename(title="請選擇一張圖片", filetypes=[("Image Files", "*.png *.jpg *.jpeg *.webp *.bmp")])
    if not file_path:
        if is_voice_command: speak("操作已取消")
        _voice_interaction_enabled = True  # 取消時恢復語音
        return

    desc = simpledialog.askstring("圖片描述", "請輸入這張圖片的描述或重點:", parent=app_window)
    if desc is None:
        if is_voice_command: speak("操作已取消")
        _voice_interaction_enabled = True  # 取消時恢復語音
        return
    if not desc.strip():
        messagebox.showwarning("輸入錯誤", "圖片描述不能為空。", parent=app_window)
        _voice_interaction_enabled = True  # 輸入錯誤時恢復語音
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

    thread = threading.Thread(target=run_image_generation_in_thread, args=(file_path, desc, is_voice_command), daemon=True)
    thread.start()

def start_video_analysis(is_voice_command: bool = False):
    global _voice_interaction_enabled
    
    # === 第一步：立即禁用語音並停止播放 ===
    _voice_interaction_enabled = False
    force_stop_speaking()
    print(f"[影片分析] 語音已停止，is_voice_command={is_voice_command}")
    
    file_path = filedialog.askopenfilename(
        title="請選擇一個影片", 
        filetypes=[("Video Files", "*.mp4 *.avi *.mov *.mkv")]
    )
    if not file_path: 
        _voice_interaction_enabled = True  # 取消時恢復語音
        return

    desc = simpledialog.askstring("影片摘要", "請輸入這段影片的摘要或重點:", parent=app_window)
    if desc is None: 
        _voice_interaction_enabled = True  # 取消時恢復語音
        return
    if not desc.strip():
        messagebox.showwarning("輸入錯誤", "影片摘要不能為空。", parent=app_window)
        _voice_interaction_enabled = True  # 輸入錯誤時恢復語音
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

    set_busy(True)

    args = ["--video_file", file_path, "--summary", desc]
    
    thread = threading.Thread(target=run_script_in_thread, args=('generate_video_ad.py', '影片', args, is_voice_command), daemon=True)
    thread.start()

# --- 即時攝影機相關函式 ---

def stop_live_capture():
    """停止即時攝影機畫面並清理資源"""
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
    """抓取並顯示即時攝影機畫面"""
    global _live_cam_frame_job, _live_cam_cap, _live_cam_label, _live_cam_tk_img
    
    if _live_cam_cap is None or not _live_cam_cap.isOpened():
        return

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
            
            _live_cam_frame_job = app_window.after(30, _update_live_frame)
        except Exception as e:
            print(f"更新即時畫面時出錯: {e}")
            stop_live_capture()
            enable_buttons()
    else:
        stop_live_capture()
        enable_buttons()

def run_countdown(count):
    """在 GUI 執行緒中執行語音倒數"""
    global _live_cam_countdown_job
    
    if not _live_cam_window or not _live_cam_window.winfo_exists():
        stop_live_capture()
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
    """執行拍照、儲存,並觸發分析"""
    global _last_selected_image_path, _live_cam_cap, _voice_interaction_enabled
    
    if _live_cam_cap is None or not _live_cam_cap.isOpened():
        messagebox.showwarning("錯誤", "攝影機未開啟,無法拍照。")
        stop_live_capture()
        enable_buttons()
        _voice_interaction_enabled = True  # 失敗時恢復語音
        return
        
    try:
        import cv2
    except ImportError:
        messagebox.showerror("缺少套件", "需要 OpenCV (cv2) 來拍照。")
        stop_live_capture()
        enable_buttons()
        _voice_interaction_enabled = True  # 失敗時恢復語音
        return

    ret, frame = _live_cam_cap.read()
    
    stop_live_capture()

    if not ret:
        messagebox.showerror("拍照失敗", "無法從攝影機擷取影像。")
        if VOICE_ENABLED: speak("拍照失敗")
        enable_buttons()
        _voice_interaction_enabled = True  # 失敗時恢復語音
        return

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
        _voice_interaction_enabled = True  # 失敗時恢復語音
        return

    if not _preload_completed:
        msg = "模型仍在預載入中,請稍候..." if _preloading_in_progress else "模型預載入失敗,無法執行即時分析。"
        messagebox.showinfo("請稍候", msg, parent=app_window)
        if _preload_error:
             update_gui_safe(result_text_widget, f"[錯誤] {_preload_error}")
        enable_buttons()
        _voice_interaction_enabled = True  # 失敗時恢復語音
        return

    desc = simpledialog.askstring("圖片描述", "請輸入這張相片的描述或重點:", parent=app_window)
    if desc is None or not desc.strip():
        if VOICE_ENABLED: speak("取消操作")
        enable_buttons()
        _voice_interaction_enabled = True  # 取消時恢復語音
        return

    _last_selected_image_path = file_path

    if result_text_widget and result_text_widget.winfo_exists():
        try: result_text_widget.config(state=tk.NORMAL); result_text_widget.delete('1.0', tk.END); result_text_widget.config(state=tk.DISABLED)
        except tk.TclError: pass
    
    show_image_and_text(file_path, f"正在為 {file_name} 生成口述影像...")

    set_busy(True)

    # 即時拍照是語音命令觸發
    thread = threading.Thread(target=run_image_generation_in_thread, args=(file_path, desc, True), daemon=True)
    thread.start()

def start_live_capture(is_voice_command: bool = False):
    """開啟即時攝影機視窗並開始倒數"""
    global _live_cam_window, _live_cam_label, _live_cam_cap, _voice_interaction_enabled
    
    # === 第一步：立即禁用語音並停止播放 ===
    _voice_interaction_enabled = False
    force_stop_speaking()
    print(f"[即時拍照] 語音已停止，is_voice_command={is_voice_command}")
    
    stop_video_playback()
    stop_live_capture()

    try:
        import cv2
    except ImportError:
        messagebox.showerror("缺少套件", "需要 OpenCV (cv2) 來使用攝影機功能。")
        _voice_interaction_enabled = True  # 失敗時恢復語音
        return

    _live_cam_cap = cv2.VideoCapture(0)
    if not _live_cam_cap or not _live_cam_cap.isOpened():
        messagebox.showerror("攝影機錯誤", "找不到攝影機,或無法開啟。")
        if VOICE_ENABLED: speak("找不到攝影機")
        if _live_cam_cap: _live_cam_cap.release()
        _live_cam_cap = None
        _voice_interaction_enabled = True  # 失敗時恢復語音
        return

    set_busy(True)
    try:
        if image_button: image_button.config(state=tk.DISABLED)
        if video_button: video_button.config(state=tk.DISABLED)
        if live_button: live_button.config(state=tk.DISABLED)
    except tk.TclError: pass

    _live_cam_window = tk.Toplevel(app_window)
    _live_cam_window.title("即時攝影機 - 準備拍照")
    _live_cam_window.geometry("640x640")
    _live_cam_window.configure(bg="#F2D9BB")
    
    _live_cam_label = ttk.Label(_live_cam_window, text="[正在啟動攝影機...]", anchor=tk.CENTER, background="#F2D9BB")
    _live_cam_label.pack(expand=True, fill="both", padx=10, pady=10)
    
    status_label = ttk.Label(_live_cam_window, text="3秒後將自動拍照", font=("Segoe UI", 12, "bold"), 
                             foreground="#376C8B", background="#F2D9BB")
    status_label.pack(pady=5)

    def on_close_camera_window():
        stop_live_capture()
        enable_buttons()
        global _voice_interaction_enabled
        _voice_interaction_enabled = True  # 關閉視窗時恢復語音
    
    _live_cam_window.protocol("WM_DELETE_WINDOW", on_close_camera_window)

    _update_live_frame()
    run_countdown(3)

# --- 預載入模型與資料庫功能 ---
def preload_llama_and_db():
    """在背景執行緒中預載入 LLaMA 模型和資料庫"""
    global _preloading_in_progress, _preload_completed, _preload_error

    if _preload_completed or _preloading_in_progress:
        return

    _preloading_in_progress = True
    model_dir = LLAMA_MODEL_DIR

    if not os.path.isdir(model_dir):
        print(f"[預載入] 找不到模型資料夾 {model_dir},跳過預載入。")
        _preload_error = f"找不到模型資料夾: {model_dir}"
        _preloading_in_progress = False
        return

    print(f"[預載入] 開始預載入 LLaMA 模型和 RAG 資料庫...")
    gui_queue.put(lambda: update_status_safe("正在預載入模型..."))

    try:
        print("[預載入] 正在導入 generate_image_ad 模組...")
        import generate_image_ad
        
        print("[預載入] 正在調用 preload_resources 函式...")
        resources = generate_image_ad.preload_resources(model_dir)

        if resources:
            print("[預載入] LLaMA 模型和 RAG 資料庫預載入完成!")
            _preload_completed = True
            gui_queue.put(lambda: update_status_safe("模型預載入完成,準備就緒"))
            gui_queue.put(lambda: update_gui_safe(result_text_widget, "[系統] LLaMA 模型和 RAG 資料庫已預先載入,可快速執行圖像口述影像生成。"))
        else:
            print("[預載入] 預載入失敗(資源返回 None)。")
            _preload_error = "預載入資源返回 None"
            gui_queue.put(lambda: update_status_safe("模型預載入失敗"))
            gui_queue.put(lambda: update_gui_safe(result_text_widget, "[警告] 模型預載入失敗:資源無法加載"))
    except ImportError as e:
        print(f"[預載入] 模組導入錯誤: {e}")
        traceback.print_exc()
        _preload_error = f"導入錯誤: {e}"
        error_msg = f"模型預載入失敗 (導入錯誤): {str(e)[:200]}"
        gui_queue.put(lambda: update_status_safe("模型預載入發生導入錯誤"))
        gui_queue.put(lambda: update_gui_safe(result_text_widget, f"[警告] {error_msg}\n詳細錯誤信息請查看控制台輸出。"))
    except RuntimeError as e:
        print(f"[預載入] 運行時錯誤: {e}")
        traceback.print_exc()
        _preload_error = f"運行時錯誤: {e}"
        error_msg = f"模型預載入失敗 (運行時錯誤): {str(e)[:200]}"
        gui_queue.put(lambda: update_status_safe("模型預載入發生運行時錯誤"))
        gui_queue.put(lambda: update_gui_safe(result_text_widget, f"[警告] {error_msg}\n詳細錯誤信息請查看控制台輸出。"))
    except Exception as e:
        print(f"[預載入] 發生未預期的錯誤: {e}")
        traceback.print_exc()
        _preload_error = str(e)
        error_msg = f"模型預載入失敗: {str(e)[:200]}"
        gui_queue.put(lambda: update_status_safe("模型預載入發生錯誤"))
        gui_queue.put(lambda: update_gui_safe(result_text_widget, f"[警告] {error_msg}\n詳細錯誤信息請查看控制台輸出。"))
    finally:
        _preloading_in_progress = False

# --- GUI 佇列處理函式 ---
def process_gui_queue():
    """處理來自背景執行緒的 GUI 更新請求"""
    try:
        while not gui_queue.empty():
            try:
                callback = gui_queue.get_nowait()
                callback()
            except queue.Empty:
                pass
            except Exception as e:
                print(f"處理 GUI 佇列時發生錯誤: {e}")
    finally:
        if app_window and app_window.winfo_exists():
            app_window.after(100, process_gui_queue)


# --- 語音互動迴圈 ---
def start_voice_interaction_thread():
    """啟動一個新的語音互動執行緒"""
    global _voice_interaction_enabled
    
    if not VOICE_ENABLED or not app_window or not app_window.winfo_exists():
        return
    # 檢查語音互動是否被禁用
    if not _voice_interaction_enabled:
        print("[語音迴圈] 語音互動已被禁用,不啟動新迴圈。")
        return
    if _is_task_running.is_set():
        voice_thread = threading.Thread(target=voice_interaction_loop, daemon=True)
        voice_thread.start()
    else:
        print("[警告] 上一個任務尚未完全結束,暫不啟動新語音迴圈。")


def voice_interaction_loop():
    """語音互動迴圈,執行一次指令後即結束"""
    global _voice_interaction_enabled
    
    if not VOICE_ENABLED or not app_window or not app_window.winfo_exists():
        return
    
    if not _is_task_running.is_set():
        print("[語音迴圈] 偵測到任務正在執行,本次語音互動取消。")
        return

    time.sleep(0.5)
    
    prompt = "請說出指令:生成圖像、生成影片、即時拍照,或 結束"
    command = voice_input(prompt)
    if not command or not app_window.winfo_exists():
        # 只有在語音互動啟用時才重新啟動
        if _voice_interaction_enabled:
            app_window.after(100, start_voice_interaction_thread)
        return

    parsed = VoiceCommands.parse(command)
    
    action_triggered = False
    if parsed == "image":
        speak("正在啟動圖像口述影像生成程序。", wait=True)
        app_window.after(0, lambda: start_image_analysis(is_voice_command=True))
        action_triggered = True
    elif parsed == "video":
        speak("正在啟動影片口述影像生成程序,請稍後片刻。", wait=True)
        app_window.after(0, lambda: start_video_analysis(is_voice_command=True))
        action_triggered = True
    elif parsed == "live" or "拍照" in command:
        speak("正在啟動即時拍照功能。", wait=True)
        app_window.after(0, lambda: start_live_capture(is_voice_command=True))
        action_triggered = True
    elif parsed == "exit":
        speak("感謝您的使用,系統即將關閉")
        if VOICE_ENABLED: audio.beep_success()
        if app_window and app_window.winfo_exists():
            app_window.after(0, app_window.destroy)
    else:
        speak("無法辨識指令,請重新說一次")
        if VOICE_ENABLED: audio.beep_error()
        # 只有在語音互動啟用時才重新啟動
        if _voice_interaction_enabled:
            app_window.after(100, start_voice_interaction_thread)

    if action_triggered:
        print(f"[語音迴圈] 指令 '{parsed}' 已觸發,此語音執行緒結束。")

# --- GUI 建立 ---
def create_gui():
    global result_text_widget, status_label_var, app_window
    global image_button, video_button, live_button
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
    COLOR_BG_MAIN = "#F2D9BB"
    COLOR_BG_CARD = "#FFF9F0"
    COLOR_PRIMARY = "#376C8B"
    COLOR_SECONDARY = "#638FA8"
    COLOR_ACCENT = "#FF5757"
    COLOR_TEXT_DARK = "#2C3E50"
    COLOR_TEXT_LIGHT = "#FFFFFF"
    
    # --- 自定義樣式增強 ---
    style = ttk.Style()
    
    bg_color = COLOR_BG_CARD
    fg_color = COLOR_TEXT_DARK
    
    root.configure(bg=COLOR_BG_MAIN)
    
    style.configure("TFrame", background=COLOR_BG_MAIN)
    style.configure("TLabel", background=COLOR_BG_MAIN, foreground=COLOR_TEXT_DARK)
    
    style.configure("Header.TLabel", font=("Segoe UI", 28, "bold"), 
                    foreground=COLOR_PRIMARY, background=COLOR_BG_MAIN)
    style.configure("SubHeader.TLabel", font=("Segoe UI", 11), 
                    foreground=COLOR_SECONDARY, background=COLOR_BG_MAIN)
    
    style.configure("SectionTitle.TLabel", font=("Segoe UI", 11, "bold"), 
                    foreground=COLOR_PRIMARY, background=COLOR_BG_CARD)
    
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
    
    style.configure("Card.TLabelframe", borderwidth=2, relief="solid", 
                    background=COLOR_BG_CARD, bordercolor=COLOR_SECONDARY)
    style.configure("Card.TLabelframe.Label", font=("Segoe UI", 12, "bold"), 
                    foreground=COLOR_PRIMARY, background=COLOR_BG_CARD)
    
    style.configure("Status.TLabel", font=("Segoe UI", 10), padding=(8, 5),
                    background=COLOR_BG_MAIN, foreground=COLOR_TEXT_DARK)
    
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
    
    live_button = tk.Button(btn_frame, text="📸生成即時口述影像", command=start_live_capture,
                            font=("Segoe UI", 12, "bold"), bg=COLOR_PRIMARY, fg=COLOR_TEXT_LIGHT,
                            activebackground=COLOR_SECONDARY, activeforeground=COLOR_TEXT_LIGHT,
                            relief=tk.FLAT, borderwidth=0, padx=18, pady=14, cursor="hand2")
    live_button.pack(side="left", expand=True, fill="x", padx=(6, 0))

    # --- 工具提示 ---
    try:
        ToolTip(image_button, "點擊以上傳單張圖片並輸入描述,\n使用 Llama 模型生成口述影像。")
        ToolTip(video_button, "點擊以選擇影片檔案,\n使用 Gemini 模型自動生成口述影像。")
        ToolTip(live_button, "點擊開啟攝影機,\n倒數3秒後自動拍照並生成口述影像。")
    except Exception as e: print(f"無法建立工具提示: {e}")

    # --- 視覺輸出區 ---
    output_area_frame = ttk.Frame(main_frame)
    output_area_frame.pack(expand=True, fill="both", pady=(0, 10))
    
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

    # --- 狀態列與進度列 ---
    status_frame = ttk.Frame(root, relief=tk.FLAT, padding=(0, 2))
    status_frame.pack(side=tk.BOTTOM, fill=tk.X)
    
    status_label_var = tk.StringVar(value="✓ 準備就緒 - Ready")
    status_bar = ttk.Label(status_frame, textvariable=status_label_var, anchor=tk.W, style="Status.TLabel")
    status_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)
    
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
        intro_text = (
            "歡迎使用口述影像生成系統。本系統能為視障者,"
            "將圖像與影片,轉換為生動的語音口述旁白。"
            "您可以選擇生成單張圖像的描述、為影片全自動產生口述影像,"
            "或是使用即時拍照功能,捕捉當下畫面並生成描述。"
            "系統正在初始化,請稍候片刻,馬上為您準備就緒。"
        )
        speak(intro_text, wait=True)
        start_voice_interaction_thread()
    else:
        update_status_safe("語音功能未啟用")

    app_window.protocol("WM_DELETE_WINDOW", lambda: (
        stop_video_playback(),
        stop_live_capture(),
        app_window.destroy()
    ))

    app_window.mainloop()

    stop_video_playback()
    stop_live_capture()
    print("應用程式已關閉。")
