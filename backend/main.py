import asyncio
from datetime import datetime
from pathlib import Path
from threading import Lock

import ctranslate2
import numpy as np
import sherpa_onnx
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from transformers import AutoTokenizer

app = FastAPI()

# ============================================================
# CẤU HÌNH ĐƯỜNG DẪN TỚI MODEL
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = BASE_DIR / "models"

# 1. Parakeet-JA (STT tiếng Nhật)
MODEL_JA_DIR = MODELS_DIR / "parakeet-ja"
MODEL_JA_FILE = MODEL_JA_DIR / "model.int8.onnx"
TOKENS_JA_FILE = MODEL_JA_DIR / "tokens.txt"

# 2. Zipformer-VI (STT tiếng Việt) — transducer
MODEL_VI_DIR = MODELS_DIR / "zipformer-vi"
VI_ENCODER = MODEL_VI_DIR / "encoder.int8.onnx"
VI_DECODER = MODEL_VI_DIR / "decoder.onnx"
VI_JOINER = MODEL_VI_DIR / "joiner.int8.onnx"
VI_TOKENS = MODEL_VI_DIR / "tokens.txt"

# 3. M2M-100 (Dịch) - bản CTranslate2 INT8
M2M100_DIR = MODELS_DIR / "m2m100_1.2B_int8"

# 4. Silero VAD
SILERO_VAD_FILE = MODELS_DIR / "silero_vad.onnx"

LOG_FILE = BASE_DIR / "transcript_log.txt"

# ============================================================
# CẤU HÌNH ÂM THANH / VAD
# ============================================================
SAMPLE_RATE = 16000
# Các mốc thời gian giờ do Silero VAD quản, không cắt câu thủ công bằng biên độ nữa
VAD_MIN_SILENCE = 0.4    # im lặng >= mốc này thì chốt câu (hạ xuống 0.25 nếu muốn cắt gắt hơn)
VAD_MIN_SPEECH = 0.35    # đoạn ngắn hơn mốc này coi như nhiễu, bỏ
VAD_MAX_SPEECH = 5.0     # đoạn dài hơn mốc này bị cắt cưỡng bức

# ============================================================
# KIỂM TRA FILE MODEL
# ============================================================
if not MODEL_JA_FILE.exists() or not TOKENS_JA_FILE.exists():
    raise FileNotFoundError(f"⚠️ Thiếu model Parakeet-JA tại: {MODEL_JA_DIR}")

if not (VI_ENCODER.exists() and VI_DECODER.exists() and VI_JOINER.exists() and VI_TOKENS.exists()):
    raise FileNotFoundError(f"⚠️ Thiếu model Zipformer-VI tại: {MODEL_VI_DIR}")

if not M2M100_DIR.exists():
    raise FileNotFoundError(f"⚠️ Thiếu model M2M-100 tại: {M2M100_DIR}")

if not SILERO_VAD_FILE.exists():
    raise FileNotFoundError(f"⚠️ Thiếu Silero VAD tại: {SILERO_VAD_FILE}")

# ============================================================
# KHỞI TẠO CÁC MODEL AI
# ============================================================

print("⏳ Đang nạp model Parakeet Japanese (STT-JA)...")
recognizer_ja = sherpa_onnx.OfflineRecognizer.from_nemo_ctc(
    model=str(MODEL_JA_FILE),
    tokens=str(TOKENS_JA_FILE),
    num_threads=4,
    sample_rate=SAMPLE_RATE,
    feature_dim=80,
    decoding_method="greedy_search",
    provider="cpu",
)
recognizer_ja_lock = Lock()
print("✅ Nạp xong Parakeet Japanese!")

