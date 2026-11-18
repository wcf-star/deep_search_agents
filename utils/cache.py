"""进程内 TTL 缓存：给昂贵的外部调用（如 Tavily 搜索）加缓存，降本 + 降延迟。

注意：这是单进程内存缓存。多 worker 部署时每个进程各自一份缓存，
它只是性能优化（不是正确性依赖）；要跨进程共享再换 Redis 后端。
"""
import hashlib
import json
import threading
import time

_SENTINEL = object()


class TTLCache:
    def __init__(self, ttl_seconds: int = 300, maxsize: int = 1024):
        self.ttl = ttl_seconds
        self.maxsize = maxsize
        self.hits = 0
        self.misses = 0
        self._store = {}  # key -> (expire_monotonic, value)
        self._lock = threading.Lock()

    @staticmethod
    def _make_key(fn_name: str, args, kwargs) -> str:
        payload = json.dumps([fn_name, args, kwargs], sort_keys=True, default=str, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, key):
        with self._lock:
            item = self._store.get(key)
            if item is None:
                self.misses += 1
                return _SENTINEL
            expire_at, value = item
            if time.monotonic() >= expire_at:
                self._store.pop(key, None)
                self.misses += 1
                return _SENTINEL
            self.hits += 1
            return value

    def set(self, key, value):
        with self._lock:
            self._evict_if_needed()
            self._store[key] = (time.monotonic() + self.ttl, value)

    def _evict_if_needed(self):
        if len(self._store) < self.maxsize:
            return
        now = time.monotonic()
        # 先清过期项
        self._store = {k: v for k, v in self._store.items() if now < v[0]}
        if len(self._store) >= self.maxsize:
            # 仍满则淘汰最旧（插入序第一个）
            self._store.pop(next(iter(self._store)), None)

    def clear(self):
        with self._lock:
            self._store.clear()

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return (self.hits / total) if total else 0.0


def ttl_cache(ttl_seconds: int = 300, maxsize: int = 1024):
    """装饰器：按「函数名 + 参数」哈希做进程内 TTL 缓存。

    - value 需可复用（返回后不再被修改）；返回可变对象时请在函数内做副本。
    - 缓存实例挂在 wrapper.cache 上，便于测试、统计命中率或手动 clear()。
    """
    cache = TTLCache(ttl_seconds=ttl_seconds, maxsize=maxsize)

    def decorator(fn):
        def wrapper(*args, **kwargs):
            key = TTLCache._make_key(fn.__name__, args, kwargs)
            hit = cache.get(key)
            if hit is not _SENTINEL:
                return hit
            result = fn(*args, **kwargs)
            cache.set(key, result)
            return result
        wrapper.cache = cache
        return wrapper
    return decorator
