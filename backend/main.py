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

from postprocess import Glossary, Lexicon, PostProcessor, TranslationCache
from segmenter import LiveSegment, SentenceBuffer, hard_cuts

app = FastAPI(title="KaTOBA BridgeAI Backend")

# ---------------------------------------------------------------------------
# ĐƯỜNG DẪN
# ---------------------------------------------------------------------------

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

# Thư mục ghi được (Electron truyền KATOBA_DATA_DIR). BASE_DIR nằm trong gói cài, không ghi được.
_data_dir_env = os.environ.get("KATOBA_DATA_DIR", "").strip()
DATA_DIR = Path(_data_dir_env) if _data_dir_env else BASE_DIR

try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    DATA_DIR = BASE_DIR

# Có thể đặt model ngoài gói cài.
_models_dir_env = os.environ.get("KATOBA_MODELS_DIR", "").strip()
MODELS_DIR = Path(_models_dir_env) if _models_dir_env else BASE_DIR / "models"

MODEL_JA_DIR = MODELS_DIR / "parakeet-ja"
MODEL_JA_FILE = MODEL_JA_DIR / "model.int8.onnx"
TOKENS_JA_FILE = MODEL_JA_DIR / "tokens.txt"

MODEL_VI_DIR = MODELS_DIR / "zipformer-vi"
VI_ENCODER = MODEL_VI_DIR / "encoder.int8.onnx"
VI_DECODER = MODEL_VI_DIR / "decoder.onnx"
VI_JOINER = MODEL_VI_DIR / "joiner.int8.onnx"
VI_TOKENS = MODEL_VI_DIR / "tokens.txt"

# ASR tiếng Anh, không bắt buộc: thiếu thư mục thì chỉ tắt chiều en.
MODEL_EN_DIR = MODELS_DIR / "parakeet-en"
EN_ENCODER = MODEL_EN_DIR / "encoder.int8.onnx"
EN_DECODER = MODEL_EN_DIR / "decoder.int8.onnx"
EN_JOINER = MODEL_EN_DIR / "joiner.int8.onnx"
EN_TOKENS = MODEL_EN_DIR / "tokens.txt"

# KATOBA_MT_DIR: trỏ sang bản MT khác để so A/B.
_mt_dir_env = os.environ.get("KATOBA_MT_DIR", "").strip()
M2M100_DIR = Path(_mt_dir_env) if _mt_dir_env else MODELS_DIR / "m2m100_418M_int8"
SILERO_VAD_FILE = MODELS_DIR / "silero_vad.onnx"
GLOSSARY_FILE = BASE_DIR / "glossary.json"
EVERYDAY_FILE = BASE_DIR / "everyday.json"

# Danh sách người dự họp, không bắt buộc (TEN_NGUOI_VA_NGAT_CAU.md mục 1).
_people_env = os.environ.get("KATOBA_PEOPLE_FILE", "").strip()
PEOPLE_FILE = Path(_people_env) if _people_env else BASE_DIR / "people.json"
LOG_FILE = DATA_DIR / "transcript_log.txt"

MODEL_VERSION = "v9"          # LoRA v9: 4 chiều ja↔vi, en↔vi (BAO_CAO_MT_v9.md)

# ---------------------------------------------------------------------------
# CẤU HÌNH
# ---------------------------------------------------------------------------

HOST = os.environ.get("KATOBA_HOST", "127.0.0.1")
PORT = int(os.environ.get("KATOBA_PORT", "8765"))

SAMPLE_RATE = 16000

TRANSCRIPT_LOG = os.environ.get("KATOBA_TRANSCRIPT_LOG", "0") == "1"
VERBOSE = os.environ.get("KATOBA_VERBOSE", "0") == "1"

def _vad(name: str, default: float) -> float:
    """Tham số VAD đọc từ env — chỉnh tại chỗ khi họp mà không phải build lại."""
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


# cut_silence: VAD cắt đoạn đưa đi ASR. min_silence: chốt câu chưa có dấu hiệu hết câu.
# max_speech: trần độ dài một đoạn. Lý do chọn số: TEN_NGUOI_VA_NGAT_CAU.md mục 2 và 4.
VAD_PROFILES = {
    "system": {
        "threshold":   _vad("KATOBA_VAD_THRESHOLD_SYSTEM", 0.45),
        "cut_silence": _vad("KATOBA_VAD_CUT_SYSTEM", 0.30),
        "min_silence": _vad("KATOBA_VAD_SILENCE_SYSTEM", 0.90),
        "min_speech":  _vad("KATOBA_VAD_MIN_SPEECH_SYSTEM", 0.25),
        "max_speech":  _vad("KATOBA_VAD_MAX_SPEECH", 6.0),
    },
    # Micro: ngưỡng cao hơn (tiếng gõ phím), khoảng dừng dài hơn.
    "microphone": {
        "threshold":   _vad("KATOBA_VAD_THRESHOLD_MIC", 0.65),
        "cut_silence": _vad("KATOBA_VAD_CUT_MIC", 0.40),
        "min_silence": _vad("KATOBA_VAD_SILENCE_MIC", 1.00),
        "min_speech":  _vad("KATOBA_VAD_MIN_SPEECH_MIC", 0.30),
        "max_speech":  _vad("KATOBA_VAD_MAX_SPEECH", 6.0),
    },
}

# Im lặng tới mức này thì chốt cả phần câu còn lửng.
VAD_HARD_SILENCE = _vad("KATOBA_VAD_HARD_SILENCE", 3.0)

# Bản xem trước: nhận dạng + dịch nháp phần đang nói dở, mỗi LIVE_STEP giây. KATOBA_LIVE=0 để tắt.
LIVE_PREVIEW = os.environ.get("KATOBA_LIVE", "1") == "1"
LIVE_STEP = _vad("KATOBA_LIVE_STEP", 0.4)
LIVE_MIN_SPEECH = 0.6          # ngắn hơn mức này ASR chưa ra chữ gì có nghĩa

