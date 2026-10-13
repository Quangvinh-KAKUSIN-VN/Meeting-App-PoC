# Tên người, ngắt câu và độ lan man — KaTOBA BridgeAI

Ba vấn đề gặp khi họp thật, ba tầng khác nhau. Ghi lại nguyên nhân và cách
chỉnh, vì phần lớn đều tinh chỉnh được bằng biến môi trường, không cần build lại.

---

## 1. Tên người bị dịch thành số

### Vì sao

M2M-100 không có khái niệm "danh từ riêng". Nó dịch **nghĩa** của kanji:

| Người nói | Model hiểu | Ra phụ đề |
|---|---|---|
| 一さん (Ichi-san) | 一 = số 1 | "13" |
| 千葉さん (Chiba-san) | 千 = 1000, 葉 = lá | "1.000 lá" |
| 本田さん (Honda-san) | 本 = sách, 田 = ruộng | "ruộng sách" |

Thêm một tầng nữa làm nặng thêm: bộ chuẩn hoá số (`normalize_source`) trước
đây đổi mọi cụm kanji số ≥ 100 thành chữ số, nên 千葉さん thành "1,000葉さん"
**trước cả khi** vào bộ dịch. Đã sửa: cụm số đứng ngay trước kính ngữ, hoặc
dính liền một kanji không phải đơn vị đếm, thì không còn bị coi là số.

### Cách sửa: khai người dự vào `people.json`

Đây là cách chắc chắn nhất, vì có sẵn dạng Latin để thay vào — mà chữ Latin
thì M2M-100 chép nguyên xi.

```json
{
  "people": [
    {
      "name": "Ichi",
      "ja": ["一", "イチ", "市"],
      "vi": ["ích", "ít chi"],
      "bad": ["13", "Mười ba"],
      "guard": ["一緒", "一番", "一致"]
    }
  ]
}
```

| Trường | Ý nghĩa |
|---|---|
| `name` | Dạng Latin hiển thị trên phụ đề. Bắt buộc. |
| `ja` | Các cách ASR tiếng Nhật viết ra tên này. |
| `vi` | Các cách ASR tiếng Việt nghe ra tên này (viết **thường**). |
| `bad` | Bản dịch sai đã từng thấy — lưới an toàn tầng 2 dọn nốt. |
| `guard` | Cụm chứa tên nhưng **không** phải tên, cần chừa ra. |

**`guard` là trường quan trọng nhất với tên một ký tự.** Tiếng Nhật không có
dấu cách nên không có ranh giới từ: đăng ký "一" mà không guard thì 一緒/一番/
一致 đều bị ăn. Vì vậy code **cố tình không** đăng ký dạng trần của tên chỉ có
một kanji — tên đó chỉ được nhận khi đi kèm kính ngữ (一さん).

Đổi file khác cho từng cuộc họp mà không build lại:

```bash
KATOBA_PEOPLE_FILE=/duong/dan/hop-thang-9.json
```

### Cách dựng danh sách nhanh

Chạy thử một buổi rồi đọc log — backend in ra những tên nó tự phát hiện mà
chưa được khai:

```
👤 Tên chưa khai trong people.json (7 tên, hiện 15 tên xuất hiện nhiều nhất):
   • 本田さん  ×12
   • 佐藤部長  ×5
```

Chép thẳng vào `people.json`.

### Tên chưa khai thì sao

Có lớp đỡ thứ hai: cụm `<tên>さん` được đóng băng bằng placeholder trước khi
dịch rồi bung lại nguyên văn sau khi dịch. Tên giữ được dạng tiếng Nhật gốc
thay vì biến thành con số.

Lớp này **chỉ chạy cho tiếng Nhật**. ASR tiếng Việt đã bị hạ hết về chữ
thường nên không còn tín hiệu viết hoa để nhận ra danh từ riêng, mà khớp
theo "anh/chị/em + <từ>" thì sai tràn lan ("anh xem giúp em"). Tên tiếng Việt
bắt buộc phải khai trong `people.json`.

Placeholder không đảm bảo 100% — M2M-100 đôi khi nuốt mất. Khi đó log cảnh báo:

```
⚠️  M2M-100 nuốt mất 1 tên người trong: ... Khai những tên này trong people.json
```

Thấy dòng này thì khai tên vào file, đừng bỏ qua.

Những cụm sau được nhận là **không phải tên**, không bị đụng: 皆さん, お客さん,
お母さん, パン屋さん, 店員さん…

---

## 2. Ngắt câu quá nhiều

