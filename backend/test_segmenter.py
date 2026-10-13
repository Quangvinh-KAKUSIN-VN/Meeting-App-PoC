# -*- coding: utf-8 -*-
"""Kiểm thử segmenter.py — chạy: python test_segmenter.py  (không cần model)"""
from segmenter import (MAX_BUFFER_CHARS, MAX_CARRIES, SOFT_LIMIT, LiveSegment,
                       SentenceBuffer, ends_sentence, split_sentences)

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


def ja(text):
    return split_sentences(text, "ja")


print("--- で+する và 〜ですかって không phải chỗ hết câu")
check("スペインでする: không cắt ở です",
      ja("スペインでするその日本の行事ってちょっといいですね"),
      ["スペインでするその日本の行事ってちょっといいですね"])
check("〜ですかって: trích dẫn, câu còn tiếp",
      ja("日本から持ってきたんですかって、みんなびっくりしてました"),
      ["日本から持ってきたんですかって、みんなびっくりしてました"])

print("--- Tiếng Nhật: tách ở đuôi lịch sự")
check("đoạn trong biên bản 12/10 (3 câu dính liền)",
      ja("今日のエピソードでは私の朝のルーティンを紹介します仕事を始めるまでのルーティーンですね"
         "自然な日本語で話すのでぜひリスニングの練習に使ってください"),
      ["今日のエピソードでは私の朝のルーティンを紹介します",
       "仕事を始めるまでのルーティーンですね",
       "自然な日本語で話すのでぜひリスニングの練習に使ってください"])
check("ますか + câu mới",
      ja("何か質問はありますか特になければ本日の会議は以上です"),
      ["何か質問はありますか", "特になければ本日の会議は以上です"])
check("ます + なので (liên từ mở đầu câu sau)",
      ja("朝は結構時間がありますなので私が朝ごはんを作ります"),
      ["朝は結構時間があります", "なので私が朝ごはんを作ります"])
check("ください + câu mới",
      ja("レビューしてくださいマージは明日の予定です"),
      ["レビューしてください", "マージは明日の予定です"])
check("dấu câu có sẵn",
      ja("リクエストがタイムアウトしました。サーバーの処理が遅いのが原因かもしれません。"),
      ["リクエストがタイムアウトしました。", "サーバーの処理が遅いのが原因かもしれません。"])
check("câu hỏi lựa chọn",
      ja("午後4時は日本時間ですかベトナム時間ですか"),
      ["午後4時は日本時間ですか", "ベトナム時間ですか"])

print("--- Tiếng Nhật: KHÔNG tách khi câu còn tiếp")
check("〜ましたが", ja("本番環境へデプロイしましたがエラーが発生しました"),
      ["本番環境へデプロイしましたがエラーが発生しました"])
check("〜ますので", ja("確認しますので少々お待ちください"),
      ["確認しますので少々お待ちください"])
check("〜ですから", ja("明日は休みですから対応できません"),
      ["明日は休みですから対応できません"])
check("〜ですけど", ja("この件なんですけど仕様がまだ固まっていません"),
      ["この件なんですけど仕様がまだ固まっていません"])
check("〜ましたら (điều kiện)", ja("完了しましたら連絡してください"),
      ["完了しましたら連絡してください"])
check("〜ですし", ja("値段も安いですし処理も速いです"),
      ["値段も安いですし処理も速いです"])
check("〜ますと (điều kiện)", ja("そうしますとコストが上がります"),
      ["そうしますとコストが上がります"])
check("〜ますかどうか", ja("対応できますかどうか確認します"),
      ["対応できますかどうか確認します"])
check("〜くださいますよう", ja("ご確認くださいますようお願いします"),
      ["ご確認くださいますようお願いします"])
check("〜ますでしょうか", ja("資料はございますでしょうか"),
      ["資料はございますでしょうか"])
check("ますます (phó từ)", ja("アクセスがますます増えています"),
      ["アクセスがますます増えています"])
check("ですね chêm giữa câu, theo sau là を",
      ja("インゲン豆っていう野菜ですねを焼いたやつを置きます"),
      ["インゲン豆っていう野菜ですねを焼いたやつを置きます"])

