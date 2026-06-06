import frappe


def init_sentry():
    """Initialize the Sentry SDK once per process if a DSN is configured."""
    dsn = frappe.conf.get("sentry_dsn")
    if not dsn:
        return

    import sentry_sdk

    client = sentry_sdk.get_client()
    if client and client.is_active():
        return

    sentry_sdk.init(
        dsn=dsn,
        environment=(
            frappe.conf.get("sentry_environment")
            or getattr(frappe.local, "site", None)
            or "frappe"
        ),
        traces_sample_rate=float(frappe.conf.get("sentry_traces_sample_rate") or 0.0),
        send_default_pii=False,
    )