# Nhiễu trắng rất nhỏ cho ASR tiếng Nhật: Parakeet-JA nuốt câu khi gặp lặng tuyệt đối.
ASR_DITHER = float(os.environ.get("KATOBA_ASR_DITHER", "3e-4"))
_DITHER_NOISE = np.random.default_rng(7).standard_normal(SAMPLE_RATE * 30).astype(np.float32)

SEGMENT_QUEUE_MAX = 6

# Ngưỡng điểm riêng cho bản nháp và bản chốt.
MIN_LOGPROB_FINAL = float(os.environ.get("KATOBA_MIN_LOGPROB", "-3.0"))
MIN_LOGPROB_PARTIAL = MIN_LOGPROB_FINAL - 1.0

# Gate ASR: bỏ đoạn có avg logprob dưới ngưỡng trước khi dịch. -99 = tắt.
MIN_ASR_LOGPROB = float(os.environ.get("KATOBA_MIN_ASR_LOGPROB", "-1.0"))
# Chiều EN chưa có log họp thật để calibrate -> mặc định TẮT gate (-99).
MIN_ASR_LOGPROB_EN = float(os.environ.get("KATOBA_MIN_ASR_LOGPROB_EN", "-99"))

# Hệ số nở token theo chiều: đích tiếng Việt cần nhiều token, đích tiếng Nhật cần ít.
LEN_MULT = {("ja", "vi"): 4.0, ("vi", "ja"): 2.0,
            ("en", "vi"): 3.0, ("vi", "en"): 2.0}

# Các chiều được hỗ trợ; chiều khác bị endpoint từ chối.
ALLOWED_DIRECTIONS = set(LEN_MULT)

# Chiều dịch mặc định khi client không gửi ?target= (giữ tương thích bản cũ).
DEFAULT_TARGET = {"ja": "vi", "vi": "ja", "en": "vi"}

BEAM_FINAL = 4
BEAM_PARTIAL = 1          # bản nháp: đổi chất lượng lấy độ trễ

# Dịch câu chốt kèm câu liền trước làm ngữ cảnh. Mặc định TẮT: trên lời nói thật không hơn
# dịch riêng lẻ mà thêm lỗi (TEN_NGUOI_VA_NGAT_CAU.md mục 5). Bật: KATOBA_MT_CONTEXT=1.
MT_CONTEXT = os.environ.get("KATOBA_MT_CONTEXT", "0") == "1"
BEAM_CONTEXT = 2
CONTEXT_DIRECTIONS = {("ja", "vi")}
CONTEXT_MIN_CHARS = 10        # câu hiện tại ngắn hơn thì dịch riêng
CONTEXT_MAX_PREV_CHARS = 80   # câu trước dài hơn thì bỏ: prefix dài, chậm, dễ lệch
CONTEXT_MAX_AGE_SEC = 20.0    # câu trước nói xong quá lâu thì không còn là ngữ cảnh

MIN_RAM_GB = 1.5

STARTUP_ERROR_FILE = DATA_DIR / "startup_error.log"


# ---------------------------------------------------------------------------
# THOÁT CÓ DẤU VẾT
# ---------------------------------------------------------------------------

def _fatal(*lines: str) -> None:
    """Ghi lỗi chí mạng ra đĩa rồi thoát (không có console thì print() mất)."""
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


def _has_en() -> bool:
    return all(p.exists() for p in (EN_ENCODER, EN_DECODER, EN_JOINER, EN_TOKENS))


def _check_ram() -> None:
    try:
        import psutil
    except ImportError:
        print("ℹ️  Không có psutil, bỏ qua kiểm tra RAM")
        return
    avail = psutil.virtual_memory().available / 1e9
    print(f"💾 RAM trống: {avail:.2f} GB")
    if avail < MIN_RAM_GB:
        _fatal(f"❌ Cần tối thiểu {MIN_RAM_GB} GB trống để nạp model "
               f"(đang trống {avail:.2f} GB).",
               "   Đóng bớt ứng dụng rồi thử lại.")


def _rss_gb() -> float:
    try:
        import psutil
        return psutil.Process(os.getpid()).memory_info().rss / 1e9
    except Exception:
        pass
    # Không có psutil thì hỏi thẳng Windows.
    try:
        import ctypes
        from ctypes import wintypes

        class _Counters(ctypes.Structure):
            _fields_ = ([("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)]
                        + [(name, ctypes.c_size_t) for name in (
                            "PeakWorkingSetSize", "WorkingSetSize",
                            "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                            "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
                            "PagefileUsage", "PeakPagefileUsage")])

        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.windll.psapi
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(_Counters), wintypes.DWORD]
        counters = _Counters()
        counters.cb = ctypes.sizeof(_Counters)
        if psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(),
                                      ctypes.byref(counters), counters.cb):
            return counters.WorkingSetSize / 1e9
    except Exception:
        pass
    return 0.0


# ---------------------------------------------------------------------------
# NẠP MODEL — SONG SONG
# ---------------------------------------------------------------------------

def _load_ja():
    # Parakeet-JA nặng (RTF ~0.4 với 2 thread) nên cho nhiều thread hơn Zipformer-VI.
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


def _load_en():
    en_threads = int(os.environ.get("KATOBA_ASR_EN_THREADS", "4"))
    return sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=str(EN_ENCODER), decoder=str(EN_DECODER), joiner=str(EN_JOINER),
        tokens=str(EN_TOKENS), num_threads=en_threads, sample_rate=SAMPLE_RATE,
        feature_dim=80, decoding_method="greedy_search", provider="cpu",
        model_type="nemo_transducer",
    )


