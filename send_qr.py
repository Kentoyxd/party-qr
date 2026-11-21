#!/usr/bin/env python3
"""
Acquaintance Party (CETA-CHELLA) - Ticket QR generator + sender.

1. Reads the MASTER LIST from your Google Sheet or Excel file (everyone is confirmed).
2. Builds a reusable blank CETA-CHELLA ticket template (ticket_template.png) with NO white boxes.
3. Makes TWO separate ticket PNGs per attendee:
   - out/qr/<Name>.png           (ATTENDANCE ticket)
   - out/qr_food/<Name>_FOOD.png (FOOD TICKET - 1 meal)
4. Writes attendees.js so the scanner page knows who is allowed in and which codes are valid.
5. Emails BOTH separate tickets inside the SAME email (only with --send).
"""
import argparse, base64, csv, hashlib, hmac, html, io, json, math, os, re, secrets, smtplib, ssl, sys, time, unicodedata
import urllib.error, urllib.request
from email.message import EmailMessage
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFilter, ImageFont

PARTY_NAME = "CETA-CHELLA Acquaintance Party"
OUT_DIR = Path("out/qr")              # entry ticket images
FOOD_DIR = Path("out/qr_food")        # food ticket images
SENT_LOG = Path("out/sent_log.csv")
SENT_FOOD_LOG = Path("out/sent_food_log.csv")  # used by --food-only
SECRET_FILE = Path("secret.key")
ATTENDEES_JS = Path("attendees.js")
TEMPLATE_FILE = Path("ticket_template.png")
POSTER_FILE = Path("CETA TARP & LED.jpg")

# ---------- reading the sheet ----------
def is_email_header(h: str) -> bool:
    return "MAIL" in h or "OUTLOOK" in h or "EMAIL" in h

def read_xlsx(src):
    try:
        import openpyxl
    except ImportError:
        sys.exit("Missing package. Run:  pip install -r requirements.txt")
    wb = openpyxl.load_workbook(src, data_only=True, read_only=True)
    out = []
    for ws in wb.worksheets:
        rows = [["" if v is None else str(v).strip() for v in r] for r in ws.iter_rows(values_only=True)]
        out.append((ws.title, rows))
    return out

def load_sheets(src: str):
    """Returns [(tab_name, rows)] from a Google Sheets link, a local .xlsx, or a local .csv."""
    m = re.search(r"/spreadsheets/d/([\w-]+)", src)
    if m:
        url = f"https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=xlsx"
        try:
            with urllib.request.urlopen(url) as r:
                data = r.read()
        except Exception as e:
            sys.exit(f"Could not download the sheet ({e}).\nShare it as 'Anyone with the link: Viewer' and try again.")
        if data[:2] != b"PK":
            sys.exit("Google did not return the spreadsheet. Share it as 'Anyone with the link: Viewer' and try again.")
        return read_xlsx(io.BytesIO(data))
    p = Path(src)
    if p.suffix.lower() in (".xlsx", ".xlsm"):
        return read_xlsx(p)
    return [(p.stem, list(csv.reader(io.StringIO(p.read_text(encoding="utf-8-sig")))))]

def parse_tab(tab, rows):
    """Returns (paid_people, unpaid_names). Bypasses payment checks; everyone is confirmed."""
    hdr_i, cols = None, {}
    for i, row in enumerate(rows):
        up = [c.strip().upper() for c in row]
        name_h = next((h for h in ("NAME", "NAMES") if h in up), None)
        if name_h:
            hdr_i = i
            cols = {c: up.index(c) for c in up if c}
            cols["NAME"] = up.index(name_h)
            break
    if hdr_i is None:
        return None

    email_hdr = next((h for h in cols if is_email_header(h)), None)

    def cell(row, key):
        j = cols.get(key)
        return row[j].strip() if j is not None and j < len(row) else ""

    people, unpaid, blanks = [], [], 0
    for row in rows[hdr_i + 1:]:
        name = cell(row, "NAME")
        if not name:
            blanks += 1
            if blanks >= 3 and people:
                break
            continue
        blanks = 0
        
        # Clean up department spacing (e.g., "BS ARCH" -> "BSARCH")
        dept_raw = cell(row, "DEPARTMENT") or tab
        dept_clean = re.sub(r"\s+", "", dept_raw).upper()
        
        # Everyone is added directly; no payment checks
        people.append({"name": name, "dept": dept_clean,
                       "email": cell(row, email_hdr) if email_hdr else ""})
                       
    print(f"  {tab}: {len(people)} attendees found (All confirmed), "
          f"{sum(1 for p in people if not p['email'])} without email.")
    return people, unpaid

