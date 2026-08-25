# -*- coding: utf-8 -*-
"""Kiểm thử postprocess.py — chạy: python test_postprocess.py"""
from pathlib import Path

from postprocess import (Glossary, PostProcessor, TranslationCache, cleanup,
                         fix_decimal_locale, normalize_source)

G = Glossary.load(Path(__file__).resolve().parent / "glossary.json")
P = PostProcessor(G, cache=TranslationCache())

PASS = FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    ok = got == want
    PASS += ok
    FAIL += (not ok)
    mark = "✅" if ok else "❌"
    print(f"{mark} {name}")
    if not ok:
        print(f"     muốn: {want!r}")
        print(f"     nhận: {got!r}")


def contains(name, got, sub):
    global PASS, FAIL
    ok = sub in got
    PASS += ok
    FAIL += (not ok)
    print(f"{'✅' if ok else '❌'} {name}")
    if not ok:
        print(f"     thiếu: {sub!r} trong {got!r}")


print("--- TERM-01: sửa nguồn tiếng Việt (ASR CHỮ HOA -> chữ thường -> thuật ngữ)")
check("đíp lôi -> deploy",
      P.prepare_source("ANH ĐÃ ĐÍP LÔI LÊN SƠ VƠ CHƯA", "vi"),
      "Anh đã deploy lên server chưa")
check("chuẩn hoá hoa thường tên riêng (gít háp -> GitHub)",
      P.prepare_source("EM ĐẨY CODE LÊN GÍT HÁP RỒI", "vi"),
      "Em đẩy code lên GitHub rồi")
check("thuật ngữ đứng đầu câu vẫn viết hoa lại",
      P.prepare_source("ĐÍP LÔI XONG RỒI Ạ", "vi"),
      "Deploy xong rồi ạ")
check("từ thường không bị đụng (cam kết là câu nói thật)",
      P.prepare_source("CHÚNG TÔI CAM KẾT HOÀN THÀNH ĐÚNG HẸN", "vi"),
      "Chúng tôi cam kết hoàn thành đúng hẹn")
check("guard nguồn: xin lỗi không dính gì",
      P.prepare_source("XIN LỖI ANH EM ĐẾN MUỘN", "vi"),
      "Xin lỗi anh em đến muộn")

print("--- TERM-01: sửa nguồn tiếng Nhật (katakana -> tiếng Anh)")
check("デプロイ -> deploy (sát kanji vẫn khớp)",
      P.prepare_source("明日デプロイします", "ja"),
      "明日deployします")
check("nghe lệch デプロー vẫn về deploy",
      P.prepare_source("デプローをお願いします", "ja"),
      "deployをお願いします")
check("プルリク (viết tắt) -> pull request",
      P.prepare_source("プルリクを確認してください", "ja"),
      "pull requestを確認してください")
check("レポジトリ (biến thể) -> repository",
      P.prepare_source("レポジトリはギットハブにあります", "ja"),
      "repositoryはGitHubにあります")

print("--- TERM-02: lưới an toàn sau dịch, có điều-kiện-theo-nguồn")
check("JA->VI: nguồn có deploy, dịch ra 'triển khai' -> deploy",
      G.apply("明日deployします", "Ngày mai sẽ triển khai", "ja", "vi")[0],
      "Ngày mai sẽ deploy")
check("JA->VI: nguồn KHÔNG có thuật ngữ -> không đụng bản dịch",
      G.apply("計画を展開します", "Chúng tôi sẽ triển khai kế hoạch", "ja", "vi")[0],
      "Chúng tôi sẽ triển khai kế hoạch")
check("JA->VI: katakana lọt nguyên sang bản dịch -> thay",
      G.apply("サーバーを再起動します", "Khởi động lại サーバー", "ja", "vi")[0],
      "Khởi động lại server")
check("VI->JA: nguồn có deploy, dịch ra デプロイ -> deploy (giữ tiếng Anh)",
      G.apply("anh đã deploy chưa", "もうデプロイしましたか", "vi", "ja")[0],
      "もうdeployしましたか")
check("VI->JA: dịch ra 展開 -> deploy",
      G.apply("chúng ta cần deploy gấp", "早急に展開する必要があります", "vi", "ja")[0],
      "早急にdeployする必要があります")
