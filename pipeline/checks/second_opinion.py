"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.

Với từng ảnh (bỏ qua ảnh không có trong preds hoặc không có file nhãn):
  P = dự đoán có conf >= conf  VÀ diện tích px >= min_area_px
  Với mỗi r trong P, cands = nhãn (mọi lớp) có IoU(r, nhãn) >= iou_missing:
   (1) cands rỗng                                   -> POSSIBLE_MISSING
   (2) có cands cùng lớp: IoU tốt nhất < iou_loose  -> POSSIBLE_LOOSE_BOX, ngược lại không cờ
   (3) chỉ có khác lớp: IoU tốt nhất >= iou_match   -> POSSIBLE_WRONG_CLASS, ngược lại không cờ (mơ hồ)
  Mỗi dòng nhãn hợp lệ có IoU < iou_missing với MỌI dự đoán conf >= fp_conf -> POSSIBLE_FALSE_POS (Issue.line)
Tất cả WARN.
"""
from ..common import WARN, Issue, iou_xywh, parse_yolo_line
from ..model_cache import get_preds

CHECK = "second_opinion"


def _labels(ds, stem):
    """[(số dòng gốc, id lớp, (cx, cy, w, h))] của các dòng hợp lệ; dòng hỏng bỏ qua (label_format báo)."""
    out = []
    for ln, text in ds.read_label_lines(stem):
        try:
            c, *box = parse_yolo_line(text)
        except ValueError:
            continue
        if 0 <= c < len(ds.classes):
            out.append((ln, c, tuple(box)))
    return out


def run(ds, cfg, preds=None):
    c = cfg["second_opinion"]
    if preds is None:
        preds = get_preds(ds, cfg, "checker")
    names = ds.classes
    issues = []
    for p in ds.image_files():
        stem = p.stem
        if stem not in preds or ds.read_label_lines(stem) is None:
            continue
        size = ds.image_size(stem)
        if not size:
            continue
        W, H = size
        labels = _labels(ds, stem)
        rows = preds[stem]

        def add(code, msg, line=None, **extra):
            issues.append(Issue(CHECK, WARN, code, stem, msg, line, extra))

        for r in rows:
            cls, conf, box = int(r[0]), r[1], tuple(r[2:6])
            if conf < c["conf"] or box[2] * W * box[3] * H < c["min_area_px"]:
                continue
            cands = [(iou_xywh(box, b), lc) for _, lc, b in labels]
            cands = [x for x in cands if x[0] >= c["iou_missing"]]
            same = [iou for iou, lc in cands if lc == cls]
            other = [(iou, lc) for iou, lc in cands if lc != cls]
            pname = names[cls] if 0 <= cls < len(names) else cls
            if not cands:
                add("POSSIBLE_MISSING", f"model thấy {pname} (conf {conf:.2f}) mà nhãn không có box",
                    conf=conf, pred_class=cls, box=list(box))
            elif same:
                best = max(same)
                if best < c["iou_loose"]:
                    add("POSSIBLE_LOOSE_BOX", f"box {pname} lệch/lỏng so với model (IoU {best:.2f})",
                        conf=conf, iou=round(best, 4), pred_class=cls)
            else:
                best, lc = max(other)
                if best >= c["iou_match"]:
                    add("POSSIBLE_WRONG_CLASS", f"nhãn {names[lc]} nhưng model nói {pname} (conf {conf:.2f}, IoU {best:.2f})",
                        conf=conf, iou=round(best, 4), pred_class=cls, label_class=lc)

        fp_boxes = [tuple(r[2:6]) for r in rows if r[1] >= c["fp_conf"]]
        for ln, lc, b in labels:
            best = max((iou_xywh(b, pb) for pb in fp_boxes), default=0.0)
            if best < c["iou_missing"]:
                add("POSSIBLE_FALSE_POS", f"box {names[lc]} không khớp vật nào model thấy (IoU tốt nhất {best:.2f})",
                    line=ln, iou=round(best, 4), label_class=lc)
    return issues
