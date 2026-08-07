
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Lock

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr:
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import ctranslate2
import numpy as np
import sherpa_onnx
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from transformers import AutoTokenizer

from postprocess import Glossary, PostProcessor, TranslationCache

app = FastAPI(title="KaTOBA BridgeAI Backend")

# ---------------------------------------------------------------------------
# ĐƯỜNG DẪN
# ---------------------------------------------------------------------------

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

MODELS_DIR = BASE_DIR / "models"

MODEL_JA_DIR = MODELS_DIR / "parakeet-ja"
MODEL_JA_FILE = MODEL_JA_DIR / "model.int8.onnx"
TOKENS_JA_FILE = MODEL_JA_DIR / "tokens.txt"

MODEL_VI_DIR = MODELS_DIR / "zipformer-vi"
VI_ENCODER = MODEL_VI_DIR / "encoder.int8.onnx"
VI_DECODER = MODEL_VI_DIR / "decoder.onnx"
VI_JOINER = MODEL_VI_DIR / "joiner.int8.onnx"
VI_TOKENS = MODEL_VI_DIR / "tokens.txt"

M2M100_DIR = MODELS_DIR / "m2m100_418M_int8"
SILERO_VAD_FILE = MODELS_DIR / "silero_vad.onnx"
GLOSSARY_FILE = BASE_DIR / "glossary.json"
LOG_FILE = BASE_DIR / "transcript_log.txt"

# ---------------------------------------------------------------------------
# CẤU HÌNH
# ---------------------------------------------------------------------------

HOST = os.environ.get("KATOBA_HOST", "127.0.0.1")
PORT = int(os.environ.get("KATOBA_PORT", "8765"))   # BUG-026: khớp tài liệu

SAMPLE_RATE = 16000

# BUG-030 — MẶC ĐỊNH TẮT.
# write_log() cũ ghi nguyên văn nội dung họp doanh nghiệp ra file, vô điều kiện.
# Đó không phải logger gỡ lỗi bị sót mà là đường đi mặc định của chương trình.
# Muốn bật khi debug: đặt KATOBA_TRANSCRIPT_LOG=1
TRANSCRIPT_LOG = os.environ.get("KATOBA_TRANSCRIPT_LOG", "0") == "1"
VERBOSE = os.environ.get("KATOBA_VERBOSE", "0") == "1"

# BUG-003 / BUG-033 — VAD theo nguồn âm thanh.
# Frontend đã gửi ?source=system|microphone từ lâu, backend cũ không hề đọc.
#   system     : lấy thẳng từ Zoom/Teams, khá sạch -> ngưỡng thấp, bắt được giọng nhỏ
#   microphone : phòng ồn / nhà máy SNR 15dB -> ngưỡng cao để VAD không kích hoạt trên tiếng máy
VAD_PROFILES = {
    "system":     {"threshold": 0.45, "min_silence": 0.60, "min_speech": 0.25, "max_speech": 12.0},
    "microphone": {"threshold": 0.65, "min_silence": 0.70, "min_speech": 0.30, "max_speech": 12.0},
}

# BUG-028 — hàng đợi có trần. Đầy thì bỏ đoạn CŨ NHẤT, giữ đoạn mới.
# Thà mất một câu cũ còn hơn để độ trễ phân kỳ quá 30 giây.
SEGMENT_QUEUE_MAX = 6

# BUG-001 — điểm log-prob trung bình/token thấp hơn ngưỡng thì im lặng.
# -3.0 là mức KHỞI ĐẦU rất nới, gần như chỉ chặn rác hiển nhiên.
# Phải chỉnh lại bằng dữ liệu thật: bật KATOBA_VERBOSE=1, đọc điểm của những
# câu bạn thấy sai, rồi kéo ngưỡng lên dần. Đặt quá chặt sẽ nuốt câu đúng.
MIN_AVG_LOGPROB = float(os.environ.get("KATOBA_MIN_LOGPROB", "-3.0"))

MIN_RAM_GB = 1.5

# ---------------------------------------------------------------------------
# KIỂM TRA TRƯỚC KHI NẠP
# ---------------------------------------------------------------------------