check("guard đích: nguồn có bug nhưng 'xin lỗi' không bị thay",
      G.apply("バグがあります、すみません", "Có lỗi, xin lỗi anh", "ja", "vi")[0],
      "Có bug, xin lỗi anh")

print("--- Ba ca chồng lấn A/B/C")
# A: chuỗi sai dài chứa chuỗi sai ngắn -> chuỗi dài ăn trước
check("A: 'chi nhánh' ăn trước 'nhánh'",
      G.apply("ブランチを作ります", "Tạo chi nhánh mới", "ja", "vi")[0],
      "Tạo branch mới")
# B: bản chuẩn đã có trong câu đích -> không thay chồng lên
check("B: 'pull request' có sẵn, không thành 'pull request request'",
      G.apply("プルリクを送ります", "Tôi sẽ gửi pull request", "ja", "vi")[0],
      "Tôi sẽ gửi pull request")
# C: chuỗi sai là mảnh của cụm được bảo vệ
check("C: 'nhánh sông' được guard, không thành 'branch sông'",
      G.apply("ブランチと nhánh sông", "Đây là nhánh và nhánh sông", "ja", "vi")[0],
      "Đây là branch và nhánh sông")

print("--- TERM-04: cleanup tiếng Nhật giữ dấu cách giữa từ Latin")
check("pull request không bị dính",
      cleanup("私は pull request を送ります", "ja"),
      "私はpull requestを送ります")
check("khoảng trắng quanh kana vẫn bị xoá",
      cleanup("これ は テスト です", "ja"),
      "これはテストです")

print("--- Tính năng cũ không vỡ")
check("số tiếng Nhật: 千五百円 -> 1,500円",
      normalize_source("千五百円です", "ja"), "1,500円です")
check("số tiếng Việt: hai trăm nghìn -> 200.000",
      normalize_source("giá hai trăm nghìn đồng", "vi"), "giá 200.000 đồng")
check("locale VI: 0.3% -> 0,3%",
      fix_decimal_locale("tăng 0.3%", "vi"), "tăng 0,3%")
check("locale JA: 200.000 -> 200,000",
      fix_decimal_locale("200.000ドン", "ja"), "200,000ドン")
check("cắt lặp cụm: Hướng dẫn hướng dẫn -> Hướng dẫn",
      cleanup("Hướng dẫn hướng dẫn sử dụng", "vi"), "Hướng dẫn sử dụng")
check("láy hợp lệ không bị cắt: xanh xanh",
      cleanup("bầu trời xanh xanh", "vi"), "Bầu trời xanh xanh")

print("--- Bẫy tiếng Việt nguy hiểm")
check("'ai' (đại từ) không bị biến thành 'AI'",
      P.prepare_source("AI LÀ NGƯỜI PHỤ TRÁCH VIỆC NÀY", "vi"),
      "Ai là người phụ trách việc này")
check("'ây ai' mới thành AI",
      P.prepare_source("BÊN EM DÙNG ÂY AI ĐỂ PHÂN TÍCH", "vi"),
      "Bên em dùng AI để phân tích")
check("'mít tinh' (meeting) đổi, nhưng câu không thuật ngữ giữ nguyên",
      P.prepare_source("CHIỀU NAY CÓ MÍT TINH VỚI SẾP", "vi"),
      "Chiều nay có meeting với sếp")
sub_ok = G.apply("gặp nhau ở meeting nhé", "ミーティングで会いましょう", "vi", "ja")[0]
check("VI->JA meeting: ミーティング -> meeting", sub_ok, "meetingで会いましょう")

print("--- Schema cũ vẫn nạp được (tương thích ngược)")
old = Glossary([{"ja": "ブランチ", "vi": "nhánh",
                 "vi_variants": ["chi nhánh", "branch"],
                 "ja_variants": ["支店"],
                 "vi_guard": ["nhánh sông"]}])
check("schema cũ: 1 mục nạp ok", len(old.entries), 1)
check("schema cũ: vẫn ép được thuật ngữ",
      old.apply("ブランチです", "Đây là chi nhánh", "ja", "vi")[0],
      "Đây là nhánh")

print(f"\n{'='*50}\nKẾT QUẢ: {PASS} đạt / {FAIL} lỗi")
raise SystemExit(1 if FAIL else 0)
