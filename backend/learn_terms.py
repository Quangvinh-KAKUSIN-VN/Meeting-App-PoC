# -*- coding: utf-8 -*-
"""
"Dạy" từ điển cách TAI CỦA ASR nghe thuật ngữ qua giọng thật của người dùng.

Ý tưởng: bạn đọc từng thuật ngữ vào mic (2-3 lần mỗi từ), ASR nghe ra gì
thì cái đó chính là dạng cần thêm vào ja_hears / vi_hears. Không cần đoán mò.

Bước 1 — thu âm, mỗi file MỘT thuật ngữ, đặt tên theo mẫu:
        <slug>__<số thứ tự>.wav
    slug = thuật ngữ viết thường, ký tự đặc biệt/dấu cách thay bằng "-":
        deploy__1.wav   deploy__2.wav
        pull-request__1.wav
        ci-cd__1.wav          (CI/CD)
        api-key__1.wav        (API key)
    Nói TỰ NHIÊN như lúc họp, đừng cố phát âm chuẩn Anh-Mỹ.

Bước 2 — chạy thử (chỉ in đề xuất, KHÔNG sửa gì):
    python learn_terms.py --lang vi --wav-dir recordings/terms_vi

Bước 3 — ưng rồi thì ghi vào từ điển (tự backup glossary.json trước):
    python learn_terms.py --lang vi --wav-dir recordings/terms_vi --apply

Script có bộ lọc an toàn: đề xuất trùng với từ tiếng Việt phổ thông
("ai", "anh", "không"...) bị LOẠI thẳng, đề xuất quá ngắn bị đánh dấu ⚠️
để bạn tự cân nhắc — thêm nhầm một từ phổ thông vào vi_hears sẽ làm app
"sửa" cả câu nói bình thường của con người.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from eval_terms import read_wav_16k_mono  # noqa: E402  (import nhẹ, không nạp model)

GLOSSARY_FILE = BASE_DIR / "glossary.json"

# Từ tiếng Việt phổ thông — cấm tuyệt đối đưa vào vi_hears.
_VI_STOPWORDS = {
    "ai", "anh", "em", "chị", "cô", "chú", "bác", "ông", "bà", "tôi", "ta",
    "mình", "bạn", "nó", "họ", "và", "là", "của", "cho", "với", "này", "kia",
    "đó", "gì", "không", "có", "rồi", "chưa", "đã", "sẽ", "đang", "được",
    "đi", "ăn", "làm", "nói", "xem", "biết", "nha", "nhé", "ạ", "dạ", "vâng",
    "ừ", "ờ", "à", "ơi", "thì", "mà", "nếu", "vì", "nên", "cũng", "rất",
    "quá", "lắm", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám",
    "chín", "mười", "trăm", "nghìn", "triệu",
}


def slugify(term: str) -> str:
    s = term.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def normalize_heard(text: str, lang: str) -> str:
    text = unicodedata.normalize("NFKC", text).strip()
    if lang == "vi":
        text = text.lower()
        text = re.sub(r"\s+", " ", text)
        text = text.strip(" .,!?;:")
    else:
        text = re.sub(r"[ \u3000]+", "", text)
        text = text.strip("。、．，！？!?")
    return text


def classify(proposal: str, entry: dict, lang: str) -> tuple[str, str]:
    """Trả (trạng thái, ghi chú). Trạng thái: ok / da_co / loai / canh_bao."""
    if not proposal:
        return "loai", "ASR không nghe ra gì (file lặng hoặc quá nhỏ?)"

    if entry["_term_pat"][lang].search(proposal):
        return "da_co", "ASR đã nhận ra đúng bản chuẩn — không cần dạy thêm"
    lowered = [h.lower() for h in entry[f"{lang}_hears"]]
    if proposal.lower() in lowered:
        return "da_co", "dạng này đã có trong từ điển"

    if lang == "vi":
        words = proposal.split()
        if all(w in _VI_STOPWORDS for w in words):
            return "loai", "toàn từ tiếng Việt phổ thông — thêm vào sẽ phá câu thường"
        if len(words) == 1 and (len(proposal) <= 3 or proposal in _VI_STOPWORDS):
            return "canh_bao", "một từ đơn rất ngắn — dễ trùng từ thật, tự cân nhắc"
        if any(w in _VI_STOPWORDS for w in words):
            return "canh_bao", ("có chứa từ phổ thông (" +
                                ", ".join(w for w in words if w in _VI_STOPWORDS) +
                                ") — kiểm tra kỹ trước khi ghi")
    else:
        if len(proposal) <= 1:
            return "canh_bao", "quá ngắn — dễ khớp lung tung"

    return "ok", ""


def run(lang: str, wav_dir: Path, apply: bool, out_json: Path) -> None:
    print("⏳ Nạp model (dùng chung code với main.py, mất ~30-60s)...")
    import main  # noqa: E402

    rec = main.recognizer_ja if lang == "ja" else main.recognizer_vi
    lock = main.recognizer_ja_lock if lang == "ja" else main.recognizer_vi_lock

    slug_map = {slugify(e["term"]): e for e in main.GLOSSARY.entries}

    wavs = sorted(wav_dir.glob("*.wav"))
    if not wavs:
        raise SystemExit(f"Không có file .wav nào trong {wav_dir}")

    proposals: dict[str, list[str]] = {}
    warnings: dict[str, list[str]] = {}

    for wav in wavs:
        slug = wav.stem.split("__")[0].strip().lower()
        entry = slug_map.get(slug)
        if entry is None:
            print(f"⏭️  {wav.name}: '{slug}' không có trong glossary — bỏ qua "
                  f"(muốn dạy từ hoàn toàn mới thì thêm mục vào glossary.json trước)")
            continue

        try:
            raw = main.recognize(rec, lock, read_wav_16k_mono(wav))
        except Exception as err:
            print(f"⏭️  {wav.name}: không đọc/giải mã được ({err}) — bỏ qua")
            continue
        heard = normalize_heard(raw, lang)
        status, note = classify(heard, entry, lang)

        term = entry["term"]
        if status == "ok":
            proposals.setdefault(term, [])
            if heard not in proposals[term]:
                proposals[term].append(heard)
            print(f"✅ {wav.name}: nghe ra '{heard}' -> đề xuất thêm cho [{term}]")
        elif status == "canh_bao":
            warnings.setdefault(term, [])
            if heard not in warnings[term]:
                warnings[term].append(heard)
            print(f"⚠️  {wav.name}: nghe ra '{heard}' — {note}")
        elif status == "da_co":
            print(f"👌 {wav.name}: '{heard}' — {note}")
        else:
            print(f"🚫 {wav.name}: '{heard}' — {note}")

    if not proposals and not warnings:
        print("\nKhông có gì mới để dạy — hoặc ASR đã nhận tốt, hoặc file thu lỗi.")
        return

    out = {
        "lang": lang,
        "field": f"{lang}_hears",
        "de_xuat": proposals,
        "canh_bao_tu_xem_lai": warnings,
    }
    out_json.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(f"\n📄 Đã ghi đề xuất vào {out_json}")

    if not apply:
        print("   Xem lại file trên. Ưng thì chạy lại kèm --apply để ghi vào "
              "glossary.json (mục cảnh báo ⚠️ KHÔNG tự ghi — muốn thêm thì sửa tay).")
        return

    # ------------------------------------------------------------- --apply
    data = json.loads(GLOSSARY_FILE.read_text(encoding="utf-8"))
    entries = data["entries"] if isinstance(data, dict) else data
    by_term = {e.get("term", ""): e for e in entries}

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = GLOSSARY_FILE.with_suffix(f".json.bak-{stamp}")
    backup.write_text(GLOSSARY_FILE.read_text(encoding="utf-8"), encoding="utf-8")

    n_added = 0
    field = f"{lang}_hears"
    for term, variants in proposals.items():
        e = by_term.get(term)
        if e is None:
            continue
        cur = e.setdefault(field, [])
        for v in variants:
            if v not in cur:
                cur.append(v)
                n_added += 1

    GLOSSARY_FILE.write_text(
        json.dumps({"entries": entries}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"✅ Đã ghi {n_added} dạng nghe-ra mới vào {GLOSSARY_FILE.name} "
          f"(backup: {backup.name})")
    print("   Khởi động lại backend để từ điển mới có hiệu lực.")


def build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Dạy từ điển các dạng nghe-ra của thuật ngữ qua giọng thật")
    ap.add_argument("--lang", required=True, choices=["ja", "vi"],
                    help="ngôn ngữ NÓI trong file WAV")
    ap.add_argument("--wav-dir", required=True, type=Path,
                    help="thư mục file WAV, tên dạng <slug>__<n>.wav")
    ap.add_argument("--apply", action="store_true",
                    help="ghi đề xuất ✅ vào glossary.json (có backup)")
    ap.add_argument("--out", type=Path, default=None,
                    help="file JSON đề xuất (mặc định: learn_proposals_<lang>.json)")
    return ap


if __name__ == "__main__":
    args = build_argparser().parse_args()
    out = args.out or (BASE_DIR / f"learn_proposals_{args.lang}.json")
    run(args.lang, args.wav_dir, args.apply, out)
