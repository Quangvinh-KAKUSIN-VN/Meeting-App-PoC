# Báo cáo MT v9 — review, sửa, train và thay model

**Ngày:** 30/09/2026 · **Phạm vi:** model dịch M2M-100 418M + LoRA v9, notebook train, hậu xử lý backend

## Tóm tắt

- Có review notebook `Lora_m2m418_v9.ipynb` trước khi train và sửa 1 bug nghiêm trọng: phần dạy model chép placeholder tên `PnA` không chạy (0/30 câu). Ngoài ra đã sửa thêm 6 điểm khác.
- Sửa 2 bug đổi số tiếng Việt trong `backend/postprocess.py`:
  - "một phẩy năm triệu" bị đổi thành `một phẩy 5.000.000`.
  - "tỷ lệ lỗi" bị đổi thành `1.000.000.000 lệ lỗi`.
- Đã train v9 trên Colab. So với v6 (bản đang chạy trước đó), **chrF tăng ở cả 4 chiều**, xem bảng bên dưới.
- **v9 đã thay v6 làm model chính của app.** Bản v6 cất ở `old_models/m2m100_418M_int8_v6/`.
- Còn 4 lỗi (v6 cũng mắc cả 4), xem mục "Lỗi còn lại".

## 1. Model có phù hợp với dự án không

Dự án cần dịch 4 chiều: ja↔vi và en↔vi, không có en↔ja. Notebook train đúng 4 chiều này, khớp với `ALLOWED_DIRECTIONS` trong `main.py`.

- **M2M-100 418M + LoRA hợp với PoC:** một model phục vụ cả 4 chiều, license MIT dùng thương mại được, chạy CTranslate2 int8 trên CPU đủ nhanh cho dịch realtime.
- **Hạn chế:** chất lượng có trần thấp, rõ nhất ở vi→ja.
- **Nếu cần nâng chất lượng:** bước rẻ nhất là lên M2M-100 1.2B. Model này dùng cùng tokenizer, vocab và token ngôn ngữ, nên notebook và backend gần như giữ nguyên. Đổi lại độ trễ trên CPU tăng đáng kể, cần đo trước khi quyết.
- **Không dùng NLLB-200:** license CC-BY-NC không cho dùng thương mại.

## 2. Data train

Notebook chỉ đọc **`data_v9.jsonl`**. File có 1.291 câu, mỗi câu gồm đủ vi, ja, en: 1.188 câu train và 103 câu eval (bộ eval này giữ cố định từ v6 để các bản so được với nhau).

| Nguồn | Origin | Số câu |
|---|---|---|
| `it_dataset_clean.jsonl` | `it` + 103 câu eval | 693 |
| `general_clean.jsonl` | `general` | 162/516 (chỉ lấy một phần) |
| `new_it_pairs_v6.jsonl` | `new_v6` | 67 |
| Thêm ở v7/v8 | `target_time`, `target_num`, `target_polarity`, `target_terms`, `target_it`, `target_meeting`, `target_causal` | 261 |
| Mới ở v9 (`new_pairs_v9.py`) | `target_jargon` 42, `target_short` 36, `target_names` 30 | 108 |

Ba file nguồn chỉ có cặp vi-ja; phần tiếng Anh được thêm lúc gộp thành `data_v7/v8/v9.jsonl`. Hai file `data_v7.jsonl` và `data_v8.jsonl` là bản cũ, notebook v9 không dùng.

## 3. Sửa notebook `Lora_m2m418_v9.ipynb` (trước khi train)

