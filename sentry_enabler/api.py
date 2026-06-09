import json

import frappe


@frappe.whitelist()
def send_test():
    from sentry_enabler.boot import init_sentry
    dsn_set = bool(frappe.conf.get("sentry_dsn"))
    init_sentry()
    import sentry_sdk
    client_active = sentry_sdk.get_client().is_active()
    event_id = sentry_sdk.capture_message("Sentry test event from sentry_enabler")
    sentry_sdk.flush()
    return {"dsn_set": dsn_set, "client_active": client_active, "event_id": event_id}


@frappe.whitelist()
def send_error():
    from sentry_enabler.boot import init_sentry
    init_sentry()
    import sentry_sdk
    import time
    marker = time.strftime("%Y%m%d-%H%M%S")
    try:
        raise ValueError(f"Sentry Enabler test error @ {marker}")
    except Exception as exc:
        with sentry_sdk.new_scope() as scope:
            scope.fingerprint = ["sentry-enabler-test", marker]
            event_id = sentry_sdk.capture_exception(exc)
        sentry_sdk.flush()
    return {"captured": True, "event_id": event_id, "marker": marker, "user": frappe.session.user}


@frappe.whitelist(allow_guest=True)
def sentry_webhook():
    expected = frappe.conf.get("sentry_webhook_token")
    provided = (
        frappe.request.args.get("token")
        or frappe.form_dict.get("token")
        or frappe.get_request_header("X-Sentry-Token")
    )
    if expected and provided != expected:
        raise frappe.PermissionError("Invalid Sentry webhook token")

    try:
        payload = json.loads(frappe.request.data or b"{}")
    except Exception:
        payload = dict(frappe.form_dict)

    # Sentry nests the event under data.event (alert action) or data.issue (issue webhook)
    d = payload.get("data") or {}
    event = d.get("event") or payload.get("event") or {}
    issue = d.get("issue") or payload.get("issue") or {}
    metadata = event.get("metadata") or issue.get("metadata") or {}

    # Build a tag lookup (Sentry sends tags as [[key, value], ...])
    tagmap = {}
    for t in (event.get("tags") or issue.get("tags") or []):
        if isinstance(t, (list, tuple)) and len(t) == 2:
            tagmap[t[0]] = t[1]
        elif isinstance(t, dict):
            tagmap[t.get("key")] = t.get("value")

    title = (
        event.get("title")
        or issue.get("title")
        or payload.get("message")
        or ": ".join(x for x in [metadata.get("type"), metadata.get("value")] if x)
        or "Sentry error"
    )
    level = str(
        event.get("level") or issue.get("level") or payload.get("level")
        or tagmap.get("level") or "error"
    ).upper()
    url = (
        event.get("web_url") or issue.get("permalink") or issue.get("url")
        or payload.get("url") or ""
    )
    culprit = event.get("culprit") or issue.get("culprit") or ""

    u = event.get("user") or {}
    if isinstance(u, dict):
        who = u.get("email") or u.get("username") or u.get("id") or u.get("ip_address")
    else:
        who = str(u or "")
    who = who or tagmap.get("user") or tagmap.get("user.email") or "unknown"

    esc = frappe.utils.escape_html
    parts = [
        "🔴 <b>New Sentry error</b>",
        f"<b>{esc(str(title))}</b>",
        f"👤 User: {esc(str(who))}",
        f"🏷️ Level: {esc(level)}" + (f" • {esc(str(culprit))}" if culprit else ""),
    ]
    if url:
        parts.append(f'🔗 <a href="{url}">{esc(str(url))}</a>')
    text = "<br>".join(parts)

    _send_to_raven(text)
    return {"ok": True}


def _send_to_raven(text):
    channel = frappe.conf.get("raven_alert_channel")
    bot_name = frappe.conf.get("raven_alert_bot")
    if not channel:
        return
    try:
        if bot_name:
            bot = frappe.get_doc("Raven Bot", bot_name)
            bot.send_message(channel_id=channel, text=text)
        else:
            frappe.get_doc({"doctype": "Raven Message", "channel_id": channel, "text": text, "message_type": "Text"}).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        pass
