#!/usr/bin/env python

##############################################################################
## Copyright (c) 2020 by Gambit Communications, Inc.
## All Rights Reserved
## This is released under the GNU GPL 3.0
## https://www.gnu.org/licenses/gpl-3.0.en.html
##############################################################################

from __future__ import print_function

import os 
import getopt
import sys
import socket
import time
import logging
import threading
import binascii
import re
import ssl

# debug.setLogger(debug.Debug('all'))

formatting = '%(levelname)s %(asctime)s (%(filename)s-%(lineno)d) - %(message)s'
logging.basicConfig(level=logging.DEBUG, format=formatting, )


import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')

try:
	from gi.repository import Gtk
	from gi.repository import Gdk
	from gi.repository import GObject
	from gi.repository import Pango as pango
except:
	logging.error ("require Gtk")
	sys.exit(1)

import paho.mqtt.client as mqtt

import json


###########################################################################


###########################################################################
debug = False
if debug:
  from colorlog import ColoredFormatter
  def setup_logger():
    """Return a logger with a default ColoredFormatter."""
    formatter = ColoredFormatter(
        "(%(threadName)-9s) %(log_color)s%(levelname)-8s%(reset)s %(message_log_color)s%(message)s",
        datefmt=None,
        reset=True,
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red',
        },
        secondary_log_colors={
            'message': {
                'ERROR': 'red',
                'CRITICAL': 'red',
                'DEBUG': 'yellow'
            }
        },
        style='%'
    )

    logger = logging.getLogger(__name__)
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    return logger

  # Create a player
  logger = setup_logger()

  from functools import wraps
  def trace(func):
    """Tracing wrapper to log when function enter/exit happens.
    :param func: Function to wrap
    :type func: callable
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger.debug('Start {!r}'. format(func.__name__))
        result = func(*args, **kwargs)
        logger.debug('End {!r}'. format(func.__name__))
        return result
    return wrapper

else:

  from functools import wraps
  def trace(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        return result
    return wrapper

###########################################################################
class _IdleObject(GObject.GObject):
    """
    Override GObject.GObject to always emit signals in the main thread
    by emmitting on an idle handler
    """

    @trace
    def __init__(self):
        GObject.GObject.__init__(self)

    @trace
    def emit(self, *args):
        GObject.idle_add(GObject.GObject.emit, self, *args)


###########################################################################
class _UpdateThread(threading.Thread, _IdleObject):
	"""
	Cancellable thread which uses gobject signals to return information
	to the GUI.
	"""
	__gsignals__ = {
		"completed": (
		    GObject.SignalFlags.RUN_LAST, None, []),
		"progress": (
		    GObject.SignalFlags.RUN_LAST, None, [
		        GObject.TYPE_FLOAT])  # percent complete
	}

	@trace
	def __init__(self, parent):
		threading.Thread.__init__(self, target=self.update_main, name="Update Thread")
		_IdleObject.__init__(self)
		self.cancelled = False

	# main thread for the update thread
	# this thread periodically checks for any changes
	# and initiates updates
	@trace
	def update_main(self):
		while True:
			# wake up every second for response
			time.sleep (0.99999)

			if main.is_stopped:
				break

			if main.is_paused:
				continue

			# but only do the work every N seconds
#			count += 1
#			if count < self.poller.poll_interval:
#				continue
#			count = 0

			logging.debug ("update_cycle start")
			self.update_cycle()
			logging.debug ("update_cycle completed")
			self.emit("completed")

		logging.debug ("done update_main")

	# run a poll cycle
	@trace
	def update_cycle(self):
		# logging.debug ("done update_cycle " )
		return


###########################################################################
# key / value statistics
class Key():
	def __init__(self, number, key, value, time, rowref):
		self.key = key
		self.number = number
		self.count = 1;		# seen at least once
		self.triggers = 0;	# not triggered
		self.value = value
		self.time = time
		self.rowref = rowref

	def dump(self, outfile):
		print ("%6d %20s %6d %6d %s" % (self.number, self.key, self.count, self.value, self.time), file=outfile)

###########################################################################
# MQTT subscriber code
# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc, properties=""):
	logging.debug ("MQTT client connected with result code "+str(rc)+" "+str(properties))

	# Subscribing in on_connect() means that if we lose the connection and
	# reconnect then subscriptions will be renewed.
	client.subscribe(main.topic, main.qos)

# The callback for when a PUBLISH message is received from the server.
# updates metrics for later GUI display
def on_message(client, userdata, msg):
    if main.clear_stats:
        main.messages_received = 0
        main.num_keys = 0
        main.topics = dict()
        main.changed = dict()	# a small subset of entries that is changed
        main.last_changed = dict() # the changed in the last iteration
                                # GUI needs this to 0 out some values
        main.clear_stats = False
        main.clear_store = True

    numbytes = len (msg.payload)
    now = time.time()

#    if main.verbose:
#        logging.debug (msg.topic + ' ' + str(numbytes) + ' ' + str(msg.payload))

    main.messages_received += 1

    # parse the JSON, and look at SN and temperature
    try:
        jsondict = json.loads(bytes(msg.payload))
    except Exception as e:
#        logging.debug ("ERROR: cannot load json")
#        print (str(e))
#        print (str(msg.payload))
#        raise
        main.messages_ignored += 1
        return

#    logging.debug ("jsondict " + str(jsondict))

    # get the (unique) serial key value; ignore if not there
    strarray = main.key.split ('.')
    tmpdict = jsondict
    for idx in strarray: 
        try:
            retval = tmpdict[idx]
        except Exception as e:
            print ('ERROR cannot find JSON field ' + idx)
            print (str(e))
            main.messages_ignored += 1
            return
        tmpdict = retval
    key = tmpdict

#    logging.debug ("sensor " + str(key))

    # check temperature value and if higher than threshold, alert
    strarray = main.field.split ('.')
    tmpdict = jsondict
    for idx in strarray: 
        try:
            retval = tmpdict[idx]
        except Exception as e:
#            print ('ERROR cannot find JSON field ' + idx)
#            print (str(e))
            main.messages_ignored += 1
            return
        tmpdict = retval

    try:
        tempval = int(tmpdict)
    except Exception as e:
            print ('ERROR sensor ' + str(key) + ' not an integer value ' + tmpdict)
            print (str(e))
            main.messages_ignored += 1
            return

    # if not already there, add to set of serial numbers detected
    try:
        if key not in main.keys:
#            logging.debug ("new sensor " + key)
            main.num_keys += 1
            newentry = Key (main.num_keys, key, tempval, now, None)
            main.keys[key] = newentry
            thisentry = newentry
        else:
            thisentry = main.keys[key]
            thisentry.count += 1
            thisentry.value = tempval
            thisentry.time = now
    except Exception as e:
        print (str(e))

    if main.verbose:
        logging.debug ("received key: " + str(key) + " " + main.field + ": " + str(tempval))

    if thisentry.number not in main.changed:
        main.changed[thisentry.number] = key

    # we need to do this here because it could happen multiple times per
    # update interval
    if tempval > main.thresh:
        logging.debug ("Sensor " + key + ": " + main.field + " "  + str(tempval) + " > " + str(main.thresh))
        main.total_triggered += 1
        thisentry.triggers += 1
        if key not in main.triggered_set:
            main.triggered_set.add(key)

    return

    # UWE: TODO move to completed_cb

    timestamp = time.ctime (time.time())
    if is_added:
        number = len (main.keys)
        rowref = main.trigstore.append(
                    [number,
                    key,
                    tempval,
                    timestamp,
                    color
                    ])
        main.keys[key] = rowref
    else:
        # update existing entry
        rowref = main.keys[key]
        main.trigstore.set (rowref, 2, tempval, 3, timestamp, 4, color)


# reconnect and re-subscribe
def on_disconnect(client, userdata, rc):

    if rc != 0:
    	logging.error ("unexpected disconnect: " + str(rc))

    # since we specified reconnect_delay_set, it will automatically reconnect
    # could keep track of re-connects

def subscriber_client():
	client = mqtt.Client(main.clientid, protocol=main.protocol)
	client.on_connect = on_connect
	client.on_message = on_message
	client.on_disconnect = on_disconnect
	client.reconnect_delay_set(min_delay=10, max_delay=60)

	if (main.user != None):
		logging.debug ("user " + main.user)
		client.username_pw_set(main.user, main.pwd)

	if (main.is_tls):
#		logging.debug ("cafile " + main.cafile)
		client.tls_set(ca_certs=main.cafile, certfile=main.certfile, keyfile=main.keyfile, tls_version=ssl.PROTOCOL_SSLv23, cert_reqs=main.required)
		client.tls_insecure_set(True)

	logging.debug ("connecting to " + main.host_ip + ":" + str(main.port_num))

	client.connect_async(main.host_ip, main.port_num, 60)
	client.loop_start()


###########################################################################
class MyApp:
	def __init__(self):
		self.host_ip = None
		self.port_num = None
		self.verbose = False
		self.key = 'sn'
		self.field = 'data.temp.value'
		self.thresh = 70000
		self.clientid = ""
		self.user = None
		self.pwd = None
		self.topic = 'BCDS/#'
		self.qos = 0
		self.is_tls = False
		self.cafile = ""
		self.certfile = None
		self.keyfile = None
		self.required = ssl.CERT_NONE
		self.protocol = mqtt.MQTTv311

		self.is_stopped = False
		self.is_paused = False

		self.messages_received = 0
		self.messages_ignored = 0
		self.last_received = 0
		self.last_now = 0
		self.keys = dict()
		self.num_keys = 0
		self.triggered_set = set()
		self.total_triggered = 0
		self.changed = dict()
		self.last_changed = dict()

		self.clear_stats = False

		self.excluded = 0
		self.shown = dict()		# topic numbers shown
		self.matchprog = None		# regular expression for match

	def usage(self):
		print ("Usage: monitor-thresh.py")
		print ("\t[-h|--host host]        broker to connect to; default localhost")
		print ("\t[-p|--port port]        port to connect to; default port 1883")
		print ("\t[-S|--serial field]     serial key field in JSON, default sn")
		print ("\t[-F|--field field]      value field in JSON, default data.temp.value")
		print ("\t[-V|--thresh number]    value threshold; default 70000")
		print ("\t[-v|--verbose]     verbose output")
		print ("\t[-i|--clientid]    clientid (eg. for AWS)")
		print ("\t[-u|--user user]   username")
		print ("\t[-P|--pass pwd]    password")
		print ("\t[-t|--topic topic] topic; default BCDS/#")
		print ("\t[-q|--qos qos]     QoS; default 0")
		print ("\t[-T|--tls]         use TLS")
		print ("\t[-c|--cafile]      certificate authority file for TLS")
		print ("\t[-C|--certfile]    client certificate file for TLS")
		print ("\t[-K|--keyfile]     client private key file for TLS")
		print ("\t[-R|--required NONE|OPTIONAL|REQUIRED] certificate required")
		print ("\t[-M|--MQTT MQTTv31|MQTTv311|MQTTv5] MQTT protocol version")
		return

	def start(self):
		self.command_line()

		self.load_styles()

		self.show_gui()
		# from now on GUI is expected to be up

		subscriber_client ()

		self.update_thread = _UpdateThread(self)
		self.update_thread.connect("completed", self.completed_cb)
		self.update_thread.start()

		Gtk.main()

	###############################
	def command_line(self):
		try:
			opts, args = getopt.getopt(sys.argv[1:], "h:p:S:F:V:vi:u:P:t:q:Tc:C:K:R:M:", ["host=", "port=", "serial=", "field=", "thresh=", "verbose", "id=", "user=", "pass=", "topic=", "qos=", "tls", "cafile=", "certfile=", "keyfile=", "required=", "MQTT="])
		except getopt.GetoptError as err:
			# print help information and exit:
			logging.error (str(err)) # will print something like "option -a not recognized"
			self.usage()
			sys.exit(1)

		for o, a in opts:
#			logging.debug ("opt " + o)
			if o in ("-v", "--verbose"):
			    self.verbose = True
			elif o in ("-h", "--host"):
				self.host_ip = a
			elif o in ("-p", "--port"):
				self.port_num = int(a)
			elif o in ("-S", "--serial"):
				self.key = a
			elif o in ("-F", "--field"):
				self.field = a
			elif o in ("-V", "--thresh"):
				self.thresh = int(a)
			elif o in ("-i", "--id"):
				self.clientid = a
			elif o in ("-u", "--user"):
				self.user = a
			elif o in ("-P", "--pass"):
				self.pwd = a
			elif o in ("-t", "--topic"):
				self.topic = a
			elif o in ("-q", "--qos"):
				self.qos = int(a)
			elif o in ("-T", "--tls"):
				self.is_tls = True
			elif o in ("-c", "--cafile"):
				self.cafile = a
			elif o in ("-C", "--certfile"):
				self.certfile = a
			elif o in ("-K", "--keyfile"):
				self.keyfile = a
			elif o in ("-R", "--required"):
				if a == "NONE":
					self.required = ssl.CERT_NONE
				elif a == "OPTIONAL":
					self.required = ssl.CERT_OPTIONAL
				elif a == "REQUIRED":
					self.required = ssl.CERT_REQUIRED
				else:
					assert False, "needs to be one of NONE, OPTIONAL, REQUIRED"
			elif o in ("-M", "--MQTT"):
				if a == "MQTTv31":
					self.protocol = mqtt.MQTTv31
				elif a == "MQTTv311":
					self.protocol = mqtt.MQTTv311
				elif a == "MQTTv5":
					self.protocol = mqtt.MQTTv5
				else:
					assert False, "needs to be one of MQTTv31, MQTTv311, MQTTv5"
			else:
			    assert False, "unhandled option"

		if self.host_ip == None:
			self.host_ip = "127.0.0.1"

		if self.port_num == None:
			self.port_num = 1883

	###############################
	def load_styles(self):
		# CSS styles for GTK objects
		style_provider = Gtk.CssProvider()
		dir_path = os.path.dirname(os.path.realpath(__file__))
		css_path = dir_path+"/monitor-thresh.css"
		try:
			css = open(css_path, 'rb') # rb needed for python 3 support
		except:
			logging.warning ("no CSS file " + css_path + ", ignoring...")
			return
		css_data = css.read()
		css.close()

		style_provider.load_from_data(css_data)

		Gtk.StyleContext.add_provider_for_screen(
		    Gdk.Screen.get_default(),
		    style_provider,     
		    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
		)

	###############################
	def show_gui(self):
		self.builder = Gtk.Builder()
		dir_path = os.path.dirname(os.path.realpath(__file__))
		glade_path = dir_path+"/monitor-thresh.glade"
		self.builder.add_from_file(glade_path)
		self.builder.connect_signals(Handler())

		self.window = self.builder.get_object("mainWindow")

		# dialogs
		# Help->About
		self.aboutdialog = self.builder.get_object("aboutdialog1")

		# File->New

		self.errordialog = self.builder.get_object("errordialog")

		# status bar
		self.statusbar = self.builder.get_object("statusmessage")
		self.context_id = self.statusbar.get_context_id("status")
		self.clients = self.builder.get_object("clients")
		self.clients_context = self.statusbar.get_context_id("clients")
		self.freevm = self.builder.get_object("freevm")
		self.freevm_context = self.statusbar.get_context_id("freevm")
		self.activity_meter = self.builder.get_object("activitymeter")

		# the first titlelabel
		self.titlelabel = self.builder.get_object("titlelabel")
		self.titlelabel.set_text("MQTT Subscriber demo")

		self.infolabel1 = self.builder.get_object("infolabel1")
		self.infolabel1.set_text(
                'MQTT Broker:  ' + self.host_ip + '          Topic:  "' + self.topic + '"      Started:  ' + time.ctime (time.time()) +
                '\nMonitoring sensors with Key:  "' + main.key + '"      Value:  "' + main.field + '"       Threshold:  ' + str(main.thresh)
                )

		self.infolabel2 = self.builder.get_object("infolabel2")
		self.infolabel2.set_text("")

		self.infolabel3 = self.builder.get_object("infolabel3")
		self.infolabel3.set_text("")

		self.infolabel4 = self.builder.get_object("infolabel4")
		self.infolabel4.set_text("")

		self.infolabel5 = self.builder.get_object("infolabel5")
		self.infolabel5.set_text("")

		self.infolabel6 = self.builder.get_object("infolabel6")
		self.infolabel6.set_text("")

		self.infolabel7 = self.builder.get_object("infolabel7")
		self.infolabel7.set_text("")

		# the liststore containing the agents
		self.trigstore = self.builder.get_object("trigstore")

		self.treefilter = self.builder.get_object("treemodelfilter1")
		self.treefilter.set_visible_func(self.filter_func, data=None)

                # the types of cells
		cell = Gtk.CellRendererText()

		numcell = Gtk.CellRendererText(xalign=1.0)
		numcell.set_property('ellipsize', pango.EllipsizeMode.END)

		keycell = Gtk.CellRendererText()
		keycell.set_property('ellipsize', pango.EllipsizeMode.END)

                # the columns
		treeview = self.builder.get_object("treeview1")
		self.treeview = treeview
		tvcolumn = Gtk.TreeViewColumn('Number')
		treeview.append_column(tvcolumn)
		tvcolumn.pack_start(numcell, True)
		tvcolumn.add_attribute(numcell, 'text', 0)
		tvcolumn.set_sort_column_id(0)
		tvcolumn.set_resizable(True)

		tvcolumn = Gtk.TreeViewColumn('Key                 ')
		treeview.append_column(tvcolumn)
		tvcolumn.pack_start(keycell, True)
		tvcolumn.add_attribute(keycell, 'text', 1)
		tvcolumn.set_sort_column_id(1)
		tvcolumn.set_resizable(True)
		#tvcolumn.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
		#tvcolumn.set_min_width(20)
		#tvcolumn.set_fixed_width(80)
		#tvcolumn.set_expand(True)

		tvcolumn = Gtk.TreeViewColumn('Value')
		treeview.append_column(tvcolumn)
		tvcolumn.pack_start(cell, True)
		tvcolumn.add_attribute(cell, 'text', 2)
		tvcolumn.add_attribute(cell, "foreground", 6)
		tvcolumn.set_sort_column_id(2)
		tvcolumn.set_resizable(True)

		tvcolumn = Gtk.TreeViewColumn('Updates')
		treeview.append_column(tvcolumn)
		tvcolumn.pack_start(numcell, True)
		tvcolumn.add_attribute(numcell, 'text', 3)
		tvcolumn.set_sort_column_id(3)
		tvcolumn.set_resizable(True)

		tvcolumn = Gtk.TreeViewColumn('Triggers')
		treeview.append_column(tvcolumn)
		tvcolumn.pack_start(numcell, True)
		tvcolumn.add_attribute(numcell, 'text', 4)
		tvcolumn.set_sort_column_id(4)
		tvcolumn.set_resizable(True)

		tvcolumn = Gtk.TreeViewColumn('Time')
		treeview.append_column(tvcolumn)
		tvcolumn.pack_start(cell, True)
		tvcolumn.add_attribute(cell, 'text', 5)
		tvcolumn.set_sort_column_id(5)
		tvcolumn.set_resizable(True)

		self.window.show_all()

	@trace
	def filter_func(self, model, iter, data):
		if self.matchprog is None:
			return True
		if self.matchprog.search (model[iter][1]) is not None:
			if model[iter][0] not in self.shown:
				self.shown[model[iter][0]] = model[iter][0]
			return True
		self.excluded += 1
		return False

	###############################
	# GUI component, could be separated out into a GUI class
	# the callback on every poller cycle
	@trace
	def completed_cb(self, thread):
#            logging.debug ("start completed_cb")
            now = time.time()
            msgpersec = int ((self.messages_received - self.last_received) / (now - self.last_now))
            self.last_now = now
            self.last_received = self.messages_received
            self.infolabel2.set_markup('<span foreground="blue">Messages received:  ' + str(self.messages_received) + '        Messages/sec:  ' + str(msgpersec) + '      ignored:  ' + str(self.messages_ignored) + '</span>')

            # run through the changed topics and add to the matrix
            updated_entries = 0

            # take a snapshot of main.changed and main.last_changed
            changed = self.changed
            last_changed = self.last_changed
            self.last_changed = self.changed
            self.changed = dict()
            numbers = set (changed.keys()) | set(last_changed.keys())
            for number in numbers:
                key = changed.get(number, last_changed.get(number, None))
                if key == None:
                    logging.error ('number ' + str(number) + ' not in changed or last_changed')
                    continue

                entry =  self.keys[key]

                color = 'black'
                if entry.value > self.thresh:
                    color = 'red'

                if entry.rowref == None:
                    rowref = self.trigstore.append(
                        [
                        entry.number,
                        entry.key,
                        entry.value,
                        entry.count,
                        entry.triggers,
                        time.ctime (entry.time),
                        color
                        ])

                    entry.rowref = rowref
                    updated_entries += 1
                else:
                    # update existing entry
                    self.trigstore.set (entry.rowref, 2, entry.value, 3, entry.count, 4, entry.triggers, 5, time.ctime (entry.time), 6, color)
                    updated_entries += 1

            # more info after updating entries
            self.infolabel3.set_markup('<span foreground="green">Sensors detected:  ' + str(len(self.keys)) + '         Active:  ' + str(updated_entries) + '</span>')
            num_triggered = len (self.triggered_set)
            if num_triggered > 0:
                self.infolabel4.set_markup('<span foreground="red">Total triggered:  ' +
                        str(self.total_triggered) +
                        '         Sensors:  ' +
                        str(num_triggered) +
                        '</span>')

            # logging.debug ("completed_cb - exit")

            return

	def dump(self):
		outfile = open ("dump.lst", "w+")
		print ("Number Topic                Messages Bytes Last payload", file=outfile)
		keys = self.topics.keys()
		for key in keys:
			topic =  self.topics[key]

			topic.dump(outfile)

		outfile.close()
		print ("dumped to dump.lst")
		return

	def quit(self):
		# client.loop_stop()
		self.is_stopped = True
		return


###########################################################################
class Handler:
	def on_mainWindow_delete_event(self, *args):
		Gtk.main_quit(*args)
		main.quit()
	
	def on_gtk_quit_activate(self, menuitem, data=None):
		Gtk.main_quit()
		main.quit()

	# File->New menu handler
	def on_gtk_filenew_activate(self, menuitem, data=None):
		# clear everything
		main.infolabel3.set_text("")
		main.infolabel4.set_text("")

		main.clear_stats = True

	# File->Save menu handler
	def on_gtk_filesave_activate(self, menuitem, data=None):
		main.dump()

	# Help->About menu handler
	def on_gtk_about_activate(self, menuitem, data=None):
		self.response = main.aboutdialog.run()
		main.aboutdialog.hide()

	def on_gtk_entry2_changed(self, item, data=None):
		# logging.debug ("on_gtk_entry2_changed " + item.get_text())
		if item.get_text() == '':
			main.matchprog = None
		else:
			try:
				main.matchprog = re.compile(item.get_text())
			except:
				main.matchprog = None

		# force an update to all entries
		main.shown.clear()
		for key in main.keys:
			entry = main.keys[key]
			if entry.number not in main.changed:
				main.changed[entry.number] = key
		return

###########################################################################
if __name__ == "__main__":
	GObject.threads_init()

	main = MyApp()
	main.start()
