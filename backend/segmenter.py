# -*- coding: utf-8 -*-
"""
Tách văn bản ASR thành CÂU trước khi dịch.

Ranh giới CỨNG: dấu câu và, với tiếng Nhật, đuôi vị ngữ lịch sự (です/ます/ください…).
Ranh giới MỀM: chỉ dùng khi câu dài quá SOFT_LIMIT — cắt ở liên từ hoặc dấu phẩy gần giữa câu.
"""

from __future__ import annotations

import os
import re

# ---------------------------------------------------------------------------
# TIẾNG NHẬT
# ---------------------------------------------------------------------------

# Đuôi vị ngữ lịch sự; dạng dài đứng trước. Lookahead loại ましたら/でしたら, ますます và các chỗ
# で/ま ghép ngẫu nhiên với từ đứng sau (ですごく, ですぐ, ですら, でしたい…).
_JA_END = (
    r"(?:"
    r"(?:ください|下さい)(?:ませ(?:ん(?:でした)?)?|ました|ます)?"
    r"|ませんでした|ましょう|でしょう"
    r"|ました(?!ら)|でした(?!ら|い)|ません"
    r"|(?<!ます)ます(?!ます|ぐ)"
    r"|です(?!ごく|ごい|ぐ|っかり|こし|ら|る)"
    r")"
)

# Thứ đứng ngay sau đuôi lịch sự mà câu vẫn còn tiếp (ですが, ますので, ですって, ますと…).
_JA_CONT = re.compile(
    r"(?:が|を|けど|けれど|ので|のに|んで|から|って|でしょう"
    r"|よう(?:に|な|お願い|よろしく)"
    r"|し(?!かし|かも|たがって|ばらく|っかり|ゃ|ゅ|ょ)"
    r"|と(?!りあえず|りわけ|ころで|ころが|にかく|はいえ|ても|もかく|なると|すると"
    r"|いうことで|いうわけで|いうのは|いうのも|いっても))"
)

# Tiểu từ cuối câu đi kèm đuôi lịch sự (よ ね か), trừ khi là đầu một từ (よろしく, かなり…).
_JA_SFP = re.compile(
    r"(?:よ(?![ろくうりほっしいそ])|ね|か(?![なしつもけわら]|っ(?!て)))[ー〜ぇ]*"
)

# Sau tiểu từ cuối câu vẫn có thể là trích dẫn: ですかと聞きました.
_JA_CONT_AFTER_SFP = re.compile(
    r"(?:って|どうか|を"
    r"|と(?!りあえず|りわけ|ころで|ころが|にかく|はいえ|ても|もかく|なると|すると"
    r"|いうことで|いうわけで|いうのは|いうのも|いっても))"
)

_JA_END_RE = re.compile(_JA_END)
_JA_PUNCT = "。！？!?"
# Ngoặc đóng đi theo câu đứng trước nó, không mở đầu câu sau.
_JA_PUNCT_RUN = re.compile(r"[。！？!?]+[」』）)]*")

# Ranh giới MỀM: (regex, điểm phạt cộng vào khoảng cách tới giữa câu).
_JA_SOFT = [
    (re.compile(r"(?:ので|けれども|けれど|けど|のに)、?"), 0),
    (re.compile(r"(?:です|ます|ました|でした|ません|ん)が、?"), 0),
    (re.compile(r"(?<=[たいるだすんく])から、?"), 2),      # から = "vì", không phải "từ"
    (re.compile(r"(?:たら|れば)、?"), 4),
    (re.compile(r"、"), 6),
]

# Trần độ dài trước khi phải cắt MỀM.
SOFT_LIMIT = {"ja": 70, "vi": 150, "en": 180}
_SOFT_MIN_PART = {"ja": 12, "vi": 30, "en": 40}

# Câu hoàn chỉnh nhưng ngắn hơn mức này thì dính vào câu kế tiếp.
_TINY = {"ja": 7, "en": 12, "vi": 0}


def _ja_boundary_after_end(text: str, end: int) -> int | None:
    """`end` là vị trí ngay sau một đuôi lịch sự. Trả vị trí cắt câu, hoặc None nếu câu còn tiếp."""
    if _JA_CONT.match(text, end):
        return None

    pos = end
    for _ in range(3):                      # ですよね / ますかね: tối đa 3 tiểu từ
        m = _JA_SFP.match(text, pos)
        if not m:
            break
        pos = m.end()

    if pos > end and _JA_CONT_AFTER_SFP.match(text, pos):
        return None

    m = _JA_PUNCT_RUN.match(text, pos)
    return m.end() if m else pos


