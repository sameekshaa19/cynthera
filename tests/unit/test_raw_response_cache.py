"""Unit tests for RawResponseCache."""
import os
import tempfile
import time
import pytest

from backend.infrastructure.cache.raw_response_cache import RawResponseCache, TTL_STRUCTURAL


def test_raw_response_cache_lifecycle():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = os.path.join(tmpdir, "test_cache.db")
        cache = RawResponseCache(db_path=db_path)

        key = cache.make_key("chembl_activity", "CHEMBL468", "activity", {"limit": 50})
        payload = {"activities": [{"act_id": 1, "value": 10.5}]}

        # Cache miss
        assert cache.get(key, source_name="chembl_activity") is None

        # Cache set
        cache.set(key, "chembl_activity", "CHEMBL468", "activity", payload, ttl_seconds=3600)

        # Cache hit
        cached = cache.get(key, source_name="chembl_activity")
        assert cached == payload

        # Stats verify
        stats = cache.stats()
        assert stats["total_entries"] == 1
        assert stats["total_cache_hits"] == 1


def test_raw_response_cache_expiry():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = os.path.join(tmpdir, "test_cache.db")
        cache = RawResponseCache(db_path=db_path)

        key = cache.make_key("test_source", "ID123", "endpoint")
        payload = {"data": "test"}

        # Set with 1-second TTL
        cache.set(key, "test_source", "ID123", "endpoint", payload, ttl_seconds=1)
        assert cache.get(key) == payload

        # Wait for expiry
        time.sleep(1.1)

        # Cache miss on expired item
        assert cache.get(key) is None
