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

from . import app, db


ROLE_USER = 0
ROLE_ADMIN = 1


class User(db.Model, UserMixin):

    id = db.Column(db.Integer, primary_key=True)
    steam_id = db.Column(db.String(40))
    nickname = db.Column(db.String(128))
    role = db.Column(db.SmallInteger, default=ROLE_USER)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'))

    @staticmethod
    def get_or_create(steam_id):
        user = User.query.filter_by(steam_id=steam_id).first()
        if user is None:
            user = User()
            user.steam_id = steam_id
            db.session.add(user)
        return user


class Server(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128))
    address = db.Column(db.String(32), unique=True)
    rcon_password = db.Column(db.String(64))


class Player(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64))
    steam_id = db.Column(db.String(32), unique=True)

    def __init__(self, steamid, name):
        self.steamid = steamid
        self.name = name

    def __repr__(self):
        return '<Player %r<%r>>' % (self.name, self.steamid)
