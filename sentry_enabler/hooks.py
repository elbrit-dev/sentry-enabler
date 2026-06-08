app_name = "sentry_enabler"
app_title = "Sentry Enabler"
app_publisher = "Elbrit"
app_description = "Initializes sentry-sdk, sends Frappe errors and performance data to Sentry"
app_email = "support@elbrit.org"
app_license = "mit"

before_request = ["sentry_enabler.boot.init_sentry"]
after_request = ["sentry_enabler.boot.finish_transaction"]
before_job = ["sentry_enabler.boot.init_sentry"]

app_include_js = ["/assets/sentry_enabler/js/sentry_frontend.js"]
boot_session = "sentry_enabler.boot.add_frontend_dsn_to_boot"
