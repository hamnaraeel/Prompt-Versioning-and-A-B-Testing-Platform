import random

from app.services import stats_engine


def test_no_effect_is_not_significant():
    random.seed(42)
    control = [random.gauss(0.5, 0.1) for _ in range(200)]
    variant = [random.gauss(0.5, 0.1) for _ in range(200)]

    result = stats_engine.compare_variant_to_control(
        control_values=control,
        variant_id="v",
        variant_name="v",
        control_id="c",
        variant_values=variant,
        alpha=0.05,
        higher_is_better=True,
    )
    assert result.significant is False


def test_large_effect_is_significant():
    random.seed(7)
    control = [random.gauss(0.5, 0.05) for _ in range(200)]
    variant = [random.gauss(0.8, 0.05) for _ in range(200)]

    result = stats_engine.compare_variant_to_control(
        control_values=control,
        variant_id="v",
        variant_name="v",
        control_id="c",
        variant_values=variant,
        alpha=0.05,
        higher_is_better=True,
    )
    assert result.significant is True
    assert result.favors_variant is True
    assert result.p_value_ttest < 0.05
    assert result.diff > 0.2


def test_minimum_detectable_effect_shrinks_with_sample_size():
    small_mde = stats_engine.minimum_detectable_effect(std_control=0.1, n_control=20, n_variant=20)
    large_mde = stats_engine.minimum_detectable_effect(std_control=0.1, n_control=2000, n_variant=2000)
    assert large_mde < small_mde


def test_favors_variant_respects_metric_direction():
    random.seed(3)
    control = [100.0 + random.gauss(0, 2) for _ in range(50)]
    variant = [80.0 + random.gauss(0, 2) for _ in range(50)]  # lower latency is better

    result = stats_engine.compare_variant_to_control(
        control_values=control,
        variant_id="v",
        variant_name="v",
        control_id="c",
        variant_values=variant,
        alpha=0.05,
        higher_is_better=False,
    )
    assert result.favors_variant is True