| # | Vấn đề | Sửa |
|---|---|---|
| 1 | **Regex tên hỏng.** `\b[A-Z][a-z]+-san\b`: Python coi kana/kanji cũng là ký tự chữ (`\w`), nên `Ota-sanは` không có ranh giới từ sau `san`. Sau bước làm nhiễu, regex khớp **0/30** câu, tức model không được dạy chép `PnA`. | Dùng lookaround chỉ xét chữ Latin: 58 dòng train có `PnA`. Thêm assert để lần sau hỏng thì notebook dừng ngay. |
| 2 | Mỗi câu chỉ có một bản nhiễu, cả 7 epoch đều thấy đúng bản đó. | `NOISE_COPIES = 3` (3 seed khác nhau), `EPOCHS = 2`, eval và lưu checkpoint sau mỗi 1/3 epoch. |
| 3 | Làm nhiễu biến `5 triệu` thành `năm triệu`, trong khi app (`normalize_source`) luôn đưa vào model dạng `5.000.000`. | Làm nhiễu theo đúng cách app xử lý: `5 triệu` → `5.000.000`, `1,5 triệu` → `1.500.000`, `2,5%` → `2,5 phần trăm`. |
| 4 | Data gọi người nghe gần như toàn "anh". | 30% câu nguồn tiếng Việt đổi `anh` → `chị`, chỉ ở phía nguồn. Bỏ qua "anh ấy", "anh ta", "anh chị", "anh em", "tiếng Anh" và tên riêng. |
| 5 | Cách decode lúc eval khác backend. | Cột APP decode giống hệt backend (`repetition_penalty` 1.1, trần độ dài theo `LEN_MULT`). Cột SẠCH/NHIỄU giữ cách cũ để còn so với v6–v8. |
| 6 | Không có bộ eval nào kiểm tra model có quên cách dịch câu đời thường không. | Thêm CELL 9b: 40 câu đời thường ngoài domain IT, so v9 với M2M-100 gốc. |
| 7 | Contrast set chưa có case "chị". | Thêm 1 case: "chị" phải dịch thành "you". |

**Sự cố khi chạy trên Colab:** ở CELL 9b, biến `gen_app` trùng tên với hàm `gen_app()` của CELL 9 nên ghi đè lên hàm, gây `TypeError: 'list' object is not callable`. Đã đổi tên biến thành `ood_*`. Trên Colab chỉ cần chạy lại CELL 9 rồi CELL 9b, không phải train lại.

## 4. Sửa backend

**`backend/postprocess.py` — `normalize_source`, phần đổi số tiếng Việt**

| Nguồn từ ASR | Trước | Sau |
|---|---|---|
| một phẩy năm triệu yên | `một phẩy 5.000.000 yên` | `1.500.000 yên` |
| hai phẩy năm lần | `hai phẩy 5 lần` | `2,5 lần` |
| tỷ lệ lỗi giảm rồi | `1.000.000.000 lệ lỗi giảm rồi` | `tỷ lệ lỗi giảm rồi` |
| hàng nghìn người dùng | `hàng 1.000 người dùng` | `hàng nghìn người dùng` |

Có thêm hàm `_vi_decimal()`. Cụm số chỉ được đổi khi có ít nhất một chữ số. `test_postprocess.py` thêm 8 test, hiện pass **86/86**.

**`backend/main.py`:** `MODEL_VERSION = "v9"`, sửa comment ví dụ của `KATOBA_MT_DIR`.

**`.gitignore`:** thêm `old_models/`.

## 5. Kết quả test v9 so với v6

Dùng `eval_mt.py` trên bộ `testdata/cau_test_mt.tsv` (30 câu mỗi chiều). Mỗi câu chạy đúng pipeline của app: `prepare_source`, bọc tên, M2M-100, rồi `finish`/glossary.

| Chiều | v6 | v9 | Chênh |
|---|---|---|---|
| ja → vi | 51.3 | **57.9** | +6.6 |
| vi → ja | 39.7 | **43.6** | +3.9 |
| en → vi | 49.9 | **57.0** | +7.1 |
| vi → en | 59.8 | **71.7** | +11.9 |

