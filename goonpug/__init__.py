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
import os
from flask import Flask
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.login import LoginManager
from flask.ext.openid import OpenID


app = Flask(__name__)

app.config.from_object('goonpug.default_config')
app.config.from_envvar('GOONPUG_CONFIG')

app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://%s:%s@%s:%d/%s' % (
    app.config['MYSQL_USER'], app.config['MYSQL_PASSWORD'],
    app.config['MYSQL_SERVER'], app.config['MYSQL_PORT'],
    app.config['MYSQL_DATABASE'],)

# DB stuff
db = SQLAlchemy(app)

# Login stuff
login_manager = LoginManager()
login_manager.setup_app(app)
oid = OpenID(app)

from . import models, views
