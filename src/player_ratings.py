"""
SupeRR Selector Season 2 - Player Rating Engine

Computes the Batting Pressure Index (BPI) and Bowling Pressure Index (BWPI)
for all eligible players using a composite z-score rating model.

Methodology:
============
Batting Pressure Index (BPI):
  Measures a batter's performance during high-pressure moments relative to their
  own baseline and the competition-phase-pressure benchmark.

  Components (weighted):
    1. Total Value Added (TVA) under HP [28%]
       TVA = HP Runs Above Expected + 12 × (Wicket Avoidance Above Expected)
    2. TVA per 100 HP balls [25%]  → rate-based efficiency
    3. Delta Strike Rate (HP SR − Baseline SR) [20%]  → clutch elevation vs own form
    4. Win Contribution Rate (% matches with positive net impact) [15%]
    5. Average Net Match Impact [7%]
    6. Big Game Rate (% matches with NMI ≥ 10) [5%]
    × Credibility weight (sample-size Bayesian shrinkage)

Bowling Pressure Index (BWPI):
  Identical structure for bowlers, using:
    1. Total Value Saved (TVS) = Runs Saved + 12 × Wickets Above Expected [28%]
    2. TVS per 100 HP balls [25%]
    3. Economy Drop (Baseline Economy − HP Economy) [20%]
    4. Win Contribution Rate [15%]
    5. Average Net Match Impact [7%]
    6. Big Game Rate [5%]

Allrounder Pressure Index (API):
  Combined batting + bowling pressure score for dual-role players.

Eligibility thresholds:
  - Batters:  ≥100 HP balls faced, ≥100 baseline balls, ≥10 HP matches
  - Bowlers:  ≥100 HP legal balls bowled, ≥100 baseline balls, ≥10 HP matches
  - Allrounders: ≥50 HP balls in each role, ≥8 HP matches in each role

All ratings are scaled 0–100 (100 = best in dataset).
"""

import sqlite3
import statistics
import csv
import os
import logging

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "cricket_analytics.db")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "Data", "processed")

IPL_COMP_IDS = (1358, 1715, 2193, 2725, 3298)

# Minimum qualifying thresholds
BAT_MIN_HP_BALLS = 100
BAT_MIN_BASE_BALLS = 100
BAT_MIN_HP_MATCHES = 10
BOW_MIN_HP_BALLS = 100
BOW_MIN_BASE_BALLS = 100
BOW_MIN_HP_MATCHES = 10
AR_MIN_HP_BALLS = 50
AR_MIN_HP_MATCHES = 8


def _zscore(arr: list[float]) -> list[float]:
    m = statistics.mean(arr)
    s = statistics.stdev(arr) if len(arr) > 1 else 1.0
    return [(x - m) / s for x in arr]


def _normalize(scores: list[float], lo: float = 0.0, hi: float = 100.0) -> list[float]:
    mn, mx = min(scores), max(scores)
    span = mx - mn if mx != mn else 1.0
    return [round(lo + (hi - lo) * (s - mn) / span, 2) for s in scores]


def _cred(hp_balls: int, k: int = 50) -> float:
    """Empirical Bayes credibility weight: approaches 1.0 as sample size grows."""
    return hp_balls / (hp_balls + k)


