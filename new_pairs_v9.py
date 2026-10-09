"""Sinh data_v9.jsonl = data_v8.jsonl + bộ ba mới của v9.

    python new_pairs_v9.py

Nhóm mới (đều nhắm vào thứ app gặp thật nhưng data v8 chưa có):
  target_names   tên người dạng "X-san" — đúng dạng glossary/people.json đưa vào
                 model; notebook v9 còn đổi ngẫu nhiên sang placeholder PnA/PnB
                 (NameProtector) cho chiều ja→vi.
  target_short   câu ngắn/đệm trong họp — dạng M2M-100 hay bịa nghĩa nhất.
  target_jargon  thuật ngữ BrSE/dự án offshore Nhật: 工数, 切り分け, 横展開,
                 本番反映, 差分, 納期, 持ち帰り, 影響範囲, 手戻り...
"""
import json
from pathlib import Path

ROOT = Path(__file__).parent
SRC, OUT = ROOT / "data_v8.jsonl", ROOT / "data_v9.jsonl"

# (vi, ja, en)
NAMES = [
    ("Kishimoto-san xem giúp em tài liệu này nhé.", "Kishimoto-san、この資料を確認していただけますか。", "Kishimoto-san, could you check this document?"),
    ("Ota-san đang nghỉ phép đến thứ Sáu.", "Ota-sanは金曜日まで休暇中です。", "Ota-san is on leave until Friday."),
    ("Phần backend do Quan-san phụ trách.", "バックエンドはQuan-sanが担当しています。", "Quan-san is in charge of the backend."),
    ("Em đã gửi mail cho Shinoda-san rồi.", "Shinoda-sanにメールを送りました。", "I've sent an email to Shinoda-san."),
    ("Sayaka-san sẽ trình bày phần demo.", "デモはSayaka-sanが発表します。", "Sayaka-san will present the demo."),
    ("Vinh-san share màn hình giúp em với.", "Vinh-san、画面を共有していただけますか。", "Vinh-san, could you share your screen?"),
    ("Chiba-san có ý kiến gì không ạ?", "Chiba-sanは何かご意見ありますか。", "Chiba-san, do you have any comments?"),
    ("Theo Nao-san thì spec này chưa chốt.", "Nao-sanによると、この仕様はまだ確定していないそうです。", "According to Nao-san, this spec hasn't been finalized yet."),
    ("Julia-san vừa vào họp.", "Julia-sanが会議に参加しました。", "Julia-san just joined the meeting."),
    ("Em sẽ hỏi lại Fuji-san rồi báo anh.", "Fuji-sanに確認してから連絡します。", "I'll check with Fuji-san and let you know."),
    ("Lisa-san review giúp em pull request này nhé.", "Lisa-san、このプルリクエストのレビューをお願いします。", "Lisa-san, could you review this pull request?"),
    ("Mendy-san và Pon-san đang xử lý lỗi đó.", "その不具合はMendy-sanとPon-sanが対応しています。", "Mendy-san and Pon-san are working on that bug."),
    ("Kuniko-san nhờ em sửa màn hình login.", "Kuniko-sanからログイン画面の修正を頼まれました。", "Kuniko-san asked me to fix the login screen."),
    ("Dong-san hôm nay nghỉ ốm.", "Dong-sanは今日病欠です。", "Dong-san is out sick today."),
    ("Son-san đã deploy bản mới lên staging.", "Son-sanが新しいバージョンをステージングにデプロイしました。", "Son-san deployed the new version to staging."),
    ("Cảm ơn Icchi-san đã hỗ trợ.", "Icchi-san、サポートしていただきありがとうございます。", "Thank you for your support, Icchi-san."),
    ("Tanaka-san đã gửi spec mới cho em chưa?", "Tanaka-sanは新しい仕様書を送ってくれましたか。", "Has Tanaka-san sent you the new spec yet?"),
    ("Sato-san và Suzuki-san sẽ tham gia buổi review.", "レビューにはSato-sanとSuzuki-sanが参加します。", "Sato-san and Suzuki-san will join the review."),
    ("Có vấn đề gì thì liên hệ Yamada-san nhé.", "何か問題があれば、Yamada-sanに連絡してください。", "If there are any problems, please contact Yamada-san."),
    ("Ota-san nói là khách muốn dời lịch demo.", "Ota-sanによると、お客様がデモの日程を変更したいそうです。", "Ota-san said the client wants to reschedule the demo."),
    ("Em đã nhờ Kishimoto-san cấp quyền repo.", "Kishimoto-sanにリポジトリの権限付与をお願いしました。", "I asked Kishimoto-san to grant repo access."),
    ("Quan-san với Vinh-san cùng làm task này nhé.", "このタスクはQuan-sanとVinh-sanで一緒に進めてください。", "Quan-san and Vinh-san, please work on this task together."),
    ("Sayaka-san có nghe rõ không ạ?", "Sayaka-san、聞こえますか。", "Sayaka-san, can you hear me?"),
    ("Shinoda-san đang nói dở, mọi người đợi chút nhé.", "Shinoda-sanがまだ話しているので、少し待ちましょう。", "Shinoda-san is still talking, so let's wait a moment."),
    ("Kết quả test em đã gửi cho Nao-san.", "テスト結果はNao-sanに送りました。", "I've sent the test results to Nao-san."),
    ("Phần này Chiba-san nắm rõ nhất.", "この部分はChiba-sanが一番詳しいです。", "Chiba-san knows this part best."),
    ("Takahashi-san chưa trả lời mail.", "Takahashi-sanからまだメールの返信がありません。", "Takahashi-san hasn't replied to the email yet."),
    ("Mình chờ Fuji-san xác nhận rồi mới release nhé.", "Fuji-sanの確認を待ってからリリースしましょう。", "Let's wait for Fuji-san's confirmation before releasing."),
    ("Em xin giới thiệu, đây là Julia-san bên team QA.", "ご紹介します。QAチームのJulia-sanです。", "Let me introduce Julia-san from the QA team."),
    ("Lisa-san với em sẽ lo phần tài liệu.", "ドキュメントはLisa-sanと私が担当します。", "Lisa-san and I will take care of the documentation."),
]

