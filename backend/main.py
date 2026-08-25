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

MODEL_VERSION = "v6"          # LoRA v6: +67 câu (kính ngữ lồng, giúp+động từ,
                              # rủ rê/lệnh), contrast 14/16, chrF tăng cả 4 hướng

# ---------------------------------------------------------------------------
# CẤU HÌNH
# ---------------------------------------------------------------------------

HOST = os.environ.get("KATOBA_HOST", "127.0.0.1")
PORT = int(os.environ.get("KATOBA_PORT", "8765"))

SAMPLE_RATE = 16000

TRANSCRIPT_LOG = os.environ.get("KATOBA_TRANSCRIPT_LOG", "0") == "1"
VERBOSE = os.environ.get("KATOBA_VERBOSE", "0") == "1"

VAD_PROFILES = {
    "system":     {"threshold": 0.45, "min_silence": 0.60, "min_speech": 0.25, "max_speech": 12.0},
    "microphone": {"threshold": 0.65, "min_silence": 0.70, "min_speech": 0.30, "max_speech": 12.0},
}

SEGMENT_QUEUE_MAX = 6

# FIX-v5 (1) — ngưỡng riêng cho bản nháp và bản chốt.
# Bản nháp sẽ bị GHI ĐÈ nên nới tay hơn; bản chốt mới là thứ người ta đọc và trích.
MIN_LOGPROB_FINAL = float(os.environ.get("KATOBA_MIN_LOGPROB", "-3.0"))
MIN_LOGPROB_PARTIAL = MIN_LOGPROB_FINAL - 1.0

# ĐỢT-3 — gate ASR: chặn segment có avg logprob ASR quá thấp TRƯỚC khi dịch.
# Ngưỡng -1.0 chọn từ log phiên 2026-08-18 (VERBOSE): rác rõ ('U' -1.65,
# 'ĐÂY' -1.79, 'ANA VẪN LA TẤT NHIÊN' -1.04) nằm dưới, mẩu ngắn hợp lệ
# ('MAI' -0.56, 'TRỜI ƠI' -0.19) nằm trên. Mới calibrate trên MỘT phiên
# tiếng Việt nội dung vlog — chỉnh qua env var khi có log họp thật, không
# cần sửa code. Đặt -99 để tắt gate. Chiều nào ASR không trả ys_log_probs
# (score=None) thì tự động không bị gate.
MIN_ASR_LOGPROB = float(os.environ.get("KATOBA_MIN_ASR_LOGPROB", "-1.0"))

# FIX-v5 (2) — hệ số nở token TÁCH THEO CHIỀU.
# Bản cũ dùng chung 2.5 cho cả hai chiều, nhưng tỉ lệ ngược nhau hoàn toàn:
#   ja→vi : nguồn kanji dày -> n_src nhỏ; đích tiếng Việt tách âm tiết -> cần
#           NHIỀU token. Trần 2.5 quá chặt -> câu bị CẮT CỤT giữa chừng.
#   vi→ja : nguồn tiếng Việt đơn âm -> n_src lớn; đích tiếng Nhật dày -> cần ÍT
#           token. Trần 2.5 quá lỏng -> model lan man.
LEN_MULT = {("ja", "vi"): 4.0, ("vi", "ja"): 2.0}

BEAM_FINAL = 4
BEAM_PARTIAL = 1          # bản nháp: đổi chất lượng lấy độ trễ

MIN_RAM_GB = 1.5

STARTUP_ERROR_FILE = BASE_DIR / "startup_error.log"


# ---------------------------------------------------------------------------
# THOÁT CÓ DẤU VẾT
# ---------------------------------------------------------------------------

