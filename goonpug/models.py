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
import datetime
from flask.ext.login import UserMixin
from srcds.objects import SteamId
from sqlalchemy import func, case, not_, and_

from . import db, manager


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
               and_(Round.match_id == CsgoMatch.id,
                    CsgoMatch.end_time is not None)
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
               and_(Round.match_id == CsgoMatch.id,
                    CsgoMatch.end_time is not None)
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
            CsgoMatch.map,
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
        ).select_from(PlayerRound).join(Round).join(
            CsgoMatch,
            and_(Round.match_id == CsgoMatch.id,
                 CsgoMatch.end_time is not None)
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
            and_(player_match_frags.c.player_id ==
                 player_match_rounds.c.player_id,
                 player_match_frags.c.match_id ==
                 player_match_rounds.c.match_id)
        ).outerjoin(
            player_match_hits,
            and_(player_match_hits.c.player_id ==
                 player_match_rounds.c.player_id,
                 player_match_hits.c.match_id ==
                 player_match_rounds.c.match_id)
        )
        return query

    @classmethod
    def total_stats(cls, *match_filters):
        player_match_stats = cls.match_stats()
        for arg in match_filters:
            player_match_stats = player_match_stats.filter(arg)
        player_match_stats = player_match_stats.subquery()
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
            func.sum(player_match_stats.c.rounds_dropped)
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
        )
        return query

    @classmethod
    def overall_stats(cls, min_rounds=0, player_id=None):
        query = cls.total_stats(player_id).group_by('player_id').having(
            'rounds_played >= %d' % min_rounds
        )
        return query

    @classmethod
    def map_stats(cls, mapname):
        query = cls.total_stats("map = '%s'" % mapname).group_by('player_id')
        return query

    @classmethod
    def weapon_kill_stats(cls, weapon):
        frags_query = db.session.query(
            Frag.fragger.label('player_id'),
            Frag.weapon,
            func.sum(
                case([
                    (not_(Frag.tk), 1),
                ], else_=0)
            ).label('frags'),
        ).group_by(Frag.fragger, Frag.weapon).subquery()
        hits_query = db.session.query(
            Attack.attacker.label('player_id'),
            Attack.weapon,
            (
                func.sum(
                    case([
                        (and_(not_(Attack.ff), Attack.hitgroup == 'head'), 1),
                    ], else_=0)
                ) / func.sum(
                    case([
                        (not_(Attack.ff), 1),
                    ], else_=0)
                )
            ).label('hsp'),
        ).group_by(Attack.weapon, Attack.attacker).subquery()
        query = db.session.query(
            frags_query.c.player_id,
            Player.nickname,
            frags_query.c.weapon,
            frags_query.c.frags,
            hits_query.c.hsp,
        ).select_from(
            frags_query
        ).outerjoin(
            hits_query,
            and_(frags_query.c.player_id == hits_query.c.player_id,
                 frags_query.c.weapon == hits_query.c.weapon)
        ).join(
            Player,
            frags_query.c.player_id == Player.id
        )
        return query.filter(frags_query.c.weapon == weapon)

    @classmethod
    def weapon_death_stats(cls, weapon):
        deaths_query = db.session.query(
            Frag.victim.label('player_id'),
            Frag.weapon,
            func.sum(
                case([
                    (not_(Frag.tk), 1),
                ], else_=0)
            ).label('deaths'),
        ).group_by(Frag.victim, Frag.weapon).subquery()
        query = db.session.query(
            deaths_query.c.player_id,
            Player.nickname,
            deaths_query.c.weapon,
            deaths_query.c.deaths,
        ).select_from(
            deaths_query
        ).join(
            Player,
            deaths_query.c.player_id == Player.id
        )
        return query.filter(deaths_query.c.weapon == weapon)

    def average_rws(self):
        summary = db.session.query(PlayerOverallStatsSummary).filter_by(
            player_id=self.id).first()
        return summary.rws


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
        server = Server.query.filter_by(ip_address=ip_address,
                                        port=port).first()
        if server is None:
            server = Server()
            server.ip_address = ip_address
            server.port = port
            db.session.add(server)
        return server


match_players = db.Table('match_players',
                         db.Column('player_id', db.Integer,
                                   db.ForeignKey('player.id')),
                         db.Column('match_id', db.Integer,
                                   db.ForeignKey('csgo_match.id')),
                         db.Column('team', db.SmallInteger))


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