print("⏳ Đang nạp model Zipformer Vietnamese (STT-VI)...")
# LƯU Ý: dùng OfflineRecognizer (khớp luồng: VAD cắt xong câu -> nhận diện cả câu).
# Nếu bản zipformer-vi của bạn là model STREAMING, dòng này sẽ báo lỗi lúc load —
# khi đó đổi sang sherpa_onnx.OnlineRecognizer.from_transducer(...) với cùng bộ file.
recognizer_vi = sherpa_onnx.OfflineRecognizer.from_transducer(
    encoder=str(VI_ENCODER),
    decoder=str(VI_DECODER),
    joiner=str(VI_JOINER),
    tokens=str(VI_TOKENS),
    num_threads=4,
    sample_rate=SAMPLE_RATE,
    feature_dim=80,
    decoding_method="greedy_search",
    provider="cpu",
)
recognizer_vi_lock = Lock()
print("✅ Nạp xong Zipformer Vietnamese!")

print("⏳ Đang nạp model Dịch M2M-100 1.2B (CTranslate2 INT8)...")
translator = ctranslate2.Translator(str(M2M100_DIR), device="cpu", compute_type="int8")

# ---- FIX #1: nạp tokenizer TỪ LOCAL để app chạy offline ----
# Lần đầu (còn mạng) sẽ tải từ HF rồi tự lưu vào thư mục model; các lần sau nạp offline.
# Sau lần chạy đầu, thư mục m2m100_1.2B_int8 sẽ có thêm file tokenizer -> ship kèm app là xong.
try:
    tokenizer = AutoTokenizer.from_pretrained(str(M2M100_DIR))
    print("   (tokenizer nạp từ local)")
except Exception:
    print("   (chưa có tokenizer local, tải từ HuggingFace rồi lưu lại...)")
    tokenizer = AutoTokenizer.from_pretrained("facebook/m2m100_1.2B")
    tokenizer.save_pretrained(str(M2M100_DIR))
translator_lock = Lock()
print("✅ Nạp xong model Dịch M2M-100!")


# ============================================================
# HÀM BỔ TRỢ & GHI LOG
# ============================================================
def split_sentences(text: str, lang: str) -> list[str]:
    if lang == "ja":
        formatted = (
            text.replace("。", "。\n")
            .replace("？", "？\n")
            .replace("！", "！\n")
            .replace("?", "?\n")
            .replace("!", "!\n")
        )
        return [s.strip() for s in formatted.splitlines() if s.strip()]
    # Với tiếng Việt, VAD đã cắt theo câu nói nên không tách thêm (tránh cắt nhầm ở dấu chấm viết tắt)
    return [text.strip()] if text.strip() else []


def write_log(text_src: str, text_dst: str, src_lang: str, dst_lang: str) -> None:
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_content = (
        f"[{current_time}]\n{src_lang.upper()}: {text_src}\n"
        f"{dst_lang.upper()}: {text_dst}\n{'-' * 50}\n"
    )
    with LOG_FILE.open("a", encoding="utf-8", buffering=1) as log_file:
        log_file.write(log_content)
        log_file.flush()


# ============================================================
# NHẬN DIỆN & DỊCH (chạy local)
# ============================================================
def recognize(recognizer, lock: Lock, samples: np.ndarray) -> str:
    samples = np.ascontiguousarray(samples, dtype=np.float32)
    with lock:
        stream = recognizer.create_stream()
        stream.accept_waveform(SAMPLE_RATE, samples)
        recognizer.decode_stream(stream)
        return stream.result.text.strip()


def translate(text: str, src_lang: str, tgt_lang: str) -> str:
    """Dịch M2M-100 theo chuẩn CTranslate2. src_lang/tgt_lang dùng mã 2 ký tự: 'vi', 'ja'."""
    if not text:
        return ""
    try:
        with translator_lock:
            tokenizer.src_lang = src_lang
            source_tokens = tokenizer.convert_ids_to_tokens(tokenizer.encode(text))
            target_prefix = [tokenizer.lang_code_to_token[tgt_lang]]

            results = translator.translate_batch(
                [source_tokens],
                target_prefix=[target_prefix],
                max_decoding_length=128,
            )

            target_tokens = results[0].hypotheses[0][1:]  # bỏ token ngôn ngữ đích ở đầu
            # ---- FIX #2: skip_special_tokens=True để không lẫn </s> vào bản dịch ----
            text_out = tokenizer.decode(
                tokenizer.convert_tokens_to_ids(target_tokens),
                skip_special_tokens=True,
            )
            return text_out.strip()
    except Exception as e:
        print(f"❌ Lỗi dịch M2M-100: {e}")
        return "(Lỗi dịch)"


