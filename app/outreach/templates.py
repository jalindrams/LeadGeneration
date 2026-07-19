"""
Micraft Growth Engine - Smart Template Engine

Selects and renders the right message for each lead based on:
  - target_product  (mes / dms / tms / courier / calibration / ecom)
  - source          (nabl -> special DMS angle; exhibition_pdf -> "saw you at event")
  - sequence step   (0=intro, 1=followup_1, 2=final)

WhatsApp templates must be pre-approved by Meta before use.
Submit each template at: business.facebook.com -> WhatsApp Manager -> Message Templates.
"""

from __future__ import annotations
import re


def _persona(title: str) -> str:
    t = (title or "").lower()
    if any(x in t for x in ("plant head", "plant manager", "factory manager", "works manager")):
        return "plant_head"
    if any(x in t for x in ("quality", "qa", "qc", "document controller")):
        return "quality"
    if any(x in t for x in ("it manager", "it head", "systems manager")):
        return "it"
    if any(x in t for x in ("founder", "co-founder", "ceo", "md", "managing director")):
        return "founder"
    if any(x in t for x in ("lab manager", "lab head", "technical manager")):
        return "lab_head"
    return "generic"


def _first_name(full_name: str) -> str:
    if not full_name:
        return "there"
    skip = {"mr", "mrs", "ms", "dr", "prof", "shri", "smt"}
    # Split on spaces and dots to handle "Mr.Rishab" or "Dr.Singh" formats
    words = re.split(r"[\s.]+", full_name.strip())
    for w in words:
        clean = w.strip(".,").lower()
        if clean and clean not in skip and len(clean) > 1 and clean.isalpha():
            return w.strip(".,").capitalize()
    return "there"


def _company_short(company_name: str) -> str:
    name = re.sub(
        r"\b(pvt\.?|private|ltd\.?|limited|llp|inc\.?|co\.?)\b",
        "", company_name, flags=re.IGNORECASE
    ).strip(" .,")
    name = name or company_name
    # Title-case if all-caps
    if name == name.upper():
        name = name.title()
    return name


# ---------------------------------------------------------------------------
# Email HTML bodies defined at module level
# ---------------------------------------------------------------------------

_MES_INTRO_HTML = """
<p>Hi {name},</p>
<p>We help <b>SME manufacturers</b> like {company} go from spreadsheets and
paper job cards to a live shop-floor dashboard — tracking production, WIP,
quality rejections and OEE in real time.</p>
<p><b>Results our customers see:</b><br>
&bull; 30% reduction in production reporting time<br>
&bull; Real-time WIP visibility across shifts<br>
&bull; Quality rejection trends caught 2x faster</p>
<p>Would you be open to a quick 10-min demo call this week?</p>
<p>Best,<br><b>Micraft Solutions</b><br>
<a href="https://micraft.co.in">micraft.co.in</a></p>
"""

_MES_FOLLOWUP_HTML = """
<p>Hi {name},</p>
<p>Wanted to follow up on my earlier note. In case it helps, here is what
Micraft MES delivers for manufacturers your size:</p>
<ul>
<li>Live production dashboard (no more end-of-shift reporting)</li>
<li>Digital job cards replacing paper travellers</li>
<li>Quality rejection tracking by operator, machine and shift</li>
</ul>
<p>10 minutes is all it takes to see if it fits. Can we connect this week?</p>
<p>Best,<br><b>Micraft Solutions</b></p>
"""

_DMS_INTRO_HTML = """
<p>Hi {name},</p>
<p>For ISO-certified and compliance-bound organizations like {company}, document
chaos is a real risk: version mismatches, missing signatures, audit surprises.</p>
<p><b>Micraft DMS solves this:</b><br>
&bull; Centralized document repository with version control<br>
&bull; Digital approval workflows - no more email chains<br>
&bull; Instant audit trail for ISO 9001 / IATF / ISO 17025 audits<br>
&bull; Works on any device: desktop, tablet, phone</p>
<p>Can I show you a 10-min demo tailored to your industry?</p>
<p>Best,<br><b>Micraft Solutions</b><br>
<a href="https://micraft.co.in">micraft.co.in</a></p>
"""

