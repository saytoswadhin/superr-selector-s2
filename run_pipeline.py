"""
SupeRR Selector Season 2 - Main Pipeline Runner

Usage:
    python run_pipeline.py [--rebuild-db] [--skip-ratings]

Steps:
    1. Load raw CSVs → SQLite database
    2. Build pressure context (match state, pressure scores, expected values)
    3. Build match-level aggregates (batter_match_hp, bowler_match_hp)
    4. Compute Batting Pressure Index (BPI), Bowling Pressure Index (BWPI),
       Allrounder Pressure Index (API)
    5. Export results to Data/processed/
"""

import os
import sys
import argparse
import sqlite3
import logging
import time

# Add src to path
sys.path.insert(0, os.path.dirname(__file__))

from src.data_loader import load_all, get_connection
from src.pressure_engine import build_pressure_context, build_context_benchmarks, build_delivery_with_expected
from src.player_ratings import run_all as run_ratings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("pipeline.log", mode="w")
    ]
)
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "cricket_analytics.db")


def build_match_aggregates(conn: sqlite3.Connection):
    """Build match-level HP aggregates for batters and bowlers (consistency analysis)."""
    cur = conn.cursor()

    logger.info("Building batter_match_hp...")
    cur.execute("DROP TABLE IF EXISTS batter_match_hp")
    cur.execute("""
        CREATE TABLE batter_match_hp AS
        SELECT
            striker_id, striker_name, match_id,
            COUNT(*) as hp_balls,
            SUM(runs) as hp_runs,
            COUNT(CASE WHEN is_wicket='true' THEN 1 END) as hp_outs,
            SUM(batter_runs_above_exp) as hp_rae,
            SUM(wkt_avoided_above_exp) as hp_wae,
            (SUM(batter_runs_above_exp) + 12.0 * SUM(wkt_avoided_above_exp)) as net_match_impact
        FROM delivery_with_expected
        WHERE is_high_pressure = 1
        GROUP BY striker_id, striker_name, match_id
    """)

    logger.info("Building bowler_match_hp...")
    cur.execute("DROP TABLE IF EXISTS bowler_match_hp")
    cur.execute("""
        CREATE TABLE bowler_match_hp AS
        SELECT
            bowler_id, bowler_name, match_id,
            COUNT(CASE WHEN legal_ball=1 THEN 1 END) as hp_balls,
            SUM(CASE WHEN legal_ball=1 THEN bowler_runs ELSE 0 END) as hp_runs,
            SUM(is_bowler_wicket) as hp_wkts,
            SUM(bowler_runs_saved) as hp_runs_saved,
            SUM(bowler_wkt_above_exp) as hp_wkts_above_exp,
            (SUM(bowler_runs_saved) + 12.0 * SUM(bowler_wkt_above_exp)) as net_match_impact
        FROM delivery_with_expected
        WHERE is_high_pressure = 1
        GROUP BY bowler_id, bowler_name, match_id
    """)

    logger.info("Building match consistency summary tables...")
    cur.execute("DROP TABLE IF EXISTS batter_match_consistency")
    cur.execute("""
        CREATE TABLE batter_match_consistency AS
        SELECT
            striker_id as player_id, striker_name as player_name,
            COUNT(*) as hp_matches,
            AVG(net_match_impact) as avg_nmi,
            MIN(net_match_impact) as min_nmi,
            MAX(net_match_impact) as max_nmi,
            100.0 * COUNT(CASE WHEN net_match_impact > 0 THEN 1 END) / COUNT(*) as wcr,
            100.0 * COUNT(CASE WHEN net_match_impact >= 10 THEN 1 END) / COUNT(*) as big_game_pct
        FROM batter_match_hp
        GROUP BY striker_id, striker_name
    """)

    cur.execute("DROP TABLE IF EXISTS bowler_match_consistency")
    cur.execute("""
        CREATE TABLE bowler_match_consistency AS
        SELECT
            bowler_id as player_id, bowler_name as player_name,
            COUNT(*) as hp_matches,
            AVG(net_match_impact) as avg_nmi,
            MIN(net_match_impact) as min_nmi,
            MAX(net_match_impact) as max_nmi,
            100.0 * COUNT(CASE WHEN net_match_impact > 0 THEN 1 END) / COUNT(*) as wcr,
            100.0 * COUNT(CASE WHEN net_match_impact >= 8 THEN 1 END) / COUNT(*) as big_game_pct
        FROM bowler_match_hp
        GROUP BY bowler_id, bowler_name
    """)

    cur.execute("DROP TABLE IF EXISTS batter_stats")
    cur.execute("""
        CREATE TABLE batter_stats AS
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
            COUNT(CASE WHEN is_high_pressure=0 THEN 1 END) as base_balls,
            SUM(CASE WHEN is_high_pressure=0 THEN runs ELSE 0 END) as base_runs,
            COUNT(CASE WHEN is_high_pressure=0 AND is_wicket='true' THEN 1 END) as base_outs,
            COUNT(DISTINCT match_id) as total_matches,
            ROUND(SUM(CASE WHEN is_high_pressure=1 THEN runs ELSE 0 END)*100.0 / NULLIF(COUNT(CASE WHEN is_high_pressure=1 THEN 1 END),0), 2) as hp_sr,
            ROUND(SUM(CASE WHEN is_high_pressure=0 THEN runs ELSE 0 END)*100.0 / NULLIF(COUNT(CASE WHEN is_high_pressure=0 THEN 1 END),0), 2) as base_sr,
            ROUND(SUM(CASE WHEN is_high_pressure=1 THEN (batter_runs_above_exp + 12.0*wkt_avoided_above_exp) ELSE 0 END)*100.0 / NULLIF(COUNT(CASE WHEN is_high_pressure=1 THEN 1 END),0), 2) as hp_tva_per_100,
            ROUND(COUNT(CASE WHEN is_high_pressure=1 AND is_high_pressure=1 AND overid>=16 THEN 1 END)*1.0, 0) as hp_death_balls,
            ROUND(SUM(CASE WHEN is_high_pressure=1 AND overid>=16 THEN runs ELSE 0 END)*100.0 / NULLIF(COUNT(CASE WHEN is_high_pressure=1 AND overid>=16 THEN 1 END),0), 2) as hp_death_sr,
            COUNT(CASE WHEN is_high_pressure=1 AND knock_out=1 THEN 1 END) as ko_hp_balls,
            SUM(CASE WHEN is_high_pressure=1 AND knock_out=1 THEN runs ELSE 0 END) as ko_hp_runs
        FROM delivery_with_expected
        GROUP BY striker_id, striker_name
    """)

    cur.execute("DROP TABLE IF EXISTS bowler_stats")
    cur.execute("""
        CREATE TABLE bowler_stats AS
        SELECT
            bowler_id as player_id, bowler_name as player_name,
            COUNT(CASE WHEN is_high_pressure=1 AND legal_ball=1 THEN 1 END) as hp_balls,
            SUM(CASE WHEN is_high_pressure=1 AND legal_ball=1 THEN bowler_runs ELSE 0 END) as hp_runs,
            SUM(CASE WHEN is_high_pressure=1 THEN is_bowler_wicket ELSE 0 END) as hp_wkts,
            COUNT(CASE WHEN is_high_pressure=1 AND legal_ball=1 AND runs=0 AND extras_type='None' THEN 1 END) as hp_dots,
            SUM(CASE WHEN is_high_pressure=1 THEN bowler_runs_saved ELSE 0 END) as hp_runs_saved,
            SUM(CASE WHEN is_high_pressure=1 THEN bowler_wkt_above_exp ELSE 0 END) as hp_wkts_above_exp,
            SUM(CASE WHEN is_high_pressure=1 THEN (bowler_runs_saved + 12.0*bowler_wkt_above_exp) ELSE 0 END) as hp_tvs,
            COUNT(CASE WHEN is_high_pressure=0 AND legal_ball=1 THEN 1 END) as base_balls,
            SUM(CASE WHEN is_high_pressure=0 AND legal_ball=1 THEN bowler_runs ELSE 0 END) as base_runs,
            SUM(CASE WHEN is_high_pressure=0 THEN is_bowler_wicket ELSE 0 END) as base_wkts,
            COUNT(DISTINCT match_id) as total_matches,
            ROUND(SUM(CASE WHEN is_high_pressure=1 AND legal_ball=1 THEN bowler_runs ELSE 0 END)*6.0 / NULLIF(COUNT(CASE WHEN is_high_pressure=1 AND legal_ball=1 THEN 1 END),0), 2) as hp_econ,
            ROUND(SUM(CASE WHEN is_high_pressure=0 AND legal_ball=1 THEN bowler_runs ELSE 0 END)*6.0 / NULLIF(COUNT(CASE WHEN is_high_pressure=0 AND legal_ball=1 THEN 1 END),0), 2) as base_econ,
            ROUND(SUM(CASE WHEN is_high_pressure=1 THEN (bowler_runs_saved + 12.0*bowler_wkt_above_exp) ELSE 0 END)*100.0 / NULLIF(COUNT(CASE WHEN is_high_pressure=1 AND legal_ball=1 THEN 1 END),0), 2) as hp_tvs_per_100,
            COUNT(CASE WHEN is_high_pressure=1 AND knock_out=1 AND legal_ball=1 THEN 1 END) as ko_hp_balls,
            SUM(CASE WHEN is_high_pressure=1 AND knock_out=1 THEN is_bowler_wicket ELSE 0 END) as ko_hp_wkts
        FROM delivery_with_expected
        GROUP BY bowler_id, bowler_name
    """)

    conn.commit()
    logger.info("All match aggregate tables built.")