def _load_mt():
    """Nạp MT + tokenizer từ đĩa, không tải từ Internet. Mỗi chiều một tokenizer nên không cần lock."""
    try:
        tokenizers = {lang: AutoTokenizer.from_pretrained(str(M2M100_DIR),
                                                          local_files_only=True)
                      for lang in ("ja", "vi", "en")}
    except Exception as err:
        _fatal("❌ Không nạp được tokenizer từ thư mục model.",
               f"   {M2M100_DIR}",
               f"   Lỗi: {err}",
               "   Thư mục CT2 thiếu file tokenizer -> sửa ở bước convert:",
               "   ct2-transformers-converter ... --copy_files "
               "sentencepiece.bpe.model vocab.json tokenizer_config.json")

    for lang, tok in tokenizers.items():
        tok.src_lang = lang

    # inter_threads=2: hai chiều dịch song song. intra_threads: KATOBA_MT_THREADS.
    mt_threads = int(os.environ.get("KATOBA_MT_THREADS", "2"))
    tr = ctranslate2.Translator(str(M2M100_DIR), device="cpu",
                                compute_type="int8", inter_threads=2,
                                intra_threads=mt_threads)
    return tr, tokenizers


_check_files()
_check_ram()

HAS_EN = _has_en()
if not HAS_EN:
    print(f"ℹ️  Không có ASR tiếng Anh tại {MODEL_EN_DIR} — tắt chiều en")

# Chỉ nạp sẵn ASR của ngôn ngữ trong KATOBA_PRELOAD; còn lại nạp ở phiên đầu dùng tới.
_ASR_LOADERS = {"ja": _load_ja, "vi": _load_vi}
if HAS_EN:
    _ASR_LOADERS["en"] = _load_en

PRELOAD = [lang for lang in _ASR_LOADERS
           if lang in {x.strip() for x in
                       os.environ.get("KATOBA_PRELOAD", "ja,vi").split(",")}]


class Recognizers:
    """Ngôn ngữ nói -> (recognizer, lock), dùng như dict; chưa nạp thì nạp khi lấy lần đầu."""

    def __init__(self, loaders: dict, loaded: dict):
        self._loaders = loaders
        self._loaded = dict(loaded)
        self._locks = {lang: Lock() for lang in loaders}    # khoá lúc nhận dạng
        self._loading = Lock()

    def __contains__(self, lang: str) -> bool:
        return lang in self._loaders

    def __iter__(self):
        return iter(self._loaders)

    def loaded(self) -> list[str]:
        return sorted(self._loaded)

    def __getitem__(self, lang: str):
        # Hai phiên cùng mở một ngôn ngữ chưa nạp: phiên sau chờ phiên trước.
        with self._loading:
            if lang not in self._loaded:
                t0 = time.time()
                print(f"⏳ Nạp ASR {lang} (lần đầu dùng tới)...")
                self._loaded[lang] = self._loaders[lang]()
                print(f"✅ ASR {lang} sẵn sàng sau {time.time() - t0:.1f}s "
                      f"(RAM tổng {_rss_gb():.2f} GB)")
        return self._loaded[lang], self._locks[lang]


print(f"⏳ Nạp song song: ASR {', '.join(PRELOAD) or '(không)'} + MT {MODEL_VERSION}...")
print(f"🔧 VERBOSE={'BẬT' if VERBOSE else 'TẮT'} | TRANSCRIPT_LOG={'BẬT' if TRANSCRIPT_LOG else 'TẮT'}"
      f"   (bật log chi tiết: chạy  $env:KATOBA_VERBOSE=\"1\"  trong CÙNG cửa sổ PowerShell trước khi python main.py)")
_t0 = time.time()
_rss0 = _rss_gb()

with ThreadPoolExecutor(max_workers=4) as _pool:
    _f_asr = {lang: _pool.submit(_ASR_LOADERS[lang]) for lang in PRELOAD}
    _f_mt = _pool.submit(_load_mt)
    RECOGNIZERS = Recognizers(_ASR_LOADERS,
                              {lang: f.result() for lang, f in _f_asr.items()})
    translator, TOKENIZERS = _f_mt.result()

_later = [lang for lang in _ASR_LOADERS if lang not in PRELOAD]
if _later:
    print(f"ℹ️  ASR {', '.join(_later)} sẽ nạp khi có phiên đầu tiên dùng tới")
# FIX-v5 (4) — không còn translator_lock. CT2 Translator tự an toàn đa luồng.

print(f"✅ Nạp xong sau {time.time() - _t0:.1f}s "
      f"(RAM +{_rss_gb() - _rss0:.2f} GB, tổng {_rss_gb():.2f} GB)")

# Khởi động ngon -> dọn dấu vết lần chết trước, tránh hỗ trợ đọc nhầm log cũ.
try:
    STARTUP_ERROR_FILE.unlink(missing_ok=True)
except Exception:
    pass

GLOSSARY = Glossary.load(GLOSSARY_FILE, PEOPLE_FILE)
LEXICON = Lexicon.load(EVERYDAY_FILE)
SHARED_CACHE = TranslationCache(maxsize=1024)


def _lang_token(tok, code: str) -> str:
    mapping = getattr(tok, "lang_code_to_token", None)
    if isinstance(mapping, dict) and code in mapping:
        return mapping[code]
    return f"__{code}__"


# ---------------------------------------------------------------------------
# BỘ ĐỆM CÂU
# ---------------------------------------------------------------------------

# Quy tắc chốt câu nằm ở segmenter.py.

# Độ dài tối thiểu để dịch NHÁP (bản chốt luôn được dịch).
MIN_PARTIAL_CHARS = int(os.environ.get("KATOBA_MIN_PARTIAL_CHARS", "8"))
MIN_PARTIAL_BY_LANG = {"ja": max(3, MIN_PARTIAL_CHARS - 3),
                       "vi": MIN_PARTIAL_CHARS, "en": MIN_PARTIAL_CHARS}


