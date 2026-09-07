from app.services.traffic_splitter import choose_variant


def test_same_user_always_gets_same_variant():
    variants = [
        {"id": "a", "traffic_pct": 50},
        {"id": "b", "traffic_pct": 50},
    ]
    for user in ["alice", "bob", "carol", "dave-1234"]:
        first = choose_variant("exp-1", user, variants)
        for _ in range(20):
            again = choose_variant("exp-1", user, variants)
            assert again["id"] == first["id"]


def test_distribution_roughly_matches_traffic_split():
    variants = [
        {"id": "a", "traffic_pct": 80},
        {"id": "b", "traffic_pct": 20},
    ]
    counts = {"a": 0, "b": 0}
    n = 5000
    for i in range(n):
        chosen = choose_variant("exp-2", f"user-{i}", variants)
        counts[chosen["id"]] += 1

    assert abs(counts["a"] / n - 0.8) < 0.03
    assert abs(counts["b"] / n - 0.2) < 0.03


def test_different_experiments_reshuffle_independently():
    variants = [{"id": "a", "traffic_pct": 50}, {"id": "b", "traffic_pct": 50}]
    a1 = choose_variant("exp-1", "same-user", variants)
    a2 = choose_variant("exp-2", "same-user", variants)
    # not asserting they differ (could coincide), just that both are valid variants
    assert a1["id"] in ("a", "b")
    assert a2["id"] in ("a", "b")
