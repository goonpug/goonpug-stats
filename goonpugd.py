#!/usr/bin/env python
"""GoonPUG-stats log handling daemon"""

from __future__ import absolute_import, division
import os
import sys
import argparse
import threading
import SocketServer
import srcds.events
from Queue import Queue
from daemon import Daemon

from goonpug import db


class GoonPugParser(object):

    """GoonPUG log parser class"""

    def __init__(self):
        self.events = Queue()
        self.events_types = []
        self.skip_unknowns = skip_unknowns
        self.add_event_types(srcds.events.generic.STANDARD_EVENTS)
        self.add_event_types(srcds.csgo.CSGO_EVENTS)

    def add_event_types(self, event_types=[]):
        """Add event types"""
        for cls in event_types:
            regex = re.compile(cls.regex)
            self.events_types.append((regex, cls))

    def parse_line(self, line):
        """Parse a single log line"""
        line = line.strip()
        for (regex, cls) in self.events_types:
            match = regex.match(line)
            if match:
                event = cls.from_re_match(match)
                self.events.put(event)
                return
        if not self.skip_unknowns:
            raise UnknownEventError('Could not parse event: %s' % line)

    def read(self, filename):
        """Read in a log file"""
        fd = open(filename)
        for line in fd.readlines():
            self.parse_line(line)
        fd.close()


class GoonPugLogHandler(SocketServer.BaseRequestHandler):

    def handle(self):
        data = self.request[0].strip()
        # Strip the 4-byte header and the first 'R' character
        #
        # There is no documentation for this but I am guessing the 'R' stands
        # for 'Remote'? Either way normal log entires are supposed to start
        # with 'L', but the UDP packets start with 'RL'
        data = data[5:]
        socket = self.request[1]
        print "{} wrote:".format(self.client_address[0])
        print data[5:]


class GoonPugDaemon(Daemon):

    def __init__(self, pidfile, port=27500, stdout=sys.stdout, stderr=sys.stderr):
        super(GoonPugDaemon, self).__init__(pidfile, stdout=stdout, stderr=stderr)
        self.port = port

    def run(self):
        server = SocketServer.UDPServer(('0.0.0.0', self.port),
                                        GoonPugLogHandler)
        server.serve_forever()


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
            sys.exit()
    else:
        daemon.start()


if __name__ == '__main__':
    main()
