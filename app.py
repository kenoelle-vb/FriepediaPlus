import os
import json
import base64
import hashlib
import uuid
from datetime import datetime
from io import BytesIO
import numpy as np

import pandas as pd
import matplotlib
matplotlib.use("Agg")  # headless, no GUI
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from flask import (
    Flask, render_template, request, redirect, url_for,
    send_file, send_from_directory, flash, session
)

# NEW: for gradient bars
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

# Optional: Gemini (google-generativeai). We handle absence gracefully.
try:
    import google.generativeai as genai
    _GENAI_AVAILABLE = True
except Exception:
    genai = None
    _GENAI_AVAILABLE = False

try:
    from PyPDF2 import PdfMerger
    _PDF_MERGE_AVAILABLE = True
except Exception:
    _PDF_MERGE_AVAILABLE = False


# ---------------------------
# Flask setup — we’ll use .htm templates
# ---------------------------
app = Flask(__name__, template_folder="templates")
app.secret_key = "dev-secret-change-me"

DATA_DIR = "data"
IMAGES_DIR = "IMAGES"
COURSES_CSV = os.path.join(DATA_DIR, "courses.csv")
IMAGES_PARQUET = os.path.join(DATA_DIR, "images.parquet")

# ---------------------------
# Existing utilities
# ---------------------------
def load_courses():
    """Loads courses from CSV, parses meta_json, and returns a list of dicts."""
    if os.path.exists(COURSES_CSV):
        df = pd.read_csv(COURSES_CSV)
        df["meta"] = df["meta_json"].apply(lambda x: json.loads(x) if pd.notna(x) else {})
        return df.to_dict(orient="records")
    return []

def load_images_map():
    """Loads image paths from Parquet and returns a map of image_id to serving_path."""
    images = {}
    if os.path.exists(IMAGES_PARQUET):
        try:
            idf = pd.read_parquet(IMAGES_PARQUET)
            idf["serving_path"] = idf["card_path"].where(idf["card_path"].notna(), idf["image_path"])
            for _, row in idf.iterrows():
                images[row["image_id"]] = str(row["serving_path"])
        except Exception as e:
            print("Error reading parquet:", e)
    return images

# ---------------------------
# Gemini configuration & call (Create Course flow)
# ---------------------------
GEMINI_API_KEY = "AIzaSyD6w7Lep4QaHQTGAwfUQv8AgTa1dmMJkSE"

def configure_model():
    if not _GENAI_AVAILABLE:
        print("google-generativeai not installed; will use mock syllabus JSON.")
        return None
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        generation_config = {
            "temperature": 1,
            "top_p": 0.95,
            "top_k": 60,
            "max_output_tokens": 8192,
            "response_mime_type": "application/json",
        }
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash-lite",
            generation_config=generation_config
        )
        print("Gemini model configured successfully!")
        return model
    except Exception as e:
        print(f"Gemini configuration error: {e}")
        return None

def _mock_syllabus(institution_name, references, parts_count, parts_keypoints):
    parts = []
    for i in range(1, parts_count + 1):
        user_kp = (parts_keypoints.get(i) or "").strip()
        parts.append({
            "part_index": i,
            "title": f"Part {i}: Thematic Module",
            "learning_objectives": [
                f"Understand core ideas of module {i}.",
                "Connect concepts to real-world applications.",
                "Practice structured reasoning using provided references."
            ],
            "key_points_summary": user_kp if user_kp else f"Key concepts for part {i} derived from references.",
            "suggested_readings": references[:3] if references else []
        })
    return {
        "title": "Generated Course (Mock)",
        "institution": institution_name,
        "parts_count": parts_count,
        "references": references,
        "parts": parts,
        "assessment": {
            "type": "Essay (mock)",
            "grading_method": "RAG-based rubric (keywords, logic, frameworks)"
        }
    }

