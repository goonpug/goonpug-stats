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
        match_players, Server


VERBOSE = False


class GoonPugParser(object):

    """GoonPUG log parser class"""

    def __init__(self, server_address):
        self.eventq = Queue(100)
        self.event_handlers = {
            generic_events.LogFileEvent: self.handle_log_file,
            generic_events.ChangeMapEvent: self.handle_change_map,
            generic_events.EnterGameEvent: self.handle_enter_game,
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
        self.server = Server.get_or_create(server_address[0], server_address[1])
        db.session.commit()
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
                event = self.eventq.get(False)
                handler = self.event_handlers[type(event)]
                handler(event)
                self.eventq.task_done()
            except Empty:
                pass

    def reset_server_state(self):
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
        self.frags = []
        self.player_rounds = {}

    def _restart_match(self, timestamp):
        # if there was an existing match in progress delete it
        if self.match:
            print 'abandoning match %s' % self.match
            db.session.expunge(self.match)
        if self.round:
            print 'abandoning round %s' % self.round
            db.session.expunge(self.round)
        db.session.commit()
        # If this match exists already, delete the existing one
        match = db.session.query(CsgoMatch).filter_by(server_id=self.server.id,
            start_time=timestamp).first()
        if match:
            db.session.expunge(match)
        self.match = CsgoMatch()
        # we only support pugs right now
        self.match.type = CsgoMatch.TYPE_PUG
        self.match.map = self.mapname
        self.match.server_id = self.server.id
        self.match.start_time = timestamp
        db.session.add(self.match)
        db.session.commit()
        self.team_a = self.ts
        self.team_b = self.cts
        for steam_id in self.team_a:
            player = db.session.query(Player).filter_by(steam_id=steam_id).first()
            db.session.execute(match_players.insert().values(
                player_id=player.id,
                match_id=self.match.id,
                team=CsgoMatch.TEAM_A))
        for steam_id in self.team_b:
            player = db.session.query(Player).filter_by(steam_id=steam_id).first()
            db.session.execute(match_players.insert().values(
                player_id=player.id,
                match_id=self.match.id,
                team=CsgoMatch.TEAM_B))
        db.session.commit()
        self.period = 1
        self.round = None
        self.frags = []
        self.player_rounds = {}
        self.t_score = 0
        self.ct_score = 0
        print 'started new match %s' % self.match

    def _end_match(self, event):
        self._commit_round()
        self.match.end_time = event.timestamp
        db.session.commit()
        print 'ended match %s' % self.match
        self.match = None
        self.round = None

    def _commit_round(self):
        db.session.add(self.round)
        db.session.commit()
        for player_round in self.player_rounds.values():
            player_round.round_id = self.round.id
            db.session.add(player_round)
        for frag in self.frags:
            frag.round_id = self.round.id
            db.session.add(frag)
        db.session.commit()
        self.round = None
        self.frags = []
        self.player_round = {}

    def _start_round(self):
        if self.round:
            self._commit_round()
        self.round = Round()
        self.round.match_id = self.match.id
        self.round.period = self.period
        self.player_rounds = {}
        for steam_id in (self.team_a + self.team_b):
            player = Player.query.filter_by(steam_id=steam_id).first()
            player_round = PlayerRound()
            player_round.player_id = player.id
            self.player_rounds[player.steam_id] = player_round
        self.defuser = None
        self.planter = None
        self.live_cts = len(self.cts)
        self.live_ts = len(self.ts)

    def _end_round(self, event):
        rounds_played = self.t_score + self.ct_score
        if rounds_played == 0:
            self.period = 1
        elif rounds_played < 30 and (rounds_played % 15) == 0:
            self.period += 1
        elif rounds_played >= 30 and (rounds_played % 5) == 0:
            self.period += 1
        # check for end of match conditions
        if self.period <= 2 and (self.t_score == 16 or self.ct_score == 16):
            # a team won in regulation
            self._end_match(event)
        elif rounds_played == 30 and self.match.type == CsgoMatch.TYPE_PUG:
            # match was a draw
            self._end_match(event)
        elif self.period > 2 and (self.t_score == 6 or self.t_score == 6):
            # a team won in OT
            self._end_match(event)

    def _sfui_notice(self, winning_team, defused=False, exploded=False):
        if winning_team == 'TERRORIST':
            team = self.ts
            if self.period % 2 == 0:
                self.round.winning_team = CsgoMatch.TEAM_A
            else:
                self.round.winning_team = CsgoMatch.TEAM_B
        else:
            team = self.cts
            if self.period % 2 == 0:
                self.round.winning_team = CsgoMatch.TEAM_B
            else:
                self.round.winning_team = CsgoMatch.TEAM_A
        for steam_id, v1 in self.v1.items():
            if steam_id in team:
                self.player_rounds[steam_id].won_1v = v1
            break
        team_damage = 0
        for steam_id in team:
            if not self.player_rounds[steam_id].damage:
                self.player_rounds[steam_id].damage = 0
            team_damage += self.player_rounds[steam_id].damage
        if defused or exploded:
            multi = 70.0
        else:
            multi = 100.0
        for steam_id in team:
            try:
                rws = multi * (self.player_rounds[steam_id].damage / team_damage)
            except ZeroDivisionError:
                rws = 0.0
            if defused and self.defuser == steam_id:
                rws += 30.0
            if exploded and self.planter == steam_id:
                rws += 30.0
            self.player_rounds[steam_id].rws = rws

    def handle_log_file(self, event):
        pass

    def handle_change_map(self, event):
        if VERBOSE:
            print event
        self.reset_server_state()
        if event.started:
            self.mapname = event.mapname

    def handle_enter_game(self, event):
        if VERBOSE:
            print event
        steam_id = event.player.steam_id.id64()
        Player.get_or_create(steam_id, nickname=event.player.name)
        db.session.commit()

    def handle_suicide(self, event):
        if not self.match:
            return
        if VERBOSE:
            print event
        steam_id = event.player.steam_id.id64()
        if self.player_rounds.has_key(steam_id):
            self.player_rounds[steam_id].dead = True
        if event.player.team == 'CT':
            self.live_cts -= 1
            if self.live_cts == 1:
                for steam_id in self.cts:
                    if not self.player_rounds[steam_id].dead:
                        self.v1[steam_id] = self.live_ts
                        break
        elif event.player.team == 'TERRORIST':
            self.live_ts -= 1
            if self.live_ts == 1:
                for steam_id in self.ts:
                    if not self.player_rounds[steam_id].dead:
                        self.v1[steam_id] = self.live_cts
                        break

    def handle_disconnection(self, event):
        if VERBOSE:
            print event
        steam_id = event.player.steam_id.id64()
        if self.match:
            self.drops.append(steam_id)

    def handle_kick(self, event):
        # the leaving part should be taken care of by handle_disconnection
        pass

    def handle_player_action(self, event):
        if not self.match:
            return
        if VERBOSE:
            print event
        if event.action == "Planted_The_Bomb":
            self.planter = event.player.steam_id.id64()
            self.player_rounds[self.planter].bomb_planted = True
        elif event.action == "Defused_The_Bomb":
            self.defuser = event.player.steam_id.id64()
            self.player_rounds[self.defuser].bomb_defused = True

    def handle_team_action(self, event):
        if not self.match or not self.round:
            return
        if VERBOSE:
            print event
        if event.action == "SFUI_Notice_Bomb_Defused":
            self._sfui_notice(event.team, defused=True)
        elif event.action == "SFUI_Notice_Target_Bombed":
            self._sfui_notice(event.team, exploded=True)
        elif event.action == "SFUI_Notice_Terrorists_Win" \
                or event.action == "SFUI_Notice_CTs_Win" \
                or event.action == "SFUI_Notice_Target_Saved":
            self._sfui_notice(event.team)

    def handle_world_action(self, event):
        # look for 3 or more restarts within 5 seconds of each other.
        # assume that this is a lo3 (or loN)
        if VERBOSE:
            print event
        if event.action.startswith('Restart_Round_'):
            if self.round:
                self.round = None
            if not self.last_restart:
                self.lo3_count = 1
            else:
                delta = event.timestamp - self.last_restart
                if delta.days == 0 and delta.seconds <= 5:
                    self.lo3_count += 1
                else:
                    self.lo3_count = 1
            self.last_restart = event.timestamp
            if self.lo3_count >= 3:
                self._restart_match(event.timestamp)
        elif event.action == 'Round_Start':
            if self.match:
                self._start_round()
        elif event.action == 'Round_End':
            if self.match:
                self._end_round(event)

    def handle_round_end_team(self, event):
        if VERBOSE:
            print event
        if event.team == 'CT':
            self.ct_score = event.score
        elif event.team == 'TERRORIST':
            self.t_score = event.score

    def handle_kill(self, event):
        if not self.match or not self.round:
            return
        if VERBOSE:
            print event
        steam_id = event.player.steam_id.id64()
        target_id = event.target.steam_id.id64()
        self.player_rounds[target_id].dead = True
        if event.target.team == 'CT':
            self.live_cts -= 1
            if self.live_cts == 1:
                for steam_id in self.cts:
                    if not self.player_rounds[steam_id].dead:
                        self.v1[steam_id] = self.live_ts
                        break
        elif event.target.team == 'TERRORIST':
            self.live_ts -= 1
            if self.live_ts == 1:
                for steam_id in self.ts:
                    if not self.player_rounds[steam_id].dead:
                        self.v1[steam_id] = self.live_cts
                        break
        fragger = Player.query.filter_by(steam_id=steam_id).first()
        victim = Player.query.filter_by(steam_id=target_id).first()
        frag = Frag()
        frag.fragger = fragger.id
        frag.victim = victim.id
        frag.weapon = event.weapon
        frag.headshot = event.headshot
        if event.player.team == event.target.team:
            frag.tk = True
        self.frags.append(frag)

    def handle_attack(self, event):
        if not self.match or not self.round:
            return
        if VERBOSE:
            print event
        steam_id = event.player.steam_id.id64()
        if self.player_rounds.has_key(steam_id):
            player_round = self.player_rounds[steam_id]
            if event.player.team != event.target.team:
                if player_round.damage is None:
                    player_round.damage = 0
                player_round.damage += event.damage
            elif event.player.steam_id.id64() != event.target.steam_id.id64():
                if player_round.ff_damage is None:
                    player_round.ff_damage = 0
                player_round.ff_damage += event.damage

    def handle_assist(self, event):
        if not self.match or not self.round:
            return
        if VERBOSE:
            print event
        steam_id = event.player.steam_id.id64()
        if self.player_rounds.has_key(steam_id):
            if self.player_rounds[steam_id].assists is None:
                self.player_rounds[steam_id].assists = 0
            self.player_rounds[steam_id].assists += 1

    def handle_switch_team(self, event):
        if VERBOSE:
            print event
        steam_id = event.player.steam_id.id64()
        player = db.session.query(Player).filter_by(steam_id=steam_id).first()
        try:
            if event.orig_team == 'CT':
                self.cts.remove(steam_id)
            elif event.orig_team == 'TERRORIST':
                self.ts.remove(steam_id)
        except ValueError:
            pass
        if event.new_team == 'CT':
            self.cts.append(steam_id)
            if self.round:
                self.live_cts += 1
        elif event.new_team == 'TERRORIST':
            self.ts.append(steam_id)
            if self.round:
                self.live_ts += 1
        else:
            return
        if not self.match:
            return
        if steam_id not in self.team_a and steam_id not in self.team_b:
            if (event.new_team == 'TERRORIST' and (self.period % 2) == 1) \
                    or (event.new_team == 'CT' and (self.period % 2) == 0):
                self.team_a.append(steam_id)
                db.session.execute(match_players.insert().values(
                    player_id=player.id,
                    match_id=self.match.id,
                    team=CsgoMatch.TEAM_A))
            else:
                self.team_b.append(steam_id)
                db.session.execute(match_players.insert().values(
                    player_id=player.id,
                    match_id=self.match.id,
                    team=CsgoMatch.TEAM_B))
        if not self.round:
            return
        if not self.player_rounds.has_key(steam_id):
            player_round = PlayerRound()
            player_round.player_id = player.id
            self.player_rounds[player.steam_id] = player_round


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
        print "goonpugd: Listening for HL log connections on %s:%d" % (
            self.server.server_address)
        self.server.serve_forever()


def main():
    global VERBOSE
    parser = argparse.ArgumentParser(description='GoonPUG logparser')
    parser.add_argument('-p', '--port', dest='port', action='store', type=int,
                        default=27500, help='port to listen on')
    parser.add_argument('-d', '--daemon', action='store_true',
                        help='run goonpugd as a daemon')
    parser.add_argument('--pidfile', action='store', type=str,
                        help='path to the pidfile',
                        default='/tmp/goonpugd.pid')
    parser.add_argument('-s', action='store_true', dest='stdin',
                        help='read log entries from stdin instead of '
                              'listening on a network port')
    parser.add_argument('--server', action='store', dest='server_address',
                        help='server address (used with -s) in form of '
                             'IP:PORT')
    parser.add_argument('-v', action='store_true', dest='verbose',
                        help='verbose output')
    args = parser.parse_args()
    VERBOSE = args.verbose
    if args.stdin:
        if not args.server_address:
            parser.error('No server address specified')
        (host, port) = args.server_address.split(':', 1)
        port = int(port)
        log_parser = GoonPugParser((host, port))
        print "goonpugd: Reading from STDIN"
        thread = threading.Thread(target=log_parser.process_events)
        thread.start()
        while True:
            try:
                for line in sys.stdin.readlines():
                    log_parser.parse_line(line)
            except KeyboardInterrupt:
                sys.exit()
            except EOFError:
                sys.exit()
    else:
        daemon = GoonPugDaemon(args.pidfile, port=args.port)
        if not args.daemon:
            try:
                print "goonpugd: Running in foreground"
                daemon.run()
            except KeyboardInterrupt:
                daemon.server.shutdown()
                daemon.stop()
                sys.exit()
        else:
            print "goonpugd: Running in daemon mode"
            daemon.start()


if __name__ == '__main__':
    main()
