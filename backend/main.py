from datetime import datetime
from pathlib import Path
from threading import Lock

from deep_translator import GoogleTranslator
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

import asyncio
import numpy as np
import sherpa_onnx
import uvicorn


app = FastAPI()

# ============================================================
# ĐƯỜNG DẪN
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

MODEL_DIR = (
    BASE_DIR
    / "models"
    / "parakeet-ja"
)

MODEL_FILE = MODEL_DIR / "model.int8.onnx"
TOKENS_FILE = MODEL_DIR / "tokens.txt"

LOG_FILE = BASE_DIR / "transcript_log.txt"


# ============================================================
# CẤU HÌNH ÂM THANH
# ============================================================

SAMPLE_RATE = 16000

# Ngưỡng âm lượng để xem là có tiếng nói
SILENCE_THRESHOLD = 0.008

# Im lặng bao lâu thì xem là kết thúc một câu
SILENCE_WAIT = 0.4

# Bỏ những đoạn quá ngắn
MIN_RECORD_TIME = 0.35

# Tối đa 5 giây thì bắt buộc xử lý
MAX_RECORD_TIME = 5.0


# ============================================================
# KIỂM TRA FILE MODEL
# ============================================================

if not MODEL_FILE.exists():
    raise FileNotFoundError(
        f"Không tìm thấy model:\n{MODEL_FILE}\n\n"
        "Hãy kiểm tra lại thư mục models/parakeet-ja."
    )

if not TOKENS_FILE.exists():
    raise FileNotFoundError(
        f"Không tìm thấy tokens.txt:\n{TOKENS_FILE}\n\n"
        "Hãy kiểm tra lại thư mục models/parakeet-ja."
    )


# ============================================================
# NẠP MODEL PARAKEET JAPANESE
# ============================================================

print("⏳ Đang nạp model Parakeet Japanese...")
print(f"📁 Model: {MODEL_FILE}")
print(f"📁 Tokens: {TOKENS_FILE}")
print(f"📁 File log: {LOG_FILE}")

recognizer = sherpa_onnx.OfflineRecognizer.from_nemo_ctc(
    model=str(MODEL_FILE),
    tokens=str(TOKENS_FILE),
    num_threads=4,
    sample_rate=SAMPLE_RATE,
    feature_dim=80,
    decoding_method="greedy_search",
    provider="cpu",
)

# Tránh nhiều luồng cùng truy cập recognizer một lúc
recognizer_lock = Lock()

print("✅ Đã nạp xong model Parakeet Japanese")


# ============================================================
# XỬ LÝ VĂN BẢN
# ============================================================

def split_japanese_sentences(text: str) -> list[str]:
    """
    Tách kết quả nhận dạng thành từng câu tiếng Nhật.
    Hỗ trợ cả dấu câu Nhật và dấu câu ASCII.
    """

    formatted = (
        text.replace("。", "。\n")
        .replace("？", "？\n")
        .replace("！", "！\n")
        .replace("?", "?\n")
        .replace("!", "!\n")
    )

    return [
        sentence.strip()
        for sentence in formatted.splitlines()
        if sentence.strip()
    ]


def write_log(text_ja: str, text_vi: str) -> None:
    """
    Ghi tiếng Nhật và tiếng Việt vào file log.
    """

    current_time = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    log_content = (
        f"[{current_time}]\n"
        f"JA: {text_ja}\n"
        f"VI: {text_vi}\n"
        f"{'-' * 50}\n"
    )

    with LOG_FILE.open(
        "a",
        encoding="utf-8",
        buffering=1,
    ) as log_file:
        log_file.write(log_content)
        log_file.flush()


# ============================================================
# NHẬN DẠNG TIẾNG NHẬT
# ============================================================

def recognize_japanese(samples: np.ndarray) -> str:
    """
    Chuyển audio thành văn bản tiếng Nhật bằng Parakeet.
    Hàm này chạy đồng bộ nên sẽ được gọi trong thread riêng.
    """

    if samples.size == 0:
        return ""

    samples = np.ascontiguousarray(
        samples,
        dtype=np.float32,
    )

    # Không để hai request decode model cùng lúc
    with recognizer_lock:
        stream = recognizer.create_stream()

        stream.accept_waveform(
            SAMPLE_RATE,
            samples,
        )

        recognizer.decode_stream(stream)

        result = stream.result.text

    return result.strip() if result else ""


async def recognize_japanese_async(
    samples: np.ndarray,
) -> str:
    """
    Chạy nhận dạng trong thread riêng để không khóa WebSocket.
    """

    try:
        return await asyncio.to_thread(
            recognize_japanese,
            samples,
        )

    except Exception as error:
        print(f"❌ Lỗi nhận dạng tiếng Nhật: {error}")
        return ""