def _check_files() -> None:
    missing = []
    if not (MODEL_JA_FILE.exists() and TOKENS_JA_FILE.exists()):
        missing.append(f"Parakeet-JA tại {MODEL_JA_DIR}")
    if not (VI_ENCODER.exists() and VI_DECODER.exists()
            and VI_JOINER.exists() and VI_TOKENS.exists()):
        missing.append(f"Zipformer-VI tại {MODEL_VI_DIR}")
    if not M2M100_DIR.exists():
        missing.append(f"M2M-100 tại {M2M100_DIR}")
    if not SILERO_VAD_FILE.exists():
        missing.append(f"Silero VAD tại {SILERO_VAD_FILE}")
    if missing:
        print("❌ Thiếu model:")
        for m in missing:
            print(f"   • {m}")
        raise SystemExit(1)


def _check_ram() -> None:
    """BUG-041 — báo trước thay vì để nó chết giữa chừng lúc nạp."""
    try:
        import psutil
    except ImportError:
        print("ℹ️  Không có psutil, bỏ qua kiểm tra RAM")
        return
    avail = psutil.virtual_memory().available / 1e9
    print(f"💾 RAM trống: {avail:.2f} GB")
    if avail < MIN_RAM_GB:
        print(f"❌ Cần tối thiểu {MIN_RAM_GB} GB trống để nạp 3 model.")
        print("   Đóng bớt ứng dụng rồi thử lại.")
        raise SystemExit(1)


def _rss_gb() -> float:
    try:
        import psutil
        return psutil.Process(os.getpid()).memory_info().rss / 1e9
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# NẠP MODEL — SONG SONG (BUG-032)
# ---------------------------------------------------------------------------

def _load_ja():
    return sherpa_onnx.OfflineRecognizer.from_nemo_ctc(
        model=str(MODEL_JA_FILE), tokens=str(TOKENS_JA_FILE),
        num_threads=2, sample_rate=SAMPLE_RATE, feature_dim=80,
        decoding_method="greedy_search", provider="cpu",
    )


def _load_vi():
    return sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=str(VI_ENCODER), decoder=str(VI_DECODER), joiner=str(VI_JOINER),
        tokens=str(VI_TOKENS), num_threads=2, sample_rate=SAMPLE_RATE,
        feature_dim=80, decoding_method="greedy_search", provider="cpu",
    )


def _load_mt():
    tr = ctranslate2.Translator(str(M2M100_DIR), device="cpu",
                                compute_type="int8", inter_threads=1, intra_threads=2)
    try:
        tok = AutoTokenizer.from_pretrained(str(M2M100_DIR))
    except Exception as err:
        # Nhánh này CẦN MẠNG -> app đóng gói sẽ chết khi offline.
        # Nếu rơi vào đây thì thư mục CT2 thiếu file tokenizer, sửa ở bước convert.
        print(f"⚠️  Không nạp được tokenizer local ({err}), thử tải từ HuggingFace...")
        tok = AutoTokenizer.from_pretrained("facebook/m2m100_418M")
        tok.save_pretrained(str(M2M100_DIR))
    return tr, tok


_check_files()
_check_ram()

print("⏳ Nạp 3 model song song...")
_t0 = time.time()
_rss0 = _rss_gb()

# num_threads mỗi model để 2 (thay vì 4) vì 3 model chạy song song trên cùng CPU.
# Tổng 6 luồng vẫn đủ cho i5-8250U 4 nhân 8 luồng của máy test B.
with ThreadPoolExecutor(max_workers=3) as _pool:
    _f_ja = _pool.submit(_load_ja)
    _f_vi = _pool.submit(_load_vi)
    _f_mt = _pool.submit(_load_mt)
    recognizer_ja = _f_ja.result()
    recognizer_vi = _f_vi.result()
    translator, tokenizer = _f_mt.result()

recognizer_ja_lock = Lock()
recognizer_vi_lock = Lock()
translator_lock = Lock()

print(f"✅ Nạp xong sau {time.time() - _t0:.1f}s "
      f"(RAM +{_rss_gb() - _rss0:.2f} GB, tổng {_rss_gb():.2f} GB)")

GLOSSARY = Glossary.load(GLOSSARY_FILE)
SHARED_CACHE = TranslationCache(maxsize=1024)   # BUG-024: nhất quán xuyên phiên

