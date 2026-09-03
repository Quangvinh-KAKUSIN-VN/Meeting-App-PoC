""""""

from __future__ import annotations

import json
import re
import time
import unicodedata
from collections import OrderedDict, deque
from pathlib import Path
from threading import Lock

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

_JA_DIGIT = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
             "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_JA_SMALL = {"十": 10, "百": 100, "千": 1000}
_JA_BIG = {"万": 10 ** 4, "億": 10 ** 8, "兆": 10 ** 12}

_JA_NUM_RE = re.compile(r"[〇零一二三四五六七八九十百千万億兆]+")

_JA_HONORIFIC = ("さん", "サン", "ちゃん", "くん", "君", "様", "さま", "氏",
                 "先生", "社長", "部長", "課長", "係長", "主任", "専務", "常務",
                 "会長", "支店長", "所長", "リーダー")

_JA_COUNTER = set("円人個時分秒日月年週回名件枚台本冊度割歳才階号番点箱杯匹頭"
                  "倍億万千百兆円歩件社軒室部屋")


_KANJI_LO = "\u4e00"
_KANJI_HI = "\u9fff"

def _ja_number_is_real(text: str, end: int) -> bool:
    """"""
    rest = text[end:]

    if rest.startswith(_JA_HONORIFIC):
        return False

    if not rest:
        return True

    nxt = rest[0]

    if _KANJI_LO <= nxt <= _KANJI_HI:
        return nxt in _JA_COUNTER

    return True


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


# --- Số Ả-RẬP + đơn vị kanji: dạng ASR hay xuất nhất ------------------------
_JA_ARAB_UNIT_RE = re.compile(r"(?:\d[\d,]*[兆億万])+(?:\d[\d,]*)?")
_JA_ARAB_PAIR_RE = re.compile(r"(\d[\d,]*)([兆億万])")
_JA_ARAB_TAIL_RE = re.compile(r"[兆億万](\d[\d,]*)$")


def _ja_arabic_units(text: str) -> str:
    """'3400万'->'34,000,000' | '21万5000'->'215,000' | '1億2000万'->'120,000,000'."""
    def rep(m):
        s = m.group(0)
        if not _ja_number_is_real(m.string, m.end()):
            return s
        total, last_unit = 0, 0
        for d, u in _JA_ARAB_PAIR_RE.findall(s):
            total += int(d.replace(",", "")) * _JA_BIG[u]
            last_unit = _JA_BIG[u]
        tail = _JA_ARAB_TAIL_RE.search(s)
        if tail:
            t = int(tail.group(1).replace(",", ""))
            if t >= last_unit:
                return s          # dạng dị thường — đừng đoán, giữ nguyên
            total += t
        return _fmt_ja(total)
    return _JA_ARAB_UNIT_RE.sub(rep, text)


# --- N割 -> N0% -------------------------------------------------------------
_WARI_MAP = {**{k: v for k, v in _JA_DIGIT.items() if 1 <= v <= 9}, "十": 10,
             **{str(i): i for i in range(1, 11)}}
_JA_WARI_RE = re.compile(r"(?<![\d割])(10|[1-9]|[一二三四五六七八九十])割(?!り)")


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
    """"""
    if not text:
        return text

    if lang == "ja":
        text = _ja_arabic_units(text)
        text = _JA_WARI_RE.sub(lambda m: f"{_WARI_MAP[m.group(1)] * 10}%", text)

        def rep(m):
            raw = m.group(0)
            if all(c in _JA_BIG for c in raw):
                return raw
            if not _ja_number_is_real(text, m.end()):
                return raw
            n = _ja_kanji_to_int(raw)
            if n is None or n < 100:
                return raw
            if text[m.end():m.end() + 1] == "年" and 1000 <= n <= 2999:
                return str(n)
            return _fmt_ja(n)
        return _JA_NUM_RE.sub(rep, text)

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
# ---------------------------------------------------------------------------

_VI_DEC = re.compile(r"(?<=\d),(?=\d)")
_JA_DEC = re.compile(r"(?<=\d)\.(?=\d)")
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
# ---------------------------------------------------------------------------

def _is_ascii(s: str) -> bool:
    return all(ord(c) < 128 for c in s)


def _is_acronym(text: str) -> bool:
    """"""
    return (_is_ascii(text) and len(text) >= 2 and text.upper() == text
            and any(c.isalpha() for c in text))


def _compile_pattern(text: str, side: str) -> re.Pattern:
    """"""
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
    """"""
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
            if any(bs <= s and e <= be for bs, be in blocked):
                return m.group(0)
            replaced += 1
            slots.append(canonical)       # thay bằng bản chuẩn
            return f"\x02{len(slots) - 1}\x02"
        return _swap

    for pat, canonical, _n in sorted(replacements,
                                     key=lambda rc: rc[2], reverse=True):
        blocked = [m.span() for cp in canonicals for m in cp.finditer(text)]
        text = pat.sub(_swap_factory(canonical, blocked), text)

    text = _PLACEHOLDER.sub(lambda m: slots[int(m.group(1))], text)
    return text, replaced


