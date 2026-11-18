"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Số dòng trong `issues` là số dòng GỐC (kể cả dòng trống) -> gom theo file, sửa trên bản đọc một lần, ghi lại một lần.
Xoá dòng thắng cắt box. Không động tới WARN. Chạy lại trên dữ liệu đã sửa không làm gì thêm (trừ `needs_label`).
"""
from collections import defaultdict

import yaml

from ..common import ERROR, parse_yolo_line

DROP = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
CLIP = {"BOX_OUT_OF_IMAGE"}
REMOVE = {"LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}          # + mọi mã bắt đầu bằng DUP_IMAGE_


def _rec(image, line, action, before, after):
    return dict(image=image, line=line, action=action, before=before, after=after)


def _clip(text):
    """Cắt box về [0,1]. Trả dòng mới, hoặc None nếu box không còn diện tích."""
    c, x, y, w, h = parse_yolo_line(text)
    x1, x2 = max(0.0, x - w / 2), min(1.0, x + w / 2)
    y1, y2 = max(0.0, y - h / 2), min(1.0, y + h / 2)
    if x2 <= x1 or y2 <= y1:
        return None
    return f"{c} {(x1 + x2) / 2:.6f} {(y1 + y2) / 2:.6f} {x2 - x1:.6f} {y2 - y1:.6f}"


def _remove_image(ds, stem):
    p = ds.image_path(stem)
    if p is None:                                   # đã xoá ở lần trước / issue lặp: bỏ qua êm
        return None
    p.unlink()
    ds.label_path(stem).unlink(missing_ok=True)
    return _rec(stem, "", "remove_image", p.name, "(đã xoá ảnh + nhãn)")


def _rename_classes(ds, classes):
    d = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) if ds.yaml_path.exists() else None
    d = d if isinstance(d, dict) else {}
    before = d.get("names")
    d["names"] = dict(enumerate(classes))
    ds.yaml_path.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return _rec("data.yaml", "", "rename_classes", str(before), str(d["names"]))


def _fix_lines(ds, stem, drops, clips):
    """Sửa một file nhãn một lần theo số dòng gốc."""
    p = ds.label_path(stem)
    if not p.exists():
        return []
    rows = p.read_text(encoding="utf-8", errors="replace").splitlines()
    out, keep = [], []
    for n, text in enumerate(rows, 1):
        if n in drops:
            out.append(_rec(stem, n, "drop_line", text, ""))
            continue
        if n in clips:
            try:
                new = _clip(text)
            except ValueError:                      # không parse được thì không thể cắt an toàn
                new = None
            if new is None:
                out.append(_rec(stem, n, "drop_line", text, ""))
                continue
            out.append(_rec(stem, n, "clip_box", text, new))
            text = new
        keep.append(text)
    if out:
        p.write_text("".join(t + "\n" for t in keep), encoding="utf-8")
    return out


def fix(ds, issues, cfg):
    errors = [i for i in issues if i.severity == ERROR]
    fixes = []

    removed = set()
    for i in errors:
        if (i.code in REMOVE or i.code.startswith("DUP_IMAGE_")) and i.image not in removed:
            removed.add(i.image)
            r = _remove_image(ds, i.image)
            if r:
                fixes.append(r)

    if any(i.code == "BAD_CLASS_NAME" for i in errors):
        fixes.append(_rename_classes(ds, cfg["classes"]))

    drops, clips = defaultdict(set), defaultdict(set)
    for i in errors:
        if i.image in removed or i.line is None:
            continue
        if i.code in DROP:
            drops[i.image].add(i.line)
        elif i.code in CLIP:
            clips[i.image].add(i.line)
    for stem in sorted(set(drops) | set(clips)):
        fixes.extend(_fix_lines(ds, stem, drops[stem], clips[stem] - drops[stem]))

    for stem in sorted({i.image for i in errors if i.code == "MISSING_LABEL_FILE"} - removed):
        if ds.image_path(stem) and not ds.label_path(stem).exists():
            fixes.append(_rec(stem, "", "needs_label", "(không có file)", "chuyển người gán"))
    return fixes