# M2M-100 dùng token ngôn ngữ dạng __ja__ / __vi__.
# Tên thuộc tính lang_code_to_token đã đổi qua vài bản transformers -> có fallback.
def _lang_token(code: str) -> str:
    mapping = getattr(tokenizer, "lang_code_to_token", None)
    if isinstance(mapping, dict) and code in mapping:
        return mapping[code]
    return f"__{code}__"


# ---------------------------------------------------------------------------
# BỘ ĐỆM CÂU (BUG-003)
# ---------------------------------------------------------------------------

JA_END = re.compile(r"[。．！？!?]\s*$|(?:です|ます|ました|でした|ください|しょう|ですね|ますね)\s*$")
VI_END = re.compile(r"[.!?]\s*$|\b(nhé|nha|ạ|rồi|nhá|được không|chưa|đi)\s*$", re.IGNORECASE)

MAX_BUFFER_CHARS = 120
MAX_BUFFER_SEC = 6.0


class SentenceBuffer:
    """
    Giữ mẩu ASR chưa thành câu, ghép với mẩu kế rồi dịch lại toàn bộ.

    Đây là chỗ Google Translate hơn app này — GG nhận cả câu do người dùng gõ
    xong mới bấm dịch, còn app nhận từng mẩu VAD rồi dịch ngay mẩu đó.
    Cách bù: đệm ở tầng server và ghi đè dòng cũ theo msg_id, giống live
    caption của YouTube/Teams.
    """

    def __init__(self, lang: str):
        self.lang = lang
        self.parts: list[str] = []
        self.started_at = 0.0
        self.msg_id = 0

    def _complete(self, text: str) -> bool:
        pat = JA_END if self.lang == "ja" else VI_END
        return bool(pat.search(text.strip()))

    def push(self, chunk: str) -> list[tuple[int, str, bool]]:
        chunk = chunk.strip()
        if not chunk:
            return []
        if not self.parts:
            self.started_at = time.time()
            self.msg_id += 1

        self.parts.append(chunk)
        merged = ("" if self.lang == "ja" else " ").join(self.parts)

        final = (self._complete(merged)
                 or len(merged) > MAX_BUFFER_CHARS
                 or (time.time() - self.started_at) > MAX_BUFFER_SEC)

        out = [(self.msg_id, merged, final)]
        if final:
            self.parts = []
        return out

    def flush(self) -> list[tuple[int, str, bool]]:
        if not self.parts:
            return []
        merged = ("" if self.lang == "ja" else " ").join(self.parts)
        self.parts = []
        return [(self.msg_id, merged, True)]


# ---------------------------------------------------------------------------
# ASR / DỊCH
# ---------------------------------------------------------------------------

def recognize(recognizer, lock: Lock, samples: np.ndarray) -> str:
    samples = np.ascontiguousarray(samples, dtype=np.float32)
    with lock:
        stream = recognizer.create_stream()
        stream.accept_waveform(SAMPLE_RATE, samples)
        recognizer.decode_stream(stream)
        return stream.result.text.strip()


def translate(text: str, src_lang: str, tgt_lang: str,
              cache: TranslationCache | None = None) -> tuple[str, float]:
    """Trả (bản dịch, log-prob trung bình mỗi token). Chuỗi rỗng = nên bỏ qua."""
    if not text:
        return "", 0.0

    if cache is not None:
        hit = cache.get(text, src_lang, tgt_lang)
        if hit is not None:
            return hit, 0.0

    try:
        with translator_lock:
            tokenizer.src_lang = src_lang
            source_tokens = tokenizer.convert_ids_to_tokens(tokenizer.encode(text))
            n_src = len(source_tokens)

            results = translator.translate_batch(
                [source_tokens],
                target_prefix=[[_lang_token(tgt_lang)]],
                beam_size=4,
                # BUG-004 / BUG-006 — bản cũ để mặc định nên lặp token trên input ngắn
                repetition_penalty=1.1,
                no_repeat_ngram_size=3,
                # chặn output dài lê thê khi nguồn là mẩu vụn
                max_decoding_length=min(128, int(n_src * 2.5) + 12),
                min_decoding_length=1,
                length_penalty=1.0,
                return_scores=True,
            )

            hyp = results[0].hypotheses[0][1:]
            if not hyp:
                return "", -99.0
            score = results[0].scores[0] / max(1, len(hyp))
            out = tokenizer.decode(tokenizer.convert_tokens_to_ids(hyp),
                                   skip_special_tokens=True).strip()

        if cache is not None:
            cache.put(text, src_lang, tgt_lang, out)
        return out, score

    except Exception as err:
        print(f"❌ Lỗi dịch M2M-100: {err}")
        return "", -99.0


