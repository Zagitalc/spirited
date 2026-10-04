"""Every number the loop generator uses, in one place.

All of these are first guesses, set before anyone has looked at a real loop. Change
them here after looking at real loops, and say why in docs/decisions.md.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LoopConfig:
    # Real drives are slower than Valhalla's free-flow times: real speed as a share of it.
    speed_factor: float = 0.85
    # A loop must take the requested time, give or take this share.
    tolerance: float = 0.15
    # Shares of a loop's length on each kind of road (see spirited.loops.generate.Group).
    min_recommended_share: float = 0.55
    max_not_recommended_share: float = 0.15
    max_not_recommended_run_km: float = 2.0
    max_built_up_share: float = 0.30
    # Built-up road in the first and last this many km of a loop is left out of the share
    # checks: most people live in a town and must leave it, and that is not the drive.
    # The shares reported with a loop still count every kilometre.
    town_allowance_km: float = 4.0
    # Share of a loop that may repeat a way it has already used.
    max_reuse_share: float = 0.10
    # A loop must stay this many degrees inside the edge of the data.
    edge_margin_deg: float = 0.02
    # Waypoints are chosen inside the isochrone at this share of the target (Valhalla) time.
    isochrone_share: float = 0.4
    anchor_min_length_m: float = 2000.0
    anchor_min_separation_m: float = 3000.0
    max_anchors: int = 16
    max_anchors_per_corridor: int = 3
    # Candidates routed per request, and how far a candidate's raw estimated time may
    # stray from the target before it is kept as a candidate at all. The estimate comes
    # from a time matrix of shortest routes; real loops run well over it (see below), so
    # far more is allowed below the target than above it.
    max_candidates: int = 100
    planning_below: float = 0.45
    planning_above: float = 0.15
    # Routed time over the matrix's estimate. Measured medians were 1.24, 1.25 (first runs)
    # and 1.09 to 1.15 (later ones), with single loops anywhere from 1.0 to over 2. The
    # prior orders candidates; a candidate is routed unless it misses the time even at the
    # low or the high end.
    detour_prior: float = 1.25
    detour_low: float = 1.0
    detour_high: float = 1.7
    # Later legs steer clear of roads earlier legs used (except near the leg's own ends):
    # a point every `avoid_spacing_m` along them, at most `max_avoid` points.
    avoid_clearance_m: float = 1500.0
    avoid_spacing_m: float = 800.0
    max_avoid: int = 50
    # Two anchors of a loop must lie at least this far apart as seen from the start.
    min_bearing_gap_deg: float = 45.0
    # Loops sharing more than this share of their ways count as the same loop.
    duplicate_overlap: float = 0.6
    # From this target time (in Valhalla minutes) three waypoints are tried as well as two.
    three_waypoints_from_min: float = 55.0
