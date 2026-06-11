import json

import frappe
import sentry_sdk


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
    event = (
        d.get("event") or payload.get("event")
        or d.get("issue") or payload.get("issue") or {}
    )

    text = _build_sentry_message(payload, event)
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


def _normalize_tags(tags):
    pairs = []
    for t in (tags or []):
        if isinstance(t, (list, tuple)) and len(t) == 2:
            pairs.append((t[0], t[1]))
        elif isinstance(t, dict):
            pairs.append((t.get("key"), t.get("value")))
    return pairs


def _stringify_query(qs):
    if not qs:
        return ""
    if isinstance(qs, str):
        return qs
    if isinstance(qs, dict):
        return "&".join(f"{k}={v}" for k, v in qs.items())
    if isinstance(qs, (list, tuple)):
        out = []
        for item in qs:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                out.append(f"{item[0]}={item[1]}")
            else:
                out.append(str(item))
        return "&".join(out)
    return str(qs)


def _build_sentry_message(data, event):
    esc = frappe.utils.escape_html

    exc_values = (event.get("exception") or {}).get("values") or []
    root = exc_values[-1] if exc_values else {}
    exc_type = root.get("type") or ""
    exc_value = root.get("value") or ""
    title = (event.get("title") or data.get("message")
             or f"{exc_type}: {exc_value}".strip(": ") or "Sentry error")

    project = data.get("project_name") or event.get("project") or data.get("project") or ""
    environment = event.get("environment") or ""
    level = str(event.get("level") or data.get("level") or "error").upper()
    ts = _fmt_time(event.get("datetime") or event.get("timestamp"))
    event_id = event.get("event_id") or ""
    short_id = (event_id[:8] + "…" + event_id[-4:]) if len(event_id) > 14 else event_id
    issue_url = data.get("url") or event.get("web_url") or ""

    frames = ((root.get("stacktrace") or {}).get("frames")) or []
    in_app = [f for f in frames if f.get("in_app")] or frames
    lines = []
    for f in in_app[-6:]:
        fn = f.get("function") or "?"
        raw = f.get("filename") or f.get("abs_path") or "?"
        base = str(raw).rsplit("/", 1)[-1]
        ln = f.get("lineno")
        lines.append(f"at {fn} ({base}:{ln})" if ln else f"at {fn} ({base})")
    trace_block = "\n".join(lines)

    req = event.get("request") or {}
    req_url = req.get("url") or ""
    req_query = _stringify_query(req.get("query_string"))
    if len(req_query) > 220:
        req_query = req_query[:220] + "…"

    user = event.get("user") or {}
    who = user.get("email") or user.get("username") or user.get("id") or ""
    u_ip = user.get("ip_address") or ""

    tag_pairs = _normalize_tags(event.get("tags"))
    skip = {"level", "environment"}
    chips = " ".join(
        f"<code>{esc(str(k))}:{esc(str(v))}</code>"
        for k, v in tag_pairs[:10] if str(k) not in skip
    )

    sev = {"FATAL": "💀", "ERROR": "🔴", "WARNING": "🟠",
           "INFO": "🔵", "DEBUG": "⚪"}.get(level, "🔴")

    p = []
    banner = f"{sev} <b>{esc(level)}</b>"
    if environment:
        banner += f" · {esc(str(environment))}"
    p.append(banner)
    p.append(f"<b>{esc(str(title))}</b>")

    line2 = []
    if project:  line2.append("📦 " + esc(str(project)))
    if ts:       line2.append("🕒 " + esc(ts))
    if short_id: line2.append("🆔 " + esc(short_id))
    if line2:
        p.append("<hr>" + " &nbsp; ".join(line2))

    if trace_block:
        p.append("<b>⚠️ Exception</b><pre>" + esc(trace_block) + "</pre>")

    if req_url or req_query:
        r = "<b>🌐 Request</b><br>"
        if req_url:
            r += f'<a href="{esc(str(req_url))}">{esc(str(req_url))}</a>'
        if req_query:
            r += ("<br>" if req_url else "") + "<code>" + esc(str(req_query)) + "</code>"
        p.append(r)

    if who or u_ip:
        u = "<b>👤 User</b><br>" + esc(str(who))
        if u_ip:
            u += " &nbsp;·&nbsp; IP " + esc(str(u_ip))
        p.append(u)

    if chips:
        p.append("<b>🏷️ Tags</b><br>" + chips)

    if issue_url:
        p.append('<hr>🔗 <a href="' + esc(str(issue_url)) + '"><b>View full issue on Sentry →</b></a>')

    return "<br><br>".join(p)


def _fmt_time(ts):
    if not ts:
        return ""
    try:
        if isinstance(ts, (int, float)):
            from datetime import datetime, timezone
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%b %d, %Y %H:%M UTC")
        return str(ts).replace("T", " ")[:16] + " UTC"
    except Exception:
        return str(ts)


@frappe.whitelist()
def send_log_test():
    from sentry_sdk import logger as sentry_logger
    marker = frappe.utils.now()
    sentry_logger.info("sentry_enabler log test (info) @ {marker}", marker=marker)
    sentry_logger.warning("sentry_enabler log test (warning) @ {marker}", marker=marker)
    sentry_logger.error("sentry_enabler log test (error-level LOG, not an exception) @ {marker}", marker=marker)
    sentry_sdk.flush()
    return {"ok": True, "marker": marker}


@frappe.whitelist()
def send_metric_test():
    from sentry_enabler.boot import init_sentry
    init_sentry()
    marker = frappe.utils.now()
    attrs = {"marker": marker, "site": frappe.local.site}
    sentry_sdk.metrics.count("sentry_enabler.test_count", 1, attributes=attrs)
    sentry_sdk.metrics.gauge("sentry_enabler.test_gauge", 42, attributes=attrs)
    sentry_sdk.metrics.distribution("sentry_enabler.test_distribution", 187,
                                    unit="millisecond", attributes=attrs)
    sentry_sdk.flush()
    return {"ok": True, "marker": marker}


@frappe.whitelist()
def send_profile_test():
    import time
    from sentry_enabler.boot import init_sentry
    init_sentry()
    marker = frappe.utils.now()
    sentry_sdk.profiler.start_profiler()
    for _ in range(10):
        time.sleep(0.1)   # slow path
        time.sleep(0.05)  # fast path
    sentry_sdk.profiler.stop_profiler()
    sentry_sdk.flush()
    return {"ok": True, "marker": marker}