SHORT = [
    ("Vâng ạ.", "はい。", "Yes."),
    ("Dạ, em hiểu rồi.", "はい、わかりました。", "Yes, I understand."),
    ("Đúng rồi.", "そうです。", "That's right."),
    ("Không, không phải vậy.", "いいえ、そうではありません。", "No, that's not it."),
    ("Ok anh.", "了解です。", "Okay."),
    ("Chờ em một chút.", "ちょっと待ってください。", "Just a moment."),
    ("Alo, mọi người nghe thấy em không?", "もしもし、聞こえますか。", "Hello, can you hear me?"),
    ("Em nghe rõ rồi.", "よく聞こえます。", "I can hear you clearly."),
    ("Tiếng bị rè quá.", "音声にノイズが入っています。", "There's a lot of noise on the audio."),
    ("Màn hình bị đen.", "画面が真っ黒です。", "The screen is black."),
    ("Hình như mạng bị lag.", "ネットワークが遅いみたいです。", "The connection seems laggy."),
    ("Cảm ơn anh.", "ありがとうございます。", "Thank you."),
    ("Không có gì ạ.", "どういたしまして。", "You're welcome."),
    ("Xin lỗi anh.", "すみません。", "Sorry."),
    ("Thế à?", "そうなんですか。", "Is that so?"),
    ("Hay quá.", "いいですね。", "That's great."),
    ("Xong rồi ạ.", "完了しました。", "It's done."),
    ("Cái này em làm được.", "これは対応できます。", "I can handle this."),
    ("Cái này thì hơi khó.", "これはちょっと難しいです。", "This one is a bit difficult."),
    ("Để em xem.", "確認します。", "Let me check."),
    ("Chưa ạ.", "まだです。", "Not yet."),
    ("Em không có câu hỏi.", "質問はありません。", "I have no questions."),
    ("Tạm thời như vậy đã.", "とりあえず以上です。", "That's all for now."),
    ("Em nói tiếp nhé.", "続けます。", "I'll continue."),
    ("Anh nói trước đi.", "お先にどうぞ。", "Go ahead."),
    ("Ừ, được.", "うん、いいよ。", "Yeah, sure."),
    ("Rồi, mình chuyển sang mục tiếp theo.", "では、次の議題に移ります。", "Alright, let's move on to the next item."),
    ("Nhất trí.", "賛成です。", "Agreed."),
    ("Em cũng nghĩ vậy.", "私もそう思います。", "I think so too."),
    ("Chắc là không kịp.", "たぶん間に合いません。", "It probably won't make it in time."),
    ("Để mai em trả lời nhé.", "明日回答します。", "I'll answer tomorrow."),
    ("Không vấn đề gì.", "問題ありません。", "No problem."),
    ("Anh còn ở đó không?", "まだいらっしゃいますか。", "Are you still there?"),
    ("Được, cứ làm vậy đi.", "はい、それで進めてください。", "Okay, go ahead with that."),
    ("Đợi mọi người vào đủ đã.", "全員揃うまで待ちましょう。", "Let's wait until everyone has joined."),
    ("Em xin phép vào họp trễ.", "会議には遅れて参加します。", "I'll be joining the meeting late."),
]

