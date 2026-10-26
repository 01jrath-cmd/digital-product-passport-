# =====================================================================
#  DIGITAL PRODUCT PASSPORT  -  Streamlit web app
#  Theme: Sustainable & Circular Engineering (RVCE ECE, Experiential Learning)
#
#  Run on your laptop:   python -m streamlit run app.py
#  Home page:            http://localhost:8501
#  One device's page:    http://localhost:8501/?id=DPP-001
# =====================================================================

import io
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import qrcode
import requests
import streamlit as st

# ---------------------------------------------------------------------
# 1. SETTINGS  (the only part you normally need to change)
# ---------------------------------------------------------------------

# After you deploy on Streamlit Community Cloud, paste your app's link here
# (no "/" at the end). The QR codes are built from this link.
APP_URL = "https://rvce-dpptrial.streamlit.app/"

# LIVE prices: fetched from the free Gold-API service (no API key needed).
# Symbol for each metal on https://gold-api.com
LIVE_SYMBOLS = {"gold": "XAU", "silver": "XAG", "palladium": "XPD", "copper": "HG"}

# How often to fetch new prices (seconds). Refreshing the page after this
# time gets fresh prices. Gold-API itself updates about every 30 seconds.
PRICE_REFRESH_SECONDS = 60

# Backup prices in Rupees per gram, used ONLY if the live service cannot be reached.
FALLBACK_PRICES = {"gold": 12000.0, "silver": 150.0, "palladium": 3500.0, "copper": 1.0}

# REFERENCE prices in Rupees per gram for metals with no free live source.
# They can be changed in the sidebar during the demo.
REFERENCE_PRICES = {"cobalt": 3.0, "lithium": 1.0, "aluminium": 0.25}

GRAMS_PER_TROY_OUNCE = 31.1034768   # gold, silver, palladium are quoted per troy ounce
GRAMS_PER_POUND = 453.59237         # copper (HG) is quoted per pound

# The life-cycle stages a device moves through, in order.
STATUS_STEPS = ["In use", "Repaired", "Collected", "Sent to recycler", "Recycled"]

st.set_page_config(page_title="Digital Product Passport", page_icon="♻️", layout="centered")


# ---------------------------------------------------------------------
# 2. LOAD THE DATA
# ---------------------------------------------------------------------
def load_devices():
    """Read devices.csv into a table. The id column is kept as text."""
    df = pd.read_csv("devices.csv", dtype={"id": str})
    df["id"] = df["id"].str.strip()
    return df


# ---------------------------------------------------------------------
# 3. HELPER FUNCTIONS
# ---------------------------------------------------------------------
def recommend(row):
    """Repair / Reuse / Recycle decision (same logic as the decision-tree slide)."""
    age = date.today().year - int(row["year"])
    condition = str(row["condition"]).strip().lower()

    if row["status"] == "Recycled":
        return "RECYCLED", "success", "This device has completed its journey. Its materials are back in use."
    if condition == "working":
        if age > 5:
            return "REUSE - Donate or sell", "info", f"It still works but is {age} years old. Give it a second life with someone who needs it."
        return "REUSE - Keep using", "success", f"It works and is only {age} years old. The greenest device is the one you already own."
    if condition == "repairable":
        return "REPAIR", "warning", "The fault can be fixed. Repairing it saves the materials and energy needed to make a new one."
    return "RECYCLE", "error", "It cannot be repaired. Send it to an authorised recycler so its metals can be recovered safely."


def material_values(row, prices):
    """Return a table of each metal: amount in grams and estimated value in Rupees."""
    grams = {
        "Gold": row["gold_mg"] / 1000,
        "Silver": row["silver_g"],
        "Palladium": row["palladium_mg"] / 1000,
        "Copper": row["copper_g"],
        "Cobalt": row["cobalt_g"],
        "Lithium": row["lithium_g"],
        "Aluminium": row["aluminium_g"],
    }
    table = pd.DataFrame({"Material": list(grams.keys()), "Amount (g)": list(grams.values())})
    table["Price (Rs/g)"] = [prices[m.lower()] for m in table["Material"]]
    table["Value (Rs)"] = table["Amount (g)"] * table["Price (Rs/g)"]
    return table


