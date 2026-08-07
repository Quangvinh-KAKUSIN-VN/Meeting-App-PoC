"""
KaTOBA BridgeAI — Module hậu xử lý (Python thuần, KHÔNG dùng model AI).

Đóng các bug:
  BUG-008  thay thuật ngữ theo từ điển
  BUG-024  bản dịch cùng một thuật ngữ dao động trong phiên
  BUG-022  số tiền tiếng Nhật đọc thành lời -> chữ số  (千五百円 -> 1,500円)
  BUG-047  số tiền tiếng Việt đọc thành lời -> chữ số  (hai trăm nghìn -> 200.000)
  BUG-031  dấu thập phân theo locale                   (0,3% <-> 0.3%)
  BUG-016  loại trùng khi có tiếng vọng

KHÔNG đóng được BUG-007 (kế thừa ngữ cảnh giữa segment).
M2M-100 là encoder-decoder, không nhận prompt, không tuân theo chỉ dẫn.
Giải đại từ 「それ」 cần model khác — đừng ghi bug đó vào file này.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from collections import OrderedDict, deque
from pathlib import Path
from threading import Lock

# ---------------------------------------------------------------------------
# 1. CHUẨN HOÁ SỐ (ITN) — áp dụng lên text NGUỒN, ngay sau ASR
# ---------------------------------------------------------------------------

_JA_DIGIT = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
             "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_JA_SMALL = {"十": 10, "百": 100, "千": 1000}
_JA_BIG = {"万": 10 ** 4, "億": 10 ** 8, "兆": 10 ** 12}

_JA_NUM_RE = re.compile(r"[〇零一二三四五六七八九十百千万億兆]+")


def _ja_kanji_to_int(s: str) -> int | None:
    """千五百 -> 1500. Trả None nếu chuỗi không phải số hợp lệ."""
    total = section = current = 0
    seen = False
    for ch in s:
        if ch in _JA_DIGIT:
            current = _JA_DIGIT[ch]
            seen = True
        elif ch in _JA_SMALL:
            section += (current or 1) * _JA_SMALL[ch]
            current = 0
            seen = True
        elif ch in _JA_BIG:
            section += current
            total += (section or 1) * _JA_BIG[ch]
            section = current = 0
            seen = True
        else:
            return None
    return total + section + current if seen else None


def _fmt_ja(n: int) -> str:
    return f"{n:,}"          # 1500 -> "1,500"


def _fmt_vi(n: int) -> str:
    return f"{n:,}".replace(",", ".")   # 200000 -> "200.000"


_VI_DIGIT = {"không": 0, "một": 1, "mốt": 1, "hai": 2, "ba": 3, "bốn": 4, "tư": 4,
             "năm": 5, "lăm": 5, "nhăm": 5, "sáu": 6, "bảy": 7, "bẩy": 7,
             "tám": 8, "chín": 9}
_VI_SCALE = {"nghìn": 1000, "ngàn": 1000, "triệu": 10 ** 6, "tỷ": 10 ** 9, "tỉ": 10 ** 9}
_VI_SKIP = {"lẻ", "linh"}
_VI_WORDS = set(_VI_DIGIT) | set(_VI_SCALE) | _VI_SKIP | {"trăm", "mươi", "mười"}


def _vi_block(words: list[str]) -> int:
    """Cụm dưới 1000: 'hai trăm ba mươi tư' -> 234."""
    val, i = 0, 0
    while i < len(words):
        w = words[i]
        if w in _VI_DIGIT:
            d = _VI_DIGIT[w]
            if i + 1 < len(words) and words[i + 1] == "trăm":
                val += d * 100
                i += 2
                continue
            if i + 1 < len(words) and words[i + 1] == "mươi":
                tens = d * 10
                i += 2
                if i < len(words) and words[i] in _VI_DIGIT:
                    tens += _VI_DIGIT[words[i]]
                    i += 1
                val += tens
                continue
            val += d
            i += 1
            continue
        if w == "mười":
            tens = 10
            i += 1
            if i < len(words) and words[i] in _VI_DIGIT:
                tens += _VI_DIGIT[words[i]]
                i += 1
            val += tens
            continue
        i += 1
    return val


def _vi_words_to_int(words: list[str]) -> int:
    total, block = 0, []
    for w in words:
        if w in ("tỷ", "tỉ"):
            total += (_vi_block(block) or 1) * 10 ** 9
            block = []
        elif w == "triệu":
            total += (_vi_block(block) or 1) * 10 ** 6
            block = []
        elif w in ("nghìn", "ngàn"):
            total += (_vi_block(block) or 1) * 1000
            block = []
        else:
            block.append(w)
    return total + _vi_block(block)


def normalize_source(text: str, lang: str) -> str:
    """
    Chuẩn hoá số trong text NGUỒN (sau ASR, trước khi dịch).
    Chỉ đổi cụm số >= 100 — dưới ngưỡng đó chữ viết thường tự nhiên hơn.
    """
    if not text:
        return text

    if lang == "ja":
        def rep(m):
            n = _ja_kanji_to_int(m.group(0))
            return _fmt_ja(n) if n is not None and n >= 100 else m.group(0)
        return _JA_NUM_RE.sub(rep, text)

    # tiếng Việt: gom các từ số liền nhau
    tokens = text.split()
    out, i = [], 0
    while i < len(tokens):
        raw = tokens[i]
        key = re.sub(r"[^\w]", "", raw).lower()
        if key in _VI_WORDS:
            j = i
            grp = []
            while j < len(tokens):
                k = re.sub(r"[^\w]", "", tokens[j]).lower()
                if k not in _VI_WORDS:
                    break
                grp.append(k)
                j += 1
            # bỏ đuôi 'lẻ'/'linh' lơ lửng
            while grp and grp[-1] in _VI_SKIP:
                grp.pop()
                j -= 1
            n = _vi_words_to_int(grp) if grp else 0
            if grp and n >= 100:
                out.append(_fmt_vi(n))
                i = j
                continue
        out.append(raw)
        i += 1
    return " ".join(out)


# ---------------------------------------------------------------------------
# 2. DẤU THẬP PHÂN THEO LOCALE (BUG-031)
# ---------------------------------------------------------------------------

_VI_DEC = re.compile(r"(?<=\d),(?=\d)")
_JA_DEC = re.compile(r"(?<=\d)\.(?=\d)")
# Dùng (?!\d) chứ KHÔNG dùng \b: kanji như 円 cũng là ký tự \w trong Python,
# nên "1,500円" không có ranh giới từ giữa '0' và '円' -> \b sẽ trượt.
_VI_THOUS = re.compile(r"(?<=\d)\.(?=\d{3}(?!\d))")
_JA_THOUS = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")


def fix_decimal_locale(text: str, tgt_lang: str) -> str:
    """VI dùng ',' làm thập phân và '.' làm phân cách nghìn. JA thì ngược lại."""
    if not text:
        return text
    if tgt_lang == "ja":
        text = _VI_THOUS.sub("\x00", text)   # 200.000 -> tạm
        text = _VI_DEC.sub(".", text)        # 0,3     -> 0.3
        return text.replace("\x00", ",")     # -> 200,000
    text = _JA_THOUS.sub("\x00", text)
    text = _JA_DEC.sub(",", text)
    return text.replace("\x00", ".")


# ---------------------------------------------------------------------------
# 3. TỪ ĐIỂN THUẬT NGỮ (BUG-008)
# ---------------------------------------------------------------------------

class Glossary:
    """
    Ép thuật ngữ sau khi dịch. Nguyên tắc: CHỈ thay biến thể sai bằng bản
    chuẩn — không bao giờ chèn thêm từ vào câu dịch. Chèn thêm dễ tạo câu
    vô nghĩa hơn là để nguyên.
    """

    def __init__(self, entries: list[dict]):
        self.entries = []
        for e in entries:
            ja, vi = e.get("ja", "").strip(), e.get("vi", "").strip()
            if not ja or not vi:
                continue
            self.entries.append({
                "ja": ja,
                "vi": vi,
                "ja_variants": [v for v in e.get("ja_variants", []) if v and v != ja],
                "vi_variants": [v for v in e.get("vi_variants", []) if v and v != vi],
                # cụm được bảo vệ: biến thể nằm trong đây thì KHÔNG thay
                "ja_guard": list(e.get("ja_guard", [])),
                "vi_guard": list(e.get("vi_guard", [])),
            })

    @classmethod
    def load(cls, path: Path) -> "Glossary":
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            entries = data["entries"] if isinstance(data, dict) else data
            g = cls(entries)
            print(f"📖 Từ điển thuật ngữ: {len(g.entries)} mục")
            return g
        except FileNotFoundError:
            print(f"📖 Không có {path} — chạy không từ điển")
            return cls([])
        except Exception as err:
            print(f"⚠️  Lỗi đọc từ điển ({err}) — chạy không từ điển")
            return cls([])

    @staticmethod
    def _finditer(text: str, term: str, vi: bool):
        """Tiếng Việt cần ranh giới từ; tiếng Nhật không có dấu cách nên khớp thẳng."""
        pat = rf"(?<!\w){re.escape(term)}(?!\w)" if vi else re.escape(term)
        return list(re.finditer(pat, text, re.IGNORECASE if vi else 0))

    @classmethod
    def _has(cls, text: str, term: str, vi: bool) -> bool:
        return bool(cls._finditer(text, term, vi))

    @classmethod
    def _enforce(cls, dst: str, correct: str, variants: list[str],
                 guards: list[str], vi: bool) -> tuple[str, bool]:
        """
        Thay biến thể sai bằng bản chuẩn, có kiểm tra CHỒNG LẤN.

        Ba ca bắt buộc phải xử lý đúng:
          A) biến thể chứa bản chuẩn — 'chi nhánh' ⊃ 'nhánh'  -> PHẢI thay
          B) bản chuẩn chứa biến thể — 'khuôn dập' ⊃ 'khuôn'  -> PHẢI bỏ qua,
             nếu không sẽ ra 'khuôn dập dập'
          C) biến thể là một âm tiết của từ ghép khác — 'khuôn' trong 'khuôn khổ'
             -> PHẢI bỏ qua. Tiếng Việt viết rời từng âm tiết nên \b không đủ;
             phải liệt kê tường minh trong 'vi_guard'.

        Cả ba dùng chung một cơ chế: dựng danh sách vùng CẤM ĐỘNG rồi bỏ qua
        mọi khớp nằm trọn bên trong vùng đó.
        """
        good = [m.span() for m in cls._finditer(dst, correct, vi)]
        blocked = list(good)
        for gphrase in guards:
            blocked += [m.span() for m in cls._finditer(dst, gphrase, vi)]

        for var in sorted(variants, key=len, reverse=True):
            for m in cls._finditer(dst, var, vi):
                s, e = m.span()
                if any(bs <= s and e <= be for bs, be in blocked):
                    continue                      # ca B hoặc C
                new = correct
                if vi and m.group(0)[:1].isupper():
                    new = correct[:1].upper() + correct[1:]
                return dst[:s] + new + dst[e:], True
        return dst, bool(good)

    def apply(self, src: str, dst: str, src_lang: str, tgt_lang: str) -> tuple[str, int]:
        """Trả (bản dịch đã sửa, số thuật ngữ đã áp)."""
        if not self.entries or not dst:
            return dst, 0
        hits = 0
        for e in self.entries:
            if src_lang == "ja":
                if not self._has(src, e["ja"], False) and not any(
                        self._has(src, v, False) for v in e["ja_variants"]):
                    continue
                dst, hit = self._enforce(dst, e["vi"], e["vi_variants"],
                                         e["vi_guard"], vi=True)
            else:
                if not self._has(src, e["vi"], True) and not any(
                        self._has(src, v, True) for v in e["vi_variants"]):
                    continue
                dst, hit = self._enforce(dst, e["ja"], e["ja_variants"],
                                         e["ja_guard"], vi=False)
            hits += int(hit)
        return dst, hits


# ---------------------------------------------------------------------------
# 4. LOẠI TRÙNG (BUG-016)
# ---------------------------------------------------------------------------

def _norm_key(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    return re.sub(r"[^\w\u3040-\u30ff\u4e00-\u9fff]+", "", s)


class Deduper:
    """Tiếng vọng làm cùng một câu vào ASR hai lần cách nhau vài trăm ms."""

    def __init__(self, window_sec: float = 6.0, maxlen: int = 12):
        self.window = window_sec
        self.recent: deque[tuple[float, str]] = deque(maxlen=maxlen)

    def is_duplicate(self, text: str) -> bool:
        key = _norm_key(text)
        if not key:
            return False
        now = time.time()
        while self.recent and now - self.recent[0][0] > self.window:
            self.recent.popleft()
        for _, old in self.recent:
            if old == key or (len(key) > 8 and (key in old or old in key)):
                return True
        self.recent.append((now, key))
        return False


# ---------------------------------------------------------------------------
# 5. CACHE BẢN DỊCH (BUG-024)
# ---------------------------------------------------------------------------

class TranslationCache:
    """Cùng một câu nguồn -> luôn cùng một bản dịch trong phiên. Kèm lợi ích tốc độ."""

    def __init__(self, maxsize: int = 512):
        self.maxsize = maxsize
        self._d: OrderedDict[tuple, str] = OrderedDict()
        self._lock = Lock()
        self.hits = self.misses = 0

    def get(self, src: str, sl: str, tl: str) -> str | None:
        k = (_norm_key(src), sl, tl)
        with self._lock:
            if k in self._d:
                self._d.move_to_end(k)
                self.hits += 1
                return self._d[k]
            self.misses += 1
            return None

    def put(self, src: str, sl: str, tl: str, dst: str) -> None:
        if not dst:
            return
        k = (_norm_key(src), sl, tl)
        with self._lock:
            self._d[k] = dst
            self._d.move_to_end(k)
            while len(self._d) > self.maxsize:
                self._d.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._d.clear()


# ---------------------------------------------------------------------------
# 6. DỌN DẸP CHUNG
# ---------------------------------------------------------------------------

# Một từ lặp >= 3 lần mới cắt — tiếng Việt có láy hợp lệ ("xanh xanh", "đi đi").
_REPEAT_WORD = re.compile(r"\b(\w+)(?:\s+\1\b){2,}", re.IGNORECASE)
# Cụm 2-4 từ lặp >= 2 lần thì cắt ngay — gần như không bao giờ là tiếng Việt hợp lệ.
# Đây chính là ca 'Hướng dẫn hướng dẫn' của BUG-004.
_REPEAT_PHRASE = re.compile(r"\b((?:\w+\s+){1,3}\w+)(?:\s+\1\b)+", re.IGNORECASE)


def cleanup(text: str, lang: str) -> str:
    """Cắt lặp token còn sót và chuẩn hoá khoảng trắng."""
    if not text:
        return text
    text = unicodedata.normalize("NFKC", text).strip()
    if lang == "vi":
        # từ trước, cụm sau: "a a a a" -> "a" thay vì dừng ở "a a"
        text = _REPEAT_WORD.sub(r"\1", text)
        text = _REPEAT_PHRASE.sub(r"\1", text)
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\s+([,.!?;:])", r"\1", text)
        if text and text[0].islower():
            text = text[0].upper() + text[1:]
    else:
        text = re.sub(r"[ \u3000]+", "", text)
    return text.strip()


class PostProcessor:
    """Gộp tất cả lại. Mỗi kết nối WebSocket dùng một instance riêng."""

    def __init__(self, glossary: Glossary, cache: TranslationCache | None = None):
        self.glossary = glossary
        self.cache = cache or TranslationCache()
        self.deduper = Deduper()
        self.stats = {"dedup": 0, "glossary": 0, "cache_hit": 0}

    def prepare_source(self, text: str, lang: str) -> str:
        return normalize_source(cleanup(text, lang), lang)

    def is_duplicate(self, text: str) -> bool:
        dup = self.deduper.is_duplicate(text)
        if dup:
            self.stats["dedup"] += 1
        return dup

    def finish(self, src: str, dst: str, src_lang: str, tgt_lang: str) -> str:
        dst = cleanup(dst, tgt_lang)
        dst, hits = self.glossary.apply(src, dst, src_lang, tgt_lang)
        self.stats["glossary"] += hits
        return fix_decimal_locale(dst, tgt_lang)