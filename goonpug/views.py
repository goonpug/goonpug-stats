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
from flask import g, session, json, flash, redirect, escape, render_template
from flask.ext.login import login_user, logout_user
from werkzeug.urls import url_encode

from . import app, db, oid, login_manager
from .models import Frag, CsgoMatch, Player, PlayerRound, Round


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

def get_player_stats(player, match=None):
    stats = {}
    if match:
        matches = player.matches.filter(CsgoMatch.id == match.id)
    else:
        matches = player.matches
    rounds = []
    for match in matches:
        rounds.append(match.rounds)
    player_rounds = []
    stats['frags'] = 0
    stats['singles'] = 0
    stats['doubles'] = 0
    stats['triples'] = 0
    stats['quads'] = 0
    stats['aces'] = 0
    headshots = 0
    for round in rounds:
        round_frags = round.frags.filter(Frag.fragger == g.player.id)
        if len(round_frags) == 1:
            stats['singles'] += 1
        elif len(round_frags) == 2:
            stats['doubles'] += 1
        elif len(round_frags) == 3:
            stats['triples'] += 1
        elif len(round_frags) == 4:
            stats['quads'] += 1
        elif len(round_frags) == 5:
            stats['aces'] += 1
        stats['frags'] += len(round_frags)
        for frag in round_frags:
            if frag.headshot:
                headshots += 1
        player_rounds.append(round.player_rounds.filter(
            PlayerRound.player_id == player.id))
    try:
        stats['hsp'] = headshots / stats['frags']
    except ZeroDivisionError:
        stats['hsp'] = 0.0
    stats['rounds_played']= len(player_rounds)
    try:
        stats['fpr'] = stats['frags'] / stats['rounds_played']
    except ZeroDivisionError:
        stats['fpr'] = 0.0
    stats['assists'] = 0
    stats['deaths'] = 0
    stats['plants'] = 0
    stats['defuses'] = 0
    stats['v1'] = 0
    stats['v2'] = 0
    stats['v3'] = 0
    stats['v4'] = 0
    stats['v5'] = 0
    stats['damage'] = 0
    total_rws = 0.0
    for round in player_rounds:
        stats['damage'] += round.damage
        stats['assists'] += round.assists
        if round.dead:
            stats['deaths'] += 1
        stats['damage'] += round.damage
        if round.bomb_planted:
            stats['plants'] += 1
        if round.bomb_defused:
            stats['defuses'] += 1
        if won_1v == 1:
            stats['v1'] += 1
        if won_1v == 2:
            stats['v2'] += 1
        if won_1v == 3:
            stats['v3'] += 1
        if won_1v == 4:
            stats['v4'] += 1
        if won_1v == 5:
            stats['v5'] += 1
        total_rws += round.rws
    try:
        stats['adr'] = stats['damage'] / stats['rounds_played']
    except ZeroDivisionError:
        stats['adr'] = 0.0
    try:
        stats['rws'] = total_rws / stats['rounds_played']
    except ZeroDivisionError:
        stats['rws'] = 0.0
    return stats

@app.route('/player/<int:player_id>')
def player(player_id):
    g.player = Player.query.get(player_id)
    g.stats = get_player_stats(g.player)
    return render_template('player.html')
