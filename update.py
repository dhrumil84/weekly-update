"""Patel Family Weekly Update — orchestrator.

Calls each section's render() to get an HTML fragment, wraps them in the master
template, and sends via Gmail SMTP.

Modes:
  python update.py            # send (gated to Sun 8-10pm Pacific)
  python update.py --dry-run  # write preview.html, do not send
  python update.py --force    # send regardless of day/time
  python update.py --only weather,markets  # render only listed sections
"""
from __future__ import annotations

import argparse
import importlib
import os
import smtplib
import sys
import traceback
from datetime import datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from sections._common import LOCAL_TZ, section_error

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

# Order matters — this is the visual order in the email.
SECTIONS = ["weather", "markets", "look_ahead"]


def _render_section(name: str) -> str:
    try:
        mod = importlib.import_module(f"sections.{name}")
        return mod.render()
    except Exception as e:
        traceback.print_exc()
        return section_error(name.replace("_", " ").title(), "Error", f"{type(e).__name__}: {e}")


def _master_template(sections_html: str) -> str:
    gen_fmt = ("%A, %b %-d %Y at %-I:%M %p %Z" if sys.platform != "win32"
               else "%A, %b %#d %Y at %#I:%M %p %Z")
    generated = datetime.now(LOCAL_TZ).strftime(gen_fmt)
    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#F5F7FA;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F5F7FA;padding:24px 12px;">
    <tr><td align="center">
      <table role="presentation" width="760" cellpadding="0" cellspacing="0" style="max-width:760px;">
        <tr><td style="padding:8px 8px 20px 8px;text-align:center;">
          <div style="font-size:28px;font-weight:800;color:#1F2933;letter-spacing:-0.5px;">Patel Family Weekly Update</div>
          <div style="font-size:12px;color:#9AA5B1;margin-top:6px;">{generated}</div>
        </td></tr>
        <tr><td>{sections_html}</td></tr>
        <tr><td style="padding:8px 24px 24px 24px;font-size:11px;color:#9AA5B1;text-align:center;">
          Generated automatically every Sunday &middot; Times in America/Los_Angeles
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def build_email(only: list[str] | None = None) -> str:
    selected = [s for s in SECTIONS if (only is None or s in only)]
    fragments = [_render_section(name) for name in selected]
    return _master_template("\n".join(fragments))


def send_email(html: str, *, sender: str, recipient: str, password: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = "Patel Family Weekly Update"
    msg["From"] = sender
    msg["To"] = recipient
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    msg.set_content("Your email client does not support HTML. Open in an HTML-capable client.")
    msg.add_alternative(html, subtype="html")

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
        s.starttls()
        s.login(sender, password)
        s.send_message(msg)


def is_target_time() -> bool:
    """True if it's Sunday 8-10pm Pacific. Used to gate the dual-cron in CI."""
    now = datetime.now(LOCAL_TZ)
    return now.weekday() == 6 and 20 <= now.hour <= 22


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Write preview.html, do not send")
    ap.add_argument("--force", action="store_true", help="Skip the time-of-day guard")
    ap.add_argument("--only", help="Comma-separated section names to render (default: all)")
    args = ap.parse_args()

    if not args.dry_run and not args.force and not is_target_time():
        now = datetime.now(LOCAL_TZ)
        print(f"Skip: not Sun 8-10pm Pacific (now: {now:%a %H:%M %Z}). Use --force to override.")
        return 0

    only = [s.strip() for s in args.only.split(",")] if args.only else None
    print(f"Building email (sections: {only or SECTIONS})...")
    html = build_email(only=only)

    if args.dry_run:
        with open("preview.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("Wrote preview.html")
        return 0

    sender    = os.environ.get("SMTP_USER", "dhrumil84@gmail.com")
    password  = os.environ.get("SMTP_PASSWORD")
    recipient = os.environ.get("RECIPIENT_EMAIL", "patel.dhrumil@protonmail.com")
    if not password:
        print("ERROR: SMTP_PASSWORD env var not set.", file=sys.stderr)
        return 1

    print(f"Sending to {recipient}...")
    send_email(html, sender=sender, recipient=recipient, password=password)
    print("Sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