class Glossary:
    """"""

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
        term = (e.get("term") or "").strip()

        ja_hears = [v.strip() for v in e.get("ja_hears", []) if v and v.strip()]
        vi_hears = [v.strip() for v in e.get("vi_hears", []) if v and v.strip()]
        ja_bad = [v.strip() for v in e.get("ja_bad", []) if v and v.strip()]
        vi_bad = [v.strip() for v in e.get("vi_bad", []) if v and v.strip()]

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
        """"""
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
    def load(cls, path: Path, people_path: Path | None = None) -> "Glossary":
        """"""
        people_entries = people_to_entries(load_people(people_path)) if people_path else []

        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            entries = data["entries"] if isinstance(data, dict) else data
            g = cls(people_entries + entries)
            print(f"📖 Từ điển thuật ngữ: {len(g.entries)} mục "
                  f"(trong đó {len(people_entries)} mục tên người)")
            return g
        except FileNotFoundError:
            print(f"📖 Không có {path} — chạy không từ điển")
            return cls(people_entries)
        except Exception as err:
            print(f"⚠️  Lỗi đọc từ điển ({err}) — chạy không từ điển")
            return cls(people_entries)

    # --------------------------------------------------------------- tầng 1

    def fix_source(self, text: str, lang: str) -> tuple[str, int]:
        """"""
        if not text or not self.entries:
            return text, 0

        guards: list[tuple[re.Pattern, int]] = []
        repls: list[tuple[re.Pattern, str, int]] = []
        for e in self.entries:
            guards += e["_guard_pat"][lang]
            for pat, n in e["_hears_pat"][lang]:
                repls.append((pat, e["term"], n))
            repls.append((e["_term_pat"][lang], e["term"], e["_term_len"]))

        return _protected_replace(text, guards, [], repls)

    # --------------------------------------------------------------- tầng 2

    def apply(self, src: str, dst: str, src_lang: str, tgt_lang: str) -> tuple[str, int]:
        """"""
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
            guards += e["_guard_pat"][tgt_lang]
            canonicals.append(e["_term_pat"][tgt_lang])
            for pat, n in e["_bad_pat"][tgt_lang]:
                repls.append((pat, e["term"], n))
            for pat, n in e["_hears_pat"][src_lang]:
                repls.append((pat, e["term"], n))

        if not repls:
            return dst, 0

        return _protected_replace(dst, guards, canonicals, repls)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

_HONORIFICS = ("さん", "サン", "ちゃん", "チャン", "くん", "君", "様", "さま",
               "氏", "先生", "社長", "部長", "課長", "係長", "主任", "専務",
               "常務", "会長", "支店長", "所長")

_NOT_A_NAME = {
    "皆", "みな", "みんな", "皆様", "お客", "客", "お母", "母", "お父", "父",
    "お兄", "兄", "お姉", "姉", "おじ", "おば", "おじい", "おばあ", "祖父",
    "祖母", "息子", "娘", "奥", "旦那", "主人", "店員", "患者", "神", "仏",
    "お疲れ", "ご苦労", "おまわり", "人", "方", "者", "誰", "どなた",
}

_NOT_A_NAME_SUFFIX = ("屋", "店", "社", "様方")

_NAME_CHARS = r"\u4e00-\u9fff\u30a0-\u30ff\uff66-\uff9dA-Za-z\u30fc"

_JA_NAME_RE = re.compile(
    r"(?P<name>[" + _NAME_CHARS + r"]{1,6})"
    r"(?P<hon>" + "|".join(_HONORIFICS) + r")"
)

_NAME_SLOT_RE = re.compile(r"\bPn([A-Z])\b")


def _looks_like_name(name: str) -> bool:
    if not name or name in _NOT_A_NAME:
        return False
    if name.endswith(_NOT_A_NAME_SUFFIX):
        return False
    if name.strip("ー") == "":
        return False
    return True


