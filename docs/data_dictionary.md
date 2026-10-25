# IPL Intelligence Platform: Data Dictionary

This document details every table, column, constraint, business definition, and source mapping in the IPL Intelligence database.

---

## 1. Dimension Tables

### 1.1. `dim_teams`
Stores unique franchise identities across all tournament seasons.

| Column Name | Data Type | Nullable | Key / Constraint | Description & Source Mapping |
| :--- | :--- | :--- | :--- | :--- |
| `team_id` | `SERIAL` | No | Primary Key | Synthetic unique identifier for the franchise. |
| `team_name` | `VARCHAR(100)` | No | Unique | Official franchise name (e.g., `Chennai Super Kings`). Mapped from Cricsheet `info.teams`. |

---

### 1.2. `dim_players`
Registry of all cricketers who participated in at least one IPL match.

| Column Name | Data Type | Nullable | Key / Constraint | Description & Source Mapping |
| :--- | :--- | :--- | :--- | :--- |
| `player_id` | `SERIAL` | No | Primary Key | Synthetic unique player identifier. |
| `player_name` | `VARCHAR(100)` | No | - | Player display name (e.g., `V Kohli`, `MS Dhoni`). Mapped from Cricsheet delivery batter/bowler names. |
| `cricsheet_id` | `VARCHAR(50)` | Yes | Unique | Cricsheet unique registry identifier. Mapped from `info.registry.people`. |

---

### 1.3. `dim_venues`
Registry of stadiums and host venues.

| Column Name | Data Type | Nullable | Key / Constraint | Description & Source Mapping |
| :--- | :--- | :--- | :--- | :--- |
| `venue_id` | `SERIAL` | No | Primary Key | Synthetic unique venue identifier. |
| `venue_name` | `VARCHAR(150)` | No | Unique | Official stadium name (e.g., `Wankhede Stadium, Mumbai`). Mapped from `info.venue`. |
| `city` | `VARCHAR(100)` | Yes | - | Host city (e.g., `Mumbai`, `Chennai`). Mapped from `info.city`. |

---

### 1.4. `dim_seasons`
Tournament editions from 2008 through 2024.

| Column Name | Data Type | Nullable | Key / Constraint | Description & Source Mapping |
| :--- | :--- | :--- | :--- | :--- |
| `season_id` | `SERIAL` | No | Primary Key | Synthetic unique season identifier. |
| `season_name` | `VARCHAR(20)` | No | Unique | Season identifier string (e.g., `2008`, `2020/21`, `2024`). Mapped from `info.season`. |

---

## 2. Fact Tables

### 2.1. `fact_matches`
Match-level outcomes, conditions, and awards for all 1,241 fixtures.

| Column Name | Data Type | Nullable | Key / Constraint | Description & Source Mapping |
| :--- | :--- | :--- | :--- | :--- |
| `match_id` | `INTEGER` | No | Primary Key | Official Cricsheet match ID (e.g., `335982` for IPL Match 1). |
| `match_date` | `DATE` | No | - | Date on which fixture was played. Mapped from `info.dates[0]`. |
| `season_id` | `INTEGER` | No | Foreign Key (`dim_seasons.season_id`) | Season edition FK. |
| `match_type` | `VARCHAR(20)` | No | - | Format code (e.g., `T20`). Mapped from `info.match_type`. |
| `venue_id` | `INTEGER` | No | Foreign Key (`dim_venues.venue_id`) | Host stadium FK. |
| `team1_id` | `INTEGER` | No | Foreign Key (`dim_teams.team_id`) | First listed participating team FK. |
| `team2_id` | `INTEGER` | No | Foreign Key (`dim_teams.team_id`) | Second listed participating team FK. |
| `toss_winner_team_id` | `INTEGER` | Yes | Foreign Key (`dim_teams.team_id`) | Franchise that won the coin toss. Mapped from `info.toss.winner`. |
| `toss_decision` | `VARCHAR(10)` | Yes | - | Toss decision: `'bat'` or `'field'`. Mapped from `info.toss.decision`. |
| `winner_team_id` | `INTEGER` | Yes | Foreign Key (`dim_teams.team_id`) | Winning franchise FK (NULL for no result/abandoned). Mapped from `info.outcome.winner`. |
| `win_margin_runs` | `INTEGER` | Yes | - | Victory margin in runs (e.g., 140). Mapped from `info.outcome.by.runs`. |
| `win_margin_wickets`| `INTEGER` | Yes | - | Victory margin in wickets (e.g., 7). Mapped from `info.outcome.by.wickets`. |
| `method` | `VARCHAR(20)` | Yes | - | Rain adjustment rule (e.g., `D/L` for Duckworth-Lewis). Mapped from `info.outcome.method`. |
| `player_of_match` | `VARCHAR(100)` | Yes | - | Player of the Match award recipient (e.g., `BB McCullum`). Mapped from `info.player_of_match[0]`. |

---

### 2.2. `fact_deliveries`
Ball-by-ball micro-events for all 295,258 deliveries.

