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
import streamlit.components.v1 as components

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


# Website text in English, Hindi and Kannada (translations.json)
with open("translations.json", encoding="utf-8") as _f:
    TEXT = json.load(_f)
LANGS = TEXT["languages"]          # {"en": "English", "hi": "हिंदी", "kn": "ಕನ್ನಡ"}


def current_lang():
    lang = st.query_params.get("lang", "en")
    return lang if lang in LANGS else "en"


def ui(key):
    """Website text in the chosen language (falls back to English)."""
    return TEXT[current_lang()].get(key, TEXT["en"][key])


def localize(d):
    """Copy of the device with its text swapped for the chosen language (numbers and scores stay the same)."""
    import copy
    lang = current_lang()
    tr = d.get("translations", {}).get(lang)
    out = copy.deepcopy(d)
    for i, sec in enumerate(out["sections"]):
        sec["anchor"] = slug(d["sections"][i]["title"])      # link targets always from the English title
    if not tr:
        return out
    if tr.get("model"):
        out["model"] = tr["model"]
    for sec, t in zip(out["sections"], tr.get("sections", [])):
        for key in ("title", "subtitle", "intro", "note", "table"):
            if key in t:
                sec[key] = t[key]
        if "hazard_meter" in sec and "hazard_meter" in t:
            sec["hazard_meter"]["note"] = t["hazard_meter"].get("note", sec["hazard_meter"]["note"])
            for item, ti in zip(sec["hazard_meter"]["items"], t["hazard_meter"].get("items", [])):
                item["name"], item["reason"] = ti.get("name", item["name"]), ti.get("reason", item["reason"])
    return out


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
        return ui("rec_recycled"), "success", ui("rec_recycled_why")
    if condition == "working":
        if age > 5:
            return ui("rec_donate"), "info", ui("rec_donate_why").format(age=age)
        return ui("rec_keep"), "success", ui("rec_keep_why").format(age=age)
    if condition == "repairable":
        return ui("rec_repair"), "warning", ui("rec_repair_why")
    return ui("rec_recycle"), "error", ui("rec_recycle_why")


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
        src = ui("src_" + sources[key])
        rows.append((ui("metals")[key], text, f"{prices[key]:,.2f} ({src})", g * prices[key]))
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
    lang = current_lang()
    st.query_params.clear()
    st.query_params["lang"] = lang
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
    names = ui("metals")
    st.sidebar.header(ui("prices_header"))
    st.sidebar.subheader(ui("live_header"))
    for metal in LIVE_SYMBOLS:
        if metal in live:
            prices[metal], sources[metal] = live[metal], "live"
            st.sidebar.metric(names[metal], f"Rs {live[metal]:,.2f}")
        else:
            prices[metal], sources[metal] = FALLBACK_PRICES[metal], "backup"
            st.sidebar.metric(names[metal], f"Rs {FALLBACK_PRICES[metal]:,.2f}", ui("backup_price"), delta_color="off")
    if updated:
        st.sidebar.caption(ui("updated").format(time=to_ist(updated)))
    if failed:
        st.sidebar.warning(ui("unavailable").format(metals=", ".join(names[m] for m in failed)))
    if st.sidebar.button(ui("refresh")):
        fetch_live_prices.clear()
        st.rerun()
    st.sidebar.subheader(ui("ref_header"))
    st.sidebar.caption(ui("ref_caption"))
    for metal, value in REFERENCE_PRICES.items():
        prices[metal] = st.sidebar.number_input(names[metal], min_value=0.0, value=value, step=0.25, key="ref_" + metal)
        sources[metal] = "reference"
    return prices, sources