# ---------------------------------------------------------------------------
# ASR / DỊCH
# ---------------------------------------------------------------------------

# Cấm token kana/kanji/hangul khi đích không phải tiếng Nhật: model đôi khi chép nguyên chữ nguồn.
_CJK_RE = re.compile(r"[぀-ヿ一-鿿ｦ-ﾟ가-힯]")
_NO_CJK = [[t] for t in TOKENIZERS["ja"].get_vocab() if _CJK_RE.search(t)]
_SUPPRESS = {"vi": _NO_CJK, "en": _NO_CJK}

# Số ký tự đích tối đa cho mỗi ký tự nguồn trước khi coi bản dịch là bịa/lặp.
_MAX_EXPANSION = {("ja", "vi"): 8.0, ("vi", "ja"): 2.5,
                  ("en", "vi"): 3.5, ("vi", "en"): 3.5}


def plausible(src: str, dst: str, src_lang: str, tgt_lang: str) -> bool:
    """Lưới an toàn cho bản dịch: rỗng, sót chữ Nhật, hoặc dài bất thường thì loại."""
    if not dst.strip():
        return False
    if tgt_lang != "ja" and _CJK_RE.search(dst):
        return False
    limit = _MAX_EXPANSION.get((src_lang, tgt_lang), 6.0)
    return len(dst) <= max(40, len(src) * limit)


def _pieces(tok, text: str) -> list[str]:
    """Token của `text`, bỏ token ngôn ngữ ở đầu và </s> ở cuối."""
    return tok.convert_ids_to_tokens(tok.encode(text))[1:-1]


def _with_context(prev: str, text: str, lang: str) -> str:
    if lang == "ja":
        return prev + ("" if prev[-1] in "。！？!?" else "。") + text
    return prev + (" " if prev[-1] in ".!?" else ". ") + text


_WORD_RE = re.compile(r"\w+")


def _looped(text: str) -> bool:
    """Cùng một cụm 1-4 từ lặp liền nhau từ 3 lần trở lên ("15 phút, 15 phút, 15 phút")."""
    words = [w.lower() for w in _WORD_RE.findall(text)]
    for n in (1, 2, 3, 4):
        for i in range(len(words) - 3 * n + 1):
            if words[i:i + n] == words[i + n:i + 2 * n] == words[i + 2 * n:i + 3 * n]:
                return True
    return False


def context_went_wrong(dst: str, prev_dst: str) -> bool:
    """Dịch kèm ngữ cảnh bị hỏng: lặp vòng, hoặc nhại lại câu trước."""
    if _looped(dst):
        return True
    words = [w.lower() for w in _WORD_RE.findall(dst)]
    seen = {w.lower() for w in _WORD_RE.findall(prev_dst)}
    return len(words) >= 3 and sum(w in seen for w in words) / len(words) >= 0.7


def split_phrases(post: PostProcessor, text: str, src_lang: str,
                  tgt_lang: str) -> tuple[list[str], str, list[str]]:
    """Tách câu cửa miệng ở đầu và cuối `text`. Trả (bản dịch đầu, phần còn phải dịch, bản dịch cuối)."""
    cuts = [0, *hard_cuts(text, src_lang), len(text)]
    pieces = [text[a:b] for a, b in zip(cuts, cuts[1:]) if a < b]
    fixed = [post.phrase(p, src_lang, tgt_lang) for p in pieces]
    lead, tail = 0, len(pieces)
    while lead < tail and fixed[lead]:
        lead += 1
    while tail > lead and fixed[tail - 1]:
        tail -= 1
    rest = "".join(pieces[lead:tail])
    return fixed[:lead], rest.lstrip("、。 ") if lead else rest, fixed[tail:]


def join_phrases(lead: list[str], dst: str, tail: list[str]) -> str:
    if lead:
        dst = dst[:1].upper() + dst[1:]
    if tail and dst[-1:] not in ".!?…":
        dst += "."
    return " ".join([*lead, dst, *tail])


_JA_TAIL_NE = re.compile(r"(です|ます|ました|でした|ません)ね(?=[。！？!?]*$)")


def translate_final(text: str, src_lang: str, tgt_lang: str,
                    context: tuple[str, str] | None = None) -> tuple[str, float]:
    """translate() cho câu chốt. Câu 〜ですね/ますね bị dịch thành câu hỏi thì bỏ ね rồi dịch lại."""
    dst, score = translate(text, src_lang, tgt_lang, True, None, context)
    if (src_lang, tgt_lang) == ("ja", "vi") and dst.rstrip().endswith("?"):
        plain = _JA_TAIL_NE.sub(r"\1", text)
        if plain != text:
            retry, retry_score = translate(plain, src_lang, tgt_lang, True, None, context)
            if retry and not retry.rstrip().endswith("?"):
                return retry, retry_score
    return dst, score


