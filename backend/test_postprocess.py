# -*- coding: utf-8 -*-
"""Kiểm thử postprocess.py — chạy: python test_postprocess.py"""
from pathlib import Path

from postprocess import (Deduper, Glossary, Lexicon, NameProtector, PostProcessor,
                         TranslationCache, cleanup, fix_decimal_locale, fix_duration,
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
check("số thập phân VI: một phẩy năm triệu -> 1.500.000",
      normalize_source("chi phí một phẩy năm triệu yên", "vi"), "chi phí 1.500.000 yên")
check("số thập phân VI: hai phẩy năm -> 2,5",
      normalize_source("tăng hai phẩy năm lần", "vi"), "tăng 2,5 lần")
check("số thập phân VI: không phẩy không năm -> 0,05",
      normalize_source("sai số không phẩy không năm", "vi"), "sai số 0,05")
check("'dấu phẩy' KHÔNG bị coi là số thập phân",
      normalize_source("thiếu dấu phẩy ở đây", "vi"), "thiếu dấu phẩy ở đây")
check("'tỷ lệ' KHÔNG thành 1.000.000.000",
      normalize_source("tỷ lệ lỗi giảm rồi", "vi"), "tỷ lệ lỗi giảm rồi")
check("'hàng nghìn' KHÔNG thành 'hàng 1.000'",
      normalize_source("hàng nghìn người dùng", "vi"), "hàng nghìn người dùng")
check("ba tỷ vẫn đổi",
      normalize_source("khoảng ba tỷ đồng", "vi"), "khoảng 3.000.000.000 đồng")
check("số VI không có phẩy vẫn như cũ",
      normalize_source("khoảng ba triệu yên", "vi"), "khoảng 3.000.000 yên")
check("locale VI: 0.3% -> 0,3%",
      fix_decimal_locale("tăng 0.3%", "vi"), "tăng 0,3%")
check("locale JA: 200.000 -> 200,000",
      fix_decimal_locale("200.000ドン", "ja"), "200,000ドン")
check("locale JA: số ĐÃ đúng kiểu 1,500 giữ nguyên",
      fix_decimal_locale("約1,500人", "ja"), "約1,500人")
check("locale VI: số ĐÃ đúng kiểu 1.500 giữ nguyên",
      fix_decimal_locale("khoảng 1.500 người", "vi"), "khoảng 1.500 người")
check("locale EN: 2.000.000 -> 2,000,000, giữ 1,500",
      fix_decimal_locale("2.000.000 yen, 1,500 users, 0,3%", "en"),
      "2,000,000 yen, 1,500 users, 0.3%")

print("--- Tiếng Anh")
check("tiếng đệm EN: um/uh bị cắt, 'Umbrella' giữ",
      strip_fillers("Um, I think, uh, we need the Umbrella API.", "en"),
      "I think, we need the Umbrella API.")
check("cleanup EN giữ dấu cách sau dấu phẩy",
      cleanup("Hello ,  world  world  world !", "en"), "Hello, world!")
check("glossary EN->VI: nhánh -> branch khi nguồn có 'branch'",
      G.apply("Check the main branch", "Kiểm tra nhánh chính", "en", "vi")[0],
      "Kiểm tra branch chính")
check("glossary ->JA: hai thuật ngữ liền nhau không bị dính",
      G.apply("deploy to the staging server", "ステージングサーバーにデプロイします",
              "en", "ja")[0],
      "staging serverにdeployします")
check("normalize_source EN không đụng 'ba'/'năm'",
      normalize_source("Ba said five hundred", "en"), "Ba said five hundred")
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
check("えーとですね (câu mào đầu) bị cắt cả cụm",
      strip_fillers("えーとですね、この件なんですけど", "ja"), "この件なんですけど")
check("あのですね đầu câu bị cắt",
      strip_fillers("あのですね仕様がまだ固まっていません", "ja"), "仕様がまだ固まっていません")
check("そうですね (câu trả lời thật) KHÔNG bị cắt",
      strip_fillers("そうですね", "ja"), "そうですね")

print("--- ビュー nằm trong từ khác không bị đổi thành Vue")
check("レビュー -> review, không phải レVue",
      G.fix_source("設計書をレビューしてください", "ja")[0], "設計書をreviewしてください")
check("プレビュー giữ nguyên",
      G.fix_source("プレビュー画面を確認します", "ja")[0], "プレビュー画面を確認します")
check("ビュー đứng riêng vẫn là Vue",
      G.fix_source("ビューの画面を更新します", "ja")[0], "Vueの画面を更新します")
check("仕様 trần -> spec",
      G.fix_source("仕様がまだ固まっていません", "ja")[0], "specがまだ固まっていません")
check("ポッドキャスト giữ nguyên, không thành podキャスト",
      G.fix_source("このポッドキャストは長いです", "ja")[0], "このポッドキャストは長いです")
check("ポッド đứng riêng vẫn là pod",
      G.fix_source("ポッドを再起動します", "ja")[0], "podを再起動します")

print("--- Thuật ngữ katakana ngắn không được cắt vào giữa từ katakana khác")
for word in ("プログラム", "ブログ", "レスポンス", "テキスト", "レストラン", "マージン",
             "ガイドライン", "コンテスト", "コミットメント"):
    check(f"{word} giữ nguyên", G.fix_source(f"{word}を確認します", "ja")[0], f"{word}を確認します")
check("ログ đứng riêng vẫn thành log",
      G.fix_source("ログを確認します", "ja")[0], "logを確認します")
check("テスト+データ (ghép toàn thuật ngữ) vẫn được thay",
      G.fix_source("テストデータを用意します", "ja")[0], "test dataを用意します")

print("--- Từ đời thường đi qua bằng ký hiệu giữ chỗ")
LEX = Lexicon([{"vi": "gạo lứt", "ja": ["玄米"]}, {"vi": "cá hồi", "ja": ["鮭"]},
               {"vi": "việc giặt giũ", "ja": ["洗濯"]}, {"vi": "siêu thị", "ja": ["スーパー"]},
               {"vi": "chồng", "ja": ["旦那さん", "夫"]}, {"vi": "cơm", "ja": ["ごはん"]},
               {"vi": "chuyến công tác", "verb": "đi công tác", "ja": ["出張"]},
               {"vi": "bài tập về nhà", "ja": ["宿題"]}],
              [{"vi": "Mọi người vất vả rồi ạ.", "ja": ["お疲れ様です"]}])
check("từ nhiều kanji", LEX.protect("みそ汁と玄米でした", "ja", "vi"),
      ("みそ汁とW1でした", {"W1": "gạo lứt"}))
check("kanji đơn sau từ chỉ thời gian", LEX.protect("昨日鮭を食べました", "ja", "vi")[0],
      "昨日W1を食べました")
check("kanji đơn trong từ ghép KHÔNG khớp", LEX.protect("鮭茶漬けを食べました", "ja", "vi")[1], {})
check("洗濯 trong 洗濯機 KHÔNG khớp", LEX.protect("洗濯機を買いました", "ja", "vi")[1], {})
check("毎日洗濯 vẫn khớp", LEX.protect("毎日洗濯をします", "ja", "vi")[0], "毎日W1をします")
check("katakana trong từ dài hơn KHÔNG khớp",
      LEX.protect("スーパーユーザーで実行します", "ja", "vi")[1], {})
check("ごはん trong 朝ごはん KHÔNG khớp", LEX.protect("朝ごはんを作ります", "ja", "vi")[1], {})
check("ごはん đứng riêng vẫn khớp", LEX.protect("毎日ごはんを食べます", "ja", "vi")[0],
      "毎日W1を食べます")
check("danh từ dùng làm động từ, mục không có verb -> KHÔNG khớp",
      LEX.protect("宿題します", "ja", "vi")[1], {})
check("mục có verb: dạng động từ lấy nghĩa verb",
      LEX.protect("来週出張します", "ja", "vi"), ("来週W1します", {"W1": "đi công tác"}))
check("mục có verb: dạng danh từ vẫn lấy nghĩa vi",
      LEX.protect("来週の出張は中止です", "ja", "vi"), ("来週のW1は中止です", {"W1": "chuyến công tác"}))
check("bỏ chữ 'làm' model thêm trước động từ",
      LEX.restore("Tuần sau em làm W1.", {"W1": "đi công tác"}), ("Tuần sau em đi công tác.", 0))
check("danh từ thì giữ nguyên chữ 'làm'",
      LEX.restore("Em làm W1 rồi.", {"W1": "bài tập về nhà"}), ("Em làm bài tập về nhà rồi.", 0))
check("câu nguồn đã có sẵn chữ giống ký hiệu -> bỏ qua",
      LEX.protect("W1の玄米です", "ja", "vi")[1], {})
check("chỉ áp cho chiều ja→vi", LEX.protect("玄米が好きです", "ja", "en")[1], {})
PL = PostProcessor(G, cache=TranslationCache(), lexicon=LEX)
lx, words = PL.protect_words("昨日旦那さんと田中さんが来ました", "ja", "vi")
mt, names = PL.protect_names(lx, "ja")
check("từ đời thường trước, tên người sau, ký hiệu không trùng",
      (mt, words, names),
      ("昨日W1と PnA が来ました", {"W1": "chồng"}, {"PnA": "田中さん"}))
out, lost = PL.restore_words("Hôm qua W1 và PnA đã đến.", words)
check("điền nghĩa vào, không mất từ nào",
      (PL.restore_names(out, names)[0], lost), ("Hôm qua chồng và 田中さん đã đến.", 0))
check("model làm mất ký hiệu -> báo để dịch lại",
      PL.restore_words("Hôm qua đã đến.", words)[1], 1)
check("ký hiệu bị model tách / viết thường vẫn nhận ra",
      PL.restore_words("Hôm qua w 1 đã đến.", words), ("Hôm qua chồng đã đến.", 0))
check("đứng đầu câu thì viết hoa",
      PL.restore_words("Xong rồi. W1 đã đến.", words)[0], "Xong rồi. Chồng đã đến.")

print("--- Từ chỉ thời gian / danh xưng đứng trước さん không bị nuốt vào tên người")
NP = PostProcessor(G, cache=TranslationCache())
check("昨日 không dính vào tên", NP.protect_names("昨日田中さんと話しました", "ja"),
      ("昨日 PnA と話しました", {"PnA": "田中さん"}))
check("昨日旦那さん không phải tên người", NP.protect_names("昨日旦那さんと話しました", "ja")[1], {})
check("お医者さん không phải tên người", NP.protect_names("昨日お医者さんと話しました", "ja")[1], {})
check("ご近所さん không phải tên người", NP.protect_names("昨日ご近所さんと話しました", "ja")[1], {})
check("聴くんだ là động từ, không phải tên + くん",
      NP.protect_names("英語のポッドキャストもよく聴くんだけど", "ja")[1], {})
check("聞くんですか cũng vậy", NP.protect_names("毎日何時間ぐらい聞くんですか", "ja")[1], {})
check("田中くん vẫn là tên", NP.protect_names("田中くんが来ました", "ja")[1], {"PnA": "田中くん"})
check("ký hiệu tên bị model tách 'Pn A' vẫn bung được",
      NP.restore_names("Hôm qua Pn A đã đến.", {"PnA": "田中さん"}), ("Hôm qua 田中さん đã đến.", 0))

print("--- Mục chỉ có verb: chỉ thay dạng động từ")
VLEX = Lexicon([{"verb": "háo hức", "ja": ["ワクワク"]}])
check("ワクワクします -> thay", VLEX.protect("明日はワクワクします", "ja", "vi"),
      ("明日はW1します", {"W1": "háo hức"}))
check("ワクワク không kèm する -> để nguyên", VLEX.protect("ワクワクが止まりません", "ja", "vi")[1], {})

print("--- Mẩu câu không có nội dung thì bỏ, 何か đệm đầu câu thì cắt")
check("なんですよ rơi ra sau câu trước", strip_fillers("なんですよ", "ja"), "")
check("một chữ kana lẻ", strip_fillers("ち", "ja"), "")
check("なんですか (= 何ですか) là câu hỏi thật, giữ", strip_fillers("なんですか", "ja"), "なんですか")
check("何か đệm sau tiếng thốt", strip_fillers("そうそう何か毎朝7時に起きます", "ja"), "そうそう毎朝7時に起きます")
check("何か質問 giữ nguyên", strip_fillers("何か質問はありますか", "ja"), "何か質問はありますか")
check("何かあれば giữ nguyên", strip_fillers("でも何かあれば連絡してください", "ja"),
      "でも何かあれば連絡してください")

print("--- Dọn bản dịch: số đầu câu, gạch đầu dòng thừa, thời lượng")
check("câu mở đầu bằng số không viết hoa chữ sau", cleanup("6 giờ, em thấy ngắn.", "vi"), "6 giờ, em thấy ngắn.")
check("gạch đầu dòng thừa", cleanup("- vâng, mọi người ổn không?", "vi"), "Vâng, mọi người ổn không?")
check("số âm đầu câu giữ nguyên", cleanup("-5 độ", "vi"), "-5 độ")
check("6時間 -> 6 tiếng", fix_duration("平日は6時間ぐらい寝てます", "Ngày thường ngủ khoảng 6 giờ."),
      "Ngày thường ngủ khoảng 6 tiếng.")
check("6時 (giờ đồng hồ) giữ nguyên", fix_duration("6時に起きます", "Em dậy lúc 6 giờ."), "Em dậy lúc 6 giờ.")
check("何時間 -> mấy tiếng", fix_duration("あと何時間しか残っていない", "Chỉ còn mấy giờ thôi."),
      "Chỉ còn mấy tiếng thôi.")

print("--- Câu cửa miệng khớp nguyên câu")
check("khớp, bỏ qua dấu câu", PL.phrase("お疲れ様です。", "ja", "vi"), "Mọi người vất vả rồi ạ.")
check("nằm trong câu dài hơn thì KHÔNG khớp", PL.phrase("お疲れ様ですと言いました", "ja", "vi"), None)
check("chỉ áp cho chiều ja→vi", PL.phrase("お疲れ様です", "ja", "en"), None)
check("bỏ qua tiếng thốt đứng trước", PL.phrase("あっお疲れ様です", "ja", "vi"), "Mọi người vất vả rồi ạ.")
check("hai câu cửa miệng nối bằng dấu phẩy", PL.phrase("お疲れ様です、お疲れ様です", "ja", "vi"),
      "Mọi người vất vả rồi ạ. Mọi người vất vả rồi ạ.")
check("một vế không phải câu cửa miệng -> không khớp", PL.phrase("お疲れ様です、田中です", "ja", "vi"), None)

print("--- Lọc trùng không nuốt câu dài chứa một câu ngắn vừa nói")
D = Deduper()
D.is_duplicate("はい")
check("'はい' rồi tới câu dài bắt đầu bằng はい",
      D.is_duplicate("はい、わかりました。今週中に見積もりを出します"), False)
check("lặp lại y hệt vẫn bị coi là trùng",
      D.is_duplicate("はい、わかりました。今週中に見積もりを出します"), True)

print(f"\n{'='*50}\nKẾT QUẢ: {PASS} đạt / {FAIL} lỗi")
raise SystemExit(1 if FAIL else 0)