def _ja_hard_cuts(text: str) -> list[int]:
    cuts: list[int] = []
    pos = 0
    n = len(text)

    while pos < n:
        m_end = _JA_END_RE.search(text, pos)
        m_punct = _JA_PUNCT_RUN.search(text, pos)

        # Dấu câu đứng trước đuôi lịch sự kế tiếp -> cắt ở dấu câu.
        if m_punct and (not m_end or m_punct.start() < m_end.start()):
            cuts.append(m_punct.end())
            pos = m_punct.end()
            continue

        if not m_end:
            break

        cut = _ja_boundary_after_end(text, m_end.end())
        if cut is None:
            pos = m_end.end()
            continue
        if cut < n:
            cuts.append(cut)
        pos = cut

    return cuts


def _ja_ends_sentence(text: str) -> bool:
    text = text.rstrip(" 、,」』）)")
    if not text:
        return False
    if text[-1] in _JA_PUNCT:
        return True
    # Tìm đuôi lịch sự cuối cùng mà phần sau nó chỉ gồm tiểu từ cuối câu.
    last = None
    for m in _JA_END_RE.finditer(text):
        last = m
    if last is None:
        return False
    return _ja_boundary_after_end(text, last.end()) == len(text)


# ---------------------------------------------------------------------------
# TIẾNG ANH — Parakeet-EN tự sinh dấu câu và viết hoa
# ---------------------------------------------------------------------------

# Chữ viết tắt kết bằng dấu chấm không phải hết câu (lookbehind phải có độ dài cố định).
_EN_ABBR = (r"(?<!\bMr\.)(?<!\bMs\.)(?<!\bDr\.)(?<!\bvs\.)(?<!\bNo\.)(?<!\bMrs\.)"
            r"(?<!\be\.g\.)(?<!\bi\.e\.)")
_EN_BOUNDARY = re.compile(r"(?<=[.?!])" + _EN_ABBR + r"[\"')\]]*\s+(?=[A-Z0-9\"'(\[])")
_EN_SOFT = [
    (re.compile(r"[;:]\s+"), 0),
    (re.compile(r",\s+(?=(?:and|but|so|because|which|while|although)\b)", re.IGNORECASE), 0),
    (re.compile(r",\s+"), 12),
]


def _en_hard_cuts(text: str) -> list[int]:
    return [m.end() for m in _EN_BOUNDARY.finditer(text)]


# ---------------------------------------------------------------------------
# TIẾNG VIỆT — không có ranh giới CỨNG; chỉ cắt MỀM ở từ nối luôn mở đầu một vế mới
# ---------------------------------------------------------------------------

_VI_SOFT = [
    (re.compile(r"[.?!;]\s+"), 0),
    (re.compile(r"\s+(?=(?:nhưng mà|nhưng|tuy nhiên|vì vậy|vì thế|do đó|do vậy|cho nên"
                r"|sau đó|ngoài ra|bên cạnh đó|tiếp theo|cuối cùng|đầu tiên"
                r"|thứ nhất|thứ hai|thứ ba|còn về|về phần)\b)", re.IGNORECASE), 0),
    (re.compile(r",\s+"), 12),
]


# ---------------------------------------------------------------------------
# DÙNG CHUNG
# ---------------------------------------------------------------------------

def _slice(text: str, cuts: list[int]) -> list[str]:
    parts, start = [], 0
    for cut in cuts:
        if cut > start:
            parts.append(text[start:cut])
            start = cut
    parts.append(text[start:])
    return parts


def _clean(parts: list[str]) -> list[str]:
    out = []
    for p in parts:
        p = p.strip(" 　、,")
        if p:
            out.append(p)
    return out


def _soft_split(text: str, lang: str) -> list[str]:
    """Cắt đôi (đệ quy) một câu dài quá SOFT_LIMIT ở ranh giới mềm gần giữa nhất."""
    limit = SOFT_LIMIT[lang]
    if len(text) <= limit:
        return [text]

    patterns = {"ja": _JA_SOFT, "en": _EN_SOFT, "vi": _VI_SOFT}[lang]
    min_part = _SOFT_MIN_PART[lang]
    middle = len(text) / 2

    best = None
    for pat, penalty in patterns:
        for m in pat.finditer(text):
            cut = m.end()
            if cut < min_part or len(text) - cut < min_part:
                continue
            cost = abs(cut - middle) + penalty * (limit / 70)
            if best is None or cost < best[0]:
                best = (cost, cut)

    if best is None:
        return [text]

    cut = best[1]
    left, right = text[:cut], text[cut:]
    return _soft_split(left, lang) + _soft_split(right, lang)