def main():
    parser = argparse.ArgumentParser(description="SupeRR Selector Season 2 Pipeline")
    parser.add_argument("--rebuild-db", action="store_true", help="Force reload raw CSVs into DB")
    parser.add_argument("--skip-ratings", action="store_true", help="Skip ratings computation")
    args = parser.parse_args()

    t0 = time.time()
    logger.info("=" * 60)
    logger.info("SupeRR Selector Season 2 — Analysis Pipeline")
    logger.info("=" * 60)

    # Step 1: Load raw data
    logger.info("STEP 1: Loading raw data...")
    load_all(force_rebuild=args.rebuild_db)

    # Step 2: Build pressure context
    logger.info("STEP 2: Building pressure context...")
    conn = get_connection(DB_PATH)
    build_pressure_context(conn)
    build_context_benchmarks(conn)
    build_delivery_with_expected(conn)

    # Step 3: Build match aggregates
    logger.info("STEP 3: Building match aggregates...")
    build_match_aggregates(conn)
    conn.close()

    # Step 4: Compute ratings
    if not args.skip_ratings:
        logger.info("STEP 4: Computing player pressure ratings...")
        batters, bowlers, ars = run_ratings(DB_PATH)
        logger.info(f"Rated {len(batters)} batters, {len(bowlers)} bowlers, {len(ars)} allrounders")

    elapsed = time.time() - t0
    logger.info(f"\nPipeline complete in {elapsed:.1f}s")
    logger.info("Outputs saved to Data/processed/")


if __name__ == "__main__":
    main()