def parse_attendees(src: str):
    people, seen, all_unpaid = [], {}, []
    print("Tabs found:")
    for tab, rows in load_sheets(src):
        if re.search(r"total|master|summary", tab, re.I):
            print(f"  {tab}: (summary tab, skipped)")
            continue
        res = parse_tab(tab, rows)
        if res is None:
            print(f"  {tab}: (no attendee table, skipped)")
            continue
        paid, unpaid = res
        all_unpaid += unpaid
        for p in paid:
            key = norm(p["name"])
            if key in seen:
                first = seen[key]
                if p["email"] and not first["email"]:
                    first["email"] = p["email"]
                    print(f"  (email for {p['name']} taken from tab {tab})")
                continue
            seen[key] = p
            people.append(p)
    if not people:
        sys.exit("No attendees found. Check that each tab has a header row with NAMES.")
    return people

def norm(s: str) -> str:
    """Same rule as the web page: lowercase, letters only, words sorted (so 'Last, First' == 'First Last')."""
    s = unicodedata.normalize("NFC", s).lower()
    s = re.sub(r"[^\w\s]|_", " ", s)
    return " ".join(sorted(s.split()))

def get_secret() -> bytes:
    """Private key that makes every guest's code. Created once, kept in secret.key (never upload it)."""
    if not SECRET_FILE.exists():
        SECRET_FILE.write_text(secrets.token_hex(32))
        print("Created secret.key. Keep it private and do not delete it, or every QR code changes.")
    return SECRET_FILE.read_text().strip().encode()

def code_for(name: str, kind: str = "entry") -> str:
    msg = norm(name) if kind == "entry" else f"food:{norm(name)}"
    digest = hmac.new(get_secret(), msg.encode(), hashlib.sha256).digest()
    return base64.b32encode(digest).decode()[:12]

def hash_for(name: str, code: str) -> str:
    return hashlib.sha256(f"{norm(name)}:{code}".encode()).hexdigest()

def merge_emails(people, path):
    lookup = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            r = {k.strip().lower(): (v or "").strip() for k, v in r.items() if k}
            if r.get("name") and r.get("email"):
                lookup[norm(r["name"])] = r["email"]
    for p in people:
        p["email"] = lookup.get(norm(p["name"]), p["email"])


# ---------- CETA-CHELLA Ticket Template & Transparent QR Stamp ----------
def slug(name):
    return re.sub(r"[^A-Za-z0-9]+", "_", unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()).strip("_") or "attendee"

def load_font(size: int, bold: bool = False, serif: bool = False):
    """Loads a clean system font on Windows/Mac/Linux with a safe Pillow fallback."""
    if serif:
        candidates = ["georgia.ttf", "times.ttf", "DejaVuSerif.ttf"]
    elif bold:
        candidates = ["arialbd.ttf", "segoeuib.ttf", "calibrib.ttf", "trebucbd.ttf", "DejaVuSans-Bold.ttf"]
    else:
        candidates = ["arial.ttf", "segoeui.ttf", "calibri.ttf", "DejaVuSans.ttf"]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()

