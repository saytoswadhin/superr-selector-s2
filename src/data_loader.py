"""
SupeRR Selector Season 2 - Data Loader
Loads all raw CSVs into a SQLite database for efficient analysis.
"""

import os
import sqlite3
import csv
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

RAW_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "Data", "raw")
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "cricket_analytics.db")


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA synchronous = OFF")
    conn.execute("PRAGMA journal_mode = MEMORY")
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.execute("PRAGMA cache_size = -32000")
    return conn


def load_all(db_path: str = DB_PATH, raw_dir: str = RAW_DATA_DIR, force_rebuild: bool = False):
    """Load all raw CSV files into SQLite. Skips if already loaded unless force_rebuild=True."""
    if os.path.exists(db_path) and not force_rebuild:
        logger.info("Database already exists. Use force_rebuild=True to reload.")
        return

    if os.path.exists(db_path):
        os.remove(db_path)

    conn = get_connection(db_path)
    cur = conn.cursor()

    # 1. Competitions
    logger.info("Loading competitions...")
    cur.execute("DROP TABLE IF EXISTS competitions")
    cur.execute("""
        CREATE TABLE competitions (
            comp_id INTEGER PRIMARY KEY,
            comp_name TEXT,
            match_format TEXT,
            season TEXT
        )
    """)
    _load_csv(cur, os.path.join(raw_dir, "competitions.csv"),
              "INSERT INTO competitions VALUES (?, ?, ?, ?)")

    # 2. Teams
    logger.info("Loading teams...")
    cur.execute("DROP TABLE IF EXISTS teams")
    cur.execute("""
        CREATE TABLE teams (comp_id INTEGER, team_id INTEGER, team_name TEXT)
    """)
    _load_csv(cur, os.path.join(raw_dir, "teams.csv"),
              "INSERT INTO teams VALUES (?, ?, ?)")

    # 3. Matches
    logger.info("Loading matches...")
    cur.execute("DROP TABLE IF EXISTS matches")
    cur.execute("""
        CREATE TABLE matches (
            match_id INTEGER PRIMARY KEY, comp_id INTEGER,
            match_number TEXT, match_date TEXT, stage TEXT,
            venue_id INTEGER, venue_country TEXT,
            home_team_id INTEGER, home_team TEXT,
            away_team_id INTEGER, away_team TEXT,
            home_team_captain_id TEXT, away_team_captain_id TEXT,
            toss_win_team_id INTEGER, toss_opted TEXT,
            man_of_the_match TEXT,
            first_inn_revised_overs TEXT, second_inn_revised_overs TEXT,
            revised_target TEXT, knock_out INTEGER,
            win_team_id INTEGER, result TEXT
        )
    """)
    _load_csv(cur, os.path.join(raw_dir, "matches.csv"),
              "INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")

    # 4. Competition Team Player Mapping
    logger.info("Loading player mapping...")
    cur.execute("DROP TABLE IF EXISTS player_mapping")
    cur.execute("""
        CREATE TABLE player_mapping (
            comp_id INTEGER, comp_name TEXT,
            team_id INTEGER, team_name TEXT,
            player_id INTEGER, player_name TEXT
        )
    """)
    _load_csv(cur, os.path.join(raw_dir, "competition_team_player_mapping.csv"),
              "INSERT INTO player_mapping VALUES (?, ?, ?, ?, ?, ?)")

    # 5. Playing Eleven
    logger.info("Loading playing eleven...")
    cur.execute("DROP TABLE IF EXISTS playing_eleven")
    cur.execute("""
        CREATE TABLE playing_eleven (
            match_id INTEGER, team_id INTEGER, player_id INTEGER,
            batting_order INTEGER, is_played TEXT, is_captain TEXT,
            is_wk TEXT, is_impact INTEGER, is_impact_off INTEGER
        )
    """)
    _load_csv(cur, os.path.join(raw_dir, "playing_eleven.csv"),
              "INSERT INTO playing_eleven VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)")

    # 6. Ball by Ball (largest file)
    logger.info("Loading ball_by_ball (this takes a moment)...")
    cur.execute("DROP TABLE IF EXISTS ball_by_ball")
    cur.execute("""
        CREATE TABLE ball_by_ball (
            match_id INTEGER, innings INTEGER,
            overid INTEGER, over_ball_num INTEGER, innings_ball_num INTEGER,
            batting_team_id INTEGER, bowling_team_id INTEGER,
            striker_id INTEGER, striker_name TEXT,
            non_striker_id INTEGER, non_striker_name TEXT,
            bowler_id INTEGER, bowler_name TEXT,
            batting_type TEXT, bowling_type TEXT,
            batting_order INTEGER,
            runs INTEGER, is_four TEXT, is_six TEXT, is_wicket TEXT,
            dismissal_type_id TEXT, dismissal_type TEXT, dismissed_player_id TEXT,
            extras_type TEXT, extras1_runs TEXT, extras_2_runs INTEGER,
            pace_or_spin TEXT, bowl_speed REAL,
            stroke TEXT, delivery_style TEXT,
            over_or_around TEXT, on_or_off TEXT, delivery_ist_time TEXT
        )
    """)
    t0 = time.time()
    _load_bbb(cur, os.path.join(raw_dir, "ball_by_ball.csv"))
    logger.info(f"Ball-by-ball loaded in {time.time()-t0:.1f}s")

    # Indexes
    logger.info("Creating indexes...")
    cur.execute("CREATE INDEX idx_bbb_match_inn ON ball_by_ball (match_id, innings)")
    cur.execute("CREATE INDEX idx_bbb_striker ON ball_by_ball (striker_id)")
    cur.execute("CREATE INDEX idx_bbb_bowler ON ball_by_ball (bowler_id)")
    cur.execute("CREATE INDEX idx_pe_player ON playing_eleven (player_id)")
    cur.execute("CREATE INDEX idx_pm_player ON player_mapping (player_id)")

    conn.commit()
    conn.close()
    logger.info("All data loaded successfully.")


def _load_csv(cur: sqlite3.Cursor, path: str, sql: str, batch_size: int = 10000):
    rows = []
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        for row in reader:
            rows.append(row)
            if len(rows) >= batch_size:
                cur.executemany(sql, rows)
                rows = []
        if rows:
            cur.executemany(sql, rows)


def _load_bbb(cur: sqlite3.Cursor, path: str, batch_size: int = 10000):
    sql = "INSERT INTO ball_by_ball VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    rows = []

    def parse(r):
        return (
            int(r[0]), int(r[1]), int(r[2]), int(r[3]), int(r[4]),
            int(r[5]), int(r[6]), int(r[7]), r[8], int(r[9]), r[10],
            int(r[11]), r[12], r[13], r[14],
            int(r[15]) if r[15] else 0,
            int(r[16]), r[17], r[18], r[19],
            r[20], r[21], r[22], r[23], r[24],
            int(r[25]) if r[25] else 0,
            r[26],
            float(r[27]) if r[27] else 0.0,
            r[28], r[29], r[30], r[31], r[32]
        )

    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.reader(f)
        next(reader)
        for r in reader:
            rows.append(parse(r))
            if len(rows) >= batch_size:
                cur.executemany(sql, rows)
                rows = []
        if rows:
            cur.executemany(sql, rows)


if __name__ == "__main__":
    load_all(force_rebuild=True)
    logger.info("Done.")