def compute_batting_pressure_index(conn: sqlite3.Connection) -> list[dict]:
    """Compute BPI for all eligible batters."""
    cur = conn.cursor()

    # Aggregate delivery-level metrics per batter
    cur.execute("""
        WITH b_agg AS (
            SELECT
                striker_id as player_id, striker_name as player_name,
                COUNT(CASE WHEN is_high_pressure=1 THEN 1 END) as hp_balls,
                SUM(CASE WHEN is_high_pressure=1 THEN runs ELSE 0 END) as hp_runs,
                COUNT(CASE WHEN is_high_pressure=1 AND is_wicket='true' THEN 1 END) as hp_outs,
                COUNT(CASE WHEN is_high_pressure=1 AND is_four='true' THEN 1 END) as hp_fours,
                COUNT(CASE WHEN is_high_pressure=1 AND is_six='true' THEN 1 END) as hp_sixes,
                COUNT(CASE WHEN is_high_pressure=1 AND runs=0 AND extras_type='None' THEN 1 END) as hp_dots,
                SUM(CASE WHEN is_high_pressure=1 THEN batter_runs_above_exp ELSE 0 END) as hp_rae,
                SUM(CASE WHEN is_high_pressure=1 THEN wkt_avoided_above_exp ELSE 0 END) as hp_wae,
                SUM(CASE WHEN is_high_pressure=1 THEN (batter_runs_above_exp + 12.0*wkt_avoided_above_exp) ELSE 0 END) as hp_tva,
                -- By phase
                COUNT(CASE WHEN is_high_pressure=1 AND overid<=6 THEN 1 END) as hp_pp_balls,
                SUM(CASE WHEN is_high_pressure=1 AND overid<=6 THEN runs ELSE 0 END) as hp_pp_runs,
                COUNT(CASE WHEN is_high_pressure=1 AND overid>=16 THEN 1 END) as hp_death_balls,
                SUM(CASE WHEN is_high_pressure=1 AND overid>=16 THEN runs ELSE 0 END) as hp_death_runs,
                -- Knockout
                COUNT(CASE WHEN is_high_pressure=1 AND knock_out=1 THEN 1 END) as ko_hp_balls,
                SUM(CASE WHEN is_high_pressure=1 AND knock_out=1 THEN runs ELSE 0 END) as ko_hp_runs,
                -- Baseline
                COUNT(CASE WHEN is_high_pressure=0 THEN 1 END) as base_balls,
                SUM(CASE WHEN is_high_pressure=0 THEN runs ELSE 0 END) as base_runs,
                COUNT(CASE WHEN is_high_pressure=0 AND is_wicket='true' THEN 1 END) as base_outs,
                COUNT(DISTINCT match_id) as total_matches
            FROM delivery_with_expected
            GROUP BY striker_id, striker_name
            HAVING hp_balls >= ? AND base_balls >= ?
        ),
        b_match AS (
            SELECT striker_id,
                   COUNT(*) as hp_matches,
                   AVG(net_match_impact) as avg_nmi,
                   100.0*COUNT(CASE WHEN net_match_impact>0 THEN 1 END)/COUNT(*) as wcr,
                   100.0*COUNT(CASE WHEN net_match_impact>=10 THEN 1 END)/COUNT(*) as big_game_pct
            FROM batter_match_hp
            GROUP BY striker_id
        )
        SELECT b.*, m.hp_matches, m.avg_nmi, m.wcr, m.big_game_pct
        FROM b_agg b
        JOIN b_match m ON b.player_id = m.striker_id
        WHERE m.hp_matches >= ?
    """, (BAT_MIN_HP_BALLS, BAT_MIN_BASE_BALLS, BAT_MIN_HP_MATCHES))

    batters = []
    for r in cur.fetchall():
        (pid, pname,
         hp_b, hp_r, hp_o, hp_4, hp_6, hp_d, hp_rae, hp_wae, hp_tva,
         hp_pp_b, hp_pp_r, hp_death_b, hp_death_r,
         ko_b, ko_r,
         base_b, base_r, base_o, tm,
         hpm, avg_nmi, wcr, bgp) = r

        hp_sr = (hp_r * 100.0 / hp_b) if hp_b else 0
        base_sr = (base_r * 100.0 / base_b) if base_b else 0
        hp_avg = (hp_r / hp_o) if hp_o else float(hp_r)
        hp_tva_per_100 = (hp_tva * 100.0 / hp_b) if hp_b else 0
        hp_death_sr = (hp_death_r * 100.0 / hp_death_b) if hp_death_b else 0
        hp_pp_sr = (hp_pp_r * 100.0 / hp_pp_b) if hp_pp_b else 0

        batters.append({
            'player_id': pid, 'player_name': pname,
            'total_matches': tm,
            'hp_balls': hp_b, 'hp_runs': hp_r, 'hp_outs': hp_o,
            'hp_fours': hp_4, 'hp_sixes': hp_6, 'hp_dots': hp_d,
            'hp_sr': round(hp_sr, 2),
            'hp_avg': round(hp_avg, 2),
            'hp_rae': round(hp_rae, 2),
            'hp_wae': round(hp_wae, 4),
            'hp_tva': round(hp_tva, 2),
            'hp_tva_per_100': round(hp_tva_per_100, 2),
            'hp_death_sr': round(hp_death_sr, 2),
            'hp_pp_sr': round(hp_pp_sr, 2),
            'ko_hp_balls': ko_b, 'ko_hp_runs': ko_r,
            'base_sr': round(base_sr, 2),
            'delta_sr': round(hp_sr - base_sr, 2),
            'hp_matches': hpm,
            'avg_nmi': round(avg_nmi or 0, 3),
            'wcr': round(wcr or 0, 2),
            'big_game_pct': round(bgp or 0, 2),
            'cred': round(_cred(hp_b), 4)
        })

    if not batters:
        return []

    # Z-score components
    z_tva = _zscore([b['hp_tva'] for b in batters])
    z_tva100 = _zscore([b['hp_tva_per_100'] for b in batters])
    z_dsr = _zscore([b['delta_sr'] for b in batters])
    z_wcr = _zscore([b['wcr'] for b in batters])
    z_nmi = _zscore([b['avg_nmi'] for b in batters])
    z_bgp = _zscore([b['big_game_pct'] for b in batters])

    for i, b in enumerate(batters):
        raw = (
            0.28 * z_tva[i] +
            0.25 * z_tva100[i] +
            0.20 * z_dsr[i] +
            0.15 * z_wcr[i] +
            0.07 * z_nmi[i] +
            0.05 * z_bgp[i]
        ) * b['cred']
        b['raw_score'] = raw

    batters.sort(key=lambda x: -x['raw_score'])
    ratings = _normalize([b['raw_score'] for b in batters])
    for i, b in enumerate(batters):
        b['batting_pressure_index'] = ratings[i]
        b['batting_rank'] = i + 1

    logger.info(f"Batting Pressure Index computed for {len(batters)} players")
    return batters


