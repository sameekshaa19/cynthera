"""
Cache manager for storing API responses locally.
Reduces API calls and improves performance.
"""
import json
import hashlib
from pathlib import Path
from typing import Any, Optional
from datetime import datetime, timedelta
import os

from utils.logger import get_logger

logger = get_logger(__name__)


class CacheManager:
    """Simple file-based cache for API responses."""
    
    def __init__(self, cache_dir: str = "./cache", ttl_seconds: int = 86400):
        """
        Initialize cache manager.
        
        Args:
            cache_dir: Directory to store cache files
            ttl_seconds: Time-to-live for cache entries (default: 24 hours)
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds
    
    def _get_cache_key(self, key: str) -> str:
        """Generate cache file name from key."""
        return hashlib.md5(key.encode()).hexdigest()
    
    def _get_cache_path(self, key: str) -> Path:
        """Get full path to cache file."""
        cache_key = self._get_cache_key(key)
        return self.cache_dir / f"{cache_key}.json"
    
    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve value from cache.
        
        Args:
            key: Cache key
        
        Returns:
            Cached value or None if not found/expired
        """
        cache_path = self._get_cache_path(key)
        
        if not cache_path.exists():
            return None
        
        try:
            with open(cache_path, 'r') as f:
                cache_data = json.load(f)
            
            # Check if expired
            cached_at = datetime.fromisoformat(cache_data['cached_at'])
            if datetime.now() - cached_at > timedelta(seconds=self.ttl_seconds):
                logger.debug(f"Cache expired for key: {key}")
                cache_path.unlink()  # Delete expired cache
                return None
            
            logger.debug(f"Cache hit for key: {key}")
            return cache_data['value']
        
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Error reading cache for key {key}: {e}")
            return None
    
    def set(self, key: str, value: Any) -> None:
        """
        Store value in cache.
        
        Args:
            key: Cache key
            value: Value to cache (must be JSON serializable)
        """
        cache_path = self._get_cache_path(key)
        
        cache_data = {
            'key': key,
            'value': value,
            'cached_at': datetime.now().isoformat()
        }
        
        try:
            with open(cache_path, 'w') as f:
                json.dump(cache_data, f)
            logger.debug(f"Cached value for key: {key}")
        except (TypeError, ValueError) as e:
            logger.error(f"Error caching value for key {key}: {e}")
    
    def clear(self) -> None:
        """Clear all cache files."""
        for cache_file in self.cache_dir.glob("*.json"):
            cache_file.unlink()
        logger.info("Cache cleared")
    
    def clear_expired(self) -> int:
        """
        Remove expired cache entries.
        
        Returns:
            Number of entries removed
        """
        removed = 0
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                with open(cache_file, 'r') as f:
                    cache_data = json.load(f)
                
                cached_at = datetime.fromisoformat(cache_data['cached_at'])
                if datetime.now() - cached_at > timedelta(seconds=self.ttl_seconds):
                    cache_file.unlink()
                    removed += 1
            except Exception as e:
                logger.error(f"Error checking cache file {cache_file}: {e}")
        
        logger.info(f"Removed {removed} expired cache entries")
        return removed
