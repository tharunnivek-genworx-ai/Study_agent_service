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
