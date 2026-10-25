# =====================================================================
#  QR STICKER GENERATOR for the Digital Product Passport
#
#  Run:   python generate_qr.py
#  Makes: qr_codes/DPP-001.png ... (one sticker per device)
#         qr_codes/all_stickers.pdf  (A4 sheet ready to print)
# =====================================================================

import os

import pandas as pd
import qrcode
from PIL import Image, ImageDraw, ImageFont

# Paste the SAME link you put in app.py (no "/" at the end)
APP_URL = "https://your-app-name.streamlit.app"

OUTPUT_FOLDER = "qr_codes"
GREEN = (27, 127, 90)


def get_font(size, bold=False):
    """Use Arial if available, otherwise Pillow's built-in font."""
    names = ["arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf"] if bold else ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def make_sticker(device_id, device_name):
    """One sticker: green header, QR code, device name and ID."""
    link = f"{APP_URL}/?id={device_id}"
    qr = qrcode.make(link, box_size=10, border=2).convert("RGB").resize((340, 340))

    sticker = Image.new("RGB", (380, 500), "white")
    draw = ImageDraw.Draw(sticker)
    draw.rectangle([0, 0, 380, 60], fill=GREEN)
    draw.text((190, 30), "Digital Product Passport", fill="white", font=get_font(24, bold=True), anchor="mm")
    sticker.paste(qr, (20, 70))
    draw.text((190, 432), device_name[:28], fill="black", font=get_font(22, bold=True), anchor="mm")
    draw.text((190, 465), f"ID: {device_id}  |  Scan me", fill=(80, 80, 80), font=get_font(18), anchor="mm")
    draw.rectangle([0, 0, 379, 499], outline=GREEN, width=3)
    return sticker


def main():
    if "your-app-name" in APP_URL:
        print("WARNING: APP_URL is still the placeholder. Paste your real app link first.\n")

    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    devices = pd.read_csv("devices.csv", dtype={"id": str})

    stickers = []
    for _, row in devices.iterrows():
        sticker = make_sticker(row["id"].strip(), row["device"])
        sticker.save(os.path.join(OUTPUT_FOLDER, f"{row['id'].strip()}.png"))
        stickers.append(sticker)
        print(f"Made sticker for {row['id']}  ->  {APP_URL}/?id={row['id'].strip()}")

    # Arrange stickers on A4 pages (3 across, 3 down) for printing
    page_w, page_h, cols, rows = 1240, 1754, 3, 3
    pages = []
    for start in range(0, len(stickers), cols * rows):
        page = Image.new("RGB", (page_w, page_h), "white")
        for i, sticker in enumerate(stickers[start:start + cols * rows]):
            x = 25 + (i % cols) * 405
            y = 60 + (i // cols) * 560
            page.paste(sticker, (x, y))
        pages.append(page)
    pdf_path = os.path.join(OUTPUT_FOLDER, "all_stickers.pdf")
    pages[0].save(pdf_path, save_all=True, append_images=pages[1:], resolution=150)
    print(f"\nDone. {len(stickers)} stickers saved in the '{OUTPUT_FOLDER}' folder.")
    print(f"Print this file: {pdf_path}")


if __name__ == "__main__":
    main()