def recognize(recognizer, lock: Lock, samples: np.ndarray,
              dither: float = 0.0) -> tuple[str, float | None, float]:
    """Trả (text, avg_logprob hoặc None, thời gian ms)."""
    samples = np.ascontiguousarray(samples, dtype=np.float32)
    if dither:
        samples = samples + np.resize(_DITHER_NOISE, samples.size) * dither
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
              cache: TranslationCache | None = None,
              context: tuple[str, str] | None = None) -> tuple[str, float]:
    """
    Trả (bản dịch, log-prob trung bình mỗi token). Chuỗi rỗng = nên bỏ qua.
    context = (câu nguồn liền trước, bản dịch của nó) — xem MT_CONTEXT.
    """
    if not text:
        return "", 0.0

    # Chỉ cache bản chốt (bản nháp dịch beam 1, kém hơn).
    use_cache = cache is not None and is_final
    if use_cache:
        hit = cache.get(text, src_lang, tgt_lang)
        if hit is not None:
            return hit, 0.0

    tok = TOKENIZERS[src_lang]

    try:
        # Zipformer-VI xuất chữ HOA, model dịch được train trên chữ thường.
        text_for_model = text.lower() if src_lang == "vi" else text
        n_src = len(tok.encode(text_for_model))
        mult = LEN_MULT.get((src_lang, tgt_lang), 2.5)

        prefix = [_lang_token(tok, tgt_lang)]
        if context:
            prev_src, prev_dst = context
            prev_src = prev_src.lower() if src_lang == "vi" else prev_src
            text_for_model = _with_context(prev_src, text_for_model, src_lang)
            # Prefix phải kết bằng dấu câu, không thì model chèn dấu chấm vào đầu bản dịch mới.
            prev_dst = prev_dst.rstrip()
            if prev_dst and prev_dst[-1] not in ".!?…。！？":
                prev_dst += "。" if tgt_lang == "ja" else "."
            prefix += _pieces(TOKENIZERS[tgt_lang], prev_dst)
        source_tokens = tok.convert_ids_to_tokens(tok.encode(text_for_model))

        results = translator.translate_batch(
            [source_tokens],
            target_prefix=[prefix],
            beam_size=(BEAM_PARTIAL if not is_final
                       else BEAM_CONTEXT if context else BEAM_FINAL),
            # Luật chống lặp xét cả prefix nên phải nới khi có ngữ cảnh.
            repetition_penalty=1.05 if context else 1.1,
            no_repeat_ngram_size=0 if context else 3,
            # Trần độ dài tính riêng cho câu hiện tại, cộng phần prefix đã ép.
            max_decoding_length=len(prefix) - 1 + min(128, int(n_src * mult) + 12),
            min_decoding_length=1,
            length_penalty=1.0,
            suppress_sequences=_SUPPRESS.get(tgt_lang),
            return_scores=True,
        )

        full_hyp = results[0].hypotheses[0]
        hyp = full_hyp[len(prefix):]             # bỏ token ngôn ngữ + ngữ cảnh đã ép
        if not hyp:
            return "", -99.0

        # Chuẩn hoá điểm theo độ dài đầy đủ (gồm cả token ngôn ngữ).
        score = results[0].scores[0] / max(1, len(full_hyp))

        out = tok.decode(tok.convert_tokens_to_ids(hyp),
                         skip_special_tokens=True).strip()
        if context:
            out = out.lstrip(" .,;:!?…。、")

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

def _report_unknown_names(post: PostProcessor) -> None:
    """In những tên người chưa khai trong people.json."""
    unknown = post.names.unknown
    if not unknown:
        return
    top = sorted(unknown.items(), key=lambda kv: kv[1], reverse=True)[:15]
    print(f"👤 Tên chưa khai trong {PEOPLE_FILE.name} "
          f"({len(unknown)} tên, hiện 15 tên xuất hiện nhiều nhất):")
    for name, n in top:
        print(f"   • {name}  ×{n}")


