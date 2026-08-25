# -*- coding: utf-8 -*-
"""
Bộ đo chất lượng thuật ngữ — chạy file WAV qua ĐÚNG pipeline của app:
    ASR -> sửa thuật ngữ (tầng 1) -> dịch M2M-100 -> hậu xử lý (tầng 2)
rồi so với câu tham chiếu, xuất báo cáo CSV + tổng kết ra màn hình.

Cách dùng:
    python eval_terms.py --lang vi --wav-dir recordings/vi --sentences testdata/cau_test_vi.tsv
    python eval_terms.py --lang ja --wav-dir recordings/ja --sentences testdata/cau_test_ja.tsv

File câu (.tsv): mỗi dòng "tên_file<TAB>câu tham chiếu", dòng bắt đầu bằng #
bị bỏ qua. File WAV nào chưa thu thì tự động bỏ qua — thu được bao nhiêu
đo bấy nhiêu.

WAV mọi sample rate / stereo đều đọc được (tự trộn mono + resample về 16k),
nhưng khuyến nghị thu thẳng 16000 Hz mono 16-bit cho đúng điều kiện thật.

Chạy script này nạp cả 3 model như lúc chạy app (mất ~30-60s trên máy yếu).

Các cột trong report:
    asr_raw    text ASR thô (tiếng Việt sẽ là CHỮ HOA)
    src_fixed  sau tầng 1 — đây là text thật sự được đưa vào bộ dịch
    dst        bản dịch cuối cùng (đã qua tầng 2) — cái người xem thấy
    heard_raw  ASR có nghe ra thuật ngữ ở DẠNG BẤT KỲ không (kể cả nghe lệch
               đã có trong từ điển) — thấp nghĩa là cần chạy learn_terms.py
    ok_src     sau tầng 1, text nguồn có đúng bản chuẩn ("deploy") không
    ok_dst     phụ đề cuối có đúng bản chuẩn không — CON SỐ QUAN TRỌNG NHẤT
    cer        tỉ lệ lỗi ký tự của src_fixed so với câu tham chiếu
               (0.0 = trùng khớp; 0.15 đổ xuống thường là nghe khá tốt)
"""

from __future__ import annotations

import argparse
import csv
import sys
import unicodedata
import wave
from pathlib import Path

import numpy as np

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from postprocess import PostProcessor, TranslationCache  # noqa: E402

# Khớp main.py — chỉ là hằng số, còn model/glossary nạp bên trong run()
# (import main mới nạp model; để trong hàm thì --help khỏi chờ 60 giây).
SAMPLE_RATE = 16000


# ---------------------------------------------------------------------------
# Đọc WAV: mọi định dạng PCM phổ biến -> float32 mono 16k
# ---------------------------------------------------------------------------

