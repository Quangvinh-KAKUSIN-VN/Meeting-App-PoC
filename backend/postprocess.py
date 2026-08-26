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

# Kính ngữ / chức danh. Đứng ngay sau một cụm kanji thì cụm đó là TÊN NGƯỜI,
# tuyệt đối không phải số: 百三さん là "Momozo-san", không phải "103-san".
_JA_HONORIFIC = ("さん", "サン", "ちゃん", "くん", "君", "様", "さま", "氏",
                 "先生", "社長", "部長", "課長", "係長", "主任", "専務", "常務",
                 "会長", "支店長", "所長", "リーダー")

# Ký tự ĐẾM hợp lệ đứng sau con số. Danh sách đóng, và đó là chủ ý:
# gặp kanji lạ ngay sau cụm số thì mặc định coi như TỪ GHÉP, không phải số.
# 千葉 (Chiba) / 百貨店 / 一致 / 三田 đều rơi vào ca này.
_JA_COUNTER = set("円人個時分秒日月年週回名件枚台本冊度割歳才階号番点箱杯匹頭"
                  "倍億万千百兆円歩件社軒室部屋")


# Khối kanji thông dụng (CJK Unified Ideographs).
_KANJI_LO = "\u4e00"
_KANJI_HI = "\u9fff"

def _ja_number_is_real(text: str, end: int) -> bool:
    """
    Cụm kanji số vừa khớp có THẬT SỰ là số không, xét bối cảnh đứng sau nó.

    Không có bộ tách từ tiếng Nhật trong pipeline (thêm MeCab/SudachiPy chỉ
    để việc này là không đáng), nên dùng luật bối cảnh — bắt đúng toàn bộ ca
    hỏng thực tế: họ tên chứa kanji số.
    """
    rest = text[end:]

    # 千葉さん, 百三さん, 九十九里さん...
    if rest.startswith(_JA_HONORIFIC):
        return False

    if not rest:
        return True

    nxt = rest[0]

    # Kanji đứng liền sau: là đơn vị đếm thì là số, còn lại là từ ghép.
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
            raw = m.group(0)
            if not _ja_number_is_real(text, m.end()):
                return raw
            n = _ja_kanji_to_int(raw)
            if n is None or n < 100:
                return raw
            # Năm không bao giờ có dấu phân cách nghìn: 二千二十六年 -> 2026年,
            # chứ không phải 2,026年.
            if text[m.end():m.end() + 1] == "年" and 1000 <= n <= 2999:
                return str(n)
            return _fmt_ja(n)
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
    def load(cls, path: Path, people_path: Path | None = None) -> "Glossary":
        """
        `people_path` là danh sách người dự (people.json). Mỗi người được
        biến thành mục từ điển nên tên đi qua đúng máy thay thế hai tầng đã
        có: tầng 1 đổi "千葉さん" -> "Chiba-san" ngay sau ASR (chữ Latin đi
        qua M2M-100 gần như luôn được giữ nguyên), tầng 2 dọn các bản dịch
        sai đã biết trong câu đích.
        """
        people_entries = people_to_entries(load_people(people_path)) if people_path else []

        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            entries = data["entries"] if isinstance(data, dict) else data
            # Người dự đứng TRƯỚC thuật ngữ: trùng chuỗi thì tên người thắng.
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
# 4. TÊN NGƯỜI
# ---------------------------------------------------------------------------
#
# Vì sao cần cả một tầng riêng: M2M-100 không có khái niệm "danh từ riêng".
# Tên người tiếng Nhật viết bằng kanji trùng với kanji số hoặc từ thường, và
# model dịch NGHĨA của kanji đó:
#     一さん   -> "13"          (đọc 一 như chữ số)
#     千葉さん -> "1.000 lá"     (千 = 1000, 葉 = lá)
#     本田さん -> "ruộng sách"
# Trong biên bản họp, sai tên người là sai nội dung, không phải sai thẩm mỹ.
#
# Hai lớp:
#   Lớp A — DANH SÁCH NGƯỜI DỰ (people.json). Chắc chắn, vì có sẵn dạng Latin
#           để thay vào. Chuyển thẳng thành mục từ điển nên dùng lại toàn bộ
#           máy thay thế hai tầng đã có (fix_source + apply).
#   Lớp B — PHÁT HIỆN CHUNG cho tên KHÔNG có trong danh sách: đóng băng cụm
#           "<tên>さん" bằng placeholder trước khi dịch rồi bung lại nguyên
#           văn sau khi dịch. Giữ được tên gốc tiếng Nhật thay vì biến thành
#           con số, và ghi log để người dùng bổ sung vào people.json.

_HONORIFICS = ("さん", "サン", "ちゃん", "チャン", "くん", "君", "様", "さま",
               "氏", "先生", "社長", "部長", "課長", "係長", "主任", "専務",
               "常務", "会長", "支店長", "所長")