def draw_four_petal_star(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int = 16, color=(234, 195, 232, 255)):
    """Draws the 4-petal corner flower icon in soft pink-lavender (no harsh white)."""
    for dx, dy in [(-1, -1), (1, -1), (-1, 1), (1, 1)]:
        px, py = cx + dx * int(r * 0.55), cy + dy * int(r * 0.55)
        draw.ellipse((px - r // 2, py - r // 2, px + r // 2, py + r // 2), fill=color)

def build_ticket_template(force: bool = False) -> Path:
    """Creates ticket_template.png (1060x350 RGBA) with transparent edges and NO white boxes."""
    if TEMPLATE_FILE.exists() and not force:
        return TEMPLATE_FILE

    W, H = 1060, 350
    stub_x = 690

    # 1. Create pink tropical base texture
    base = Image.new("RGB", (W, H), (235, 162, 226))
    bd = ImageDraw.Draw(base)
    for y in range(H):
        t = y / max(H - 1, 1)
        r = int(240 * (1 - t) + 216 * t)
        g = int(172 * (1 - t) + 128 * t)
        b = int(232 * (1 - t) + 208 * t)
        bd.line([(0, y), (W, y)], fill=(r, g, b))

    # If CETA TARP & LED.jpg exists, blend a soft crop of the pink ticket texture onto the left side
    if POSTER_FILE.exists():
        try:
            poster = Image.open(POSTER_FILE).convert("RGB")
            pw, ph = poster.size
            crop = poster.crop((int(pw * 0.28), int(ph * 0.28), int(pw * 0.65), int(ph * 0.58)))
            crop = crop.resize((W, H)).filter(ImageFilter.GaussianBlur(radius=14))
            base = Image.blend(base, crop, alpha=0.30)
        except Exception:
            pass

    # Subtle diagonal sunbeams & palm silhouettes (kept on left side so QR stub stays clean pink)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.polygon([(0, 35), (W, 120), (W, 175), (0, 85)], fill=(248, 205, 242, 40))
    od.polygon([(0, 195), (W, 265), (W, 310), (0, 240)], fill=(248, 205, 242, 35))
    for px, py in [(160, 35), (330, 60), (500, 85)]:
        for angle in range(-65, 75, 28):
            rad = math.radians(angle)
            ex = px + int(math.cos(rad) * 90)
            ey = py + int(math.sin(rad) * 52)
            od.line([(px, py), (ex, ey)], fill=(175, 85, 160, 55), width=8)
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=3))
    canvas = Image.alpha_composite(base.convert("RGBA"), overlay)

    draw = ImageDraw.Draw(canvas)

    # Dashed perforation line separating main ticket and QR stub
    for dy in range(28, H - 24, 14):
        draw.line([(stub_x, dy), (stub_x, dy + 7)], fill=(185, 105, 178, 255), width=3)

    # 4 corner floral icons on the left body
    draw_four_petal_star(draw, 44, 42, r=16)
    draw_four_petal_star(draw, stub_x - 44, 42, r=16)
    draw_four_petal_star(draw, 44, H - 42, r=16)
    draw_four_petal_star(draw, stub_x - 44, H - 42, r=16)

    # Main Title: CETA-CHELLA
    cx = stub_x // 2
    title_font = load_font(72, bold=True)
    sub_font = load_font(22, serif=True)
    date_font = load_font(21, serif=True)

    title_text = "CETA-CHELLA"
    tw_title = draw.textlength(title_text, font=title_font)
    tx, ty = cx - tw_title / 2, 82
    draw.text((tx + 3, ty + 3), title_text, font=title_font, fill=(95, 40, 130, 255))
    draw.text((tx, ty), title_text, font=title_font, fill=(24, 6, 52, 255))

    # Subtitle: ACQUAINTANCE PARTY & Date: 09-23-26 (soft pink-lavender, not stark white)
    sub_text = "ACQUAINTANCE PARTY"
    tw_sub = draw.textlength(sub_text, font=sub_font)
    sx, sy = cx - tw_sub / 2, 172
    draw.text((sx + 1, sy + 1), sub_text, font=sub_font, fill=(105, 45, 100, 255))
    draw.text((sx, sy), sub_text, font=sub_font, fill=(242, 212, 240, 255))

    date_text = "09-23-26"
    tw_date = draw.textlength(date_text, font=date_font)
    dx, dy = cx - tw_date / 2, 204
    draw.text((dx + 1, dy + 1), date_text, font=date_font, fill=(105, 45, 100, 255))
    draw.text((dx, dy), date_text, font=date_font, fill=(242, 212, 240, 255))

    # Decorative vertical barcode & "500" along the right edge of the stub
    bc_x0, bc_x1 = 982, 1034
    pattern = [4, 2, 6, 3, 2, 5, 2, 3, 6, 2, 4, 2, 5, 3]
    cy_bar = 22
    idx = 0
    while cy_bar < H - 22:
        if 135 <= cy_bar <= 220:
            cy_bar = 223
            continue
        bh = pattern[idx % len(pattern)]
        if idx % 2 == 0:
            draw.rectangle((bc_x0, cy_bar, bc_x1, min(cy_bar + bh, H - 22)), fill=(236, 196, 232, 255))
        cy_bar += bh + 2
        idx += 1

    num_img = Image.new("RGBA", (90, 50), (0, 0, 0, 0))
    nd = ImageDraw.Draw(num_img)
    n_font = load_font(34, bold=False)
    nd.text((8, 4), "500", font=n_font, fill=(238, 200, 234, 255))
    num_rot = num_img.rotate(90, expand=True)
    canvas.paste(num_rot, (bc_x0 + 2, 135), num_rot)

    # Cut out transparent scalloped perforations on left/right edges & stub notches
    mask = Image.new("L", (W, H), 255)
    md = ImageDraw.Draw(mask)
    for sy in range(28, H - 16, 42):
        md.ellipse((-12, sy - 12, 12, sy + 12), fill=0)
        md.ellipse((W - 12, sy - 12, W + 12, sy + 12), fill=0)
    notch_r = 20
    md.ellipse((stub_x - notch_r, -notch_r, stub_x + notch_r, notch_r), fill=0)
    md.ellipse((stub_x - notch_r, H - notch_r, stub_x + notch_r, H + notch_r), fill=0)
    canvas.putalpha(mask)

    canvas.save(TEMPLATE_FILE)
    return TEMPLATE_FILE