async def handle_stream(websocket: WebSocket, recognizer, recognizer_lock: Lock,
                        src_lang: str, tgt_lang: str) -> None:
    source = websocket.query_params.get("source", "system")
    if source not in VAD_PROFILES:
        source = "system"
    prof = VAD_PROFILES[source]

    # cut_silence > min_silence là vô nghĩa -> coi như bằng nhau.
    hold_silence = prof["min_silence"]
    cut_silence = min(prof["cut_silence"], hold_silence)
    hard_silence = max(VAD_HARD_SILENCE, hold_silence)

    print(f"🔌 Kết nối {src_lang.upper()}→{tgt_lang.upper()} | nguồn={source} "
          f"| VAD thr={prof['threshold']} cắt={cut_silence}s "
          f"chốt={hold_silence}s trần={prof['max_speech']}s")

    vad_config = sherpa_onnx.VadModelConfig()
    vad_config.silero_vad.model = str(SILERO_VAD_FILE)
    vad_config.silero_vad.threshold = prof["threshold"]
    vad_config.silero_vad.min_silence_duration = cut_silence
    vad_config.silero_vad.min_speech_duration = prof["min_speech"]
    vad_config.silero_vad.max_speech_duration = prof["max_speech"]
    vad_config.sample_rate = SAMPLE_RATE
    window_size = vad_config.silero_vad.window_size
    vad = sherpa_onnx.VoiceActivityDetector(vad_config, buffer_size_in_seconds=30)

    # Hai mốc chốt câu, tính bằng số mẫu âm thanh kể từ lúc VAD đóng đoạn.
    soft_after = int((hold_silence - cut_silence) * SAMPLE_RATE)
    hard_after = int((hard_silence - cut_silence) * SAMPLE_RATE)

    asr_gate = MIN_ASR_LOGPROB_EN if src_lang == "en" else MIN_ASR_LOGPROB
    asr_dither = ASR_DITHER if src_lang == "ja" else 0.0
    queue: asyncio.Queue = asyncio.Queue(maxsize=SEGMENT_QUEUE_MAX)
    post = PostProcessor(GLOSSARY, cache=SHARED_CACHE, lexicon=LEXICON)
    # Bản nháp dùng PostProcessor riêng để không làm sai bộ đếm của bản chốt.
    draft_post = PostProcessor(GLOSSARY, cache=TranslationCache(maxsize=1),
                               lexicon=LEXICON)
    buffer = SentenceBuffer(src_lang)
    live = LiveSegment()
    dropped = 0
    # Thời gian (giây) của lượt xem trước gần nhất; producer giãn nhịp theo số này.
    preview_cost = 0.0

    # id đang hiện ở dạng chưa chốt -> (câu nguồn, bản nháp).
    on_screen: dict[int, tuple[str, str]] = {}
    # Bản dịch nháp theo câu nguồn, khỏi dịch lại câu không đổi.
    draft_memo: dict[str, str] = {}
    # (câu nguồn, bản dịch, thời điểm) của câu chốt gần nhất — ngữ cảnh cho câu sau.
    last_final: tuple[str, str, float] | None = None

    # Ảnh chụp mới nhất của đoạn đang nói dở; ảnh mới đè ảnh cũ.
    snapshot: np.ndarray | None = None
    wake = asyncio.Event()

    def enqueue(item: tuple) -> None:
        nonlocal dropped
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
        queue.put_nowait(item)
        wake.set()

    async def producer() -> None:
        nonlocal snapshot
        pending = np.zeros(0, dtype=np.float32)
        quiet = 0          # số mẫu kể từ khi VAD thôi thấy tiếng nói
        flush_stage = 2    # 0: chưa báo mốc nào | 1: đã báo mốc thường | 2: đã báo cả hai
        speech = 0         # số mẫu của đoạn đang nói dở
        peeked = 0         # giá trị `speech` lúc chụp ảnh gần nhất
        live_min = int(LIVE_MIN_SPEECH * SAMPLE_RATE)
        live_step = int(LIVE_STEP * SAMPLE_RATE)
        while True:
            data = await websocket.receive_bytes()
            chunk = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
            if chunk.size == 0:
                continue

            pending = np.concatenate([pending, chunk])
            while pending.size >= window_size:
                vad.accept_waveform(np.ascontiguousarray(pending[:window_size]))
                pending = pending[window_size:]
                if vad.is_speech_detected():
                    quiet, flush_stage = 0, 0
                    speech += window_size
                else:
                    quiet += window_size
                    speech = peeked = 0

            while not vad.empty():
                samples = np.ascontiguousarray(
                    np.array(vad.front.samples, dtype=np.float32))
                vad.pop()
                # Đoạn đã đóng thì ảnh chụp dở của nó hết giá trị.
                snapshot = None
                speech = peeked = 0
                # Thời điểm VAD chốt đoạn, để đo e2e.
                enqueue(("segment", samples, time.perf_counter()))

            step = max(live_step, int(1.5 * preview_cost * SAMPLE_RATE))
            if (LIVE_PREVIEW and speech >= live_min
                    and speech - peeked >= step):
                peeked = speech
                current = np.array(vad.current_segment.samples, dtype=np.float32)
                # Người nói vừa ngừng thì VAD sắp đóng đoạn: không bắt đầu lượt xem trước.
                tail = current[-int(0.15 * SAMPLE_RATE):]
                trailing_off = (float(np.sqrt(np.mean(tail * tail)))
                                < 0.2 * float(np.sqrt(np.mean(current * current))))
                if current.size >= live_min and not trailing_off:
                    snapshot = current
                    wake.set()

            # Đặt SAU vòng lấy đoạn: mốc chốt phải xếp hàng sau đoạn mà nó chốt.
            if flush_stage == 0 and quiet >= soft_after:
                enqueue(("flush", False, time.perf_counter()))
                flush_stage = 1
            if flush_stage == 1 and quiet >= hard_after:
                enqueue(("flush", True, time.perf_counter()))
                flush_stage = 2

    async def send(msg_id: int, src: str, dst: str, final: bool, **flags) -> None:
        await websocket.send_text(json.dumps({
            "id": msg_id,
            "src": src,
            "dst": dst,
            "final": final,
            "pending": False,
            **flags,
        }, ensure_ascii=False))

    async def retract(msg_id: int) -> None:
        """Báo frontend gỡ một dòng chưa chốt không còn ứng với câu nào."""
        if msg_id in on_screen:
            del on_screen[msg_id]
            await send(msg_id, "", "", True, dropped=True)

    async def show(msg_id: int, text: str, dst: str) -> None:
        """Hiện/cập nhật một dòng CHƯA chốt. Không gửi lại nếu không có gì đổi."""
        if on_screen.get(msg_id) == (text, dst):
            return
        on_screen[msg_id] = (text, dst)
        if dst:
            await send(msg_id, text, dst, False)
        else:
            await send(msg_id, text, "", False, pending=True)

    async def emit_draft(msg_id: int, text: str) -> None:
        """Bản nháp cho câu còn đang nói: dịch nhanh (beam 1), sẽ bị bản chốt thay."""
        shown = on_screen.get(msg_id, ("", ""))[1]

        # Quá ngắn thì model bịa câu -> chỉ hiện câu nguồn, giữ bản nháp cũ nếu có.
        text_clean = draft_post.for_model(text, src_lang)
        if len(text) < MIN_PARTIAL_BY_LANG[src_lang] or not text_clean:
            await show(msg_id, text, shown)
            return

        dst = draft_memo.get(text) or draft_post.phrase(text_clean, src_lang, tgt_lang)
        if dst is None:
            text_mt, word_map = draft_post.protect_words(text_clean, src_lang, tgt_lang)
            text_mt, name_map = draft_post.protect_names(text_mt, src_lang)
            raw_dst, score = await asyncio.to_thread(
                translate, text_mt, src_lang, tgt_lang, False, None)
            if (score < MIN_LOGPROB_PARTIAL
                    or not plausible(text_mt, raw_dst, src_lang, tgt_lang)):
                await show(msg_id, text, shown)
                return
            dst, _lost = draft_post.restore_words(raw_dst, word_map)
            dst, _lost = draft_post.restore_names(dst, name_map)
            dst = draft_post.finish(text, dst, src_lang, tgt_lang)
            if len(draft_memo) > 64:
                draft_memo.clear()
            draft_memo[text] = dst

        await show(msg_id, text, dst)

    def pick_context(text_clean: str) -> tuple[str, str] | None:
        if not (MT_CONTEXT and last_final
                and (src_lang, tgt_lang) in CONTEXT_DIRECTIONS):
            return None
        prev_src, prev_dst, when = last_final
        if (len(text_clean) < CONTEXT_MIN_CHARS
                or len(prev_src) > CONTEXT_MAX_PREV_CHARS
                or time.time() - when > CONTEXT_MAX_AGE_SEC):
            return None
        return prev_src, prev_dst

    async def emit_final(msg_id: int, text: str, t_seg: float, timing: str) -> None:
        """Câu đã trọn: dịch lại cả câu từ nguyên văn rồi thay dòng nháp."""
        nonlocal last_final

        if post.is_duplicate(text):
            if VERBOSE:
                print(f"🔁 Bỏ trùng: {text}")
            await retract(msg_id)
            return

        # Bỏ tiếng đệm khỏi bản đưa cho model; đoạn chỉ có tiếng đệm thì không dịch.
        text_clean = post.for_model(text, src_lang)
        if not text_clean:
            if VERBOSE:
                print(f"🔇 Chỉ có tiếng đệm, bỏ: {text!r}")
            await retract(msg_id)
            return

        # Câu cửa miệng, từ đời thường, tên người: chỉ đổi text đưa cho model, `text` hiển thị giữ nguyên.
        lead, text_rest, tail = split_phrases(post, text_clean, src_lang, tgt_lang)
        text_lx, word_map = post.protect_words(text_rest, src_lang, tgt_lang)
        text_mt, name_map = post.protect_names(text_lx, src_lang)

        t_mt = time.perf_counter()
        text_dst, score, used_context = "", -99.0, False

        cache_key = text_mt
        cached = post.cache.get(cache_key, src_lang, tgt_lang)
        if not text_rest:
            text_dst, score, lead, tail = " ".join(lead + tail), 0.0, [], []
        elif cached is not None:
            text_dst, score = post.restore_words(cached, word_map)[0], 0.0
        else:
            # Lùi dần: kèm ngữ cảnh (nếu bật) -> dịch thường -> dịch không dùng từ đời thường.
            context = pick_context(text_rest)
            attempts = [(True, context)] if context else []
            attempts.append((True, None))
            if word_map:
                attempts.append((False, None))

            for use_words, ctx in attempts:
                words = word_map
                if not use_words:
                    words = {}
                    text_mt, name_map = post.protect_names(text_rest, src_lang)
                mt_in = text_mt
                candidate, cand_score = await asyncio.to_thread(
                    translate_final, mt_in, src_lang, tgt_lang, ctx)
                restored, words_lost = post.restore_words(candidate, words)
                if (cand_score >= MIN_LOGPROB_FINAL
                        and plausible(mt_in, candidate, src_lang, tgt_lang)
                        and not words_lost
                        and not (ctx and context_went_wrong(candidate, ctx[1]))):
                    text_dst, score, used_context = restored, cand_score, bool(ctx)
                    post.cache.put(cache_key, src_lang, tgt_lang, candidate)
                    break
                if VERBOSE:
                    print(f"🔇 Bản dịch bị loại (score={cand_score:.2f}, "
                          f"mất {words_lost} từ): {text} → {candidate}")
        mt_ms = (time.perf_counter() - t_mt) * 1000

        if not text_dst:
            # Dịch hỏng: giữ bản nháp làm bản chốt nếu có, không thì gỡ dòng.
            draft = on_screen.get(msg_id, ("", ""))[1]
            if draft:
                del on_screen[msg_id]
                if VERBOSE:
                    print(f"↩️  #{msg_id} giữ bản nháp làm bản chốt: {text} → {draft}")
                await send(msg_id, text, draft, True)
            else:
                await retract(msg_id)
            return

        # Bung tên người trước finish() để glossary làm việc trên tên thật.
        text_dst, names_lost = post.restore_names(text_dst, name_map)
        if names_lost:
            print(f"⚠️  M2M-100 nuốt mất {names_lost} tên người trong: "
                  f"{text!r} → {text_dst!r}. "
                  f"Khai những tên này trong {PEOPLE_FILE.name} để "
                  f"chúng đi qua bằng dạng Latin thay vì placeholder.")

        t_post = time.perf_counter()
        text_dst = post.finish(text, join_phrases(lead, text_dst, tail), src_lang, tgt_lang)
        post_ms = (time.perf_counter() - t_post) * 1000

        write_log(text, text_dst, src_lang, tgt_lang)
        on_screen.pop(msg_id, None)
        last_final = (text_clean, text_dst, time.time())

        if VERBOSE:
            print(f"[FINAL][{src_lang}] {text}")
            print(f"[FINAL][{tgt_lang}] {text_dst}  (score={score:.2f}"
                  f"{', có ngữ cảnh' if used_context else ''})")
            # Thời gian tính từ lúc VAD chốt đoạn, chưa gồm khoảng chờ im lặng.
            e2e_ms = (time.perf_counter() - t_seg) * 1000
            print(f"⏱️  #{msg_id} FINAL | {timing} "
                  f"| mt {mt_ms:.0f}ms | post {post_ms:.0f}ms "
                  f"| e2e {e2e_ms:.0f}ms")

        await send(msg_id, text, text_dst, True)

    async def emit_units(units: list[tuple[int, str, bool]],
                         t_seg: float, timing: str) -> None:
        """Câu chốt -> dịch lại cả câu; phần còn dở -> bản nháp. Rồi dọn dòng thừa."""
        for msg_id, text, is_final in units:
            if is_final:
                await emit_final(msg_id, text, t_seg, timing)
            else:
                await emit_draft(msg_id, text)
        await prune({msg_id for msg_id, _text, is_final in units if not is_final})

    async def prune(alive: set[int]) -> None:
        """Gỡ mọi dòng chưa chốt không nằm trong `alive` (và không phải phần dở của bộ đệm)."""
        if buffer.tail:
            alive = alive | {buffer.tail_id}
        for msg_id in [i for i in on_screen if i not in alive]:
            await retract(msg_id)

    async def asr(samples: np.ndarray) -> tuple[str, float]:
        """Nhận dạng + gate. Trả ("", ms) nếu không có gì dùng được."""
        # ĐỢT-2 — recognize() trả kèm logprob + thời gian, chỉ để LOG.
        raw, asr_score, asr_ms = await asyncio.to_thread(
            recognize, recognizer, recognizer_lock, samples, asr_dither)
        # Gate ASR: đoạn rác không vào bộ đệm câu.
        if raw and asr_score is not None and asr_score < asr_gate:
            if VERBOSE:
                print(f"🔇 ASR gate (logprob={asr_score:.2f} < {asr_gate}): {raw!r}")
            return "", asr_ms
        return raw, asr_ms

    async def on_segment(samples: np.ndarray, t_seg: float) -> None:
        """VAD đã đóng đoạn: nhận dạng lần cuối, chốt những câu đã trọn."""
        queue_ms = (time.perf_counter() - t_seg) * 1000
        raw, asr_ms = await asr(samples)
        dur = samples.size / SAMPLE_RATE
        if VERBOSE and raw:
            print(f"🎙️ ASR {asr_ms:.0f}ms / {dur:.1f}s audio | {raw!r}")

        live.reset()
        text_src = post.prepare_source(raw, src_lang) if raw else ""
        timing = (f"audio {dur:.1f}s | queue {queue_ms:.0f}ms "
                  f"| asr {asr_ms:.0f}ms")
        await emit_units(buffer.push(text_src) if text_src else [], t_seg, timing)

    async def on_snapshot(samples: np.ndarray) -> None:
        """Đoạn đang nói dở: hiện bản nháp. Bỏ dở ngay khi có việc chốt đang chờ."""
        nonlocal preview_cost
        t0 = time.perf_counter()
        try:
            raw, _asr_ms = await asr(samples)
            if not raw or not queue.empty() or not live.accept(raw):
                return

            units = buffer.peek(draft_post.prepare_source(raw, src_lang))
            for msg_id, text, _would_close in units:
                if not queue.empty():
                    return
                await emit_draft(msg_id, text)
            await prune({msg_id for msg_id, _text, _c in units})
        finally:
            preview_cost = time.perf_counter() - t0

    async def consumer() -> None:
        nonlocal snapshot
        while True:
            await wake.wait()
            wake.clear()
            # Đoạn đã đóng và mốc im lặng luôn đi trước bản xem trước.
            while True:
                if not queue.empty():
                    item = queue.get_nowait()
                    try:
                        if item[0] == "flush":
                            _, hard, t_mark = item
                            await emit_units(buffer.flush(hard), t_mark,
                                             "chốt do im lặng")
                        else:
                            _, samples, t_seg = item
                            await on_segment(samples, t_seg)
                    finally:
                        queue.task_done()
                elif snapshot is not None:
                    samples, snapshot = snapshot, None
                    await on_snapshot(samples)
                else:
                    break

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
              f"| glossary {post.stats['glossary']} "
              f"| tên giữ {post.stats['name_kept']}/mất {post.stats['name_lost']}")
        _report_unknown_names(post)
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

