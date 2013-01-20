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
import re, urllib2
from flask import g, session, json, flash, redirect, escape, render_template
from flask.ext.login import login_user, logout_user
from werkzeug.urls import url_encode

from . import app, db, oid, login_manager
from .models import User, ROLE_USER, ROLE_ADMIN


_steam_id_re = re.compile('steamcommunity.com/openid/id/(.*?)$')

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
def load_user(userid):
    return User.query.get(int(userid))

@app.route('/login')
@oid.loginhandler
def login():
    if g.user is not None and g.user.is_authenticated():
        return redirect(oid.get_next_url())
    return oid.try_login('http://steamcommunity.com/openid')

@oid.after_login
def create_or_login(resp):
    match = _steam_id_re.search(resp.identity_url)
    g.user = User.get_or_create(match.group(1))
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
        g.user = User.query.get(session['user_id'])

@app.route('/logout')
def logout():
    flash('You are now logged out')
    logout_user()
    return redirect(oid.get_next_url())
