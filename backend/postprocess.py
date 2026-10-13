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


def _vi_decimal(grp: list[str], tokens: list[str], j: int) -> tuple[str, int] | None:
    """'một phẩy năm triệu' -> ('1.500.000', vị trí token kế tiếp); 'hai phẩy năm' -> '2,5'.

    Không xử lý thì cụm trước "phẩy" (< 100) bị để nguyên còn cụm sau bị đổi
    riêng: 'một phẩy năm triệu' -> 'một phẩy 5.000.000' -> model dịch thành 5 triệu.
    """
    if not grp or any(w in _VI_SCALE for w in grp) or j >= len(tokens):
        return None
    if re.sub(r"[^\w]", "", tokens[j]).lower() != "phẩy":
        return None
    frac, k, scale = [], j + 1, None
    while k < len(tokens):
        w = re.sub(r"[^\w]", "", tokens[k]).lower()
        if w in _VI_SCALE:
            scale = w
            k += 1
            break
        if w not in _VI_DIGIT and w not in ("mươi", "mười", "trăm"):
            break
        frac.append(w)
        k += 1
    if not frac:
        return None
    # "hai lăm" đọc từng chữ số -> "25"; "hai mươi lăm" đọc như số -> cũng "25"
    if all(w in _VI_DIGIT for w in frac):
        frac_s = "".join(str(_VI_DIGIT[w]) for w in frac)
    else:
        frac_s = str(_vi_block(frac))
    whole = _vi_block(grp)
    if scale:
        mul = _VI_SCALE[scale]
        if 10 ** len(frac_s) <= mul:          # 1,5 triệu -> số nguyên 1.500.000
            return _fmt_vi(whole * mul + int(frac_s) * mul // 10 ** len(frac_s)), k
        return f"{whole},{frac_s} {scale}", k
    return f"{whole},{frac_s}", k


def normalize_source(text: str, lang: str) -> str:
    """"""
    if not text:
        return text

    # Parakeet-EN tự xuất chữ số, và các từ số tiếng Việt ("ba", "năm"...)
    # không có nghĩa số trong câu tiếng Anh -> không chuẩn hoá gì cả.
    if lang == "en":
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
            dec = _vi_decimal(grp, tokens, j)
            if dec:
                out.append(dec[0])
                i = dec[1]
                continue
            # Cụm không có chữ số nào ("tỷ lệ", "tỷ giá", "hàng nghìn") không phải số:
            # _vi_words_to_int tự thêm 1 -> "tỷ lệ lỗi" thành "1.000.000.000 lệ lỗi".
            has_digit = any(w in _VI_DIGIT or w == "mười" for w in grp)
            n = _vi_words_to_int(grp) if grp and has_digit else 0
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
    """VI dùng ',' làm thập phân và '.' làm phân cách nghìn. JA và EN thì ngược lại."""
    if not text:
        return text
    # Model nhiều khi ĐÃ viết số đúng kiểu đích ("1,500人", "1.500 người").
    # Phải khoá dạng đúng đó lại trước, nếu không bước đổi thập phân bên dưới
    # sẽ lật nó thành sai ("1,500" -> "1.500").
    if tgt_lang in ("ja", "en"):
        text = _JA_THOUS.sub("\x00", text)   # 1,500   -> giữ nguyên
        text = _VI_THOUS.sub("\x00", text)   # 200.000 -> tạm
        text = _VI_DEC.sub(".", text)        # 0,3     -> 0.3
        return text.replace("\x00", ",")     # -> 200,000
    text = _VI_THOUS.sub("\x00", text)       # 1.500   -> giữ nguyên
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
    if side in ("vi", "en"):
        return re.compile(rf"(?<!\w){re.escape(text)}(?!\w)", re.IGNORECASE)
    return re.compile(re.escape(text))


LANGS = ("ja", "vi", "en")


_PLACEHOLDER = re.compile("\x02(\\d+)\x02")


def _protected_replace(text: str,
                       guards: list[tuple[re.Pattern, int]],
                       canonicals: list[re.Pattern],
                       replacements: list[tuple[re.Pattern, str, int]],
                       frozen: list[tuple[int, int]] = ()) -> tuple[str, int]:
    """"""
    if not text:
        return text, 0

    slots: list[str] = []

    for start, end in sorted(frozen, reverse=True):
        slots.append(text[start:end])
        text = f"{text[:start]}\x02{len(slots) - 1}\x02{text[end:]}"

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
            # \x03 đánh dấu biên của bản chuẩn vừa chèn — xem _fix_gaps().
            slots.append(f"\x03{canonical}\x03")
            return f"\x02{len(slots) - 1}\x02"
        return _swap

    for pat, canonical, _n in sorted(replacements,
                                     key=lambda rc: rc[2], reverse=True):
        blocked = [m.span() for cp in canonicals for m in cp.finditer(text)]
        text = pat.sub(_swap_factory(canonical, blocked), text)

    text = _PLACEHOLDER.sub(lambda m: slots[int(m.group(1))], text)
    return _fix_gaps(text), replaced


_BOUNDARY = re.compile("\x03+")


def _fix_gaps(text: str) -> str:
    """
    Câu tiếng Nhật không có dấu cách, nên khi ステージングサーバー được đổi
    thành staging + server thì hai từ Latin dính liền ("stagingserver").
    Tại biên của từ vừa chèn: hai bên đều là chữ/số Latin -> thêm một dấu
    cách, còn lại thì bỏ dấu biên.
    """
    def _gap(m: re.Match) -> str:
        s = m.string
        before = s[m.start() - 1] if m.start() > 0 else ""
        after = s[m.end()] if m.end() < len(s) else ""
        return " " if before.isascii() and before.isalnum() \
            and after.isascii() and after.isalnum() else ""
    return _BOUNDARY.sub(_gap, text)


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
        if not term:
            return None

        clean = lambda key: [v.strip() for v in e.get(key, []) if v and v.strip()]
        dedup = lambda xs: list(dict.fromkeys(x for x in xs if x and x != term))

        # Mục chưa khai en_* thì các danh sách tiếng Anh rỗng — thuật ngữ chuẩn
        # vốn đã là tiếng Anh nên vẫn khớp được qua _term_pat["en"].
        out = {"term": term}
        for lang in LANGS:
            out[f"{lang}_hears"] = dedup(clean(f"{lang}_hears"))
            out[f"{lang}_bad"] = dedup(clean(f"{lang}_bad"))
            out[f"{lang}_guard"] = clean(f"{lang}_guard")
        return out

    def _compile(self) -> None:
        """"""
        for e in self.entries:
            e["_term_len"] = len(e["term"])
            e["_term_pat"] = {lang: _compile_pattern(e["term"], lang) for lang in LANGS}
            e["_hears_pat"], e["_bad_pat"], e["_guard_pat"] = {}, {}, {}
            for lang in LANGS:
                e["_hears_pat"][lang] = [(_compile_pattern(h, lang), len(h))
                                         for h in e[f"{lang}_hears"]]
                e["_bad_pat"][lang] = [(_compile_pattern(b, lang), len(b))
                                       for b in e[f"{lang}_bad"]]
                e["_guard_pat"][lang] = [(_compile_pattern(g, lang), len(g))
                                         for g in e[f"{lang}_guard"]]

        self._kata_forms = {h for e in self.entries for h in e["ja_hears"]
                            if _KATA_RUN.fullmatch(h)}
        short = sorted((f for f in self._kata_forms if len(f) <= 3), key=len, reverse=True)
        self._kata_short = re.compile("|".join(map(re.escape, short))) if short else None

    def _tiles(self, word: str) -> bool:
        """True nếu `word` ghép được hoàn toàn từ các thuật ngữ katakana (テスト+データ)."""
        reach = [True] + [False] * len(word)
        for i in range(len(word)):
            if reach[i]:
                for form in self._kata_forms:
                    if word.startswith(form, i):
                        reach[i + len(form)] = True
        return reach[-1]

    def _stray_short_forms(self, text: str) -> list[tuple[int, int]]:
        """Thuật ngữ katakana ngắn nằm GIỮA một từ katakana khác (ログ trong ブログ)."""
        if not self._kata_short:
            return []
        spans = []
        for run in _KATA_RUN.finditer(text):
            word = run.group(0)
            if not self._tiles(word):
                spans += [(run.start() + m.start(), run.start() + m.end())
                          for m in self._kata_short.finditer(word)]
        return spans

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

        frozen = self._stray_short_forms(text) if lang == "ja" else []
        return _protected_replace(text, guards, [], repls, frozen)

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
    "医者", "赤", "彼", "嫁", "婿", "孫", "子", "大家", "駅員", "業者", "運転手", "看護師",
    "社員", "学生", "職人", "近所",
}

