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
from flask.ext.sqlalchemy import SQLAlchemy

from . import app


app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://goonpug_user:password1@localhost/goonpug'
db = SQLAlchemy(app)


class Server(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128))
    address = db.Column(db.String(32), unique=True)
    rcon_password = db.Column(db.String(64))


class Player(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64))
    steamid = db.Column(db.String(32), unique=True)

    def __init__(self, steamid, name):
        self.steamid = steamid
        self.name = name

    def __repr__(self):
        return '<Player %r<%r>>' % (self.name, self.steamid)