JARGON = [
    ("Sửa phần này tốn khoảng bao nhiêu effort?", "この修正の工数はどれくらいですか。", "How much effort will this fix take?"),
    ("Em ước tính effort khoảng 3 man-day.", "工数は3人日くらいと見積もっています。", "I estimate the effort at about 3 man-days."),
    ("Trước tiên anh khoanh vùng nguyên nhân giúp em nhé.", "まず原因の切り分けをお願いします。", "First, please narrow down the cause."),
    ("Em đã xác định được lỗi nằm ở frontend hay backend.", "フロントエンドとバックエンドのどちらの問題か切り分けました。", "I've isolated whether the problem is in the frontend or the backend."),
    ("Áp dụng bản sửa này cho các màn hình khác luôn nhé.", "この修正を他の画面にも横展開してください。", "Please apply this fix to the other screens as well."),
    ("Em đã kiểm tra xem các module khác có bị lỗi tương tự không.", "同じ不具合が他のモジュールにないか、横展開して確認しました。", "I checked whether the other modules have the same bug."),
    ("Dự kiến tối mai sẽ đưa lên production.", "本番反映は明日の夜を予定しています。", "We plan to release to production tomorrow night."),
    ("Trước khi đưa lên production, anh kiểm tra lần cuối trên staging giúp em nhé.", "本番反映の前に、ステージングで最終確認をお願いします。", "Before releasing to production, please do a final check on staging."),
    ("Anh gửi giúp em bản diff so với version trước nhé.", "前回のバージョンとの差分を送ってください。", "Please send me the diff from the previous version."),
    ("Em xem diff thì thấy chỉ có file config bị thay đổi.", "差分を確認したら、設定ファイルだけが変わっていました。", "I checked the diff, and only the config file had changed."),
    ("Có kịp hạn bàn giao không anh?", "納期に間に合いそうですか。", "Do you think we'll make the delivery deadline?"),
    ("Bên em xin lùi hạn bàn giao thêm 1 tuần được không ạ?", "納期を1週間延ばしていただけないでしょうか。", "Could we possibly extend the delivery deadline by a week?"),
    ("Em xin phép mang về trao đổi với team rồi trả lời sau ạ.", "一度持ち帰って、チームで検討します。", "Let me take this back and discuss it with the team."),
    ("Việc này bên em sẽ thảo luận nội bộ rồi phản hồi lại ạ.", "この件は社内で検討してから回答いたします。", "We'll discuss this internally and then get back to you."),
    ("Anh điều tra giúp em phạm vi ảnh hưởng nhé.", "影響範囲を調査してください。", "Please investigate the scope of impact."),
    ("Phạm vi ảnh hưởng chỉ ở màn hình login thôi.", "影響範囲はログイン画面だけです。", "The impact is limited to the login screen."),
    ("Hai bên hiểu spec khác nhau nên phải làm lại.", "仕様の認識がずれていたので、手戻りが発生しました。", "We had different understandings of the spec, so we had to redo some work."),
    ("Để tránh phải làm lại, mình confirm spec trước khi code nhé.", "手戻りを防ぐため、実装前に仕様を確認しましょう。", "To avoid rework, let's confirm the spec before implementing."),
    ("Anh cho em xin chút thời gian để thống nhất cách hiểu nhé.", "認識合わせのために、少しお時間をいただけますか。", "Could you spare some time so we can get on the same page?"),
    ("Nếu em hiểu sai thì anh chỉ giúp em nhé.", "私の認識が間違っていたら教えてください。", "Please tell me if my understanding is wrong."),
    ("Anh cho em xin các bước tái hiện lỗi được không?", "不具合の再現手順を教えていただけますか。", "Could you tell me the steps to reproduce the bug?"),
    ("Bên em không tái hiện được lỗi này.", "こちらの環境では再現できませんでした。", "We couldn't reproduce this in our environment."),
    ("Để xử lý tạm thời sự cố, em đã khởi động lại server.", "障害の暫定対応として、サーバーを再起動しました。", "As a temporary fix for the outage, I restarted the server."),
    ("Tuần sau bên em sẽ đưa ra giải pháp triệt để.", "恒久対応は来週までに検討します。", "We'll work out a permanent fix by next week."),
    ("Chào anh, em liên hệ về việc hôm trước ạ.", "お世話になっております。先日の件でご連絡しました。", "Hello, I'm contacting you about the matter from the other day."),
    ("Dạ em hiểu rồi, em sẽ xử lý ngay.", "承知しました。すぐに対応します。", "Understood. I'll take care of it right away."),
    ("Dạ vâng, em sẽ gửi bản sửa trước ngày mai.", "かしこまりました。明日までに修正版をお送りします。", "Certainly. I'll send the revised version by tomorrow."),
    ("Để cho chắc, anh backup lại trước nhé.", "念のため、バックアップを取っておいてください。", "Just in case, please make a backup."),
    ("Tiến độ thế nào rồi anh?", "進捗はいかがでしょうか。", "How's the progress?"),
    ("Đang chậm 2 ngày so với kế hoạch.", "予定より2日遅れています。", "We're 2 days behind schedule."),
    ("Anh đẩy nhanh tiến độ một chút được không?", "スケジュールを少し巻きでお願いできますか。", "Could you speed up the schedule a little?"),
    ("Có vẻ release sớm hơn dự kiến được.", "前倒しでリリースできそうです。", "It looks like we can release ahead of schedule."),
    ("Anh ưu tiên xử lý việc này nhé.", "優先度を上げて対応してください。", "Please handle this with higher priority."),
    ("Em xin lỗi, em đã bỏ sót phần kiểm tra đó.", "確認が漏れていました。申し訳ありません。", "I missed checking that. I'm sorry."),
    ("Anh kiểm tra xem test case có bị sót không nhé.", "テストケースに漏れがないか確認してください。", "Please check whether any test cases are missing."),
    ("Trong tuần này em sẽ viết xong tài liệu thiết kế chi tiết.", "詳細設計書を今週中に作成します。", "I'll finish the detailed design document this week."),
    ("Review thiết kế cơ bản đã xong rồi.", "基本設計のレビューは完了しました。", "The basic design review is complete."),
    ("Trong đợt test nghiệm thu, khách có chỉ ra vài điểm.", "受け入れテストでいくつか指摘がありました。", "The client pointed out a few issues during acceptance testing."),
    ("Em đã sửa các điểm anh góp ý, anh kiểm tra lại giúp em.", "ご指摘の点を修正しました。ご確認をお願いします。", "I've fixed the points you raised. Please take a look."),
    ("Nếu không có vấn đề gì thì mình làm theo hướng này nhé.", "問題なければ、この方針で進めます。", "If there are no issues, we'll proceed with this approach."),
    ("Em đã điền câu trả lời vào file Q&A rồi.", "QA表に回答を記入しました。", "I've filled in the answers in the Q&A sheet."),
    ("Anh cho em biết căn cứ của bản ước tính được không?", "見積もりの根拠を教えていただけますか。", "Could you explain the basis for the estimate?"),
]

