#!/usr/bin/env python
"""GoonPUG-stats log handling daemon"""

from __future__ import absolute_import, division
import os
import sys
import argparse
import threading
import SocketServer
import datetime
import re
import srcds.events.generic as generic_events
import srcds.events.csgo as csgo_events
from Queue import Queue, Empty
from daemon import Daemon

from goonpug import db
from goonpug.models import CsgoMatch, Round, Player, PlayerRound, Frag, \
        match_players


class GoonPugParser(object):

    """GoonPUG log parser class"""

    def __init__(self, server_address):
        self.eventq = Queue()
        self.event_handlers = {
            generic_events.LogFileEvent: self.handle_log_file,
            generic_events.ChangeMapEvent: self.handle_change_map,
            generic_events.ValidationEvent: self.handle_validation,
            generic_events.SuicideEvent: self.handle_suicide,
            generic_events.DisconnectionEvent: self.handle_disconnection,
            generic_events.KickEvent: self.handle_kick,
            generic_events.PlayerActionEvent: self.handle_player_action,
            generic_events.TeamActionEvent: self.handle_team_action,
            generic_events.WorldActionEvent: self.handle_world_action,
            generic_events.RoundEndTeamEvent: self.handle_round_end_team,
            csgo_events.CsgoKillEvent: self.handle_kill,
            csgo_events.CsgoAttackEvent: self.handle_attack,
            csgo_events.CsgoAssistEvent: self.handle_assist,
            csgo_events.SwitchTeamEvent: self.handle_switch_team,
        }
        self._compile_regexes()
        self.server = server_address
        self.reset_server_state()

    def _compile_regexes(self):
        """Add event types"""
        self.event_types = []
        for cls in self.event_handlers.keys():
            regex = re.compile(cls.regex)
            self.event_types.append((regex, cls))

    def parse_line(self, line):
        """Parse a single log line"""
        line = line.strip()
        for (regex, cls) in self.event_types:
            match = regex.match(line)
            if match:
                event = cls.from_re_match(match)
                self.eventq.put(event)
                return

    def read(self, filename):
        """Read in a log file"""
        fd = open(filename)
        for line in fd.readlines():
            self.parse_line(line)
        fd.close()

    def process_events(self):
        while True:
            event = None
            try:
                event = self.eventq.get(60)
            except Empty:
                return
            handler = self.event_handlers[type(event)]
            handler(event)
            self.eventq.task_done()

    def reset_server_state(self):
        self.map = ''
        self.last_restart = None
        self.lo3_count = 0
        self.team_a = []
        self.team_b = []
        self.ts = []
        self.live_ts = 0
        self.cts = []
        self.live_cts = 0
        self.v1 = {}
        self.drops = []
        self.match = None
        self.round = None
        self.period = 0
        self.player_rounds = {}

    def _restart_match(self):
        # if there is a match in progress than we just want to reset everything
        db.session.rollback()
        self.match = CsgoMatch()
        # we only support pugs right now
        self.match.type = CsgoMatch.TYPE_PUG
        self.match.map = self.map
        self.team_a = self.ts
        self.team_b = self.cts
        for player in db.session.query.(Player).filter( \
                Player.steam_id.in_(self.team_a)):
            match_players.insert().values(player_id=player.id,
                                          match_id=self.match.id,
                                          team=CsgoMatch.TEAM_A)
        for player in db.session.query.(Player).filter( \
                Player.steam_id.in_(self.team_b)):
            match_players.insert().values(player_id=player.id,
                                          match_id=self.match.id,
                                          team=CsgoMatch.TEAM_B)
        self.period = 1
        self.round = None
        self.player_rounds = {}

    def _start_round(self):
        self.round = Round()
        self.round.match_id = self.match.id
        self.round.period = self.period
        db.session.add(self.round)
        for player in db.session.query.(Player).filter( \
                Player.steam_id.in_(self.team_a + self.team_b)):
            player_round = PlayerRound()
            player_round.player_id = player
            player_round.round_id = self.round.id
            player_rounds[player.steam_id] = player_round
            db.session.add(player_round)

    def _end_round(self):
        self.round = None
        self.player_rounds = {}

    def handle_log_file(self, event):
        pass

    def handle_change_map(self, event):
        self.reset_server_state()
        if event.started:
            self.mapname = event.mapname

    def handle_validation(self, event):
        # if this player is not in our db, add them
        player = Player.get_or_create(event.player.id64())
        if player.nickname != event.player.name:
            # If this player's nick has changed since the last time we saw them
            # update it
            session = db.Session.object_session(player)
            player.nickname = event.player.name
            session.commit()

    def handle_suicide(self, event):
        if not self.round:
            return
        steam_id = event.player.id64()
        if self.player_rounds.has_key(steam_id):
            self.player_rounds[steam_id].dead = True
        if event.player.team == 'CT':
            live_cts -= 1
            if live_cts == 1:
                for steam_id in self.ts:
                    if not self.player_rounds[steam_id].dead:
                        self.v1[steam_id] = live_cts
                        break
        elif event.player.team == 'TERRORIST':
            live_ts -= 1
            if live_ts == 1:
                for steam_id in self.ts:
                    if not self.player_rounds[steam_id].dead:
                        self.v1[steam_id] = live_cts
                        break

    def handle_disconnection(self, event):
        steam_id = event.player.id64()
        if steam_id in ts:
            ts.remove(steam_id)
            self.drops.append(steam_id)
        elif steam_id in cts:
            cts.remove(steam_id)
            self.drops.append(steam_id)

    def handle_kick(self, event):
        # the leaving part should be taken care of by handle_disconnection
        pass

    def handle_player_action(self, event):
        pass

    def handle_team_action(self, event):
        pass

    def handle_world_action(self, event):
        # look for 3 or more restarts within 5 seconds of each other.
        # assume that this is a lo3 (or loN)
        if event.action.startswith('Restart_Round_'):
            if not last_restart:
                self.lo3_count = 1
            else:
                delta = event.timestamp - last_restart
                if delta.days == 0 and delta.seconds <= 5:
                    self.lo3_count += 1
                else:
                    self.lo3_count = 1
            last_restart = event.timestamp
            if self.lo3_count >= 3:
                self._restart_match()
                self.match.start_time = event.timestamp
        elif event.action == 'Round_Start':
            self._start_round()
        elif event.action == 'Round_End':
            self._end_round()

    def handle_round_end_team(self, event):
        pass

    def handle_kill(self, event):
        if not self.round:
            return
        if event.player.is_bot:
            steam_id = 0
        else:
            steam_id = event.player.id64()
        if event.target.is_bot:
            target_id = 0
        else:
            target_id = event.target.id64()
        if self.player_rounds.has_key(steam_id):
            self.player_rounds[steam_id].damage += event.damage
        if self.player_rounds.has_key(target_id):
            self.player_rounds[target_id].dead = True
            if event.target.team == 'CT':
                live_cts -= 1
                if live_cts == 1:
                    for steam_id in self.cts:
                        if not self.player_rounds[steam_id].dead:
                            self.v1[steam_id] = live_ts
                            break
            elif event.target.team == 'TERRORIST':
                live_ts -= 1
                if live_ts == 1:
                    for steam_id in self.ts:
                        if not self.player_rounds[steam_id].dead:
                            self.v1[steam_id] = live_cts
                            break
            self._check_v1(event.player)
        fragger = Player.query.filter_by(steam_id=steam_id).first()
        victim = Player.query.filter_by(steam_id=target_id).first()
        frag = Frag()
        frag.round_id = self.round.id
        frag.fragger = fragger.id
        frag.victim = victim.id
        frag.weapon = event.weapon
        frag.headshot = event.headshot
        db.session.add(frag)

    def handle_attack(self, event):
        if not self.round:
            return
        steam_id = event.player.id64()
        if self.player_rounds.has_key(steam_id):
            self.player_rounds[steam_id].damage += event.damage

    def handle_assist(self, event):
        if not self.round:
            return
        steam_id = event.player.id64()
        if self.player_rounds.has_key(steam_id):
            self.player_rounds[steam_id].assists += 1

    def handle_switch_team(self, event):
        if event.player.is_bot
            steam_id = 0
        else:
            steam_id = event.player.id64()
        if orig_team == 'CT':
            self.cts.remove(steam_id)
        elif orig_team == 'TERRORIST':
            self.ts.remove(steam_id)
        if new_team == 'CT':
            self.cts.append(steam_id)
        elif new_team == 'TERRORIST':
            self.ts.append(steam_id)
        if not self.match and not self.round:
            return
        player = db.session.query(Player).filter(steam_id=steam_id).first()
        if self.match and (steam_id not in self.team_a
                           and steam_id not in self.team_b):
            if (new_team == 'TERRORIST' and (self.period % 2) == 1) \
                    or (new_team == 'CT' and (self.period % 2) == 0):
                match_players.insert().values(player_id=player.id,
                                              match_id=self.match.id,
                                              team=CsgoMatch.TEAM_A)
            elif (new_team == 'CT' and (self.period % 2) == 1) \
                    or (new_team == 'TERRORIST' and (self.period % 2) == 0):
                match_players.insert().values(player_id=player.id,
                                              match_id=self.match.id,
                                              team=CsgoMatch.TEAM_B)
        if self.round:
            if self.player_rounds.has_key(steam_id):
                db.session.delete(self.player_rounds[steam_id])
            player_round = PlayerRound()
            player_round.player_id = player.id
            player_round.round_id = round.id
            self.player_rounds[steam_id] = player_round
            db.session.add(player_round)