def generate_syllabus_via_gemini(institution_name, references, parts_count, parts_keypoints):
    schema_hint = {
        "title": "string",
        "institution": "string",
        "parts_count": "int",
        "references": ["url", "..."],
        "parts": [
            {
                "part_index": "int (1-based)",
                "title": "string",
                "learning_objectives": ["string", "..."],
                "key_points_summary": "string",
                "suggested_readings": ["string", "..."]
            }
        ],
        "assessment": {
            "type": "Essay (mock)",
            "grading_method": "RAG-based rubric (keywords, logic, frameworks)"
        }
    }
    prompt = {
        "instruction": "Generate a concise course syllabus in strict JSON following the schema hint.",
        "notes": [
            "Return ONLY JSON (no prose, no markdown).",
            "Ensure parts_count equals the number of objects in 'parts'.",
            "Use provided references where relevant for suggested_readings.",
            "Make titles and objectives clear and undergraduate-friendly."
        ],
        "context": {
            "institution": institution_name,
            "references": references,
            "parts_count": parts_count,
            "user_keypoints_by_part": parts_keypoints
        },
        "schema_hint": schema_hint
    }
    model = configure_model()
    if model is None:
        print("Using MOCK syllabus JSON (Gemini unavailable).")
        return _mock_syllabus(institution_name, references, parts_count, parts_keypoints)
    try:
        resp = model.generate_content(json.dumps(prompt))
        raw = None
        if hasattr(resp, "text") and resp.text:
            raw = resp.text
        elif hasattr(resp, "candidates") and resp.candidates:
            raw = resp.candidates[0].content.parts[0].text if resp.candidates[0].content.parts else None
        if not raw:
            raise ValueError("Empty response from Gemini.")
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.startswith("json"):
                raw = raw[4:].strip()
        syllabus = json.loads(raw)
        return syllabus
    except Exception as e:
        print(f"Gemini call failed ({e}); producing MOCK syllabus instead.")
        return _mock_syllabus(institution_name, references, parts_count, parts_keypoints)

# ---------------------------
# Certificate helpers
# ---------------------------
def _render_certificate_image(course_title: str, cert_hash: str) -> bytes:
    """Return PNG bytes for a styled certificate image."""
    fig_w, fig_h = 8, 5
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=150)
    bg = "#0f172a"
    panel = "#111827"
    accent = "#60a5fa"
    text = "#e5e7eb"

    fig.patch.set_facecolor(bg)
    ax.set_facecolor(panel)
    ax.axis("off")

    title = "Certificate of Completion"
    subtitle = course_title
    body = "Awarded to: Demo User"
    stamp = f"Hash: {cert_hash[:16]}..."

    ax.text(0.5, 0.78, title, ha="center", va="center", fontsize=20, color=text, fontweight="bold")
    ax.text(0.5, 0.62, subtitle, ha="center", va="center", fontsize=14, color=accent)
    ax.text(0.5, 0.48, body, ha="center", va="center", fontsize=12, color=text)
    ax.text(0.5, 0.22, stamp, ha="center", va="center", fontsize=10, color="#a7f3d0")

    ax.plot([0.08, 0.92], [0.86, 0.86], color=accent, linewidth=1.6)
    ax.plot([0.08, 0.92], [0.14, 0.14], color=accent, linewidth=1.6)
    ax.plot([0.08, 0.08], [0.14, 0.86], color=accent, linewidth=1.6)
    ax.plot([0.92, 0.92], [0.14, 0.86], color=accent, linewidth=1.6)

    buf = BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format="png", facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf.read()

def _save_pdf_from_png(png_path: str, pdf_path: str):
    """Create a single-page PDF that contains the given PNG."""
    img = plt.imread(png_path)
    # A4 portrait is fine; the image will be scaled to fit.
    fig = plt.figure(figsize=(8.27, 11.69))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    ax.imshow(img)
    with PdfPages(pdf_path) as pdf:
        pdf.savefig(fig, dpi=150)
    plt.close(fig)

# ---------------------------
# Routes
# ---------------------------
@app.route("/")
def root():
    return redirect(url_for("landing"))

@app.route("/landing")
def landing():
    return render_template("landing.htm")

# Serve images from ./IMAGES safely (fixes course card thumbnails)
@app.route("/images/<path:filename>")
def images_file(filename):
    return send_from_directory(IMAGES_DIR, filename)

