# =====================================================================
#  DIGITAL PRODUCT PASSPORT  -  Streamlit web app  (version 3)
#  Theme: Sustainable & Circular Engineering (RVCE ECE, Experiential Learning)
#  Device: Dell Inspiron 6400 (PP20L) - all details are in devices.json
#
#  Run on your laptop:   python -m streamlit run app.py
#  Home page:            http://localhost:8501
#  Passport page:        http://localhost:8501/?id=DPP-001
# =====================================================================

import io
import json
from datetime import date, datetime, timedelta, timezone

import qrcode
import requests
import streamlit as st

# ---------------------------------------------------------------------
# 1. SETTINGS  (the only part you normally need to change)
# ---------------------------------------------------------------------

# After you deploy on Streamlit Community Cloud, paste your app's link here
# (no "/" at the end). The QR codes are built from this link.
APP_URL = "https://rvce-dpptrial.streamlit.app"

# LIVE prices: fetched from the free Gold-API service (no API key needed).
LIVE_SYMBOLS = {"gold": "XAU", "silver": "XAG", "palladium": "XPD", "copper": "HG"}

# How often to fetch new prices (seconds).
PRICE_REFRESH_SECONDS = 60

# Backup prices in Rupees per gram, used ONLY if the live service cannot be reached.
FALLBACK_PRICES = {"gold": 14395.0, "silver": 195.0, "palladium": 3076.0, "copper": 1.39}

# REFERENCE prices in Rupees per gram for metals with no free live source.
REFERENCE_PRICES = {"cobalt": 3.65, "lithium": 1.0}

GRAMS_PER_TROY_OUNCE = 31.1034768   # gold, silver, palladium are quoted per troy ounce
GRAMS_PER_POUND = 453.59237         # copper (HG) is quoted per pound

# The life-cycle stages a device moves through, in order.
STATUS_STEPS = ["In use", "Repaired", "Collected", "Sent to recycler", "Recycled"]

st.set_page_config(page_title="Digital Product Passport", page_icon="♻️", layout="centered")


# ---------------------------------------------------------------------
# 2. LOAD THE DATA  (everything about the device lives in devices.json)
# ---------------------------------------------------------------------
def load_devices():
    with open("devices.json", encoding="utf-8") as f:
        return json.load(f)["devices"]


def find_device(devices, device_id):
    for d in devices:
        if d["id"].strip().upper() == device_id.strip().upper():
            return d
    return None


# ---------------------------------------------------------------------
# 3. HELPER FUNCTIONS
# ---------------------------------------------------------------------
def recommend(d):
    """Repair / Reuse / Recycle decision (same logic as the decision-tree slide)."""
    age = date.today().year - int(d["year"])
    condition = d["condition"].strip().lower()
    if d["status"] == "Recycled":
        return "RECYCLED", "success", "This device has completed its journey. Its materials are back in use."
    if condition == "working":
        if age > 5:
            return "REUSE - Donate or sell", "info", f"It still works but is {age} years old. Give it a second life with someone who needs it."
        return "REUSE - Keep using", "success", f"It works and is only {age} years old. The greenest device is the one you already own."
    if condition == "repairable":
        return "REPAIR", "warning", "The fault can be fixed. Repairing it saves the materials and energy needed to make a new one."
    return "RECYCLE", "error", "It cannot be repaired. Send it to an authorised recycler so its metals can be recovered safely."


def metal_value_rows(d, prices, sources):
    """Rows of (metal, amount text, price text, value in Rs) using the device's value_basis."""
    v = d["value_basis"]
    grams = {
        "Gold": (v["gold_mg"] / 1000, f"{v['gold_mg']} mg"),
        "Silver": (v["silver_mg"] / 1000, f"{v['silver_mg']} mg"),
        "Palladium": (v["palladium_mg"] / 1000, f"{v['palladium_mg']} mg"),
        "Copper": (v["copper_g"], f"{v['copper_g']} g"),
        "Cobalt": (v["cobalt_g"], f"{v['cobalt_g']} g"),
        "Lithium": (v["lithium_g"], f"{v['lithium_g']} g"),
    }
    rows = []
    for metal, (g, text) in grams.items():
        key = metal.lower()
        rows.append((metal, text, f"{prices[key]:,.2f} ({sources[key]})", g * prices[key]))
    return rows


