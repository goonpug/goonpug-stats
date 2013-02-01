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

from . import app, db, metadata


class Player(db.Model, UserMixin):

    ROLE_USER = 0
    ROLE_ADMIN = 1

    id = db.Column(db.Integer, primary_key=True)
    steam_id = db.Column(db.BigInteger, unique=True)
    nickname = db.Column(db.Unicode(128))
    role = db.Column(db.SmallInteger, default=ROLE_USER)

    @staticmethod
    def get_or_create(steam_id, nickname=None):
        if isinstance(steam_id, str) or isinstance(steam_id, unicode):
            steam_id = SteamId(steam_id).id64()
        player = Player.query.filter_by(steam_id=steam_id).first()
        if player is None:
            player = Player()
            player.steam_id = steam_id
            if nickname:
                player.nickname = nickname.encode('utf-8')
            db.session.add(player)
        return player


class Server(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Unicode(128))
    ip_address = db.Column(db.Unicode(16), nullable=False)
    port = db.Column(db.SmallInteger, default=27015)
    rcon_password = db.Column(db.Unicode(64))
    db.UniqueConstraint('ip_address', 'port', name='uidx_address')
    matches = db.relationship('CsgoMatch', backref='server',
                              cascade='all, delete-orphan')

    @staticmethod
    def get_or_create(ip_address, port=27015):
        server = Server.query.filter_by(ip_address=ip_address, port=port).first()
        if server is None:
            server = Server()
            server.ip_address = ip_address
            server.port = port
            db.session.add(server)
        return server


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
    server_id = db.Column(db.Integer, db.ForeignKey('server.id'),
                          nullable=False)
    start_time = db.Column(db.DateTime, nullable=False, index=True)
    end_time = db.Column(db.DateTime)
    map = db.Column(db.Unicode(64))
    rounds = db.relationship('Round', backref='csgo_match', lazy='dynamic',
                             cascade='all, delete-orphan')
    team_a = db.ForeignKey('team')
    team_b = db.ForeignKey('team')
    players = db.relationship('Player', secondary=match_players,
                              backref='matches')
    db.UniqueConstraint('server_id', 'start_time', name='uidx_server_match')


team_players = db.Table('team_players',
    db.Column('player_id', db.Integer, db.ForeignKey('player.id')),
    db.Column('team_id', db.Integer, db.ForeignKey('team.id')),
)


class Team(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    nickname = db.Column(db.Unicode(64))
    tag = db.Column(db.Unicode(16))
    players = db.relationship('Player', secondary=team_players,
                              backref='teams')


class Frag(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    round_id = db.Column(db.Integer, db.ForeignKey('round.id'))
    victim = db.Column(db.Integer, db.ForeignKey('player.id'))
    fragger = db.Column(db.Integer, db.ForeignKey('player.id'))
    weapon = db.Column(db.Unicode(16), default=False)
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
    bomb_planted = db.Column(db.Boolean, default=False)
    bomb_defused = db.Column(db.Boolean, default=False)
    # if the player won 1vN, set this to N
    won_1v = db.Column(db.SmallInteger, default=0)
    rws = db.Column(db.Float, default=0.0, index=True)
    dropped = db.Column(db.Boolean, default=False)
    team = db.Column(db.SmallInteger)
    player = db.relationship('Player', backref='player_rounds')


class Round(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey('csgo_match.id'))
    period = db.Column(db.SmallInteger)
    winning_team = db.Column(db.SmallInteger)
    player_rounds = db.relationship('PlayerRound', backref='round',
                                    cascade='all, delete-orphan')
    frags = db.relationship('Frag', backref='round',
                            cascade='all, delete-orphan')
    players = db.relationship('Player', backref='rounds',
                              secondary=PlayerRound.__table__,
                              lazy="dynamic")
