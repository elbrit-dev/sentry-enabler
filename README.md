# Sentry Enabler

A minimal Frappe app whose only job is to install `sentry-sdk` into the bench
environment so that Frappe v15's built-in Sentry integration becomes active.

## How it works
Frappe v15 ships the Sentry capture code in `frappe/utils/sentry.py`, but it does
NOT bundle the `sentry-sdk` Python package. This app declares `sentry-sdk` as a
dependency, so installing it on a Frappe Cloud bench makes the SDK available.

## Usage
1. Add this app to your bench (Frappe Cloud: Benches > Apps > Add App > this repo URL).
2. Deploy the bench (installs sentry-sdk).
3. Install the app on your site (Apps > Install App).
4. Add the DSN in Site Config:  "sentry_dsn": "https://...ingest.sentry.io/..."
5. Restart, trigger a test error, and check your Sentry Issues feed.

Use sentry-sdk >= 2.0 to avoid the Python 3.13 FrameLocalsProxy capture bug.