def make_transparent_qr(payload: str, size: int = 236, dark_rgb=(24, 6, 52)) -> Image.Image:
    """Generates a QR code with a 100% transparent background (NO white box)."""
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=1)
    qr.add_data(payload)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    n = len(matrix)

    qr_rgba = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    pixels = qr_rgba.load()
    dark = (*dark_rgb, 255)
    for y in range(n):
        for x in range(n):
            if matrix[y][x]:
                pixels[x, y] = dark
    return qr_rgba.resize((size, size), Image.Resampling.NEAREST)

def make_qr(person, kind: str = "entry") -> Path:
    """Stamps a separate ATTENDANCE or FOOD ticket PNG for this attendee with NO white areas."""
    food = kind == "food"
    ticket = Image.open(TEMPLATE_FILE).convert("RGBA")
    draw = ImageDraw.Draw(ticket)

    W, H = ticket.size
    stub_x = 690
    cx = stub_x // 2

    # 1. Top Header Text directly on the pink ticket (NO white pill box)
    badge_text = "FOOD TICKET (1 MEAL)" if food else "ATTENDANCE TICKET"
    badge_font = load_font(23, bold=True)
    bw = draw.textlength(badge_text, font=badge_font)
    draw.text((cx - bw / 2 + 1, 31), badge_text, font=badge_font, fill=(185, 105, 178, 255))
    draw.text((cx - bw / 2, 30), badge_text, font=badge_font, fill=(24, 6, 52, 255))

    # 2. Bottom Attendee Info: NAME and DEPT
    name_str = f"NAME: {person['name'].upper()}"
    dept_str = f"DEPT: {person['dept'].upper()}"
    info_y = H - 52

    max_info_w = stub_x - 160
    font_size = 20
    info_font = load_font(font_size, bold=True)
    while font_size > 13 and (draw.textlength(name_str, font=info_font) + draw.textlength(dept_str, font=info_font) + 32) > max_info_w:
        font_size -= 1
        info_font = load_font(font_size, bold=True)

    draw.text((80, info_y), name_str, font=info_font, fill=(24, 6, 52, 255))
    dept_w = draw.textlength(dept_str, font=info_font)
    draw.text((stub_x - 80 - dept_w, info_y), dept_str, font=info_font, fill=(24, 6, 52, 255))

    # 3. Transparent QR Code stamped directly onto the pink right stub (NO white background box)
    qr_payload = f"{person['name']}|{person['food_code' if food else 'code']}"
    qr_size = 232
    qr_img = make_transparent_qr(qr_payload, size=qr_size, dark_rgb=(24, 6, 52))
    qr_x = 720
    qr_y = 36
    ticket.alpha_composite(qr_img, (qr_x, qr_y))

    # 4. Stub Footer Label: "SCAN FOR ENTRY" or "SCAN FOR FOOD"
    scan_label = "SCAN FOR FOOD" if food else "SCAN FOR ENTRY"
    scan_font = load_font(19, bold=True)
    sw = draw.textlength(scan_label, font=scan_font)
    draw.text((qr_x + (qr_size - sw) / 2, qr_y + qr_size + 14), scan_label, font=scan_font, fill=(24, 6, 52, 255))

    folder = FOOD_DIR if food else OUT_DIR
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (f"{slug(person['name'])}_FOOD.png" if food else f"{slug(person['name'])}.png")
    ticket.save(path)
    return path


# ---------- email (Outlook / Microsoft 365, uv.edu.ph) ----------
def already_sent(path=SENT_LOG):
    if not path.exists():
        return set()
    with open(path, newline="", encoding="utf-8") as f:
        return {r[0] for r in csv.reader(f) if r}

def qr_files(p, food_only=False):
    """Returns the TWO separate ticket PNGs to attach/embed in the same email."""
    out = []
    if not food_only:
        out.append((f"{slug(p['name'])}_ATTENDANCE_TICKET.png", p["qr"], "qr"))
    out.append((f"{slug(p['name'])}_FOOD_TICKET.png", p["food_qr"], "qrfood"))
    return out

def body_text(p, food_only=False):
    if food_only:
        return (f"Hi {p['name']},\n\nAttached is your FOOD TICKET QR code. Show it at the food counter to claim your meal. "
                f"You get one meal only, so please don't share it.\n\nSee you at the {PARTY_NAME}!")
    return (f"Hi {p['name']},\n\nYour payment is confirmed! Attached in this email are your 2 separate tickets:\n"
            f"1) ATTENDANCE TICKET: show this QR at the entrance to log your attendance.\n"
            f"2) FOOD TICKET (1 MEAL): show this QR at the food counter to claim your meal.\n\n"
            f"Please save both tickets to your phone and do not share them.\n\nSee you at the {PARTY_NAME}!")