### Vì sao

Hai nguyên nhân cộng lại:

1. **`min_silence` quá ngắn.** Bản cũ để 0,60s (audio hệ thống) và 0,70s
   (micro). Khoảng dừng để nghĩ giữa câu của người nói tiếng Nhật thường
   0,8–1,2 giây — tức là VAD cắt ngay giữa câu mỗi lần người ta ngập ngừng.

2. **Bộ đệm câu không biết "câu chưa xong".** Danh sách đuôi-còn-tiếp cũ chỉ
   có liên từ (ので, けど, たら…), thiếu hẳn **hạt cách**. Tiếng Nhật không bao
   giờ kết thúc câu bằng hạt cách trần, nên "明日の会議は" + ngừng 1 giây là
   câu **chưa xong** — nhưng bản cũ chốt luôn.

### Đã sửa

- `min_silence` nâng lên 0,90s / 1,00s.
- Bổ sung vào danh sách đuôi-còn-tiếp:
  - hạt cách: を に で と へ が も や の は
  - thể nối: て / し / ば (gom cả して, くて, ていて)
  - tiếng đệm lúc nghĩ: えーと, あのー, なんか…
  - phía tiếng Việt: là, các, những, cần, phải, sẽ, đang, trong, trên…
- **Không** đưa vào: か (dấu hỏi), ね / よ / な (tiểu từ cuối câu), và
  こんにちは / こんばんは được chặn riêng — nếu không thì mọi lời chào đều bị
  dính vào câu kế tiếp.

Kết quả:

```
Người nói:  "明日の会議は" … (nghĩ) … "えーと" … "十時から" … "始めます"
Trước  →  4 câu rời, mỗi câu được dịch thành một câu hoàn chỉnh bịa ra
Sau    →  1 câu: "明日の会議はえーと十時から始めます"
```

### Đánh đổi

Mỗi câu chậm thêm khoảng 0,3 giây. Câu **hoàn chỉnh** thì chốt ngay như cũ,
không chậm thêm — chỉ câu bị ngắt quãng mới phải chờ gộp.

Chuỗi gộp bị chặn ở `MAX_PAUSE_MERGES` (ban đầu 3; nay 6 vì VAD cắt đoạn ngắn
hơn — xem mục 4). Không có trần này thì người cứ kết thúc từng đoạn bằng hạt
cách sẽ làm câu bị giữ lại mãi, độ trễ dồn thành hàng chục giây.

### Chỉnh

| Biến môi trường | Mặc định | Tác dụng |
|---|---|---|
| `KATOBA_VAD_SILENCE_SYSTEM` | 0.90 | Im lặng bao lâu thì chốt một câu **lửng** (audio hệ thống) |
| `KATOBA_VAD_SILENCE_MIC` | 1.00 | Như trên, cho micro |
| `KATOBA_VAD_CUT_SYSTEM` | 0.30 | Im lặng bao lâu thì VAD cắt đoạn đưa đi ASR — xem mục 4 |
| `KATOBA_VAD_CUT_MIC` | 0.40 | Như trên, cho micro |
| `KATOBA_VAD_HARD_SILENCE` | 3.0 | Im lặng lâu tới mức này thì chốt cả câu đang lửng ở trợ từ |
| `KATOBA_VAD_THRESHOLD_SYSTEM` | 0.45 | Ngưỡng coi là có tiếng nói |
| `KATOBA_VAD_THRESHOLD_MIC` | 0.65 | Như trên, cho micro (cao hơn vì micro thu cả tiếng gõ phím) |
| `KATOBA_VAD_MAX_SPEECH` | 6.0 | Trần thời lượng một đoạn (giây) |
| `KATOBA_MAX_PAUSE_MERGES` | 6 | Số đoạn được nối vào một câu còn dở trước khi buộc chốt |

Vẫn thấy ngắt quá nhiều → nâng `KATOBA_VAD_SILENCE_*` lên 1.2.
Thấy chậm quá → hạ về 0.7, chấp nhận vụn hơn.

---

## 3. Bản dịch lan man

Phần lớn là **hệ quả** của hai vấn đề trên: mảnh câu vụn và tiếng đệm ép
M2M-100 phải bịa nội dung cho đủ một câu. Sửa xong hai phần trên là đỡ hẳn.
Thêm hai thay đổi trực tiếp:

### Cắt tiếng đệm trước khi dịch

`えーと` / `あのー` / `ừ` / `ờ` bị bỏ khỏi bản đưa vào bộ dịch. Vài token vô
nghĩa ở đầu câu đủ để beam search lái cả câu sang hướng khác.

