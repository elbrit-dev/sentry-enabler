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