# ---------------------------------------------------------------------
# 5. HOME PAGE  (and the green banner shown at the top of every page)
# ---------------------------------------------------------------------
BANNER_HTML = """
<style>
.dpp-banner { background: linear-gradient(135deg, #3fa34d 0%, #2e8b57 100%);
              border-radius: 14px; padding: 22px 20px; margin: 0 0 22px 0;
              display: flex; justify-content: center; }
.dpp-badge  { background: #ffffff; border-radius: 60px; padding: 14px 30px;
              display: flex; align-items: center; gap: 16px;
              box-shadow: 0 4px 14px rgba(0,0,0,0.15); max-width: 100%; }
.dpp-logo   { font-size: 3rem; line-height: 1; flex-shrink: 0; }
.dpp-name   { font-size: 1.9rem; font-weight: 800; color: #1f7a3f; line-height: 1.1; }
.dpp-tag    { font-size: 0.95rem; font-style: italic; color: #333333; margin-top: 4px; }
@media (max-width: 600px) {
  .dpp-badge { padding: 10px 18px; gap: 10px; border-radius: 40px; }
  .dpp-logo  { font-size: 2.2rem; }
  .dpp-name  { font-size: 1.3rem; }
  .dpp-tag   { font-size: 0.8rem; }
}
</style>
<div class="dpp-banner">
  <div class="dpp-badge">
    <div class="dpp-logo">♻️</div>
    <div>
      <div class="dpp-name">__NAME__</div>
      <div class="dpp-tag">__TAG__</div>
    </div>
  </div>
</div>
"""


def show_banner():
    st.markdown(BANNER_HTML.replace("__NAME__", ui("banner_name")).replace("__TAG__", ui("banner_tag")),
                unsafe_allow_html=True)


def home_page(devices):
    show_banner()
    st.write(ui("home_intro"))
    for d in devices:
        d = localize(d)
        label, _, _ = recommend(d)
        with st.container(border=True):
            left, right = st.columns([1, 2])
            left.image(d["image"], width="stretch")
            right.markdown(f"**{d['device']}**  \n{d['model']} · {d['year']} · ID {d['id']}")
            right.caption(f"{ui('status')}: {status_label(d['status'])}  |  {ui('advice')}: {label}")
            right.button(ui("open_passport"), key=d["id"], on_click=go_to, args=(d["id"],), width="stretch")


# ---------------------------------------------------------------------
# 6. PASSPORT PAGE
# ---------------------------------------------------------------------
def slug(title):
    """'1. Identity and Specifications' -> 'identity-and-specifications' (used as the link target)."""
    words = "".join(ch.lower() if ch.isalnum() else " " for ch in title).split()
    words = [w for w in words if not w.isdigit()]       # drop the section number
    return "-".join(words) or "section"


TOC_STYLE = """
<style>
.dpp-toc { border: 1px solid #d0d7de; background: #f6f8fa; border-radius: 8px;
           padding: 12px 18px; margin: 8px 0 24px 0; }
.dpp-toc summary { font-weight: 700; font-size: 1.1rem; cursor: pointer; color: #1f2328; }
.dpp-toc summary .toggle { font-weight: 400; font-size: 0.85rem; color: #1b7f5a; margin-left: 8px; }
.dpp-toc ul { margin: 10px 0 0 0; padding-left: 20px; }
.dpp-toc li { margin: 4px 0; }
.dpp-toc a { color: #1b7f5a; text-decoration: none; }
.dpp-toc a:hover { text-decoration: underline; }
.dpp-toc a.clicked, .dpp-toc a:visited { color: #8c8c8c; }   /* clicked headings turn grey */
h1[id], h2[id], h3[id] { scroll-margin-top: 70px; }  /* stop the top bar hiding the heading */
section.main, [data-testid="stMain"] { scroll-behavior: smooth; }
</style>
"""


def hazard_meter(meter):
    """Speedtest-style Hazard-o-meter (hazardometer.html), filled with this device's scores."""
    with open("hazardometer.html", encoding="utf-8") as f:
        html = f.read().replace("__DATA__", json.dumps({**meter, "ui": ui("meter")}, ensure_ascii=False))
    components.html(html, height=720)