**Bản hiển thị phía nguồn vẫn giữ nguyên tiếng đệm** — biên bản họp phải đúng
lời người nói. Chỉ bản đưa cho model là bản sạch.

Cố tình **không** cắt, vì mang nghĩa thật:

| Giữ lại | Lý do |
|---|---|
| あの / その (không kéo dài) | từ chỉ định — "cái đó", "người kia" |
| なんか | danh từ/phó từ thật |
| まあ | mang sắc thái nhượng bộ |
| ạ | tiểu từ **kính ngữ** — cắt đi thì vi→ja mất tín hiệu lịch sự |
| hả / hử | dấu hỏi |

Đoạn nào chỉ toàn tiếng đệm thì bỏ hẳn, không dịch.

### Không dịch nháp quá ngắn

Bản nháp dưới `KATOBA_MIN_PARTIAL_CHARS` (mặc định 8) ký tự không được dịch,
chỉ hiện "đang nghe…". Gặp mẩu 2–3 token thì M2M-100 bịa ra cả câu để lấp chỗ
trống — người dùng thấy một câu hoàn chỉnh **sai** nhấp nháy rồi bị thay bằng
câu khác. Đó chính là cảm giác "lan man".

Bản **chốt** vẫn luôn được dịch dù ngắn đến đâu: "はい" hay "vâng" là câu trả
lời thật và phải hiện ra.

---

## 4. Phụ đề ra chậm, nhiều câu dính thành một khối

### Vì sao

Người nói liền mạch (thuyết trình, báo cáo tiến độ) không nghỉ đủ `min_silence`
giữa các câu, nên VAD chỉ cắt khi chạm trần `max_speech` = 12 giây. Bộ đệm câu
lại gộp tiếp hai đoạn như vậy mới chốt. Hệ quả, đo trên biên bản ngày 12/10:

- khoảng **24 giây** mới có một dòng phụ đề, trong lúc đó màn hình trống;
- mỗi dòng là 3–4 câu dính liền không dấu chấm, đưa vào M2M-100 như **một**
  câu — model chỉ được train trên câu đơn nên dịch lan man và bịa nội dung;
- riêng khâu dịch một khối như thế mất 1,5–2,5 giây.

### Đã sửa

1. **Tách câu trước khi dịch** (`segmenter.py`). Tiếng Nhật công sở kết câu
   bằng thể lịch sự (です / ます / ました / ください / でしょう…), và thể lịch sự
   không đứng trước danh từ, nên "ます + chữ khác" là hết câu. Vẫn giữ nguyên
   câu khi theo sau là liên từ: ですが, ますので, ですから, ましたら…
   Tiếng Anh tách theo dấu câu mà Parakeet-EN tự sinh. Tiếng Việt không có dấu
   hiệu nào đáng tin nên **không** tách — vẫn chờ im lặng như cũ.

2. **Mỗi câu là một dòng, chốt ngay khi trọn câu.** Chỉ phần câu còn dở ở cuối
   đoạn mới nằm chờ đoạn sau.

3. **Hai mốc im lặng thay vì một.** `KATOBA_VAD_CUT_*` (0,3s) là lúc VAD cắt
   đoạn đưa đi ASR; `KATOBA_VAD_SILENCE_*` (0,9s) giữ nguyên nghĩa cũ nhưng chỉ
   còn áp cho câu **không** có dấu hiệu hết câu. Mẩu câu cắt ra ở chỗ ngừng
   không bị dịch riêng: chúng được nối lại ở mức chữ cho tới khi trọn câu.

4. **`max_speech` 12s → 6s**, để người nói liền mạch không phải chờ đủ 12 giây.

5. **Dấu `。` ở cuối đoạn không còn được tin mặc nhiên.** Parakeet-JA chấm câu
   theo khoảng lặng, nên nó chấm cả sau `問題がなければ。` khi người nói mới
   ngừng lấy hơi. Chỉ giữ dấu chấm đó khi chữ đứng trước đã là dạng kết câu.

### Đo được

Đoạn họp IT 18 câu, giọng tổng hợp, phát đúng thời gian thực. Độ trễ = từ lúc
nói xong câu tới lúc bản dịch **chốt** của câu đó hiện ra:

| Cách nói | Trước | Sau |
|---|---|---|
| Nghỉ 0,7s giữa câu | trung bình 15,2s, tệ nhất 30s | trung vị 1,1s, tệ nhất 2,0s |
| Có ngắt giữa câu, nghỉ 0,5s giữa câu | chưa đo | trung vị 0,5s, tệ nhất 1,2s |
| Nói liền (nghỉ 0,25s) | trung bình 13,0s, tệ nhất 34s | trung vị 3,7s, tệ nhất 11,3s |

18 câu trước đây ra 2–3 khối, giờ ra 21–22 dòng. Bộ test chuẩn `eval_mt.py`
không đổi (ja→vi 57,7 so với 57,9; ba chiều còn lại giữ nguyên) vì các câu
trong đó vốn là câu đơn.

### Giới hạn còn lại

- **Văn nói thân mật** (thể thường, không です/ます) không có đuôi để bám, nên
  vẫn phải chờ im lặng hoặc chạm trần. Họp công việc thì ít gặp.
- **Nói liền hoàn toàn** (không chỗ nào ngừng tới 0,3s) vẫn phải chờ chạm trần
  ~6s mới có câu chốt; trong lúc đó chỉ có bản nháp (mục 5).
- Mọi số đo ở đây dùng **giọng tổng hợp**. Mốc cắt 0,3s chưa được kiểm chứng
  với giọng người thật; nếu thấy nhận dạng kém đi thì thử 0,5.
- Tách câu chỉ sửa **ngắt nghỉ và tốc độ**. Từ model không biết thì vẫn dịch
  sai; đó là giới hạn của M2M-100 418M, phải xử lý bằng dữ liệu train hoặc đổi
  model.

Quay về gần hành vi cũ để so sánh:

```bash
KATOBA_VAD_CUT_SYSTEM=0.9 KATOBA_VAD_CUT_MIC=1.0 KATOBA_VAD_MAX_SPEECH=12 KATOBA_LIVE=0
```

---

## 5. Chữ chạy theo lời nói (bản nháp) và dịch lại cả câu

### Cách hoạt động

1. **Bản nháp.** Trong lúc người ta còn đang nói, cứ khoảng 0,4 giây âm thanh
   mới thì backend nhận dạng lại phần đang nói dở và dịch nhanh (beam 1).
   Giao diện vẽ bản nháp **mờ và nghiêng**. Bản nháp không vào biên bản.

2. **Bản chốt.** Khi câu trọn, backend dịch lại **cả câu từ nguyên văn** (beam
   4) rồi thay bản nháp. Bản chốt không ghép từ các mẩu nháp. Dòng đã chốt thì
   cố định, bản nháp tới muộn không ghi đè được.

3. **Khi dịch câu chốt hỏng hoặc chậm.** Bản dịch hỏng (rỗng, điểm thấp, dài
   bất thường) thì giữ bản nháp đang hiện làm bản chốt, không để trống. Trong
   lúc chờ, bản nháp vẫn nằm nguyên trên màn hình.

Bản xem trước luôn nhường việc chốt câu và chỉ giữ ảnh chụp mới nhất của đoạn
đang nói, nên máy chậm thì bản nháp thưa đi chứ không dồn việc.

### Ba điều đã đo và quyết định theo số liệu

**Câu chốt không lấy từ nhận dạng dở.** Đã thử chốt sớm câu trọn vẹn ngay khi
người ta đang nói câu sau, và bỏ: âm thanh bị cắt giữa chừng làm Parakeet-JA
nuốt cả cụm (`始めます` → `をます`), có khi lặp ở hai lần liên tiếp. Chữ sai mà
đã chốt thì nằm luôn trong biên bản. Câu chốt chỉ lấy từ đoạn đã kết thúc ở
chỗ ngừng.

**Dịch kèm câu trước làm ngữ cảnh: có sẵn nhưng mặc định tắt.** Trên đoạn họp
IT 18 câu (giọng tổng hợp, câu sạch) nó có lợi: chrF cả đoạn 55,5 → 57,3. Trên
73 câu nói thật của biên bản 13/10 thì không: so từng câu thì chất lượng ngang
nhau, còn lỗi nhìn thấy được chỉ bên có ngữ cảnh mới có —

| Trên 73 câu thật | Dịch riêng lẻ | Kèm ngữ cảnh |
|---|---|---|
| Bản dịch mở đầu bằng dấu chấm | 0 | 3 |
| Lặp vòng ("15 phút, 15 phút, …") | 0 | 1 |
| Nhại câu trước thay vì dịch câu này | 0 | 2 |
| Thời gian dịch (trung vị) | 492 ms | 872 ms |