def md_table(table):
    """Turn {'columns': [...], 'rows': [[...]]} into a Markdown table (keeps **bold**)."""
    clean = lambda s: str(s).replace("|", "/").replace("\n", " ")
    lines = ["| " + " | ".join(clean(c) for c in table["columns"]) + " |",
             "|" + "---|" * len(table["columns"])]
    for row in table["rows"]:
        lines.append("| " + " | ".join(clean(c) for c in row) + " |")
    return "\n".join(lines)


def make_qr_png(url):
    img = qrcode.make(url, box_size=10, border=2)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def passport_link(device_id):
    return f"{APP_URL}/?id={device_id}"


def show_message(kind, text):
    {"success": st.success, "info": st.info, "warning": st.warning, "error": st.error}[kind](text)


def go_to(device_id=None):
    st.query_params.clear()
    if device_id:
        st.query_params["id"] = device_id


# ---------------------------------------------------------------------
# 4. LIVE METAL PRICES + SIDEBAR
# ---------------------------------------------------------------------
@st.cache_data(ttl=3 * 60 * 60, show_spinner=False)
def usd_to_inr_rate():
    """Backup only: USD -> INR exchange rate."""
    data = requests.get("https://open.er-api.com/v6/latest/USD", timeout=8).json()
    return float(data["rates"]["INR"])


def fetch_one_price(symbol):
    """Price of one metal in Rupees per gram, from Gold-API."""
    data = requests.get(f"https://api.gold-api.com/price/{symbol}/INR", timeout=8).json()
    price = float(data["price"])
    if data.get("currency") != "INR":
        price = price * usd_to_inr_rate()
    grams = GRAMS_PER_POUND if symbol == "HG" else GRAMS_PER_TROY_OUNCE
    return price / grams, data.get("updatedAt")


@st.cache_data(ttl=PRICE_REFRESH_SECONDS, show_spinner="Fetching live metal prices...")
def fetch_live_prices():
    prices, updated, failed = {}, None, []
    for metal, symbol in LIVE_SYMBOLS.items():
        try:
            per_gram, when = fetch_one_price(symbol)
            if metal == "copper" and not 0.1 < per_gram < 20:   # sanity check on the unit
                raise ValueError("unexpected copper price")
            prices[metal] = per_gram
            updated = when or updated
        except Exception:
            failed.append(metal)
    return prices, updated, failed


def to_ist(iso_time):
    try:
        t = datetime.fromisoformat(iso_time.replace("Z", "+00:00"))
        return t.astimezone(timezone(timedelta(hours=5, minutes=30))).strftime("%d %b %Y, %I:%M %p IST")
    except Exception:
        return "unknown time"


def price_sidebar():
    live, updated, failed = fetch_live_prices()
    prices, sources = {}, {}
    st.sidebar.header("Metal prices (Rs per gram)")
    st.sidebar.subheader("🟢 Live market prices")
    for metal in LIVE_SYMBOLS:
        if metal in live:
            prices[metal], sources[metal] = live[metal], "live"
            st.sidebar.metric(metal.capitalize(), f"Rs {live[metal]:,.2f}")
        else:
            prices[metal], sources[metal] = FALLBACK_PRICES[metal], "backup"
            st.sidebar.metric(metal.capitalize(), f"Rs {FALLBACK_PRICES[metal]:,.2f}", "backup price", delta_color="off")
    if updated:
        st.sidebar.caption(f"Updated: {to_ist(updated)}. Source: gold-api.com")
    if failed:
        st.sidebar.warning("Live price unavailable for: " + ", ".join(failed) + ". Showing backup prices.")
    if st.sidebar.button("🔄 Refresh prices now"):
        fetch_live_prices.clear()
        st.rerun()
    st.sidebar.subheader("📘 Reference prices")
    st.sidebar.caption("No free live source for these metals. Edit if needed.")
    for metal, value in REFERENCE_PRICES.items():
        prices[metal] = st.sidebar.number_input(metal.capitalize(), min_value=0.0, value=value, step=0.25)
        sources[metal] = "reference"
    return prices, sources


