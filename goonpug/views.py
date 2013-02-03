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
    request, url_for, Markup
from flask.ext.login import login_user, logout_user
from flask.ext.sqlalchemy import Pagination
from werkzeug.urls import url_encode
from sqlalchemy.exc import NoSuchTableError
from sqlalchemy.orm.exc import NoResultFound

from . import app, db, oid, login_manager, metadata
from .models import Frag, CsgoMatch, Player, PlayerRound, Round, \
    match_players

_steam_id_re = re.compile('steamcommunity.com/openid/id/(.*?)$')

def url_for_other_page(page):
    args = request.args.to_dict().copy()
    args['page'] = page
    return url_for(request.endpoint, **args)
app.jinja_env.globals['url_for_other_page'] = url_for_other_page

def sortable_th(display, title="", column_name=""):
    if not column_name:
        column_name = display.lower()
    sort_order = 'desc'
    ico = ''
    if request.view_args.has_key('sort_by') \
            and column_name == request.view_args['sort_by']:
        ico = 'icon-chevron-down'
        if request.view_args.has_key('sort_order') \
                and request.view_args['sort_order'] == 'asc':
            sort_order = 'desc'
            ico = 'icon-chevron-up'
        else:
            sort_order = 'asc'
    url = url_for(request.endpoint, sort_by=column_name, sort_order=sort_order)
    return Markup('<th><a href="%s" rel="tooltip" title="%s">'
                  '<i class="%s"></i> %s</a></th>'% (url, title, ico, display))
app.jinja_env.globals['sortable_th'] = sortable_th

def last_updated():
    (last_updated,) = db.session.query(CsgoMatch.end_time).order_by(db.desc('end_time')).first()
    return last_updated.strftime(u'%Y-%m-%d %H:%M:%S %Z')
app.jinja_env.globals['last_updated'] = last_updated

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
    print resp.identity_url
    match = _steam_id_re.search(resp.identity_url)
    g.user = Player.get_or_create(int(match.group(1)))
    steam_data = get_steam_userinfo(g.user.steam_id)
    g.user.nickname = steam_data['personaname']
    db.session.commit()
    login_user(g.user)
    flash(u'You are now logged in')
    return redirect(oid.get_next_url())

@app.before_request
def before_request():
    g.user = None
    if 'user_id' in session:
        g.user = Player.query.get(session['user_id'])

@app.route('/logout')
def logout():
    flash(u'You are now logged out')
    logout_user()
    return redirect(oid.get_next_url())

@app.route('/player/<int:player_id>')
def player(player_id=None):
    if player_id:
        g.player = Player.query.get(player_id)
        query = Player.overall_stats().filter_by(id=player_id)
        try:
            g.stats = query.one()
        except NoResultFound:
            g.stats = None
    return render_template('player.html')

@app.route('/stats/')
def stats():
    subquery = Player.overall_stats().filter(
        'rounds_won + rounds_lost >= 75'
    ).subquery()
    g.rws_leaders = db.session.query(
        subquery.c.nickname,
        subquery.c.player_id,
        subquery.c.rws
    ).order_by(
        db.desc('rws')
    ).limit(5).all()
    g.kdr_leaders = db.session.query(
        subquery.c.nickname,
        subquery.c.player_id,
        subquery.c.kdr
    ).order_by(
        db.desc('kdr')
    ).limit(5).all()
    g.ace_leaders = db.session.query(
        subquery.c.nickname,
        subquery.c.player_id,
        subquery.c.k5
    ).filter('k5 > 0').order_by(
        db.desc('k5')
    ).limit(5).all()
    return render_template('stats.html')

@app.route('/stats/player/')
@app.route('/stats/player/sort/<sort_by>/')
@app.route('/stats/player/sort/<sort_by>/<int:page>')
@app.route('/stats/player/sort/<sort_by>/order/<sort_order>/')
@app.route('/stats/player/sort/<sort_by>/order/<sort_order>/<int:page>')
def stats_player(page=1, sort_by='rws', sort_order='desc'):
    query = Player.overall_stats().filter('rounds_won + rounds_lost >= 75')
    per_page = 20
    if sort_order == 'asc':
        query = query.order_by(db.asc(sort_by))
    else:
        query = query.order_by(db.desc(sort_by))
    total = query.count()
    items = query.limit(per_page).offset((page - 1) * per_page).all()
    g.pagination = Pagination(query, page, per_page, total, items)
    return render_template('stats_player.html')
