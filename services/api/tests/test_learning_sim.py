"""Simulation: a synthetic user with a fixed hidden preference function.

200 swipes; the ranker's agreement with the hidden preference must climb.
Runs entirely in numpy against the same update rule the API uses — no DB.
"""

import numpy as np

DIM = 64
RNG = np.random.default_rng(7)


def normalise(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n else v


def apply_update(interest: np.ndarray, item: np.ndarray, liked: bool) -> np.ndarray:
    """Mirror of wire_api.learning.taste — asymmetric learning rates."""
    if liked:
        updated = interest + 0.08 * (item - interest)
    else:
        updated = interest - 0.03 * item
    return normalise(updated)


def test_ranker_agreement_climbs_over_200_swipes() -> None:
    hidden = normalise(RNG.normal(0, 1, DIM))  # the user's true taste
    interest = np.zeros(DIM)

    agreements: list[float] = []
    for _ in range(200):
        # a fresh pool of 20 candidate briefings each round
        pool = [normalise(RNG.normal(0, 1, DIM)) for _ in range(20)]
        # ranker's pick: best by current interest vector (cold start: random)
        if np.linalg.norm(interest) == 0:
            pick_idx = 0
        else:
            pick_idx = int(np.argmax([np.dot(interest, p) for p in pool]))
        # hidden preference decides the swipe
        liked = np.dot(hidden, pool[pick_idx]) > 0
        interest = apply_update(interest, pool[pick_idx], liked)
        agreements.append(float(np.dot(interest, hidden)))

    early = float(np.mean(agreements[:20]))
    mid = float(np.mean(agreements[90:110]))
    late = float(np.mean(agreements[-20:]))

    # monotone improvement across thirds, and meaningful final alignment
    assert early < mid < late, (early, mid, late)
    assert late > 0.5, f"final alignment too weak: {late:.3f}"


def test_dislike_is_weaker_than_like() -> None:
    item = normalise(RNG.normal(0, 1, DIM))
    base = normalise(RNG.normal(0, 1, DIM))
    liked = apply_update(base.copy(), item, liked=True)
    disliked = apply_update(base.copy(), item, liked=False)
    like_shift = float(np.linalg.norm(liked - base))
    dislike_shift = float(np.linalg.norm(disliked - base))
    assert like_shift > dislike_shift
