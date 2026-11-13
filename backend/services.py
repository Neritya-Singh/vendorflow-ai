"""Factory for the UNMODIFIED v1.1 services (or the explicit offline doubles)."""
from __future__ import annotations

import threading

from vendorflow.gemini_extractor import GeminiExtractor
from vendorflow.persistence import PersistentVendorService, SupabaseRepository

from .config import Settings
from .offline import InMemorySupabase, OfflineLabelExtractor


class ServiceProvider:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = threading.Lock()
        self._offline_client = InMemorySupabase() if settings.offline_mode else None
        self._repo: SupabaseRepository | None = None

    def repo(self) -> SupabaseRepository:
        if self._offline_client is not None:
            return SupabaseRepository(self._offline_client)
        with self._lock:
            if self._repo is None:
                # Raises PersistenceError with a safe message when unconfigured.
                self._repo = SupabaseRepository.from_env()
            return self._repo

    def extractor(self):
        if self.settings.offline_mode and self.settings.offline_extractor != "gemini":
            return OfflineLabelExtractor()
        # A fresh extractor per evaluation: diagnostics are per-request state.
        return GeminiExtractor()

    def service(self) -> PersistentVendorService:
        return PersistentVendorService(self.repo(), self.extractor())