def write_log(src: str, dst: str, sl: str, tl: str) -> None:
    """BUG-030 — chỉ ghi khi được bật tường minh."""
    if not TRANSCRIPT_LOG:
        return
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"[{stamp}]\n{sl.upper()}: {src}\n{tl.upper()}: {dst}\n{'-' * 50}\n")


# ---------------------------------------------------------------------------
# LUỒNG CHÍNH — producer / consumer tách rời (BUG-028, BUG-018)
# ---------------------------------------------------------------------------

async def handle_stream(websocket: WebSocket, recognizer, recognizer_lock: Lock,
                        src_lang: str, tgt_lang: str) -> None:
    await websocket.accept()

    source = websocket.query_params.get("source", "system")
    if source not in VAD_PROFILES:
        source = "system"
    prof = VAD_PROFILES[source]

    print(f"🔌 Kết nối {src_lang.upper()}→{tgt_lang.upper()} | nguồn={source} "
          f"| VAD thr={prof['threshold']} silence={prof['min_silence']}s")

    vad_config = sherpa_onnx.VadModelConfig()
    vad_config.silero_vad.model = str(SILERO_VAD_FILE)
    vad_config.silero_vad.threshold = prof["threshold"]
    vad_config.silero_vad.min_silence_duration = prof["min_silence"]
    vad_config.silero_vad.min_speech_duration = prof["min_speech"]
    vad_config.silero_vad.max_speech_duration = prof["max_speech"]
    vad_config.sample_rate = SAMPLE_RATE
    window_size = vad_config.silero_vad.window_size
    vad = sherpa_onnx.VoiceActivityDetector(vad_config, buffer_size_in_seconds=30)

    queue: asyncio.Queue = asyncio.Queue(maxsize=SEGMENT_QUEUE_MAX)
    post = PostProcessor(GLOSSARY, cache=SHARED_CACHE)
    buffer = SentenceBuffer(src_lang)
    dropped = 0

    async def producer() -> None:
        """Nhận byte -> VAD -> đẩy đoạn vào hàng đợi. Không chạm ASR/dịch."""
        nonlocal dropped
        pending = np.zeros(0, dtype=np.float32)
        while True:
            data = await websocket.receive_bytes()
            chunk = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
            if chunk.size == 0:
                continue

            pending = np.concatenate([pending, chunk])
            while pending.size >= window_size:
                vad.accept_waveform(np.ascontiguousarray(pending[:window_size]))
                pending = pending[window_size:]

            while not vad.empty():
                samples = np.ascontiguousarray(
                    np.array(vad.front.samples, dtype=np.float32))
                vad.pop()
                # BUG-028: đầy thì vứt đoạn CŨ NHẤT, không để hàng đợi phình vô hạn
                if queue.full():
                    try:
                        queue.get_nowait()
                        queue.task_done()
                        dropped += 1
                        if dropped % 5 == 1:
                            print(f"⚠️  Hàng đợi đầy, đã bỏ {dropped} đoạn cũ "
                                  f"(máy không kịp xử lý)")
                    except asyncio.QueueEmpty:
                        pass
                queue.put_nowait(samples)

    async def consumer() -> None:
        """Lấy đoạn -> ASR -> hậu xử lý -> dịch -> gửi về Electron."""
        while True:
            samples = await queue.get()
            try:
                raw = await asyncio.to_thread(
                    recognize, recognizer, recognizer_lock, samples)
                if not raw:
                    continue

                # BUG-022 / BUG-047: chuẩn hoá số ngay trên text nguồn
                text_src = post.prepare_source(raw, src_lang)
                if not text_src:
                    continue

                for msg_id, merged, is_final in buffer.push(text_src):
                    # BUG-016: tiếng vọng -> chỉ lọc ở câu đã chốt,
                    # câu tạm thời vốn dĩ trùng nhau theo thiết kế
                    if is_final and post.is_duplicate(merged):
                        if VERBOSE:
                            print(f"🔁 Bỏ trùng: {merged}")
                        continue

                    text_dst, score = await asyncio.to_thread(
                        translate, merged, src_lang, tgt_lang, post.cache)

                    # BUG-001: điểm quá thấp = model đang đoán mò -> im còn hơn hiện sai
                    if not text_dst or score < MIN_AVG_LOGPROB:
                        if VERBOSE:
                            print(f"🔇 Bỏ (score={score:.2f}): {merged} → {text_dst}")
                        continue

                    # BUG-008 / BUG-031: từ điển + locale số
                    text_dst = post.finish(merged, text_dst, src_lang, tgt_lang)

                    if is_final:
                        write_log(merged, text_dst, src_lang, tgt_lang)
                    if VERBOSE:
                        print(f"[{src_lang}] {merged}")
                        print(f"[{tgt_lang}] {text_dst}  (score={score:.2f})")

                    await websocket.send_text(json.dumps({
                        "id": msg_id,          # Electron dùng id để GHI ĐÈ dòng cũ
                        "src": merged,
                        "dst": text_dst,
                        "final": is_final,     # false -> render mờ/nghiêng
                    }, ensure_ascii=False))
            finally:
                queue.task_done()

    prod = asyncio.create_task(producer())
    cons = asyncio.create_task(consumer())
    try:
        done, pending_tasks = await asyncio.wait(
            {prod, cons}, return_when=asyncio.FIRST_EXCEPTION)
        for t in done:
            if t.exception():
                raise t.exception()
    except WebSocketDisconnect:
        print(f"❌ Ngắt kết nối {src_lang.upper()}→{tgt_lang.upper()} "
              f"| bỏ {dropped} đoạn | dedup {post.stats['dedup']} "
              f"| glossary {post.stats['glossary']}")
    except Exception as err:
        print(f"❌ Lỗi WebSocket: {err}")
    finally:
        for t in (prod, cons):
            t.cancel()
        await asyncio.gather(prod, cons, return_exceptions=True)
        try:
            await websocket.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# ENDPOINT
