(function () {
    var SENTRY_SDK_URL = "https://browser.sentry-cdn.com/7.119.0/bundle.min.js";

    function getBoot(key) {
        try { return frappe && frappe.boot && frappe.boot[key]; } catch (e) { return null; }
    }

    var dsn = getBoot("sentry_frontend_dsn");
    if (!dsn || window.__sentryFrontendLoaded) { return; }
    window.__sentryFrontendLoaded = true;

    var script = document.createElement("script");
    script.src = SENTRY_SDK_URL;
    script.crossOrigin = "anonymous";
    script.onload = function () {
        if (!window.Sentry) return;
        window.Sentry.init({
            dsn: dsn,
            environment: getBoot("sentry_frontend_environment") || "frappe",
            sampleRate: 1.0,
            ignoreErrors: [
                "ResizeObserver loop limit exceeded",
                "ResizeObserver loop completed with undelivered notifications",
                "Non-Error promise rejection captured",
            ],
            denyUrls: [/extensions\//i, /^chrome:\/\//i, /^moz-extension:\/\//i, /^safari-extension:\/\//i],
        });
        try {
            var user = frappe.session && frappe.session.user;
            if (user) { window.Sentry.setUser({ id: user, username: user, email: user }); }
            window.Sentry.setTag("site", getBoot("sitename") || "");
        } catch (e) {}
    };
    document.head.appendChild(script);
})();