M2M-100 418M được train từng câu đơn; ép nó nối tiếp một câu khác chỉ ổn khi
cả hai câu đều gọn. Ba loại lỗi trên đã được vá (phát hiện rồi dịch lại không
ngữ cảnh), nhưng chưa có số liệu nào trên lời nói thật cho thấy nó hơn dịch
riêng lẻ. Bật thử: `KATOBA_MT_CONTEXT=1`.

**Nền nhiễu cho ASR tiếng Nhật.** Gặp khoảng lặng tuyệt đối (mẫu bằng 0, do
noise gate của micro hoặc Zoom tạo ra) nằm giữa đoạn, Parakeet-JA nuốt mất cả
câu. Cộng nhiễu trắng −70 dBFS chỉ cho ASR: CER 4,2% → 2,4% trên bản ghi nói
liền, không đổi (3,5%) trên bản ghi có nghỉ.

### Chỉnh

| Biến môi trường | Mặc định | Tác dụng |
|---|---|---|
| `KATOBA_LIVE` | 1 | 0 = tắt bản nháp, chỉ hiện câu đã chốt (máy yếu) |
| `KATOBA_LIVE_STEP` | 0.4 | Số giây âm thanh mới giữa hai bản nháp |
| `KATOBA_MT_CONTEXT` | 0 | 1 = dịch câu chốt kèm câu liền trước (chậm hơn ~0,4s/câu) |
| `KATOBA_ASR_DITHER` | 3e-4 | Biên độ nền nhiễu cho ASR tiếng Nhật; 0 = tắt |
| `KATOBA_MT_THREADS` | 2 | Số luồng của bộ dịch; 4 nhanh hơn ~15% trên máy nhiều nhân |

### Giới hạn

- **Bản nháp tiếng Nhật hay sai.** Tiếng Nhật đặt động từ và phủ định ở cuối
  câu, nên dịch nửa câu thường ra một câu khác hẳn. Vì vậy bản nháp chỉ để
  biết app đang chạy; nội dung phải đọc ở bản chốt.
- **Tốn CPU hơn.** Mỗi bản nháp là một lượt nhận dạng + một lượt dịch.
- Chất lượng bản chốt vẫn bị chặn bởi M2M-100 418M và bởi lỗi nhận dạng
  (`話す` nghe thành `離す` thì bản dịch ra "tách ra").

---

## 6. Bộ nhớ

RAM của backend gần như toàn bộ là model nạp sẵn. Đo trên Windows:

| Thành phần | RAM |
|---|---|
| ASR tiếng Nhật (Parakeet-JA) | 710 MB |
| ASR tiếng Anh (Parakeet-EN) | 689 MB |
| Bộ dịch M2M-100 | 516 MB |
| 3 tokenizer | 142 MB |
| ASR tiếng Việt (Zipformer-VI) | 73 MB |
| Python, thư viện, bộ nhớ làm việc | ~170 MB |

Nạp hết lúc khởi động là 2,3 GB. Giờ chỉ nạp sẵn ASR của các ngôn ngữ trong
`KATOBA_PRELOAD` (mặc định `ja,vi`) → **1,5 GB**; ngôn ngữ còn lại nạp ở phiên
đầu tiên dùng tới (Parakeet-EN: ~2 giây) và ở lại từ đó.

| Biến môi trường | Mặc định | Tác dụng |
|---|---|---|
| `KATOBA_PRELOAD` | ja,vi | Ngôn ngữ ASR nạp sẵn lúc khởi động. `en,vi` cho máy chủ yếu dịch Anh→Việt; `ja,vi,en` = hành vi cũ |

`/v1/health` báo `rss_gb` và `asr_loaded` để xem đang nạp những gì.

---

## 7. Từ đời thường và câu cửa miệng (`everyday.json`)

Model dịch được huấn luyện trên câu họp IT nên thiếu hẳn vốn từ sinh hoạt.
Cho nó dịch thử 287 danh từ thường ngày trong câu mẫu thì **117 từ sai ở mọi
câu thử** (`玄米` → "cá mập", `鮭` → "cây búa", `残業` → "nghỉ việc",
`出張` → "du lịch"), và **28/55 câu cửa miệng** sai (`お世話になっております`
→ "Em đang chăm sóc anh", `お大事に` → "Anh quan trọng em").

`everyday.json` chữa hai loại đó, chỉ cho chiều Nhật → Việt:

- **`entries` — danh từ (145 mục).** Từ được thay bằng ký hiệu `W1`, `W2`…
  trước khi dịch, dịch xong mới điền nghĩa tiếng Việt vào. Model chỉ lo cấu
  trúc câu, không phải đoán nghĩa của từ nó không biết.
