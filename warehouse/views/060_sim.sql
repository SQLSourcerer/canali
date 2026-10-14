-- Sim output: event and season runs, and each team's chances in them. A run is keyed by its predictor and sim
-- version, and every version is published, so a read names the ones it wants.

-- One event sim run per event, predictor, sim version and match it was simulated from.
CREATE VIEW pub.v_event_sim_run AS
SELECT r.sim_run_id, r.event_id, e.season, e.code AS event_code, r.predictor, r.sim_version, r.as_of_match,
       r.n_iterations, r.achieved_mcse, r.computed_at_utc
FROM derived.event_sim_run r
JOIN core.event e ON e.event_id = r.event_id;

-- One row per team per event sim run. rank_probabilities is an array of the chance of each qualification rank when
-- the team attends, first place first.
CREATE VIEW pub.v_event_sim_result AS
SELECT r.sim_run_id, r.event_id, e.season, e.code AS event_code, r.predictor, r.sim_version, r.as_of_match,
       t.team_number, t.p_attend, t.mean_rank, t.rank_probabilities, t.p_captain, t.p_selected, t.p_win,
       t.p_advance, t.p_advance_first_championship
FROM derived.event_sim_result t
JOIN derived.event_sim_run r ON r.sim_run_id = t.sim_run_id
JOIN core.event e ON e.event_id = r.event_id;

-- One season sim run per season, region, predictor, sim version and count of the region's events started.
CREATE VIEW pub.v_season_sim_run AS
SELECT sim_run_id, season, region_code, predictor, sim_version, events_started, as_of_date,
       n_iterations, achieved_mcse, computed_at_utc
FROM derived.season_sim_run;

-- One row per team per season sim run.
CREATE VIEW pub.v_season_sim_result AS
SELECT r.sim_run_id, r.season, r.region_code, r.predictor, r.sim_version, r.events_started, r.as_of_date,
       t.team_number, t.p_attend_rcmp, t.p_premier, t.p_cmp
FROM derived.season_sim_result t
JOIN derived.season_sim_run r ON r.sim_run_id = t.sim_run_id;