_NOT_A_NAME_SUFFIX = ("屋", "店", "社", "様方") + tuple(w for w in _NOT_A_NAME if len(w) >= 2)

_NAME_CHARS = r"\u4e00-\u9fff\u30a0-\u30ff\uff66-\uff9dA-Za-z\u30fc"

_JA_NAME_RE = re.compile(
    r"(?P<name>[" + _NAME_CHARS + r"]{1,6})"
    r"(?P<hon>" + "|".join(_HONORIFICS) + r")"
)

_NAME_SLOT_RE = re.compile(r"\bPn([A-Z])\b")
_KU_VERB_KANJI = "聴聞行書働歩動続届着引置開焼泣咲磨履描乾空向付突弾効利解吹巻敷拭招抱除省驚傾頂"


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
            lead = next((w for w in _JA_TIME_WORDS if name.startswith(w) and name != w), "")
            name = name[len(lead):]
            if not _looks_like_name(name) or len(mapping) >= self.MAX_SLOTS:
                return m.group(0)
            if (m.group("hon") == "くん" and name[-1] in _KU_VERB_KANJI
                    and re.match("だ|で|じゃ|な", m.string[m.end():])):
                return m.group(0)       # 聴くんだ / 聞くんです: động từ + んだ
            slot = "Pn" + chr(ord("A") + len(mapping))
            full = name + m.group("hon")
            mapping[slot] = full
            self.unknown[full] = self.unknown.get(full, 0) + 1
            return lead + " " + slot + " "

        out = _JA_NAME_RE.sub(_sub, text)
        return (re.sub(r"\s+", " ", out).strip(), mapping) if mapping else (text, {})

    @staticmethod
    def restore(text: str, mapping: dict[str, str]) -> tuple[str, int]:
        """"""
        if not mapping:
            return text, 0

        text = re.sub(r"\bp[nN]([a-zA-Z])\b|\bPn ([A-H])\b",
                      lambda m: mapping.get("Pn" + (m.group(1) or m.group(2)).upper(), m.group(0)), text)

        lost = 0
        for slot, original in mapping.items():
            pat = r"\b" + slot + r"\b"
            if re.search(pat, text):
                text = re.sub(pat, original, text)
            elif original not in text:
                lost += 1

        return re.sub(r"\s+", " ", text).strip(), lost


