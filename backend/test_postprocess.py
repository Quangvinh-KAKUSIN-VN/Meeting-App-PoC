# -*- coding: utf-8 -*-
"""Kiểm thử postprocess.py — chạy: python test_postprocess.py"""
from pathlib import Path

from postprocess import (Glossary, NameProtector, PostProcessor,
                         TranslationCache, cleanup, fix_decimal_locale,
                         normalize_source, people_to_entries, strip_fillers)

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
print("--- Số kanji trong TÊN NGƯỜI không được thành chữ số")
check("千葉さん không thành '1.000 lá'",
      normalize_source("千葉さんが来ます", "ja"), "千葉さんが来ます")
check("百三さん giữ nguyên (không thành 103さん)",
      normalize_source("百三さんに聞いて", "ja"), "百三さんに聞いて")
check("九十九里さん giữ nguyên",
      normalize_source("九十九里さん", "ja"), "九十九里さん")
check("百貨店 không phải số",
      normalize_source("百貨店に行く", "ja"), "百貨店に行く")
check("số THẬT vẫn đổi: 三千円",
      normalize_source("三千円かかります", "ja"), "3,000円かかります")
check("số THẬT vẫn đổi: 千五百人",
      normalize_source("千五百人が参加", "ja"), "1,500人が参加")
check("năm không có dấu phân cách nghìn",
      normalize_source("二千二十六年", "ja"), "2026年")

print("--- Số Ả-rập + đơn vị kanji (lỗi '340010,000' trong biên bản 28/8)")
check("3400万 -> 34,000,000",
      normalize_source("まで3400万です", "ja"), "まで34,000,000です")
check("160万円 -> 1,600,000円",
      normalize_source("160万円かかります", "ja"), "1,600,000円かかります")
check("21万5000円 -> 215,000円 (đuôi lẻ sau đơn vị)",
      normalize_source("一番悪くても21万5000円", "ja"), "一番悪くても215,000円")
check("1億2000万 -> 120,000,000 (hai bậc đơn vị)",
      normalize_source("1億2000万かかる", "ja"), "120,000,000かかる")
check("万が一 giữ nguyên (万 trơ trọi không phải số)",
      normalize_source("万が一のために", "ja"), "万が一のために")
check("万人受け giữ nguyên",
      normalize_source("万人受けする", "ja"), "万人受けする")

print("--- N割 -> N0% (2割 từng bị dịch thành 'hai phần trăm')")
check("2割 -> 20%",
      normalize_source("2割ぐらいです", "ja"), "20%ぐらいです")
check("八割 (kanji) -> 80%",
      normalize_source("八割は完成した", "ja"), "80%は完成した")
check("割り勘 không bị đụng",
      normalize_source("割り勘にしよう", "ja"), "割り勘にしよう")

print("--- Lớp A: người dự trong people.json -> dạng Latin trước khi dịch")
PEOPLE = Glossary(people_to_entries([
    {"name": "Ichi", "ja": ["一", "イチ"], "bad": ["13"],
     "guard": ["一緒", "一番", "一致"]},
    {"name": "Chiba", "ja": ["千葉"]},
]))
PP = PostProcessor(PEOPLE, cache=TranslationCache())
check("一さん -> Ichi-san", PP.prepare_source("一さんが来ます", "ja"), "Ichi-sanが来ます")
check("千葉さん -> Chiba-san", PP.prepare_source("千葉さんです", "ja"), "Chiba-sanです")
check("一緒 KHÔNG bị ăn (guard)",
      PP.prepare_source("一緒に行きましょう", "ja"), "一緒に行きましょう")
check("一番 KHÔNG bị ăn (guard)",
      PP.prepare_source("一番早いのは一さんです", "ja"), "一番早いのはIchi-sanです")
check("tên một kanji KHÔNG đăng ký dạng trần",
      PP.prepare_source("一致しました", "ja"), "一致しました")

print("--- Lớp B: tên chưa khai vẫn sống sót qua bộ dịch")
NP = NameProtector()
out, mp = NP.protect("千葉さんと本田さんが参加します", "ja")
check("hai tên -> hai placeholder", len(mp), 2)
check("hạt nối 'と' KHÔNG bị nuốt vào tên", mp.get("PnB"), "本田さん")
check("bung lại đúng tên",
      NameProtector.restore("PnA và PnB sẽ tham gia.", mp)[0],
      "千葉さん và 本田さん sẽ tham gia.")
check("model hạ chữ thường -> vẫn cứu được",
      NameProtector.restore("pna và pnb sẽ tham gia.", mp)[0],
      "千葉さん và 本田さん sẽ tham gia.")
check("model nuốt placeholder -> đếm đúng số tên mất",
      NameProtector.restore("Họ sẽ tham gia.", mp)[1], 2)
check("皆さん KHÔNG phải tên người", NP.protect("皆さんおはよう", "ja")[1], {})
check("お客さん KHÔNG phải tên người", NP.protect("お客さんが待っています", "ja")[1], {})
check("パン屋さん KHÔNG phải tên người", NP.protect("パン屋さんに行く", "ja")[1], {})
check("chức danh cũng được bọc", NP.protect("田中部長に確認", "ja")[1].get("PnA"), "田中部長")
check("tiếng Việt không dùng lớp B", NP.protect("anh Ichi nói", "vi")[1], {})

print("--- Tiếng đệm bị cắt trước khi dịch, giữ nguyên bản hiển thị")
check("えーと bị cắt",
      strip_fillers("えーと、明日の会議は十時からです", "ja"), "明日の会議は十時からです")
check("あのー bị cắt", strip_fillers("あのー、資料を送りました", "ja"), "資料を送りました")
check("đoạn chỉ toàn tiếng đệm -> rỗng", strip_fillers("えーと", "ja"), "")
check("あの (chỉ định) KHÔNG bị cắt",
      strip_fillers("あの人は誰ですか", "ja"), "あの人は誰ですか")
check("なんか (từ thật) KHÔNG bị cắt",
      strip_fillers("なんか問題がありますか", "ja"), "なんか問題がありますか")
check("ừ bị cắt", strip_fillers("ừ thì cái này cần sửa", "vi"), "thì cái này cần sửa")
check("ạ (kính ngữ) KHÔNG bị cắt",
      strip_fillers("báo cáo đã xong ạ", "vi"), "báo cáo đã xong ạ")
check("hả (dấu hỏi) KHÔNG bị cắt",
      strip_fillers("anh làm xong chưa hả", "vi"), "anh làm xong chưa hả")
check("'và' KHÔNG bị cắt nhầm thành 'v'",
      strip_fillers("cà phê và trà", "vi"), "cà phê và trà")

print(f"\n{'='*50}\nKẾT QUẢ: {PASS} đạt / {FAIL} lỗi")
raise SystemExit(1 if FAIL else 0)