class NameProtector:
    """"""

    MAX_SLOTS = 8

    def __init__(self) -> None:
        self.unknown: dict[str, int] = {}

    def protect(self, text: str, lang: str) -> tuple[str, dict[str, str]]:
        """"""
        if lang != "ja" or not text:
            return text, {}

        mapping: dict[str, str] = {}

        def _sub(m: re.Match) -> str:
            name = m.group("name")
            if not _looks_like_name(name) or len(mapping) >= self.MAX_SLOTS:
                return m.group(0)
            slot = "Pn" + chr(ord("A") + len(mapping))
            mapping[slot] = m.group(0)
            self.unknown[m.group(0)] = self.unknown.get(m.group(0), 0) + 1
            return " " + slot + " "

        out = _JA_NAME_RE.sub(_sub, text)
        return (re.sub(r"\s+", " ", out).strip(), mapping) if mapping else (text, {})

    @staticmethod
    def restore(text: str, mapping: dict[str, str]) -> tuple[str, int]:
        """"""
        if not mapping:
            return text, 0

        def _salvage(m: re.Match) -> str:
            return mapping.get("Pn" + m.group(1).upper(), m.group(0))

        text = re.sub(r"\bp[nN]([a-zA-Z])\b", _salvage, text)

        lost = 0
        for slot, original in mapping.items():
            pat = r"\b" + slot + r"\b"
            if re.search(pat, text):
                text = re.sub(pat, original, text)
            elif original not in text:
                lost += 1

        return re.sub(r"\s+", " ", text).strip(), lost


def people_to_entries(people: list[dict]) -> list[dict]:
    """"""
    entries: list[dict] = []

    for p in people:
        latin = (p.get("name") or "").strip()
        if not latin:
            continue

        ja_forms = [v.strip() for v in p.get("ja", []) if v and v.strip()]
        vi_forms = [v.strip() for v in p.get("vi", []) if v and v.strip()]
        bad = [v.strip() for v in p.get("bad", []) if v and v.strip()]
        guard = [v.strip() for v in p.get("guard", []) if v and v.strip()]

        with_hon_ja = [f + h for f in ja_forms for h in ("さん", "サン")]
        if with_hon_ja:
            entries.append({
                "term": latin + "-san",
                "ja_hears": with_hon_ja,
                "vi_hears": [v + " san" for v in vi_forms],
                "ja_guard": guard,
                "vi_guard": guard,
                "vi_bad": bad,
                "ja_bad": bad,
            })

        safe_ja = [f for f in ja_forms if len(f) >= 2]
        if safe_ja or vi_forms:
            entries.append({
                "term": latin,
                "ja_hears": safe_ja,
                "vi_hears": vi_forms,
                "ja_guard": guard,
                "vi_guard": guard,
                "vi_bad": bad,
                "ja_bad": bad,
            })

    return entries


def load_people(path: Path) -> list[dict]:
    """Đọc people.json. Thiếu file là chuyện bình thường -> chạy không danh sách."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except Exception as err:
        print("[people] Loi doc " + str(path) + ": " + str(err))
        return []

    people = data.get("people", data) if isinstance(data, dict) else data
    return people if isinstance(people, list) else []


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

_JA_FILLER_RE = re.compile(
    r"(?:えーと|えっと|ええと|えーっと|うーん|うんーと|んー|えー(?![るりらろ])|"
    r"あのー+|そのー+|あーー*)"
    r"[、,\s]*"
)

_VI_FILLER_RE = re.compile(
    r"(?:^|(?<=[\s,]))(?:ừ+m*|ờ+|à|ê)(?=[\s,]|$)[\s,]*",
    re.IGNORECASE,
)


def strip_fillers(text: str, lang: str) -> str:
    """"""
    if not text:
        return text

    out = _JA_FILLER_RE.sub("", text) if lang == "ja" else _VI_FILLER_RE.sub(" ", text)
    out = re.sub(r"\s+", " ", out).strip(" ,、")
    return out


# ---------------------------------------------------------------------------
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
# ---------------------------------------------------------------------------

_REPEAT_WORD = re.compile(r"\b(\w+)(?:\s+\1\b){2,}", re.IGNORECASE)
_REPEAT_PHRASE = re.compile(r"\b((?:\w+\s+){1,3}\w+)(?:\s+\1\b)+", re.IGNORECASE)

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
        text = _REPEAT_WORD.sub(r"\1", text)
        text = _REPEAT_PHRASE.sub(r"\1", text)
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\s+([,.!?;:])", r"\1", text)
        text = _cap_first(text)
    else:
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
        self.names = NameProtector()
        self.stats = {"dedup": 0, "glossary": 0, "term_fix": 0, "cache_hit": 0,
                      "name_kept": 0, "name_lost": 0}

    # ------------------------------------------------------------- tên người

    def for_model(self, text: str, lang: str) -> str:
        """"""
        return strip_fillers(text, lang)

    def protect_names(self, text: str, lang: str) -> tuple[str, dict[str, str]]:
        """"""
        return self.names.protect(text, lang)

    def restore_names(self, text: str, mapping: dict[str, str]) -> tuple[str, int]:
        """Gọi NGAY SAU translate(), trước finish(). Trả (text, số tên bị mất)."""
        if not mapping:
            return text, 0
        out, lost = NameProtector.restore(text, mapping)
        self.stats["name_kept"] += len(mapping) - lost
        self.stats["name_lost"] += lost
        return out, lost

    def prepare_source(self, text: str, lang: str) -> str:
        """"""
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