_KANJI = "一-鿿々"
_KATAKANA = "゠-ヿｦ-ﾟ"
_HIRAGANA = "ぁ-ゖ"
_KATA_RUN = re.compile(f"[{_KATAKANA}]+")
_JA_PARTICLE_AHEAD = r"(?=[をがはにでともやのへ、。？！?!\s]|$)"
_JA_TIME_WORDS = ("昨日", "今日", "明日", "毎日", "今朝", "毎朝", "今晩", "毎晩", "今週", "来週",
                  "先週", "毎週", "今月", "来月", "先月", "今年", "去年", "来年", "最近")
_JA_SINGLE_KANJI_BEHIND = ("(?:" + "|".join([f"(?<![{_KANJI}])"]
                           + [f"(?<={w})" for w in _JA_TIME_WORDS]) + ")")


_JA_SURU = r"(?:する|し(?:ます|ません|まし|て|た|ない|なかっ|よう)|でき|さ(?:せ|れ))"


def _ja_word_pattern(word: str, noun_only: bool = True) -> str:
    """Regex khớp `word` như một từ độc lập, không khớp vào giữa từ ghép."""
    esc = re.escape(word)
    not_verb = f"(?!{_JA_SURU})" if noun_only else ""
    if re.fullmatch(f"[{_KANJI}]", word):
        return f"{_JA_SINGLE_KANJI_BEHIND}{esc}{_JA_PARTICLE_AHEAD}"
    if re.fullmatch(f"[{_KANJI}]+", word):
        return f"{esc}(?![{_KANJI}]){not_verb}"
    if re.fullmatch(f"[{_KATAKANA}]+", word):
        return f"(?<![{_KATAKANA}]){esc}(?![{_KATAKANA}]){not_verb}"
    if re.match(f"[{_HIRAGANA}]", word):
        return f"{_JA_SINGLE_KANJI_BEHIND}{esc}{not_verb}"
    return esc + not_verb


