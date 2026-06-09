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

    d = payload.get("data") or {}
    event = d.get("event") or payload.get("event") or {}
    issue = d.get("issue") or payload.get("issue") or {}
    metadata = event.get("metadata") or issue.get("metadata") or {}

    tagmap = {}
    for t in (event.get("tags") or issue.get("tags") or []):
        if isinstance(t, (list, tuple)) and len(t) == 2:
            tagmap[t[0]] = t[1]
        elif isinstance(t, dict):
            tagmap[t.get("key")] = t.get("value")

    exc_values = (event.get("exception") or {}).get("values") or []
    exc = exc_values[-1] if exc_values else {}
    exc_type = exc.get("type") or metadata.get("type") or ""
    exc_value = exc.get("value") or metadata.get("value") or ""
    description = ": ".join(p for p in [exc_type, exc_value] if p)
    if not description:
        description = (
            event.get("title") or issue.get("title")
            or payload.get("message") or "Sentry error"
        )

    # Find the frame where the error happened (last in-app frame with code)
    frames = (exc.get("stacktrace") or {}).get("frames") or []
    in_app = [f for f in frames if f.get("in_app")] or frames
    code_frame = None
    for f in reversed(in_app):
        if f.get("context_line") is not None or f.get("pre_context") or f.get("post_context"):
            code_frame = f
            break
    if not code_frame and in_app:
        code_frame = in_app[-1]

    level = str(
        event.get("level") or issue.get("level") or payload.get("level")
        or tagmap.get("level") or "error"
    ).upper()
    url = (
        event.get("web_url") or issue.get("permalink") or issue.get("url")
        or payload.get("url") or ""
    )

    u = event.get("user") or {}
    if isinstance(u, dict):
        who = u.get("email") or u.get("username") or u.get("id") or u.get("ip_address")
    else:
        who = str(u or "")
    who = who or tagmap.get("user") or tagmap.get("user.email") or "unknown"

    esc = frappe.utils.escape_html
    parts = [
        "🔴 <b>New Sentry error</b>",
        f"👤 <b>User:</b> {esc(str(who))}",
        f"🏷️ <b>Level:</b> {esc(level)}",
        f"📝 <b>Description:</b> {esc(str(description))}",
    ]

    if code_frame:
        loc = code_frame.get("filename") or code_frame.get("module") or "?"
        ln = code_frame.get("lineno")
        fn = code_frame.get("function") or "?"
        header = f"{loc}:{ln} in {fn}" if ln else f"{loc} in {fn}"
        pre = code_frame.get("pre_context") or []
        post = code_frame.get("post_context") or []
        ctx = code_frame.get("context_line")
        code_lines = []
        n = (ln or 0) - len(pre)
        for l in pre:
            code_lines.append(f"{n}    {l}")
            n += 1
        if ctx is not None:
            code_lines.append(f"{n} →  {ctx}")
            n += 1
        for l in post:
            code_lines.append(f"{n}    {l}")
            n += 1
        code_html = "<br>".join(esc(l) for l in code_lines)
        if len(code_html) > 2500:
            code_html = code_html[:2500] + " …"
        parts.append(f"<b>📄 {esc(header)}</b>")
        parts.append(f"<pre>{code_html}</pre>")

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