def read_wav_16k_mono(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        n_ch = w.getnchannels()
        width = w.getsampwidth()
        rate = w.getframerate()
        raw = w.readframes(w.getnframes())

    if width == 2:
        x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif width == 4:
        x = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    elif width == 1:
        x = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 3:                    # 24-bit PCM: đệm mỗi mẫu lên 4 byte
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        pad = np.where(b[:, 2] >= 128, 255, 0).astype(np.uint8)[:, None]
        x = (np.concatenate([b, pad], axis=1).view("<i4").ravel()
             .astype(np.float32) / 8388608.0)
    else:
        raise ValueError(f"Không hỗ trợ WAV {width * 8}-bit: {path.name}")

    if n_ch > 1:
        x = x.reshape(-1, n_ch).mean(axis=1)

    if rate != SAMPLE_RATE:
        n_out = int(round(len(x) * SAMPLE_RATE / rate))
        x = np.interp(
            np.linspace(0.0, len(x) - 1.0, n_out, dtype=np.float64),
            np.arange(len(x), dtype=np.float64), x).astype(np.float32)
    return x


# ---------------------------------------------------------------------------
# CER (Character Error Rate) — Levenshtein mức ký tự
# ---------------------------------------------------------------------------

def _norm_for_cer(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    return "".join(ch for ch in s if ch.isalnum())


def cer(ref: str, hyp: str) -> float:
    r, h = _norm_for_cer(ref), _norm_for_cer(hyp)
    if not r:
        return 0.0 if not h else 1.0
    prev = list(range(len(h) + 1))
    for i, rc in enumerate(r, 1):
        cur = [i] + [0] * len(h)
        for j, hc in enumerate(h, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rc != hc))
        prev = cur
    return prev[-1] / len(r)


# ---------------------------------------------------------------------------
# Thuật ngữ trong câu
# ---------------------------------------------------------------------------

def expected_terms(glossary, ref: str, lang: str) -> list[dict]:
    """
    Các mục glossary xuất hiện trong câu tham chiếu (bản chuẩn hoặc dạng nghe-ra).

    Loại "kỳ vọng ảo" do thuật ngữ lồng nhau: データベース chứa データ nên
    nếu quét ngây thơ thì câu database bị tính thêm cả "data" (rồi báo trượt
    oan vì text sau sửa là "database", không khớp "data" đứng riêng).
    Quy tắc: mục nào MỌI vùng khớp đều nằm trọn trong vùng khớp DÀI HƠN của
    mục khác thì không phải kỳ vọng của câu này.
    """
    cands: list[tuple[dict, list[tuple[int, int]]]] = []
    for e in glossary.entries:
        spans = [m.span() for m in e["_term_pat"][lang].finditer(ref)]
        for p, _n in e["_hears_pat"][lang]:
            spans += [m.span() for m in p.finditer(ref)]
        if spans:
            cands.append((e, spans))

    hits = []
    for e, spans in cands:
        covered = all(
            any(os <= s and t <= oe and (oe - os) > (t - s)
                for other, ospans in cands if other is not e
                for os, oe in ospans)
            for s, t in spans)
        if not covered:
            hits.append(e)
    return hits


def heard_any_form(e: dict, text: str, lang: str) -> bool:
    return bool(e["_term_pat"][lang].search(text)) or any(
        p.search(text) for p, _n in e["_hears_pat"][lang])


def has_canonical(e: dict, text: str, lang: str) -> bool:
    return bool(e["_term_pat"][lang].search(text))


# ---------------------------------------------------------------------------
# Chạy
# ---------------------------------------------------------------------------

def run(lang: str, wav_dir: Path, sentences: Path, out_csv: Path) -> None:
    print("⏳ Nạp model (dùng chung code với main.py, mất ~30-60s)...")
    import main  # noqa: E402 — nạp 3 model + glossary y hệt app thật

    tgt = "vi" if lang == "ja" else "ja"
    rec = main.recognizer_ja if lang == "ja" else main.recognizer_vi
    lock = main.recognizer_ja_lock if lang == "ja" else main.recognizer_vi_lock

    rows = []
    for line in sentences.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            fname, ref = line.split("\t", 1)
        except ValueError:
            print(f"⚠️  Dòng sai định dạng (thiếu TAB): {line[:50]}")
            continue
        rows.append((fname.strip(), ref.strip()))

    if not rows:
        raise SystemExit(f"Không có câu nào trong {sentences}")

    results = []
    n_missing = 0
    for fname, ref in rows:
        wav = wav_dir / fname
        if not wav.exists():
            n_missing += 1
            continue

        samples = read_wav_16k_mono(wav)
        raw = main.recognize(rec, lock, samples)

        post = PostProcessor(main.GLOSSARY, cache=TranslationCache())
        src_fixed = post.prepare_source(raw, lang)
        dst, _lp = main.translate(src_fixed, lang, tgt, cache=None)
        dst = post.finish(src_fixed, dst, lang, tgt)

        terms = expected_terms(main.GLOSSARY, ref, lang)
        heard = [e["term"] for e in terms if heard_any_form(e, raw, lang)]
        ok_src = [e["term"] for e in terms if has_canonical(e, src_fixed, lang)]
        ok_dst = [e["term"] for e in terms if has_canonical(e, dst, tgt)]

        r = {
            "file": fname,
            "ref": ref,
            "asr_raw": raw,
            "src_fixed": src_fixed,
            "dst": dst,
            "terms_expected": ", ".join(e["term"] for e in terms),
            "heard_raw": ", ".join(heard),
            "ok_src": ", ".join(ok_src),
            "ok_dst": ", ".join(ok_dst),
            "n_terms": len(terms),
            "n_heard": len(heard),
            "n_ok_src": len(ok_src),
            "n_ok_dst": len(ok_dst),
            "cer": round(cer(ref, src_fixed), 3),
        }
        results.append(r)

        mark = "✅" if r["n_ok_dst"] == r["n_terms"] else "🔶"
        print(f"{mark} {fname}  CER={r['cer']:.2f}  "
              f"thuật ngữ {r['n_ok_dst']}/{r['n_terms']}")
        print(f"     nghe : {raw}")
        print(f"     sửa  : {src_fixed}")
        print(f"     dịch : {dst}")

    if not results:
        raise SystemExit(
            f"Không tìm thấy file WAV nào trong {wav_dir} khớp với danh sách. "
            f"Kiểm tra lại tên file (vd: {rows[0][0]}).")

    # ------------------------------------------------------------------ CSV
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8-sig") as f:
        wr = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        wr.writeheader()
        wr.writerows(results)

    # ------------------------------------------------------------- tổng kết
    n = len(results)
    t_all = sum(r["n_terms"] for r in results)
    t_heard = sum(r["n_heard"] for r in results)
    t_src = sum(r["n_ok_src"] for r in results)
    t_dst = sum(r["n_ok_dst"] for r in results)
    mean_cer = sum(r["cer"] for r in results) / n

    def pct(a, b):
        return f"{100.0 * a / b:5.1f}%" if b else "  n/a"

    print("\n" + "=" * 62)
    print(f"TỔNG KẾT  ({n} file đo được"
          + (f", {n_missing} file chưa thu" if n_missing else "") + ")")
    print(f"  CER trung bình (nguồn sau sửa vs tham chiếu): {mean_cer:.3f}")
    print(f"  Thuật ngữ trong bộ câu:                {t_all}")
    print(f"  ASR nghe ra dạng bất kỳ:               {t_heard}  ({pct(t_heard, t_all)})")
    print(f"  Nguồn có bản chuẩn sau tầng sửa:       {t_src}  ({pct(t_src, t_all)})")
    print(f"  PHỤ ĐỀ cuối có bản chuẩn:              {t_dst}  ({pct(t_dst, t_all)})")
    print(f"\n  Báo cáo chi tiết: {out_csv}")
    if t_heard < t_all:
        print("  💡 'Nghe ra' còn thấp -> thu âm các từ bị trượt rồi chạy "
              "learn_terms.py để dạy thêm dạng nghe-lệch.")


def build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Đo chất lượng bắt & dịch thuật ngữ trên bộ câu test")
    ap.add_argument("--lang", required=True, choices=["ja", "vi"],
                    help="ngôn ngữ NÓI trong file WAV")
    ap.add_argument("--wav-dir", required=True, type=Path,
                    help="thư mục chứa file WAV đã thu")
    ap.add_argument("--sentences", required=True, type=Path,
                    help="file .tsv: tên_file<TAB>câu tham chiếu")
    ap.add_argument("--out", type=Path, default=None,
                    help="đường dẫn CSV báo cáo (mặc định: eval_<lang>.csv)")
    return ap


if __name__ == "__main__":
    args = build_argparser().parse_args()
    out = args.out or (BASE_DIR / f"eval_{args.lang}.csv")
    run(args.lang, args.wav_dir, args.sentences, out)
