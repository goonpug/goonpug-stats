#!/usr/bin/env python

from goonpug import db
from goonpug.models import Player


db.create_all()
bot = Player.get_or_create(0, 'Bot')
bot.nickname = 'Bot'
db.session.commit()

# create the player stats views
q = '''CREATE OR REPLACE VIEW player_round_frags AS
SELECT round_id, fragger as player_id, SUM(tk) AS tks,
SUM(IF(tk, 0, 1)) as frags, SUM(headshot) AS headshots
FROM frag GROUP BY player_id, round_id
'''
db.session.execute(q)

q = '''CREATE OR REPLACE VIEW player_round_stats AS
SELECT pr.*, COALESCE(f.frags, 0) AS frags, COALESCE(f.tks, 0) AS tks,
COALESCE(f.headshots, 0) AS headshots
FROM player_round pr
LEFT JOIN
    (player_round_frags f) ON (pr.player_id = f.player_id AND
    pr.round_id = f.round_id)
'''
db.session.execute(q)

q = '''CREATE OR REPLACE VIEW player_overall_rws AS
SELECT player_id, AVG(rws) AS rws FROM player_round
GROUP BY player_round.player_id
'''
db.session.execute(q)

q = '''CREATE OR REPLACE VIEW player_match_k1 AS
SELECT r.match_id, p.player_id, COUNT(*) AS k1
FROM round r, player_round_stats p
WHERE r.id = p.round_id AND p.frags = 1
GROUP BY p.player_id, r.match_id
'''
db.session.execute(q)

q = '''CREATE OR REPLACE VIEW player_match_k2 AS
SELECT r.match_id, p.player_id, COUNT(*) AS k2
FROM round r, player_round_stats p
WHERE r.id = p.round_id AND p.frags = 2
GROUP BY p.player_id, r.match_id
'''
db.session.execute(q)

q = '''CREATE OR REPLACE VIEW player_match_k3 AS
SELECT r.match_id, p.player_id, COUNT(*) AS k3
FROM round r, player_round_stats p
WHERE r.id = p.round_id AND p.frags = 3
GROUP BY p.player_id, r.match_id
'''
db.session.execute(q)

q = '''CREATE OR REPLACE VIEW player_match_k4 AS
SELECT r.match_id, p.player_id, COUNT(*) AS k4
FROM round r, player_round_stats p
WHERE r.id = p.round_id AND p.frags = 4
GROUP BY p.player_id, r.match_id
'''
db.session.execute(q)

q = '''CREATE OR REPLACE VIEW player_match_k5 AS
SELECT r.match_id, p.player_id, COUNT(*) AS k5
FROM round r, player_round_stats p
WHERE r.id = p.round_id AND p.frags = 5
GROUP BY p.player_id, r.match_id
'''
db.session.execute(q)

q = '''CREATE OR REPLACE VIEW player_match_1v1 AS
SELECT r.match_id, p.player_id, COUNT(*) AS won_1v1
FROM round r, player_round_stats p
WHERE r.id = p.round_id AND p.won_1v = 1
GROUP BY p.player_id, r.match_id
'''
db.session.execute(q)

q = '''CREATE OR REPLACE VIEW player_match_1v2 AS
SELECT r.match_id, p.player_id, COUNT(*) AS won_1v2
FROM round r, player_round_stats p
WHERE r.id = p.round_id AND p.won_1v = 2
GROUP BY p.player_id, r.match_id
'''
db.session.execute(q)

q = '''CREATE OR REPLACE VIEW player_match_1v3 AS
SELECT r.match_id, p.player_id, COUNT(*) AS won_1v3
FROM round r, player_round_stats p
WHERE r.id = p.round_id AND p.won_1v = 3
GROUP BY p.player_id, r.match_id
'''
db.session.execute(q)

q = '''CREATE OR REPLACE VIEW player_match_1v4 AS
SELECT r.match_id, p.player_id, COUNT(*) AS won_1v4
FROM round r, player_round_stats p
WHERE r.id = p.round_id AND p.won_1v = 4
GROUP BY p.player_id, r.match_id
'''
db.session.execute(q)

q = '''CREATE OR REPLACE VIEW player_match_1v5 AS
SELECT r.match_id, p.player_id, COUNT(*) AS won_1v5
FROM round r, player_round_stats p
WHERE r.id = p.round_id AND p.won_1v = 5
GROUP BY p.player_id, r.match_id
'''
db.session.execute(q)

q = '''CREATE OR REPLACE VIEW player_match_rounds_won AS
SELECT mp.match_id, mp.player_id, COUNT(*) as rounds_won
FROM match_players mp, round r, player_round pr
WHERE mp.match_id = r.match_id AND r.winning_team = mp.team
    AND pr.player_id = mp.player_id AND pr.round_id = r.id
GROUP BY mp.player_id, mp.match_id
'''
db.session.execute(q)

q = '''CREATE OR REPLACE VIEW player_match_rounds_lost AS
SELECT mp.match_id, mp.player_id, COUNT(*) as rounds_lost
FROM match_players mp, round r, player_round pr
WHERE mp.match_id = r.match_id AND r.winning_team != mp.team
    AND pr.player_id = mp.player_id AND pr.round_id = r.id
GROUP BY mp.player_id, mp.match_id
'''
db.session.execute(q)

q = '''CREATE OR REPLACE VIEW player_match_stats AS
SELECT p.player_id, r.match_id, SUM(p.assists) AS assists,
    SUM(p.damage) AS damage, AVG(p.rws) AS rws, SUM(p.frags) AS frags,
    SUM(p.tks) AS tks, SUM(p.headshots) AS headshots, SUM(p.dead) AS deaths,
    SUM(p.bomb_planted) AS bomb_planted,
    SUM(p.bomb_defused) AS bomb_defused,
    COALESCE(v1.won_1v1, 0) AS won_1v1, COALESCE(v2.won_1v2, 0) AS won_1v2,
    COALESCE(v3.won_1v3, 0) AS won_1v3, COALESCE(v4.won_1v4, 0) AS won_1v4,
    COALESCE(v5.won_1v5, 0) AS won_1v5,
    COALESCE(k1.k1, 0) AS k1, COALESCE(k2.k2, 0) AS k2,
    COALESCE(k3.k3, 0) AS k3, COALESCE(k4.k4, 0) AS k4,
    COALESCE(k5.k5, 0) AS k5,
    COALESCE(rw.rounds_won, 0) AS rounds_won,
    COALESCE(rl.rounds_lost, 0) AS rounds_lost
    FROM player_round_stats p
    LEFT JOIN
        (round r) ON (p.round_id = r.id)
    LEFT JOIN
        (player_match_1v1 v1) ON (v1.player_id = p.player_id AND v1.match_id = r.match_id)
    LEFT JOIN
        (player_match_1v2 v2) ON (v2.player_id = p.player_id AND v2.match_id = r.match_id)
    LEFT JOIN
        (player_match_1v3 v3) ON (v3.player_id = p.player_id AND v3.match_id = r.match_id)
    LEFT JOIN
        (player_match_1v4 v4) ON (v4.player_id = p.player_id AND v4.match_id = r.match_id)
    LEFT JOIN
        (player_match_1v5 v5) ON (v4.player_id = p.player_id AND v5.match_id = r.match_id)
    LEFT JOIN
        (player_match_rounds_won rw) ON (rw.player_id = p.player_id AND rw.match_id = r.match_id)
    LEFT JOIN
        (player_match_k1 k1) ON (k1.player_id = p.player_id AND k1.match_id = r.match_id)
    LEFT JOIN
        (player_match_k2 k2) ON (k2.player_id = p.player_id AND k2.match_id = r.match_id)
    LEFT JOIN
        (player_match_k3 k3) ON (k3.player_id = p.player_id AND k3.match_id = r.match_id)
    LEFT JOIN
        (player_match_k4 k4) ON (k4.player_id = p.player_id AND k4.match_id = r.match_id)
    LEFT JOIN
        (player_match_k5 k5) ON (k5.player_id = p.player_id AND k5.match_id = r.match_id)
    LEFT JOIN
        (player_match_rounds_lost rl) ON (rl.player_id = p.player_id AND rl.match_id = r.match_id)
    GROUP BY p.player_id, r.match_id
'''
db.session.execute(q)

q = '''CREATE OR REPLACE VIEW player_overall_stats AS
SELECT p.player_id, pl.nickname, SUM(p.assists) AS assists, SUM(p.damage) AS damage,
porws.rws, SUM(p.frags) AS frags, SUM(p.tks) AS tks, SUM(p.deaths) AS deaths,
SUM(p.headshots) AS headshots,
SUM(p.bomb_planted) AS bomb_planted, SUM(p.bomb_defused) AS bomb_defused,
SUM(p.won_1v1) AS won_1v1, SUM(p.won_1v2) AS won_1v2,
SUM(p.won_1v3) AS won_1v3, SUM(p.won_1v4) AS won_1v4,
SUM(p.won_1v5) AS won_1v5,
SUM(p.k1) AS k1, SUM(p.k2) AS k2,
SUM(p.k3) AS k3, SUM(p.k4) AS k4,
SUM(p.k5) AS k5,
SUM(p.rounds_won) AS rounds_won,
SUM(p.rounds_lost) AS rounds_lost
FROM player_match_stats p, player_overall_rws porws, player pl
WHERE p.player_id = porws.player_id AND p.player_id = pl.id
GROUP BY p.player_id
'''
db.session.execute(q)
db.session.commit()