@app.route("/create", methods=["GET", "POST"])
def create():
    """
    No-JS, multi-step server-rendered flow:
    - 'Update Parts' (action=update): re-render page with the chosen number of part textareas.
    - 'Generate Course Syllabus' (action=generate): call Gemini/mock, show readable preview.
    - 'Submit to Institution' (action=submit): flash confirmation and persist JSON to /data.
    """
    institutions = ["Unpad", "Binus", "Friepedia Labs", "Coursera", "Open University", "ASEAN EdTech Network", "NGO Youth Co:Lab"]

    form_snapshot = {
        "references": [],
        "parts_count": 5,
        "institution_index": 0,
        "parts_keypoints": {}
    }
    generated_syllabus = None
    persisted_path = None

    if request.method == "POST":
        action = request.form.get("action", "update").lower()

        # References: 15 fixed fields
        references = []
        for i in range(1, 16):
            val = request.form.get(f"ref_{i}", "").strip()
            if val:
                references.append(val)
        if len(references) > 15:
            references = references[:15]

        # Parts count
        try:
            parts_count = int(request.form.get("parts_count", "5"))
        except ValueError:
            parts_count = 5
        parts_count = max(5, min(25, parts_count))

        # Institution index
        try:
            inst_index = int(request.form.get("institution_index", "0"))
        except ValueError:
            inst_index = 0
        if inst_index < 0 or inst_index >= len(institutions):
            inst_index = 0
        institution_name = institutions[inst_index]

        # Key points per part
        parts_keypoints = {}
        for i in range(1, parts_count + 1):
            parts_keypoints[i] = request.form.get(f"part_{i}_points", "")

        form_snapshot = {
            "references": references,
            "parts_count": parts_count,
            "institution_index": inst_index,
            "parts_keypoints": parts_keypoints
        }

        if action == "update":
            flash("Form updated. Review/edit your inputs, then generate the syllabus.", "info")

        elif action == "generate":
            generated_syllabus = generate_syllabus_via_gemini(
                institution_name=institution_name,
                references=references,
                parts_count=parts_count,
                parts_keypoints=parts_keypoints
            )
            session["last_generated_syllabus"] = generated_syllabus
            session["last_form_snapshot"] = form_snapshot
            flash("Syllabus generated (Gemini/mock). Review below, then click Submit to Institution.", "success")

        elif action == "submit":
            generated_syllabus = session.get("last_generated_syllabus")
            if not generated_syllabus:
                flash("No generated syllabus found. Please generate one first.", "error")
            else:
                os.makedirs(DATA_DIR, exist_ok=True)
                fname = f"syllabus_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}.json"
                fpath = os.path.join(DATA_DIR, fname)
                with open(fpath, "w", encoding="utf-8") as f:
                    json.dump(generated_syllabus, f, ensure_ascii=False, indent=2)
                persisted_path = fpath
                flash(f"Submitted to {institution_name} (mock). Syllabus saved to {fname} for review.", "success")

        return render_template(
            "create.htm",
            institutions=institutions,
            generated_syllabus=generated_syllabus,
            persisted_path=persisted_path,
            form_snapshot=form_snapshot
        )

    # GET
    if "last_form_snapshot" in session:
        form_snapshot = session["last_form_snapshot"]

    return render_template(
        "create.htm",
        institutions=institutions,
        generated_syllabus=None,
        persisted_path=None,
        form_snapshot=form_snapshot
    )

@app.route("/courses")
def courses_list():
    courses = load_courses()
    images = load_images_map()
    for c in courses:
        image_path = c["meta"].get("image_path")
        if not image_path:
            mapped = images.get(c.get("image_id"))
            if mapped:
                image_path = mapped
        # Build a URL that Flask can actually serve
        resolved_url = None
        if image_path:
            if image_path.startswith("IMAGES/"):
                resolved_url = url_for("images_file", filename=image_path[len("IMAGES/"):])
            else:
                basename = os.path.basename(image_path)
                candidate = os.path.join(IMAGES_DIR, basename)
                if os.path.exists(candidate):
                    resolved_url = url_for("images_file", filename=basename)
        c["resolved_image_url"] = resolved_url
    return render_template("courses.htm", courses=courses)

# ---------------------------
# Course + Quiz flow (no-JS)
# ---------------------------
@app.route("/course/<course_id>", methods=["GET", "POST"])
def course_detail(course_id):
    courses = load_courses()
    course = next((c for c in courses if c["id"] == course_id), None)
    if not course:
        flash("Course not found.")
        return redirect(url_for("courses_list"))

    # Example syllabus DataFrame
    syllabus = pd.DataFrame({
        "Week": [1, 2, 3, 4],
        "Topic": ["Introduction", "Core Concepts", "Hands-on Project", "Assessment & Wrap-up"],
        "Reading/Links": ["linkA", "linkB", "linkC", "linkD"]
    })
    syllabus_html = syllabus.to_html(index=False, classes="syllabus-table")

    if request.method == "POST":
        # Mint a real certificate (PNG + proper PDF)
        cert_text = f"{course_id}|{course['title']}|user:demo_user"
        cert_hash = hashlib.sha256(cert_text.encode()).hexdigest()

        os.makedirs(DATA_DIR, exist_ok=True)
        timestamp = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')

        # Save PNG
        png_name = f"cert_{course_id}_{timestamp}.png"
        png_path = os.path.join(DATA_DIR, png_name)
        png_bytes = _render_certificate_image(course['title'], cert_hash)
        with open(png_path, "wb") as f:
            f.write(png_bytes)

        # Save single-page PDF
        pdf_name = f"cert_{course_id}_{timestamp}.pdf"
        pdf_path = os.path.join(DATA_DIR, pdf_name)
        _save_pdf_from_png(png_path, pdf_path)

        return render_template("cert_issued.htm", course=course, cert_hash=cert_hash, cert_filename=pdf_name)

    return render_template("course_detail.htm", course=course, syllabus_html=syllabus_html)