def table_of_contents(d):
    """Collapsible table of contents. Clicking an entry scrolls to it; visited entries go grey."""
    items = [(sec["title"], sec["anchor"]) for sec in d["sections"]]
    items += [(ui("sources"), "sources"), (ui("qr_title"), "qr-code")]
    links = "".join(f'<li><a href="#{anchor}" target="_self">{title}</a></li>' for title, anchor in items)
    st.markdown(
        TOC_STYLE
        + f'<details class="dpp-toc" open><summary>{ui("toc")}<span class="toggle">{ui("toggle")}</span></summary>'
        + f"<ul>{links}</ul></details>",
        unsafe_allow_html=True,
    )
    # Small script: marks a clicked entry grey and remembers it (per device) in this browser
    components.html(TOC_SCRIPT.replace("DEVICE_ID", d["id"]), height=0)


TOC_SCRIPT = """
<script>
(function () {
  const doc = window.parent.document;
  const key = "dpp-toc-clicked-DEVICE_ID";
  let saved = [];
  try { saved = JSON.parse(window.parent.localStorage.getItem(key) || "[]"); } catch (e) {}
  function mark() {
    doc.querySelectorAll(".dpp-toc a").forEach(function (a) {
      const target = a.getAttribute("href");
      if (saved.includes(target)) a.classList.add("clicked");
      if (!a.dataset.bound) {
        a.dataset.bound = "1";
        a.addEventListener("click", function () {
          a.classList.add("clicked");
          if (!saved.includes(target)) saved.push(target);
          try { window.parent.localStorage.setItem(key, JSON.stringify(saved)); } catch (e) {}
        });
      }
    });
  }
  mark();
  new MutationObserver(mark).observe(doc.body, { childList: true, subtree: true });
})();
</script>
"""


def status_label(status):
    """Translated name of a life-cycle stage (the data always stores the English name)."""
    return ui("status_steps")[STATUS_STEPS.index(status)] if status in STATUS_STEPS else status


def passport_page(d, prices, sources):
    d = localize(d)
    show_banner()
    st.button(ui("home"), on_click=go_to)

    # Header: photo, name, author
    # Top of the page: photo and name on the left, Hazard-o-meter on the right
    meter = next((sec["hazard_meter"] for sec in d["sections"] if sec.get("hazard_meter")), None)
    left, right = st.columns([1, 2], gap="small") if meter else (st.container(), None)
    with left:
        st.image(d["image"], width=260)
        st.title(d["device"])
        st.subheader(d["model"])
        st.caption(d["author"])
    if meter:
        with right:
            hazard_meter(meter)

    # Recommendation and key numbers
    label, kind, reason = recommend(d)
    show_message(kind, f"**{ui('recommendation')}: {label}**  \n{reason}")
    rows = metal_value_rows(d, prices, sources)
    c1, c2, c3 = st.columns(3)
    c1.metric(ui("weight"), f"{d['weight_g'] / 1000:.1f} kg")
    c2.metric(ui("age"), f"{date.today().year - int(d['year'])} {ui('years')}")
    c3.metric(ui("metal_value"), f"Rs {sum(r[3] for r in rows):,.0f}")

    st.markdown(f"**{ui('lifecycle')}**")
    step = STATUS_STEPS.index(d["status"]) if d["status"] in STATUS_STEPS else 0
    st.progress((step + 1) / len(STATUS_STEPS))
    st.write("  →  ".join(f"**{s}**" if i == step else s for i, s in enumerate(ui("status_steps"))))
    st.divider()

    # Table of contents: built from this device's sections, so every device gets one
    table_of_contents(d)

    # All sections from the Word document, in the same order
    for sec in d["sections"]:
        st.header(sec["title"], anchor=sec["anchor"])
        if sec.get("subtitle"):
            st.subheader(sec["subtitle"])
        if sec.get("intro"):
            st.markdown(sec["intro"])
        st.markdown(md_table(sec["table"]))
        if sec.get("note"):
            st.markdown(sec["note"])
        if sec.get("show_live_value"):
            st.markdown(ui("live_value_title"))
            st.markdown(md_table({
                "columns": [ui("col_metal"), ui("col_amount"), ui("col_price"), ui("col_value")],
                "rows": [[m, a, p, f"{v:,.2f}"] for m, a, p, v in rows]
                        + [[f"**{ui('total')}**", "", "", f"**{sum(r[3] for r in rows):,.2f}**"]],
            }))
            st.caption(ui("live_caption"))

    # Sources
    st.header(ui("sources"), anchor="sources")
    st.markdown("\n".join(f"{i}. {text} [{url}]({url})" for i, (text, url) in enumerate(d["sources"], 1)))

    # QR code
    st.divider()
    st.subheader("🔳 " + ui("qr_title"), anchor="qr-code")
    link = passport_link(d["id"])
    st.image(make_qr_png(link), width=220)
    st.code(link, language=None)
    st.download_button(ui("download_qr"), make_qr_png(link), file_name=f"{d['id']}.png", mime="image/png")
    if "your-app-name" in APP_URL:
        st.warning("APP_URL in app.py is still the placeholder. Update it after deploying, or this QR code will not open.")