def subject_text(food_only=False):
    return f"Your Food Ticket for the {PARTY_NAME}" if food_only else f"Your Attendance & Food Tickets for the {PARTY_NAME}"

class OutlookDesktop:
    """Sends through the Outlook app that is already signed in with your uv.edu.ph account (Windows)."""
    def __init__(self, from_addr=None):
        try:
            import win32com.client
        except ImportError:
            sys.exit("Outlook method needs Windows + pywin32:  pip install pywin32")
        self.ol = win32com.client.Dispatch("Outlook.Application")
        self.account = None
        if from_addr:
            for acc in self.ol.Session.Accounts:
                if acc.SmtpAddress.lower() == from_addr.lower():
                    self.account = acc
            if not self.account:
                sys.exit(f"{from_addr} is not signed in to Outlook.")

    def send(self, p, food_only=False):
        m = self.ol.CreateItem(0)
        m.To, m.Subject, m.Body = p["email"], subject_text(food_only), body_text(p, food_only)
        for _, path, _ in qr_files(p, food_only):
            m.Attachments.Add(str(Path(path).resolve()))
        if self.account:
            m.SendUsingAccount = self.account
        m.Send()

    def close(self):
        pass

class OutlookSMTP:
    """smtp.office365.com:587 with your full school email + password."""
    def __init__(self, host, port):
        self.user, pw = os.getenv("SMTP_USER"), os.getenv("SMTP_PASS")
        if not (self.user and pw):
            sys.exit("Set SMTP_USER (e.g. you@uv.edu.ph) and SMTP_PASS first.")
        self.srv = smtplib.SMTP(host, port, timeout=60)
        self.srv.starttls(context=ssl.create_default_context())
        try:
            self.srv.login(self.user, pw)
        except smtplib.SMTPAuthenticationError as e:
            sys.exit(f"Login refused: {e}\nYour school may have disabled SMTP AUTH / requires MFA. "
                     "Use --method outlook (desktop Outlook) instead, or --manual.")

    def send(self, p, food_only=False):
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = subject_text(food_only), self.user, p["email"]
        msg.set_content(body_text(p, food_only))
        for fname, path, _ in qr_files(p, food_only):
            msg.add_attachment(Path(path).read_bytes(), maintype="image", subtype="png", filename=fname)
        self.srv.send_message(msg)

    def close(self):
        self.srv.quit()

class GraphSender:
    """Sends from your school Outlook (web) account using Microsoft sign-in in the browser (OAuth device login)."""
    CLIENT_ID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"

    def __init__(self, client_id=None):
        try:
            import msal
        except ImportError:
            sys.exit("Missing package. Run:  pip install -r requirements.txt")
        app = msal.PublicClientApplication(client_id or self.CLIENT_ID,
                                           authority="https://login.microsoftonline.com/organizations")
        flow = app.initiate_device_flow(scopes=["Mail.Send"])
        if "user_code" not in flow:
            sys.exit(f"Could not start sign-in: {flow.get('error_description', flow)}")
        print("\n" + flow["message"] + "\n(Sign in with your @uv.edu.ph account, the one you want to send FROM.)\n")
        res = app.acquire_token_by_device_flow(flow)
        if "access_token" not in res:
            sys.exit("Sign-in failed: " + str(res.get("error_description", res)) +
                     "\nIf it says 'admin approval required', your school blocks this. Use --method smtp or --manual instead.")
        self.token = res["access_token"]
        print("Signed in.\n")

    def send(self, p, food_only=False):
        name = html.escape(p["name"])
        files = qr_files(p, food_only)
        img = lambda cid, alt: f'<p><img src="cid:{cid}" width="560" style="max-width:100%;height:auto;display:block;" alt="{alt}"></p>'
        
        if food_only:
            body = (f"<p>Hi {name},</p><p>Here is your <b>FOOD TICKET (1 MEAL)</b>. Show it at the food counter to claim your meal. "
                    f"You get one meal only, so please don't share it.</p>{img('qrfood', 'Food Ticket')}"
                    f"<p><i>(If the ticket image above is blocked by your browser, download the attached PNG file at the top of this email.)</i></p>"
                    f"<p>See you at the {PARTY_NAME}!</p>")
        else:
            body = (f"<p>Hi {name},</p><p>Your payment is confirmed! Here are your <b>2 separate tickets</b>. Please save both and don't share them.</p>"
                    f"<p><b>1) ATTENDANCE TICKET</b>: show this at the entrance to log your attendance.</p>{img('qr', 'Attendance Ticket')}"
                    f"<p><b>2) FOOD TICKET (1 MEAL)</b>: show this at the food counter to claim your meal.</p>{img('qrfood', 'Food Ticket')}"
                    f"<p><i>(Tip: You can also download both ticket PNGs directly from the attachments at the top of this email.)</i></p>"
                    f"<p>See you at the {PARTY_NAME}!</p>")

        atts = []
        for fname, path, cid in files:
            b64 = base64.b64encode(Path(path).read_bytes()).decode()
            # Inline ticket in email body
            atts.append({
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": f"inline_{fname}",
                "contentType": "image/png",
                "contentBytes": b64,
                "isInline": True,
                "contentId": cid,
            })
            # Downloadable PNG attachment at top of email
            atts.append({
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": fname,
                "contentType": "image/png",
                "contentBytes": b64,
                "isInline": False,
            })

        payload = {"message": {
            "subject": subject_text(food_only),
            "body": {"contentType": "HTML", "content": body},
            "toRecipients": [{"emailAddress": {"address": p["email"]}}],
            "attachments": atts,
        }, "saveToSentItems": True}
        req = urllib.request.Request("https://graph.microsoft.com/v1.0/me/sendMail",
                                     data=json.dumps(payload).encode(), method="POST",
                                     headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=60)
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{e.code} {e.read().decode(errors='ignore')[:300]}")

    def close(self):
        pass

    def close(self):
        pass


