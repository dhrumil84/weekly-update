"""Shared helpers for all weekly-update sections."""
from __future__ import annotations

from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("America/Los_Angeles")


def section_card(eyebrow: str, title: str, body_html: str, *, body_padding: str = "12px 24px 24px 24px") -> str:
    """Wrap a section's body in the standard card chrome.

    eyebrow: small uppercase label (e.g. "7-DAY FORECAST")
    title:   larger section title (e.g. "Anaheim, CA")
    body_html: pre-rendered inner HTML
    """
    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
           style="margin-bottom:20px;background:#FFFFFF;border-radius:12px;overflow:hidden;
                  box-shadow:0 1px 3px rgba(0,0,0,0.06);">
      <tr><td style="padding:24px 24px 4px 24px;">
        <div style="font-size:12px;color:#7B8794;letter-spacing:1.5px;text-transform:uppercase;font-weight:600;">{eyebrow}</div>
        <div style="font-size:18px;font-weight:600;color:#1F2933;margin-top:2px;">{title}</div>
      </td></tr>
      <tr><td style="padding:{body_padding};">{body_html}</td></tr>
    </table>"""


def section_error(eyebrow: str, title: str, message: str) -> str:
    """Render a section that failed to fetch its data, so the rest of the email still goes through."""
    body = f"""<div style="padding:8px 0;font-size:13px;color:#C7372F;">
      Unable to load this section: {message}
    </div>"""
    return section_card(eyebrow, title, body)