# "Xさん" nhưng X KHÔNG phải tên người. Thiếu danh sách này thì 皆さん
# ("mọi người") bị đóng băng và câu dịch mất luôn chủ ngữ.
_NOT_A_NAME = {
    "皆", "みな", "みんな", "皆様", "お客", "客", "お母", "母", "お父", "父",
    "お兄", "兄", "お姉", "姉", "おじ", "おば", "おじい", "おばあ", "祖父",
    "祖母", "息子", "娘", "奥", "旦那", "主人", "店員", "患者", "神", "仏",
    "お疲れ", "ご苦労", "おまわり", "人", "方", "者", "誰", "どなた",
}

# Đuôi cho biết đó là CỬA HÀNG/NGHỀ chứ không phải người: パン屋さん, 魚屋さん.
_NOT_A_NAME_SUFFIX = ("屋", "店", "社", "様方")

# Kanji + katakana (cả nửa thân) + Latin. CỐ TÌNH BỎ hiragana:
# hiragana ngay trước kính ngữ gần như luôn là HẠT NỐI, không phải tên —
# "千葉さんと本田さん" mà cho hiragana vào lớp ký tự thì "と" bị nuốt vào tên
# thành "と本田さん", và câu dịch mất luôn liên từ "và".
# Đánh đổi: tên viết thuần hiragana (ひろしさん) không tự nhận ra được —
# những tên đó phải khai trong people.json.
_NAME_CHARS = r"\u4e00-\u9fff\u30a0-\u30ff\uff66-\uff9dA-Za-z\u30fc"

# {1,6} THAM (không phải lười): quét từ trái sang, khớp tham lấy trọn cụm
# kanji dài nhất đứng liền trước kính ngữ, đúng bằng họ + tên.
_JA_NAME_RE = re.compile(
    r"(?P<name>[" + _NAME_CHARS + r"]{1,6})"
    r"(?P<hon>" + "|".join(_HONORIFICS) + r")"
)

# Placeholder đi XUYÊN qua M2M-100. Yêu cầu: ASCII, viết hoa đầu, không mang
# nghĩa, không bị SentencePiece băm thành mảnh vô nghĩa. Dạng "Pn" + chữ cái
# được model đối xử như một danh từ riêng lạ -> chép nguyên xi.
_NAME_SLOT_RE = re.compile(r"\bPn([A-Z])\b")


def _looks_like_name(name: str) -> bool:
    if not name or name in _NOT_A_NAME:
        return False
    if name.endswith(_NOT_A_NAME_SUFFIX):
        return False
    # Dấu kéo dài katakana đứng một mình không phải tên.
    if name.strip("ー") == "":
        return False
    return True


class NameProtector:
    """
    Lớp B — giữ tên người KHÔNG có trong people.json sống sót qua bộ dịch.

    Dùng theo cặp: protect() trước khi dịch, restore() sau khi dịch.
    Không có trạng thái dùng chung giữa các câu nên an toàn khi hai chiều
    JA->VI và VI->JA chạy song song.
    """

    MAX_SLOTS = 8

    def __init__(self) -> None:
        self.unknown: dict[str, int] = {}

    def protect(self, text: str, lang: str) -> tuple[str, dict[str, str]]:
        """
        Trả (text đã thay placeholder, bảng bung ngược).

        Chỉ làm cho tiếng Nhật: ASR tiếng Việt đã bị hạ hết về chữ thường
        (TERM-03) nên không còn tín hiệu viết hoa để nhận ra danh từ riêng,
        mà "anh/chị/em + <từ>" thì khớp nhầm tràn lan ("anh xem giúp em").
        Tên tiếng Việt phải khai trong people.json.
        """
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
        """
        Bung placeholder về tên gốc. Trả (text, số slot BỊ MẤT).

        Số slot mất > 0 nghĩa là M2M-100 đã nuốt placeholder — bên gọi phải
        biết để log, chứ không được im lặng trả về câu thiếu tên người.
        """
        if not mapping:
            return text, 0

        # Model đôi khi chép placeholder nhưng đổi hoa-thường ("pna", "PNA").
        # Cứu trước, đếm mất sau — đảo thứ tự là báo mất nhầm những slot thực
        # ra vẫn còn, và cảnh báo trong log mất hết giá trị.
        def _salvage(m: re.Match) -> str:
            return mapping.get("Pn" + m.group(1).upper(), m.group(0))

        text = re.sub(r"\bp[nN]([a-zA-Z])\b", _salvage, text)

        lost = 0
        for slot, original in mapping.items():
            pat = r"\b" + slot + r"\b"
            if re.search(pat, text):
                text = re.sub(pat, original, text)
            elif original not in text:
                # Không còn placeholder mà cũng không thấy tên gốc -> mất thật.
                lost += 1

        return re.sub(r"\s+", " ", text).strip(), lost


