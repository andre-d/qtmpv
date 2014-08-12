from __future__ import print_function

import mpv
import threading
import os
from PyQt5.Qt import *


class VideoContainer(QWidget):
    def sizeHint(self):
        if not self.vwidth:
            return QWidget.sizeHint(self)
        return QSize(self.vwidth, self.vheight)

    def __init__(self, parent):
        QWidget.__init__(self, parent)
        self.vwidth = None
        self.vheight = None
        self.childwin = QWindow()
        self.childwidget = QWidget.createWindowContainer(self.childwin)
        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(self.childwidget)
        self.setLayout(self.layout)

class PlayListItem(QListWidgetItem):
    def __init__(self, path):
        QListWidgetItem.__init__(self)
        self.path = path
        self.setText(os.path.basename(self.path))

class PlayList(QListWidget):
    def __init__(self, mpv):
        QListView.__init__(self)
        self.mpv = mpv
        self.mpv.playlistchanged.connect(self.doplaylist)
        self.itemDoubleClicked.connect(self.clicked)

    def doplaylist(self):
        for i, item in enumerate(self.mpv.playlist):
            existingitem = self.item(i)
            if not existingitem or existingitem.path != item['filename']:
                self.insertItem(i, PlayListItem(item['filename']))
            if i == self.mpv.playlist_pos:
                self.setCurrentRow(i)

    def clicked(self, item):
        self.mpv.m.set_property('playlist-pos', self.row(item))

class MainWindow(QMainWindow):
    def novid(self):
        self.videocontainer.hide()

    def hasvid(self):
        self.videocontainer.show()
        self.setWindowTitle(self.mpv.media_title)

    def reconfig(self, width, height):
        self.videocontainer.vwidth = width
        self.videocontainer.vheight = height
        self.show()
        if not self.sized_once and width:
            self.resize(self.sizeHint())
            self.sized_once = True

    def createPlaylistDock(self):
        self.playlist = PlayList(self.mpv)
        self.playlistdock = QDockWidget()
        self.playlistdock.setWindowTitle("Playlist")
        self.playlistdock.setFeatures(QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetMovable)
        self.playlistdock.setWidget(self.playlist)

    def fullscreen(self, fullscreen):
        if fullscreen:
            self.playlistdock.hide()
            self.showFullScreen()
        elif self.isFullScreen():
            self.playlistdock.show()
            self.showNormal()

    def __init__(self, mpv):
        QMainWindow.__init__(self)
        mpv.reconfig.connect(self.reconfig)
        mpv.novid.connect(self.novid)
        self.sized_once = False
        mpv.hasvid.connect(self.hasvid)
        mpv.fullscreen.connect(self.fullscreen)
        self.mpv = mpv
        self.videocontainer = VideoContainer(self)
        self.setCentralWidget(self.videocontainer)
        self.createPlaylistDock()
        self.addDockWidget(Qt.LeftDockWidgetArea, self.playlistdock)


class MPV(QObject):
    def get_options(self, args):
        options = {}
        media = []
        for arg in args:
            if arg.startswith('--'):
                arg, _, value = arg[2:].partition('=')
                options[arg] = value or True
                continue
            media.append(arg)
        return options, media

    @property
    def media_title(self):
        try:
            return self.m.get_property('media-title')
        except mpv.MPVError:
            return None

    def init(self, args, wid):
        self.playlist = []
        self.playlist_pos = None
        self.wakeup.connect(self.handle_event)
        
        options, media = self.get_options(args)

        try:
            self.m = mpv.Context()
        except mpv.MPVError:
            print('failed creating context')
            qApp.exit(1)

        for option in options.items():
            self.m.set_option(*option)

        self.m.set_log_level('info')
        self.m.set_option('input-default-bindings')
        self.m.set_option('osc')
        self.m.set_option('wid', wid)
        
        self.m.initialize()
        
        self.m.observe_property('playlist')
        self.m.observe_property('playlist-pos')
        self.m.observe_property('fullscreen')
        
        for media in media:
            self.m.command('loadfile', media, 'append')
        
        if media:
            self.m.set_property('playlist-pos', 0)
        
        self.m.set_wakeup_callback(self.mpv_wakeup)

        return self

    def handle_event(self):
        while True:
            event = self.m.wait_event(0)
            if event.id  == mpv.Events.none:
                break
            elif event.id == mpv.Events.shutdown:
                qApp.exit()
                break
            elif event.id == mpv.Events.idle:
                self.novid.emit()
            elif event.id == mpv.Events.start_file:
                self.hasvid.emit()
            elif event.id == mpv.Events.log_message:
                print(event.data.text, end='')
            elif (event.id == mpv.Events.end_file
             or event.id == mpv.Events.video_reconfig):
                try:
                    self.reconfig.emit(
                        self.m.get_property('dwidth'),
                        self.m.get_property('dheight')
                    )
                except mpv.MPVError:
                    self.reconfig.emit(None, None)
            elif event.id == mpv.Events.property_change:
                if event.data.name == 'playlist':
                    self.playlist = event.data.data
                    self.playlistchanged.emit()
                elif event.data.name == 'playlist-pos':
                    self.playlist_pos = event.data.data
                    self.playlistchanged.emit()
                elif event.data.name == 'fullscreen':
                    self.fullscreen.emit(event.data.data or False)

    novid = pyqtSignal()
    hasvid = pyqtSignal()
    playlistchanged = pyqtSignal()
    reconfig = pyqtSignal(int, int)
    fullscreen = pyqtSignal(bool)
    wakeup = pyqtSignal()

    def mpv_wakeup(self):
        self.wakeup.emit()

class App(QApplication):
    def run(self):
        # See you on the other side
        QTimer.singleShot(0, self.init)
        self.exec_()
        self.mpv.m.set_wakeup_callback(None)

    def init(self):
        self.mpv = MPV()
        self.win = MainWindow(self.mpv)
        self.mpv.init(self.mpvargs, int(self.win.videocontainer.childwin.winId()))

    def __init__(self, args):
        QApplication.__init__(self, args)
        self.mpvargs = args[1:]
