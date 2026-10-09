# -*- coding: utf-8 -*-
"""
Đo chất lượng DỊCH MÁY (không qua ASR) cho 4 chiều: ja↔vi, en↔vi (không có en↔ja).

Mỗi câu nguồn đi qua ĐÚNG pipeline chữ của app:
    prepare_source -> bỏ tiếng đệm -> bọc tên người -> M2M-100 -> finish (glossary)
rồi so với bản tham chiếu.

Cách dùng:
    python eval_mt.py                                   # cả 4 chiều
    python eval_mt.py --dirs en-vi,vi-en                # vài chiều
    python eval_mt.py --sentences testdata/cau_test_mt.tsv --out eval_mt.csv

File câu (.tsv): id<TAB>en<TAB>ja<TAB>vi, dòng bắt đầu bằng # bị bỏ qua.

Chỉ số:
    chrF     điểm n-gram ký tự (0-100, cao hơn = gần tham chiếu hơn). Tính trên
             cả bộ câu. Hợp cho tiếng Nhật (không có dấu cách) và tiếng Việt.
             So sánh GIỮA CÁC CHIỀU trên cùng bộ câu, đừng so với số ở nơi khác.
    ampm     số câu dịch NGƯỢC sáng/chiều (tham chiếu nói chiều, bản dịch nói
             sáng hoặc ngược lại). Lỗi nghiêm trọng trong biên bản họp.
    num      số câu mất/sai con số so với tham chiếu.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from postprocess import PostProcessor, TranslationCache  # noqa: E402

LANGS = ("en", "ja", "vi")
ALL_DIRS = ["ja-vi", "vi-ja", "en-vi", "vi-en"]


# ---------------------------------------------------------------------------
# chrF (Popović 2015) — n-gram ký tự 1..6, beta=2, bỏ khoảng trắng như sacrebleu
# ---------------------------------------------------------------------------

CHRF_N = 6
CHRF_BETA = 2.0


def _char_ngrams(s: str, n: int) -> Counter:
    s = "".join(unicodedata.normalize("NFKC", s).split())
    return Counter(s[i:i + n] for i in range(len(s) - n + 1))


def chrf_stats(hyp: str, ref: str) -> list[tuple[int, int, int]]:
    """[(khớp, tổng_hyp, tổng_ref)] cho từng bậc n."""
    out = []
    for n in range(1, CHRF_N + 1):
        h, r = _char_ngrams(hyp, n), _char_ngrams(ref, n)
        out.append((sum((h & r).values()), sum(h.values()), sum(r.values())))
    return out


def chrf_score(stats: list[list[tuple[int, int, int]]]) -> float:
    """chrF cấp bộ câu: cộng dồn thống kê rồi mới tính F."""
    b2 = CHRF_BETA ** 2
    precs, recs = [], []
    for n in range(CHRF_N):
        m = sum(s[n][0] for s in stats)
        th = sum(s[n][1] for s in stats)
        tr = sum(s[n][2] for s in stats)
        if th and tr:
            precs.append(m / th)
            recs.append(m / tr)
    if not precs:
        return 0.0
    p, r = sum(precs) / len(precs), sum(recs) / len(recs)
    return 100.0 * (1 + b2) * p * r / (b2 * p + r) if p + r else 0.0


# ---------------------------------------------------------------------------
# Kiểm tra sáng/chiều và con số
# ---------------------------------------------------------------------------

_AM = {"en": r"\ba\.?m\.?\b|\bmorning\b", "ja": r"午前|朝", "vi": r"\bsáng\b"}
_PM = {"en": r"\bp\.?m\.?\b|\bafternoon\b|\bevening\b|\btonight\b",
       "ja": r"午後|夕方|夜|今夜", "vi": r"\bchiều\b|\btối\b"}


def _ampm(text: str, lang: str) -> str | None:
    am = bool(re.search(_AM[lang], text, re.IGNORECASE))
    pm = bool(re.search(_PM[lang], text, re.IGNORECASE))
    if am == pm:
        return None
    return "am" if am else "pm"


def ampm_flipped(hyp: str, ref: str, lang: str) -> bool:
    r, h = _ampm(ref, lang), _ampm(hyp, lang)
    return r is not None and h is not None and r != h


_WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
             "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def _numbers(text: str) -> set[int]:
    """Giá trị số trong câu, không phụ thuộc cách viết 1,500 / 1.500 / 200万."""
    t = unicodedata.normalize("NFKC", text)
    vals = set()
    for m in re.finditer(r"\d+(?:[.,]\d{3})*(?:[.,]\d+)?\s*(万|triệu|million)?", t):
        raw = re.sub(r"[.,](?=\d{3}\b)", "", m.group(0).split()[0].rstrip("万"))
        try:
            v = float(raw.replace(",", "."))
        except ValueError:
            continue
        unit = m.group(1)
        if unit == "万":
            v *= 10_000
        elif unit in ("triệu", "million"):
            v *= 1_000_000
        vals.add(int(round(v)))
    for w, v in _WORD_NUM.items():
        if re.search(rf"\b{w}\b", t, re.IGNORECASE):
            vals.add(v)
    return vals


def number_mismatch(hyp: str, ref: str) -> bool:
    r = _numbers(ref)
    return bool(r) and not r <= _numbers(hyp)


# ---------------------------------------------------------------------------
# Chạy
# ---------------------------------------------------------------------------

def load_rows(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 4:
            print(f"⚠️  Bỏ dòng sai định dạng (cần 4 cột): {line[:60]}")
            continue
        rows.append(dict(zip(("id", "en", "ja", "vi"), (p.strip() for p in parts))))
    return rows


def translate_like_app(main, post: PostProcessor, text: str, sl: str, tl: str) -> str:
    src = post.prepare_source(text, sl)
    clean = post.for_model(src, sl)
    mt_in, names = post.protect_names(clean, sl)
    dst, _score = main.translate(mt_in, sl, tl, is_final=True, cache=None)
    dst, _lost = post.restore_names(dst, names)
    return post.finish(src, dst, sl, tl)


def run(sentences: Path, dirs: list[str], out_csv: Path) -> None:
    rows = load_rows(sentences)
    if not rows:
        raise SystemExit(f"Không có câu nào trong {sentences}")

    print("⏳ Nạp model (dùng chung code với main.py)...")
    import main  # noqa: E402

    results, summary = [], []
    for d in dirs:
        sl, tl = d.split("-")
        post = PostProcessor(main.GLOSSARY, cache=TranslationCache())
        stats, n_ampm, n_num = [], 0, 0
        for r in rows:
            hyp = translate_like_app(main, post, r[sl], sl, tl)
            ref = r[tl]
            flip = ampm_flipped(hyp, ref, tl)
            nmis = number_mismatch(hyp, ref)
            n_ampm += flip
            n_num += nmis
            st = chrf_stats(hyp, ref)
            stats.append(st)
            results.append({
                "dir": d, "id": r["id"], "src": r[sl], "ref": ref, "hyp": hyp,
                "chrf": round(chrf_score([st]), 1),
                "ampm_flip": int(flip), "num_mismatch": int(nmis),
            })
        score = chrf_score(stats)
        summary.append((d, score, n_ampm, n_num))
        print(f"✅ {d}: chrF {score:5.1f} | sáng/chiều ngược {n_ampm} | sai số {n_num}")

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8-sig") as f:
        wr = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        wr.writeheader()
        wr.writerows(results)

    print("\n" + "=" * 56)
    print(f"TỔNG KẾT  ({len(rows)} câu mỗi chiều)")
    print(f"  {'chiều':<7}{'chrF':>7}{'sáng/chiều':>13}{'sai số':>9}")
    for d, s, a, n in summary:
        print(f"  {d:<7}{s:7.1f}{a:13d}{n:9d}")
    print(f"\n  Chi tiết từng câu: {out_csv}")


def build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Đo chất lượng dịch máy 4 chiều ja↔vi, en↔vi")
    ap.add_argument("--sentences", type=Path,
                    default=BASE_DIR / "testdata" / "cau_test_mt.tsv")
    ap.add_argument("--dirs", default=",".join(ALL_DIRS),
                    help="các chiều, cách nhau bởi dấu phẩy (vd: en-vi,ja-en)")
    ap.add_argument("--out", type=Path, default=BASE_DIR / "eval_mt.csv")
    return ap


if __name__ == "__main__":
    args = build_argparser().parse_args()
    dirs = [d.strip() for d in args.dirs.split(",") if d.strip()]
    bad = [d for d in dirs if d not in ALL_DIRS]
    if bad:
        raise SystemExit(f"Chiều không hợp lệ: {bad}. Hợp lệ: {ALL_DIRS}")
    run(args.sentences, dirs, args.out)