def people_to_entries(people: list[dict]) -> list[dict]:
    """
    Lớp A — biến danh sách người dự thành mục từ điển.

    Mỗi người sinh ra tối đa hai mục:
      1. "<tên>さん" -> "<Latin>-san"   (dài hơn, được thay TRƯỚC)
      2. "<tên>"     -> "<Latin>"       (chỉ khi dạng viết đủ dài để an toàn)

    Mục 2 bị CHẶN với tên một ký tự kanji: máy khớp phía tiếng Nhật không có
    ranh giới từ (tiếng Nhật không có dấu cách), nên đăng ký "一" sẽ ăn luôn
    một-chữ-一 trong 一緒/一番/一致 và phá nát câu. Tên một ký tự chỉ được
    nhận diện khi đi kèm kính ngữ.
    """
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

        # Chỉ đăng ký dạng trần khi đủ dài để không ăn nhầm giữa từ khác.
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
# 5. TIẾNG ĐỆM
# ---------------------------------------------------------------------------
#
# Tiếng đệm lúc nghĩ ("えーと", "あのー", "ừ thì") không mang nội dung, nhưng
# M2M-100 vẫn phải dịch chúng thành MỘT CÁI GÌ ĐÓ. Với beam search, vài token
# vô nghĩa ở đầu câu đủ để lái cả câu sang hướng khác và sinh ra phần thừa —
# đúng triệu chứng "bản dịch lan man".
#
# Chỉ cắt những dạng KHÔNG THỂ nhầm với từ thật:
#   - えーと / えっと / ええと / うーん / んー : không có nghĩa nào khác.
#   - あのー / そのー (có dấu kéo dài ー): dạng kéo dài chỉ dùng khi ngập ngừng.
# CỐ TÌNH GIỮ LẠI:
#   - あの / その không kéo dài -> là từ chỉ định ("cái đó", "người kia").
#   - なんか -> là danh từ/phó từ thật ("cái gì đó", "kiểu như").
#   - まあ  -> nhiều khi mang sắc thái nhượng bộ có nghĩa.
# Cắt nhầm nhóm này thì mất nội dung thật, tệ hơn hẳn việc để lại tiếng đệm.

_JA_FILLER_RE = re.compile(
    r"(?:えーと|えっと|ええと|えーっと|うーん|うんーと|んー|えー(?![るりらろ])|"
    r"あのー+|そのー+|あーー*)"
    r"[、,\s]*"
)

# Tiếng Việt: ASR đã hạ hết về chữ thường trước khi tới đây (TERM-03).
# Neo hai đầu bằng ranh giới khoảng trắng để "à" không ăn mất âm tiết "à"
# trong "cà phê" hay "và".
#
# CỐ TÌNH KHÔNG cắt:
#   "ạ"      -> tiểu từ KÍNH NGỮ, không phải tiếng đệm. Cắt đi thì chiều
#               vi->ja mất tín hiệu lịch sự và model chọn thể suồng sã.
#   "hả/hử"  -> dấu hỏi, mang nghĩa.
#   "ơ"      -> vừa là thán từ vừa là âm tiết thật, không đáng rủi ro.
_VI_FILLER_RE = re.compile(
    r"(?:^|(?<=[\s,]))(?:ừ+m*|ờ+|à|ê)(?=[\s,]|$)[\s,]*",
    re.IGNORECASE,
)


def strip_fillers(text: str, lang: str) -> str:
    """
    Bỏ tiếng đệm khỏi text TRƯỚC KHI DỊCH.

    Chỉ dùng cho bản đưa vào bộ dịch — text nguồn hiển thị cho người dùng
    vẫn giữ nguyên tiếng đệm, vì đó là thứ người ta thực sự đã nói và biên
    bản họp phải trung thực.

    Trả chuỗi rỗng nếu cả đoạn chỉ toàn tiếng đệm — bên gọi phải bỏ qua đoạn
    đó thay vì dịch, nếu không màn hình sẽ hiện một câu bịa từ hư không.
    """
    if not text:
        return text

    out = _JA_FILLER_RE.sub("", text) if lang == "ja" else _VI_FILLER_RE.sub(" ", text)
    out = re.sub(r"\s+", " ", out).strip(" ,、")
    return out


# ---------------------------------------------------------------------------
# 6. LOẠI TRÙNG (BUG-016)
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
# 7. CACHE BẢN DỊCH (BUG-024)
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
# 8. DỌN DẸP CHUNG
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
        self.names = NameProtector()
        self.stats = {"dedup": 0, "glossary": 0, "term_fix": 0, "cache_hit": 0,
                      "name_kept": 0, "name_lost": 0}

    # ------------------------------------------------------------- tên người

    def for_model(self, text: str, lang: str) -> str:
        """
        Bản rút gọn của câu nguồn, CHỈ để đưa vào bộ dịch.

        Tách riêng khỏi text hiển thị: biên bản họp phải giữ đúng lời người
        nói (kể cả tiếng đệm), còn bộ dịch thì nên nhận bản sạch.
        Chuỗi rỗng nghĩa là cả đoạn chỉ có tiếng đệm -> đừng dịch.
        """
        return strip_fillers(text, lang)

    def protect_names(self, text: str, lang: str) -> tuple[str, dict[str, str]]:
        """
        Gọi NGAY TRƯỚC translate(), trên text đã qua prepare_source().

        Chỉ bọc những tên KHÔNG có trong people.json — tên đã khai thì
        fix_source() đã đổi sang dạng Latin từ trước, không còn kính ngữ
        tiếng Nhật để lớp này khớp nữa.
        """
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