print("--- Tiếng Nhật: で/い ghép ngẫu nhiên với từ sau KHÔNG phải です/ます")
check("で + すごく (biên bản 12/10)",
      ja("何だかんだですごくバタバタしました"), ["何だかんだですごくバタバタしました"])
check("なので + すぐに", ja("重要なのですぐに確認します"), ["重要なのですぐに確認します"])
check("いますぐ (今すぐ)", ja("いますぐ対応します"), ["いますぐ対応します"])
check("ですら", ja("専門家ですら気づきません"), ["専門家ですら気づきません"])

print("--- Tiếng Nhật: chữ mở đầu câu sau trùng với tiểu từ / liên từ")
check("です + よろしく (よ không phải tiểu từ)",
      ja("報告は以上ですよろしくお願いします"),
      ["報告は以上です", "よろしくお願いします"])
check("です + しかし", ja("処理が遅いですしかし問題はありません"),
      ["処理が遅いです", "しかし問題はありません"])
check("ます + とりあえず", ja("会議を終わりますとりあえず次回は来週です"),
      ["会議を終わります", "とりあえず次回は来週です"])
check("です + かなり", ja("原因は不明ですかなり時間がかかります"),
      ["原因は不明です", "かなり時間がかかります"])
check("です + ということで", ja("報告は以上ですということで次の議題に進みます"),
      ["報告は以上です", "ということで次の議題に進みます"])

print("--- Tiếng Nhật: câu quá ngắn dính vào câu sau")
check("すみません + câu",
      ja("すみません会議に数分遅れました"),
      ["すみません、会議に数分遅れました"])
check("はい。 + câu",
      ja("はい。今週中に見積もりを出します"),
      ["はい。今週中に見積もりを出します"])
check("了解しました。 + câu",
      ja("了解しました。その方法で進めます。"),
      ["了解しました。その方法で進めます。"])
check("câu ngắn KHÔNG dính vào phần còn dở",
      ja("そうですね明日の会議は"),
      ["そうですね", "明日の会議は"])
check("câu ngắn đứng cuối thì đứng riêng",
      ja("資料を確認しましたはい。"),
      ["資料を確認しました", "はい。"])

print("--- Tiếng Nhật: cắt mềm khi quá dài")
long_ja = ("お客様から新しい要望が来ていまして検索機能のレスポンスが遅いので"
           "来週のリリースまでにキャッシュを追加して改善してほしいという連絡を昨日の夜にメールで受け取りました")
check("câu > SOFT_LIMIT cắt ở ので", len(long_ja) > SOFT_LIMIT["ja"] and ja(long_ja),
      ["お客様から新しい要望が来ていまして検索機能のレスポンスが遅いので",
       "来週のリリースまでにキャッシュを追加して改善してほしいという連絡を昨日の夜にメールで受け取りました"])
mid_ja = "金曜日に本番環境へデプロイしましたがログイン画面でエラーが発生したためロールバックしました"
check("câu ≤ SOFT_LIMIT để nguyên", ja(mid_ja), [mid_ja])
check("から = 'từ' không phải chỗ cắt",
      len(ja("9時から" + "あ" * 80)), 1)

print("--- ends_sentence")
check("ja: です", ends_sentence("原因はバグです", "ja"), True)
check("ja: ますよね", ends_sentence("できるようになりますよね", "ja"), True)
check("ja: ましょうか", ends_sentence("早速始めましょうか", "ja"), True)
check("ja: dấu câu", ends_sentence("すごい簡単。", "ja"), True)
check("ja: trợ từ", ends_sentence("明日の会議は", "ja"), False)
check("ja: ですが", ends_sentence("確認したんですが", "ja"), False)
check("ja: thể thường", ends_sentence("もうすぐできる", "ja"), False)
check("en: dấu chấm", ends_sentence("We found a bug.", "en"), True)
check("en: dở", ends_sentence("We found a bug in the", "en"), False)
check("vi: luôn False (chỉ im lặng mới chốt)", ends_sentence("em gửi rồi ạ", "vi"), False)

print("--- Tiếng Anh / tiếng Việt")
check("en: tách ở dấu chấm, câu ngắn dính vào câu sau",
      split_sentences("Okay. Let's start the meeting. Please review the design document.", "en"),
      ["Okay. Let's start the meeting.", "Please review the design document."])
