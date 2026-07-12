"""Shared pytest fixtures and import-time stubs for optional cloud deps."""

from __future__ import annotations

import sys
import types

google_mod = types.ModuleType("google")
google_auth_mod = types.ModuleType("google.auth")
google_auth_transport_mod = types.ModuleType("google.auth.transport")
google_auth_transport_requests_mod = types.ModuleType("google.auth.transport.requests")
google_auth_credentials_mod = types.ModuleType("google.auth.credentials")
google_cloud_mod = types.ModuleType("google.cloud")
google_cloud_storage_mod = types.ModuleType("google.cloud.storage")

google_auth_credentials_mod.Signing = type("Signing", (), {})
google_cloud_storage_mod.Client = type("Client", (), {})
google_auth_transport_requests_mod.Request = type("Request", (), {})

google_mod.auth = google_auth_mod
google_mod.cloud = google_cloud_mod
google_auth_mod.transport = google_auth_transport_mod
google_auth_mod.credentials = google_auth_credentials_mod
google_auth_transport_mod.requests = google_auth_transport_requests_mod
google_cloud_mod.storage = google_cloud_storage_mod

sys.modules.setdefault("google", google_mod)
sys.modules.setdefault("google.auth", google_auth_mod)
sys.modules.setdefault("google.auth.transport", google_auth_transport_mod)
sys.modules.setdefault(
    "google.auth.transport.requests", google_auth_transport_requests_mod
)
sys.modules.setdefault("google.auth.credentials", google_auth_credentials_mod)
sys.modules.setdefault("google.cloud", google_cloud_mod)
sys.modules.setdefault("google.cloud.storage", google_cloud_storage_mod)

# Minimal procrastinate stub when the package is not installed in the test env.
if "procrastinate" not in sys.modules:
    try:
        import procrastinate  # noqa: F401
    except ModuleNotFoundError:
        procrastinate_mod = types.ModuleType("procrastinate")

        class _PsycopgConnector:
            def __init__(self, *, conninfo: str) -> None:
                self.conninfo = conninfo

        class _App:
            def __init__(self, *, connector: _PsycopgConnector) -> None:
                self.connector = connector

            def task(self, *, name: str, retry: int = 0):
                def decorator(fn):
                    async def wrapper(*args, **kwargs):
                        return await fn(*args, **kwargs)

                    wrapper.defer_async = lambda **kwargs: None
                    wrapper.__name__ = fn.__name__
                    return wrapper

                return decorator

            def open_async(self):
                class _Ctx:
                    async def __aenter__(self_inner):
                        return self

                    async def __aexit__(self_inner, *args):
                        return None

                return _Ctx()

        procrastinate_mod.App = _App
        procrastinate_mod.PsycopgConnector = _PsycopgConnector
        sys.modules["procrastinate"] = procrastinate_mod