_DMS_NABL_HTML = """
<p>Hi {name},</p>
<p>Maintaining NABL accreditation means your documents - SOPs, calibration
certificates, test reports, personnel records - must be version-controlled,
accessible, and audit-ready at all times.</p>
<p><b>Micraft DMS for NABL labs:</b><br>
&bull; SOP and work instruction version control<br>
&bull; Calibration certificate repository with expiry alerts<br>
&bull; Digital approval workflows for document changes<br>
&bull; Instant document retrieval during NABL assessments</p>
<p>Takes 10 minutes to see if it fits your lab. Can we connect?</p>
<p>Best,<br><b>Micraft Solutions</b></p>
"""

_DMS_FOLLOWUP_HTML = """
<p>Hi {name},</p>
<p>Just checking in. The one thing our DMS customers mention most:
<em>no more scrambling during audits.</em>
Everything is version-controlled, signed off digitally, and retrievable in seconds.</p>
<p>Happy to do a quick 10-min walkthrough whenever suits you.</p>
<p>Best,<br><b>Micraft Solutions</b></p>
"""

_CALIBRATION_INTRO_HTML = """
<p>Hi {name},</p>
<p>Managing calibration due dates, certificates and instrument history on
spreadsheets is time-consuming - and one missed calibration can jeopardize
your NABL accreditation.</p>
<p><b>Micraft Calibration MS:</b><br>
&bull; Instrument master register with full calibration history<br>
&bull; Automatic due-date alerts (email + WhatsApp)<br>
&bull; Digital calibration certificates - no paper files<br>
&bull; NABL-ready reports at the click of a button</p>
<p>I would love to show you a 10-min demo. Does this week work?</p>
<p>Best,<br><b>Micraft Solutions</b><br>
<a href="https://micraft.co.in">micraft.co.in</a></p>
"""

_CALIBRATION_FOLLOWUP_HTML = """
<p>Hi {name},</p>
<p>Following up on my earlier note about Micraft Calibration MS.</p>
<p>The most common thing we hear from lab managers:
<em>"We spend 2-3 days before every audit just compiling calibration records."</em></p>
<p>Our system brings that down to minutes. Interested in a 10-min walkthrough?</p>
<p>Best,<br><b>Micraft Solutions</b></p>
"""

_TMS_INTRO_HTML = """
<p>Hi {name},</p>
<p>For transport companies like {company}, managing trips across multiple
vehicles, drivers and routes manually leads to billing errors and delays.</p>
<p><b>Micraft TMS gives you:</b><br>
&bull; Digital trip sheets - no more paper lorry receipts<br>
&bull; Real-time trip status for your customers<br>
&bull; Automated freight billing and POD management<br>
&bull; Driver performance tracking</p>
<p>Can I show you a quick demo this week?</p>
<p>Best,<br><b>Micraft Solutions</b><br>
<a href="https://micraft.co.in">micraft.co.in</a></p>
"""

_TMS_FOLLOWUP_HTML = """
<p>Hi {name},</p>
<p>Following up on my earlier note. Here is what a typical TMS customer
saves after going live with Micraft:</p>
<ul>
<li>2-3 hours/day of manual trip sheet work eliminated</li>
<li>Freight billing errors reduced by 80%+</li>
<li>Real-time trip visibility for customers (reduces inbound calls)</li>
</ul>
<p>Happy to walk you through in 10 minutes. When works for you?</p>
<p>Best,<br><b>Micraft Solutions</b></p>
"""

_COURIER_INTRO_HTML = """
<p>Hi {name},</p>
<p>Growing a courier business is hard when booking, tracking and billing are all manual.
Micraft Courier MS brings it together:</p>
<p><b>What it does:</b><br>
&bull; Digital booking with instant waybill generation<br>
&bull; Parcel tracking from pickup to delivery<br>
&bull; Automated invoicing and COD reconciliation<br>
&bull; Branch-wise performance dashboard</p>
<p>10-min demo to see if it fits {company}?</p>
<p>Best,<br><b>Micraft Solutions</b><br>
<a href="https://micraft.co.in">micraft.co.in</a></p>
"""

