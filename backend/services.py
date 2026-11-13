"""Factory for the v1.1 services with the v2 policy hooks (or the explicit offline doubles)."""
from __future__ import annotations

import threading

from vendorflow import v2_policy as v2
from vendorflow.gemini_extractor import GeminiExtractor
from vendorflow.persistence import DocumentCache, PersistentVendorService, SupabaseRepository
from vendorflow.v2_intake import DraftService

from .config import Settings
from .offline import InMemorySupabase, OfflineLabelExtractor


class ServiceProvider:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = threading.Lock()
        self._offline_client = InMemorySupabase() if settings.offline_mode else None
        self._repo: SupabaseRepository | None = None
        # One cache of verified document bytes per process (see DocumentCache).
        self.document_cache = DocumentCache()

    def repo(self) -> SupabaseRepository:
        if self._offline_client is not None:
            return SupabaseRepository(self._offline_client, self.document_cache)
        with self._lock:
            if self._repo is None:
                # Raises PersistenceError with a safe message when unconfigured.
                self._repo = SupabaseRepository.from_env()
                self._repo.cache = self.document_cache
            return self._repo

    def extractor(self):
        if self.settings.offline_mode and self.settings.offline_extractor != "gemini":
            return OfflineLabelExtractor()
        # A fresh extractor per evaluation: diagnostics are per-request state.
        return GeminiExtractor()

    def service(self) -> PersistentVendorService:
        repo = self.repo()
        # v2 policy hooks: records screening across all statuses + bank reuse, and
        # legal-suffix name equivalence for the GST name vs bank holder check.
        return PersistentVendorService(repo, self.extractor(), pipeline_options=v2.pipeline_options(repo))

    def drafts(self) -> DraftService:
        """B5 upload-first drafts: one provider call per file, reused on submit."""
        repo = self.repo()
        return DraftService(repo, self.extractor, pipeline_options=v2.pipeline_options(repo))