def compute_bowling_pressure_index(conn: sqlite3.Connection) -> list[dict]:
    """Compute BWPI for all eligible bowlers."""
    cur = conn.cursor()

    cur.execute("""
        WITH b_agg AS (
            SELECT
                bowler_id as player_id, bowler_name as player_name,
                COUNT(CASE WHEN is_high_pressure=1 AND legal_ball=1 THEN 1 END) as hp_balls,
                SUM(CASE WHEN is_high_pressure=1 AND legal_ball=1 THEN bowler_runs ELSE 0 END) as hp_runs,
                SUM(CASE WHEN is_high_pressure=1 THEN is_bowler_wicket ELSE 0 END) as hp_wkts,
                COUNT(CASE WHEN is_high_pressure=1 AND legal_ball=1 AND runs=0 AND extras_type='None' THEN 1 END) as hp_dots,
                SUM(CASE WHEN is_high_pressure=1 THEN bowler_runs_saved ELSE 0 END) as hp_runs_saved,
                SUM(CASE WHEN is_high_pressure=1 THEN bowler_wkt_above_exp ELSE 0 END) as hp_wkts_above_exp,
                SUM(CASE WHEN is_high_pressure=1 THEN (bowler_runs_saved + 12.0*bowler_wkt_above_exp) ELSE 0 END) as hp_tvs,
                -- By phase
                COUNT(CASE WHEN is_high_pressure=1 AND legal_ball=1 AND overid<=6 THEN 1 END) as hp_pp_balls,
                SUM(CASE WHEN is_high_pressure=1 AND legal_ball=1 AND overid<=6 THEN bowler_runs ELSE 0 END) as hp_pp_runs,
                COUNT(CASE WHEN is_high_pressure=1 AND legal_ball=1 AND overid>=16 THEN 1 END) as hp_death_balls,
                SUM(CASE WHEN is_high_pressure=1 AND legal_ball=1 AND overid>=16 THEN bowler_runs ELSE 0 END) as hp_death_runs,
                -- Knockout
                COUNT(CASE WHEN is_high_pressure=1 AND knock_out=1 AND legal_ball=1 THEN 1 END) as ko_hp_balls,
                SUM(CASE WHEN is_high_pressure=1 AND knock_out=1 THEN is_bowler_wicket ELSE 0 END) as ko_hp_wkts,
                -- Baseline
                COUNT(CASE WHEN is_high_pressure=0 AND legal_ball=1 THEN 1 END) as base_balls,
                SUM(CASE WHEN is_high_pressure=0 AND legal_ball=1 THEN bowler_runs ELSE 0 END) as base_runs,
                SUM(CASE WHEN is_high_pressure=0 THEN is_bowler_wicket ELSE 0 END) as base_wkts,
                COUNT(DISTINCT match_id) as total_matches
            FROM delivery_with_expected
            GROUP BY bowler_id, bowler_name
            HAVING hp_balls >= ? AND base_balls >= ?
        ),
        b_match AS (
            SELECT bowler_id,
                   COUNT(*) as hp_matches,
                   AVG(net_match_impact) as avg_nmi,
                   100.0*COUNT(CASE WHEN net_match_impact>0 THEN 1 END)/COUNT(*) as wcr,
                   100.0*COUNT(CASE WHEN net_match_impact>=8 THEN 1 END)/COUNT(*) as big_game_pct
            FROM bowler_match_hp
            GROUP BY bowler_id
        )
        SELECT b.*, m.hp_matches, m.avg_nmi, m.wcr, m.big_game_pct
        FROM b_agg b
        JOIN b_match m ON b.player_id = m.bowler_id
        WHERE m.hp_matches >= ?
    """, (BOW_MIN_HP_BALLS, BOW_MIN_BASE_BALLS, BOW_MIN_HP_MATCHES))

    bowlers = []
    for r in cur.fetchall():
        (pid, pname,
         hp_b, hp_r, hp_w, hp_d, hp_saved, hp_wae, hp_tvs,
         hp_pp_b, hp_pp_r, hp_death_b, hp_death_r,
         ko_b, ko_w,
         base_b, base_r, base_w, tm,
         hpm, avg_nmi, wcr, bgp) = r

        hp_econ = (hp_r * 6.0 / hp_b) if hp_b else 0
        hp_avg = (hp_r / hp_w) if hp_w else 999.0
        hp_sr = (hp_b / hp_w) if hp_w else 0
        base_econ = (base_r * 6.0 / base_b) if base_b else 0
        delta_econ = base_econ - hp_econ
        hp_tvs_per_100 = (hp_tvs * 100.0 / hp_b) if hp_b else 0
        hp_saved_per_100 = (hp_saved * 100.0 / hp_b) if hp_b else 0
        hp_dot_pct = (hp_d * 100.0 / hp_b) if hp_b else 0
        hp_death_econ = (hp_death_r * 6.0 / hp_death_b) if hp_death_b else 0
        hp_pp_econ = (hp_pp_r * 6.0 / hp_pp_b) if hp_pp_b else 0

        bowlers.append({
            'player_id': pid, 'player_name': pname,
            'total_matches': tm,
            'hp_balls': hp_b, 'hp_runs': hp_r, 'hp_wkts': hp_w, 'hp_dots': hp_d,
            'hp_econ': round(hp_econ, 2),
            'hp_avg': round(hp_avg, 2),
            'hp_sr': round(hp_sr, 2),
            'hp_runs_saved': round(hp_saved, 2),
            'hp_wkts_above_exp': round(hp_wae, 4),
            'hp_tvs': round(hp_tvs, 2),
            'hp_tvs_per_100': round(hp_tvs_per_100, 2),
            'hp_saved_per_100': round(hp_saved_per_100, 2),
            'hp_dot_pct': round(hp_dot_pct, 2),
            'hp_death_econ': round(hp_death_econ, 2),
            'hp_pp_econ': round(hp_pp_econ, 2),
            'ko_hp_balls': ko_b, 'ko_hp_wkts': ko_w,
            'base_econ': round(base_econ, 2),
            'delta_econ': round(delta_econ, 2),
            'hp_matches': hpm,
            'avg_nmi': round(avg_nmi or 0, 3),
            'wcr': round(wcr or 0, 2),
            'big_game_pct': round(bgp or 0, 2),
            'cred': round(_cred(hp_b), 4)
        })

    if not bowlers:
        return []

    z_tvs = _zscore([b['hp_tvs'] for b in bowlers])
    z_tvs100 = _zscore([b['hp_tvs_per_100'] for b in bowlers])
    z_decon = _zscore([b['delta_econ'] for b in bowlers])
    z_wcr = _zscore([b['wcr'] for b in bowlers])
    z_nmi = _zscore([b['avg_nmi'] for b in bowlers])
    z_bgp = _zscore([b['big_game_pct'] for b in bowlers])

    for i, b in enumerate(bowlers):
        raw = (
            0.28 * z_tvs[i] +
            0.25 * z_tvs100[i] +
            0.20 * z_decon[i] +
            0.15 * z_wcr[i] +
            0.07 * z_nmi[i] +
            0.05 * z_bgp[i]
        ) * b['cred']
        b['raw_score'] = raw

    bowlers.sort(key=lambda x: -x['raw_score'])
    ratings = _normalize([b['raw_score'] for b in bowlers])
    for i, b in enumerate(bowlers):
        b['bowling_pressure_index'] = ratings[i]
        b['bowling_rank'] = i + 1

    logger.info(f"Bowling Pressure Index computed for {len(bowlers)} players")
    return bowlers


