"""Statistical significance testing for experiment variants.

For each non-control variant we run both a Welch's two-sample t-test and a
Mann-Whitney U test against the control's samples for the primary metric, and
report whichever is more appropriate alongside the raw numbers so the
dashboard can show its work. We also compute a 95%-style CI for the
difference in means and the minimum detectable effect (MDE) given the
current sample size, so users can see how far they are from being able to
detect a real difference at all.
"""
import math
from dataclasses import dataclass, field

from scipy import stats


@dataclass
class VariantStats:
    variant_id: str
    name: str
    is_control: bool
    n: int
    mean: float
    std: float


@dataclass
class ComparisonResult:
    variant_id: str
    variant_name: str
    control_id: str
    n_variant: int
    n_control: int
    mean_variant: float
    mean_control: float
    diff: float
    diff_ci_low: float
    diff_ci_high: float
    p_value_ttest: float
    p_value_mannwhitney: float
    significant: bool
    favors_variant: bool
    minimum_detectable_effect: float


def describe(values: list[float]) -> tuple[int, float, float]:
    n = len(values)
    if n == 0:
        return 0, 0.0, 0.0
    mean = sum(values) / n
    if n < 2:
        return n, mean, 0.0
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    return n, mean, math.sqrt(variance)


def minimum_detectable_effect(std_control: float, n_control: int, n_variant: int, alpha: float = 0.05, power: float = 0.8) -> float:
    if n_control < 2 or n_variant < 2 or std_control == 0:
        return float("inf")
    z_alpha = stats.norm.ppf(1 - alpha / 2)
    z_beta = stats.norm.ppf(power)
    pooled_n = (n_control + n_variant) / 2
    se = std_control * math.sqrt(2 / pooled_n)
    return (z_alpha + z_beta) * se


def compare_variant_to_control(
    control_values: list[float],
    variant_id: str,
    variant_name: str,
    control_id: str,
    variant_values: list[float],
    alpha: float,
    higher_is_better: bool,
) -> ComparisonResult:
    n_c, mean_c, std_c = describe(control_values)
    n_v, mean_v, std_v = describe(variant_values)

    diff = mean_v - mean_c

    if n_c >= 2 and n_v >= 2:
        t_res = stats.ttest_ind(variant_values, control_values, equal_var=False)
        p_ttest = float(t_res.pvalue)
        try:
            u_res = stats.mannwhitneyu(variant_values, control_values, alternative="two-sided")
            p_mw = float(u_res.pvalue)
        except ValueError:
            p_mw = 1.0

        se_diff = math.sqrt((std_v ** 2) / n_v + (std_c ** 2) / n_c)
        z = stats.norm.ppf(1 - alpha / 2)
        ci_low = diff - z * se_diff
        ci_high = diff + z * se_diff
    else:
        p_ttest, p_mw = 1.0, 1.0
        ci_low, ci_high = diff, diff

    significant = p_ttest < alpha and n_c >= 2 and n_v >= 2
    favors_variant = (diff > 0) if higher_is_better else (diff < 0)

    mde = minimum_detectable_effect(std_c, n_c, n_v, alpha=alpha)

    return ComparisonResult(
        variant_id=variant_id,
        variant_name=variant_name,
        control_id=control_id,
        n_variant=n_v,
        n_control=n_c,
        mean_variant=mean_v,
        mean_control=mean_c,
        diff=diff,
        diff_ci_low=ci_low,
        diff_ci_high=ci_high,
        p_value_ttest=p_ttest,
        p_value_mannwhitney=p_mw,
        significant=significant,
        favors_variant=favors_variant,
        minimum_detectable_effect=mde,
    )