def _fatal(*lines: str) -> None:
    """
    FIX-v5 (9) — chết KÈM BẰNG CHỨNG.

    main.spec đang để console=True, nhưng comment trong đó nói khi chạy ổn sẽ
    đổi sang False. Lúc đó print() đi vào hư không: process tắt lặng lẽ và
    Electron chỉ thấy backend không lên, không biết vì sao. Vì FIX-v5 (3) đã
    biến "thiếu tokenizer" thành lỗi chí mạng, đường thoát này phải để lại
    dấu vết trên đĩa.
    """
    msg = "\n".join(lines)
    print(msg)
    try:
        STARTUP_ERROR_FILE.write_text(
            f"{datetime.now():%Y-%m-%d %H:%M:%S}\n{msg}\n", encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(1)


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
        _fatal("❌ Thiếu model:", *[f"   • {m}" for m in missing])


def _check_ram() -> None:
    try:
        import psutil
    except ImportError:
        print("ℹ️  Không có psutil, bỏ qua kiểm tra RAM")
        return
    avail = psutil.virtual_memory().available / 1e9
    print(f"💾 RAM trống: {avail:.2f} GB")
    if avail < MIN_RAM_GB:
        _fatal(f"❌ Cần tối thiểu {MIN_RAM_GB} GB trống để nạp 3 model "
               f"(đang trống {avail:.2f} GB).",
               "   Đóng bớt ứng dụng rồi thử lại.")


def _rss_gb() -> float:
    try:
        import psutil
        return psutil.Process(os.getpid()).memory_info().rss / 1e9
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# NẠP MODEL — SONG SONG
# ---------------------------------------------------------------------------

def _load_ja():
    # ĐỢT-4 — Parakeet-JA là model NẶNG: đo thực tế RTF ~0.4 với num_threads=2
    # (12s audio -> 4.6-5.8s ASR), làm queue dồn tới 5.8s và e2e tới 9.6s trong
    # phiên chỉ-một-chiều. Zipformer-VI thì RTF ~0.01 nên giữ 2 thread.
    # Nâng JA lên 4 thread (chỉnh qua env var để đo A/B không cần sửa code).
    # LƯU Ý: máy test B (i5-8250U) chỉ có 4 core vật lý — khi họp SONG PHƯƠNG
    # (2 ASR + 2 MT cùng chạy) 4 thread sẽ tranh CPU với phần còn lại; phải đo
    # lại kịch bản hai chiều cùng nói trước khi chốt số này cho bản ship.
    ja_threads = int(os.environ.get("KATOBA_ASR_JA_THREADS", "4"))
    return sherpa_onnx.OfflineRecognizer.from_nemo_ctc(
        model=str(MODEL_JA_FILE), tokens=str(TOKENS_JA_FILE),
        num_threads=ja_threads, sample_rate=SAMPLE_RATE, feature_dim=80,
        decoding_method="greedy_search", provider="cpu",
    )


def _load_vi():
    return sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=str(VI_ENCODER), decoder=str(VI_DECODER), joiner=str(VI_JOINER),
        tokens=str(VI_TOKENS), num_threads=2, sample_rate=SAMPLE_RATE,
        feature_dim=80, decoding_method="greedy_search", provider="cpu",
    )


def _load_mt():
    """
    FIX-v5 (3) — BỎ nhánh fallback tải tokenizer từ HuggingFace.

    Bản cũ khi thiếu file tokenizer sẽ lặng lẽ gọi ra Internet. Với một sản phẩm
    bán ra dưới nhãn "dịch offline", một request đi ra ngoài sẽ xuất hiện trong
    firewall log của khách doanh nghiệp, và lúc đó rất khó giải thích. Thà chết
    ngay lúc khởi động với thông báo rõ ràng.

    FIX-v5 (4) — HAI tokenizer, mỗi chiều một cái.
    `tokenizer.src_lang` là state mutable dùng chung; đó là lý do bản cũ phải ôm
    `translator_lock` quanh toàn bộ quá trình dịch, khiến hai chiều ja→vi và
    vi→ja nối đuôi nhau trong cuộc họp song phương. Set src_lang một lần lúc nạp
    thì không còn state chia sẻ, bỏ được lock.
    """
    try:
        tok_ja = AutoTokenizer.from_pretrained(str(M2M100_DIR), local_files_only=True)
        tok_vi = AutoTokenizer.from_pretrained(str(M2M100_DIR), local_files_only=True)
    except Exception as err:
        _fatal("❌ Không nạp được tokenizer từ thư mục model.",
               f"   {M2M100_DIR}",
               f"   Lỗi: {err}",
               "   Thư mục CT2 thiếu file tokenizer -> sửa ở bước convert:",
               "   ct2-transformers-converter ... --copy_files "
               "sentencepiece.bpe.model vocab.json tokenizer_config.json")

    tok_ja.src_lang = "ja"
    tok_vi.src_lang = "vi"

    # inter_threads=2 cho phép CT2 chạy hai bản dịch song song (một chiều mỗi
    # luồng). Đo lại RSS qua /v1/health sau khi đổi: nếu bộ nhớ tăng gần gấp đôi
    # thì bản CT2 này nhân bản trọng số, hạ về 1.
    tr = ctranslate2.Translator(str(M2M100_DIR), device="cpu",
                                compute_type="int8", inter_threads=2, intra_threads=2)
    return tr, {"ja": tok_ja, "vi": tok_vi}


