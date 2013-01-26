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

def get_player_overall_stats(player):
    stats = PlayerOverallStats.query.filter_by(player_id=player.id).first()
    return stats

@app.route('/player/<int:player_id>')
def player(player_id=None):
    g.player = Player.query.get(player_id)
    g.stats = db.session.query(player_overall_stats).filter_by(player_id=player_id).first()
    print g.stats
    return render_template('player.html')

@app.route('/stats')
@app.route('/stats/<int:page>')
def stats(page=1):
    query = db.session.query(player_overall_stats)
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
