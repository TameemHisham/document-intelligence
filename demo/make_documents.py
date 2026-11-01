"""Generate the demo library's sample documents (fictional brands), styled like phone photos of paper.

Usage: python demo/make_documents.py demo/samples
"""

import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "demo/samples")
SUPP = "/System/Library/Fonts/Supplemental/"


def font(names: list[str], size: int) -> ImageFont.FreeTypeFont:
    for n in names:
        for base in (SUPP, "/System/Library/Fonts/", "/usr/share/fonts/truetype/dejavu/"):
            try:
                return ImageFont.truetype(base + n, size)
            except OSError:
                continue
    return ImageFont.load_default(size)


SERIF = lambda s: font(["Georgia.ttf", "Times New Roman.ttf", "DejaVuSerif.ttf"], s)  # noqa: E731
SANS = lambda s: font(["Arial.ttf", "DejaVuSans.ttf"], s)  # noqa: E731
BOLD = lambda s: font(["Arial Bold.ttf", "DejaVuSans-Bold.ttf"], s)  # noqa: E731
MONO = lambda s: font(["Courier New.ttf", "Menlo.ttc", "DejaVuSansMono.ttf"], s)  # noqa: E731
HAND = lambda s: font(["Bradley Hand Bold.ttf", "Noteworthy.ttc", "DejaVuSans.ttf"], s)  # noqa: E731


def photograph(paper: Image.Image, bg: str, date: str, name: str, angle: float) -> None:
    """Place paper on a surface with a soft shadow and slight tilt; save as JPEG with an EXIF date."""
    W, H = 1600, 1200
    canvas = Image.new("RGB", (W, H), bg)
    noise = Image.effect_noise((W, H), 18).convert("RGB")
    canvas = Image.blend(canvas, noise, 0.06)
    paper = paper.rotate(angle, expand=True, resample=Image.BICUBIC, fillcolor=(0, 0, 0, 0))
    scale = min((W * 0.82) / paper.width, (H * 0.9) / paper.height)
    paper = paper.resize((int(paper.width * scale), int(paper.height * scale)), Image.LANCZOS)
    x, y = (W - paper.width) // 2, (H - paper.height) // 2
    shadow = Image.new("L", paper.size, 0)
    shadow.paste(paper.getchannel("A").point(lambda a: 110 if a else 0))
    canvas.paste(Image.new("RGB", paper.size, (40, 35, 30)), (x + 14, y + 18), shadow.filter(ImageFilter.GaussianBlur(14)))
    canvas.paste(paper, (x, y), paper)
    exif = Image.Exif()
    exif[306] = date
    canvas.save(OUT / name, "JPEG", quality=88, exif=exif)
    print("wrote", name)


def sheet(w: int, h: int, color=(252, 250, 244)) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    im = Image.new("RGBA", (w, h), color + (255,))
    return im, ImageDraw.Draw(im)


def warranty():
    im, d = sheet(1100, 1450)
    d.rectangle([30, 30, 1070, 1420], outline=(176, 150, 92), width=10)
    d.rectangle([52, 52, 1048, 1398], outline=(176, 150, 92), width=2)
    d.text((550, 150), "CERTIFICATE OF WARRANTY", font=SERIF(58), fill=(60, 50, 30), anchor="mm")
    d.text((550, 230), "AeroBreeze Home Appliances", font=SERIF(34), fill=(110, 95, 60), anchor="mm")
    lines = [
        ("Product", "AeroBreeze Pure Cool AB-7 Air Purifier Fan"),
        ("Serial no.", "AB7-4821-9930"),
        ("Purchase date", "14 November 2024"),
        ("Retailer", "Hartley & Sons, Manchester"),
    ]
    y = 360
    for k, v in lines:
        d.text((130, y), f"{k}:", font=BOLD(30), fill=(50, 50, 50))
        d.text((420, y), v, font=SANS(30), fill=(30, 30, 30))
        y += 70
    body = [
        "This product is guaranteed for 2 years from the date of purchase",
        "against defects in materials and workmanship. During the warranty",
        "period we will repair or replace the product free of charge.",
        "",
        "To make a claim, keep this certificate with your proof of purchase",
        "and contact support@aerobreeze.example quoting the serial number.",
        "The warranty does not cover filters, accidental damage or misuse.",
    ]
    y += 40
    for line in body:
        d.text((130, y), line, font=SERIF(28), fill=(45, 45, 45))
        y += 46
    d.ellipse([820, 1150, 980, 1310], fill=(196, 160, 70), outline=(150, 120, 50), width=6)
    d.text((900, 1230), "2 YEAR\nWARRANTY", font=BOLD(24), fill=(255, 250, 235), anchor="mm", align="center")
    d.text((130, 1290), "Authorised signature  __________________", font=SERIF(26), fill=(80, 80, 80))
    photograph(im, "#8d7b68", "2024:11:14 18:20:00", "doc-warranty-air-purifier.jpg", 1.5)