def make_qr_png(url):
    """Turn a link into a QR code image (PNG bytes)."""
    img = qrcode.make(url, box_size=10, border=2)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def passport_link(device_id):
    return f"{APP_URL}/?id={device_id}"


def show_message(kind, text):
    {"success": st.success, "info": st.info, "warning": st.warning, "error": st.error}[kind](text)


def go_to(device_id=None):
    """Switch between the home page and a passport page."""
    st.query_params.clear()
    if device_id:
        st.query_params["id"] = device_id


# ---------------------------------------------------------------------
# 4. LIVE METAL PRICES + SIDEBAR
# ---------------------------------------------------------------------
@st.cache_data(ttl=3 * 60 * 60, show_spinner=False)
def usd_to_inr_rate():
    """Backup only: USD -> INR exchange rate (updates once a day)."""
    data = requests.get("https://open.er-api.com/v6/latest/USD", timeout=8).json()
    return float(data["rates"]["INR"])


def fetch_one_price(symbol):
    """Price of one metal in Rupees per gram, from Gold-API."""
    data = requests.get(f"https://api.gold-api.com/price/{symbol}/INR", timeout=8).json()
    price = float(data["price"])
    if data.get("currency") != "INR":          # service sent USD instead -> convert
        price = price * usd_to_inr_rate()
    grams = GRAMS_PER_POUND if symbol == "HG" else GRAMS_PER_TROY_OUNCE
    return price / grams, data.get("updatedAt")


@st.cache_data(ttl=PRICE_REFRESH_SECONDS, show_spinner="Fetching live metal prices...")
def fetch_live_prices():
    """Try to get live prices for every metal in LIVE_SYMBOLS.
    Returns (prices, last_updated_time, list_of_metals_that_failed)."""
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
    """'2026-10-25T09:30:00Z' -> '25 Oct 2026, 3:00 PM IST'"""
    try:
        t = datetime.fromisoformat(iso_time.replace("Z", "+00:00"))
        t = t.astimezone(timezone(timedelta(hours=5, minutes=30)))
        return t.strftime("%d %b %Y, %I:%M %p IST")
    except Exception:
        return "unknown time"


def price_sidebar():
    """Shows prices in the sidebar. Returns (prices, sources) for all metals."""
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
def home_page(df, prices):
    st.title("♻️ Digital Product Passport")
    st.subheader("Scan it. Know it. Repair, Reuse or Recycle it.")
    st.write(
        "Every device below has its own passport page showing what it is made of, "
        "how to repair it, and how to recycle it safely. Scan the QR sticker on a device, "
        "or open its passport here."
    )

    # Totals across all devices
    total_value = sum(material_values(r, prices)["Value (Rs)"].sum() for _, r in df.iterrows())
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Devices", len(df))
    c2.metric("Gold inside", f"{df['gold_mg'].sum():.0f} mg")
    c3.metric("Copper inside", f"{df['copper_g'].sum():.0f} g")
    c4.metric("Metal value", f"Rs {total_value:,.0f}")
    st.caption("Metal value uses live market prices for gold, silver, palladium and copper (see sidebar).")

    st.divider()
    search = st.text_input("🔍 Search devices", placeholder="Type a name, brand or category")
    if search:
        text = search.lower()
        df = df[df.apply(lambda r: text in f"{r['device']} {r['brand']} {r['category']}".lower(), axis=1)]

    for _, row in df.iterrows():
        label, kind, _ = recommend(row)
        with st.container(border=True):
            left, right = st.columns([3, 1])
            left.markdown(f"**{row['device']}**  \n{row['category']} · {row['year']} · ID {row['id']}")
            left.caption(f"Status: {row['status']}  |  Advice: {label}")
            right.button("Open passport", key=row["id"], on_click=go_to, args=(row["id"],), width="stretch")

    if df.empty:
        st.info("No devices match your search.")

    st.caption("Material amounts are estimates based on published averages and device specifications.")


