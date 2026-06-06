import sys
import logging

import frappe

_log_error_patched = False


def init_sentry():
    dsn = frappe.conf.get("sentry_dsn")
    if not dsn:
        return

    import sentry_sdk
    from sentry_sdk.integrations.logging import LoggingIntegration

    client = sentry_sdk.get_client()
    if not (client and client.is_active()):
        sentry_sdk.init(
            dsn=dsn,
            environment=(
                frappe.conf.get("sentry_environment")
                or getattr(frappe.local, "site", None)
                or "frappe"
            ),
            traces_sample_rate=float(frappe.conf.get("sentry_traces_sample_rate") or 0.0),
            send_default_pii=bool(frappe.conf.get("sentry_send_default_pii") or False),
            integrations=[
                LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
            ],
        )

    _patch_log_error()
    _set_request_scope()


def _patch_log_error():
    global _log_error_patched
    if _log_error_patched:
        return

    import sentry_sdk

    original_log_error = frappe.log_error

    def log_error_with_sentry(*args, **kwargs):
        result = original_log_error(*args, **kwargs)
        try:
            exc_value = sys.exc_info()[1]
            if exc_value is not None:
                sentry_sdk.capture_exception(exc_value)
            else:
                title = kwargs.get("title")
                if not title and len(args) >= 2:
                    title = args[1]
                if not title and args:
                    title = args[0]
                sentry_sdk.capture_message(str(title or "Frappe error"))
        except Exception:
            pass
        return result

    frappe.log_error = log_error_with_sentry
    _log_error_patched = True


def _set_request_scope():
    import sentry_sdk

    try:
        user = getattr(getattr(frappe, "session", None), "user", None)
    except Exception:
        user = None

    if user:
        sentry_sdk.set_user(
            {"id": user, "username": user, "email": user if "@" in str(user) else None}
        )

    site = getattr(frappe.local, "site", None)
    if site:
        sentry_sdk.set_tag("site", site)

    request = getattr(frappe.local, "request", None)
    if request is not None:
        try:
            sentry_sdk.set_context("request", {"url": request.url, "method": request.method})
            sentry_sdk.get_current_scope().set_transaction_name(request.path)
        except Exception:
            pass
