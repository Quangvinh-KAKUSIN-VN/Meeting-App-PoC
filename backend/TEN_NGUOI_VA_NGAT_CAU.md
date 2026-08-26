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

Chuỗi gộp bị chặn ở `MAX_PAUSE_MERGES` = 3 (khoảng 4 đoạn VAD). Không có trần
này thì người cứ kết thúc từng đoạn bằng hạt cách sẽ làm câu bị giữ lại tới
150 ký tự, độ trễ dồn thành hàng chục giây mà màn hình không hiện gì.

### Chỉnh

| Biến môi trường | Mặc định | Tác dụng |
|---|---|---|
| `KATOBA_VAD_SILENCE_SYSTEM` | 0.90 | Im lặng bao lâu thì chốt đoạn (audio hệ thống) |
| `KATOBA_VAD_SILENCE_MIC` | 1.00 | Như trên, cho micro |
| `KATOBA_VAD_THRESHOLD_SYSTEM` | 0.45 | Ngưỡng coi là có tiếng nói |
| `KATOBA_VAD_THRESHOLD_MIC` | 0.65 | Như trên, cho micro (cao hơn vì micro thu cả tiếng gõ phím) |
| `KATOBA_VAD_MAX_SPEECH` | 12.0 | Trần thời lượng một đoạn (giây) |
| `KATOBA_MAX_PAUSE_MERGES` | 3 | Số lần được gộp vì ngắt hơi |

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

## Kiểm thử

```bash
cd backend
python test_postprocess.py      # 63 ca, gồm cả tên người và tiếng đệm
```