_check_files()
_check_ram()

print(f"⏳ Nạp 3 model song song... (MT {MODEL_VERSION})")
print(f"🔧 VERBOSE={'BẬT' if VERBOSE else 'TẮT'} | TRANSCRIPT_LOG={'BẬT' if TRANSCRIPT_LOG else 'TẮT'}"
      f"   (bật log chi tiết: chạy  $env:KATOBA_VERBOSE=\"1\"  trong CÙNG cửa sổ PowerShell trước khi python main.py)")
_t0 = time.time()
_rss0 = _rss_gb()

with ThreadPoolExecutor(max_workers=3) as _pool:
    _f_ja = _pool.submit(_load_ja)
    _f_vi = _pool.submit(_load_vi)
    _f_mt = _pool.submit(_load_mt)
    recognizer_ja = _f_ja.result()
    recognizer_vi = _f_vi.result()
    translator, TOKENIZERS = _f_mt.result()

recognizer_ja_lock = Lock()
recognizer_vi_lock = Lock()
# FIX-v5 (4) — không còn translator_lock. CT2 Translator tự an toàn đa luồng.

print(f"✅ Nạp xong sau {time.time() - _t0:.1f}s "
      f"(RAM +{_rss_gb() - _rss0:.2f} GB, tổng {_rss_gb():.2f} GB)")

# Khởi động ngon -> dọn dấu vết lần chết trước, tránh hỗ trợ đọc nhầm log cũ.
try:
    STARTUP_ERROR_FILE.unlink(missing_ok=True)
except Exception:
    pass

GLOSSARY = Glossary.load(GLOSSARY_FILE)
SHARED_CACHE = TranslationCache(maxsize=1024)


def _lang_token(tok, code: str) -> str:
    mapping = getattr(tok, "lang_code_to_token", None)
    if isinstance(mapping, dict) and code in mapping:
        return mapping[code]
    return f"__{code}__"


# ---------------------------------------------------------------------------
# BỘ ĐỆM CÂU
# ---------------------------------------------------------------------------

# FIX-v5 (5) — BỎ regex đoán kết câu, dùng tín hiệu IM LẶNG từ VAD.
#
# Bản cũ:
#   VI_END = r"[.!?]\s*$|\b(nhé|nha|ạ|rồi|nhá|được không|chưa|đi)\s*$"
# "rồi", "đi", "chưa" KHÔNG phải tiểu từ cuối câu tiếng Việt — chúng là động
# từ/phó từ tần suất cao nằm giữa câu:
#   "tôi gửi tài liệu rồi | anh xem giúp em nhé"   -> cắt làm hai
#   "tuần sau anh đi | công tác Osaka"             -> cắt giữa cụm động từ
#   "em chưa | nhận được mail"                     -> cắt giữa cụm phủ định
# Mỗi lần khớp nhầm là buffer bị xoá, nửa câu sau thành message riêng, và MT
# nhận hai nửa vô nghĩa. Đây là nguồn chính của lỗi "câu bị cắt cụt".
#
# Bản cũ cũng kiểm tra 。！？ cho tiếng Nhật — nhưng Parakeet chạy NeMo CTC
# greedy_search KHÔNG SINH DẤU CÂU, nên vế đó là code chết.
#
# Thay bằng: VAD kết thúc đoạn vì im lặng ≥ min_silence -> hết câu.
# VAD kết thúc vì chạm trần max_speech -> người ta còn đang nói, giữ đệm lại.

# Đuôi cho biết câu CHẮC CHẮN còn tiếp, dù có ngắt hơi.
JA_CONTINUES = re.compile(r"(ので|のに|けど|けれど|んですが|ですが|ますが|たら|れば|"
                          r"して|くて|でも|から|とか|など|、)\s*$")
VI_CONTINUES = re.compile(r"\b(và|nhưng|thì|để|mà|nên|vì|do|nếu|khi|hoặc|với|của|"
                          r"cho|theo|về)\s*$", re.IGNORECASE)

MAX_BUFFER_CHARS = 150
MAX_CONTINUATIONS = 2      # tối đa 2 đoạn nối -> chốt, tránh trễ dồn quá 30s