def send_all(people, args):
    log_path = SENT_FOOD_LOG if args.food_only else SENT_LOG
    done = set() if args.resend else already_sent(log_path)
    sender = None
    if not args.dry_run:
        if args.method == "graph":
            sender = GraphSender(args.client_id)
        elif args.method == "outlook":
            sender = OutlookDesktop(args.from_addr)
        else:
            sender = OutlookSMTP(args.smtp_host, args.smtp_port)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    sent = skipped = 0
    with open(log_path, "a", newline="", encoding="utf-8") as log:
        w = csv.writer(log)
        for p in people:
            if args.test_to:
                p = {**p, "email": args.test_to}
            if not p["email"]:
                print(f"  - no email: {p['name']}"); skipped += 1; continue
            if norm(p["name"]) in done and not args.test_to:
                print(f"  = already sent: {p['name']}"); continue
            if args.domain and not p["email"].lower().endswith("@" + args.domain):
                print(f"  ? not a @{args.domain} address (sending anyway): {p['email']}")
            if args.dry_run:
                print(f"  [dry-run] would send to {p['email']}  ({p['name']})"); continue
            try:
                sender.send(p, args.food_only)
                if not args.test_to:
                    w.writerow([norm(p["name"]), p["email"], time.strftime("%F %T")]); log.flush()
                sent += 1; print(f"  + sent: {p['name']} -> {p['email']}")
                time.sleep(args.delay)
            except Exception as e:
                print(f"  ! FAILED {p['name']} ({p['email']}): {e}")
    if sender:
        sender.close()
    print(f"\nEmails sent: {sent} | without email: {skipped}")


# ---------- manual send kit (backup if automatic sending fails) ----------


