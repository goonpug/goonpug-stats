# Copyright (c) 2013 Peter Rowlands
#
# This file is part of GoonPUG
#
# GoonPUG is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# GoonPUG is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with GoonPUG.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import absolute_import
from flask.ext.login import UserMixin
from srcds.objects import SteamId

from . import app, db


class Player(db.Model, UserMixin):

    ROLE_USER = 0
    ROLE_ADMIN = 1

    id = db.Column(db.Integer, primary_key=True)
    steam_id = db.Column(db.BigInteger, unique=True)
    nickname = db.Column(db.String(128))
    role = db.Column(db.SmallInteger, default=ROLE_USER)

    @staticmethod
    def get_or_create(steam_id):
        if isinstance(steam_id, str):
            steam_id = SteamId(steam_id).id64()
        player = Player.query.filter_by(steam_id=steam_id).first()
        if player is None:
            player = Player()
            player.steam_id = steam_id
            db.session.add(user)
        return user


class Server(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128))
    ip_address = db.Column(db.String(16))
    port = db.Column(db.SmallInteger)
    rcon_password = db.Column(db.String(64))
    db.UniqueConstraint('ip_address', 'port', name='uidx_address')


class CsgoMatch(db.Model):

    TYPE_PUG = 0
    TYPE_SCRIM = 1
    TYPE_LEAGUE = 2
    TEAM_A = 0
    TEAM_B = 1

    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.SmallInteger)
    rounds = db.relationship('round', backref='csgo_match', lazy='dynamic')
    team_a = db.ForeignKey('team')
    team_b = db.ForeignKey('team')


class Team(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    nickname = db.Column(db.String(64))
    tag = db.Column(db.String(16))


# for PUGs we just keep track of who participated, not actual teams
pug_match_players = db.Table('pug_match_players',
    db.Column('player_id', db.Integer, db.ForeignKey('player.id')),
    db.Column('match_id', db.Integer, db.ForeignKey('csgo_match.id')),
    db.Column('team', db.SmallInteger),
)


class Round(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey('csgo_match.id'))
    period = db.Column(db.SmallInteger)
    winning_team = db.Column(db.SmallInteger)


frags = db.Table('frags',
    db.Column('round_id', db.Integer, db.ForeignKey('round.id')),
    db.Column('fragger', db.Integer, db.ForeignKey('player.id')),
    db.Column('victim', db.Integer, db.ForeignKey('player.id')),
    db.Column('weapon', db.String(16), default=False),
    db.Column('headshot', db.Boolean, default=False),
)


# Tracks everything but kills, which are tracked in the 'frags' table
player_rounds = db.Table('player_rounds',
    db.Column('player_id', db.Integer, db.ForeignKey('player.id')),
    db.Column('round_id', db.Integer, db.ForeignKey('round.id')),
    db.Column('assists', db.SmallInteger, default=0),
    db.Column('dead', db.Boolean, default=False),
    db.Column('damage', db.Integer, default=0),
    db.Column('bomb_planted', db.Boolean, default=False),
    db.Column('bomb_defused', db.Boolean, default=False),
    # if the player won 1vN, set this to N
    db.Column('won_1v', db.SmallInteger, default=0),
)
