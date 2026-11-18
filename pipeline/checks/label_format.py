"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line

CHECK = "label_format"


def run(ds, cfg):
    c = cfg["label_format"]
    n_cls = len(ds.classes)
    issues = []
    for lf in ds.label_files():
        stem = lf.stem
        size = ds.image_size(stem)                        # None nếu không có ảnh / ảnh hỏng
        seen = []                                         # box hợp lệ ở các dòng trước: (id, cx, cy, w, h)
        for ln, text in ds.read_label_lines(stem) or []:
            def add(sev, code, msg, **extra):
                issues.append(Issue(CHECK, sev, code, stem, msg, ln, extra))

            try:
                cls, x, y, w, h = parse_yolo_line(text)
            except ValueError as e:
                add(ERROR, "BAD_FORMAT", f"dòng sai định dạng ({e}): {text.strip()!r}")
                continue
            if not 0 <= cls < n_cls:
                add(ERROR, "BAD_CLASS_ID", f"id lớp {cls} ngoài 0..{n_cls - 1}", id=cls)
                continue
            if w <= 0 or h <= 0:
                add(ERROR, "BOX_ZERO", f"box không có diện tích (w={w}, h={h})")
                continue

            overflow = max(w / 2 - x, x + w / 2 - 1, h / 2 - y, y + h / 2 - 1)
            if overflow > c["overflow_tol"]:
                add(ERROR, "BOX_OUT_OF_IMAGE", f"box tràn ra ngoài ảnh {overflow:.4f}", overflow=round(overflow, 6))

            box = (x, y, w, h)
            dup = next((i for i, b in enumerate(seen) if b[0] == cls and iou_xywh(b[1], box) > c["dup_box_iou"]), None)
            if dup is not None:
                add(ERROR, "DUP_BOX", f"trùng box cùng lớp với dòng {seen[dup][2]}", of_line=seen[dup][2])
            seen.append((cls, box, ln))

            if size:
                short_px = min(w * size[0], h * size[1])
                if short_px < c["min_box_px"]:
                    add(WARN, "BOX_TINY", f"cạnh ngắn {short_px:.1f}px < {c['min_box_px']}px", short_px=round(short_px, 1))
            if w * h > c["max_box_frac"]:
                add(WARN, "BOX_HUGE", f"box chiếm {w * h:.2%} ảnh", frac=round(w * h, 4))
    return issues
