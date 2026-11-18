"""BƯỚC 4 — Cửa chặn: quyết định Release / Hold / Rework.   ★

Test:  pytest tests/test_gate.py -q

Cây quyết định Day 07 (slide Day 09: "Lỗi bắt buộc chặn pipeline; lỗi cảnh báo chuyển người xem"):

  còn ≥ 1 lỗi bắt buộc (severity ERROR)                          -> "Rework"
  không còn lỗi bắt buộc, nhưng tỉ lệ ẢNH còn cảnh báo
      >= cfg["gate"]["warn_ratio_hold"]                          -> "Hold"
  còn lại                                                        -> "Release"

Tỉ lệ cảnh báo = (số ẢNH khác nhau có ≥ 1 cảnh báo) / (tổng số ảnh).  Chú ý:
- chỉ đếm issue có `image` nằm trong `image_stems` (bỏ "<dataset>", "data.yaml");
- bỏ qua ảnh nằm trong `reviewed` (người đã xem, cảnh báo của ảnh đó coi như đã xử lý) — nhưng LỖI BẮT BUỘC thì không bao giờ được bỏ qua;
- mẫu số là số ảnh, không phải số issue.

Trả về dict: decision, n_errors, n_warn_images, n_images, warn_ratio (làm tròn 4 chữ số), reasons (list[str], giải thích bằng tiếng Việt, có số liệu).
"""
from ..common import ERROR, WARN


def decide(issues, image_stems, cfg, reviewed=frozenset()):
    stems, reviewed = set(image_stems), set(reviewed)
    hold_at = cfg["gate"]["warn_ratio_hold"]
    n_errors = sum(i.severity == ERROR for i in issues)          # lỗi bắt buộc: đếm hết, kể cả cấp dataset / ảnh đã duyệt
    warn_imgs = {i.image for i in issues if i.severity == WARN and i.image in stems and i.image not in reviewed}
    n = len(stems)
    raw = len(warn_imgs) / n if n else 0.0                      # so ngưỡng bằng số chưa làm tròn
    ratio = round(raw, 4)

    if n_errors:
        decision = "Rework"
        reasons = [f"còn {n_errors} lỗi bắt buộc (máy/người phải sửa trước khi xuất)"]
    elif raw >= hold_at:
        decision = "Hold"
        reasons = [f"{len(warn_imgs)}/{n} ảnh ({ratio:.1%}) còn cảnh báo chưa người duyệt, ≥ ngưỡng {hold_at:.0%}"]
    else:
        decision = "Release"
        reasons = [f"0 lỗi bắt buộc; {len(warn_imgs)}/{n} ảnh ({ratio:.1%}) còn cảnh báo chưa duyệt, < ngưỡng {hold_at:.0%}"]
    return dict(decision=decision, n_errors=n_errors, n_warn_images=len(warn_imgs), n_images=n, warn_ratio=ratio, reasons=reasons)
