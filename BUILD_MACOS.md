# Build KaTOBA trên macOS (Apple Silicon)

Ghi lại vì quy trình macOS **khác hẳn** Windows và là nguồn gốc của lỗi
"app mở được nhưng backend không khởi chạy".

## Nguyên tắc quan trọng nhất

> **PyInstaller không cross-compile.** `backend/dist/main/main.exe` build trên
> Windows hoàn toàn vô dụng trên macOS. Phải build lại backend **trên chính
> máy Mac**, bằng Python arm64.

`electron-builder.yml` chép nguyên `../backend/dist/main` vào
`KaTOBA.app/Contents/Resources/backend`. Thư mục đó không có, hoặc chứa binary
sai kiến trúc, thì app vẫn mở bình thường — chỉ backend là không lên.

## Bước 1 — Kiểm tra kiến trúc Python

```bash
uname -m                      # phải ra: arm64
python3 -c "import platform; print(platform.machine())"   # phải ra: arm64
```

Nếu Python in ra `x86_64` là bạn đang chạy qua Rosetta. Gỡ và cài lại Python
arm64 (`brew install python@3.12`), nếu không `sherpa-onnx` / `ctranslate2` sẽ
kéo về wheel Intel và binary sinh ra bị macOS chặn hoặc chạy cực chậm.

## Bước 2 — Dựng môi trường Python

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller
```

## Bước 3 — Đặt model vào đúng chỗ

`main.spec` **không** đóng gói `models/` (vài GB, cố tình để ngoài). Backend gọi
`_check_files()` và thoát ngay bằng `_fatal()` nếu thiếu — đây là lý do phổ
biến nhất khiến backend "không khởi chạy".

Cấu trúc bắt buộc:

```text
backend/models/
├── parakeet-ja/       (model.int8.onnx, tokens.txt)
├── zipformer-vi/      (encoder.int8.onnx, decoder.onnx, joiner.int8.onnx, tokens.txt)
├── m2m100_418M_int8/
└── silero_vad.onnx
```

Kiểm tra trước khi build:

```bash
python main.py        # phải thấy "Backend sẵn sàng", Ctrl-C để thoát
```

Không chạy nổi ở bước này thì đóng gói cũng vô ích.

## Bước 4 — Build backend

```bash
cd backend
source venv/bin/activate
python -m PyInstaller main.spec
```

Kết quả: `backend/dist/main/main` + `backend/dist/main/_internal/`.

Chép model và glossary vào cạnh binary (PyInstaller không tự làm):

```bash
cp -R models dist/main/models
cp glossary.json dist/main/
cp people.json dist/main/      # danh sách người dự — xem TEN_NGUOI_VA_NGAT_CAU.md
```

Chạy thử **bản đã đóng gói**, tách hẳn khỏi Electron:

```bash
cd dist/main && ./main
```

Đây là bài kiểm tra quyết định. Backend chạy được ở đây mà vẫn chết trong app
thì lỗi nằm ở chữ ký / quarantine (xem phần Sự cố bên dưới).

## Bước 5 — Build app

```bash
cd frontend
npm install
npm run build:mac
```

Kết quả trong `frontend/dist/`: `mac-arm64/KaTOBA.app` và file `.dmg`.

Hook `build/afterPack.js` tự trả bit `+x` cho backend và gỡ
`com.apple.quarantine` trước bước ký.

## Bước 6 — Cài lên máy đích

Máy không có Apple Developer ID nên bản build chỉ ký ad-hoc. Sau khi chép
`.app` sang máy khác, **bắt buộc** gỡ cờ quarantine:

```bash
xattr -cr /Applications/KaTOBA.app
```

Bỏ qua bước này thì Gatekeeper giết tiến trình backend lồng bên trong bundle
bằng SIGKILL, không để lại một dòng log nào.

---

## Sự cố: app mở được nhưng backend không lên

Từ bản này app đã tự hiện hộp thoại kèm nguyên nhân. Nếu cần đào sâu:

```bash
# Xem log main process (mở app từ Terminal)
/Applications/KaTOBA.app/Contents/MacOS/KaTOBA

# Log tử vong của Python — nay nằm ở thư mục userData, KHÔNG còn trong bundle
cat ~/Library/Application\ Support/KaTOBA/startup_error.log

# Chạy thẳng backend
cd /Applications/KaTOBA.app/Contents/Resources/backend && ./main

# Vì sao macOS giết tiến trình
log show --last 5m --predicate 'senderImagePath CONTAINS "backend"'
```

| Triệu chứng | Nguyên nhân | Cách sửa |
|---|---|---|
| `spawn EACCES` | Mất bit `+x` (backend đi qua zip / ổ NTFS / máy Windows) | `chmod -R +x .../Resources/backend` |
| Chết ngay, `signal=SIGKILL`, không output | Quarantine hoặc chữ ký hỏng | `xattr -cr KaTOBA.app` rồi `codesign --force --deep --sign - KaTOBA.app` |
| `Library not loaded` / `code signature invalid` | Hardened runtime bật mà không có Developer ID | Giữ `hardenedRuntime: false` trong `electron-builder.yml` |
| `❌ Thiếu model:` | Quên chép `models/` vào `dist/main/` | Làm lại Bước 3–4 |
| `Bad CPU type` / `mach-o file, but is an incompatible architecture` | Backend build bằng Python x86_64 hoặc lấy từ Windows | Làm lại Bước 1–4 trên Mac arm64 |
| Chạy `./main` thì được, trong app thì không | Chữ ký / quarantine | Như dòng SIGKILL ở trên |

## Khi có Apple Developer ID

Sửa `frontend/electron-builder.yml`:

```yaml
mac:
  hardenedRuntime: true
  notarize: true
```

`build/entitlements.mac.plist` đã khai sẵn `disable-library-validation`,
`allow-jit` và `allow-unsigned-executable-memory` — đủ để binary PyInstaller
nạp dylib từ `_internal/` và để ctranslate2/onnxruntime sinh mã JIT dưới
hardened runtime.