GROUPS = [("names", "target_names", NAMES), ("short", "target_short", SHORT),
          ("jargon", "target_jargon", JARGON)]


def main():
    rows = [json.loads(l) for l in SRC.read_text(encoding="utf-8").splitlines() if l.strip()]
    eval_txt = {r[k] for r in rows if r["split"] == "eval" for k in ("vi", "ja", "en")}
    seen = {(k, r[k]) for r in rows for k in ("vi", "ja", "en")}

    new = []
    for tag, origin, triples in GROUPS:
        for i, (vi, ja, en) in enumerate(triples, 1):
            for k, v in (("vi", vi), ("ja", ja), ("en", en)):
                assert v not in eval_txt, f"Trùng câu eval: {v}"
                assert (k, v) not in seen, f"Trùng câu đã có: {v}"
                seen.add((k, v))
            new.append({"id": f"v9{tag}{i:03d}", "vi": vi, "ja": ja, "en": en,
                        "origin": origin, "split": "train"})

    with OUT.open("w", encoding="utf-8") as f:
        for r in rows + new:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{OUT.name}: {len(rows)} (v8) + {len(new)} mới = {len(rows) + len(new)}")
    for tag, origin, triples in GROUPS:
        print(f"  {origin:14s} {len(triples)}")


if __name__ == "__main__":
    main()
