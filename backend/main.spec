# main.spec — đóng gói backend Meeting-App bằng PyInstaller (onedir)
# Chạy: python -m PyInstaller main.spec
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []

# Gom trọn các package có binary/dữ liệu native (đây là chỗ hay thiếu DLL)
for pkg in ["ctranslate2", "sherpa_onnx", "onnxruntime",
            "sentencepiece", "transformers", "tokenizers"]:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as e:
        print(f"[spec] Bỏ qua {pkg}: {e}")

# uvicorn/fastapi nạp động nhiều submodule -> khai báo tay cho chắc
hiddenimports += [
    "uvicorn", "fastapi",
    "uvicorn.logging",
    "uvicorn.loops", "uvicorn.loops.auto",
    "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan", "uvicorn.lifespan.on",
    "websockets", "websockets.legacy", "websockets.legacy.server",
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Không dùng mấy cái này -> loại cho gói nhẹ và build nhanh
    excludes=["torch", "torchvision", "torchaudio", "tensorflow", "flax", "jax"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="main",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # tắt UPX cho khỏi hỏng DLL native
    console=True,       # để THẤY log/lỗi; khi chạy ổn đổi thành False cho gọn
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="main",        # -> output ở dist/main/
)