| Column Name | Data Type | Nullable | Key / Constraint | Description & Source Mapping |
| :--- | :--- | :--- | :--- | :--- |
| `delivery_id` | `BIGSERIAL` | No | Primary Key | Synthetic unique ball ID. |
| `match_id` | `INTEGER` | No | Foreign Key (`fact_matches.match_id`) | Parent match identifier. |
| `innings_no` | `INTEGER` | No | Part of Compound UK | Innings number (1 = first innings, 2 = chase innings, 3/4 = super-overs). |
| `over_no` | `INTEGER` | No | Part of Compound UK | Over number (1 to 20, 1-indexed). |
| `ball_no` | `INTEGER` | No | Part of Compound UK | Sequential ball within over (1, 2, 3... includes extras). |
| `batting_team_id` | `INTEGER` | No | Foreign Key (`dim_teams.team_id`) | Team batting FK. |
| `bowling_team_id` | `INTEGER` | No | Foreign Key (`dim_teams.team_id`) | Team bowling FK. |
| `batter_id` | `INTEGER` | No | Foreign Key (`dim_players.player_id`) | Batsman on strike. |
| `non_striker_id` | `INTEGER` | No | Foreign Key (`dim_players.player_id`) | Batsman at non-striker's end. |
| `bowler_id` | `INTEGER` | No | Foreign Key (`dim_players.player_id`) | Bowler delivering the ball. |
| `runs_batter` | `INTEGER` | No | - | Runs scored off the bat (0, 1, 2, 3, 4, 6). |
| `runs_extras` | `INTEGER` | No | - | Total extra runs conceded on delivery. |
| `runs_total` | `INTEGER` | No | - | Total runs scored on delivery (`runs_batter + runs_extras`). |
| `wides` | `INTEGER` | No | - | Wide extra runs (0 or more). Ball does not count towards over. |
| `noballs` | `INTEGER` | No | - | No-ball extra runs (0 or more). Ball does not count towards over. |
| `byes` | `INTEGER` | No | - | Bye extras (not charged to bowler). |
| `legbyes` | `INTEGER` | No | - | Leg-bye extras (not charged to bowler). |
| `penalty` | `INTEGER` | No | - | Penalty runs awarded to batting side. |
| `is_legal_ball` | `BOOLEAN` | No | - | `TRUE` if `wides == 0 AND noballs == 0`; `FALSE` otherwise. |
| `is_wicket` | `BOOLEAN` | No | - | `TRUE` if any dismissal occurred on the delivery. |
| `dismissal_kind` | `VARCHAR(50)` | Yes | - | Type of dismissal (`bowled`, `caught`, `run out`, `lbw`, `stumped`, etc.). |
| `player_out_id` | `INTEGER` | Yes | Foreign Key (`dim_players.player_id`) | Dismissed batsman FK. |
| `fielders` | `VARCHAR(255)` | Yes | - | Names of fielders involved in dismissal (e.g., catcher, thrower). |
| `is_bowler_wicket`| `BOOLEAN` | No | - | `TRUE` only for bowler-credited dismissals (`bowled`, `caught`, `caught and bowled`, `lbw`, `stumped`, `hit wicket`). |

---

### 2.3. `document_chunks`
Text chunk corpus for dense vector and lexical hybrid search.

| Column Name | Data Type | Nullable | Key / Constraint | Description |
| :--- | :--- | :--- | :--- | :--- |
| `chunk_id` | `VARCHAR(100)` | No | Primary Key | Unique chunk identifier hash. |
| `doc_id` | `VARCHAR(100)` | No | - | Parent document identifier. |
| `doc_type` | `VARCHAR(50)` | No | - | Category: `'match_summary'`, `'player_profile'`, or `'cricket_glossary'`. |
| `title` | `TEXT` | No | - | Section / document title. |
| `content` | `TEXT` | No | - | Chunk narrative content for RAG synthesis. |
| `metadata` | `JSONB` | Yes | - | Structured filtering attributes (`season`, `teams`, `player_name`). |
| `embedding` | `VECTOR(384)` | Yes | - | Dense vector embedding representation. |
| `search_vector` | `TSVECTOR` | Yes | GIN Index | Precomputed lexeme vector for English full-text search. |
| `created_at` | `TIMESTAMP` | No | - | Ingestion timestamp. |

---

## 3. Standard Analytical Metrics & Calculations

### Batting Strike Rate
$$\text{Batting SR} = \frac{\sum \text{runs\_batter}}{\text{COUNT}(\text{deliveries where wides} = 0)} \times 100$$

### Bowling Economy Rate
$$\text{Economy Rate} = \frac{\sum (\text{runs\_batter} + \text{wides} + \text{noballs})}{\sum \text{is\_legal\_ball} / 6.0}$$

### Bowling Average
$$\text{Bowling Average} = \frac{\sum (\text{runs\_batter} + \text{wides} + \text{noballs})}{\sum \text{is\_bowler\_wicket}}$$

### Match Phase Definitions
- **Powerplay**: `over_no BETWEEN 1 AND 6`
- **Middle Overs**: `over_no BETWEEN 7 AND 15`
- **Death Overs**: `over_no BETWEEN 16 AND 20`