check("en: e.g. không phải hết câu",
      split_sentences("Use a cache, e.g. Redis, for this endpoint.", "en"),
      ["Use a cache, e.g. Redis, for this endpoint."])
check("en: số thập phân không phải hết câu",
      split_sentences("Latency dropped to 2.5 seconds after the fix.", "en"),
      ["Latency dropped to 2.5 seconds after the fix."])
vi_short = "em đã fix bug và push lên branch main rồi anh review giúp em nhé"
check("vi: đoạn ngắn để nguyên", split_sentences(vi_short, "vi"), [vi_short])
vi_long = ("hôm qua em đã deploy bản mới lên môi trường staging và chạy toàn bộ test case "
           "tuy nhiên vẫn còn ba case bị fail ở phần thanh toán nên em chưa thể release "
           "lên production trong hôm nay được")
check("vi: đoạn dài cắt trước 'tuy nhiên'",
      split_sentences(vi_long, "vi"),
      ["hôm qua em đã deploy bản mới lên môi trường staging và chạy toàn bộ test case",
       "tuy nhiên vẫn còn ba case bị fail ở phần thanh toán nên em chưa thể release "
       "lên production trong hôm nay được"])

print("--- SentenceBuffer: chốt từng câu, nối phần dở")
b = SentenceBuffer("ja")
check("đoạn 1: một câu chốt + phần dở",
      b.push("本日の会議を始めますまず先週の"),
      [(1, "本日の会議を始めます", True), (2, "まず先週の", False)])
check("đoạn 2: phần dở trọn câu, GIỮ id cũ",
      b.push("リリースについて報告します"),
      [(2, "まず先週のリリースについて報告します", True)])
check("đoạn 3: câu trọn vẹn chốt ngay, id mới",
      b.push("原因はバグです"), [(3, "原因はバグです", True)])
check("không còn gì để chốt", b.flush(True), [])

print("--- SentenceBuffer: im lặng chốt câu lửng")
b = SentenceBuffer("ja")
check("thể thường -> chờ", b.push("もうすぐできる"), [(1, "もうすぐできる", False)])
check("mốc im lặng thường -> chốt", b.flush(False), [(1, "もうすぐできる", True)])
b = SentenceBuffer("ja")
b.push("明日の会議は")
check("kết bằng trợ từ: mốc thường CHƯA chốt", b.flush(False), [])
check("nói tiếp -> nối, giữ id",
      b.push("午後3時からです"), [(1, "明日の会議は午後3時からです", True)])
b = SentenceBuffer("ja")
b.push("明日の会議は")
check("kết bằng trợ từ rồi im hẳn: mốc dài chốt",
      b.flush(True), [(1, "明日の会議は", True)])

print("--- SentenceBuffer: từ mở đầu / từ định ngữ đứng cuối đoạn (biên bản 13/10)")
for dangling in ("まず最初にたくさんと流ちょうなんですけどもとにかく",
                 "このプロセスを取っていきたいつまり",
                 "もこのとちゅうの日本語を考えるっていう",
                 "シャドーイングをやってみるってどういう"):
    b = SentenceBuffer("ja")
    b.push(dangling)
    check(f"…{dangling[-5:]}: mốc im lặng thường chưa chốt", b.flush(False), [])
b = SentenceBuffer("ja")
b.push("このプロセスを取っていきたいつまり")
check("nói tiếp -> nối thành một câu",
      b.push("考えて話すっていうtrainingをしなきゃいけないわけなんです"),
      [(1, "このプロセスを取っていきたいつまり考えて話すっていうtrainingをしなきゃいけないわけなんです", True)])
b = SentenceBuffer("ja")
b.push("training方法だ")
check("だ (hệ từ kết câu) vẫn chốt ở mốc im lặng thường",
      b.flush(False), [(1, "training方法だ", True)])

print("--- SentenceBuffer: dấu 。 do ASR tự thêm ở cuối đoạn")
b = SentenceBuffer("ja")
check("。 sau mệnh đề điều kiện -> bỏ dấu, chờ nói tiếp",
      b.push("問題がなければ。"), [(1, "問題がなければ", False)])
