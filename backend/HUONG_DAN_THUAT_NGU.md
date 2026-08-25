# Hướng dẫn hệ thống thuật ngữ chuyên ngành — KaTOBA BridgeAI

Bản nâng cấp này giải quyết đúng một việc: **thuật ngữ IT được nhận ra và
giữ nguyên chữ tiếng Anh trên phụ đề ở CẢ HAI CHIỀU**, dù người Nhật đọc
kiểu katakana (デプロイ) hay người Việt đọc kiểu Việt ("đíp lôi").

File thay đổi: `postprocess.py` (viết lại) + `glossary.json` (từ điển mới
141 mục). File thêm: `eval_terms.py`, `learn_terms.py`, `build_glossary.py`,
`test_postprocess.py`, `testdata/`, file này. `requirements.txt` sửa lại
cho đúng. **`main.py` và toàn bộ frontend KHÔNG đổi một dòng nào.**

---

## 1. Nó hoạt động thế nào (30 giây)

```
Giọng nói ──► ASR ──► [TẦNG 1: sửa ngay trên text nguồn] ──► Dịch M2M-100
                       "đíp lôi"      → "deploy"
                       "デプロー"      → "deploy"                    │
                                                                    ▼
Phụ đề  ◄── [TẦNG 2: lưới an toàn trên bản dịch] ◄──────────────────┘
             nguồn có "deploy" mà bản dịch ra 展開/"triển khai"
             → ép về "deploy"
```

- **Tầng 1** là tầng quyết định: chữ Latin đi qua bộ dịch thường được giữ
  nguyên, nên sửa sớm chừng nào tốt chừng đó.
- **Tầng 2** chỉ kích hoạt khi câu NGUỒN thật sự chứa thuật ngữ. Nhờ vậy
  khi ai đó nói "chúng ta cam kết hoàn thành" thì chữ "cam kết" bình thường
  không bao giờ bị đổi thành "commit".

## 2. Cấu trúc một mục trong `glossary.json`

```json
{
  "term": "deploy",
  "ja_hears": ["デプロイ", "デプロー"],
  "vi_hears": ["đíp lôi", "đi lôi", "đép lôi"],
  "ja_bad":   ["展開", "配置"],
  "vi_bad":   ["triển khai"],
  "ja_guard": [],
  "vi_guard": []
}
```

| Trường | Nghĩa | Dùng ở |
|---|---|---|
| `term` | Bản chuẩn hiển thị trên phụ đề (thường là tiếng Anh) | cả hai tầng |
| `ja_hears` / `vi_hears` | Các dạng **ASR nghe ra** khi người nói đọc thuật ngữ | tầng 1 |
| `ja_bad` / `vi_bad` | Các **bản dịch sai** cần ép về `term` | tầng 2 |
| `ja_guard` / `vi_guard` | Cụm chứa chuỗi giống `*_bad` nhưng **cấm đụng vào** | tầng 2 |

Ví dụ guard: mục `bug` có `vi_bad: ["lỗi"]` và `vi_guard: ["xin lỗi"]` —
bản dịch "xin lỗi anh" sẽ không bao giờ thành "xin bug anh".

### Quy tắc vàng khi tự sửa

1. **`vi_hears` chỉ điền chuỗi "phiên âm" gần như không thể là tiếng Việt
   thật** ("sơ vơ", "đíp lôi", "gít háp"). Từ tiếng Việt có nghĩa thật
   ("triển khai", "máy chủ", "cam kết") tuyệt đối không điền vào đây —
   chúng thuộc `vi_bad`, nơi chỉ được thay khi câu nguồn có thuật ngữ.
2. **Không bao giờ thêm `"ai"` vào `vi_hears` của mục `AI`** — sẽ nuốt đại
   từ "ai" của tiếng Việt. Muốn bắt AI hãy dùng "ây ai" (đã có sẵn).
3. `ja_hears` chủ yếu là katakana; được phép chứa cách gọi Nhật **đặc thù
   ngành** (本番環境 → production, 単体テスト → unit test) vì người Nhật thật
   sự gọi vậy trong họp dev — nhưng tránh từ đa nghĩa phổ thông.
4. Sửa `glossary.json` xong phải **khởi động lại backend** mới có hiệu lực.
5. Sửa xong nên chạy `python test_postprocess.py` — 5 giây, 32 bài kiểm tra
   an toàn (nếu lỡ tay thêm từ phá câu thường sẽ lộ ra ngay).

## 3. Đo chất lượng trước/sau (eval_terms.py)

Mỗi lần đổi từ điển, đo lại để có **con số** thay vì cảm giác:

1. Mở `testdata/cau_test_vi.tsv` (32 câu tiếng Việt) — tự đọc từng câu,
   thu mỗi câu một file WAV **16000 Hz, mono, 16-bit**, đặt tên đúng cột 1
   (`vi_01.wav`, `vi_02.wav`...), bỏ chung một thư mục. Bộ tiếng Nhật
   `cau_test_ja.tsv` nhờ đồng nghiệp Nhật đọc (hoặc TTS giọng bản xứ).
   Thu được bao nhiêu đo bấy nhiêu, không cần đủ 32.
2. Chạy:
   ```
   python eval_terms.py --lang vi --wav-dir <thư_mục_wav> --sentences testdata/cau_test_vi.tsv
   ```
3. Đọc tổng kết cuối:
   - **`PHỤ ĐỀ cuối có bản chuẩn`** — con số quan trọng nhất, mục tiêu ≥ 90%.
   - **`ASR nghe ra dạng bất kỳ`** thấp → ASR nghe kiểu khác với những gì
     từ điển biết → sang mục 4 để "dạy".
   - `CER trung bình` ≤ 0.15 là nghe ổn.
   - Hai câu cuối mỗi bộ là **câu đối chứng không có thuật ngữ** — nếu cột
     `dst` của chúng xuất hiện thuật ngữ tức là từ điển đang quá tay, xem
     lại các mục vừa thêm.
4. Báo cáo chi tiết nằm trong file CSV (mở bằng Excel được).

## 4. "Dạy" từ điển giọng của chính bạn (learn_terms.py)

Không cần đoán ASR nghe "deploy" thành gì — để nó tự khai:

1. Thu mỗi thuật ngữ 2–3 file WAV, chỉ nói **một từ đó**, tự nhiên như lúc
   họp. Tên file: `<slug>__<số>.wav`, slug là term viết thường, ký tự đặc
   biệt thay bằng `-`:
   ```
   deploy__1.wav   deploy__2.wav   pull-request__1.wav   ci-cd__1.wav
   ```
2. Chạy thử (chỉ in đề xuất, chưa sửa gì):
   ```
   python learn_terms.py --lang vi --wav-dir <thư_mục>
   ```
   Script tự phân loại: ✅ đề xuất thêm / 👌 đã nhận tốt / ⚠️ cần bạn tự
   cân nhắc / 🚫 loại (trùng từ tiếng Việt phổ thông — thêm vào sẽ phá app).
3. Ưng thì ghi thật (tự backup `glossary.json` trước):
   ```
   python learn_terms.py --lang vi --wav-dir <thư_mục> --apply
   ```
4. Khởi động lại backend. Xong.

## 5. Thêm thuật ngữ hoàn toàn mới (từ riêng của công ty)

1. Mở `glossary.json`, thêm mục mới tối thiểu:
   ```json
   { "term": "KaTOBA", "ja_hears": ["カトバ", "カトーバ"], "vi_hears": [] }
   ```
2. Thu âm `katoba__1.wav`... rồi chạy `learn_terms.py` (mục 4) để nó tự đề
   xuất `vi_hears`/`ja_hears` theo giọng thật.
3. Nếu bộ dịch hay dịch bậy từ đó, bổ sung `vi_bad`/`ja_bad` sau khi thấy
   lỗi thật trên phụ đề (kèm `*_guard` nếu chuỗi đó có thể là mảnh của cụm
   thường gặp).

`build_glossary.py` là script đã sinh ra 141 mục hiện tại — chỉ chạy lại
khi muốn **làm lại từ đầu** (nó ghi đè `glossary.json`, các chỉnh tay và
những gì `learn_terms.py` đã học sẽ mất; file cũ tự lưu thành bản `.bak`).

## 6. Sự cố thường gặp

| Hiện tượng | Nguyên nhân / cách xử |
|---|---|
| Sửa glossary mà phụ đề không đổi | Quên khởi động lại backend |
| Một từ tiếng Việt bình thường bị đổi thành thuật ngữ | Có ai đó điền từ Việt thật vào `vi_hears` — chuyển nó sang `vi_bad`, chạy `test_postprocess.py` kiểm lại |
| Phụ đề ra "xin bug" | Thiếu guard: thêm `"vi_guard": ["xin lỗi"]` vào mục đó |
| `pip install -r requirements.txt` lỗi encoding | Đang dùng file cũ UTF-16 — bản mới trong repo đã là UTF-8 |
| eval báo `Không hỗ trợ WAV xx-bit` | Xuất lại WAV PCM 16-bit (mọi app thu âm đều có tuỳ chọn này) |