# ---------------------------------------------------------------------
# 7. LANGUAGE CHOICE  (popup on first visit + switcher in the sidebar)
# ---------------------------------------------------------------------
POPUP_HTML = """
<style>
/* page behind the popup: blurred and dimmed until a language is chosen */
div[data-testid="stDialog"] { backdrop-filter: blur(7px); -webkit-backdrop-filter: blur(7px);
                              background-color: rgba(15, 23, 42, 0.45) !important; }
/* the popup box itself */
div[data-testid="stDialog"] > div {
  background: linear-gradient(160deg, #f0fdf4 0%, #ecfeff 45%, #fdf4ff 100%) !important;
  border-radius: 22px !important; border: 3px solid transparent;
  box-shadow: 0 20px 60px rgba(0,0,0,.35), 0 0 0 3px rgba(34,197,94,.35); }
.lang-head { display:flex; align-items:center; justify-content:center; gap:14px; text-align:center;
             background: linear-gradient(120deg, #2dd4bf 0%, #0ea5e9 35%, #0284c7 50%, #0ea5e9 65%, #2dd4bf 100%);
             border-radius: 16px; padding: 16px 18px; margin: -8px 0 16px; color:#000000;
             box-shadow: 0 8px 22px rgba(14,165,233,.45); }
.lang-head .logo { font-size:2.6rem; line-height:1; filter: drop-shadow(0 2px 4px rgba(0,0,0,.25)); }
.lang-head .l1 { font-size:1.55rem; font-weight:900; line-height:1.35; color:#000000; }
.lang-head .l2 { font-size:1.2rem; font-weight:900; letter-spacing:4px; margin-top:2px; color:#000000; }
.lang-title { text-align:center; font-size:1.7rem; font-weight:900; margin:6px 0 18px; color:#94a3b8; }
.lang-title .t { -webkit-background-clip:text; background-clip:text; color:transparent; }
.lang-title .t.hi { background-image: linear-gradient(135deg, #22c55e 0%, #16a34a 50%, #047857 100%); }
.lang-title .t.en { background-image: linear-gradient(135deg, #4f46e5 0%, #7c3aed 50%, #06b6d4 100%); }
.lang-title .t.kn { background-image: linear-gradient(135deg, #eab308 0%, #f97316 45%, #dc2626 100%); }
.lang-cards { display:grid; grid-template-columns:repeat(3, 1fr); gap:16px; margin-bottom:10px; }
.lang-card { position:relative; overflow:hidden; display:flex; flex-direction:column; align-items:center;
             justify-content:center; gap:4px; min-height:130px; padding:16px; border-radius:18px;
             text-decoration:none !important; color:#fff !important;
             box-shadow:0 8px 20px rgba(0,0,0,.18); transition: transform .18s, box-shadow .18s; }
.lang-card:hover { transform: translateY(-5px) scale(1.03); box-shadow:0 14px 30px rgba(0,0,0,.28); }
.lang-card .big { position:absolute; right:10px; bottom:-18px; font-size:6rem; font-weight:900;
                  opacity:.18; line-height:1; pointer-events:none; }
.lang-card .n { position:relative; font-size:1.9rem; font-weight:800; text-shadow:0 2px 4px rgba(0,0,0,.25); }
.lang-card .w { position:relative; font-size:1.05rem; font-weight:600; opacity:.95;
                background: rgba(255,255,255,.22); padding:2px 12px; border-radius:20px; }
.lang-card.hi { background: linear-gradient(135deg, #22c55e 0%, #16a34a 50%, #047857 100%); }
.lang-card.en { background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 50%, #06b6d4 100%);
                box-shadow:0 0 0 4px #fde047, 0 10px 26px rgba(79,70,229,.45); }
.lang-card.kn { background: linear-gradient(135deg, #facc15 0%, #f97316 45%, #dc2626 100%); }
.lang-card::after { content:""; position:absolute; top:0; left:-60%; width:40%; height:100%;
                    background: linear-gradient(100deg, transparent, rgba(255,255,255,.45), transparent);
                    transform: skewX(-20deg); animation: shine 3.2s ease-in-out infinite; }
.lang-card.en::after { animation-delay: .4s; } .lang-card.kn::after { animation-delay: .8s; }
@keyframes shine { 0% { left:-60%; } 55%, 100% { left:130%; } }
@media (max-width:600px) {
  .lang-cards { grid-template-columns:1fr; } .lang-card { min-height:88px; }
  .lang-head { flex-direction:column; gap:4px; } .lang-head .l1 { font-size:1.15rem; }
  .lang-head .l2 { font-size:1rem; letter-spacing:3px; } .lang-title { font-size:1.35rem; }
  .lang-card .big { font-size:4.5rem; }
}
</style>
<div class="lang-head">
  <div class="logo">♻️</div>
  <div>
    <div class="l1">डिजिटल उत्पाद पासपोर्ट &nbsp;·&nbsp; ಡಿಜಿಟಲ್ ಉತ್ಪನ್ನ ಪಾಸ್‌ಪೋರ್ಟ್</div>
    <div class="l2">DIGITAL PRODUCT PASSPORT</div>
  </div>
</div>
<div class="lang-title"><span class="t hi">भाषा चुनें</span> / <span class="t en">Choose Language</span> / <span class="t kn">ಭಾಷೆ ಆಯ್ಕೆಮಾಡಿ</span></div>
<div class="lang-cards">__CARDS__</div>
"""
LANG_CARDS = [("hi", "हिंदी", "स्वागत है", "अ"), ("en", "English", "Welcome", "A"), ("kn", "ಕನ್ನಡ", "ಸ್ವಾಗತ", "ಅ")]