# ---------------------------------------------------------------------
# 5. HOME PAGE
# ---------------------------------------------------------------------
def home_page(devices):
    st.title("♻️ Digital Product Passport")
    st.subheader("Scan it. Know it. Repair, Reuse or Recycle it.")
    st.write("Scan the QR sticker on the device, or open its passport below.")
    for d in devices:
        label, _, _ = recommend(d)
        with st.container(border=True):
            left, right = st.columns([1, 2])
            left.image(d["image"], width="stretch")
            right.markdown(f"**{d['device']}**  \n{d['model']} · {d['year']} · ID {d['id']}")
            right.caption(f"Status: {d['status']}  |  Advice: {label}")
            right.button("Open passport", key=d["id"], on_click=go_to, args=(d["id"],), width="stretch")


# ---------------------------------------------------------------------
# 6. PASSPORT PAGE
# ---------------------------------------------------------------------
def passport_page(d, prices, sources):
    st.button("← Home", on_click=go_to)

    # Header: photo, name, author
    st.image(d["image"], width=260)
    st.title("Digital Product Passport")
    st.subheader(f"{d['device']} ({d['model']})")
    st.caption(d["author"])

    # Recommendation and key numbers
    label, kind, reason = recommend(d)
    show_message(kind, f"**Recommendation: {label}**  \n{reason}")
    rows = metal_value_rows(d, prices, sources)
    c1, c2, c3 = st.columns(3)
    c1.metric("Weight", f"{d['weight_g'] / 1000:.1f} kg")
    c2.metric("Age", f"{date.today().year - int(d['year'])} years")
    c3.metric("Metal value (live)", f"Rs {sum(r[3] for r in rows):,.0f}")

    st.markdown("**Life-cycle status**")
    step = STATUS_STEPS.index(d["status"]) if d["status"] in STATUS_STEPS else 0
    st.progress((step + 1) / len(STATUS_STEPS))
    st.write("  →  ".join(f"**{s}**" if i == step else s for i, s in enumerate(STATUS_STEPS)))
    st.divider()

    # All sections from the Word document, in the same order
    for sec in d["sections"]:
        st.header(sec["title"])
        if sec.get("subtitle"):
            st.subheader(sec["subtitle"])
        if sec.get("intro"):
            st.markdown(sec["intro"])
        st.markdown(md_table(sec["table"]))
        if sec.get("note"):
            st.markdown(sec["note"])
        if sec.get("show_live_value"):
            st.markdown("**Estimated metal value at today's prices** (middle of each range above)")
            st.markdown(md_table({
                "columns": ["Metal", "Amount used", "Price (Rs/g)", "Value (Rs)"],
                "rows": [[m, a, p, f"{v:,.2f}"] for m, a, p, v in rows]
                        + [["**Total**", "", "", f"**{sum(r[3] for r in rows):,.2f}**"]],
            }))
            st.caption("Live prices for gold, silver, palladium and copper; reference prices for cobalt and lithium (see sidebar).")

    # Sources
    st.header("Sources")
    st.markdown("\n".join(f"{i}. {text} [{url}]({url})" for i, (text, url) in enumerate(d["sources"], 1)))

    # QR code
    st.divider()
    st.subheader("🔳 QR code for this device")
    link = passport_link(d["id"])
    st.image(make_qr_png(link), width=220)
    st.code(link, language=None)
    st.download_button("Download QR code", make_qr_png(link), file_name=f"{d['id']}.png", mime="image/png")
    if "your-app-name" in APP_URL:
        st.warning("APP_URL in app.py is still the placeholder. Update it after deploying, or this QR code will not open.")


# ---------------------------------------------------------------------
# 7. MAIN - decide which page to show
# ---------------------------------------------------------------------
devices = load_devices()
prices, sources = price_sidebar()
item_id = st.query_params.get("id")

if item_id:
    device = find_device(devices, item_id)
    if device is None:
        st.error(f"No device found with ID '{item_id}'.")
        st.button("← Home", on_click=go_to)
    else:
        passport_page(device, prices, sources)
else:
    home_page(devices)
