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
    try:
        raise ValueError("Real test error from sentry_enabler (with stack trace)")
    except Exception as exc:
        event_id = sentry_sdk.capture_exception(exc)
        sentry_sdk.flush()
    return {"captured": True, "event_id": event_id, "user": frappe.session.user}


@frappe.whitelist(allow_guest=True)
def sentry_webhook():
    expected = frappe.conf.get("sentry_webhook_token")
    provided = frappe.form_dict.get("token") or frappe.get_request_header("X-Sentry-Token")
    if expected and provided != expected:
        raise frappe.PermissionError("Invalid Sentry webhook token")
    try:
        data = json.loads(frappe.request.data or b"{}")
    except Exception:
        data = dict(frappe.form_dict)
    event = data.get("event") or {}
    title = data.get("message") or event.get("title") or "Sentry error"
    url = data.get("url") or event.get("web_url") or ""
    level = str(data.get("level") or event.get("level") or "").upper()
    project = data.get("project_name") or data.get("project") or ""
    user = event.get("user") or {}
    who = user.get("email") or user.get("username") or user.get("id") or "unknown"
    text = (
        "🔴 <b>New Sentry error</b><br>"
        f"<b>{frappe.utils.escape_html(str(title))}</b><br>"
        f"👤 User: {frappe.utils.escape_html(str(who))}<br>"
        f"📦 {frappe.utils.escape_html(str(project))} | Level: {frappe.utils.escape_html(level)}<br>"
        f'🔗 <a href="{url}">Open in Sentry</a>'
    )
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