check("đoạn sau nối vào thành một câu",
      b.push("明日の午後3時に再度リリースする予定です"),
      [(1, "問題がなければ明日の午後3時に再度リリースする予定です", True)])
b = SentenceBuffer("ja")
check("。 sau đuôi lịch sự -> tin, chốt ngay",
      b.push("まず先週のリリースについて報告します。"),
      [(1, "まず先週のリリースについて報告します。", True)])
b = SentenceBuffer("ja")
check("。 sau câu thể thường -> chờ mốc im lặng",
      b.push("すごい簡単。"), [(1, "すごい簡単", False)])
check("im lặng đủ lâu -> chốt", b.flush(False), [(1, "すごい簡単", True)])
b = SentenceBuffer("ja")
check("。 nằm GIỮA đoạn vẫn là ranh giới câu",
      b.push("今年の7月に移住する予定なんだよね。で日本には帰りません"),
      [(1, "今年の7月に移住する予定なんだよね。", True), (2, "で日本には帰りません", True)])

print("--- SentenceBuffer: trần an toàn")
b = SentenceBuffer("ja")
outs = [b.push("資料を見ながら") for _ in range(MAX_CARRIES + 1)]
check(f"nối quá {MAX_CARRIES} đoạn -> buộc chốt",
      [o[-1][2] for o in outs], [False] * MAX_CARRIES + [True])
check("sau khi buộc chốt, bộ đệm rỗng", b.flush(True), [])
b = SentenceBuffer("ja")
check("phần dở dài quá trần -> buộc chốt",
      b.push("あ" * (MAX_BUFFER_CHARS["ja"] + 1))[-1][2], True)

print("--- SentenceBuffer: tiếng Việt / tiếng Anh")
b = SentenceBuffer("vi")
check("vi: chưa chốt (dịch nháp), chờ im lặng",
      b.push("em gửi tài liệu rồi"), [(1, "em gửi tài liệu rồi", False)])
check("vi: nối bằng dấu cách",
      b.push("anh xem giúp em nhé"),
      [(1, "em gửi tài liệu rồi anh xem giúp em nhé", False)])
check("vi: im lặng -> chốt",
      b.flush(False), [(1, "em gửi tài liệu rồi anh xem giúp em nhé", True)])
b = SentenceBuffer("vi")
b.push("tuần sau anh đi công tác với")
check("vi: kết bằng giới từ, mốc thường chưa chốt", b.flush(False), [])
b = SentenceBuffer("en")
check("en: câu có dấu chấm chốt ngay",
      b.push("We found a bug in the test environment."),
      [(1, "We found a bug in the test environment.", True)])
check("en: hai câu + phần dở",
      b.push("Please fix it today. I will review it. Then we can"),
      [(2, "Please fix it today.", True), (3, "I will review it.", True),
       (4, "Then we can", False)])

print("--- SentenceBuffer.peek: xem trước mà không đổi trạng thái")
b = SentenceBuffer("ja")
b.push("本日の会議を始めますまず先週の")
state = (b.tail, b.tail_id, b.msg_id, b.carries)
expected = [(2, "まず先週のリリースについて報告します", True), (3, "次に", False)]
check("peek trả đúng thứ push sẽ trả", b.peek("リリースについて報告します次に"), expected)
check("peek không đổi trạng thái", (b.tail, b.tail_id, b.msg_id, b.carries), state)
check("push sau đó cấp đúng các id đã xem trước",
      b.push("リリースについて報告します次に"), expected)

print("--- LiveSegment: lọc lần nhận dạng dở bị nuốt chữ")
live = LiveSegment()
check("chữ dài dần -> nhận", [live.accept("それでは本日の"), live.accept("それでは本日の定例会議を始めます")],
      [True, True])
check("ngắn hẳn đi một lần -> bỏ qua", live.accept("それでは本の定例"), False)
check("lần kế vẫn ngắn -> ASR sửa thật, nhận", live.accept("それでは本の定例会"), True)
check("dao động 1-2 ký tự không tính là nuốt", live.accept("それでは本の定例"), True)
live.reset()
check("đoạn mới bắt đầu lại từ đầu", live.accept("はい"), True)

print(f"\n{'='*50}\nKẾT QUẢ: {PASS} đạt / {FAIL} lỗi")
raise SystemExit(1 if FAIL else 0)