def compute_allrounder_pressure_index(conn: sqlite3.Connection) -> list[dict]:
    """Compute API for dual-role players."""
    cur = conn.cursor()
    cur.execute("""
        SELECT
            bs.player_id, bs.player_name,
            bs.hp_balls as bat_hp_balls, bs.hp_tva, bs.hp_tva_per_100,
            bss.hp_balls as bow_hp_balls, bss.hp_tvs, bss.hp_tvs_per_100,
            bss.hp_wkts
        FROM batter_stats bs
        JOIN bowler_stats bss ON bs.player_id = bss.player_id
        JOIN batter_match_consistency bmc ON bs.player_id = bmc.player_id
        JOIN bowler_match_consistency bomc ON bs.player_id = bomc.player_id
        WHERE bs.hp_balls >= ? AND bss.hp_balls >= ?
          AND bmc.hp_matches >= ? AND bomc.hp_matches >= ?
        ORDER BY (bs.hp_tva + bss.hp_tvs) DESC
    """, (AR_MIN_HP_BALLS, AR_MIN_HP_BALLS, AR_MIN_HP_MATCHES, AR_MIN_HP_MATCHES))

    ars = []
    for r in cur.fetchall():
        (pid, pname, bat_b, bat_tva, bat_tva100, bow_b, bow_tvs, bow_tvs100, bow_w) = r
        ars.append({
            'player_id': pid, 'player_name': pname,
            'bat_hp_balls': bat_b, 'hp_tva': round(bat_tva, 2), 'hp_tva_per_100': round(bat_tva100, 2),
            'bow_hp_balls': bow_b, 'hp_tvs': round(bow_tvs, 2), 'hp_tvs_per_100': round(bow_tvs100, 2),
            'hp_wkts_as_bowler': bow_w
        })

    if not ars:
        return []

    z_bat = _zscore([a['hp_tva'] for a in ars])
    z_bow = _zscore([a['hp_tvs'] for a in ars])
    z_bat100 = _zscore([a['hp_tva_per_100'] for a in ars])
    z_bow100 = _zscore([a['hp_tvs_per_100'] for a in ars])

    for i, a in enumerate(ars):
        a['raw_score'] = 0.35*z_bat[i] + 0.35*z_bow[i] + 0.15*z_bat100[i] + 0.15*z_bow100[i]

    ars.sort(key=lambda x: -x['raw_score'])
    ratings = _normalize([a['raw_score'] for a in ars])
    for i, a in enumerate(ars):
        a['allrounder_pressure_index'] = ratings[i]
        a['allrounder_rank'] = i + 1

    logger.info(f"Allrounder Pressure Index computed for {len(ars)} players")
    return ars


