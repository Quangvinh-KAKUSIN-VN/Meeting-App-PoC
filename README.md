# Meeting App PoC

Ứng dụng Electron hỗ trợ nhận dạng giọng nói tiếng Nhật và hiển thị bản dịch tiếng Việt theo thời gian thực.

## Chức năng hiện tại

- Nhận âm thanh đang phát trong máy tính.
- Nhận âm thanh từ microphone.
- Nhận âm thanh phát từ loa ngoài thông qua microphone.
- Chuyển âm thanh tiếng Nhật thành văn bản tiếng Nhật.
- Dịch văn bản tiếng Nhật sang tiếng Việt.
- Hiển thị phụ đề tiếng Việt bằng Electron.
- Ghi lại tiếng Nhật và tiếng Việt trong file log.

## Công nghệ

### Frontend

- Electron
- Electron Vite
- Vue 3
- WebSocket
- Web Audio API

### Backend

- Python
- FastAPI
- sherpa-onnx
- Parakeet Japanese ASR
- NumPy
- deep-translator

## Cấu trúc dự án

```text
Meeting-App-PoC/
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   └── models/
│       └── parakeet-ja/
│           ├── model.int8.onnx
│           └── tokens.txt
│
└── frontend/
    ├── package.json
    └── src/
        ├── main/
        ├── preload/
        └── renderer/
```

## Model tiếng Nhật

Model không được lưu trong repository do dung lượng lớn.

Tên model:

```text
sherpa-onnx-nemo-parakeet-tdt_ctc-0.6b-ja-35000-int8
```

Sau khi tải và giải nén, đặt các file tại:

```text
backend/models/parakeet-ja/model.int8.onnx
backend/models/parakeet-ja/tokens.txt
```

Cấu trúc bắt buộc:

```text
backend/
└── models/
    └── parakeet-ja/
        ├── model.int8.onnx
        └── tokens.txt
```

## Cài đặt backend trên Windows

Mở PowerShell tại thư mục dự án:

```powershell
cd backend
```

Tạo môi trường Python:

```powershell
python -m venv venv
```

Kích hoạt môi trường:

```powershell
.\venv\Scripts\Activate.ps1
```

Cài thư viện:

```powershell
python -m pip install -r requirements.txt
```

Chạy backend:

```powershell
python main.py
```

Backend chạy tại:

```text
ws://127.0.0.1:8000/ws/audio
```

## Cài đặt frontend

Mở một PowerShell khác:

```powershell
cd frontend
```

Cài thư viện:

```powershell
npm install
```

Chạy Electron:

```powershell
npm run dev
```

## Cách sử dụng

1. Chạy backend Python.
2. Chạy frontend Electron.
3. Chọn một nguồn âm thanh:
   - Âm thanh máy tính.
   - Microphone.
4. Bấm nút bắt đầu dịch.
5. Phát hoặc nói tiếng Nhật.
6. Phụ đề tiếng Việt sẽ được hiển thị trên cửa sổ Electron.

## Lưu ý

- Model ASR chạy cục bộ trên máy.
- Phần dịch hiện sử dụng `GoogleTranslator` và cần kết nối Internet.
- Không commit model, file âm thanh, file log, `venv` hoặc `node_modules`.