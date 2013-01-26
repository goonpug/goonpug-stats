#!/usr/bin/env python

from goonpug import db
from goonpug.models import Player


db.create_all()
bot = Player.get_or_create(0, 'Bot')
bot.nickname = 'Bot'
db.session.commit()

# create the player stats views
q = '''CREATE OR REPLACE VIEW player_round_stats AS
SELECT pr.*, SUM(IF(f.tk, 0, 1)) AS frags, SUM(f.tk) AS tks,
SUM(f.headshot) AS headshots
FROM player_round pr, frag f
WHERE pr.player_id = f.fragger AND pr.round_id = f.round_id
GROUP BY pr.round_id, pr.player_id
'''
db.session.execute(q)

q = '''CREATE OR REPLACE VIEW player_overall_rws AS
SELECT player_id, AVG(rws) AS rws FROM player_round
GROUP BY player_round.player_id
'''
db.session.execute(q)

q = '''CREATE OR REPLACE VIEW player_match_round_wl AS
SELECT mp.match_id, mp.player_id,
    SUM(CASE
    WHEN r.winning_team = mp.team THEN 1 ELSE 0
    END) as rounds_won,
    SUM(CASE
    WHEN r.winning_team != mp.team THEN 1 ELSE 0
    END) as rounds_lost
FROM match_players mp, round r, player_round pr
WHERE mp.match_id = r.match_id AND pr.player_id = mp.player_id
    AND pr.round_id = r.id
GROUP BY mp.player_id, mp.match_id
'''
db.session.execute(q)

q = '''CREATE OR REPLACE VIEW player_match_stats AS
SELECT p.player_id, r.match_id, SUM(p.assists) AS assists,
    SUM(p.damage) AS damage, AVG(p.rws) AS rws, SUM(p.frags) AS frags,
    SUM(p.tks) AS tks, SUM(p.headshots) AS headshots, SUM(p.dead) AS deaths,
    SUM(p.bomb_planted) AS bomb_planted,
    SUM(p.bomb_defused) AS bomb_defused,
    SUM(CASE p.won_1v
        WHEN 1 THEN 1 ELSE 0
        END) AS won_1v1,
    SUM(CASE p.won_1v
        WHEN 2 THEN 1 ELSE 0
        END) AS won_1v2,
    SUM(CASE p.won_1v
        WHEN 3 THEN 1 ELSE 0
        END) AS won_1v3,
    SUM(CASE p.won_1v
        WHEN 4 THEN 1 ELSE 0
        END) AS won_1v4,
    SUM(CASE p.won_1v
        WHEN 5 THEN 1 ELSE 0
        END) AS won_1v5,
    SUM(CASE p.frags
        WHEN 1 THEN 1 ELSE 0
        END) AS k1,
    SUM(CASE p.frags
        WHEN 2 THEN 1 ELSE 0
        END) AS k2,
    SUM(CASE p.frags
        WHEN 3 THEN 1 ELSE 0
        END) AS k3,
    SUM(CASE p.frags
        WHEN 4 THEN 1 ELSE 0
        END) AS k4,
    SUM(CASE p.frags
        WHEN 5 THEN 1 ELSE 0
        END) AS k5,
    COALESCE(rwl.rounds_won, 0) AS rounds_won,
    COALESCE(rwl.rounds_lost, 0) AS rounds_lost
    FROM player_round_stats p
    LEFT JOIN
        (round r) ON (p.round_id = r.id)
    LEFT JOIN
        (player_match_round_wl rwl) ON (rwl.player_id = p.player_id and rwl.match_id = r.match_id)
    GROUP BY p.player_id, r.match_id
'''
db.session.execute(q)

q = '''CREATE OR REPLACE VIEW player_overall_stats AS
SELECT p.player_id, pl.nickname, SUM(p.assists) AS assists, SUM(p.damage) AS damage,
COALESCE(porws.rws, 0) AS rws,
SUM(p.frags) AS frags, SUM(p.tks) AS tks, SUM(p.deaths) AS deaths,
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