@app.websocket("/ws/audio/{src_lang}")
async def websocket_audio(websocket: WebSocket, src_lang: str) -> None:
    """/ws/audio/<ngôn ngữ nói>?target=<ngôn ngữ đích>&source=system|microphone"""
    tgt_lang = websocket.query_params.get("target") or DEFAULT_TARGET.get(src_lang, "")
    if src_lang not in RECOGNIZERS or (src_lang, tgt_lang) not in ALLOWED_DIRECTIONS:
        await websocket.close(code=1008, reason=f"unsupported {src_lang}->{tgt_lang}")
        return
    # Bắt tay trước rồi mới nạp recognizer: frontend chỉ chờ bắt tay 5 giây.
    await websocket.accept()
    recognizer, lock = await asyncio.to_thread(RECOGNIZERS.__getitem__, src_lang)
    await handle_stream(websocket, recognizer, lock, src_lang, tgt_lang)


@app.get("/v1/health")
async def health() -> dict:
    return {
        "status": "ok",
        "mt_version": MODEL_VERSION,
        "rss_gb": round(_rss_gb(), 2),
        "asr_loaded": RECOGNIZERS.loaded(),
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
        "asr_en": ({"engine": "sherpa-onnx", "arch": "Parakeet TDT 0.6B v2",
                    "quant": "int8", "device": "cpu", "hotwords": False}
                   if "en" in RECOGNIZERS else None),
        "directions": sorted(f"{s}-{t}" for s, t in ALLOWED_DIRECTIONS if s in RECOGNIZERS),
        "mt": {"engine": "ctranslate2", "arch": f"M2M-100 418M + LoRA {MODEL_VERSION}",
               "quant": "int8", "device": "cpu",
               "beam": {"final": BEAM_FINAL, "partial": BEAM_PARTIAL},
               "len_mult": {f"{a}-{b}": v for (a, b), v in LEN_MULT.items()},
               "ja_partial_translation": LIVE_PREVIEW,
               "context": MT_CONTEXT},
        "vad": {"engine": "silero", "format": "onnx"},
        "asr_gate": {"min_logprob": MIN_ASR_LOGPROB,
                     "note": "segment ASR duoi nguong bi bo truoc khi dich; -99 = tat"},
        "glossary_entries": len(GLOSSARY.entries),
    }


if __name__ == "__main__":
    print(f"🚀 http://{HOST}:{PORT}  |  ws://{HOST}:{PORT}/ws/audio/"
          f"{{{','.join(RECOGNIZERS)}}}?target=...")
    if TRANSCRIPT_LOG:
        print("⚠️  TRANSCRIPT_LOG ĐANG BẬT — nội dung phát ngôn sẽ được ghi ra đĩa.")
    uvicorn.run(app, host=HOST, port=PORT, ws_ping_interval=20, ws_ping_timeout=20)