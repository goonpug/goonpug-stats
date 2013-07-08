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
from srcds.objects import SteamId

from .models import Player
from . import manager


def player_pre_many(search_params=None, **kw):
    if not search_params:
        return
    elif 'auth_id' in search_params:
        filt = dict(name='steam_id', op='eq',
                    val=SteamId(search_params['auth_id']).id64())
        if 'filters' not in search_params:
            search_params['filters'] = []
        search_params['filters'].append(filt)


manager.create_api(Player, methods=['GET'],
                   include_columns=['nickname', 'steam_id'],
                   include_methods=['average_rws', 'auth_id'],
                   preprocessors={'GET_MANY': [player_pre_many]})
