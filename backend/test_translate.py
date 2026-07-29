"""
test_translate.py
-----------------
Test THẲNG model dịch (CTranslate2 int8) bằng chữ, KHÔNG qua STT.
Mục đích: xem LoRA đã ngấm thuật ngữ IT chưa (bug->バグ, push->プッシュ...).

Đặt file này trong thư mục backend/ (cạnh main.py) rồi chạy:
    python test_translate.py
"""

from pathlib import Path
import ctranslate2
from transformers import AutoTokenizer

# ============================================================
# Đường dẫn tới model CTranslate2 (chỉnh nếu để chỗ khác)
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "models" / "m2m100_1.2B_int8"

if not MODEL_DIR.exists():
    raise FileNotFoundError(f"Không thấy model tại: {MODEL_DIR}\n"
                            f"-> Kiểm tra lại đường dẫn hoặc đã giải nén model vào chưa.")

print("⏳ Đang nạp model dịch...")
translator = ctranslate2.Translator(str(MODEL_DIR), device="cpu", compute_type="int8")
tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR))
print("✅ Nạp xong!\n")


def translate(text: str, src_lang: str, tgt_lang: str) -> str:
    """Dịch một câu. src_lang/tgt_lang là 'vi' hoặc 'ja'. Giống hệt logic trong main.py."""
    if not text.strip():
        return ""
    tokenizer.src_lang = src_lang
    source_tokens = tokenizer.convert_ids_to_tokens(tokenizer.encode(text))
    target_prefix = [tokenizer.lang_code_to_token[tgt_lang]]
    results = translator.translate_batch(
        [source_tokens],
        target_prefix=[target_prefix],
        max_decoding_length=128,
    )
    target_tokens = results[0].hypotheses[0][1:]
    return tokenizer.decode(
        tokenizer.convert_tokens_to_ids(target_tokens),
        skip_special_tokens=True,
    ).strip()


# ============================================================
# Bộ câu test có sẵn (chú thích = kỳ vọng nếu LoRA ngấm)
# ============================================================
# (src_lang, tgt_lang, câu, ghi chú kỳ vọng)
TESTS = [
    # ---- VI -> JA (mình nói tiếng Việt, ra tiếng Nhật) ----
    ("vi", "ja", "Sửa con bug ở phần thanh toán đi.", "bug -> バグ (KHÔNG phải 虫)"),
    ("vi", "ja", "Anh push code lên nhánh dev rồi, em review nhé.", "push->プッシュ, nhánh->ブランチ, review->レビュー"),
    ("vi", "ja", "Chiều nay mình deploy lên production nhé.", "deploy->デプロイ, production->本番"),
    ("vi", "ja", "Nhánh của em bị conflict với main rồi.", "conflict->コンフリクト, nhánh->ブランチ"),
    ("vi", "ja", "Em nhớ merge nhánh feature vào dev nhé.", "merge->マージ"),
    ("vi", "ja", "Em thêm endpoint mới cho phần lấy danh sách user nhé.", "endpoint->エンドポイント"),
    ("vi", "ja", "Commit này thiếu message rõ ràng, sửa lại đi.", "commit->コミット"),
    ("vi", "ja", "Task này em ước tính khoảng 3 ngày công.", "câu họp thường"),
    ("vi", "ja", "Deadline cuối tháng hơi gấp, mình bàn lại nhé.", "câu họp thường"),
    ("vi", "ja", "Cảm ơn mọi người, buổi họp hôm nay tới đây thôi nhé.", "câu họp thường"),

    # ---- JA -> VI (đối phương nói tiếng Nhật, ra tiếng Việt) ----
    ("ja", "vi", "決済部分のバグを修正してください。", "ra 'bug', 'sửa'"),
    ("ja", "vi", "devブランチにプッシュしたのでレビューをお願いします。", "ra push/nhánh/review"),
    ("ja", "vi", "本番環境にデプロイします。", "ra deploy/production"),
    ("ja", "vi", "このAPIはページネーションが必要です。", "ra API/phân trang"),
    ("ja", "vi", "明日の朝9時に会議をしましょう。", "câu họp thường"),
    ("ja", "vi", "この機能は次のフェーズに延期します。", "câu họp thường"),
]


def run_preset():
    print("=" * 60)
    print("BỘ CÂU TEST CÓ SẴN")
    print("=" * 60)
    cur = None
    for src, tgt, text, note in TESTS:
        if (src, tgt) != cur:
            cur = (src, tgt)
            print(f"\n----- {src.upper()} -> {tgt.upper()} -----")
        out = translate(text, src, tgt)
        print(f"[{src}] {text}")
        print(f"[{tgt}] {out}")
        print(f"   (kỳ vọng: {note})\n")


def run_interactive():
    print("=" * 60)
    print("CHẾ ĐỘ GÕ TAY (Enter rỗng hoặc 'q' để thoát)")
    print("=" * 60)
    while True:
        choice = input("Chiều dịch [1=vi→ja, 2=ja→vi, q=thoát]: ").strip().lower()
        if choice in ("q", ""):
            break
        if choice == "1":
            src, tgt = "vi", "ja"
        elif choice == "2":
            src, tgt = "ja", "vi"
        else:
            print("   Nhập 1, 2 hoặc q.\n")
            continue
        text = input(f"Câu tiếng {'Việt' if src == 'vi' else 'Nhật'}: ").strip()
        if not text:
            continue
        print(f"   => {translate(text, src, tgt)}\n")


if __name__ == "__main__":
    run_preset()
    run_interactive()
    print("Xong.")