# Build KaTOBA trên Windows

Đã build và chạy thử thành công ngày 01/10/2026 với MT v9: PyInstaller 6.21, Node 22, Electron 39.

Kết quả là **thư mục portable** `frontend/dist/win-unpacked/` (khoảng 2,3 GB), chạy luôn bằng `KaTOBA.exe`, không cần cài đặt.
Cấu hình trong `electron-builder.yml` là `target: dir`; muốn có bộ cài thì dùng Inno Setup đóng gói thư mục này.

## Điều kiện

- `backend/venv` đã cài `requirements.txt` và `pyinstaller`
- `frontend/node_modules` đã cài (`npm install`)
- Đủ model trong `backend/models/`:

```text
backend/models/
├── parakeet-ja/        (model.int8.onnx, tokens.txt)
├── parakeet-en/        (không bắt buộc — thiếu thì tắt chiều en)
├── zipformer-vi/       (encoder.int8.onnx, decoder.onnx, joiner.int8.onnx, tokens.txt)
├── m2m100_418M_int8/   (model dịch đang dùng — hiện là v9)
└── silero_vad.onnx
```

## Bước 1 — Kiểm tra backend từ source

PowerShell, trong `backend/`:

```powershell
.\venv\Scripts\Activate.ps1
python test_postprocess.py          # phải ra: 0 lỗi
python main.py                      # phải thấy "(MT v9)" và "Nạp xong", Ctrl+C để thoát
```

Bước này không chạy được thì đóng gói cũng vô ích.

## Bước 2 — Build backend

```powershell
python -m PyInstaller main.spec --noconfirm
```

Lệnh tạo ra `backend\dist\main\main.exe` và `_internal\` (khoảng 1,5 phút, 243 MB).

`main.spec` **không** gom model (cố ý), nên phải chép tay vào cạnh `main.exe`:

```powershell
Copy-Item -Recurse -Force models dist\main\models
Copy-Item -Force glossary.json, people.json dist\main\
```

Chạy thử bản exe, tách hẳn khỏi Electron:

```powershell
cd dist\main; .\main.exe
# trình duyệt khác: http://127.0.0.1:8765/v1/health  -> "mt_version":"v9"
```

Nhớ tắt `main.exe` (Ctrl+C) trước bước sau, nếu không app sẽ trùng cổng 8765.

## Bước 3 — Build app

PowerShell, trong `frontend/`:

```powershell
npm run build:win
```

electron-builder chép nguyên `backend\dist\main` vào `dist\win-unpacked\resources\backend\`.

## Bước 4 — Chạy

Bấm đúp `frontend\dist\win-unpacked\KaTOBA.exe`. App tự khởi động backend, mất khoảng 5 giây để nạp model, dùng khoảng 2,2 GB RAM.
Tắt app thì backend cũng tắt theo.

Muốn chép sang máy khác thì chép **cả thư mục** `win-unpacked`, không chép riêng file exe.

## Bước 5 — Đóng gói thành 1 file cài đặt

Cần Inno Setup 6 (`C:\Program Files (x86)\Inno Setup 6\`). Ở thư mục gốc dự án:

```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
```

Lệnh tạo `Output\KaTOBA-Setup.exe`, gói đủ frontend, backend và model. Bước nén mất khoảng 8,5 phút.
Phải chạy Bước 3 trước, vì `installer.iss` lấy nguyên thư mục `frontend\dist\win-unpacked`.

| | Dung lượng |
|---|---|
| File cài đặt `KaTOBA-Setup.exe` | **1,58 GB** |
| Sau khi cài | **2,3 GB** (model 1,77 GB, Electron ~330 MB, Python backend 210 MB) |
| RAM khi chạy | ~2,2 GB |

Cài mặc định cho người dùng hiện tại, không cần quyền admin, vào `%LOCALAPPDATA%\Programs\KaTOBA`, mất khoảng 2,5 phút.
Cài im lặng: `KaTOBA-Setup.exe /VERYSILENT /CURRENTUSER`.

## Chỉ đổi model dịch (không sửa code)

Không cần build lại gì cả. Thay thư mục model trong bản đã build:

```text
frontend\dist\win-unpacked\resources\backend\models\m2m100_418M_int8\
```

Sửa code Python thì làm lại Bước 2 và 3.

## Sự cố

| Triệu chứng | Nguyên nhân | Cách sửa |
|---|---|---|
| Mở `KaTOBA.exe` từ terminal của VS Code thì app tắt ngay, hoặc báo `bad option` | Terminal VS Code đặt `ELECTRON_RUN_AS_NODE=1`, làm Electron chạy như Node | Bấm đúp từ Explorer, hoặc chạy `Remove-Item Env:ELECTRON_RUN_AS_NODE` trước khi mở |
| App mở nhưng báo không thấy backend | Thiếu `backend\dist\main` lúc chạy `build:win` | Làm Bước 2 trước Bước 3 |
| Backend chết, báo `❌ Thiếu model:` | Quên chép `models\` vào `dist\main\` | Làm lại phần chép model ở Bước 2, rồi Bước 3 |
| Cổng 8765 bị chiếm | Còn `python main.py` hoặc `main.exe` đang chạy | Tắt tiến trình đó |
| Cần xem log lỗi khởi động | | `%APPDATA%\frontend\startup_error.log` (tên thư mục lấy từ `"name"` trong `frontend/package.json`) |
