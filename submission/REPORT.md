# Báo cáo Day 09 — Trần Quang Nam, 2A202603118

## 1. Kết luận trước
Pipeline kết luận **Hold** (mã thoát 10): **224** ảnh vào, **202** ảnh qua cửa nhận, xuất **202** nhãn vào `export/clean_v1` (bản nháp, chưa phát hành).
Không còn lỗi bắt buộc nào, nhưng **38/202 ảnh (18,8%)** còn cảnh báo chưa người duyệt, vượt ngưỡng 10%. Nguyên nhân là hàng đợi có 125 ảnh mà ngân sách duyệt chỉ có 80.

## 2. Lỗi và phân việc
Nguồn: `01_intake`, `02_error_list_v1` (mẫu số: 224 ảnh ở cửa nhận, 202 ảnh ở các bước sau).

| Mã lỗi | Số ảnh/dòng | Ai sửa | Vì sao |
|---|---:|---|---|
| DUP_IMAGE_EXACT / DUP_IMAGE_NEAR | 8 / 4 ảnh | máy (loại ở cửa nhận) | trùng md5 / phash ≤ 12: giữ ảnh đầu tiên |
| LEAK_TEST | 5 ảnh | máy (loại) | trùng ảnh tập test/val, giữ lại sẽ làm số đo test bị ảo |
| BAD_SIZE / CORRUPT_IMAGE | 3 / 2 ảnh | máy (loại) | cạnh < 250 px / ảnh không `load()` được |
| BOX_OUT_OF_IMAGE | 8 dòng | máy (`clip_box`) | cắt box về [0,1], giữ nguyên lớp |
| DUP_BOX, BAD_CLASS_ID, BOX_ZERO, BAD_FORMAT | 7, 6, 4, 3 dòng | máy (`drop_line`, 20 dòng) | dòng hỏng, không có cách sửa an toàn nào khác ngoài xoá |
| BAD_CLASS_NAME | 2 dòng (data.yaml) | máy (`rename_classes`) | ghi lại `names` theo `classes` |
| MISSING_LABEL_FILE | 6 ảnh | **người** | máy không được bịa nhãn (file rỗng nghĩa là "ảnh nền") |
| POSSIBLE_MISSING / LOOSE_BOX / FALSE_POS / WRONG_CLASS | 53 / 28 / 29 / 18 dòng | **người** | lỗi ngữ nghĩa, model cũng có thể sai nên chỉ cảnh báo |
| EMPTY_LABEL, BOX_TINY, BOX_HUGE | 12, 6, 3 | **người** | cần đối chiếu guideline |

**Hàng đợi** (`05_review_queue.csv`, 125 ảnh): điểm ưu tiên = tổng trọng số các cờ, nhân thêm (1 + conf) của model. `NEEDS_LABEL` có trọng số 10 nên 6 ảnh thiếu nhãn nằm ngay đầu hàng; đứng đầu là `img_0020` (11,5 điểm) vì vừa bị máy xoá dòng vừa có cờ thiếu box và nhầm lớp.
Người duyệt hết **80/80** ảnh. Số cờ ngữ nghĩa giảm từ **123 xuống 57** (v2 → v3); 45 ảnh cuối hàng không ai xem.

## 3. Calibration (2 ngưỡng)
Số liệu lấy từ `calibration/calibration_report.md` (bộ calib 39 ảnh) và từ việc chạy thử trên raw.

