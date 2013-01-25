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
    def get_or_create(steam_id, nickname=None):
        if isinstance(steam_id, str):
            steam_id = SteamId(steam_id).id64()
        player = Player.query.filter_by(steam_id=steam_id).first()
        if player is None:
            player = Player()
            player.steam_id = steam_id
            if nickname:
                player.nickname = nickname
            db.session.add(player)
        return player


class Server(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128))
    ip_address = db.Column(db.String(16))
    port = db.Column(db.SmallInteger)
    rcon_password = db.Column(db.String(64))
    db.UniqueConstraint('ip_address', 'port', name='uidx_address')


match_players = db.Table('match_players',
    db.Column('player_id', db.Integer, db.ForeignKey('player.id')),
    db.Column('match_id', db.Integer, db.ForeignKey('csgo_match.id')),
    db.Column('team', db.SmallInteger),
)


class CsgoMatch(db.Model):

    TYPE_PUG = 0
    TYPE_SCRIM = 1
    TYPE_LEAGUE = 2
    TEAM_A = 0
    TEAM_B = 1

    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.SmallInteger)
    server = db.Column(db.Integer, db.ForeignKey('server.id'))
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    map = db.Column(db.String(64))
    rounds = db.relationship('Round', backref='csgo_match', lazy='dynamic')
    team_a = db.ForeignKey('team')
    team_b = db.ForeignKey('team')
    players = db.relationship('Player', secondary=match_players,
                              backref='matches')


team_players = db.Table('team_players',
    db.Column('player_id', db.Integer, db.ForeignKey('player.id')),
    db.Column('team_id', db.Integer, db.ForeignKey('team.id')),
)


class Team(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    nickname = db.Column(db.String(64))
    tag = db.Column(db.String(16))
    players = db.relationship('Player', secondary=team_players,
                              backref='teams')


class Frag(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    round_id = db.Column(db.Integer, db.ForeignKey('round.id'))
    victim = db.Column(db.Integer, db.ForeignKey('player.id'))
    fragger = db.Column(db.Integer, db.ForeignKey('player.id'))
    weapon = db.Column(db.String(16), default=False)
    headshot = db.Column(db.Boolean, default=False)
    tk = db.Column(db.Boolean, default=False)


class PlayerRound(db.Model):

    player_id = db.Column(db.Integer, db.ForeignKey('player.id'),
                          primary_key=True)
    round_id = db.Column(db.Integer, db.ForeignKey('round.id'),
                         primary_key=True)
    assists = db.Column(db.SmallInteger, default=0)
    dead = db.Column(db.Boolean, default=False)
    damage = db.Column(db.Integer, default=0)
    ff_damage = db.Column(db.Integer, default=0)
    bomb_planted = db.Column(db.Boolean, default=False)
    bomb_defused = db.Column(db.Boolean, default=False)
    # if the player won 1vN, set this to N
    won_1v = db.Column(db.SmallInteger, default=0)
    rws = db.Column(db.Float, default=0.0)


class Round(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey('csgo_match.id'))
    period = db.Column(db.SmallInteger)
    winning_team = db.Column(db.SmallInteger)
    player_rounds = db.relationship('PlayerRound', backref='round',
                                    lazy='dynamic')
    frags = db.relationship('Frag', backref='round', lazy='dynamic')