class SentenceBuffer:
    """
    Gom mẩu VAD thành câu. Quyết định chốt câu dựa trên VAD, không dựa trên regex.

    Trả về (msg_id, text, is_final).
    """

    def __init__(self, lang: str):
        self.lang = lang
        self.parts: list[str] = []
        self.msg_id = 0
        self.continuations = 0

    def _continues(self, text: str) -> bool:
        pat = JA_CONTINUES if self.lang == "ja" else VI_CONTINUES
        return bool(pat.search(text.strip()))

    def push(self, chunk: str, truncated: bool) -> tuple[int, str, bool] | None:
        """truncated=True nghĩa là VAD cắt vì chạm trần thời lượng, không phải im lặng."""
        chunk = chunk.strip()
        if not chunk:
            return None
        if not self.parts:
            self.msg_id += 1
            self.continuations = 0

        self.parts.append(chunk)
        merged = ("" if self.lang == "ja" else " ").join(self.parts)

        if truncated:
            self.continuations += 1

        final = (
            (not truncated and not self._continues(merged))     # im lặng + không phải đuôi nối
            or self.continuations >= MAX_CONTINUATIONS
            or len(merged) > MAX_BUFFER_CHARS
        )

        if final:
            self.parts = []
        return (self.msg_id, merged, final)

    def flush(self) -> tuple[int, str, bool] | None:
        if not self.parts:
            return None
        merged = ("" if self.lang == "ja" else " ").join(self.parts)
        self.parts = []
        return (self.msg_id, merged, True)


# ---------------------------------------------------------------------------
# ASR / DỊCH
# ---------------------------------------------------------------------------

def recognize(recognizer, lock: Lock,
              samples: np.ndarray) -> tuple[str, float | None, float]:
    """
    ĐỢT-2 (đo đạc, KHÔNG đổi hành vi) — trả (text, avg_logprob, thời_gian_ms).

    avg_logprob lấy từ stream.result.ys_log_probs (log-prob từng token).
    Giá trị None nghĩa là bản sherpa-onnx đang pin (hoặc kiến trúc model —
    NeMo CTC vs transducer) không điền trường này. Đó cũng là thông tin:
    nếu sau vài buổi họp cả hai chiều đều in "n/a" thì kế hoạch gate ASR
    (đợt 3) phải đổi hướng, khỏi viết gate vô dụng.

    Chỉ đo và ghi log — ngưỡng chặn sẽ chọn SAU, từ số liệu thật, đúng cách
    đã chốt MIN_LOGPROB=-3.0 cho MT. Không đoán ngưỡng trước khi có số.
    """
    samples = np.ascontiguousarray(samples, dtype=np.float32)
    t0 = time.perf_counter()
    with lock:
        stream = recognizer.create_stream()
        stream.accept_waveform(SAMPLE_RATE, samples)
        recognizer.decode_stream(stream)
        r = stream.result
    dt_ms = (time.perf_counter() - t0) * 1000
    probs = getattr(r, "ys_log_probs", None)
    score = (sum(probs) / len(probs)) if probs else None
    return r.text.strip(), score, dt_ms


def translate(text: str, src_lang: str, tgt_lang: str,
              is_final: bool = True,
              cache: TranslationCache | None = None) -> tuple[str, float]:
    """Trả (bản dịch, log-prob trung bình mỗi token). Chuỗi rỗng = nên bỏ qua."""
    if not text:
        return "", 0.0

    # FIX-v5 (6) — CHỈ cache bản chốt.
    # Bản nháp dịch với beam=1; nếu đưa vào cache thì lần sau cùng chuỗi đó xuất
    # hiện ở vị trí bản chốt sẽ nhận lại kết quả beam=1 kém hơn.
    use_cache = cache is not None and is_final
    if use_cache:
        hit = cache.get(text, src_lang, tgt_lang)
        if hit is not None:
            return hit, 0.0

    tok = TOKENIZERS[src_lang]

    try:
        # FIX-v6.1 — Zipformer-VI xuất CHỮ HOA TOÀN BỘ, nhưng LoRA train 100%
        # nguồn vi ở dạng thường (noise_vi() trong notebook lowercase ở MỌI
        # level nhiễu). SentencePiece băm "RẤT LÀ" khác hẳn "rất là" -> lệch
        # train/serve hệ thống, vi→ja ra rác/hallucination ("TRỜI ƠI" ->
        # "おめでとうございます"). Chỉ đổi input cho MODEL — hiển thị "src" trên
        # frontend, cache (_norm_key đã lowercase), dedup, glossary (IGNORECASE)
        # đều không bị ảnh hưởng.
        text_for_model = text.lower() if src_lang == "vi" else text
        source_tokens = tok.convert_ids_to_tokens(tok.encode(text_for_model))
        n_src = len(source_tokens)
        mult = LEN_MULT.get((src_lang, tgt_lang), 2.5)

        results = translator.translate_batch(
            [source_tokens],
            target_prefix=[[_lang_token(tok, tgt_lang)]],
            beam_size=BEAM_FINAL if is_final else BEAM_PARTIAL,
            repetition_penalty=1.1,
            no_repeat_ngram_size=3,
            max_decoding_length=min(128, int(n_src * mult) + 12),
            min_decoding_length=1,
            length_penalty=1.0,
            return_scores=True,
        )

        full_hyp = results[0].hypotheses[0]
        hyp = full_hyp[1:]                       # bỏ token ngôn ngữ ở đầu
        if not hyp:
            return "", -99.0

        # FIX-v5 (7) — chuẩn hoá điểm theo ĐỘ DÀI ĐẦY ĐỦ.
        # Bản cũ chia scores[0] cho len(hyp) sau khi đã cắt mất token ngôn ngữ,
        # trong khi scores[0] tính trên cả chuỗi. Với output ngắn (3-4 token) sai
        # số này đủ để đẩy câu qua/không qua ngưỡng MIN_LOGPROB.
        score = results[0].scores[0] / max(1, len(full_hyp))

        out = tok.decode(tok.convert_tokens_to_ids(hyp),
                         skip_special_tokens=True).strip()

        if use_cache:
            cache.put(text, src_lang, tgt_lang, out)
        return out, score

    except Exception as err:
        print(f"❌ Lỗi dịch M2M-100: {err}")
        return "", -99.0


