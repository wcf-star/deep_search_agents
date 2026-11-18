from utils.cache import ttl_cache


def test_ttl_cache_reuses_result():
    calls = {"n": 0}

    @ttl_cache(ttl_seconds=100)
    def f(x):
        calls["n"] += 1
        return x * 2

    assert f(1) == 2
    assert f(1) == 2          # 命中缓存，不再执行
    assert calls["n"] == 1
    assert f(2) == 4          # 不同参数，重新执行
    assert calls["n"] == 2


def test_ttl_cache_distinguishes_kwargs():
    calls = {"n": 0}

    @ttl_cache(ttl_seconds=100)
    def f(a, b=0):
        calls["n"] += 1
        return a + b

    assert f(1, b=2) == 3
    assert f(1, b=3) == 4
    assert calls["n"] == 2


def test_ttl_zero_always_misses():
    calls = {"n": 0}

    @ttl_cache(ttl_seconds=0)
    def f(x):
        calls["n"] += 1
        return x

    f(1)
    f(1)
    assert calls["n"] == 2     # TTL=0 视为立即过期


def test_ttl_cache_caches_none():
    calls = {"n": 0}

    @ttl_cache(ttl_seconds=100)
    def f(x):
        calls["n"] += 1
        return None

    f(1)
    f(1)
    assert calls["n"] == 1     # None 也被缓存，不会重复调用


def test_ttl_cache_exposes_stats():
    @ttl_cache(ttl_seconds=100)
    def f(x):
        return x

    f(1)
    f(1)
    f(2)
    assert f.cache.hits == 1
    assert f.cache.misses == 2
