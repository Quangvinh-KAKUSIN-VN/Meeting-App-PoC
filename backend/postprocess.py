"""
KaTOBA BridgeAI — Module hậu xử lý (Python thuần, KHÔNG dùng model AI).

Đóng các bug:
  BUG-008  thay thuật ngữ theo từ điển
  BUG-024  bản dịch cùng một thuật ngữ dao động trong phiên
  BUG-022  số tiền tiếng Nhật đọc thành lời -> chữ số  (千五百円 -> 1,500円)
  BUG-047  số tiền tiếng Việt đọc thành lời -> chữ số  (hai trăm nghìn -> 200.000)
  BUG-031  dấu thập phân theo locale                   (0,3% <-> 0.3%)
  BUG-016  loại trùng khi có tiếng vọng

MỚI (nâng cấp thuật ngữ chuyên ngành):
  TERM-01  sửa thuật ngữ NGAY TRÊN TEXT NGUỒN sau ASR, trước khi dịch.
           ASR tiếng Việt nghe "đíp lôi" -> đổi thành "deploy" rồi mới dịch.
           ASR tiếng Nhật nghe デプロイ/デプロー -> đổi thành "deploy".
  TERM-02  ép thuật ngữ trên BẢN DỊCH: phụ đề hai chiều đều giữ nguyên
           chữ tiếng Anh ("deploy", "Docker"...) theo yêu cầu sản phẩm.
  TERM-03  text ASR tiếng Việt toàn CHỮ HOA -> hạ về chữ thường trước khi
           đưa vào M2M-100 (model dịch xử lý chữ hoa kém hơn đáng kể).
  TERM-04  cleanup tiếng Nhật không được xoá dấu cách GIỮA hai từ Latin
           ("pull request" không được thành "pullrequest").

Schema glossary.json MỚI (mỗi mục):
  {
    "term":     "deploy",              # bản chuẩn hiển thị, thường là tiếng Anh
    "ja_hears": ["デプロイ", "デプロー"], # các dạng ASR tiếng Nhật nghe ra
    "vi_hears": ["đíp lôi", "đi lôi"],  # các dạng ASR tiếng Việt nghe ra
    "ja_bad":   ["展開", "配置"],        # bản dịch tiếng Nhật sai cần thay
    "vi_bad":   ["triển khai"],         # bản dịch tiếng Việt sai cần thay
    "ja_guard": [],                     # cụm chứa ja_bad nhưng KHÔNG được thay
    "vi_guard": ["xin lỗi"]             # cụm chứa vi_bad nhưng KHÔNG được thay
  }
Loader vẫn đọc được schema cũ (ja/vi/ja_variants/vi_variants) để không vỡ
nếu ai đó còn giữ file glossary đời trước.

QUAN TRỌNG khi thêm vi_hears: chỉ điền các chuỗi "phiên âm tiếng Anh"
gần như không thể là tiếng Việt thật ("sơ vơ", "đíp lôi"). KHÔNG BAO GIỜ
điền từ tiếng Việt có nghĩa thật ("triển khai", "cam kết") vào vi_hears —
những từ đó thuộc vi_bad, chỉ được thay khi câu nguồn có thuật ngữ tương ứng.

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
# 3. TỪ ĐIỂN THUẬT NGỮ (BUG-008, TERM-01, TERM-02)
# ---------------------------------------------------------------------------

def _is_ascii(s: str) -> bool:
    return all(ord(c) < 128 for c in s)


def _is_acronym(text: str) -> bool:
    """
    "AI", "OK", "API", "CI/CD"... — chữ hoa toàn phần.

    Các từ này BẮT BUỘC khớp phân biệt hoa-thường: text ASR tiếng Việt được
    hạ hết về chữ thường trước khi sửa, nếu khớp không phân biệt thì "AI"
    sẽ nuốt mất đại từ "ai" của tiếng Việt ("ai là người phụ trách" ->
    "AI là người phụ trách"). Muốn ASR bắt được acronym, hãy điền dạng
    chữ thường AN TOÀN vào vi_hears ("api", "url"... — trừ "ai").
    """
    return (_is_ascii(text) and len(text) >= 2 and text.upper() == text
            and any(c.isalpha() for c in text))


def _compile_pattern(text: str, side: str) -> re.Pattern:
    """
    Chọn kiểu ranh giới theo bản chất chuỗi cần khớp:

    - Chuỗi thuần ASCII ("deploy", "CI/CD"): ranh giới là "không dính chữ/số
      ASCII". KHÔNG dùng \\w vì kanji/kana cũng là \\w — "明日deployします"
      phải khớp được dù chữ Latin đứng sát kanji. Acronym toàn chữ hoa
      khớp phân biệt hoa-thường (xem _is_acronym).
    - Chuỗi tiếng Việt có dấu ("triển khai"): ranh giới \\w chuẩn,
      không phân biệt hoa thường.
    - Chuỗi kana/kanji (デプロイ): khớp thẳng, tiếng Nhật không có dấu cách.
    """
    if _is_ascii(text):
        flags = 0 if _is_acronym(text) else re.IGNORECASE
        return re.compile(
            rf"(?<![A-Za-z0-9]){re.escape(text)}(?![A-Za-z0-9])", flags)
    if side == "vi":
        return re.compile(rf"(?<!\w){re.escape(text)}(?!\w)", re.IGNORECASE)
    return re.compile(re.escape(text))


_PLACEHOLDER = re.compile("\x02(\\d+)\x02")


def _protected_replace(text: str,
                       guards: list[tuple[re.Pattern, int]],
                       canonicals: list[re.Pattern],
                       replacements: list[tuple[re.Pattern, str, int]]) -> tuple[str, int]:
    """
    Máy thay thế dùng chung cho cả hai tầng, xử lý đúng ba ca chồng lấn:

      A) chuỗi sai DÀI chứa bản chuẩn NGẮN ("chi nhánh" ⊃ "nhánh")
         -> vẫn PHẢI thay: chỉ bỏ qua match nằm TRỌN trong vùng bản chuẩn,
            match bao trùm ra ngoài thì được phép ăn cả cụm.
      B) bản chuẩn chứa chuỗi sai ("khuôn dập" ⊃ "khuôn")
         -> match nằm trọn trong vùng bản chuẩn -> bỏ qua,
            nếu không sẽ ra "khuôn dập dập".
      C) chuỗi sai là mảnh của cụm khác ("lỗi" trong "xin lỗi")
         -> cụm trong `guards` bị đóng băng hẳn bằng placeholder.

    `guards`/`replacements` mang kèm độ dài CHUỖI GỐC để sắp dài-trước-ngắn
    (không dùng độ dài regex — phần bọc ranh giới ASCII dài hơn phần bọc \\w
    sẽ làm sai thứ tự).

    Placeholder \\x02N\\x02 là ký tự điều khiển không bao giờ có trong text
    thật; pattern sau không thể khớp xuyên qua placeholder; cuối cùng bung ra.
    Trả (text mới, số lần thay thật sự).
    """
    if not text:
        return text, 0

    slots: list[str] = []

    def _freeze(m: re.Match) -> str:
        slots.append(m.group(0))          # giữ nguyên văn
        return f"\x02{len(slots) - 1}\x02"

    for pat, _n in sorted(guards, key=lambda gn: gn[1], reverse=True):
        text = pat.sub(_freeze, text)

    replaced = 0

    def _swap_factory(canonical: str, blocked: list[tuple[int, int]]):
        def _swap(m: re.Match) -> str:
            nonlocal replaced
            s, e = m.span()
            # ca B: match nằm trọn trong một bản chuẩn có sẵn -> để yên
            if any(bs <= s and e <= be for bs, be in blocked):
                return m.group(0)
            replaced += 1
            slots.append(canonical)       # thay bằng bản chuẩn
            return f"\x02{len(slots) - 1}\x02"
        return _swap

    # dài trước ngắn sau (ca A)
    for pat, canonical, _n in sorted(replacements,
                                     key=lambda rc: rc[2], reverse=True):
        # vùng bản chuẩn tính lại trên text hiện tại của từng lượt
        blocked = [m.span() for cp in canonicals for m in cp.finditer(text)]
        text = pat.sub(_swap_factory(canonical, blocked), text)

    text = _PLACEHOLDER.sub(lambda m: slots[int(m.group(1))], text)
    return text, replaced


class Glossary:
    """
    Từ điển thuật ngữ hai tầng.

    Tầng 1 — fix_source(): chạy NGAY SAU ASR. Mọi dạng "nghe ra"
    (ja_hears / vi_hears / chính term viết sai hoa-thường) được đưa về
    bản chuẩn `term` trước khi text vào bộ dịch. Chữ Latin đi qua M2M-100
    thường được giữ nguyên, nên đây là tầng quyết định.

    Tầng 2 — apply(): chạy SAU KHI DỊCH, làm lưới an toàn. Chỉ kích hoạt
    khi câu NGUỒN thực sự chứa thuật ngữ (bản chuẩn hoặc dạng nghe-ra),
    khi đó các bản dịch sai (vi_bad / ja_bad, kể cả katakana lọt sang)
    trong câu ĐÍCH bị thay bằng bản chuẩn. Điều kiện-theo-nguồn giữ cho
    từ thường ("cam kết", "kiểm tra") không bao giờ bị đụng tới khi người
    nói thật sự dùng chúng theo nghĩa thường.
    """

    def __init__(self, entries: list[dict]):
        self.entries = []
        for e in entries:
            norm = self._normalize_entry(e)
            if norm:
                self.entries.append(norm)
        self._compile()

    # ----------------------------------------------------------- nạp/chuẩn hoá

    @staticmethod
    def _normalize_entry(e: dict) -> dict | None:
        """Nhận cả schema mới lẫn schema cũ (ja/vi/ja_variants/vi_variants)."""
        term = (e.get("term") or e.get("en") or "").strip()

        ja_hears = [v.strip() for v in e.get("ja_hears", []) if v and v.strip()]
        vi_hears = [v.strip() for v in e.get("vi_hears", []) if v and v.strip()]
        ja_bad = [v.strip() for v in e.get("ja_bad", []) if v and v.strip()]
        vi_bad = [v.strip() for v in e.get("vi_bad", []) if v and v.strip()]

        if not term and e.get("ja") and e.get("vi"):
            # schema cũ: canonical hiển thị nằm ở e["vi"], nguồn khớp e["ja"]
            term = e["vi"].strip()
            ja_hears = [e["ja"].strip()] + [v for v in e.get("ja_variants", []) if v]
            vi_bad = [v for v in e.get("vi_variants", []) if v]
            ja_bad = [v for v in e.get("ja_variants", []) if v]

        if not term:
            return None

        dedup = lambda xs: list(dict.fromkeys(x for x in xs if x and x != term))
        return {
            "term": term,
            "ja_hears": dedup(ja_hears),
            "vi_hears": dedup(vi_hears),
            "ja_bad": dedup(ja_bad),
            "vi_bad": dedup(vi_bad),
            "ja_guard": [v.strip() for v in e.get("ja_guard", []) if v and v.strip()],
            "vi_guard": [v.strip() for v in e.get("vi_guard", []) if v and v.strip()],
        }

    def _compile(self) -> None:
        """
        Biên dịch regex một lần lúc nạp — vòng realtime không compile lại.
        Mỗi pattern lưu kèm độ dài chuỗi gốc để engine sắp dài-trước-ngắn.
        """
        for e in self.entries:
            term_len = len(e["term"])
            e["_term_pat"] = {
                "ja": _compile_pattern(e["term"], "ja"),
                "vi": _compile_pattern(e["term"], "vi"),
            }
            e["_term_len"] = term_len
            e["_hears_pat"] = {
                "ja": [(_compile_pattern(h, "ja"), len(h)) for h in e["ja_hears"]],
                "vi": [(_compile_pattern(h, "vi"), len(h)) for h in e["vi_hears"]],
            }
            e["_bad_pat"] = {
                "ja": [(_compile_pattern(b, "ja"), len(b)) for b in e["ja_bad"]],
                "vi": [(_compile_pattern(b, "vi"), len(b)) for b in e["vi_bad"]],
            }
            e["_guard_pat"] = {
                "ja": [(_compile_pattern(g, "ja"), len(g)) for g in e["ja_guard"]],
                "vi": [(_compile_pattern(g, "vi"), len(g)) for g in e["vi_guard"]],
            }

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

    # --------------------------------------------------------------- tầng 1

    def fix_source(self, text: str, lang: str) -> tuple[str, int]:
        """
        Sửa thuật ngữ ngay trên text ASR (trước khi dịch).
        'anh đã đíp lôi chưa'   -> 'anh đã deploy chưa'
        '明日デプローします'        -> '明日deployします'
        'chạy trên gít háp'     -> 'chạy trên GitHub'   (chuẩn hoá cả hoa-thường)
        """
        if not text or not self.entries:
            return text, 0

        guards: list[tuple[re.Pattern, int]] = []
        repls: list[tuple[re.Pattern, str, int]] = []
        for e in self.entries:
            guards += e["_guard_pat"][lang]
            for pat, n in e["_hears_pat"][lang]:
                repls.append((pat, e["term"], n))
            # khớp cả chính term để chuẩn hoá hoa-thường ("github" -> "GitHub")
            repls.append((e["_term_pat"][lang], e["term"], e["_term_len"]))

        # canonicals=[] : tầng nguồn không chặn theo bản chuẩn, nếu chặn thì
        # chính phép chuẩn-hoá-hoa-thường ("github" nằm trong vùng khớp của
        # "GitHub") sẽ tự khoá mình
        return _protected_replace(text, guards, [], repls)

    # --------------------------------------------------------------- tầng 2

    def apply(self, src: str, dst: str, src_lang: str, tgt_lang: str) -> tuple[str, int]:
        """
        Lưới an toàn sau dịch. Trả (bản dịch đã sửa, số thuật ngữ đã áp).
        Chỉ những mục mà câu NGUỒN có chứa thuật ngữ mới được phép sửa câu đích.
        """
        if not self.entries or not dst:
            return dst, 0

        guards: list[tuple[re.Pattern, int]] = []
        canonicals: list[re.Pattern] = []
        repls: list[tuple[re.Pattern, str, int]] = []

        for e in self.entries:
            in_src = bool(e["_term_pat"][src_lang].search(src)) or any(
                p.search(src) for p, _n in e["_hears_pat"][src_lang])
            if not in_src:
                continue
            # ca C: cụm bảo vệ đóng băng hẳn; ca B: bản chuẩn có sẵn trong
            # câu đích chặn các match nằm trọn bên trong nó
            guards += e["_guard_pat"][tgt_lang]
            canonicals.append(e["_term_pat"][tgt_lang])
            # thay: bản dịch sai phía đích + dạng nghe-ra phía nguồn lọt sang
            # (katakana đôi khi được M2M bê nguyên xi vào câu tiếng Việt)
            for pat, n in e["_bad_pat"][tgt_lang]:
                repls.append((pat, e["term"], n))
            for pat, n in e["_hears_pat"][src_lang]:
                repls.append((pat, e["term"], n))

        if not repls:
            return dst, 0

        return _protected_replace(dst, guards, canonicals, repls)


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

# TERM-04: dấu cách nằm GIỮA hai ký tự Latin/số phải sống sót qua cleanup ja.
_LATIN_GAP = re.compile(r"(?<=[A-Za-z0-9]) +(?=[A-Za-z0-9])")


def _cap_first(text: str) -> str:
    """Viết hoa ký tự chữ đầu tiên, bỏ qua ký tự không phải chữ đứng trước."""
    for i, ch in enumerate(text):
        if ch.isalpha():
            if ch.islower():
                return text[:i] + ch.upper() + text[i + 1:]
            return text
    return text


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
        text = _cap_first(text)
    else:
        # TERM-04: đóng băng dấu cách giữa từ Latin trước khi quét sạch
        text = _LATIN_GAP.sub("\x00", text)
        text = re.sub(r"[ \u3000]+", "", text)
        text = text.replace("\x00", " ")
    return text.strip()


class PostProcessor:
    """Gộp tất cả lại. Mỗi kết nối WebSocket dùng một instance riêng."""

    def __init__(self, glossary: Glossary, cache: TranslationCache | None = None):
        self.glossary = glossary
        self.cache = cache or TranslationCache()
        self.deduper = Deduper()
        self.stats = {"dedup": 0, "glossary": 0, "term_fix": 0, "cache_hit": 0}

    def prepare_source(self, text: str, lang: str) -> str:
        """
        Chuỗi xử lý text NGUỒN, đúng thứ tự:
          1. TERM-03: ASR tiếng Việt trả CHỮ HOA -> hạ hết về chữ thường
             (làm TRƯỚC cleanup để cleanup viết hoa lại đúng chữ cái đầu câu).
          2. cleanup: cắt lặp, chuẩn khoảng trắng.
          3. chuẩn hoá số đọc-thành-lời -> chữ số.
          4. TERM-01: dạng nghe-ra của thuật ngữ -> bản chuẩn tiếng Anh.
        """
        if lang == "vi" and text:
            text = text.lower()
        text = normalize_source(cleanup(text, lang), lang)
        text, n = self.glossary.fix_source(text, lang)
        if n:
            self.stats["term_fix"] += n
            if lang == "vi":
                text = _cap_first(text)   # phòng khi thuật ngữ đứng đầu câu
        return text

    def is_duplicate(self, text: str) -> bool:
        dup = self.deduper.is_duplicate(text)
        if dup:
            self.stats["dedup"] += 1
        return dup

    def finish(self, src: str, dst: str, src_lang: str, tgt_lang: str) -> str:
        dst = cleanup(dst, tgt_lang)
        dst, hits = self.glossary.apply(src, dst, src_lang, tgt_lang)
        self.stats["glossary"] += hits
        dst = fix_decimal_locale(dst, tgt_lang)
        if tgt_lang == "vi":
            dst = _cap_first(dst)
        return dst
