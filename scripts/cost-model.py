"""Simulate a month of COGS at 100 / 1k / 10k users across a realistic
tier mix. Prints COGS per user per tier and the margin picture.

Run: python scripts/cost-model.py
"""

from dataclasses import dataclass

# ---- unit costs (cents, worst-case list prices) ------------------------------
EMBED_PER_ITEM = 0.01
BRIEF_PER_CLUSTER = 0.11          # haiku-class: ~1.8k in / 100 out
SUGGEST_PER_TAKE = 0.2
TEXT_VARIANT = 0.2
IMAGE = 4.0
TRANSCRIBE_PER_TAKE = 0.05
PUBLISH_ACTION = 10.0             # unified-API per-post amortisation + link premium
PROFILE_MONTH = 200.0             # per connected profile per month (falls with volume)
INFRA_BASE_MONTH = 8000.0         # VPS + DB + storage floor for the whole platform

# ---- corpus (shared — INDEPENDENT of user count) -----------------------------
ITEMS_PER_DAY = 4000
CLUSTERS_PER_DAY = 500
REBRIEF_RATE = 0.15


@dataclass
class TierProfile:
    name: str
    share: float               # of the user base
    price_cents: int           # monthly revenue
    active_days: int           # days used per month
    keeps_per_day: int
    takes_per_day: int
    variants: int
    images_per_take: int
    voice_share: float         # takes that arrive as audio
    short_videos_month: float  # user-requested — never automatic
    long_videos_month: float
    posts_month: int
    connected_profiles: float


TIERS = [
    TierProfile("free", 0.70, 0, 12, 6, 2, 1, 1, 0.2, 0, 0, 0, 0),
    TierProfile("pro", 0.25, 2900, 20, 10, 4, 3, 3, 0.3, 1.5, 0.1, 24, 2.2),
    TierProfile("byok", 0.05, 1500, 22, 10, 5, 3, 3, 0.3, 0, 0, 20, 1.8),
]

SHORT_VIDEO = 200.0   # 20s × 10¢
LONG_VIDEO = 1800.0


def corpus_cogs_month() -> float:
    daily = ITEMS_PER_DAY * EMBED_PER_ITEM + CLUSTERS_PER_DAY * (1 + REBRIEF_RATE) * BRIEF_PER_CLUSTER
    return daily * 30


def user_cogs_month(t: TierProfile) -> float:
    takes = t.takes_per_day * t.active_days
    gen = takes * (
        SUGGEST_PER_TAKE
        + t.variants * TEXT_VARIANT
        + t.images_per_take * IMAGE
        + t.voice_share * TRANSCRIBE_PER_TAKE
    )
    if t.name == "byok":
        gen = takes * t.voice_share * TRANSCRIBE_PER_TAKE  # generation on their keys
    video = t.short_videos_month * SHORT_VIDEO + t.long_videos_month * LONG_VIDEO
    if t.name == "byok":
        video = 0.0
    publishing = t.posts_month * PUBLISH_ACTION + t.connected_profiles * PROFILE_MONTH
    return gen + video + publishing


def run(total_users: int) -> None:
    print(f"\n===== {total_users:,} users =====")
    corpus = corpus_cogs_month()
    print(f"corpus (shared, fixed):        ${corpus / 100:>10,.2f} /mo "
          f"(${corpus / 100 / total_users:.4f}/user)")
    revenue = 0.0
    cogs = corpus + INFRA_BASE_MONTH
    print(f"infra floor:                   ${INFRA_BASE_MONTH / 100:>10,.2f} /mo")
    for t in TIERS:
        n = int(total_users * t.share)
        per_user = user_cogs_month(t)
        tier_total = per_user * n
        tier_rev = t.price_cents * n
        revenue += tier_rev
        cogs += tier_total
        print(f"{t.name:>5}: {n:>6,} users  "
              f"COGS ${per_user / 100:>7.2f}/user/mo  "
              f"revenue ${tier_rev / 100:>10,.2f}  "
              f"tier COGS ${tier_total / 100:>10,.2f}")
    margin = revenue - cogs
    pct = (margin / revenue * 100) if revenue else 0.0
    print(f"{'':>5}  revenue ${revenue / 100:>12,.2f}   COGS ${cogs / 100:>12,.2f}   "
          f"margin ${margin / 100:>12,.2f}  ({pct:.0f}%)")


if __name__ == "__main__":
    print("WIRE cost model — lazy generation, shared corpus")
    print("Key invariant: the corpus line does not move between runs.")
    for n in (100, 1_000, 10_000):
        run(n)
    print("\nSanity: the naive eager-video build costs ~$600/user/day — this "
          "model only works because video is a credit purchase, never a "
          "background job.")