| Tham số | Khởi đầu | Đã chọn | P / R (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | **12** | NEAR: 1.00/0.50 → 1.00/0.67 | Lỗi này dẫn tới **xoá ảnh**, nên ưu tiên precision. 12 bắt được mọi cặp trùng thật trên raw ở khoảng cách ≤ 10 và chưa gộp nhầm cặp nào |
| `second_opinion.conf` | 0.25 | **0.6** | MISSING: 0.50/1.00 → 0.57/1.00; WRONG_CLASS: 0.56/0.83 → 0.62/0.83 | Đây là mức conf cao nhất chưa mất recall MISSING và WRONG_CLASS, đồng thời giảm báo động giả (cảnh báo trên raw: 58 → 38 ảnh) |

**Chỗ calibration đánh lừa:**
- **phash 16 trông tốt nhất trên calib** (recall NEAR 0.83), nhưng trên raw nó loại 26 ảnh thay vì 17. Mở xem từng cặp thì phần lớn là ảnh khác hẳn nhau (tennis và trượt tuyết, laptop và bóng chày). Lên phash 20 thì loại 134 ảnh.
- **conf 0.8 cho ra Release** (16/202 ảnh còn cảnh báo, tức 7,9%), nhưng recall MISSING tụt còn 0.75. Mở xem 25 cờ có conf trong khoảng 0.6–0.8 trên raw: đa số là vật thật bị thiếu box (người ở mép ảnh, xe bị che). Chọn 0.8 nghĩa là chấp nhận một lần Release giả.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
**(a) Gate chặn đúng.** Chạy `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb`:
- 6 ảnh thiếu file nhãn không có ai gán, nên kết luận **Rework** ("còn 6 lỗi bắt buộc"), mã thoát **20**.
- Log in ra "KHÔNG xuất", và thư mục `work/exp_nb` không được tạo.

Ngược lại, khi có người duyệt, 6 ảnh này nằm đầu hàng đợi, được gán nhãn, và gate chuyển sang Hold.

**(b) Điểm mù (có bằng chứng):**
1. **Box lỏng nhẹ:** recall LOOSE_BOX trên calib chỉ 0.20 (1/5), vì box lệch vừa phải vẫn có IoU ≥ 0.5 với dự đoán.
2. **Ảnh trùng bị cắt mạnh:** cặp `img_0084`/`img_0074` có khoảng cách phash 16, lẫn vào vùng của các cặp ảnh khác nhau, nên không ngưỡng nào tách được.
3. **Báo động giả của FALSE_POS:** precision trên calib chỉ 0.31 và không đổi theo conf (`fp_conf` cố định). Kết quả là 21 cờ ở v3, phần lớn có thể là nhãn đúng mà model không thấy.
4. **Nhầm lớp mà model cũng nhầm** (xe tải/xe buýt): không cờ nào được bật vì cả nhãn và model cùng sai.

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
**Chưa chạy.** Tôi ưu tiên hoàn thành phần lõi trước; phần train cần push repo và GPU trên Colab, sẽ làm sau nếu còn thời gian.

## 6. Quyết định và ghi chú AI
**(a) Quyết định: Hold.** Để thành Release cần ≤ 20/202 ảnh (dưới 10%) còn cảnh báo chưa duyệt. Muốn vậy, người cần duyệt thêm khoảng 18 ảnh tiếp theo trong hàng đợi, hoặc mở thêm một vòng duyệt (dự án thật thì tăng ngân sách). Không hạ checker để ép ra Release.

**(b) Ghi chú dùng AI** (Claude Code):
- **Prompt chính:** mô tả đủ 4 ý cho từng module (đầu vào/đầu ra theo docstring, ngưỡng đọc từ `cfg`, các ca biên trong test, không sửa `data/raw`). Yêu cầu chạy `pytest` cho từng file test.
- **Cách kiểm:** đọc từng dòng code; chạy unit test; tự viết thêm 3 ca biên (một dòng dính 2 lỗi, dòng trống giữa file, ảnh có nhiều dự đoán); chạy `make run` rồi mở `viz_labels.py` và ảnh các cặp trùng để đối chiếu.
- **Một lần AI sai:** bản đầu của `gate.py` so ngưỡng bằng tỉ lệ **đã làm tròn** 4 chữ số. Một tỉ lệ như 9,996% sẽ bị làm tròn thành 10% và ra Hold oan. Test không bắt được lỗi này; tôi sửa thành so bằng tỉ lệ gốc trước khi commit.
