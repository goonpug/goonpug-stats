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
from sqlalchemy import func, case, literal, not_, and_, or_, alias

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

    @classmethod
    def round_frags(cls):
        """Return all of a Player's frags grouped by round"""
        query = db.session.query(
            Frag.fragger.label('player_id'),
            Frag.round_id,
            func.sum(
                case([
                    (not_(Frag.tk), 1),
                ], else_=0)
            ).label('frags'),
            func.sum(
                case([
                    (and_(Frag.tk, not_(Frag.fragger == Frag.victim)), 1),
                ], else_=0)
            ).label('tks'),
        ).group_by(Frag.round_id, Frag.fragger)
        return query

    @classmethod
    def match_frags(cls):
        """Return all of a Player's frags grouped by match"""
        player_round_frags = cls.round_frags().subquery()
        query = db.session.query(
            player_round_frags.c.player_id,
            Round.match_id,
            func.sum(player_round_frags.c.frags).label('frags'),
            func.sum(player_round_frags.c.tks).label('tks'),
            func.sum(
                case([
                    (player_round_frags.c.frags == 1, 1),
                ], else_=0)
            ).label('k1'),
            func.sum(
                case([
                    (player_round_frags.c.frags == 2, 1),
                ], else_=0)
            ).label('k2'),
            func.sum(
                case([
                    (player_round_frags.c.frags == 3, 1),
                ], else_=0)
            ).label('k3'),
            func.sum(
                case([
                    (player_round_frags.c.frags == 4, 1),
                ], else_=0)
            ).label('k4'),
            func.sum(
                case([
                    (player_round_frags.c.frags == 5, 1),
                ], else_=0)
            ).label('k5'),
        ).select_from(
            player_round_frags
        ).join(
            Round,
            player_round_frags.c.round_id == Round.id
        ).join(CsgoMatch,
            and_(Round.match_id == CsgoMatch.id, CsgoMatch.end_time != None)
        ).group_by(player_round_frags.c.player_id, Round.match_id)
        return query

    @classmethod
    def round_hits(cls):
        """Return all of a Player's hits grouped by round"""
        query = db.session.query(
            Attack.attacker.label('player_id'),
            Attack.round_id,
            func.sum(
                case([
                    (not_(Attack.ff), 1),
                ], else_=0)
            ).label('hits'),
            func.sum(
                case([
                    (and_(not_(Attack.ff), Attack.hitgroup == 'head'), 1),
                ], else_=0)
            ).label('headshots'),
        ).group_by(Attack.round_id, Attack.attacker)
        return query

    @classmethod
    def match_hits(cls):
        """Return all of a Player's hits grouped by match"""
        player_round_hits = cls.round_hits().subquery()
        query = db.session.query(
            player_round_hits.c.player_id,
            Round.match_id,
            func.sum(player_round_hits.c.hits).label('hits'),
            func.sum(player_round_hits.c.headshots).label('headshots'),
        ).select_from(
            player_round_hits
        ).join(
            Round,
            player_round_hits.c.round_id == Round.id
        ).join(CsgoMatch,
            and_(Round.match_id == CsgoMatch.id, CsgoMatch.end_time != None)
        ).group_by(player_round_hits.c.player_id, Round.match_id)
        return query

    @classmethod
    def match_stats(cls):
        """Return stats for Player has played in grouped by match"""
        player_match_frags = cls.match_frags().subquery()
        player_match_hits = cls.match_hits().subquery()
        player_match_rounds = db.session.query(
            PlayerRound.player_id,
            Round.match_id,
            func.sum(PlayerRound.assists).label('assists'),
            func.sum(
                case([
                    (PlayerRound.dead, 1),
                ], else_=0)
            ).label('deaths'),
            func.sum(PlayerRound.damage).label('damage'),
            func.sum(
                case([
                    (PlayerRound.bomb_planted, 1),
                ], else_=0)
            ).label('bomb_planted'),
            func.sum(
                case([
                    (PlayerRound.bomb_defused, 1),
                ], else_=0)
            ).label('bomb_defused'),
            func.sum(PlayerRound.rws).label('total_rws'),
            func.sum(
                case([
                    (and_(PlayerRound.team == Round.winning_team,
                          not_(PlayerRound.dropped)), 1)
                ], else_=0)
            ).label('rounds_won'),
            func.sum(
                case([
                    (and_(PlayerRound.team != Round.winning_team,
                          not_(PlayerRound.dropped)), 1)
                ], else_=0)
            ).label('rounds_lost'),
            func.sum(
                case([
                    (PlayerRound.dropped, 1)
                ], else_=0)
            ).label('rounds_dropped'),
            func.sum(
                case([
                    (PlayerRound.won_1v == 1, 1),
                ], else_=0)
            ).label('won_1v1'),
            func.sum(
                case([
                    (PlayerRound.won_1v == 2, 1),
                ], else_=0)
            ).label('won_1v2'),
            func.sum(
                case([
                    (PlayerRound.won_1v == 3, 1),
                ], else_=0)
            ).label('won_1v3'),
            func.sum(
                case([
                    (PlayerRound.won_1v == 4, 1),
                ], else_=0)
            ).label('won_1v4'),
            func.sum(
                case([
                    (PlayerRound.won_1v == 5, 1),
                ], else_=0)
            ).label('won_1v5'),
        ).select_from(PlayerRound).join(Round).join(CsgoMatch,
            and_(Round.match_id == CsgoMatch.id, CsgoMatch.end_time != None)
        ).group_by(PlayerRound.player_id, Round.match_id).subquery()
        query = db.session.query(
            player_match_rounds,
            player_match_frags.c.frags,
            player_match_frags.c.tks,
            player_match_frags.c.k1,
            player_match_frags.c.k2,
            player_match_frags.c.k3,
            player_match_frags.c.k4,
            player_match_frags.c.k5,
            player_match_hits.c.hits,
            player_match_hits.c.headshots,
        ).outerjoin(
            player_match_frags,
            and_(player_match_frags.c.player_id == player_match_rounds.c.player_id,
                 player_match_frags.c.match_id == player_match_rounds.c.match_id)
        ).outerjoin(
            player_match_hits,
            and_(player_match_hits.c.player_id == player_match_rounds.c.player_id,
                 player_match_hits.c.match_id == player_match_rounds.c.match_id)
        )
        return query

    @classmethod
    def overall_stats(cls, min_rounds=0):
        player_match_stats = cls.match_stats().subquery()
        query = db.session.query(
            player_match_stats.c.player_id,
            Player.nickname,
            func.sum(player_match_stats.c.frags).label('frags'),
            func.sum(player_match_stats.c.tks).label('tks'),
            func.sum(player_match_stats.c.assists).label('assists'),
            func.sum(player_match_stats.c.deaths).label('deaths'),
            func.sum(player_match_stats.c.bomb_planted).label('bomb_planted'),
            func.sum(player_match_stats.c.bomb_defused).label('bomb_defused'),
            func.sum(player_match_stats.c.rounds_won).label('rounds_won'),
            func.sum(player_match_stats.c.rounds_lost).label('rounds_lost'),
            func.sum(player_match_stats.c.rounds_dropped)\
                .label('rounds_dropped'),
            (
                func.sum(player_match_stats.c.rounds_won)
                + func.sum(player_match_stats.c.rounds_lost)
            ).label('rounds_played'),
            func.sum(player_match_stats.c.won_1v1).label('won_1v1'),
            func.sum(player_match_stats.c.won_1v2).label('won_1v2'),
            func.sum(player_match_stats.c.won_1v3).label('won_1v3'),
            func.sum(player_match_stats.c.won_1v4).label('won_1v4'),
            func.sum(player_match_stats.c.won_1v5).label('won_1v5'),
            func.sum(player_match_stats.c.k1).label('k1'),
            func.sum(player_match_stats.c.k2).label('k2'),
            func.sum(player_match_stats.c.k3).label('k3'),
            func.sum(player_match_stats.c.k4).label('k4'),
            func.sum(player_match_stats.c.k5).label('k5'),
            (
                func.sum(player_match_stats.c.frags)
                    / func.sum(player_match_stats.c.deaths)
            ).label('kdr'),
            (
                func.sum(player_match_stats.c.headshots)
                    / func.sum(player_match_stats.c.hits)
            ).label('hsp'),
            (
                func.sum(player_match_stats.c.damage)
                    / (func.sum(player_match_stats.c.rounds_won)
                        + func.sum(player_match_stats.c.rounds_lost))
            ).label('adr'),
            (
                func.sum(player_match_stats.c.frags)
                    / (func.sum(player_match_stats.c.rounds_won)
                        + func.sum(player_match_stats.c.rounds_lost))
            ).label('fpr'),
            (
                func.sum(player_match_stats.c.total_rws)
                    / (func.sum(player_match_stats.c.rounds_won)
                        + func.sum(player_match_stats.c.rounds_lost)
                        + func.sum(player_match_stats.c.rounds_dropped))
            ).label('rws'),
        ).join(
            Player, player_match_stats.c.player_id == Player.id
        ).group_by(
            player_match_stats.c.player_id
        ).having(
            'rounds_played >= %d' % min_rounds
        )
        return query


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


class Attack(db.Model):
    id = db.Column(db.BigInteger, primary_key=True)
    round_id = db.Column(db.Integer, db.ForeignKey('round.id'))
    target = db.Column(db.Integer, db.ForeignKey('player.id'))
    attacker = db.Column(db.Integer, db.ForeignKey('player.id'))
    weapon = db.Column(db.Unicode(16), default=False)
    damage = db.Column(db.Integer)
    damage_armor = db.Column(db.Integer)
    hitgroup = db.Column(db.Unicode(16), default=False)
    ff = db.Column(db.Boolean, default=False)


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
    attacks = db.relationship('Attack', backref='round',
                            cascade='all, delete-orphan')
    players = db.relationship('Player', backref='rounds',
                              secondary=PlayerRound.__table__,
                              lazy="dynamic")