def write_log(src: str, dst: str, sl: str, tl: str) -> None:
    if not TRANSCRIPT_LOG:
        return
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"[{stamp}]\n{sl.upper()}: {src}\n{tl.upper()}: {dst}\n{'-' * 50}\n")


# ---------------------------------------------------------------------------
# LUỒNG CHÍNH
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

    # Đoạn dài xấp xỉ trần -> VAD cắt vì chạm giới hạn, KHÔNG phải vì im lặng.
    trunc_threshold = prof["max_speech"] - 0.25

    queue: asyncio.Queue = asyncio.Queue(maxsize=SEGMENT_QUEUE_MAX)
    post = PostProcessor(GLOSSARY, cache=SHARED_CACHE)
    buffer = SentenceBuffer(src_lang)
    dropped = 0

    async def producer() -> None:
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
                truncated = (samples.size / SAMPLE_RATE) >= trunc_threshold
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
                # ĐO-E2E — đóng dấu thời điểm VAD chốt đoạn; consumer dùng nó
                # để tính thời gian chờ hàng đợi + tổng e2e mỗi câu.
                queue.put_nowait((samples, truncated, time.perf_counter()))

    async def consumer() -> None:
        while True:
            samples, truncated, t_seg = await queue.get()
            queue_ms = (time.perf_counter() - t_seg) * 1000
            try:
                # ĐỢT-2 — recognize() giờ trả kèm logprob + thời gian, chỉ để LOG.
                raw, asr_score, asr_ms = await asyncio.to_thread(
                    recognize, recognizer, recognizer_lock, samples)
                if not raw:
                    continue
                if VERBOSE:
                    dur = samples.size / SAMPLE_RATE
                    sc = "n/a" if asr_score is None else f"{asr_score:.2f}"
                    print(f"🎙️ ASR {asr_ms:.0f}ms / {dur:.1f}s audio "
                          f"| logprob={sc} | {raw!r}")

                # ĐỢT-3 — gate ASR. Đặt TRƯỚC buffer/dịch: segment rác không
                # được vào câu, không tốn MT (segment rác dài từng ăn 1.4s MT).
                if asr_score is not None and asr_score < MIN_ASR_LOGPROB:
                    if VERBOSE:
                        print(f"🔇 ASR gate (logprob={asr_score:.2f} "
                              f"< {MIN_ASR_LOGPROB}): {raw!r}")
                    continue

                text_src = post.prepare_source(raw, src_lang)
                if not text_src:
                    continue

                pushed = buffer.push(text_src, truncated)
                if pushed is None:
                    continue
                msg_id, merged, is_final = pushed

                # FIX-v5 (8) — KHÔNG dịch mẩu tiếng Nhật chưa hoàn chỉnh.
                #
                # Tiếng Nhật là SOV: động từ, phủ định và thể lịch sự đều nằm
                # cuối câu. Dịch nửa câu không cho ra "nửa bản dịch" mà cho ra
                # một câu KHÁC. Đo trên chính model v5:
                #     この部分は納品前に  ->  "Chỗ này em làm trước khi bàn giao nhé."
                # Model tự bịa ra chủ ngữ và động từ không có trong nguồn. Trong
                # biên bản họp doanh nghiệp đó là rủi ro nội dung, không phải lỗi
                # thẩm mỹ.
                #
                # Chiều vi→ja thì nguồn là SVO nên mẩu dở dang vẫn có nghĩa ->
                # vẫn dịch nháp bình thường.
                if src_lang == "ja" and not is_final:
                    await websocket.send_text(json.dumps({
                        "id": msg_id,
                        "src": merged,
                        "dst": "",
                        "final": False,
                        "pending": True,     # frontend: hiện "đang nghe…"
                    }, ensure_ascii=False))
                    continue

                if is_final and post.is_duplicate(merged):
                    if VERBOSE:
                        print(f"🔁 Bỏ trùng: {merged}")
                    continue

                # ĐỢT-2 — đo thời gian dịch, chỉ để LOG.
                t_mt = time.perf_counter()
                text_dst, score = await asyncio.to_thread(
                    translate, merged, src_lang, tgt_lang, is_final, post.cache)
                mt_ms = (time.perf_counter() - t_mt) * 1000

                gate = MIN_LOGPROB_FINAL if is_final else MIN_LOGPROB_PARTIAL
                if not text_dst or score < gate:
                    if VERBOSE:
                        print(f"🔇 Bỏ (score={score:.2f} < {gate}): {merged} → {text_dst}")
                    continue

                t_post = time.perf_counter()
                text_dst = post.finish(merged, text_dst, src_lang, tgt_lang)
                post_ms = (time.perf_counter() - t_post) * 1000

                if is_final:
                    write_log(merged, text_dst, src_lang, tgt_lang)
                if VERBOSE:
                    tag = "FINAL" if is_final else "nháp "
                    print(f"[{tag}][{src_lang}] {merged}")
                    print(f"[{tag}][{tgt_lang}] {text_dst}  (score={score:.2f})")
                    # ĐO-E2E — thời gian từng câu, tính TỪ LÚC VAD CHỐT ĐOẠN.
                    # Chưa gồm min_silence (khoảng chờ im lặng để VAD quyết định
                    # chốt) — muốn latency người dùng cảm nhận thì cộng thêm
                    # ~prof['min_silence'] giây nữa. Với câu gộp nhiều đoạn VAD
                    # (continuation), queue/asr/audio là số của ĐOẠN CUỐI CÙNG.
                    e2e_ms = (time.perf_counter() - t_seg) * 1000
                    print(f"⏱️  #{msg_id} {tag.strip()} "
                          f"| audio {samples.size / SAMPLE_RATE:.1f}s "
                          f"| queue {queue_ms:.0f}ms | asr {asr_ms:.0f}ms "
                          f"| mt {mt_ms:.0f}ms | post {post_ms:.0f}ms "
                          f"| e2e {e2e_ms:.0f}ms "
                          f"(+~{prof['min_silence']:.1f}s VAD chờ im lặng)")

                await websocket.send_text(json.dumps({
                    "id": msg_id,
                    "src": merged,
                    "dst": text_dst,
                    "final": is_final,
                    "pending": False,
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
    return {
        "status": "ok",
        "mt_version": MODEL_VERSION,
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
        "mt": {"engine": "ctranslate2", "arch": f"M2M-100 418M + LoRA {MODEL_VERSION}",
               "quant": "int8", "device": "cpu",
               "beam": {"final": BEAM_FINAL, "partial": BEAM_PARTIAL},
               "len_mult": {f"{a}-{b}": v for (a, b), v in LEN_MULT.items()},
               "ja_partial_translation": False},
        "vad": {"engine": "silero", "format": "onnx"},
        "asr_gate": {"min_logprob": MIN_ASR_LOGPROB,
                     "note": "segment ASR duoi nguong bi bo truoc khi dich; -99 = tat"},
        "glossary_entries": len(GLOSSARY.entries),
    }


if __name__ == "__main__":
    print(f"🚀 http://{HOST}:{PORT}  |  ws://{HOST}:{PORT}/ws/audio/{{ja,vi}}")
    if TRANSCRIPT_LOG:
        print("⚠️  TRANSCRIPT_LOG ĐANG BẬT — nội dung phát ngôn sẽ được ghi ra đĩa.")
    uvicorn.run(app, host=HOST, port=PORT, ws_ping_interval=20, ws_ping_timeout=20)