team_players = db.Table(
    'team_players',
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


class PlayerOverallStatsSummary(db.Model):

    player_id = db.Column(db.Integer, db.ForeignKey('player.id'),
                          primary_key=True)
    nickname = db.Column(db.Unicode(128), default=u'')
    frags = db.Column(db.Integer, default=0)
    tks = db.Column(db.Integer, default=0)
    assists = db.Column(db.Integer, default=0)
    deaths = db.Column(db.Integer, default=0)
    bomb_planted = db.Column(db.Integer, default=0)
    bomb_defused = db.Column(db.Integer, default=0)
    rounds_won = db.Column(db.Integer, default=0)
    rounds_lost = db.Column(db.Integer, default=0)
    rounds_dropped = db.Column(db.Integer, default=0)
    rounds_played = db.Column(db.Integer, default=0)
    won_1v1 = db.Column(db.Integer, default=0)
    won_1v2 = db.Column(db.Integer, default=0)
    won_1v3 = db.Column(db.Integer, default=0)
    won_1v4 = db.Column(db.Integer, default=0)
    won_1v5 = db.Column(db.Integer, default=0)
    k1 = db.Column(db.Integer, default=0)
    k2 = db.Column(db.Integer, default=0)
    k3 = db.Column(db.Integer, default=0)
    k4 = db.Column(db.Integer, default=0)
    k5 = db.Column(db.Integer, default=0)
    kdr = db.Column(db.Float, default=0.0)
    hsp = db.Column(db.Float, default=0.0)
    adr = db.Column(db.Float, default=0.0)
    fpr = db.Column(db.Float, default=0.0)
    rws = db.Column(db.Float, default=0.0)

    @classmethod
    def _update_rws(cls, player_id, day_range=30):
        """Update the specified player's RWS

        Parameters:
            player_id: The player ID
            day_range: An integer specifying the number of previous days'
                matches to include in the RWS calculation.
        """
        today = datetime.datetime.now()
        date_range_start = today - datetime.timedelta(days=day_range)
        query = db.session.query(
            PlayerRound.player_id,
            func.sum(PlayerRound.rws).label('total_rws'),
            func.count(PlayerRound.round_id).label('round_count')
        ).select_from(
            PlayerRound
        ).join(
            Round,
        ).join(
            CsgoMatch,
        ).filter(
            PlayerRound.player_id == player_id,
            CsgoMatch.end_time >= date_range_start
        ).group_by(PlayerRound.player_id)
        result = query.first()
        player_summary = cls.query.filter_by(player_id=player_id).first()
        if not player_summary:
            player_summary = PlayerOverallStatsSummary()
            player_summary.player_id = player_id
            db.session.add(player_summary)
        if result:
            player_summary.rws = result.total_rws / result.round_count
        else:
            player_summary.rws = 0.0
        db.session.commit()

    @classmethod
    def _update_stats(cls, player_id):
        player = Player.total_stats(player_id).filter_by(id=player_id).first()
        player_summary = cls.query.filter_by(player_id=player_id).first()
        if not player_summary:
            player_summary = PlayerOverallStatsSummary()
            player_summary.player_id = player_id
            db.session.add(player_summary)
        if player:
            player_summary.nickname = player.nickname
            player_summary.frags = player.frags
            player_summary.tks = player.tks
            player_summary.assists = player.assists
            player_summary.deaths = player.deaths
            player_summary.bomb_planted = player.bomb_planted
            player_summary.bomb_defused = player.bomb_defused
            player_summary.rounds_won = player.rounds_won
            player_summary.rounds_lost = player.rounds_lost
            player_summary.rounds_dropped = player.rounds_dropped
            player_summary.rounds_played = player.rounds_played
            player_summary.won_1v1 = player.won_1v1
            player_summary.won_1v2 = player.won_1v2
            player_summary.won_1v3 = player.won_1v3
            player_summary.won_1v4 = player.won_1v4
            player_summary.won_1v5 = player.won_1v5
            player_summary.k1 = player.k1
            player_summary.k2 = player.k2
            player_summary.k3 = player.k3
            player_summary.k4 = player.k4
            player_summary.k5 = player.k5
            player_summary.kdr = player.kdr
            player_summary.hsp = player.hsp
            player_summary.adr = player.adr
            player_summary.fpr = player.fpr
        db.session.commit()
        cls._update_rws(player_id)

    @classmethod
    def _update_all_stats(cls):
        players = db.session.query(Player.id).all()
        for player in players:
            cls._update_stats(player.id)


manager.create_api(Player, methods=['GET'],
                   include_columns=['nickname', 'steam_id'],
                   include_methods=['average_rws'])