- Có 60/120 câu tốt hơn trên 2 điểm và 29/120 câu kém hơn trên 2 điểm. Phần lớn câu "kém hơn" chỉ do v9 xưng "anh/em" còn câu tham chiếu dùng "tôi/bạn"; nghĩa vẫn đúng.
- Bộ test có vài câu cùng chủ đề với data targeted, nên điểm hơi lạc quan. Cần thêm kiểm chứng bằng cuộc họp thật.

**Một số câu thử cụ thể (qua pipeline app):**

| Nguồn | v6 | v9 |
|---|---|---|
| dạ vâng (vi→ja) | マッサージはい | はい。 |
| chị xem giúp em cái lỗi này với (vi→en) | I'm going to see how this mistake can help me. | Could you check this bug for me? |
| chị review giúp em pull request này nhé (vi→ja) | このリクエストをpullして下さい。… | このpull requestのレビューをお願いします。 |
| Please disable the old API key… (en→vi) | Vui lòng disable key API cũ… | Tắt key API cũ sau khi migrate. |
| chi phí tăng mười lăm phần trăm… (vi→ja) | コストは前四半期と15%増加しました | 費用は前四半期と比べて15%増えました。 |

## 6. Triển khai

| Thư mục | Nội dung |
|---|---|
| `backend/models/m2m100_418M_int8/` | **v9**, model chính (đã bỏ đuôi `_v9` và lớp thư mục lồng thừa khi giải nén) |
| `old_models/m2m100_418M_int8_v6/` | v6, bản cũ; nằm ngoài `backend/models/` nên không bị đóng gói khi build |

Đã kiểm tra: chạy với cấu hình mặc định (không đặt `KATOBA_MT_DIR`), backend nạp đúng v9 và cho điểm khớp với bảng trên.

**So lại với v6** (PowerShell, trong `backend/`):
```powershell
$env:KATOBA_MT_DIR = "..\old_models\m2m100_418M_int8_v6"; python eval_mt.py --out eval_v6.csv; Remove-Item Env:KATOBA_MT_DIR
```

**Quay về v6 hoàn toàn:** đổi tên `backend/models/m2m100_418M_int8` sang tên khác, chép `old_models/m2m100_418M_int8_v6` vào `backend/models/m2m100_418M_int8`, rồi đặt lại `MODEL_VERSION = "v6"`.

## 7. Lỗi còn lại

v6 cũng mắc cả 4 lỗi dưới đây.

1. **Giờ "rưỡi chiều" bị đảo sang buổi sáng.** "dời buổi review sang 4 giờ rưỡi chiều" ra `4:30 a.m.` / `午前4時半`. Đây là lỗi nghiêm trọng trong biên bản họp. Lần train sau nên thêm data dạng "X giờ rưỡi chiều/tối".
2. **Số lớn chiều vi→ja sai:** `1.500.000 yên` ra `1500万円` (đúng: `150万円`). Hướng xử lý: thêm data số lớn, hoặc hậu xử lý đối chiếu số giữa câu nguồn và câu dịch.
3. **Tên người bị khớp nhầm vào giữa tên dài hơn:** `佐藤さん` ra `S. Fuji-san`. Lỗi nằm ở `people.json`/glossary chứ không phải model: mục khai 藤 khớp vào giữa 佐藤. Có thể sửa trong code mà không cần train lại.
4. `横展開` vẫn dịch sai nghĩa, và câu đời thường chiều vi→ja vẫn yếu.

## 8. File đã thay đổi (chưa commit)

- `Lora_m2m418_v9.ipynb`: các sửa ở mục 3
- `backend/postprocess.py`, `backend/test_postprocess.py`: các sửa ở mục 4
- `backend/main.py`: `MODEL_VERSION`, comment
- `.gitignore`: `old_models/`
- `BAO_CAO_MT_v9.md`: báo cáo này

Ghi chú: trước phiên này đã có sẵn một số thay đổi chưa commit trong `postprocess.py`, `main.py` và frontend; báo cáo này chỉ mô tả phần sửa trong phiên. Thư mục model nằm trong `.gitignore`, không đi theo Git.
