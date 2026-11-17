"""
SupeRR Selector Season 2 - Pressure Context Engine
Defines and calculates match pressure scores for every delivery,
building the enriched delivery-level dataset used for player evaluation.
"""

import sqlite3
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

# Bowler wicket types (not run-outs, retired, etc.)
BOWLER_WICKET_TYPES = {'Caught', 'Bowled', 'LBW', 'Stump', 'Hit Wicket'}

# Extra types that penalize the bowler
BOWLER_EXTRA_TYPES = {'wide', 'Overstep'}

# Extra types that add to team total but NOT bowler (byes, leg-byes)
FIELDING_EXTRA_TYPES = {'byes', 'legbyes', 'other', 'Penalty'}


def compute_ball_runs(extras_type: str, runs: int, extras_2_runs: int) -> int:
    """Total runs scored off this delivery (adds to team score)."""
    if extras_type in BOWLER_EXTRA_TYPES | FIELDING_EXTRA_TYPES:
        return runs + 1 + extras_2_runs
    return runs + extras_2_runs


def compute_bowler_runs(extras_type: str, runs: int, extras_2_runs: int) -> int:
    """Runs attributed to the bowler (economy rate calculation)."""
    if extras_type in BOWLER_EXTRA_TYPES:
        return runs + 1 + extras_2_runs
    if extras_type in FIELDING_EXTRA_TYPES:
        return 0  # byes/legbyes not charged to bowler
    return runs


def is_legal_ball(extras_type: str) -> int:
    """1 if counts as a legal ball (for economy/bowling SR)."""
    return 0 if extras_type in BOWLER_EXTRA_TYPES else 1


def compute_pressure_score(
    innings: int,
    overid: int,
    cum_runs_before: int,
    cum_wkts_before: int,
    cum_legal_before: int,
    target: int | None,
    is_knockout: int
) -> float:
    """
    Pressure Score (0–1): Quantifies match-state pressure at the moment of delivery.

    Framework:
    - Innings 2 (Chase): Modeled using required run rate (RRR), endgame proximity,
      and wickets in hand.
    - Innings 1 (Target-Setting): Modeled using collapse state, phase criticality.
    - Super Over: Maximum pressure (1.0).
    - Knockout matches: 15% amplification (capped at 1.0).
    """
    if innings in (3, 4):
        return 1.0  # Super Over

    balls_rem = max(0, 120 - cum_legal_before)
    wkts_in_hand = max(0, 10 - cum_wkts_before)

    if innings == 2 and target is not None:
        runs_needed = max(0, target - cum_runs_before)

        if runs_needed <= 0:
            p = 0.10  # Match already won
        elif balls_rem == 0:
            p = 0.10 if runs_needed > 0 else 0.10
        else:
            rrr = (runs_needed * 6.0) / balls_rem
            if balls_rem <= 6 and runs_needed > 36:
                p = 0.20  # Lost cause
            else:
                rrr_factor = min(1.0, max(0.0, (rrr - 6.0) / 10.0))
                endgame_factor = (120 - balls_rem) / 120.0
                wkt_factor = (10 - wkts_in_hand) / 9.0
                p = (
                    0.45 * rrr_factor +
                    0.30 * (rrr_factor * endgame_factor) +
                    0.25 * wkt_factor
                )
    else:
        # Innings 1: target-setting pressure
        is_collapse = (
            (overid <= 6 and cum_wkts_before >= 3) or
            (overid <= 10 and cum_wkts_before >= 4) or
            (overid <= 15 and cum_wkts_before >= 5)
        )
        is_death = overid >= 16

        if is_collapse:
            p = 0.65 + 0.05 * min(5, cum_wkts_before - 2)
        elif is_death:
            p = 0.60 + 0.10 * (overid - 16) / 4.0
        else:
            p = 0.25 + 0.05 * cum_wkts_before

    if is_knockout:
        p = min(1.0, p * 1.15)

    return round(p, 4)


