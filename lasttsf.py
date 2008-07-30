#!/usr/bin/env python

############################################################################
# LastTSF script 
# submits metadata from TSF Jazz to Last.fm
#
# Depends on: Python 2.2, PyQt, lastfmsubmitd
############################################################################
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
############################################################################

import os
import sys
import threading
import signal
import time
from math import floor

try:
    from qt import *
except:
    os.popen( "kdialog --sorry 'PyQt (Qt bindings for Python) is required for this script.'" )
    raise

try:
    import lastfm.client
except:
    os.popen( "kdialog --sorry 'lastfmsubmitd (Last.fm bindings for Python) is required for this script.'" )

debug_prefix = "[LastTSF]"

class Notification( QCustomEvent ):
    __super_init = QCustomEvent.__init__
    def __init__( self, str ):
        self.__super_init(QCustomEvent.User + 1)
        self.string = str

class Test( QApplication ):
    """ The main application, also sets up the Qt event loop """

    def saveState( self, sessionmanager ):
        # script is started by amarok, not by KDE's session manager
        sessionmanager.setRestartHint(QSessionManager.RestartNever)

    def __init__( self, args ):
        QApplication.__init__( self, args )
        debug( "Started." )
        self.track = None
        self.oldtrack = None
	self.radioMonitor = None
	self.quitting = False
	self.quitradio = False
	self.duration = time.time()
        self.cli = lastfm.client.Client('LastTSF')
        self.cli.open_log()
	self.checkTSF()

        # Start separate thread for reading data from stdin
        self.stdinReader = threading.Thread( target = self.readStdin )
        self.stdinReader.start()

############################################################################
# Stdin-Reader Thread
############################################################################

    def readStdin( self ):
        """ Reads incoming notifications from stdin """

        while not self.quitting:
            # Read data from stdin. Will block until data arrives.
            line = sys.stdin.readline()

            if line:
                qApp.postEvent( self, Notification(line) )
            else:
                break


############################################################################
# Notification Handling
############################################################################

    def customEvent( self, notification ):
        """ Handles notifications """

        string = QString(notification.string)
        debug( "Received notification: " + str( string ) )

        if string.contains( "configure" ):
            self.configure()

        if string.contains( "engineStateChange: pause" ):
            self.engineStatePause()

        if string.contains( "engineStateChange: empty" ):
            self.engineStateEmpty()

        if string.contains( "trackChange" ):
            self.trackChange()

# Notification callbacks. Implement these functions to react to specific notification
# events from Amarok:

    def configure( self ):
        debug( "configuration" )
        stdin, stdout = os.popen2("dcop amarok playlist popupMessage 'This script does not require any configuration.'")

    def engineStatePause( self ):
        """ Called when Engine state changes to Pause """
        self.radiokill()
	self.oldtrack = None

    def engineStateEmpty( self ):
        """ Called when Engine state changes to Empty """
        self.radiokill()
	self.oldtrack = None

    def trackChange( self ):
        """ Called when a new track starts """
	self.checkTSF()

############################################################################

    def radiokill( self ):
        """ Try to kill a running radio-monitor thread """
        self.quitradio = True

    def radio( self ):
        """ Connect to TSF Jazz and submit track information to Last.fm """
	while not self.quitting and not self.quitradio:
            debug( "Downloading track information..." )
            stdin, stdout = os.popen2("wget -O - --quiet http://www.tsfjazz.com/getSongInformations.php")
	    self.track = stdout.read().strip()
	    stdin.close()
	    stdout.close()
	    debug( "Done: " + self.track )
            if self.track != self.oldtrack and self.oldtrack != None:
                # Get track and artist name
                pos = self.oldtrack.find("|")
		if pos == -1:
		    debug( "WARNING: Character '|' not found in track name!" )
		    return
		artist, title = self.oldtrack[:pos].title(), self.oldtrack[pos+1:].title()

		# Sanitize artist name and title
		pos=artist.find("   ")
		if pos != -1:
                    artist = artist[:pos]
		artist = separate( artist )

                artist = sanitize( artist )
		title = sanitize( title )

		# Calculate track length
		oldduration = self.duration
		self.duration = time.time()
		length = int( self.duration - oldduration )

		# Submit
                debug( "Submitting track " + title + " by artist " + artist + ", length: " + str( length ) + " s"  )
		song = {'artist': artist, \
		        'title':  title, \
			'length': length, \
			'time':   time.gmtime()}
	        self.cli.log.info('Played song: %s' % lastfm.repr(song))
                self.cli.submit(song)

		# Update the old track
                self.oldtrack = self.track

            time.sleep(30)

    def checkTSF( self ):
        stdin, stdout = os.popen2("dcop amarok player nowPlaying")
	self.nowplaying = stdout.read().strip()
	stdin.close()
	stdout.close()
        if self.nowplaying != "TSF Jazz":
            self.radiokill()
	elif self.radioMonitor == None or not self.radioMonitor.isAlive():
            self.quitradio = False
            self.radioMonitor = threading.Thread( target = self.radio )
            self.radioMonitor.start()

############################################################################

def sanitize( string ):
    out = sanitize_ampsand( string )
    return out

def sanitize_ampsand( string ):
    out = string
    pos = out.lower().find("&amp;")
    while pos != -1:
        out = out[:pos] + "&" + out[pos+5:]
    return out

def separate( string ):
    pos = string.find("/")
    if pos == -1:
        return string
    elif string[pos+1:].find("/") == -1:
        return string[:pos] + " and " + string[pos+1:]
    else:
        return string[:pos] + ", " + separate( string[pos+1:] )

def debug( message ):
    """ Prints debug message to log file """
    log.write( debug_prefix + ' ' + message + '\n' )
    log.flush()

def main( ):
    global app
    app = Test( sys.argv )

    app.exec_loop()

def onStop(signum, stackframe):
    """ Called when script is stopped by user """
    global app, log
    app.quitting = True
    log.close()
    sys.exit()

global log

if __name__ == "__main__":
    log = open( 'lasttsf.log', 'w' )
    mainapp = threading.Thread(target=main)
    mainapp.start()
    signal.signal(signal.SIGTERM, onStop)
    # necessary for signal catching
    while 1: time.sleep(120)