_COURIER_FOLLOWUP_HTML = """
<p>Hi {name},</p>
<p>Just a quick follow-up. The one thing our courier customers love most:
<em>zero billing disputes</em> - because every booking, delivery and COD
is tracked digitally from end to end.</p>
<p>10-minute demo whenever suits you.</p>
<p>Best,<br><b>Micraft Solutions</b></p>
"""

_ECOM_INTRO_HTML = """
<p>Hi {name},</p>
<p>D2C founders spend too much time managing multiple shipping logins,
rate comparisons and COD reconciliation. Shiplystic by Micraft fixes this:</p>
<p><b>What you get:</b><br>
&bull; Best rates across 10+ carriers - auto-selected per order<br>
&bull; Single dashboard for all shipments and returns<br>
&bull; Automated COD remittance tracking<br>
&bull; One-click integrations with Shopify, WooCommerce, Unicommerce</p>
<p>Most brands save Rs.8-15 per shipment just on rates.
Happy to show you the numbers for {company}.</p>
<p>Best,<br><b>Micraft Shiplystic Team</b><br>
<a href="https://micraft.co.in">micraft.co.in</a></p>
"""

_ECOM_FOLLOWUP_HTML = """
<p>Hi {name},</p>
<p>Following up on Shiplystic. Quick question:
how many courier logins does your team manage today?</p>
<p>Most of our customers were juggling 3-5 before switching.
Now it is one dashboard, best rate auto-selected, returns handled.</p>
<p>Happy to set up a quick 10-min call.</p>
<p>Best,<br><b>Micraft Shiplystic</b></p>
"""

_FINAL_FOLLOWUP_HTML = """
<p>Hi {name},</p>
<p>This will be my last note - I do not want to clutter your inbox!</p>
<p>If the timing was not right, completely understood. When the need arises,
we are here: <a href="mailto:sales@micraft.co.in">sales@micraft.co.in</a> |
<a href="https://micraft.co.in">micraft.co.in</a></p>
<p>Wishing you and the team at {company} all the best.</p>
<p>- Micraft Solutions Team</p>
"""


# ---------------------------------------------------------------------------
# Template registry
# wa_params: fn(lead_dict) -> list[str]  (one per {{N}} placeholder in WA template)
# wa_body:   reference text for dry-run preview (use {name}/{company} placeholders)
# ---------------------------------------------------------------------------

