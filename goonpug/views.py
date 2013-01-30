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

from __future__ import absolute_import, division
import re, urllib2
from flask import g, session, json, flash, redirect, escape, render_template, \
    request
from flask.ext.login import login_user, logout_user
from flask.ext.sqlalchemy import Pagination
from werkzeug.urls import url_encode
from sqlalchemy.exc import NoSuchTableError
from sqlalchemy import func, case, literal, not_, and_, or_, alias

from . import app, db, oid, login_manager, metadata
from .models import Frag, CsgoMatch, Player, PlayerRound, Round, \
    match_players

_steam_id_re = re.compile('steamcommunity.com/openid/id/(.*?)$')

try:
    player_overall_stats = db.Table('player_overall_stats', metadata,
                db.Column('player_id', db.Integer, primary_key=True),
                autoload=True)
except NoSuchTableError:
    pass

def get_steam_userinfo(steam_id):
    options = {
        'key': app.config['STEAM_API_KEY'],
        'steamids': steam_id
    }
    url = 'http://api.steampowered.com/ISteamUser/' \
          'GetPlayerSummaries/v0002/?%s' % url_encode(options)
    retval = json.load(urllib2.urlopen(url))
    return retval['response']['players'][0] or {}

@app.route('/')
def index():
    return render_template('index.html')

@login_manager.user_loader
def load_user(user_id):
    return Player.query.get(int(user_id))

@app.route('/login')
@oid.loginhandler
def login():
    if g.user is not None and g.user.is_authenticated():
        return redirect(oid.get_next_url())
    return oid.try_login('http://steamcommunity.com/openid')

@oid.after_login
def create_or_login(resp):
    match = _steam_id_re.search(resp.identity_url)
    g.user = Player.get_or_create(int(match.group(1)))
    steam_data = get_steam_userinfo(g.user.steam_id)
    g.user.nickname = steam_data['personaname']
    db.session.commit()
    login_user(g.user)
    flash('You are now logged in')
    return redirect(oid.get_next_url())

@app.before_request
def before_request():
    g.user = None
    if 'user_id' in session:
        g.user = Player.query.get(session['user_id'])

@app.route('/logout')
def logout():
    flash('You are now logged out')
    logout_user()
    return redirect(oid.get_next_url())

def get_player_stats(player_id=None, match_id=None):
    if match_id and not player_id:
        return None
    player_round_stats = db.session.query(
        PlayerRound,
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
        func.sum(
            case([
                (and_(Frag.headshot == True, not_(Frag.tk)), 1),
            ], else_=0)
        ).label('headshots'),
    ).select_from(
        PlayerRound
    ).outerjoin(
        Frag,
        and_(Frag.fragger == PlayerRound.player_id, PlayerRound.round_id == Frag.round_id)
    ).group_by(PlayerRound.round_id, PlayerRound.player_id).subquery()
    query = db.session.query(
        player_round_stats.c.player_id,
        Round.match_id,
        func.sum(player_round_stats.c.frags).label('frags'),
        func.sum(player_round_stats.c.tks).label('tks'),
        func.sum(player_round_stats.c.headshots).label('headshots'),
        func.sum(player_round_stats.c.assists).label('assists'),
        func.sum(
            case([
                (player_round_stats.c.dead, 1),
            ], else_=0)
        ).label('deaths'),
        func.sum(player_round_stats.c.damage).label('damage'),
        func.sum(
            case([
                (player_round_stats.c.bomb_planted, 1),
            ], else_=0)
        ).label('bomb_planted'),
        func.sum(
            case([
                (player_round_stats.c.bomb_defused, 1),
            ], else_=0)
        ).label('bomb_defused'),
        func.avg(player_round_stats.c.rws).label('rws'),
        func.sum(
            case([
                (and_(player_round_stats.c.team == Round.winning_team, not_(player_round_stats.c.dropped)), 1)
            ], else_=0)
        ).label('rounds_won'),
        func.sum(
            case([
                (and_(player_round_stats.c.team != Round.winning_team, not_(player_round_stats.c.dropped)), 1)
            ], else_=0)
        ).label('rounds_lost'),
        func.sum(
            case([
                (player_round_stats.c.won_1v == 1, 1),
            ], else_=0)
        ).label('won_1v1'),
        func.sum(
            case([
                (player_round_stats.c.won_1v == 2, 1),
            ], else_=0)
        ).label('won_1v2'),
        func.sum(
            case([
                (player_round_stats.c.won_1v == 3, 1),
            ], else_=0)
        ).label('won_1v3'),
        func.sum(
            case([
                (player_round_stats.c.won_1v == 4, 1),
            ], else_=0)
        ).label('won_1v4'),
        func.sum(
            case([
                (player_round_stats.c.won_1v == 5, 1),
            ], else_=0)
        ).label('won_1v5'),
        func.sum(
            case([
                (player_round_stats.c.frags == 1, 1),
            ], else_=0)
        ).label('k1'),
        func.sum(
            case([
                (player_round_stats.c.frags == 2, 1),
            ], else_=0)
        ).label('k2'),
        func.sum(
            case([
                (player_round_stats.c.frags == 3, 1),
            ], else_=0)
        ).label('k3'),
        func.sum(
            case([
                (player_round_stats.c.frags == 4, 1),
            ], else_=0)
        ).label('k4'),
        func.sum(
            case([
                (player_round_stats.c.frags == 5, 1),
            ], else_=0)
        ).label('k5'),
    ).select_from(player_round_stats).join(Round)
    if match_id:
        return query.group_by(player_round_stats.c.player_id, Round.match_id).filter(player_round_stats.c.player_id == player_id, Round.match_id == match_id)
    elif player_id:
        return query.group_by(player_round_stats.c.player_id).filter(player_round_stats.c.player_id == player_id).first()
    else:
        return query.group_by(player_round_stats.c.player_id)

@app.route('/player/<int:player_id>')
def player(player_id=None):
    g.player = Player.query.get(player_id)
    g.stats = get_player_stats(player_id)
    return render_template('player.html')

@app.route('/stats')
@app.route('/stats/<int:page>')
def stats(page=1):
    subquery = get_player_stats().subquery()
    query = db.session.query(
        subquery,
        Player.nickname,
        (subquery.c.frags / subquery.c.deaths).label('kdr'),
        (subquery.c.headshots / subquery.c.frags).label('hsp'),
        (subquery.c.damage / (subquery.c.rounds_won + subquery.c.rounds_lost)).label('adr'),
        (subquery.c.damage / (subquery.c.rounds_won + subquery.c.rounds_lost)).label('fpr'),
    ).join(Player)
    order = request.args.get('order_by', default='rws', type=str)
    asc = request.args.get('asc', default=0, type=int)
    per_page = request.args.get('per_page', default=10, type=int)
    if asc:
        query = query.order_by(asc(order))
    else:
        query = query.order_by(db.desc(order))
    total = query.count()
    items = query.limit(per_page).offset((page - 1) * per_page).all()
    g.pagination = Pagination(query, page, per_page, total, items)
    return render_template('stats_player.html')
