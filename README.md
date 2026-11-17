# 🏏 Rajasthan Royals — SupeRR Selector Season 2: Clutch Performance Under Pressure

> **Official Round 1 Submission & Interactive Analytics Dashboard**  
> **Dataset:** 883 T20 Matches (2022–2026) | 200,999 Deliveries | 141 Competitions (IPL 2022–2026 & T20Is)

---

## 🌐 Live Interactive Streamlit Dashboard
[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io)  
*(Deploy on [Streamlit Community Cloud](https://share.streamlit.io) in 1 click using `app.py`)*

---

## 🏆 Official Top 10 Player Rankings (For Unstop Dropdowns)

These rankings are strictly ordered from **Rank 1 to Rank 10** without duplication, matching the official methodology report and analytical models.

### 🏏 Top 10 Batters Under Pressure (Dropdown 1)
| Rank | Player Name | HP SR | Diff SR (vs Base) | HP Avg | TVA (Total Value) | Win Contrib % | BPI Rating |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **1** | **Suryakumar Yadav** | 211.8 | **+58.4** | 33.7 | +320 | 63.2% | **100.0** |
| **2** | **Tristan Stubbs** | 174.2 | **+55.2** | 37.4 | +334 | 60.0% | **97.5** |
| **3** | **Rinku Singh** | 162.9 | +38.9 | 36.4 | **+397** | 60.3% | **95.2** |
| **4** | **Namboori Tilak Varma** | 162.7 | +35.2 | 34.8 | +369 | 63.0% | **93.2** |
| **5** | **Rishabh Pant** | 181.0 | **+57.5** | **39.4** | +212 | 63.0% | **91.2** |
| **6** | **Tim David** | 173.8 | +10.9 | 35.8 | +394 | 61.0% | **89.4** |
| **7** | **Heinrich Klaasen** | 174.3 | +22.5 | 33.4 | +270 | **70.0%** | **84.9** |
| **8** | **Naman Dhir** | 197.3 | +51.7 | 36.3 | +166 | 63.6% | **84.8** |
| **9** | **Rovman Powell** | 159.6 | +35.5 | 29.9 | +312 | 52.8% | **84.2** |
| **10** | **David Miller** | 167.7 | +41.2 | 29.7 | +233 | 61.8% | **80.9** |

---

### 🎯 Top 10 Bowlers Under Pressure (Dropdown 2)
| Rank | Player Name | HP Economy | Diff Econ (Drop) | HP Wickets | TVS (Runs Saved) | Win Contrib % | BWPI Rating |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **1** | **Kuldeep Yadav** | **6.79** | **+1.40** | 46 | **+326** | 61.2% | **100.0** |
| **2** | **Matheesha Pathirana** | 7.75 | +0.06 | **49** | +273 | **68.4%** | **91.0** |
| **3** | **Sunil Narine** | **5.71** | **+1.39** | 25 | +195 | 65.0% | **84.6** |
| **4** | **Noor Ahmad** | 7.02 | +0.75 | 31 | +209 | 58.8% | **83.8** |
| **5** | **Abrar Ahmed** | **5.41** | **+1.67** | 17 | +115 | **70.8%** | **78.7** |
| **6** | **Wanindu Hasaranga** | 7.77 | +0.12 | 41 | +201 | 60.9% | **77.8** |
| **7** | **Jamie Overton** | 7.86 | +0.71 | 21 | +97 | 70.0% | **72.8** |
| **8** | **Shadab Khan** | 5.63 | **+2.63** | 13 | +90 | 50.0% | **72.7** |
| **9** | **Shaheen Afridi** | 7.19 | +0.59 | 24 | +123 | 60.0% | **72.2** |
| **10** | **Sufiyan Muqeem** | 5.92 | +0.00 | 14 | +97 | 61.5% | **71.1** |

*(Note: Jasprit Bumrah is ranked #12 overall due to baseline ceiling effect: his base economy is already a world-record 6.73 rpo, so his death HP economy of 7.08 yields a slight negative delta despite saving a massive +188 runs against league expectation).*

---

## 🚀 How to Deploy on Streamlit Community Cloud (Step-by-Step)

### Step 1: Push to GitHub
Open PowerShell or Terminal in this folder:
```bash
# 1. Initialize Git repository:
git init

# 2. Add files (the 124MB .db file is automatically ignored by .gitignore):
git add .

# 3. Commit:
git commit -m "Rajasthan Royals SupeRR Selector Season 2 - Full Pipeline and Streamlit App"

# 4. Link to your GitHub repository and push:
git remote add origin https://github.com/<your-username>/superr-selector-s2.git
git branch -M main
git push -u origin main
```

### Step 2: Deploy on Streamlit Cloud (Free & Instant)
1. Go to **[share.streamlit.io](https://share.streamlit.io)** and log in with your GitHub account.
2. Click **"New app"**.
3. Select your repository: `<your-username>/superr-selector-s2`.
4. Branch: `main`.
5. Main file path: `app.py`.
6. Click **"Deploy!"**
7. Your interactive dashboard is live within 60 seconds with a shareable URL (e.g. `https://superr-selector-s2.streamlit.app`)!

---

## 📊 Dashboard Architecture & Interactive Modules

1. **🏆 Official Top 10 Dropdowns:** Interactive rankings with filters for balls faced/bowled, search, and spotlight summaries.
2. **🔍 Head-to-Head Comparison:** Select any two players for side-by-side radar charts, metric differentials, and statistical profiles.
3. **📊 In-Depth Analytics:** Plotly interactive scatter matrices (HP SR vs Base SR, HP Econ vs Base Econ), phase breakdowns, and benchmark grids.
4. **⚡ Live Match Clutch Simulator:** Input target, current score, overs, wickets, and knockout flag to compute live delivery pressure and get model-recommended tactical substitutions.
5. **📑 Methodology Whitepaper:** Comprehensive documentation of mathematical equations, context benchmarks, and Bayesian credibility shrinkage.
6. **📥 Download Center:** Direct one-click download for the Official Report PDF and processed CSVs.

---

## 📁 Repository Structure

```
├── app.py                                            # Main Streamlit Dashboard
├── requirements.txt                                  # Streamlit Cloud dependencies
├── .streamlit/
│   └── config.toml                                   # Rajasthan Royals branding theme
├── .gitignore                                        # Ignores >100MB SQLite DB
├── SupeRR_Selector_Season_2_Methodology_Report.pdf   # Official 4-page submission PDF
├── reports/
│   ├── SupeRR_Selector_Season_2_Methodology_Report.pdf
│   └── report_template.html
├── run_pipeline.py                                   # End-to-end Python pipeline
├── src/
│   ├── data_loader.py                                # CSV to SQLite DB loader
│   ├── pressure_engine.py                            # Delivery-level pressure & benchmarks
│   └── player_ratings.py                             # BPI, BWPI, API rating models
└── Data/
    ├── raw/                                          # Original match & ball-by-ball CSVs
    ├── processed/
    │   ├── batter_pressure_index.csv                 # 97 ranked batters
    │   ├── bowler_pressure_index.csv                 # 146 ranked bowlers
    │   ├── allrounder_pressure_index.csv             # 97 ranked allrounders
    │   └── player_master_stats.csv                   # 958 players master stats
    └── dashboard/                                    # Aggregated phase and trend CSVs
```

---

## 📄 Methodology & Report Summary
Read the complete [Methodology Report PDF](SupeRR_Selector_Season_2_Methodology_Report.pdf) for:
- Mathematical definition of continuous delivery-level Pressure Score $P \in [0, 1]$.
- 18-cell context expectation grid isolating IPL vs T20I scoring conditions.
- Multi-objective composite scoring with Empirical Bayes shrinkage ($Cred = \frac{N}{N+50}$).
- Strategic squad building recommendations for Rajasthan Royals.
