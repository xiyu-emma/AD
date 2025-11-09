#!/usr/bin/env python3
"""
環境檢查診斷腳本
檢查所有必要的依賴和系統配置
"""

import sys
import os
from pathlib import Path


def print_header(text):
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}")


def check_module(module_name, package_name=None):
    """檢查模塊是否可導入"""
    if package_name is None:
        package_name = module_name
    try:
        __import__(module_name)
        print(f"✓ {package_name:<40} - OK")
        return True
    except ImportError as e:
        print(f"✗ {package_name:<40} - FAILED: {e}")
        return False


def check_pil_detailed():
    """詳細檢查 PIL/Pillow"""
    print("\n--- PIL/Pillow 詳細檢查 ---")
    try:
        import PIL
        print(f"✓ Pillow 版本: {PIL.__version__}")
        
        # 檢查是否可以導入 Image
        try:
            from PIL import Image
            print("✓ PIL.Image 導入成功")
            
            # 嘗試載入 _imaging
            try:
                from PIL import _imaging
                print("✓ PIL._imaging (C 擴展) 載入成功")
                return True
            except ImportError as e:
                print(f"✗ PIL._imaging 導入失敗: {e}")
                print("  建議: pip install --upgrade Pillow")
                return False
        except ImportError as e:
            print(f"✗ PIL.Image 導入失敗: {e}")
            return False
    except ImportError:
        print("✗ Pillow 未安裝")
        print("  建議: pip install Pillow>=10.0.0")
        return False


def check_pytorch():
    """檢查 PyTorch 和 CUDA"""
    print("\n--- PyTorch 配置 ---")
    try:
        import torch
        print(f"✓ PyTorch 版本: {torch.__version__}")
        
        cuda_available = torch.cuda.is_available()
        if cuda_available:
            print(f"✓ CUDA 可用")
            print(f"  - CUDA 版本: {torch.version.cuda}")
            print(f"  - GPU 數量: {torch.cuda.device_count()}")
            for i in range(torch.cuda.device_count()):
                print(f"    GPU {i}: {torch.cuda.get_device_name(i)}")
        else:
            print("⚠ CUDA 不可用 - 將使用 CPU (性能較低)")
        return True
    except ImportError:
        print("✗ PyTorch 未安裝")
        print("  建議: pip install torch>=2.0.0")
        return False


def check_model_dir():
    """檢查模型目錄"""
    print("\n--- 模型目錄檢查 ---")
    model_dir = Path("./models/Llama-3.2-11B-Vision-Instruct")
    
    if model_dir.exists():
        print(f"✓ 模型目錄存在: {model_dir.absolute()}")
        
        # 列出目錄內容
        try:
            files = list(model_dir.iterdir())
            print(f"  包含 {len(files)} 個文件/目錄:")
            for f in sorted(files)[:5]:
                print(f"    - {f.name}")
            if len(files) > 5:
                print(f"    ... 以及 {len(files) - 5} 個其他文件")
        except Exception as e:
            print(f"  無法列出目錄: {e}")
        return True
    else:
        print(f"✗ 模型目錄不存在: {model_dir.absolute()}")
        print("  建議: 下載 Llama 模型到 ./models/ 目錄")
        return False


def check_api_key():
    """檢查 API 金鑰檔案"""
    print("\n--- API 金鑰檢查 ---")
    api_file = Path("./api_key.txt")
    
    if api_file.exists():
        try:
            with open(api_file, 'r') as f:
                content = f.read().strip()
            if content:
                print(f"✓ api_key.txt 存在且包含內容")
                print(f"  金鑰長度: {len(content)} 字符")
            else:
                print("✗ api_key.txt 為空")
                return False
        except Exception as e:
            print(f"✗ 無法讀取 api_key.txt: {e}")
            return False
    else:
        print("⚠ api_key.txt 不存在")
        print("  建議: 創建 api_key.txt 並填入 Google API 金鑰")
        print("  (如果您不使用 Google Generative AI，可以忽略此警告)")
    return True


def main():
    print_header("環境檢查診斷工具")
    print(f"Python 版本: {sys.version}")
    print(f"執行位置: {os.getcwd()}")
    
    print_header("核心依賴檢查")
    
    modules = [
        ("torch", "PyTorch"),
        ("transformers", "Hugging Face Transformers"),
        ("cv2", "OpenCV"),
        ("langchain_core", "LangChain"),
        ("langchain_chroma", "LangChain Chroma"),
        ("google.generativeai", "Google Generative AI"),
    ]
    
    results = {}
    for module, name in modules:
        results[module] = check_module(module, name)
    
    print_header("進階檢查")
    
    # PIL 詳細檢查
    pil_ok = check_pil_detailed()
    results['PIL'] = pil_ok
    
    # PyTorch 詳細檢查
    torch_ok = check_pytorch()
    results['torch_detailed'] = torch_ok
    
    # 模型目錄檢查
    model_ok = check_model_dir()
    results['model_dir'] = model_ok
    
    # API 金鑰檢查
    api_ok = check_api_key()
    results['api_key'] = api_ok
    
    print_header("摘要")
    
    essential = results.get('torch') and results.get('transformers') and results.get('PIL')
    
    if essential:
        print("✓ 所有必要的依賴已安裝")
    else:
        print("✗ 缺少必要的依賴")
        print("\n建議的修復方案:")
        if not results.get('torch'):
            print("  1. pip install torch>=2.0.0")
        if not results.get('transformers'):
            print("  2. pip install transformers>=4.30.0")
        if not results.get('PIL'):
            print("  3. pip install --upgrade Pillow")
    
    if model_ok:
        print("✓ 模型文件已準備")
    else:
        print("✗ 需要下載模型文件")
    
    if api_ok:
        print("✓ API 配置已就位")
    else:
        print("⚠ API 配置需要檢查")
    
    print("\n" + "=" * 60)
    print("檢查完成！")
    print("=" * 60)
    
    return 0 if essential else 1


if __name__ == "__main__":
    sys.exit(main())