def save_ratings(batters: list[dict], bowlers: list[dict], allrounders: list[dict]):
    """Save all rating outputs to CSV files."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    def save_csv(data, path):
        if not data:
            return
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=list(data[0].keys()))
            writer.writeheader()
            writer.writerows(data)
        logger.info(f"Saved: {path}")

    save_csv(batters,  os.path.join(OUTPUT_DIR, "batter_pressure_index.csv"))
    save_csv(bowlers,  os.path.join(OUTPUT_DIR, "bowler_pressure_index.csv"))
    save_csv(allrounders, os.path.join(OUTPUT_DIR, "allrounder_pressure_index.csv"))


def run_all(db_path: str = DB_PATH) -> tuple[list, list, list]:
    """Run the full rating pipeline and return results."""
    conn = sqlite3.connect(db_path)
    batters = compute_batting_pressure_index(conn)
    bowlers = compute_bowling_pressure_index(conn)
    allrounders = compute_allrounder_pressure_index(conn)
    conn.close()

    save_ratings(batters, bowlers, allrounders)
    return batters, bowlers, allrounders


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    batters, bowlers, ars = run_all()

    print(f"\n{'='*60}")
    print("TOP 10 BATTING PRESSURE INDEX")
    print(f"{'='*60}")
    for b in batters[:10]:
        print(f"  {b['batting_rank']:2d}. {b['player_name']:<25} BPI={b['batting_pressure_index']:6.2f} | "
              f"HP SR={b['hp_sr']:.1f} vs Base SR={b['base_sr']:.1f} | TVA={b['hp_tva']:+.0f}")

    print(f"\n{'='*60}")
    print("TOP 10 BOWLING PRESSURE INDEX")
    print(f"{'='*60}")
    for b in bowlers[:10]:
        print(f"  {b['bowling_rank']:2d}. {b['player_name']:<25} BWPI={b['bowling_pressure_index']:6.2f} | "
              f"HP Econ={b['hp_econ']:.2f} vs Base={b['base_econ']:.2f} | TVS={b['hp_tvs']:+.0f}")

    print(f"\n{'='*60}")
    print("TOP 10 ALLROUNDER PRESSURE INDEX")
    print(f"{'='*60}")
    for a in ars[:10]:
        print(f"  {a['allrounder_rank']:2d}. {a['player_name']:<25} API={a['allrounder_pressure_index']:6.2f} | "
              f"Bat TVA={a['hp_tva']:+.0f} | Bowl TVS={a['hp_tvs']:+.0f}")