@st.dialog(" ", width="large")
def language_popup():
    """Three language cards. Each is a link that reopens the same page with ?lang=... added."""
    device_id = st.query_params.get("id")
    cards = ""
    for code, name, welcome, letter in LANG_CARDS:
        href = f"?id={device_id}&lang={code}" if device_id else f"?lang={code}"
        cards += (f'<a class="lang-card {code}" href="{href}" target="_self">'
                  f'<span class="big">{letter}</span>'
                  f'<span class="n">{name}</span><span class="w">{welcome}</span></a>')
    st.markdown(POPUP_HTML.replace("__CARDS__", cards), unsafe_allow_html=True)


def language_switcher():
    codes = list(LANGS)
    st.session_state["lang_select"] = current_lang()      # keep the box in step with the link
    st.sidebar.selectbox(ui("language"), codes, format_func=lambda c: LANGS[c],
                         key="lang_select", on_change=switch_language)


def switch_language():
    st.query_params["lang"] = st.session_state["lang_select"]


# ---------------------------------------------------------------------
# 8. MAIN - decide which page to show
# ---------------------------------------------------------------------
devices = load_devices()

# First visit (no language in the link yet): ask, like the ISRO website does
if "lang" not in st.query_params and not st.session_state.get("lang_asked"):
    st.session_state["lang_asked"] = True
    language_popup()

language_switcher()
prices, sources = price_sidebar()
item_id = st.query_params.get("id")

if item_id:
    device = find_device(devices, item_id)
    if device is None:
        st.error(ui("not_found").format(id=item_id))
        st.button(ui("home"), on_click=go_to)
    else:
        passport_page(device, prices, sources)
else:
    home_page(devices)
