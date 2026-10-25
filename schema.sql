CREATE TABLE dim_players (
    player_id SERIAL PRIMARY KEY,
    cricsheet_player_id VARCHAR(20) UNIQUE,
    player_name VARCHAR(100) NOT NULL
);

CREATE TABLE dim_teams (
    team_id SERIAL PRIMARY KEY,
    team_name VARCHAR(100) UNIQUE NOT NULL
);

CREATE TABLE dim_venues (
    venue_id SERIAL PRIMARY KEY,
    venue_name VARCHAR(200) NOT NULL,
    city VARCHAR(100)
);

CREATE TABLE dim_seasons (
    season_id SERIAL PRIMARY KEY,
    season_name VARCHAR(20) UNIQUE NOT NULL
);

CREATE TABLE dim_dates (
    date_id DATE PRIMARY KEY,
    year INT,
    month INT,
    day INT,
    quarter INT
);

CREATE TABLE fact_matches (
    match_id BIGINT PRIMARY KEY,

    match_date DATE,

    season_id INT REFERENCES dim_seasons(season_id),

    venue_id INT REFERENCES dim_venues(venue_id),

    team1_id INT REFERENCES dim_teams(team_id),
    team2_id INT REFERENCES dim_teams(team_id),

    toss_winner_id INT REFERENCES dim_teams(team_id),
    toss_decision VARCHAR(20),

    winner_team_id INT REFERENCES dim_teams(team_id),

    win_margin_runs INT,
    win_margin_wickets INT
);

CREATE TABLE fact_deliveries (

    delivery_id BIGSERIAL PRIMARY KEY,

    match_id BIGINT REFERENCES fact_matches(match_id),

    innings_no SMALLINT,

    over_no SMALLINT,

    ball_no SMALLINT,

    batter_id INT REFERENCES dim_players(player_id),

    bowler_id INT REFERENCES dim_players(player_id),

    non_striker_id INT REFERENCES dim_players(player_id),

    runs_batter SMALLINT,

    runs_extras SMALLINT,

    runs_total SMALLINT,

    is_wicket BOOLEAN,

    dismissal_type VARCHAR(50),

    extra_type VARCHAR(20),

    extra_runs SMALLINT
);