# ---------- manual send kit (backup if automatic sending fails) ----------
MANUAL_HTML = r"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Manual Ticket Send</title>
<style>
body{font:15px/1.45 system-ui,Segoe UI,sans-serif;margin:0;background:#f4f0fa;color:#1f1630}
header{position:sticky;top:0;background:#fff;border-bottom:1px solid #ddd3ec;padding:12px 16px;z-index:2}
h1{font-size:1.1rem;margin:0 0 6px}.tip{color:#6b5f80;font-size:.85rem;margin:6px 0 0}
input[type=search]{width:100%;max-width:420px;padding:9px 12px;border:1px solid #ddd3ec;border-radius:8px;font:inherit}
main{max-width:1020px;margin:0 auto;padding:12px 16px 60px}
.row{display:grid;grid-template-columns:190px 190px 1fr;gap:12px;background:#fff;border:1px solid #ddd3ec;border-radius:12px;padding:12px;margin-bottom:10px;align-items:center}
.row.done{opacity:.55}.row img{width:190px;height:auto;border-radius:6px;background:#150720}
.name{font-weight:700}.dept{color:#6b5f80;font-size:.85rem}
.row input[type=email]{width:100%;max-width:340px;padding:7px 10px;border:1px solid #ddd3ec;border-radius:8px;font:inherit;margin:6px 0}
.btns{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
button,a.b{font:inherit;font-weight:600;font-size:.85rem;padding:7px 11px;border-radius:8px;border:1px solid #ddd3ec;background:#fff;color:#1f1630;cursor:pointer;text-decoration:none}
a.p{background:#5b2bd6;color:#fff;border-color:#5b2bd6}
label{font-size:.85rem;display:flex;gap:5px;align-items:center;margin-left:6px}
#msg{color:#0f8a4b;font-weight:600;font-size:.85rem}
</style></head><body>
<header><h1>Manual Ticket Send: <span id="cnt"></span></h1>
<input type="search" id="q" placeholder="Search name or department">
<p class="tip">Per person: 1) <b>Copy entry ticket</b>, 2) click <b>Open in Outlook Web</b>, 3) paste it into the email (Ctrl+V), then click <b>Copy food ticket</b> and paste that too in the same email (or click <b>Download both</b>), 4) send, then tick <b>Sent</b>. <span id="msg"></span></p></header>
<main id="list"></main>
<script>
const P = __DATA__, SUBJ = "Your Attendance & Food Tickets for the __PARTY__";
const KEY = "manual_send_v1"; let st = {};
try{ st = JSON.parse(localStorage.getItem(KEY)) || {}; }catch(e){}
const save = () => { try{ localStorage.setItem(KEY, JSON.stringify(st)); }catch(e){} };
const body = n => "Hi " + n + ",\n\nYour payment is confirmed! Attached in this email are your 2 separate tickets:\n1) ATTENDANCE TICKET: show this QR at the entrance to log your attendance.\n2) FOOD TICKET (1 MEAL): show this QR at the food counter to claim your meal.\n\nPlease save both tickets and don't share them.\n\nSee you at the __PARTY__!";
const $ = id => document.getElementById(id), msg = t => { $("msg").textContent = t; setTimeout(() => $("msg").textContent = "", 3500); };
function row(p, i){
  const d = document.createElement("div"); d.className = "row" + (st[i] && st[i].sent ? " done" : ""); d.dataset.s = (p.name + " " + p.dept).toLowerCase();
  const img = document.createElement("img"); img.src = p.img; img.alt = "Attendance Ticket for " + p.name; img.title = "Attendance Ticket";
  const img2 = document.createElement("img"); img2.src = p.fimg; img2.alt = "Food Ticket for " + p.name; img2.title = "Food Ticket";
  const c = document.createElement("div");
  const n = document.createElement("div"); n.className = "name"; n.textContent = p.name;
  const dp = document.createElement("div"); dp.className = "dept"; dp.textContent = p.dept;
  const em = document.createElement("input"); em.type = "email"; em.placeholder = "email@uv.edu.ph"; em.value = (st[i] && st[i].email) || p.email || "";
  em.oninput = () => { st[i] = Object.assign(st[i] || {}, { email: em.value }); save(); upd(); };
  const bt = document.createElement("div"); bt.className = "btns";
  const mk = (t, f) => { const b = document.createElement("button"); b.textContent = t; b.onclick = f; return b; };
  const link = (t, f, pri) => { const a = document.createElement("a"); a.className = "b" + (pri ? " p" : ""); a.textContent = t; a.target = "_blank"; a.rel = "noopener"; a.onclick = () => { a.href = f(); }; return a; };
  const enc = encodeURIComponent;
  bt.append(
    mk("Copy entry ticket", async () => { try{ const b = await (await fetch(p.img)).blob(); await navigator.clipboard.write([new ClipboardItem({ "image/png": b })]); msg("Attendance ticket copied! Paste into email."); }catch(e){ msg("Copy blocked here. Use Download both."); } }),
    mk("Copy food ticket", async () => { try{ const b = await (await fetch(p.fimg)).blob(); await navigator.clipboard.write([new ClipboardItem({ "image/png": b })]); msg("Food ticket copied! Paste into email."); }catch(e){ msg("Copy blocked here. Use Download both."); } }),
    mk("Download both", () => { [[p.img, p.file], [p.fimg, p.ffile]].forEach(([h, f], i) => setTimeout(() => { const a = document.createElement("a"); a.href = h; a.download = f; a.click(); }, i * 300)); }),
    link("Open in Outlook Web", () => "https://outlook.office.com/mail/deeplink/compose?to=" + enc(em.value) + "&subject=" + enc(SUBJ) + "&body=" + enc(body(p.name)), true),
    link("Mail app", () => "mailto:" + em.value + "?subject=" + enc(SUBJ) + "&body=" + enc(body(p.name)))
  );
  const lb = document.createElement("label"), ck = document.createElement("input"); ck.type = "checkbox"; ck.checked = !!(st[i] && st[i].sent);
  ck.onchange = () => { st[i] = Object.assign(st[i] || {}, { sent: ck.checked }); save(); d.classList.toggle("done", ck.checked); upd(); };
  lb.append(ck, "Sent"); bt.append(lb);
  c.append(n, dp, em, bt); d.append(img, img2, c); return d;
}
function upd(){ const n = Object.values(st).filter(x => x.sent).length; $("cnt").textContent = n + " of " + P.length + " sent"; }
P.forEach((p, i) => $("list").append(row(p, i)));
$("q").oninput = e => { const v = e.target.value.toLowerCase(); document.querySelectorAll(".row").forEach(r => r.hidden = !r.dataset.s.includes(v)); };
upd();
</script></body></html>"""

def write_manual(people):
    data = []
    for p in people:
        png = Path(p["qr"]).read_bytes()
        fpng = Path(p["food_qr"]).read_bytes()
        data.append({"name": p["name"], "dept": p["dept"], "email": p["email"],
                     "file": f"{slug(p['name'])}_ATTENDANCE_TICKET.png", "ffile": f"{slug(p['name'])}_FOOD_TICKET.png",
                     "img": "data:image/png;base64," + base64.b64encode(png).decode(),
                     "fimg": "data:image/png;base64," + base64.b64encode(fpng).decode()})
    html_str = (MANUAL_HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
                .replace("__PARTY__", PARTY_NAME))
    out = Path("out/manual_send.html")
    out.write_text(html_str, encoding="utf-8")
    with open("out/manual_send.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Name", "Department", "Email", "Attendance_Ticket_File", "Food_Ticket_File"])
        for p in people:
            w.writerow([p["name"], p["dept"], p["email"], str(Path(p["qr"]).resolve()), str(Path(p["food_qr"]).resolve())])
    print(f"Manual send page: {out.resolve()}\nMail-merge list:  {Path('out/manual_send.csv').resolve()}")


# ---------- main ----------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sheet", required=True, help="Google Sheet URL or a local .csv file")
    ap.add_argument("--emails", help="optional CSV with columns: name,email")
    ap.add_argument("--manual", action="store_true", help="make out/manual_send.html (copy/paste + Outlook Web links) as a backup")
    ap.add_argument("--only", help='test with one person: part of the name, e.g. --only "Pearl Joy"')
    ap.add_argument("--limit", type=int, help="only the first N people (for testing)")
    ap.add_argument("--test-to", help="send every email to THIS address instead of the guest's (safe test; not logged as sent)")
    ap.add_argument("--send", action="store_true", help="actually email the QR codes")
    ap.add_argument("--dry-run", action="store_true", help="with --send: show what would be sent")
    ap.add_argument("--method", choices=["graph", "smtp", "outlook"], default="graph",
                    help="graph = sign in with your school account in the browser (default, Outlook web); "
                         "smtp = smtp.office365.com with password; outlook = Outlook desktop app")
    ap.add_argument("--client-id", help="graph method: use your own Azure app id instead of the default")
    ap.add_argument("--from-addr", help="outlook method: send from this signed-in account, e.g. you@uv.edu.ph")
    ap.add_argument("--domain", default="uv.edu.ph", help="warn if a recipient is not on this domain")
    ap.add_argument("--food-only", action="store_true",
                    help="with --send: email ONLY the food ticket (for guests who already got their entry ticket)")
    ap.add_argument("--resend", action="store_true", help="ignore the sent log and email everyone again (use after new QR codes)")
    ap.add_argument("--delay", type=float, default=2.5, help="seconds between emails")
    ap.add_argument("--smtp-host", default="smtp.office365.com")
    ap.add_argument("--smtp-port", type=int, default=587)
    args = ap.parse_args()

    print("Reading sheet...")
    people = parse_attendees(args.sheet)
    if args.emails:
        merge_emails(people, args.emails)
    if args.only:
        q = set(norm(args.only).split())
        people = [p for p in people if q <= set(norm(p["name"]).split())]
        if not people:
            sys.exit(f"No one in the list matches '{args.only}'.")
    if args.limit:
        people = people[:args.limit]
    print(f"Confirmed attendees: {len(people)}" + ("  (TEST selection)" if args.only or args.limit else ""))

    build_ticket_template(force=True)
    for p in people:
        p["code"] = code_for(p["name"])
        p["food_code"] = code_for(p["name"], "food")
        p["qr"] = str(make_qr(p, "entry"))
        p["food_qr"] = str(make_qr(p, "food"))
    print(f"Attendance tickets saved in: {OUT_DIR.resolve()}\nFood tickets saved in:       {FOOD_DIR.resolve()}")

    if args.manual:
        write_manual(people)

    ATTENDEES_JS.write_text(
        "window.ATTENDEES = " + json.dumps([{"name": p["name"], "dept": p["dept"], "h": hash_for(p["name"], p["code"]),
                                             "fh": hash_for(p["name"], p["food_code"])} for p in people],
                                           ensure_ascii=False, indent=1) + ";\n", encoding="utf-8")
    print(f"Scanner list written: {ATTENDEES_JS}")

    no_email = [p for p in people if not p["email"]]
    if no_email and not args.send:
        print(f"\nNote: {len(no_email)} attendee(s) have no email. Fill in the Outlook column or pass --emails emails.csv.")
    if args.send:
        send_all(people, args)

if __name__ == "__main__":
    main()