@app.route("/course/<course_id>/quiz", methods=["GET", "POST"])
def course_quiz(course_id):
    courses = load_courses()
    course = next((c for c in courses if c["id"] == course_id), None)
    if not course:
        flash("Course not found.")
        return redirect(url_for("courses_list"))

    if request.method == "GET":
        return render_template("essay_test.htm", course=course)

    # POST: handle submission, compute hash, render certificate image
    essay_text = (request.form.get("essay_text") or "").strip()
    cert_text = f"{course_id}|{course['title']}|user:demo_user|essay:{essay_text[:200]}"
    cert_hash = hashlib.sha256(cert_text.encode()).hexdigest()

    # PNG bytes
    png_bytes = _render_certificate_image(course['title'], cert_hash)
    cert_img_b64 = base64.b64encode(png_bytes).decode()

    # Persist PNG + single-page PDF
    os.makedirs(DATA_DIR, exist_ok=True)
    timestamp = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    png_name = f"cert_{course_id}_{timestamp}.png"
    pdf_name = f"cert_{course_id}_{timestamp}.pdf"
    png_path = os.path.join(DATA_DIR, png_name)
    with open(png_path, "wb") as f:
        f.write(base64.b64decode(cert_img_b64))
    _save_pdf_from_png(png_path, os.path.join(DATA_DIR, pdf_name))

    return render_template("quiz_result.htm", course=course, cert_hash=cert_hash, cert_img_b64=cert_img_b64)

# ---------------------------
# Certificates: combined PDF
# ---------------------------
@app.route("/certificates/all")
def certificates_all():
    if not os.path.exists(DATA_DIR):
        flash("No certificates found.")
        return redirect(url_for("profile"))

    # Prefer merging the per-cert PDFs if available (no Matplotlib needed)
    pdfs = sorted(f for f in os.listdir(DATA_DIR) if f.startswith("cert_") and f.endswith(".pdf"))
    if _PDF_MERGE_AVAILABLE and pdfs:
        merger = PdfMerger()
        for fname in pdfs:
            merger.append(os.path.join(DATA_DIR, fname))
        buf = BytesIO()
        merger.write(buf)
        merger.close()
        buf.seek(0)
        return send_file(buf, as_attachment=False, mimetype="application/pdf", download_name="All_Certificates.pdf")

    # Fallback: build a multipage PDF from PNGs via Agg (headless)
    pngs = sorted(f for f in os.listdir(DATA_DIR) if f.startswith("cert_") and f.endswith(".png"))
    if not pngs:
        flash("No certificate images found to compile.")
        return redirect(url_for("profile"))

    from matplotlib.backends.backend_pdf import PdfPages
    buf = BytesIO()
    with PdfPages(buf) as pdf:
        for fname in pngs:
            img_path = os.path.join(DATA_DIR, fname)
            img = plt.imread(img_path)
            fig = plt.figure(figsize=(8.27, 11.69))  # A4 portrait
            ax = fig.add_axes([0, 0, 1, 1])
            ax.axis("off")
            ax.imshow(img)
            pdf.savefig(fig, dpi=150)
            plt.close(fig)
    plt.close("all")
    buf.seek(0)
    return send_file(buf, as_attachment=False, mimetype="application/pdf", download_name="All_Certificates.pdf")


# ---------------------------
# Dashboard + Profile
# ---------------------------
@app.route("/dashboard")
def dashboard():
    import numpy as np  # ensure available in this scope

    # --- Data ---
    funds_numeric = {
        "CBDC Pool": 48000,
        "Micro-Donations": 22500,
        "Institution Grants": 31000,
        "Impact Prizes": 9000,
    }
    names = list(funds_numeric.keys())
    vals = list(funds_numeric.values())
    x = np.arange(len(names))  # numeric positions 0..N-1

    # --- Theme ---
    BG_COLOR_DARK = "#0f172a"
    TEXT_COLOR = "#FFFFFF"
    EDGE_COLOR = "#cbd5e1" + "40"  # light border

    # Gradient colors (top -> bottom) — #60a5fa -> #a78bfa
    top_rgb = np.array([0x60, 0xa5, 0xfa]) / 255.0  # #60a5fa
    bot_rgb = np.array([0xa7, 0x8b, 0xfa]) / 255.0  # #a78bfa

    # --- Figure ---
    fig, ax = plt.subplots(figsize=(7, 3))
    fig.set_facecolor(BG_COLOR_DARK)
    ax.set_facecolor(BG_COLOR_DARK)

    # Build a vertical **RGB** gradient (H x 1 x 3) so imshow does NOT use a colormap
    grad_h = 256
    t = np.linspace(0, 1, grad_h).reshape(-1, 1, 1)  # (H,1,1)
    grad_rgb = t * top_rgb + (1.0 - t) * bot_rgb     # (H,1,3)

    # Draw one gradient “bar” per category using numeric extents
    width = 0.8
    for i, v in enumerate(vals):
        left, right = x[i] - width/2, x[i] + width/2
        ax.imshow(
            grad_rgb,
            extent=(left, right, 0, v),   # x-left, x-right, y-bottom, y-top
            origin="lower",
            aspect="auto",
            zorder=2,
        )
        # subtle edge to make bars crisp on dark bg
        ax.add_patch(plt.Rectangle(
            (left, 0), width, v,
            fill=False, linewidth=1.0, edgecolor=EDGE_COLOR, zorder=3
        ))

    # Axes styling
    ax.set_xlim(-0.5, len(names) - 0.5)
    ax.set_ylim(0, max(vals) * 1.05)
    ax.set_xticks(x)
    ax.set_xticklabels(names)
    ax.tick_params(axis='x', colors=TEXT_COLOR, rotation=0)
    ax.tick_params(axis='y', colors=TEXT_COLOR)
    for spine in ax.spines.values():
        spine.set_edgecolor(TEXT_COLOR + "40")
    plt.tight_layout()

    # Encode to base64
    buf = BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    img_b64 = base64.b64encode(buf.read()).decode()

    # Transparency cards (same as before)
    fund_cards = [
        {
            "title": "CBDC Pool",
            "desc": "Donations aggregated via Central Bank Digital Currency rails with transparent on-chain accounting.",
            "people": "50,657",
            "total": "IDR 5.000.000.000",
        },
        {
            "title": "Micro-Donations",
            "desc": "Small recurring gifts from individuals, rounded-up transactions, and public tip jars.",
            "people": "182,341",
            "total": "IDR 2.250.000.000",
        },
        {
            "title": "Institution Grants",
            "desc": "University, foundation, and corporate education grants earmarked for access and inclusion.",
            "people": "312 institutions",
            "total": "IDR 3.100.000.000",
        },
        {
            "title": "Impact Prizes",
            "desc": "Challenge prizes aligned to learning milestones and measurable career outcomes.",
            "people": "6,204",
            "total": "IDR 900.000.000",
        },
    ]
    return render_template("dashboard.htm", funds_img_b64=img_b64, fund_cards=fund_cards)


@app.route("/profile")
def profile():
    cert_pngs = []
    cert_pdfs = []
    if os.path.exists(DATA_DIR):
        for fname in os.listdir(DATA_DIR):
            if fname.startswith("cert_") and fname.endswith(".png"):
                cert_pngs.append(fname)
            if fname.startswith("cert_") and fname.endswith(".pdf"):
                cert_pdfs.append(fname)

    # Use PNGs to count completions (covers both quiz and hash-only paths)
    user = {
        "name": "Demo User",
        "grade": "N/A",
        "completed": len(cert_pngs),
        "certificates": cert_pngs,  # list the PNG artifacts
    }
    return render_template("profile.htm", user=user)

@app.route("/download_cert/<filename>")
def download_cert(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        flash("Certificate not found.")
        return redirect(url_for("profile"))
    return send_file(path, as_attachment=False)

if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    app.run(debug=True, use_reloader=False, threaded=False)