_JA_EXCLAIM_RE = re.compile(r"^(?:あっ|ああ|あ|えっ|ええ|え|へえ|へ|おお|おっ|うわ|わあ)")


def _norm_phrase(text: str) -> str:
    return re.sub(r"[\s、。，．,.!?！？…~〜ー]+", "", text).lower()


class Lexicon:
    """
    Vốn từ đời thường (everyday.json), chỉ Nhật -> Việt. Danh từ đi qua bộ dịch bằng ký hiệu giữ chỗ
    (mục có "verb" thì cả dạng động từ 出張します, mục chỉ có "verb" thì chỉ dạng động từ);
    câu cửa miệng khớp nguyên câu thì trả thẳng bản dịch.
    """

    DIRECTIONS = {("ja", "vi")}
    SLOTS = tuple(f"W{i}" for i in range(1, 7))

    def __init__(self, entries: list[dict], phrases: list[dict] | None = None):
        self.words: dict[str, str] = {}
        self.verbs: dict[str, str] = {}
        for e in entries:
            vi = (e.get("vi") or "").strip()
            verb = (e.get("verb") or "").strip()
            for ja in e.get("ja", []):
                ja = (ja or "").strip()
                if ja and (vi or verb) and ja not in self.words:
                    self.words[ja] = vi
                    if verb:
                        self.verbs[ja] = verb
        self._verb_vi = set(self.verbs.values())
        keys = sorted(self.words, key=len, reverse=True)
        self._pattern = re.compile("|".join(
            _ja_word_pattern(k, k not in self.verbs) + ("" if self.words[k] else f"(?={_JA_SURU})")
            for k in keys)) if keys else None

        self.phrases: dict[str, str] = {}
        for e in phrases or []:
            vi = (e.get("vi") or "").strip()
            for ja in e.get("ja", []):
                key = _norm_phrase(ja or "")
                if vi and key:
                    self.phrases.setdefault(key, vi)

    @classmethod
    def load(cls, path: Path) -> "Lexicon":
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            lex = cls(data.get("entries", []), data.get("phrases", []))
            print(f"📗 Từ đời thường: {len(lex.words)} cách viết, {len(lex.phrases)} câu cửa miệng")
            return lex
        except FileNotFoundError:
            return cls([])
        except Exception as err:
            print(f"⚠️  Lỗi đọc {path} ({err}) — bỏ qua từ đời thường")
            return cls([])

    def phrase(self, text: str, src_lang: str, tgt_lang: str) -> str | None:
        if (src_lang, tgt_lang) not in self.DIRECTIONS:
            return None
        key = _norm_phrase(text)
        hit = self.phrases.get(key) or self.phrases.get(_JA_EXCLAIM_RE.sub("", key))
        if hit:
            return hit
        # "そっか、いいですね": từng vế đều là câu cửa miệng
        parts = [self.phrases.get(_norm_phrase(p)) for p in re.split(r"[、。！？!?]+", text) if p.strip()]
        return " ".join(parts) if len(parts) > 1 and all(parts) else None

    @classmethod
    def _slot_re(cls, slot: str) -> re.Pattern:
        return re.compile(rf"(?<![A-Za-z0-9]){slot[0]}[ -]?{slot[1:]}(?![A-Za-z0-9])", re.IGNORECASE)

    def protect(self, text: str, src_lang: str, tgt_lang: str) -> tuple[str, dict[str, str]]:
        if not self._pattern or not text or (src_lang, tgt_lang) not in self.DIRECTIONS:
            return text, {}
        if any(self._slot_re(slot).search(text) for slot in self.SLOTS):
            return text, {}

        mapping: dict[str, str] = {}

        def _sub(m: re.Match) -> str:
            if len(mapping) >= len(self.SLOTS):
                return m.group(0)
            slot, ja = self.SLOTS[len(mapping)], m.group(0)
            is_verb = ja in self.verbs and re.match(_JA_SURU, m.string[m.end():])
            mapping[slot] = self.verbs[ja] if is_verb else self.words[ja]
            return slot

        return self._pattern.sub(_sub, text), mapping

    def restore(self, text: str, mapping: dict[str, str]) -> tuple[str, int]:
        """Trả (text, số ký hiệu model làm mất)."""
        lost = 0
        for slot, word in mapping.items():
            pat = self._slot_re(slot)
            if not pat.search(text):
                lost += 1
                continue
            if word in self._verb_vi:
                # model dịch "W1します" thành "làm W1"
                pat = re.compile(r"(?:\blàm\s+(?:được\s+)?)?" + pat.pattern, re.IGNORECASE)

            def _fill(m: re.Match, word: str = word) -> str:
                starts_sentence = re.search(r"(?:^|[.!?])\s*$", m.string[:m.start()])
                return _cap_first(word) if starts_sentence else word

            text = pat.sub(_fill, text)
        return text, lost


