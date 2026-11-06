"""OCR every page of one PDF into <out>/<stem>/pNN.json (lines of text, sideways pages rotated)."""
import json, sys
from pathlib import Path
import pymupdf
from rapidocr import RapidOCR

pdf, out = Path(sys.argv[1]), Path(sys.argv[2])
dest = out / pdf.stem.replace(" ", "_")
dest.mkdir(parents=True, exist_ok=True)
engine = RapidOCR()
doc = pymupdf.open(pdf)
img = dest / "tmp.png"

ORIGINAL = {}


def ocr_page(page, rotation):
    # Rotate relative to the page's own /Rotate so pages stored sideways keep their orientation.
    original = ORIGINAL.setdefault(page.number, page.rotation)
    page.set_rotation((original + rotation) % 360)
    page.get_pixmap(dpi=200).save(img)
    result = engine(str(img))
    if result.boxes is None:
        return []
    ocr_page.scores = dict(zip(map(id, result.boxes), result.scores))
    scored = list(zip(result.boxes, result.txts, result.scores))
    return [(b, t) for b, t, _ in scored] if not hasattr(ocr_page, "keep") else scored

def text_len(boxes):
    # Confidence-weighted text length: a wrong orientation yields many short, unsure fragments.
    return sum(len(item[1]) * (item[2] if len(item) > 2 else 1) ** 2 for item in boxes)

def group(boxes):
    items = sorted(boxes, key=lambda b: (b[0][0][1] + b[0][2][1]) / 2)
    lines = []
    for box, txt in items:
        y = (box[0][1] + box[2][1]) / 2
        part = [round(float(box[0][0])), round(float(box[2][0])), txt]
        if lines and abs(lines[-1]["y"] - y) < 14:
            lines[-1]["parts"].append(part)
        else:
            lines.append({"y": float(y), "parts": [part]})
    return [sorted(l["parts"]) for l in lines]

for index in range(doc.page_count):
    target = dest / f"p{index + 1:02d}.json"
    if target.exists():
        continue
    page = doc[index]
    ocr_page.keep = True
    boxes, rotation = ocr_page(page, 0), 0
    tall = sum(1 for b, *_ in boxes if (b[2][1] - b[0][1]) > (b[2][0] - b[0][0]) * 1.5)
    if boxes and tall > len(boxes) * 0.4:
        for angle in (90, 270):
            candidate = ocr_page(page, angle)
            if text_len(candidate) > text_len(boxes):
                boxes, rotation = candidate, angle
    boxes = [(b, t) for b, t, *_ in boxes]
    rows = group(boxes)
    tokens = [[round(float(b[0][0])), round(float(b[2][0])), round(float(b[0][1])), round(float(b[2][1])), t]
              for b, t in boxes]
    data = {"rotation": rotation, "lines": [" | ".join(t for _, _, t in r) for r in rows], "rows": rows,
            "tokens": tokens}
    target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
img.unlink(missing_ok=True)
print("done", pdf.name, flush=True)