# ---------------------------------------------------------------------
# 6. PASSPORT PAGE (one device)
# ---------------------------------------------------------------------
def passport_page(row, prices, sources):
    st.button("← All devices", on_click=go_to)

    st.title(f"♻️ {row['device']}")
    st.caption(f"Passport ID: {row['id']}  ·  {row['brand']}  ·  {row['category']}  ·  Made in {row['year']}")

    # Recommendation
    label, kind, reason = recommend(row)
    show_message(kind, f"**Recommendation: {label}**  \n{reason}")

    # Key numbers
    values = material_values(row, prices)
    c1, c2, c3 = st.columns(3)
    c1.metric("Weight", f"{row['weight_g']} g")
    c2.metric("Age", f"{date.today().year - int(row['year'])} years")
    c3.metric("Metal value", f"Rs {values['Value (Rs)'].sum():,.0f}")

    # Life-cycle status
    st.subheader("📍 Life-cycle status")
    step = STATUS_STEPS.index(row["status"]) if row["status"] in STATUS_STEPS else 0
    st.progress((step + 1) / len(STATUS_STEPS))
    st.write("  →  ".join(f"**{s}**" if i == step else s for i, s in enumerate(STATUS_STEPS)))

    # Materials
    st.subheader("🧪 What's inside")
    chart = pd.DataFrame(
        {"grams": [row["aluminium_g"], row["plastic_g"], row["glass_g"], row["copper_g"], row["cobalt_g"]]},
        index=["Aluminium", "Plastic", "Glass", "Copper", "Cobalt"],
    )
    st.bar_chart(chart, horizontal=True)
    show = values.copy()
    show["Amount"] = [
        f"{row['gold_mg']} mg", f"{row['silver_g']} g", f"{row['palladium_mg']} mg", f"{row['copper_g']} g",
        f"{row['cobalt_g']} g", f"{row['lithium_g']} g", f"{row['aluminium_g']} g",
    ]
    show["Price (Rs/g)"] = [f"{prices[m.lower()]:,.2f} ({sources[m.lower()]})" for m in show["Material"]]
    show["Value (Rs)"] = show["Value (Rs)"].map(lambda v: f"{v:,.2f}")
    st.dataframe(show[["Material", "Amount", "Price (Rs/g)", "Value (Rs)"]], hide_index=True, width="stretch")
    st.caption(f"Also contains about {row['plastic_g']} g of plastic and {row['glass_g']} g of glass. "
               "Amounts are estimates; values use live market prices where available.")

    # Repair tips and hazards
    st.subheader("🔧 Repair tips")
    for tip in str(row["repair_tips"]).split(";"):
        st.markdown(f"- {tip.strip()}")

    st.subheader("⚠️ Hazards - handle with care")
    for hazard in str(row["hazards"]).split(";"):
        st.markdown(f"- {hazard.strip()}")

    st.subheader("🚚 How to recycle")
    st.write(row["recycler"])
    st.write("Never throw e-waste in the dustbin or burn it.")

    # QR code for this passport
    st.subheader("🔳 QR code for this device")
    link = passport_link(row["id"])
    st.image(make_qr_png(link), width=220)
    st.code(link, language=None)
    st.download_button("Download QR code", make_qr_png(link), file_name=f"{row['id']}.png", mime="image/png")
    if "your-app-name" in APP_URL:
        st.warning("APP_URL in app.py is still the placeholder. Update it after deploying, or this QR code will not open.")


# ---------------------------------------------------------------------
# 7. MAIN - decide which page to show
# ---------------------------------------------------------------------
devices = load_devices()
prices, sources = price_sidebar()
item_id = st.query_params.get("id")

if item_id:
    match = devices[devices["id"] == item_id.strip()]
    if match.empty:
        st.error(f"No device found with ID '{item_id}'.")
        st.button("← All devices", on_click=go_to)
    else:
        passport_page(match.iloc[0], prices, sources)
else:
    home_page(devices, prices)