def build_pressure_context(conn: sqlite3.Connection):
    """
    Builds the `match_deliveries` table: every delivery enriched with:
      - match context (comp_id, stage, knockout flag)
      - match state (cum_runs, cum_wkts, target, balls_remaining)
      - pressure score and high_pressure flag
      - runs above/below expected (using context-specific benchmarks)
    """
    cur = conn.cursor()
    cur.execute("PRAGMA synchronous = OFF")
    cur.execute("PRAGMA journal_mode = MEMORY")

    # -- Fetch match metadata
    logger.info("Fetching match metadata...")
    matches_meta = {}
    cur.execute("SELECT match_id, comp_id, stage, knock_out, revised_target FROM matches")
    for m_id, c_id, stg, ko, rt in cur.fetchall():
        is_ko = 1 if (ko == 1 or stg in ('Final', 'Qualifier', 'Eliminator', 'Semi Final')) else 0
        matches_meta[m_id] = {
            'comp_id': c_id, 'stage': stg,
            'knock_out': is_ko,
            'revised_target': int(rt) if rt and rt.isdigit() else None
        }

    # -- Fetch all balls ordered
    logger.info("Fetching all deliveries...")
    cur.execute("""
        SELECT match_id, innings, overid, over_ball_num, innings_ball_num,
               batting_team_id, bowling_team_id, striker_id, striker_name,
               bowler_id, bowler_name, runs, is_four, is_six, is_wicket,
               dismissal_type, extras_type, extras_2_runs
        FROM ball_by_ball
        ORDER BY match_id, innings, innings_ball_num
    """)
    all_balls = cur.fetchall()
    logger.info(f"Loaded {len(all_balls):,} deliveries")

    # -- Group by match + innings
    match_innings = defaultdict(lambda: defaultdict(list))
    for b in all_balls:
        match_innings[b[0]][b[1]].append(b)

    # -- Build enriched rows
    logger.info("Computing pressure context for all deliveries...")
    rows = []
    for m_id, innings_dict in match_innings.items():
        meta = matches_meta.get(m_id, {'comp_id': 0, 'stage': 'League', 'knock_out': 0, 'revised_target': None})
        is_ko = meta['knock_out']

        # Compute Innings 1 total to derive target for Innings 2
        inn1_total = 0
        if 1 in innings_dict:
            for b in innings_dict[1]:
                inn1_total += compute_ball_runs(b[16], b[11], b[17])

        for inn, balls in innings_dict.items():
            if inn == 2:
                target = meta['revised_target'] if meta['revised_target'] else (inn1_total + 1 if inn1_total > 0 else 175)
            else:
                target = None

            cum_runs = cum_wkts = cum_legal = 0

            for b in balls:
                (m_id_b, innings, overid, obn, ibn,
                 bat_tid, bow_tid, str_id, str_name,
                 bow_id, bow_name, runs, is_four, is_six, is_wicket,
                 dismissal_type, extras_type, extras_2_runs) = b

                is_legal = is_legal_ball(extras_type)
                ball_runs = compute_ball_runs(extras_type, runs, extras_2_runs)
                b_runs = compute_bowler_runs(extras_type, runs, extras_2_runs)
                is_b_wkt = 1 if (is_wicket == 'true' and dismissal_type in BOWLER_WICKET_TYPES) else 0

                # State BEFORE delivery
                cr_before = cum_runs
                cw_before = cum_wkts
                cl_before = cum_legal

                # Update state
                cum_runs += ball_runs
                if is_wicket == 'true':
                    cum_wkts += 1
                if is_legal:
                    cum_legal += 1

                balls_rem = max(0, 120 - cl_before)
                wkts_in_hand = max(0, 10 - cw_before)

                p = compute_pressure_score(inn, overid, cr_before, cw_before, cl_before, target, is_ko)
                is_hp = 1 if p >= 0.60 else 0

                rn = target - cr_before if (inn == 2 and target) else None
                rrr = (rn * 6.0 / balls_rem) if (rn is not None and balls_rem > 0) else None

                rows.append((
                    m_id, inn, overid, obn, ibn,
                    meta['comp_id'], meta['stage'], is_ko,
                    bat_tid, bow_tid,
                    str_id, str_name, bow_id, bow_name,
                    runs, is_four, is_six, is_wicket, dismissal_type,
                    extras_type, extras_2_runs, is_legal, ball_runs,
                    b_runs, is_b_wkt, cr_before, cw_before,
                    cl_before, target, rn, balls_rem,
                    rrr, wkts_in_hand, p, is_hp
                ))

    logger.info(f"Computed context for {len(rows):,} deliveries")

    # -- Write to table
    cur.execute("DROP TABLE IF EXISTS match_deliveries")
    cur.execute("""
        CREATE TABLE match_deliveries (
            match_id INTEGER, innings INTEGER,
            overid INTEGER, over_ball_num INTEGER, innings_ball_num INTEGER,
            comp_id INTEGER, stage TEXT, knock_out INTEGER,
            batting_team_id INTEGER, bowling_team_id INTEGER,
            striker_id INTEGER, striker_name TEXT,
            bowler_id INTEGER, bowler_name TEXT,
            runs INTEGER, is_four TEXT, is_six TEXT,
            is_wicket TEXT, dismissal_type TEXT,
            extras_type TEXT, extras_2_runs INTEGER,
            legal_ball INTEGER, ball_runs INTEGER,
            bowler_runs INTEGER, is_bowler_wicket INTEGER,
            cum_runs_before INTEGER, cum_wickets_before INTEGER,
            cum_legal_balls_before INTEGER,
            target INTEGER, runs_needed INTEGER, balls_remaining INTEGER,
            rrr REAL, wickets_in_hand INTEGER,
            pressure_score REAL, is_high_pressure INTEGER
        )
    """)
    cur.executemany("INSERT INTO match_deliveries VALUES (" + ",".join(["?"] * 35) + ")", rows)
    cur.execute("CREATE INDEX idx_md_striker_hp ON match_deliveries (striker_id, is_high_pressure)")
    cur.execute("CREATE INDEX idx_md_bowler_hp ON match_deliveries (bowler_id, is_high_pressure)")
    cur.execute("CREATE INDEX idx_md_comp ON match_deliveries (comp_id)")
    conn.commit()
    logger.info("match_deliveries table built and indexed.")


