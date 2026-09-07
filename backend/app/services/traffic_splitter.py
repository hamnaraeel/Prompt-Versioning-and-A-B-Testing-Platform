import hashlib

BUCKET_COUNT = 10_000


def bucket_for(experiment_id: str, user_key: str) -> int:
    """Deterministic bucket in [0, BUCKET_COUNT) for a given experiment/user pair.

    Consistent hashing means the same user always lands in the same bucket for a
    given experiment, so repeat requests always resolve to the same variant.
    """
    digest = hashlib.md5(f"{experiment_id}:{user_key}".encode("utf-8")).hexdigest()
    return int(digest, 16) % BUCKET_COUNT


def choose_variant(experiment_id: str, user_key: str, variants: list[dict]) -> dict:
    """variants: list of {"id": ..., "traffic_pct": float}. Percentages need not be
    normalized to exactly 100; they are normalized here. Cumulative ranges are built
    in a stable order (by id) so the mapping doesn't shift if callers pass variants
    in a different order.
    """
    ordered = sorted(variants, key=lambda v: v["id"])
    total_pct = sum(v["traffic_pct"] for v in ordered) or 1.0
    bucket = bucket_for(experiment_id, user_key)
    target = bucket / BUCKET_COUNT * total_pct

    cumulative = 0.0
    for variant in ordered:
        cumulative += variant["traffic_pct"]
        if target < cumulative:
            return variant
    return ordered[-1]