- **`phrases` — câu cửa miệng (38 mục).** Khớp nguyên một câu (kể cả khi nó
  đứng đầu hoặc cuối một lượt nói, hoặc sau tiếng thốt `あっ` / `へえ`) thì
  hiện thẳng bản dịch có sẵn.

```json
{"vi": "chuyến công tác", "verb": "đi công tác", "ja": ["出張"]}
{"verb": "háo hức", "ja": ["ワクワク", "わくわく"]}
```

`ja` là các cách ASR có thể viết ra; `verb` (tuỳ chọn) là nghĩa khi từ được
dùng làm động từ (`出張します`). Mục chỉ có `verb` thì chỉ thay dạng động từ.
Thêm, sửa tuỳ ý rồi khởi động lại backend.

Đợt hai (sau biên bản 13/10 10:26) thêm 36 mục, lại chỉ lấy từ model sai ở
mọi câu thử: `日曜日` → "thứ Hai" và `土曜日` → "thứ Sáu" (thứ Hai–thứ Sáu thì
nó dịch đúng), `七夕` → "7 giờ", `飲み会` → "buổi họp uống", `後悔` → "xin lỗi".

### Chỉ đưa vào từ model thật sự không biết

Ký hiệu giữ chỗ có giá: model không còn biết từ đó là người, chỗ hay đồ vật,
nên dễ xếp sai câu. Với từ model vốn dịch được, thay vào chỉ làm hỏng:

| Câu | Không thay `風邪`, `居酒屋` | Có thay |
|---|---|---|
| 風邪をひいたので… | Tôi bị cảm lạnh nên… | Em đã tắt cảm cúm… |
| 居酒屋で先輩と飲みました | uống rượu với tiền bối ở một quán rượu | uống quán nhậu với tiền bối |

Vì vậy 58 từ model chỉ sai ở vài câu, và những từ nó dịch chưa đúng chữ
nhưng đọc vẫn hiểu (`居酒屋` → "quán rượu"), đều **không** có trong file.
Trước khi thêm một từ, hãy xem model có thật sự dịch sai nó không.

### Giới hạn

- Chỉ chữa được **danh từ**. Động từ, tính từ dịch sai (`沸かす` → "nén")
  là giới hạn của model, phải huấn luyện thêm mới hết.
- Mỗi câu thay tối đa 6 từ; model làm mất ký hiệu thì câu đó được dịch lại
  theo cách cũ.
- Bộ đo `eval_mt.py` không đổi (ja→vi 57,7) vì các câu trong đó không chứa
  những từ này — tác dụng chỉ thấy trên hội thoại đời thường.
- Hai ký hiệu nối nhau bằng `という` / `の` thì model hay xếp ngược quan hệ
  (`ひな祭りという行事` → "lễ hội Hinamatsuri tên là sự kiện").

### Mấy lỗi lặt vặt của hội thoại đời thường

Đối chiếu biên bản 13/10 10:26 với lời gốc, sửa thêm (chỉ Nhật → Việt):

| Lỗi | Trước | Sau |
|---|---|---|
| `〜ですね` / `〜ますね` bị dịch thành câu hỏi | 寝ますね → "Anh ngủ được không?" | bỏ `ね`, dịch lại → "Em sẽ ngủ." |
| `何か` / `なんか` đệm đầu câu | そうそう何か毎朝7時… → "có gì đó xảy ra khoảng 7 giờ sáng" | cắt trước khi dịch → "mọi sáng em thức dậy khoảng 7 giờ" |
| Thời lượng `N時間` | "ngủ khoảng 6 giờ" | "ngủ khoảng 6 tiếng" |
| Mẩu rơi ra sau câu đã chốt (`なんですよ`, một chữ kana) | "Thế nào vậy anh?" | không hiện |
| Câu cắt ở `でする`, `ですかって` | スペインです ‖ るその日本の… | một câu |
| Động từ + `んだ` bị coi là tên + `くん` | "聴くん cũng rất phổ biến…" | "em nghe rất nhiều" |

`何か` chỉ bị cắt khi đứng đầu câu hoặc sau tiếng thốt, và không cắt khi theo
sau là `質問` / `問題` / `あれば`… (nghĩa "cái gì đó" thật).

---

## Kiểm thử

```bash
cd backend
python test_postprocess.py      # tên người, tiếng đệm, số, từ điển
python test_segmenter.py        # tách câu và chốt câu — không cần model
```