def build_context_benchmarks(conn: sqlite3.Connection):
    """
    Computes expected values per delivery by (comp_group, phase, is_high_pressure).
    Used to calculate runs above/below expectation for each batter/bowler.
    """
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS context_benchmarks")
    cur.execute("""
        CREATE TABLE context_benchmarks AS
        SELECT 
            CASE WHEN c.match_format = 'T20' AND (c.comp_name LIKE '%IPL%' OR c.comp_name LIKE '%Indian Premier%') THEN 'IPL'
                 WHEN c.match_format = 'T20I' THEN 'T20I'
                 ELSE 'Other' END AS comp_group,
            CASE WHEN md.overid <= 6 THEN 'Powerplay'
                 WHEN md.overid <= 15 THEN 'Middle'
                 ELSE 'Death' END AS phase,
            md.is_high_pressure,
            COUNT(*) AS total_balls,
            COUNT(CASE WHEN md.legal_ball = 1 THEN 1 END) AS legal_balls,
            AVG(md.runs * 1.0) AS exp_runs,
            AVG(CASE WHEN md.legal_ball = 1 THEN md.bowler_runs ELSE 0 END * 1.0) AS exp_bowler_runs,
            AVG(CASE WHEN md.is_wicket = 'true' THEN 1.0 ELSE 0.0 END) AS exp_dismissal_prob,
            AVG(CASE WHEN md.is_bowler_wicket = 1 THEN 1.0 ELSE 0.0 END) AS exp_bowler_wkt_prob
        FROM match_deliveries md
        JOIN competitions c ON md.comp_id = c.comp_id
        GROUP BY comp_group, phase, md.is_high_pressure
    """)
    conn.commit()
    logger.info("context_benchmarks table built.")


def build_delivery_with_expected(conn: sqlite3.Connection):
    """
    Joins match_deliveries with context_benchmarks to annotate each delivery
    with actual vs. expected values (runs above expectation, wicket probability, etc.)
    """
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS delivery_with_expected")
    cur.execute("""
        CREATE TABLE delivery_with_expected AS
        SELECT
            md.*,
            cb.exp_runs,
            cb.exp_bowler_runs,
            cb.exp_dismissal_prob,
            cb.exp_bowler_wkt_prob,
            (md.runs - cb.exp_runs) AS batter_runs_above_exp,
            (cb.exp_dismissal_prob - CASE WHEN md.is_wicket = 'true' THEN 1.0 ELSE 0.0 END) AS wkt_avoided_above_exp,
            (cb.exp_bowler_runs - CASE WHEN md.legal_ball = 1 THEN md.bowler_runs ELSE 0 END) AS bowler_runs_saved,
            (md.is_bowler_wicket - cb.exp_bowler_wkt_prob) AS bowler_wkt_above_exp
        FROM match_deliveries md
        JOIN context_benchmarks cb
            ON (CASE WHEN md.comp_id IN (1358, 1715, 2193, 2725, 3298) THEN 'IPL'
                     WHEN md.comp_id IN (SELECT comp_id FROM competitions WHERE match_format = 'T20I') THEN 'T20I'
                     ELSE 'Other' END) = cb.comp_group
            AND (CASE WHEN md.overid <= 6 THEN 'Powerplay'
                      WHEN md.overid <= 15 THEN 'Middle'
                      ELSE 'Death' END) = cb.phase
            AND md.is_high_pressure = cb.is_high_pressure
    """)
    cur.execute("CREATE INDEX idx_dwe_striker ON delivery_with_expected (striker_id, is_high_pressure)")
    cur.execute("CREATE INDEX idx_dwe_bowler ON delivery_with_expected (bowler_id, is_high_pressure)")
    conn.commit()
    logger.info("delivery_with_expected table built.")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from data_loader import get_connection, load_all

    load_all()
    conn = get_connection()
    build_pressure_context(conn)
    build_context_benchmarks(conn)
    build_delivery_with_expected(conn)
    conn.close()
    logger.info("Pressure context pipeline complete.")
