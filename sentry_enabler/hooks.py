app_name = "sentry_enabler"
app_title = "Sentry Enabler"
app_publisher = "Elbrit"
app_description = "Provides sentry-sdk so Frappe's native Sentry integration works"
app_email = "support@elbrit.org"
app_license = "mit"

before_request = ["sentry_enabler.boot.init_sentry"]
before_job = ["sentry_enabler.boot.init_sentry"]