# ---------------------------------------------------------------------------

@app.websocket("/ws/audio/ja")
async def websocket_ja(websocket: WebSocket) -> None:
    await handle_stream(websocket, recognizer_ja, recognizer_ja_lock, "ja", "vi")


@app.websocket("/ws/audio/vi")
async def websocket_vi(websocket: WebSocket) -> None:
    await handle_stream(websocket, recognizer_vi, recognizer_vi_lock, "vi", "ja")


@app.get("/v1/health")
async def health() -> dict:
    """BUG-027 — endpoint quản trị, có gắn phiên bản."""
    return {
        "status": "ok",
        "rss_gb": round(_rss_gb(), 2),
        "transcript_log": TRANSCRIPT_LOG,
        "cache": {"hits": SHARED_CACHE.hits, "misses": SHARED_CACHE.misses},
    }


@app.get("/v1/models")
async def models() -> dict:
    return {
        "asr_ja": {"engine": "sherpa-onnx", "arch": "NeMo CTC", "quant": "int8",
                   "device": "cpu", "hotwords": False},
        "asr_vi": {"engine": "sherpa-onnx", "arch": "Zipformer transducer",
                   "quant": "int8", "device": "cpu", "hotwords": False},
        "mt": {"engine": "ctranslate2", "arch": "M2M-100 418M + LoRA",
               "quant": "int8", "device": "cpu"},
        "vad": {"engine": "silero", "format": "onnx"},
        "glossary_entries": len(GLOSSARY.entries),
    }


if __name__ == "__main__":
    print(f"🚀 http://{HOST}:{PORT}  |  ws://{HOST}:{PORT}/ws/audio/{{ja,vi}}")
    if TRANSCRIPT_LOG:
        print("⚠️  TRANSCRIPT_LOG ĐANG BẬT — nội dung phát ngôn sẽ được ghi ra đĩa.")
    uvicorn.run(app, host=HOST, port=PORT, ws_ping_interval=20, ws_ping_timeout=20)