def _merge_tiny(parts: list[str], lang: str) -> list[str]:
    """Dính câu quá ngắn vào câu kế tiếp (trừ khi câu kế tiếp là câu cuối còn dở)."""
    tiny = _TINY[lang]
    if not tiny or len(parts) < 2:
        return parts

    last_is_open = not ends_sentence(parts[-1], lang)
    out: list[str] = []
    held = ""

    for i, part in enumerate(parts):
        is_last = i == len(parts) - 1
        if held:
            if lang == "ja":
                glue = "" if held[-1] in _JA_PUNCT else "、"
            else:
                glue = " "
            part = held + glue + part
            held = ""

        core = len(part.strip(_JA_PUNCT + ". "))
        can_hold = (not is_last
                    and not (i == len(parts) - 2 and last_is_open)
                    and len(part) + len(parts[i + 1]) <= SOFT_LIMIT[lang])
        if core < tiny and can_hold:
            held = part
        else:
            out.append(part)

    return out


def hard_cuts(text: str, lang: str) -> list[int]:
    """Vị trí (chỉ số ký tự) ngay SAU mỗi ranh giới câu CỨNG nằm bên trong `text`."""
    if lang == "ja":
        return _ja_hard_cuts(text)
    if lang == "en":
        return _en_hard_cuts(text)
    return []


def split_sentences(text: str, lang: str) -> list[str]:
    """Tách `text` thành các câu. Mọi câu trừ câu cuối đều đã hoàn chỉnh."""
    text = (text or "").strip()
    if not text:
        return []

    hard = _slice(text, hard_cuts(text, lang))

    out: list[str] = []
    for sentence in _merge_tiny(_clean(hard), lang):
        out.extend(_clean(_soft_split(sentence, lang)))
    return out


def ends_sentence(text: str, lang: str) -> bool:
    """True nếu `text` kết bằng dấu hiệu hết câu rõ ràng. Tiếng Việt luôn False."""
    text = (text or "").strip()
    if not text:
        return False
    if lang == "ja":
        return _ja_ends_sentence(text)
    if lang == "en":
        return bool(re.search(r"[.?!][\"')\]]*$", text))
    return False


# ---------------------------------------------------------------------------
# BỘ ĐỆM CÂU
# ---------------------------------------------------------------------------

# Câu chốt khi có dấu hiệu hết câu (bộ tách câu ở trên) hoặc khi im lặng đủ lâu (flush).

# Đuôi cho biết câu còn tiếp dù người nói ngắt hơi: hạt cách, liên từ / thể nối, tiếng đệm.
JA_PARTICLES = "を|に|で|と|へ|が|も|や|の|は"
JA_CONJUNCTIVE = ("ので|のに|けど|けれど|けれども|んですが|ですが|ますが|"
                  "たら|れば|なら|して|くて|ながら|つつ|でも|から|とか|など|"
                  "そして|それで|それから|ただ|または|および|て|し|ば")
JA_FILLERS = ("えーと|えっと|ええと|あのー|あの|そのー|その|まあ|まぁ|"
              "なんか|なんて|ええ|うーん|んー|えー|あー")
# Từ mở đầu / định ngữ chỉ có nghĩa khi có thứ theo sau (とにかく, つまり, っていう…).
JA_DANGLING = ("とにかく|つまり|例えば|たとえば|だから|なので|もしくは|もし|"
               "やっぱり|ちなみに|実は|特に|"
               "っていう|という|どういう|こういう|そういう|どんな|こんな|そんな|ような|みたいな")

JA_CONTINUES = re.compile(
    r"(?<!こんにち)(?<!こんばん)"
    r"(?:" + JA_PARTICLES + r"|" + JA_CONJUNCTIVE + r"|" + JA_FILLERS
    + r"|" + JA_DANGLING + r"|、)"
    r"\s*$"
)

# Tiếng Việt: giới từ, liên từ, lượng từ, trợ động từ đứng cuối đoạn thì câu chưa xong.
VI_CONTINUES = re.compile(
    r"\b(và|nhưng|thì|để|mà|nên|vì|do|nếu|khi|hoặc|với|của|cho|theo|về|"
    r"là|các|những|một|cái|con|chiếc|trong|trên|dưới|ngoài|sau|trước|giữa|"
    r"cần|phải|sẽ|đang|đã|bị|được|còn|cũng|rất|hơi|khá|từ|đến|tới|bằng|"
    r"như|tại|bởi|nhờ|cùng|sang|qua|ừ|à|ờ|ừm|ạ à|thế thì|tức là|nghĩa là)"
    r"\s*$",
    re.IGNORECASE,
)

# Tiếng Anh: mạo từ, giới từ, liên từ, trợ động từ đứng cuối đoạn thì câu chưa xong.
EN_CONTINUES = re.compile(
    r"\b(and|but|or|so|because|if|when|while|although|though|unless|than|"
    r"the|a|an|this|that|these|those|my|your|our|their|his|her|its|"
    r"of|to|in|on|at|for|with|from|by|about|into|onto|over|under|after|"
    r"before|between|through|during|like|as|"
    r"is|are|was|were|be|been|will|would|can|could|should|must|might|"
    r"have|has|had|do|does|did|not|very|really|also|um|uh|er)"
    r",?\s*$",
    re.IGNORECASE,
)
_CONTINUES = {"ja": JA_CONTINUES, "vi": VI_CONTINUES, "en": EN_CONTINUES}