TEMPLATES: dict[str, dict] = {

    "mes_intro": {
        "wa_name": "micraft_mes_intro",
        "wa_params": lambda l: [
            _first_name(l.get("full_name") or ""),
            _company_short(l.get("company_name") or "your company"),
        ],
        "wa_body": (
            "Hi {name}! We help manufacturers like {company} digitize their shop floor"
            " - production tracking, quality checks and real-time OEE visibility,"
            " all in one system. Would you be open to a quick 10-min call this week?"
            " - Micraft Team"
        ),
        "email_subj": "Shop-floor digitization for {company} - 10-min demo?",
        "email_html": _MES_INTRO_HTML,
    },

    "mes_followup_1": {
        "wa_name": "micraft_mes_followup",
        "wa_params": lambda l: [_first_name(l.get("full_name") or "")],
        "wa_body": (
            "Hi {name}, quick follow-up from Micraft Solutions."
            " We help manufacturers track production, WIP and quality in real-time"
            " - replacing paper job cards and manual reporting."
            " Happy to share a 2-min video of how it works. Interested?"
        ),
        "email_subj": "Following up - shop-floor visibility for {company}",
        "email_html": _MES_FOLLOWUP_HTML,
    },

    "dms_intro": {
        "wa_name": "micraft_dms_intro",
        "wa_params": lambda l: [
            _first_name(l.get("full_name") or ""),
            _company_short(l.get("company_name") or "your company"),
        ],
        "wa_body": (
            "Hi {name}! Micraft DMS helps ISO-certified organizations like {company}"
            " go paperless - document control, version management and audit trails"
            " all in one place. Are you still managing documents on shared drives?"
            " Happy to show you a 10-min demo."
        ),
        "email_subj": "Document control for {company} - audit-ready in days",
        "email_html": _DMS_INTRO_HTML,
    },

    "dms_nabl_intro": {
        "wa_name": "micraft_dms_nabl_intro",
        "wa_params": lambda l: [
            _first_name(l.get("full_name") or ""),
            _company_short(l.get("company_name") or "your lab"),
        ],
        "wa_body": (
            "Hi {name}! Maintaining NABL/ISO 17025 compliance means keeping documents"
            " audit-ready at all times. Micraft DMS is built for labs like {company}"
            " - SOPs, calibration records, test reports, all version-controlled."
            " Quick 10-min demo?"
        ),
        "email_subj": "ISO 17025 document control for {company} - NABL audit-ready",
        "email_html": _DMS_NABL_HTML,
    },

    "dms_followup_1": {
        "wa_name": "micraft_dms_followup",
        "wa_params": lambda l: [_first_name(l.get("full_name") or "")],
        "wa_body": (
            "Hi {name}, following up from Micraft Solutions."
            " We help compliance teams go from email chains and shared drives"
            " to a proper document control system - version-controlled, audit-ready."
            " Worth a quick 10-min look?"
        ),
        "email_subj": "Quick follow-up - document control for {company}",
        "email_html": _DMS_FOLLOWUP_HTML,
    },

    "calibration_intro": {
        "wa_name": "micraft_calibration_intro",
        "wa_params": lambda l: [
            _first_name(l.get("full_name") or ""),
            _company_short(l.get("company_name") or "your lab"),
        ],
        "wa_body": (
            "Hi {name}! Micraft Calibration MS helps labs like {company} automate"
            " instrument scheduling, due-date alerts and certificate management"
            " - no more missed calibrations or manual follow-ups."
            " Quick 10-min demo this week?"
        ),
        "email_subj": "Calibration scheduling automation for {company}",
        "email_html": _CALIBRATION_INTRO_HTML,
    },

    "calibration_followup_1": {
        "wa_name": "micraft_calibration_followup",
        "wa_params": lambda l: [_first_name(l.get("full_name") or "")],
        "wa_body": (
            "Hi {name}, quick follow-up from Micraft!"
            " Are you currently tracking calibration due dates on spreadsheets?"
            " We help labs automate this completely."
            " Happy to share a quick demo - no commitment needed."
        ),
        "email_subj": "Following up - calibration management for {company}",
        "email_html": _CALIBRATION_FOLLOWUP_HTML,
    },

    "tms_intro": {
        "wa_name": "micraft_tms_intro",
        "wa_params": lambda l: [
            _first_name(l.get("full_name") or ""),
            _company_short(l.get("company_name") or "your company"),
        ],
        "wa_body": (
            "Hi {name}! Micraft TMS helps transporters like {company} manage trips,"
            " track fleet movement and generate freight bills - all in one app."
            " Are you managing trips manually or on WhatsApp groups?"
            " Happy to show you a better way - 10-min demo?"
        ),
        "email_subj": "Fleet and trip management for {company} - demo this week?",
        "email_html": _TMS_INTRO_HTML,
    },

    "tms_followup_1": {
        "wa_name": "micraft_tms_followup",
        "wa_params": lambda l: [_first_name(l.get("full_name") or "")],
        "wa_body": (
            "Hi {name}, Micraft here - quick follow-up."
            " We help transport companies manage trips, track drivers and"
            " generate freight bills digitally - saving 2-3 hours of paperwork daily."
            " Worth a 10-min look?"
        ),
        "email_subj": "Re: Transport management system for {company}",
        "email_html": _TMS_FOLLOWUP_HTML,
    },

    "courier_intro": {
        "wa_name": "micraft_courier_intro",
        "wa_params": lambda l: [
            _first_name(l.get("full_name") or ""),
            _company_short(l.get("company_name") or "your company"),
        ],
        "wa_body": (
            "Hi {name}! Micraft Courier MS helps courier companies like {company}"
            " manage bookings, track parcels and generate invoices automatically"
            " - all from one app. Quick 10-min demo this week?"
        ),
        "email_subj": "Courier management system for {company} - demo?",
        "email_html": _COURIER_INTRO_HTML,
    },

    "courier_followup_1": {
        "wa_name": "micraft_courier_followup",
        "wa_params": lambda l: [_first_name(l.get("full_name") or "")],
        "wa_body": (
            "Hi {name}, following up from Micraft!"
            " Are you managing bookings and tracking manually?"
            " We help courier companies automate this and cut billing errors significantly."
            " Happy to show you in 10 mins."
        ),
        "email_subj": "Re: Courier management for {company}",
        "email_html": _COURIER_FOLLOWUP_HTML,
    },

    "ecom_intro": {
        "wa_name": "micraft_ecom_intro",
        "wa_params": lambda l: [
            _first_name(l.get("full_name") or ""),
            _company_short(l.get("company_name") or "your brand"),
        ],
        "wa_body": (
            "Hi {name}! We help D2C brands like {company} get the best shipping rates"
            " across Delhivery, Shiprocket, Ecom Express and 10+ more carriers"
            " - all from one dashboard."
            " Are you managing shipping through multiple logins right now?"
        ),
        "email_subj": "Better shipping rates for {company} - Shiplystic by Micraft",
        "email_html": _ECOM_INTRO_HTML,
    },

    "ecom_followup_1": {
        "wa_name": "micraft_ecom_followup",
        "wa_params": lambda l: [_first_name(l.get("full_name") or "")],
        "wa_body": (
            "Hi {name}, quick follow-up from Micraft Shiplystic!"
            " We aggregate 10+ shipping carriers so D2C brands get the best"
            " rate per order automatically - no more manual rate shopping."
            " Worth a quick look?"
        ),
        "email_subj": "Re: Shipping aggregation for {company}",
        "email_html": _ECOM_FOLLOWUP_HTML,
    },

    "final_followup": {
        "wa_name": "micraft_final_followup",
        "wa_params": lambda l: [_first_name(l.get("full_name") or "")],
        "wa_body": (
            "Hi {name}, last message from Micraft - promise!"
            " If the timing was not right earlier, no worries at all."
            " We will be here whenever you are ready."
            " Feel free to reach out anytime at sales@micraft.co.in"
        ),
        "email_subj": "Closing the loop - Micraft Solutions",
        "email_html": _FINAL_FOLLOWUP_HTML,
    },
}