# ============================================================
# DỊCH TIẾNG NHẬT SANG TIẾNG VIỆT
# ============================================================

async def translate_to_vietnamese(
    translator: GoogleTranslator,
    japanese_text: str,
) -> str:
    """
    Dịch tiếng Nhật sang tiếng Việt trong thread riêng.
    """

    if not japanese_text.strip():
        return ""

    try:
        result = await asyncio.to_thread(
            translator.translate,
            japanese_text,
        )

        if not result:
            return "(Không có bản dịch)"

        return result.strip()

    except Exception as error:
        print(f"❌ Lỗi dịch: {error}")
        return "(Không thể dịch sang tiếng Việt)"


# ============================================================
# WEBSOCKET NHẬN AUDIO
# ============================================================

@app.websocket("/ws/audio")
async def websocket_endpoint(
    websocket: WebSocket,
) -> None:
    await websocket.accept()

    print("🔌 Electron đã kết nối")

    audio_buffer: list[np.ndarray] = []

    total_samples = 0
    silence_duration = 0.0
    has_voice = False

    translator = GoogleTranslator(
        source="ja",
        target="vi",
    )

    try:
        while True:
            data = await websocket.receive_bytes()

            chunk = (
                np.frombuffer(
                    data,
                    dtype=np.int16,
                )
                .astype(np.float32)
                / 32768.0
            )

            if chunk.size == 0:
                continue

            chunk_duration = (
                chunk.size / SAMPLE_RATE
            )

            volume = float(
                np.max(np.abs(chunk))
            )

            # Lưu từng chunk thay vì chuyển thành list float
            audio_buffer.append(chunk.copy())
            total_samples += chunk.size

            if volume >= SILENCE_THRESHOLD:
                has_voice = True
                silence_duration = 0.0

            elif has_voice:
                silence_duration += chunk_duration

            total_duration = (
                total_samples / SAMPLE_RATE
            )

            should_process = (
                has_voice
                and total_duration >= MIN_RECORD_TIME
                and (
                    silence_duration >= SILENCE_WAIT
                    or total_duration >= MAX_RECORD_TIME
                )
            )

            if not should_process:
                # Nếu chỉ có im lặng thì xóa buffer sau 1 giây
                if (
                    not has_voice
                    and total_duration >= 1.0
                ):
                    audio_buffer.clear()
                    total_samples = 0

                continue

            # Ghép các chunk thành một mảng audio
            full_audio = np.concatenate(
                audio_buffer
            ).astype(
                np.float32,
                copy=False,
            )

            # Cắt bớt tối đa 0.25 giây im lặng cuối câu
            trailing_silence_samples = int(
                min(
                    silence_duration,
                    0.25,
                )
                * SAMPLE_RATE
            )

            if (
                trailing_silence_samples > 0
                and full_audio.size
                > trailing_silence_samples
            ):
                samples = full_audio[
                    :-trailing_silence_samples
                ]
            else:
                samples = full_audio

            # Reset sớm để nhận câu tiếp theo
            audio_buffer.clear()
            total_samples = 0
            silence_duration = 0.0
            has_voice = False

            minimum_samples = int(
                MIN_RECORD_TIME * SAMPLE_RATE
            )

            if samples.size < minimum_samples:
                continue

            print(
                "🎧 Đang nhận dạng "
                f"{samples.size / SAMPLE_RATE:.2f} giây audio..."
            )

            text_ja = await recognize_japanese_async(
                samples
            )

            if not text_ja:
                print("⚠️ Model không nhận dạng được nội dung")
                continue

            sentences = split_japanese_sentences(
                text_ja
            )

            if not sentences:
                continue

            for sentence_ja in sentences:
                text_vi = await translate_to_vietnamese(
                    translator,
                    sentence_ja,
                )

                write_log(
                    sentence_ja,
                    text_vi,
                )

                print(f"🇯🇵 {sentence_ja}")
                print(f"🇻🇳 {text_vi}")
                print(f"✅ Đã ghi log: {LOG_FILE}")

                # Frontend hiện tại chỉ nhận tiếng Việt
                await websocket.send_text(
                    text_vi
                )

    except WebSocketDisconnect:
        print("❌ Electron đã ngắt kết nối")

    except Exception as error:
        print(f"❌ Lỗi WebSocket: {error}")

        try:
            await websocket.close()
        except Exception:
            pass


# ============================================================
# CHẠY SERVER
# ============================================================

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )