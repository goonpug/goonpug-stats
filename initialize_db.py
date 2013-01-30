#!/usr/bin/env python

from goonpug import db
from goonpug.models import Player


db.create_all()
bot = Player.get_or_create(0, u'Bot')
bot.nickname = u'Bot'
db.session.commit()

# create the player stats views needed by the plugin
q = '''CREATE OR REPLACE VIEW player_overall_rws AS
SELECT player_id, AVG(rws) AS rws FROM player_round
GROUP BY player_round.player_id
'''
db.session.execute(q)

db.session.commit()