# ---------------------------------------------------------------------------
# Smart selector
# ---------------------------------------------------------------------------

def select_template(lead: dict, step: int = 0) -> str:
    """Return the template key for this lead and outreach step (0=intro, 1=followup, 2=final)."""
    product = (lead.get("target_product") or "mes").lower()
    source = (lead.get("source") or "").lower()

    if step >= 2:
        return "final_followup"

    if step == 1:
        key = f"{product}_followup_1"
        return key if key in TEMPLATES else "final_followup"

    # step 0 intro - NABL leads get the DMS-NABL specific message for dms product
    if product == "dms" and source == "nabl":
        return "dms_nabl_intro"

    key = f"{product}_intro"
    return key if key in TEMPLATES else "mes_intro"


def render(template_key: str, lead: dict) -> dict:
    """
    Render a template for a given lead.

    Returns dict with wa_name, wa_params, wa_preview, email_subject, email_html.
    """
    tpl = TEMPLATES[template_key]
    name = _first_name(lead.get("full_name") or "")
    company = _company_short(lead.get("company_name") or "your company")

    params = tpl["wa_params"](lead)
    wa_preview = tpl["wa_body"].format(name=name, company=company)
    email_html = tpl["email_html"].format(name=name, company=company)
    email_subj = tpl["email_subj"].format(name=name, company=company)

    return {
        "wa_name": tpl["wa_name"],
        "wa_params": params,
        "wa_preview": wa_preview,
        "email_subject": email_subj,
        "email_html": email_html,
    }