# Phần câu còn dở dài quá mức này thì buộc chốt.
MAX_BUFFER_CHARS = {"ja": 100, "vi": 150, "en": 150}

# Số đoạn VAD tối đa được nối vào một câu còn dở trước khi buộc chốt.
MAX_CARRIES = int(os.environ.get("KATOBA_MAX_PAUSE_MERGES", "6"))


class SentenceBuffer:
    """
    Gom chữ ASR thành câu và quyết định câu nào đã chốt.
    push() / flush() trả [(msg_id, text, is_final)]; nhiều nhất một mục chưa chốt, luôn nằm cuối.
    """

    def __init__(self, lang: str):
        self.lang = lang
        self.tail = ""          # phần câu còn dở
        self.tail_id = 0        # id đã cấp cho phần dở (0 = không có)
        self.msg_id = 0
        self.carries = 0        # số đoạn VAD đã góp vào phần dở hiện tại

    def _continues(self, text: str) -> bool:
        return bool(_CONTINUES[self.lang].search(text.strip()))

    def _take_id(self) -> int:
        """Câu đầu tiên sau phần dở dùng lại id của phần dở, để frontend cập nhật đúng dòng đó."""
        if self.tail_id:
            taken, self.tail_id = self.tail_id, 0
            return taken
        self.msg_id += 1
        return self.msg_id

    def push(self, chunk: str) -> list[tuple[int, str, bool]]:
        chunk = chunk.strip()

        # Dấu "。" ở cuối đoạn không đáng tin (ASR chấm theo khoảng lặng): chỉ giữ khi chữ
        # đứng trước đã là dạng kết câu.
        if (self.lang == "ja" and chunk.endswith("。")
                and not ends_sentence(chunk[:-1], "ja")):
            chunk = chunk[:-1].rstrip()

        if not chunk:
            return []

        had_tail = bool(self.tail)
        sep = "" if self.lang == "ja" else " "
        merged = self.tail + sep + chunk if had_tail else chunk

        sentences = split_sentences(merged, self.lang)
        if not sentences:
            return []
        *done, last = sentences

        out = [(self._take_id(), sentence, True) for sentence in done]

        # Vừa chốt được câu nào thì phần dở còn lại là của riêng đoạn này.
        self.carries = self.carries + 1 if had_tail and not done else 1

        closed = (ends_sentence(last, self.lang)
                  or self.carries > MAX_CARRIES
                  or len(last) > MAX_BUFFER_CHARS[self.lang])

        last_id = self._take_id()
        if closed:
            self.tail, self.carries = "", 0
        else:
            self.tail, self.tail_id = last, last_id
        out.append((last_id, last, closed))
        return out

    def peek(self, chunk: str) -> list[tuple[int, str, bool]]:
        """Như push() nhưng không đổi trạng thái — dùng cho bản xem trước."""
        saved = (self.tail, self.tail_id, self.msg_id, self.carries)
        try:
            return self.push(chunk)
        finally:
            self.tail, self.tail_id, self.msg_id, self.carries = saved

    def flush(self, hard: bool = True) -> list[tuple[int, str, bool]]:
        """
        Im lặng đã đủ lâu -> chốt phần câu còn dở.
        hard=False: phần dở kết bằng đuôi nối thì chưa chốt. hard=True: chốt luôn.
        """
        if not self.tail:
            return []
        if not hard and self._continues(self.tail):
            return []
        out = [(self.tail_id, self.tail, True)]
        self.tail, self.tail_id, self.carries = "", 0, 0
        return out


# ---------------------------------------------------------------------------
# ĐOẠN ĐANG NÓI DỞ — bản xem trước (chữ ở đây không bao giờ dùng để chốt câu)
# ---------------------------------------------------------------------------


class LiveSegment:
    """Lọc các lần nhận dạng dở của MỘT đoạn VAD trước khi đem ra làm bản nháp."""

    def __init__(self) -> None:
        self.length = 0
        self.skipped = False

    def reset(self) -> None:
        self.length, self.skipped = 0, False

    def accept(self, raw: str) -> bool:
        """False nếu nên bỏ qua lần nhận dạng này: chữ ngắn hẳn hơn lần trước. Chỉ bỏ một lần."""
        n = len(raw.strip())
        if n < self.length - 3 and not self.skipped:
            self.skipped = True
            return False
        self.skipped = False
        self.length = n
        return True