def people_to_entries(people: list[dict]) -> list[dict]:
    """"""
    entries: list[dict] = []

    for p in people:
        latin = (p.get("name") or "").strip()
        if not latin:
            continue

        ja_forms = [v.strip() for v in p.get("ja", []) if v and v.strip()]
        vi_forms = [v.strip() for v in p.get("vi", []) if v and v.strip()]
        en_forms = [v.strip() for v in p.get("en", []) if v and v.strip()]
        bad = [v.strip() for v in p.get("bad", []) if v and v.strip()]
        guard = [v.strip() for v in p.get("guard", []) if v and v.strip()]

        with_hon_ja = [f + h for f in ja_forms for h in ("さん", "サン")]
        if with_hon_ja:
            entries.append({
                "term": latin + "-san",
                "ja_hears": with_hon_ja,
                "vi_hears": [v + " san" for v in vi_forms],
                "en_hears": [v + " san" for v in en_forms],
                "ja_guard": guard,
                "vi_guard": guard,
                "en_guard": guard,
                "vi_bad": bad,
                "ja_bad": bad,
                "en_bad": bad,
            })

        safe_ja = [f for f in ja_forms if len(f) >= 2]
        if safe_ja or vi_forms or en_forms:
            entries.append({
                "term": latin,
                "ja_hears": safe_ja,
                "vi_hears": vi_forms,
                "en_hears": en_forms,
                "ja_guard": guard,
                "vi_guard": guard,
                "en_guard": guard,
                "vi_bad": bad,
                "ja_bad": bad,
                "en_bad": bad,
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
    r"(?:ですね[ー、,\s]*)?"       # "えーとですね、" — です ở đây không phải vị ngữ
)

# "ですね" đứng đầu câu chỉ là câu mào đầu (あのですね、…); để nguyên thì model dịch thành "Được rồi."
_JA_LEADIN_RE = re.compile(r"^(?:あの|その|まあ|まぁ|なんか)?ですね[ー、,\s]*")

# "何か / なんか" đệm đầu câu (いや何か子どもの時に…). Giữ lại khi nó là "cái gì đó" thật: 何か質問, 何かあれば…
_JA_NANKA_REAL = (r"質問|問題|ご|お|あれば|あったら|あり|ある|あっ|でき|いい|食べ|飲|手伝|方法|意見|用|変|困|心配"
                  r"|気に|分か|わか|欲し|ほし|した|しま|しよ|言|聞|買|[をがにはもとの]")
_JA_NANKA_RE = re.compile(
    r"(?:(?<=^)|(?<=いや)|(?<=そう)|(?<=うわ)|(?<=でも)|(?<=あの)|(?<=ああ)|(?<=まあ))"
    rf"(?:何か|なんか)(?!{_JA_NANKA_REAL})")

# Mẩu rơi ra sau khi câu trước đã chốt ("…大事" | "なんですよ"), hoặc một chữ kana lẻ: không có gì để dịch.
_JA_EMPTY_RE = re.compile(r"(?:なん|ん)です(?:よね|よ|ね|けど|が)?|です(?:よ|ね|けど|が)?|[ぁ-ゖ゠-ヿ]")

_VI_FILLER_RE = re.compile(
    r"(?:^|(?<=[\s,]))(?:ừ+m*|ờ+|à|ê)(?=[\s,]|$)[\s,]*",
    re.IGNORECASE,
)

# Chỉ âm đệm thuần. "like", "you know", "so" là từ thật trong nhiều câu,
# cắt đi thì đổi nghĩa -> không đưa vào.
_EN_FILLER_RE = re.compile(
    r"(?:^|(?<=[\s,]))(?:u+[hm]+|e+r+m*|hm+|mm+|ah+)(?=[\s,.!?]|$)[\s,]*",
    re.IGNORECASE,
)


def strip_fillers(text: str, lang: str) -> str:
    """"""
    if not text:
        return text

    if lang == "ja":
        out = _JA_FILLER_RE.sub("", text)
        out = _JA_LEADIN_RE.sub("", out)
        out = _JA_NANKA_RE.sub("", out)
        if _JA_EMPTY_RE.fullmatch(out.strip(" 、。")):
            return ""
    elif lang == "en":
        out = _EN_FILLER_RE.sub(" ", text)
    else:
        out = _VI_FILLER_RE.sub(" ", text)
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
        # So chứa nhau chỉ khi cả hai đều đủ dài, kẻo "はい" vừa nói làm câu dài bắt đầu bằng はい bị coi là trùng.
        for _, old in self.recent:
            if old == key or (min(len(key), len(old)) > 8
                              and (key in old or old in key)):
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
        if ch.isdigit():
            return text
        if ch.isalpha():
            if ch.islower():
                return text[:i] + ch.upper() + text[i + 1:]
            return text
    return text


_VI_CLOCK = r"(?!\s+(?:sáng|trưa|chiều|tối|đêm))"


def fix_duration(src: str, dst: str) -> str:
    """Nhật -> Việt: 6時間 là "6 tiếng", không phải "6 giờ"."""
    for n in dict.fromkeys(re.findall(r"(\d+)時間", src)):
        if not re.search(rf"(?<!\d){n}時(?!間)", src):
            dst = re.sub(rf"(?<!\d){n} giờ\b{_VI_CLOCK}", f"{n} tiếng", dst, flags=re.IGNORECASE)
    if "何時間" in src and "何時" not in src.replace("何時間", ""):
        dst = re.sub(rf"\b(mấy|bao nhiêu) giờ\b{_VI_CLOCK}", r"\1 tiếng", dst, flags=re.IGNORECASE)
    return dst


def cleanup(text: str, lang: str) -> str:
    """Cắt lặp token còn sót và chuẩn hoá khoảng trắng."""
    if not text:
        return text
    text = unicodedata.normalize("NFKC", text).strip()
    if lang in ("vi", "en"):
        text = _REPEAT_WORD.sub(r"\1", text)
        text = _REPEAT_PHRASE.sub(r"\1", text)
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\s+([,.!?;:])", r"\1", text)
        text = re.sub(r"^(?:[-–—•.,;:]\s*)+(?!\d)", "", text)
        text = _cap_first(text)
    else:
        text = _LATIN_GAP.sub("\x00", text)
        text = re.sub(r"[ \u3000]+", "", text)
        text = text.replace("\x00", " ")
    return text.strip()


class PostProcessor:
    """Gộp tất cả lại. Mỗi kết nối WebSocket dùng một instance riêng."""

    def __init__(self, glossary: Glossary, cache: TranslationCache | None = None,
                 lexicon: Lexicon | None = None):
        self.glossary = glossary
        self.cache = cache or TranslationCache()
        self.lexicon = lexicon or Lexicon([])
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

    def protect_words(self, text: str, src_lang: str,
                      tgt_lang: str) -> tuple[str, dict[str, str]]:
        """Gọi TRƯỚC protect_names(), để 旦那さん / 赤ちゃん không bị coi là tên người."""
        return self.lexicon.protect(text, src_lang, tgt_lang)

    def restore_words(self, text: str, mapping: dict[str, str]) -> tuple[str, int]:
        return self.lexicon.restore(text, mapping)

    def phrase(self, text: str, src_lang: str, tgt_lang: str) -> str | None:
        return self.lexicon.phrase(text, src_lang, tgt_lang)

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
        if (src_lang, tgt_lang) == ("ja", "vi"):
            dst = fix_duration(src, dst)
        if tgt_lang in ("vi", "en"):
            dst = _cap_first(dst)
        return dst