def receipt(name, shop, address, date_str, exif_date, items, total, currency, angle):
    im, d = sheet(720, 300 + 60 * len(items) + 520, (255, 255, 255))
    mono = MONO(30)
    y = 50
    d.text((360, y), shop, font=BOLD(40), fill=(20, 20, 20), anchor="mm")
    y += 50
    for a in address:
        d.text((360, y), a, font=mono, fill=(60, 60, 60), anchor="mm")
        y += 38
    y += 20
    d.text((50, y), date_str, font=mono, fill=(40, 40, 40))
    y += 60
    d.line([50, y, 670, y], fill=(120, 120, 120), width=2)
    y += 30
    for label, price in items:
        d.text((50, y), label, font=mono, fill=(30, 30, 30))
        d.text((670, y), f"{price:.2f}", font=mono, fill=(30, 30, 30), anchor="ra")
        y += 52
    d.line([50, y + 10, 670, y + 10], fill=(120, 120, 120), width=2)
    y += 40
    d.text((50, y), f"TOTAL {currency}", font=BOLD(36), fill=(10, 10, 10))
    d.text((670, y), f"{total:.2f}", font=BOLD(36), fill=(10, 10, 10), anchor="ra")
    y += 70
    d.text((50, y), "PAID BY CARD  **** 4417", font=mono, fill=(60, 60, 60))
    y += 80
    d.text((360, y), "Thank you - see you soon!", font=mono, fill=(60, 60, 60), anchor="mm")
    random.seed(name)
    for _ in range(40):  # thermal-paper speckle
        x0, y0 = random.randint(0, 719), random.randint(0, im.height - 1)
        d.point((x0, y0), fill=(200, 200, 200))
    photograph(im, "#5b4a3c", exif_date, name, angle)


def lecture_notes():
    im, d = sheet(1100, 1450, (250, 250, 240))
    for yy in range(160, 1420, 52):
        d.line([0, yy, 1100, yy], fill=(170, 200, 230), width=2)
    d.line([120, 0, 120, 1450], fill=(230, 150, 150), width=3)
    hand, big = HAND(40), HAND(54)
    blue = (30, 50, 120)
    d.text((150, 80), "Biology - Lecture 7: Cell Division", font=big, fill=blue)
    lines = [
        "Mitosis = 1 cell -> 2 identical daughter cells",
        "Phases: prophase, metaphase, anaphase, telophase",
        "  - prophase: chromosomes condense, spindle forms",
        "  - metaphase: line up at the middle (metaphase plate)",
        "  - anaphase: sister chromatids pulled apart",
        "  - telophase: nuclei re-form -> cytokinesis",
        "",
        "Mitochondria make ATP by oxidative phosphorylation",
        "  (electron transport chain + ATP synthase)",
        "",
        "Exam: 12 December - revise diagrams!",
    ]
    y = 205
    for line in lines:
        d.text((150, y - 40), line, font=hand, fill=blue)
        y += 104 if not line else 52
    cx, cy = 820, 1220  # little cell sketch
    d.ellipse([cx - 160, cy - 110, cx + 160, cy + 110], outline=blue, width=4)
    d.ellipse([cx - 50, cy - 40, cx + 50, cy + 40], outline=blue, width=4)
    d.text((cx - 40, cy + 120), "cell", font=hand, fill=blue)
    photograph(im, "#c9c2b5", "2026:10:30 11:05:00", "doc-lecture-notes-biology.jpg", -2.0)


def manual():
    im, d = sheet(1100, 1450, (255, 255, 255))
    d.rectangle([0, 0, 1100, 150], fill=(35, 60, 50))
    d.text((70, 75), "Bramble Burr Grinder BG-40  ·  Quick Start", font=BOLD(42), fill="white", anchor="lm")
    sections = [
        ("1. Grind settings", ["Settings run from 1 (finest) to 40 (coarsest).",
                               "Espresso: 4-8   Pour-over: 14-20   French press: 28-34"]),
        ("2. Cleaning", ["Clean the burrs every 2 weeks with the brush provided.",
                         "Do not wash the hopper in a dishwasher.",
                         "Run 20 g of rice-free cleaning tablets monthly."]),
        ("3. Safety", ["Unplug before removing the upper burr.",
                       "Never operate with an empty hopper for more than 10 seconds."]),
        ("4. Support", ["Model BG-40 · 150 W · 220-240 V",
                        "Register your grinder at bramble.example/register"]),
    ]
    y = 220
    for title, body in sections:
        d.text((70, y), title, font=BOLD(36), fill=(35, 60, 50))
        y += 60
        for line in body:
            d.text((90, y), line, font=SANS(28), fill=(40, 40, 40))
            y += 44
        y += 40
    d.rounded_rectangle([700, 1100, 1020, 1380], radius=30, outline=(35, 60, 50), width=5)
    d.ellipse([800, 1170, 920, 1290], outline=(35, 60, 50), width=5)
    photograph(im, "#d8d2c6", "2026:11:01 09:12:00", "doc-grinder-manual.jpg", 0.8)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    warranty()
    receipt("doc-receipt-coffee.jpg", "COPPER KETTLE COFFEE", ["Rua das Flores 41", "1200-195 Lisboa"],
            "31/10/2026  09:42", "2026:10:31 09:45:00",
            [("Coffee beans 250g", 28.00), ("Oat flat white x2", 9.50), ("Pastel de nata x3", 7.00)], 44.50, "EUR", -3.0)
    receipt("doc-receipt-headphones.jpg", "VOLT & WIRE", ["14 Market Street", "Manchester M1 1PT"],
            "12/09/2026  16:05", "2026:09:12 16:10:00",
            [("Wireless headphones NX-3", 119.99), ("USB-C cable 1m", 10.00)], 129.99, "GBP", 2.5)
    lecture_notes()
    manual()
