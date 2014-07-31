#!/usr/bin/env python
import sys
import signal
import mpv

from qtapp import App

signal.signal(signal.SIGINT, signal.SIG_DFL)

def main(args):
    return App(args).run()

if __name__ == '__main__':
    exit(main(sys.argv) or 0)
