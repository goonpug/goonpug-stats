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
from srcds.objects import BasePlayer
from Queue import Queue, Empty
from daemon import Daemon

from goonpug import db
from goonpug.models import CsgoMatch, Round, Player, PlayerRound, Frag, \
        match_players, Server


VERBOSE = False


class GoonPugPlayer(BasePlayer):
    pass


class GoonPugActionEvent(generic_events.BaseEvent):

    """GoonPUG triggered action event"""

    regex = ''.join([
        generic_events.BaseEvent.regex,
        r'GoonPUG triggered "(?P<action>.*?)"',
    ])

    def __init__(self, timestamp, action):
        super(GoonPugActionEvent, self).__init__(timestamp)
        self.action = action

    def __unicode__(self):
        msg = u'GoonPUG triggered "%s"' % (self.action)
        return ' '.join([super(GoonPugActionEvent, self).__unicode__(), msg])


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
            GoonPugActionEvent: self.handle_goonpug_action,
        }
        self._compile_regexes()
        self.server = Server.get_or_create(server_address[0], server_address[1])
        db.session.commit()
        self.match = None
        self.round = None
        self.players = {}

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
                event = self.eventq.get(True, 5)
                handler = self.event_handlers[type(event)]
                handler(event)
                self.eventq.task_done()
            except Empty:
                pass

    def _abandon_match(self):
        db.session.rollback()
        if self.match:
            match = db.session.query(CsgoMatch).get(self.match.id)
            if match:
                db.session.delete(match)
                db.session.expunge(self.match)
                db.session.commit()
        self.match = None
        self.round = None

    def _start_match(self, timestamp):
        # If this match exists already, delete the existing one
        match = CsgoMatch.query.filter_by(server_id=self.server.id,
            start_time=timestamp).first()
        if match:
            db.session.delete(match)
            db.session.commit()
        self.match = CsgoMatch()
        # we only support pugs right now
        self.match.type = CsgoMatch.TYPE_PUG
        self.match.map = self.mapname
        self.match.server_id = self.server.id
        self.match.start_time = timestamp
        db.session.add(self.match)
        db.session.commit()
        self.team_a = set()
        self.team_b = set()
        for player in self.players.values():
            if player.team == 'TERRORIST':
                self.team_a.add(player.steam_id.id64())
            elif player.team == 'CT':
                self.team_b.add(player.steam_id.id64())
        self.period = 1
        self.t_score = 0
        self.ct_score = 0
        self.round = None

    def _end_match(self, event):
        self._commit_round()
        self.match.end_time = event.timestamp
        db.session.commit()
        for steam_id in self.team_a:
            player = Player.query.filter_by(steam_id=steam_id).first()
            db.session.execute(match_players.insert().values(
                player_id=player.id,
                match_id=self.match.id,
                team=CsgoMatch.TEAM_A,
                ))
        for steam_id in self.team_b:
            player = Player.query.filter_by(steam_id=steam_id).first()
            db.session.execute(match_players.insert().values(
                player_id=player.id,
                match_id=self.match.id,
                team=CsgoMatch.TEAM_A,
                ))
        self.team_a = None
        self.team_b = None
        self.match = None
        self.round = None

    def _commit_round(self):
        db.session.add(self.round)
        db.session.commit()
        for player in self.players.values():
            steam_id = player.steam_id.id64()
            db_player = Player.query.filter_by(steam_id=steam_id).first()
            if steam_id in self.team_a or steam_id in self.team_b:
                player_round = PlayerRound()
                player_round.player_id = db_player.id
                player_round.round_id = self.round.id
                player_round.dead = not player.alive
                player_round.assists = player.assists
                player_round.damage = player.damage
                player_round.bomb_planted = player.bomb_planted
                player_round.bomb_defused = player.bomb_defused
                player_round.won_1v = player.won_1v
                player_round.dropped = player.dropped
                player_round.rws = player.rws
                if steam_id in self.team_a:
                    player_round.team = CsgoMatch.TEAM_A
                elif steam_id in self.team_b:
                    player_round.team = CsgoMatch.TEAM_B
                db.session.add(player_round)
        for frag in self.round_frags:
            frag.round_id = self.round.id
            db.session.add(frag)
        db.session.commit()
        self.round = None
        self.round_frags = []

    def _start_round(self):
        if self.round:
            self._commit_round()
        for player in self.players.values():
            # count drops and spectators as alive since we don't want to record
            # them as dead at the end of a round
            player.alive = True
            player.health = 100
            player.damage = 0
            player.assists = 0
            player.rws = 0.0
            player.bomb_defused = False
            player.bomb_planted = False
            player.won_1v = 0
        self.round = Round()
        self.round.match_id = self.match.id
        self.round.period = self.period
        self.round_frags = []

    def _end_round(self, event):
        rounds_played = self.t_score + self.ct_score
        if rounds_played == 0:
            self.period = 1
        elif rounds_played < 30 and (rounds_played % 15) == 0:
            self.period += 1
        elif rounds_played >= 30 and (rounds_played % 5) == 0:
            self.period += 1

    def _sfui_notice(self, winning_team, defused=False, exploded=False):
        if winning_team == 'TERRORIST':
            if self.period % 2 == 0:
                self.round.winning_team = CsgoMatch.TEAM_A
            else:
                self.round.winning_team = CsgoMatch.TEAM_B
        else:
            if self.period % 2 == 0:
                self.round.winning_team = CsgoMatch.TEAM_B
            else:
                self.round.winning_team = CsgoMatch.TEAM_A
        team_damage = 0
        team_players = []
        for player in self.players.values():
            if self.round.winning_team == CsgoMatch.TEAM_A \
                    and player.steam_id.id64() in self.team_a:
                # player won
                team_damage += player.damage
                team_players.append(player)
            elif self.round.winning_team == CsgoMatch.TEAM_B \
                    and player.steam_id.id64() in self.team_b:
                # player won
                team_damage += player.damage
                team_players.append(player)
            if (self.round.winning_team == CsgoMatch.TEAM_A
                    and player.steam_id.id64() not in self.team_a) \
                    or (self.round.winning_team == CsgoMatch.TEAM_B
                    and player.steam_id.id64() not in self.team_b):
                # player lost
                player.won_1v = 0
                player.rws = 0.0
        if defused or exploded:
            multi = 70.0
        else:
            multi = 100.0
        for player in team_players:
            try:
                player.rws = multi * (player.damage / team_damage)
            except ZeroDivisionError:
                player.rws = 0.0
            if defused and player.bomb_defused:
                player.rws += 30.0
            if exploded and player.bomb_planted:
                player.rws += 30.0

    def handle_log_file(self, event):
        self.players = {}
        if event.closed and self.match:
            # something bad happened, like a server restart mid match
            self._abandon_match()

    def handle_change_map(self, event):
        self.players = {}
        if VERBOSE:
            print event
        if event.started:
            self.mapname = event.mapname

    def handle_enter_game(self, event):
        if VERBOSE:
            print event
        steam_id = event.player.steam_id.id64()
        Player.get_or_create(steam_id, nickname=event.player.name)
        db.session.commit()

    def _check_1v(self):
        if not self.round:
            return
        live_ts = []
        live_cts = []
        for player in self.players.values():
            if player.team == 'TERRORIST' and player.alive and not player.dropped:
                live_ts.append(player)
            elif player.team == 'CT' and player.alive and not player.dropped:
                live_cts.append(player)
        if len(live_ts) == 1 and live_ts[0].won_1v == 0:
            live_ts[0].won_1v = len(live_cts)
        elif len(live_cts) == 1 and live_cts[0].won_1v == 0:
            live_cts[0].won_1v = len(live_ts)

    def handle_suicide(self, event):
        if not self.round:
            return
        if VERBOSE:
            print event
        steam_id = event.player.steam_id.id64()
        self.players[steam_id].alive = False
        player = Player.query.filter_by(steam_id=steam_id).first()
        frag = Frag()
        frag.fragger = player.id
        frag.victim = player.id
        frag.weapon = event.weapon
        frag.headshot = False
        frag.tk = True
        self.round_frags.append(frag)
        self._check_1v()

    def handle_disconnection(self, event):
        if VERBOSE:
            print event

    def handle_kick(self, event):
        # the leaving part should be taken care of by handle_disconnection
        pass

    def handle_player_action(self, event):
        if not self.match:
            return
        if VERBOSE:
            print event
        steam_id = event.player.steam_id.id64()
        if event.action == "Planted_The_Bomb":
            self.players[steam_id].bomb_planted = True
        elif event.action == "Defused_The_Bomb":
            self.players[steam_id].bomb_defused = True

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
            self._abandon_match()
        elif event.action == 'Round_Start':
            if self.match:
                self._start_round()
        elif event.action == 'Round_End':
            if self.match:
                self._end_round(event)

    def handle_goonpug_action(self, event):
        if VERBOSE:
            print event
        if event.action == 'Start_Match':
            self._start_match(event.timestamp)
        elif event.action == 'End_Match':
            self._end_match(event)
        elif event.action == 'Abandon_Match':
            self._abandon_match()
        elif event.action == 'Start_Warmup' and self.match:
            self._abandon_match()

    def handle_round_end_team(self, event):
        if VERBOSE:
            print event
        if event.team == 'CT':
            self.ct_score = event.score
        elif event.team == 'TERRORIST':
            self.t_score = event.score

    def handle_kill(self, event):
        if not self.round:
            return
        if VERBOSE:
            print event
        steam_id = event.player.steam_id.id64()
        target_id = event.target.steam_id.id64()
        self.players[target_id].alive = False
        fragger = Player.query.filter_by(steam_id=steam_id).first()
        victim = Player.query.filter_by(steam_id=target_id).first()
        frag = Frag()
        frag.fragger = fragger.id
        frag.victim = victim.id
        frag.weapon = event.weapon
        frag.headshot = event.headshot
        if event.player.team == event.target.team:
            frag.tk = True
        self.round_frags.append(frag)
        self._check_1v()

    def handle_attack(self, event):
        if not self.round:
            return
        if VERBOSE:
            print event
        steam_id = event.player.steam_id.id64()
        target_id = event.target.steam_id.id64()
        # RWS doesn't care about ff damage
        if event.player.team != event.target.team:
            if event.health > 0:
                # target still has health remaining
                self.players[steam_id].damage += event.damage
            else:
                # target is dead, we have to adjust for overkill damage
                self.players[steam_id].damage += self.players[target_id].health
        self.players[target_id].health = event.health
        # don't set player alive flag here, it will be set in suicide or kill
        # handling

    def handle_assist(self, event):
        if not self.round:
            return
        if VERBOSE:
            print event
        steam_id = event.player.steam_id.id64()
        self.players[steam_id].assists += 1

    def handle_switch_team(self, event):
        if VERBOSE:
            print event
        steam_id = event.player.steam_id.id64()
        player = db.session.query(Player).filter_by(steam_id=steam_id).first()
        if not self.players.has_key(steam_id):
            self.players[steam_id] = GoonPugPlayer(event.player.name, event.player.uid, event.player.steam_id)
        self.players[steam_id].team = event.new_team
        self.players[steam_id].dropped = False
        if self.round:
            self.players[steam_id].alive = True
            self.players[steam_id].health = 100
            self.players[steam_id].damage = 0
            self.players[steam_id].assists = 0
            self.players[steam_id].rws = 0.0
            self.players[steam_id].bomb_defused = False
            self.players[steam_id].bomb_planted = False
            self.players[steam_id].won_1v = 0
        if self.match:
            if event.new_team == 'Unassigned' \
                    and event.orig_team in ['CT', 'TERRORIST']:
                self.players[steam_id].dropped = True
                self.players[steam_id].alive = False
                self._check_1v()
            else:
                if (self.period % 2) == 1:
                    if event.new_team == 'TERRORIST':
                        self.team_a.add(steam_id)
                        self.team_b.discard(steam_id)
                    elif event.new_team == 'CT':
                        self.team_b.add(steam_id)
                        self.team_a.discard(steam_id)
                else:
                    if event.new_team == 'TERRORIST':
                        self.team_b.add(steam_id)
                        self.team_a.discard(steam_id)
                    elif event.new_team == 'CT':
                        self.team_a.add(steam_id)
                        self.team_b.discard(steam_id)
        else:
            if event.new_team == 'Unassigned':
                del self.players[steam_id]


log_parsers = {}


class GoonPugLogHandler(SocketServer.DatagramRequestHandler):

    def handle(self):
        data = self.request[0]
        # Strip the 4-byte header and the first 'R' character
        #
        # There is no documentation for this but I am guessing the 'R' stands
        # for 'Remote'? Either way normal log entires are supposed to start
        # with 'L', but the UDP packets start with 'RL'
        data = data[5:].strip()
        socket = self.request[1]
        if not log_parsers.has_key(self.client_address):
            parser = GoonPugParser(self.client_address)
            thread = threading.Thread(target=parser.process_events)
            log_parsers[self.client_address] = (thread, parser)
            thread.daemon = True
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
        thread.daemon = True
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