log_parsers = {}


class GoonPugLogHandler(SocketServer.DatagramRequestHandler):

    def handle(self):
        data = self.request[0].strip()
        # Strip the 4-byte header and the first 'R' character
        #
        # There is no documentation for this but I am guessing the 'R' stands
        # for 'Remote'? Either way normal log entires are supposed to start
        # with 'L', but the UDP packets start with 'RL'
        data = data[5:]
        socket = self.request[1]
        if not log_parsers.has_key(self.client_address):
            parser = GoonPugParser(self.client_address)
            thread = threading.Thread(target=parser.process_events)
            log_parsers[self.client_address] = (thread, parser)
            thread.start()
        log_parsers[self.client_address][1].parse_line(data)

    def handle_timeout(self):
        for server in log_parsers.keys():
            (thread, parser) = log_parsers[server]
            if not thread.is_alive():
                thread.join()
                del log_parsers[server]


class GoonPugDaemon(Daemon):

    def __init__(self, pidfile, port=27500, stdout=sys.stdout, stderr=sys.stderr):
        super(GoonPugDaemon, self).__init__(pidfile, stdout=stdout, stderr=stderr)
        self.port = port
        self.server = SocketServer.UDPServer(('0.0.0.0', self.port),
                                        GoonPugLogHandler)
        self.server.timeout = 30

    def run(self):
        self.server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description='GoonPUG logparser')
    parser.add_argument('-p', '--port', dest='port', action='store', type=int,
                        default=27500, help='port to listen on')
    parser.add_argument('-d', '--daemon', action='store_true',
                        help='run goonpugd as a daemon')
    parser.add_argument('--pidfile', action='store', type=str,
                        help='path to the pidfile',
                        default='/tmp/goonpugd.pid')
    args = parser.parse_args()
    daemon = GoonPugDaemon(args.pidfile, port=args.port)
    if not args.daemon:
        try:
            daemon.run()
        except KeyboardInterrupt:
            daemon.server.shutdown()
            daemon.stop()
            sys.exit()
    else:
        daemon.start()


if __name__ == '__main__':
    main()