# ============================================================
# LUỒNG WEBSOCKET DÙNG CHUNG CHO CẢ 2 CHIỀU (FIX #3)
# ============================================================
async def handle_stream(
    websocket: WebSocket,
    recognizer,
    recognizer_lock: Lock,
    src_lang: str,
    tgt_lang: str,
) -> None:
    await websocket.accept()
    print(f"🔌 Electron kết nối — chiều {src_lang.upper()}→{tgt_lang.upper()}")

    # ---- FIX #3: mỗi kết nối có 1 Silero VAD RIÊNG (VAD có trạng thái, không được share) ----
    vad_config = sherpa_onnx.VadModelConfig()
    vad_config.silero_vad.model = str(SILERO_VAD_FILE)
    vad_config.silero_vad.threshold = 0.5
    vad_config.silero_vad.min_silence_duration = VAD_MIN_SILENCE
    vad_config.silero_vad.min_speech_duration = VAD_MIN_SPEECH
    vad_config.silero_vad.max_speech_duration = VAD_MAX_SPEECH
    vad_config.sample_rate = SAMPLE_RATE
    window_size = vad_config.silero_vad.window_size
    vad = sherpa_onnx.VoiceActivityDetector(vad_config, buffer_size_in_seconds=30)

    pending = np.zeros(0, dtype=np.float32)  # gom mẫu chờ đủ 1 window để nạp cho VAD

    try:
        while True:
            data = await websocket.receive_bytes()
            chunk = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
            if chunk.size == 0:
                continue

            # Nạp âm thanh vào VAD theo từng window cố định
            pending = np.concatenate([pending, chunk])
            while pending.size >= window_size:
                vad.accept_waveform(np.ascontiguousarray(pending[:window_size]))
                pending = pending[window_size:]

            # Lấy ra các đoạn nói mà VAD đã chốt
            while not vad.empty():
                segment = vad.front
                samples = np.ascontiguousarray(np.array(segment.samples, dtype=np.float32))
                vad.pop()

                text_src = await asyncio.to_thread(
                    recognize, recognizer, recognizer_lock, samples
                )
                if not text_src:
                    continue

                for sentence in split_sentences(text_src, src_lang):
                    text_dst = await asyncio.to_thread(translate, sentence, src_lang, tgt_lang)
                    write_log(sentence, text_dst, src_lang, tgt_lang)
                    print(f"[{src_lang}] {sentence}")
                    print(f"[{tgt_lang}] {text_dst}")
                    await websocket.send_text(text_dst)

    except WebSocketDisconnect:
        print(f"❌ Electron ngắt kết nối — chiều {src_lang.upper()}→{tgt_lang.upper()}")
    except Exception as error:
        print(f"❌ Lỗi WebSocket: {error}")
        try:
            await websocket.close()
        except Exception:
            pass


# Chiều 1: người Nhật nói -> hiển thị tiếng Việt
@app.websocket("/ws/audio/ja")
async def websocket_ja(websocket: WebSocket) -> None:
    await handle_stream(websocket, recognizer_ja, recognizer_ja_lock, "ja", "vi")


# Chiều 2: người Việt nói -> hiển thị tiếng Nhật
@app.websocket("/ws/audio/vi")
async def websocket_vi(websocket: WebSocket) -> None:
    await handle_stream(websocket, recognizer_vi, recognizer_vi_lock, "vi", "ja")


# ============================================================
# CHẠY SERVER
# ============================================================
if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)