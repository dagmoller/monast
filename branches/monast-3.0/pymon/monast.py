#!/usr/bin/python -u
# -*- coding: iso8859-1 -*-
##
## Imports
##
import os
import sys
import re
import time
import logging
import optparse

from ConfigParser import SafeConfigParser, NoOptionError

try:
	from twisted.internet import reactor, task, defer
	from twisted.web import server as TWebServer
	from twisted.web import resource
except ImportError:
	print "Monast ERROR: Module twisted not found."
	print "You need twisted matrix 10.1+ to run Monast. Get it from http://twistedmatrix.com/"
	sys.exit(1)

try:
	from starpy import manager
	from starpy.error import AMICommandFailure
except ImportError:
	print "Monast ERROR: Module starpy not found."
	print "You need starpy to run Monast. Get it from http://www.vrplumber.com/programming/starpy/"
	sys.exit(1)

try:
	import json
except ImportError:
	import simplejson as json

#import warnings
#warnings.filterwarnings("ignore")

##
## Defines
##
HTTP_SESSION_TIMEOUT        = 60
AMI_RECONNECT_INTERVAL      = 10
TASK_CHECK_STATUS_INTERVAL  = 60
TASK_CHECK_STATUS_INTERVAL  = 10

MONAST_CALLERID = "MonAst"

AST_DEVICE_STATES = { # copied from include/asterisk/devicestate.h
	'0': 'Unknown',
	'1': 'Not In Use',
	'2': 'In Use',
	'3': 'Busy',
	'4': 'Invalid',
	'5': 'Unavailable',
	'6': 'Ringing',
	'7': 'Ring, In Use',
	'8': 'On Hold'
}

AST_TECH_STATES = {
	'Khomp': 'Not in Use'
}

##
## Logging Initialization
##
log                 = None
logging.DUMPOBJECTS = False
logging.FORMAT      = "[%(asctime)s] %(levelname)-8s :: %(message)s" 
logging.NOTICE      = 60
logging.addLevelName(logging.NOTICE, "NOTICE")

class ColorFormatter(logging.Formatter):
	__colors = {
		'black'  : 30,
		'red'    : 31,
		'green'  : 32,
		'yellow' : 33,
		'blue'   : 34,
		'magenta': 35,
		'cyan'   : 36,
		'white'  : 37
	}
	__levelColors = {
		logging.NOTICE   : 'white',
		logging.INFO     : 'yellow',
		logging.ERROR    : 'red',
		logging.WARNING  : 'magenta',
		logging.DEBUG    : 'cyan'
	}
	
	def __init__(self, fmt = None, datefmt = None):
		logging.Formatter.__init__(self, fmt, datefmt)
		self.colored = hasattr(logging, 'COLORED')
	
	def color(self, levelno, msg):
		if self.colored:
			return '\033[%d;1m%s\033[0m' % (self.__colors[self.__levelColors[levelno]], msg)
		else:
			return msg
	
	def formatTime(self, record, datefmt):
		return self.color(logging.NOTICE, logging.Formatter.formatTime(self, record, datefmt))
	
	def format(self, record):
		if record.levelname == 'DEBUG':
			record.msg = record.msg.encode('utf-8').encode('string_escape')
		
		record.name      = self.color(record.levelno, record.name)
		record.module    = self.color(record.levelno, record.module)
		record.msg       = self.color(record.levelno, record.msg)
		record.levelname = self.color(record.levelno, record.levelname)
		if hasattr(record, 'funcName'):
			record.funcName  = self.color(record.levelno, record.funcName)
			
		if record.exc_info:
			record.exc_text = self.color(record.levelno, '>> %s' % self.formatException(record.exc_info).replace('\n', '\n>> '))
		
		return logging.Formatter.format(self, record)

##
## Classes
##
class GenericObject(object):
	def __init__(self, objecttype = "Generic Object"):
		self.objecttype = objecttype
	def __setattr__(self, key, value):
		self.__dict__[key] = value
	def __getattr__(self, key):
		return self.__dict__.get(key)
	def __delattr__(self, key):
		del self.__dict__[key]
	def __str__(self):
		out = [
			"",
			"##################################################",
			"# Object Type: %s" % self.objecttype,
			"##################################################"
		]
		keys = sorted(self.__dict__.keys())
		pad  = sorted([len(k) for k in keys])[-1]
		
		for key in keys:
			format = "%%%ds : %s" % (pad, '%s')
			value  = self.__dict__.get(key)
			out.append(format % (key, value))
		
		out.append("##################################################")
		
		return "\n".join(out)
	

class MyConfigParser(SafeConfigParser):
	def optionxform(self, optionstr):
		return optionstr

##
## Monast HTTP
##
class MonastHTTP(resource.Resource):
	
	isLeaf   = True
	monast   = None
	sessions = {}
	 
	def __init__(self, host, port):
		log.info('Initializing Monast HTTP Server at %s:%s...' % (host, port))
		self.handlers = {
			'/isAuthenticated' : self.isAuthenticated,
			'/doAuthentication': self.doAuthentication,
			'/doLogout'        : self.doLogout,
			'/getStatus'       : self.getStatus,
			'/listServers'     : self.listServers,
			'/getUpdates'      : self.getUpdates,
			'/doAction'        : self.doAction
		}
	
	def _expireSession(self):
		expired = [sessid for sessid, session in self.sessions.items() if not self.monast.site.sessions.has_key(sessid)]
		for sessid in expired:
			log.info("Removing Expired Client Session: %s" % sessid)
			del self.sessions[sessid]
	
	def _addUpdate(self, **kw):
		session = self.sessions.get(kw.get('sessid'))
		if session:
			session.updates.append(kw)
		else:
			for sessid, session in self.sessions.items():
				session.updates.append(kw)
				
	def _onRequestFailure(self, reason, request):
		session = request.getSession()
		log.error("HTTP Request from %s:%s (%s) to %s failed: %s", request.client.host, request.client.port, session.uid, request.uri, reason.getErrorMessage())
		log.exception("Unhandled Exception on HTTP Request to %s" % request.uri)
		request.setResponseCode(500)
		request.write("ERROR :: Internal Server Error");
		request.finish()
	
	def render_GET(self, request):
		session = request.getSession()
		session.touch()
		log.debug("HTTP Request from %s:%s (%s) to %s", request.client.host, request.client.port, session.uid, request.uri)

		if not self.sessions.has_key(session.uid):
			log.info("New Client Session: %s" % session.uid)
			session._expireCall.cancel()
			session.sessionTimeout = HTTP_SESSION_TIMEOUT
			session.startCheckingExpiration()
			session.notifyOnExpire(self._expireSession)
			session.updates            = []
			session.isAuthenticated    = not self.monast.authRequired
			session.username           = None
			self.sessions[session.uid] = session
		
		if not session.isAuthenticated and request.path != "/doAuthentication":
			return "ERROR :: Authentication Required"
		
		handler = self.handlers.get(request.path)
		if handler:
			d = task.deferLater(reactor, 0.1, lambda: request)
			d.addCallback(handler)
			d.addErrback(self._onRequestFailure, request)
			return TWebServer.NOT_DONE_YET
		
		return "ERROR :: Request Not Found"
	
	def isAuthenticated(self, request):
		request.write(["ERROR :: Authentication Required", "OK"][request.getSession().isAuthenticated])
		request.finish()
	
	def doAuthentication(self, request):
		session  = request.getSession()
		username = request.args.get('username', [None])[0]
		secret   = request.args.get('secret', [None])[0]
		success  = False
		
		if username != None and secret != None:
			authUser = self.monast.authUsers.get(username)
			if authUser:
				if authUser.secret == secret:
					session.isAuthenticated = True
					session.username        = username
					success = True
				else:
					success = False
			else:
				success = False
		else:
			success = False
		
		output = ""
		if success:
			log.log(logging.NOTICE, "User \"%s\" Successful Authenticated with Session \"%s\"" % (username, session.uid))
			request.write("OK :: Authentication Success")
		else:
			log.error("User \"%s\" Failed to Authenticate with session \"%s\"" % (username, session.uid))
			request.write("ERROR :: Invalid Username/Secret")
		request.finish()
	
	def doLogout(self, request):
		session = request.getSession()
		log.log(logging.NOTICE, "User \"%s\" Successful Logout with Session \"%s\"" % (session.username, session.uid))
		session.isAuthenticated = False
		request.write("OK")
		request.finish()
	
	def getStatus(self, request):
		tmp        = {}
		servername = request.args.get('servername', [None])[0]
		session    = request.getSession()
		server     = self.monast.servers.get(servername)
		
		## Clear Updates
		session.updates = []
		
		tmp[servername] = {
			'peers': {},
			'channels': [],
			'bridges': [],
			'meetmes': [],
			'queues': [],
			'queueMembers': [],
			'queueClients': [],
			'queueCalls': [],
			'parkedCalls': []
		}
		## Peers
		for tech, peerlist in server.status.peers.items():
			tmp[servername]['peers'][tech] = []
			for peername, peer in peerlist.items():
				tmp[servername]['peers'][tech].append(peer.__dict__)
			tmp[servername]['peers'][tech].sort(lambda x, y: cmp(x.get('callerid'), y.get('callerid')))
		## Channels
		for uniqueid, channel in server.status.channels.items():
			tmp[servername]['channels'].append(channel.__dict__)
		## Bridges
		for uniqueid, bridge in server.status.bridges.items():
			bridge.seconds = int(time.time()) - bridge.linktime
			tmp[servername]['bridges'].append(bridge.__dict__)
		## Meetmes
		for meetmeroom, meetme in server.status.meetmes.items():
			tmp[servername]['meetmes'].append(meetme.__dict__)
		tmp[servername]['meetmes'].sort(lambda x, y: cmp(x.get('meetme'), y.get('meetme')))
		## Parked Calls
		for channel, parked in server.status.parkedCalls.items():
			tmp[servername]['parkedCalls'].append(parked.__dict__)
		tmp[servername]['parkedCalls'].sort(lambda x, y: cmp(x.get('channel'), y.get('channel')))
		## Queues
		for queuename, queue in server.status.queues.items():
			tmp[servername]['queues'].append(queue.__dict__)
		tmp[servername]['queues'].sort(lambda x, y: cmp(x.get('queue'), y.get('queue')))
		for (queuename, membername), member in server.status.queueMembers.items():
			member.pausedur = int(time.time()) - int(member.pausedat)
			tmp[servername]['queueMembers'].append(member.__dict__)
		tmp[servername]['queueMembers'].sort(lambda x, y: cmp(x.get('name'), y.get('name')))
		for (queuename, uniqueid), client in server.status.queueClients.items():
			client.seconds = int(time.time()) - int(client.jointime)
			tmp[servername]['queueClients'].append(client.__dict__)
		tmp[servername]['queueClients'].sort(lambda x, y: cmp(x.get('name'), y.get('name')))
		for uniqueid, call in server.status.queueCalls.items():
			call.seconds = int(time.time()) - int(call.starttime)  
			tmp[servername]['queueCalls'].append(call.__dict__)
					 
		request.write(json.dumps(tmp, encoding = "ISO8859-1"))
		request.finish()
	
	def getUpdates(self, request):
		session    = request.getSession()
		servername = request.args.get('servername', [None])[0]
		updates    = []
		if len(session.updates) > 0:
			updates         = [u for u in session.updates if u.get('servername') == servername]
			session.updates = []
		if len(updates) > 0:
			request.write(json.dumps(updates, encoding = "ISO8859-1"))
		else:
			request.write("NO UPDATES")
		request.finish()
	
	def listServers(self, request):
		session = request.getSession()
		servers = self.monast.servers.keys()
		if self.monast.authRequired and session.isAuthenticated and session.username:
			servers = self.monast.authUsers[session.username].servers.keys()		
		request.write(json.dumps(servers, encoding = "ISO8859-1"))
		request.finish()
	
	def doAction(self, request):
		session = request.getSession()
		self.monast.clientActions.append((session, request.args))
		reactor.callWhenRunning(self.monast._processClientActions)
		request.write("OK")
		request.finish()

##
## Monast AMI
##
class MonastAMIFactory(manager.AMIFactory):
	amiWorker  = None
	servername = None
	def __init__(self, servername, username, password, amiWorker):
		log.info('Server %s :: Initializing Monast AMI Factory...' % servername)
		self.servername = servername
		self.amiWorker  = amiWorker
		manager.AMIFactory.__init__(self, username, password)
		
	def clientConnectionLost(self, connector, reason):
		log.warning("Server %s :: Lost connection to AMI: %s" % (self.servername, reason.value))
		self.amiWorker.__disconnected__(self.servername)
		reactor.callLater(AMI_RECONNECT_INTERVAL, self.amiWorker.connect, self.servername)

	def clientConnectionFailed(self, connector, reason):
		log.error("Server %s :: Failed to connected to AMI: %s" % (self.servername, reason.value))
		self.amiWorker.__disconnected__(self.servername)
		reactor.callLater(AMI_RECONNECT_INTERVAL, self.amiWorker.connect, self.servername)
		
class Monast:

	configFile         = None
	servers            = {}
	sortby             = 'callerid'
	clientActions      = []
	authRequired       = False
	isParkedCallStatus = False
	
	def __init__(self, configFile):
		log.log(logging.NOTICE, "Initializing Monast AMI Interface...")
		
		self.eventHandlers = {
			'Reload'              : self.handlerEventReload,
			'ChannelReload'       : self.handlerEventChannelReload,
			'PeerEntry'           : self.handlerEventPeerEntry,
			'PeerStatus'          : self.handlerEventPeerStatus,
			#'SkypeAccountStatus'  : self.handlerSkypeAccountStatus,
			#'BranchOnHook'        : self.handlerBranchOnHook,
			#'BranchOffHook'       : self.handlerBranchOffHook,
			'Newchannel'          : self.handlerEventNewchannel,
			'Newstate'            : self.handlerEventNewstate,
			'Rename'              : self.handlerEventRename,
			'Masquerade'          : self.handlerEventMasquerade,
			'Newcallerid'         : self.handlerEventNewcallerid,
			'NewCallerid'         : self.handlerEventNewcallerid,
			'Hangup'              : self.handlerEventHangup,
			'Dial'                : self.handlerEventDial,
			'Link'                : self.handlerEventLink,
			'Unlink'              : self.handlerEventUnlink,
			'Bridge'              : self.handlerEventBridge,
			'MeetmeJoin'          : self.handlerEventMeetmeJoin,
			'MeetmeLeave'         : self.handlerEventMeetmeLeave,
			'ParkedCall'          : self.handlerEventParkedCall,
			'UnParkedCall'        : self.handlerEventUnParkedCall,
			'ParkedCallTimeOut'   : self.handlerEventParkedCallTimeOut,
			'ParkedCallGiveUp'    : self.handlerEventParkedCallGiveUp,
			'QueueMemberAdded'    : self.handlerEventQueueMemberAdded,
			'QueueMemberRemoved'  : self.handlerEventQueueMemberRemoved,
			'Join'                : self.handlerEventJoin, # Queue Join
			'Leave'               : self.handlerEventLeave, # Queue Leave
			'QueueCallerAbandon'  : self.handlerEventQueueCallerAbandon,
			'QueueMemberStatus'   : self.handlerEventQueueMemberStatus,
			'QueueMemberPaused'   : self.handlerEventQueueMemberPaused,
			'MonitorStart'        : self.handlerEventMonitorStart,
			'MonitorStop'         : self.handlerEventMonitorStop,
			'AntennaLevel'        : self.handlerEventAntennaLevel,
		}
		
		self.actionHandlers = {
			'CliCommand'         : ('command', self.clientAction_CliCommand),
			'RequestInfo'        : ('command', self.clientAction_RequestInfo),
			'Originate'          : ('originate', self.clientAction_Originate),
			'Transfer'           : ('originate', self.clientAction_Transfer),
			'Park'               : ('originate', self.clientAction_Park),
			'Hangup'       	     : ('originate', self.clientAction_Hangup),
			'MonitorStart'       : ('originate', self.clientAction_MonitorStart),
			'MonitorStop'        : ('originate', self.clientAction_MonitorStop),
			'QueueMemberPause'   : ('queue', self.clientAction_QueueMemberPause),
			'QueueMemberUnpause' : ('queue', self.clientAction_QueueMemberUnpause),
			'QueueMemberAdd'     : ('queue', self.clientAction_QueueMemberAdd),
			'QueueMemberRemove'  : ('queue', self.clientAction_QueueMemberRemove),
			'MeetmeKick'         : ('originate', self.clientAction_MeetmeKick),
		}
		
		self.configFile = configFile
		self.__parseMonastConfig()
		
	def __start(self):
		log.info("Starting Monast Services...")
		for servername in self.servers:
			reactor.callLater(1, self.connect, servername)
	
	def __connected__(self, ami, servername):
		log.info("Server %s :: Marking as connected..." % servername)
		ami.servername   = servername
		server           = self.servers.get(servername)
		server.connected = True
		server.ami       = ami
		
		## Request Server Version
		def _onCoreShowVersion(result):
			versions = [1.4, 1.6, 1.8]
			log.info("Server %s :: %s" %(servername, result[0]))
			for version in versions:
				if "Asterisk %s" % version in result[0]:
					server.version = version
					break
			for event, handler in self.eventHandlers.items():
				log.debug("Server %s :: Registering EventHandler for %s" % (servername, event))
				server.ami.registerEvent(event, handler)
			log.debug("Server %s :: Starting Task Check Status..." % servername)
			server.taskCheckStatus.start(TASK_CHECK_STATUS_INTERVAL, False)
			self.__requestAsteriskConfig(servername)
			
		server.ami.command('core show version') \
			.addCallbacks(_onCoreShowVersion, self._onAmiCommandFailure, errbackArgs = (servername, "Error Requesting Asterisk Version"))
		
	def __disconnected__(self, servername):
		server = self.servers.get(servername)
		if server.connected:
			log.info("Server %s :: Marking as disconnected..." % servername)
			log.debug("Server %s :: Stopping Task Check Status..." % servername)
			server.taskCheckStatus.stop()
		server.connected = False
		server.ami       = None
	
	def connect(self, servername):
		server = self.servers.get(servername)
		log.info("Server %s :: Trying to connect to AMI at %s:%d" % (servername, server.hostname, server.hostport))
		df = server.factory.login(server.hostname, server.hostport)
		df.addCallback(self.onLoginSuccess, servername)
		df.addErrback(self.onLoginFailure, servername)
		return df
	
	def onLoginSuccess(self, ami, servername):
		log.log(logging.NOTICE, "Server %s :: AMI Connected..." % (servername))
		self.__connected__(ami, servername)
		
	def onLoginFailure(self, reason, servername):
		log.error("Server %s :: Monast AMI Failed to Login, reason: %s" % (servername, reason.getErrorMessage()))
		self.__disconnected__(servername)
	
	##
	## Helpers
	##
	## Users/Peers
	def _createPeer(self, servername, **kw):
		server      = self.servers.get(servername)
		channeltype = kw.get('channeltype')
		_log        = kw.get('_log', '')
		
		if server.status.peers.has_key(channeltype):
			peer             = GenericObject("User/Peer")
			peer.channeltype = channeltype
			peer.peername    = kw.get('peername')
			peer.channel     = '%s/%s' % (channeltype, kw.get('peername'))
			peer.callerid    = kw.get('callerid', '--')
			peer.context     = kw.get('context', server.default_context)
			peer.variables   = kw.get('variables', [])
			peer.status      = kw.get('status', '--')
			peer.time        = kw.get('time', -1)
			peer.calls       = int(kw.get('calls', 0))
			peer.forced      = kw.get('forced', False)
			
			## Dahdi Specific attributes
			if channeltype == 'DAHDI':
				peer.signalling = kw.get('signalling')
				peer.alarm      = kw.get('alarm')
				peer.dnd        = kw.get('dnd')
				peer.callerid   = [peer.channel, "%s %02d" % (peer.signalling, int(peer.peername))][peer.callerid == '--']
				peer.status     = ['--', peer.alarm][peer.status == '--']
				
			## Khomp
			if channeltype == 'Khomp':
				peer.callerid = [peer.callerid, peer.channel][peer.callerid == '--']
				peer.callerid = [peer.channel, "KGSM %s" % peer.peername]['Signal' in peer.status]
				
			log.debug("Server %s :: Adding User/Peer %s %s", servername, peer.channel, _log)
			server.status.peers[peer.channeltype][peer.peername] = peer
			
			if logging.DUMPOBJECTS:
				log.debug("Object Dump:%s", peer)
		else:
			log.warning("Server %s :: Channeltype %s not implemented in Monast.", servername, channeltype)
			
	def _updatePeer(self, servername, **kw):
		channeltype = kw.get('channeltype')
		peername    = kw.get('peername')
		_log        = kw.get('_log', '')
		try:
			peer = self.servers.get(servername).status.peers.get(channeltype, {}).get(peername)
			if peer:
				log.debug("Server %s :: Updating User/Peer %s/%s %s", servername, channeltype, peername, _log)
				for k, v in kw.items():
					if k == '_action':
						if v == 'increaseCallCounter':
							peer.calls += 1
						elif v == 'decreaseCallCounter':
							peer.calls -= 1
					if k not in ('_log', '_action'): 
						if peer.__dict__.has_key(k):
							peer.__dict__[k] = v
						else:
							log.warning("Server %s :: User/Peer %s/%s does not have attribute %s", servername, channeltype, peername, k)
				self.http._addUpdate(servername = servername, **peer.__dict__.copy())
				if logging.DUMPOBJECTS:
					log.debug("Object Dump:%s", peer)
			#else:
			#	log.warning("Server %s :: User/Peer not found: %s/%s", servername, channeltype, peername)
		except:
			log.exception("Server %s :: Unhandled exception updating User/Peer: %s/%s", servername, channeltype, peername)
	
	## Channels	
	def _createChannel(self, servername, **kw):
		server        = self.servers.get(servername)
		uniqueid      = kw.get('uniqueid')
		channel       = kw.get('channel')
		_log          = kw.get('_log', '')
		
		if not server.status.channels.has_key(uniqueid):
			chan              = GenericObject("Channel")
			chan.uniqueid     = uniqueid
			chan.channel      = channel
			chan.state        = kw.get('state', 'Unknown')
			chan.calleridnum  = kw.get('calleridnum', '')
			chan.calleridname = kw.get('calleridname', '')
			chan.monitor      = kw.get('monitor', False)
			
			log.debug("Server %s :: Channel create: %s (%s) %s", servername, uniqueid, channel, _log)
			server.status.channels[uniqueid] = chan
			self.http._addUpdate(servername = servername, **chan.__dict__.copy())
			
			channeltype, peername = channel.rsplit('-', 1)[0].split('/', 1)
			self._updatePeer(servername, channeltype = channeltype, peername = peername, _action = 'increaseCallCounter')
			
			if logging.DUMPOBJECTS:
				log.debug("Object Dump:%s", chan)
			return True
		else:
			if not kw.get('_isCheckStatus'):
				log.warning("Server %s :: Channel already exists: %s (%s)", servername, uniqueid, channel)
		return False
	
	def _updateChannel(self, servername, **kw):
		uniqueid = kw.get('uniqueid')
		channel  = kw.get('channel')
		_log     = kw.get('_log', '')
		
		try:
			chan = self.servers.get(servername).status.channels.get(uniqueid)
			if chan:
				log.debug("Server %s :: Channel update: %s (%s) %s", servername, uniqueid, chan.channel, _log)
				for k, v in kw.items():
					if k not in ('_log'):
						if chan.__dict__.has_key(k):
							chan.__dict__[k] = v
						else:
							log.warning("Server %s :: Channel %s (%s) does not have attribute %s", servername, uniqueid, chan.channel, k)
				self.http._addUpdate(servername = servername, subaction = 'Update', **chan.__dict__.copy())
				if logging.DUMPOBJECTS:
					log.debug("Object Dump:%s", chan)
			else:
				log.warning("Server %s :: Channel not found: %s (%s) %s", servername, uniqueid, channel, _log)
		except:
			log.exception("Server %s :: Unhandled exception updating channel: %s (%s)", servername, uniqueid, channel)
			
	def _removeChannel(self, servername, **kw):
		uniqueid = kw.get('uniqueid')
		channel  = kw.get('channel')
		_log     = kw.get('_log', '')
		try:
			server = self.servers.get(servername)
			chan   = server.status.channels.get(uniqueid)
			if chan:
				log.debug("Server %s :: Channel remove: %s (%s) %s", servername, uniqueid, chan.channel, _log)
				if kw.get('_isLostChannel'):
					log.warning("Server %s :: Removing lost channel: %s (%s)", servername, uniqueid, chan.channel)
				else:
					bridgekey = self._locateBridge(servername, uniqueid = uniqueid)
					if bridgekey:
						self._removeBridge(servername, uniqueid = bridgekey[0], bridgeduniqueid = bridgekey[1], _log = _log)
				del server.status.channels[uniqueid]
				self.http._addUpdate(servername = servername, action = 'RemoveChannel', uniqueid = uniqueid)
				
				channeltype, peername = channel.rsplit('-', 1)[0].split('/', 1)
				self._updatePeer(servername, channeltype = channeltype, peername = peername, _action = 'decreaseCallCounter')
				
				if logging.DUMPOBJECTS:
					log.debug("Object Dump:%s", chan)
			else:
				log.warning("Server %s :: Channel does not exists: %s (%s)", servername, uniqueid, channel)
		except:
			log.exception("Server %s :: Unhandled exception removing channel: %s (%s)", servername, uniqueid, channel)
	
	## Bridges
	def _createBridge(self, servername, **kw):
		server          = self.servers.get(servername)
		uniqueid        = kw.get('uniqueid')
		channel         = kw.get('channel')
		bridgeduniqueid = kw.get('bridgeduniqueid')
		bridgedchannel  = kw.get('bridgedchannel')
		bridgekey       = (uniqueid, bridgeduniqueid) 
		_log            = kw.get('_log', '')
		
		if not server.status.bridges.has_key(bridgekey):
			if not server.status.channels.has_key(uniqueid):
				log.warning("Server %s :: Could not create bridge %s (%s) with %s (%s). Source Channel not found.", servername, uniqueid, channel, bridgeduniqueid, bridgedchannel)
				return False
			if not server.status.channels.has_key(bridgeduniqueid):
				log.warning("Server %s :: Could not create bridge %s (%s) with %s (%s). Bridged Channel not found.", servername, uniqueid, channel, bridgeduniqueid, bridgedchannel)
				return False
				
			bridge			       = GenericObject("Bridge")
			bridge.uniqueid        = uniqueid
			bridge.bridgeduniqueid = bridgeduniqueid
			bridge.channel         = channel
			bridge.bridgedchannel  = bridgedchannel
			bridge.status          = kw.get('status', 'Link')
			bridge.dialtime        = kw.get('dialtime', int(time.time()))
			bridge.linktime        = kw.get('linktime', 0)
			bridge.seconds         = int(time.time()) - bridge.linktime
			
			log.debug("Server %s :: Bridge create: %s (%s) with %s (%s) %s", servername, uniqueid, channel, bridgeduniqueid, bridgedchannel, _log)
			server.status.bridges[bridgekey] = bridge
			self.http._addUpdate(servername = servername, **bridge.__dict__.copy())
			if logging.DUMPOBJECTS:
				log.debug("Object Dump:%s", bridge)
			return True
		else:
			log.warning("Server %s :: Bridge already exists: %s (%s) with %s (%s)", servername, uniqueid, channel, bridgeduniqueid, bridgedchannel)
		return False
	
	def _updateBridge(self, servername, **kw):
		uniqueid        = kw.get('uniqueid')
		channel         = kw.get('channel')
		bridgeduniqueid = kw.get('bridgeduniqueid')
		bridgedchannel  = kw.get('bridgedchannel')
		_log            = kw.get('_log', '')
		try:
			bridge = kw.get('_bridge', self.servers.get(servername).status.bridges.get((uniqueid, bridgeduniqueid)))
			if bridge:
				log.debug("Server %s :: Bridge update: %s (%s) with %s (%s) %s", servername, bridge.uniqueid, bridge.channel, bridge.bridgeduniqueid, bridge.bridgedchannel, _log)
				for k, v in kw.items():
					if k not in ('_log', '_bridge'):
						if bridge.__dict__.has_key(k):
							bridge.__dict__[k] = v
						else:
							log.warning("Server %s :: Bridge %s (%s) with %s (%s) does not have attribute %s", servername, uniqueid, bridge.channel, bridgeduniqueid, bridge.bridgedchannel, k)
				bridge.seconds = int(time.time()) - bridge.linktime
				self.http._addUpdate(servername = servername, subaction = 'Update', **bridge.__dict__.copy())
				if logging.DUMPOBJECTS:
					log.debug("Object Dump:%s", bridge)
			else:
				log.warning("Server %s :: Bridge not found: %s (%s) with %s (%s)", servername, uniqueid, channel, bridgeduniqueid, bridgedchannel)
		except:
			log.exception("Server %s :: Unhandled exception updating bridge: %s (%s) with %s (%s)", servername, uniqueid, channel, bridgeduniqueid, bridgedchannel)
	
	def _locateBridge(self, servername, **kw):
		server          = self.servers.get(servername)
		uniqueid        = kw.get('uniqueid')
		bridgeduniqueid = kw.get('bridgeduniqueid')
		
		if uniqueid and bridgeduniqueid:
			return [None, (uniqueid, bridgeduniqueid)][server.status.bridges.has_key((uniqueid, bridgeduniqueid))]
		
		bridges = [i for i in server.status.bridges.keys() if uniqueid in i or bridgeduniqueid in i]
		if len(bridges) == 1:
			return bridges[0]
		if len(bridges) > 1:
			log.warning("Server %s :: Found more than one bridge with same uniqueid: %s", servername, bridges)
			return None
	
	def _removeBridge(self, servername, **kw):
		uniqueid        = kw.get('uniqueid')
		channel         = kw.get('channel')
		bridgeduniqueid = kw.get('bridgeduniqueid')
		bridgedchannel  = kw.get('bridgedchannel')
		bridgekey       = (uniqueid, bridgeduniqueid)
		_log            = kw.get('_log', '')
		try:
			server = self.servers.get(servername)
			bridge = server.status.bridges.get(bridgekey)
			if bridge:
				log.debug("Server %s :: Bridge remove: %s (%s) with %s (%s) %s", servername, uniqueid, bridge.channel, bridge.bridgeduniqueid, bridge.bridgedchannel, _log)
				if kw.get('_isLostBridge'):
					log.warning("Server %s :: Removing lost bridge: %s (%s) with %s (%s)", servername, uniqueid, bridge.channel, bridge.bridgeduniqueid, bridge.bridgedchannel)
				del server.status.bridges[bridgekey]
				self.http._addUpdate(servername = servername, action = 'RemoveBridge', uniqueid = uniqueid, bridgeduniqueid = bridgeduniqueid)
				if logging.DUMPOBJECTS:
					log.debug("Object Dump:%s", bridge)
			else:
				log.warning("Server %s :: Bridge does not exists: %s (%s) with %s (%s)", servername, uniqueid, channel, bridgeduniqueid, bridgedchannel)
		except:
			log.exception("Server %s :: Unhandled exception removing bridge: %s (%s) with %s (%s)", servername, uniqueid, channel, bridgeduniqueid, bridgedchannel)
			
	## Meetme
	def _createMeetme(self, servername, **kw):
		server     = self.servers.get(servername)
		meetmeroom = kw.get('meetme')
		dynamic    = kw.get("dynamic", False)
		_log       = kw.get('_log')
		meetme     = server.status.meetmes.get(meetmeroom)
		
		if not meetme:
			meetme = GenericObject("Meetme")
			meetme.meetme  = meetmeroom
			meetme.dynamic = dynamic
			meetme.users   = {}
			
			log.debug("Server %s :: Meetme create: %s %s", servername, meetme.meetme, _log)
			server.status.meetmes[meetmeroom] = meetme
			if dynamic:
				self.http._addUpdate(servername = servername, **meetme.__dict__.copy())
			if logging.DUMPOBJECTS:
				log.debug("Object Dump:%s", meetme)
		else:
			log.warning("Server %s :: Meetme already exists: %s", servername, meetme.meetme)
			
		return meetme
			
	def _updateMeetme(self, servername, **kw):
		meetmeroom = kw.get("meetme")
		_log       = kw.get('_log', '')
		try:
			meetme = self.servers.get(servername).status.meetmes.get(meetmeroom)
			if not meetme:
				meetme = self._createMeetme(servername, meetme = meetmeroom, dynamic = True, _log = "(dynamic)")
			
			user = kw.get('addUser')
			if user:
				meetme.users[user.get('usernum')] = user
				log.debug("Server %s :: Added user %s to Meetme %s %s", servername, user.get('usernum'), meetme.meetme, _log)
				
			user = kw.get('removeUser')
			if user:
				u = meetme.users.get(user.get('usernum'))
				if u:
					log.debug("Server %s :: Removed user %s from Meetme %s %s", servername, u.get('usernum'), meetme.meetme, _log)
					del meetme.users[u.get('usernum')]
					
			self.http._addUpdate(servername = servername, **meetme.__dict__.copy())
					
			if meetme.dynamic and len(meetme.users) == 0:
				self._removeMeetme(servername, meetme = meetme.meetme, _log = "(dynamic)")
			if logging.DUMPOBJECTS:
				log.debug("Object Dump:%s", meetme)
		except:
			log.exception("Server %s :: Unhandled exception updating meetme: %s", servername, meetmeroom)
			
	def _removeMeetme(self, servername, **kw):
		meetmeroom = kw.get("meetme")
		_log       = kw.get('_log', '')
		try:
			server = self.servers.get(servername)
			meetme = server.status.meetmes.get(meetmeroom)
			if meetme:
				log.debug("Server %s :: Meetme remove: %s %s", servername, meetme.meetme, _log)
				del server.status.meetmes[meetme.meetme]
				self.http._addUpdate(servername = servername, action = 'RemoveMeetme', meetme = meetme.meetme)
				if logging.DUMPOBJECTS:
					log.debug("Object Dump:%s", meetme)
			else:
				log.warning("Server %s :: Meetme does not exists: %s", servername, meetmeroom)
		except:
			log.exception("Server %s :: Unhandled exception removing meetme: %s", servername, meetmeroom)
	
	## Parked Calls
	def _createParkedCall(self, servername, **kw):
		server     = self.servers.get(servername)
		channel    = kw.get('channel')
		parked     = server.status.parkedCalls.get(channel)
		_log       = kw.get('_log', '')
		
		if not parked:
			parked = GenericObject('ParkedCall')
			parked.channel      = channel
			parked.parkedFrom   = kw.get('from')
			parked.calleridname = kw.get('calleridname')
			parked.calleridnum  = kw.get('calleridnum')
			parked.exten        = kw.get('exten')
			parked.timeout      = int(kw.get('timeout'))
			
			# locate "from" channel
			fromChannel = None
			for uniqueid, fromChannel in server.status.channels.items():
				if parked.parkedFrom == fromChannel.channel:
					parked.calleridnameFrom = fromChannel.calleridname
					parked.calleridnumFrom = fromChannel.calleridnum
					break
			
			log.debug("Server %s :: ParkedCall create: %s at %s %s", servername, parked.channel, parked.exten, _log)
			server.status.parkedCalls[channel] = parked
			self.http._addUpdate(servername = servername, **parked.__dict__.copy())
			if logging.DUMPOBJECTS:
				log.debug("Object Dump:%s", parked)
		else:
			if not self.isParkedCallStatus:
				log.warning("Server %s :: ParkedCall already exists: %s at %s", servername, parked.channel, parked.exten)
				
	def _removeParkedCall(self, servername, **kw):
		channel    = kw.get('channel')
		_log       = kw.get('_log', '')
		
		try:
			server = self.servers.get(servername)
			parked = server.status.parkedCalls.get(channel)
			if parked:
				log.debug("Server %s :: ParkedCall remove: %s at %s %s", servername, parked.channel, parked.exten, _log)
				del server.status.parkedCalls[parked.channel]
				self.http._addUpdate(servername = servername, action = 'RemoveParkedCall', channel = parked.channel)
				if logging.DUMPOBJECTS:
					log.debug("Object Dump:%s", parked)
			else:
				log.warning("Server %s :: ParkedCall does not exists: %s", servername, channel)
		except:
			log.exception("Server %s :: Unhandled exception removing ParkedCall: %s", servername, channel)
	
	## Queues
	def _createQueue(self, servername, **kw):
		server    = self.servers.get(servername)
		queuename = kw.get('queue')
		_log      = kw.get('_log', '')
		
		queue     = server.status.queues.get(queuename)
		
		if not queue:
			queue                  = GenericObject("Queue")
			queue.queue            = queuename
			queue.calls            = int(kw.get('calls', 0))
			queue.completed        = int(kw.get('completed', 0))
			queue.holdtime         = kw.get('holdtime', 0)
			queue.max              = kw.get('max', 0)
			queue.servicelevel     = kw.get('servicelevel', 0)
			queue.servicelevelperf = kw.get('servicelevelperf', 0)
			queue.weight           = kw.get('weight', 0)
			queue.strategy         = kw.get('strategy')
			queue.talktime         = kw.get('talktime', 0)
			
			log.debug("Server %s :: Queue create: %s %s", servername, queue.queue, _log)
			server.status.queues[queuename] = queue
			if logging.DUMPOBJECTS:
				log.debug("Object Dump:%s", queue)
		else:
			log.warning("Server %s :: Queue already exists: %s", servername, queue.queue)
			
		return queue
	
	def _updateQueue(self, servername, **kw):
		server    = self.servers.get(servername)
		queuename = kw.get('queue')
		event     = kw.get('event')
		_log      = kw.get('_log', '')
		
		try:
			queue = server.status.queues.get(queuename)
			if queue:
				if event == "QueueParams":
					log.debug("Server %s :: Queue update: %s %s", servername, queuename, _log)
					queue.calls            = int(kw.get('calls', 0))
					queue.completed        = int(kw.get('completed', 0))
					queue.abandoned        = int(kw.get('abandoned', 0))
					queue.holdtime         = kw.get('holdtime', 0)
					queue.max              = kw.get('max', 0)
					queue.servicelevel     = kw.get('servicelevel', 0)
					queue.servicelevelperf = kw.get('servicelevelperf', 0)
					queue.weight           = kw.get('weight', 0)
					queue.talktime         = kw.get('talktime', 0)
					self.http._addUpdate(servername = servername, subaction = 'Update', **queue.__dict__.copy())
					if logging.DUMPOBJECTS:
						log.debug("Object Dump:%s", queue)
					return
				
				if event in ("QueueMember", "QueueMemberAdded", "QueueMemberStatus", "QueueMemberPaused"):
					location = kw.get('location')
					memberid = (queuename, location)
					member   = server.status.queueMembers.get(memberid)
					if not member:
						log.debug("Server %s :: Queue update, member added: %s -> %s %s", servername, queuename, location, _log)
						member            = GenericObject("QueueMember")
						member.location   = location
						member.name       = kw.get('name', kw.get('membername'))
						member.queue      = kw.get('queue')
						member.callstaken = kw.get('callstaken', 0)
						member.lastcall   = kw.get('lastcall', 0)
						member.membership = kw.get('membership')
						member.paused     = kw.get('paused')
						member.pausedat   = [0, time.time()][member.paused == '1']
						member.pausedur   = int(time.time() - member.pausedat)
						member.penalty    = kw.get('penalty')
						member.status     = kw.get('status')
						member.statustext = AST_DEVICE_STATES.get(member.status, 'Unknown')
						self.http._addUpdate(servername = servername, **member.__dict__.copy())
					else:
						log.debug("Server %s :: Queue update, member updated: %s -> %s %s", servername, queuename, location, _log)
						member.name       = kw.get('name', kw.get('membername'))
						member.queue      = kw.get('queue')
						member.callstaken = kw.get('callstaken', 0)
						member.lastcall   = kw.get('lastcall', 0)
						member.membership = kw.get('membership')
						member.paused     = kw.get('paused')
						member.pausedat   = [member.pausedat, time.time()][event == "QueueMemberPaused" and member.paused == '1']
						member.pausedur   = int(time.time()) - int(member.pausedat)
						member.penalty    = kw.get('penalty')
						member.status     = kw.get('status')
						member.statustext = AST_DEVICE_STATES.get(member.status, 'Unknown')
						self.http._addUpdate(servername = servername, subaction = 'Update', **member.__dict__.copy())
					server.status.queueMembers[memberid] = member
					if logging.DUMPOBJECTS:
						log.debug("Object Dump:%s", member)
					return
				
				if event == "QueueMemberRemoved":
					location = kw.get('location')
					memberid = (queuename, location)
					member   = server.status.queueMembers.get(memberid)
					if member:
						log.debug("Server %s :: Queue update, member removed: %s -> %s %s", servername, queuename, location, _log)
						del server.status.queueMembers[memberid]
						self.http._addUpdate(servername = servername, action = 'RemoveQueueMember', location = member.location, queue = member.queue)
						if logging.DUMPOBJECTS:
							log.debug("Object Dump:%s", meetme)
					else:
						log.warning("Server %s :: Queue Member does not exists: %s -> %s", servername, queuename, location)
					return
				
				if event in ("QueueEntry", "Join"):
					uniqueid = kw.get('uniqueid', None)
					if not uniqueid:
						# try to found uniqueid based on channel name
						channel  = kw.get('channel')
						for uniqueid, chan in server.status.channels.items():
							if channel == chan:
								break
					clientid = (queuename, uniqueid) 
					client   = server.status.queueClients.get(clientid)
					if not client:
						log.debug("Server %s :: Queue update, client added: %s -> %s %s", servername, queuename, uniqueid, _log)
						client              = GenericObject("QueueClient")
						client.uniqueid     = uniqueid
						client.channel      = kw.get('channel')
						client.queue        = kw.get('queue')
						client.calleridname = kw.get('calleridname')
						client.calleridnum  = kw.get('calleridnum')
						client.position     = kw.get('position')
						client.abandonned   = False
						client.jointime     = int(time.time() - int(kw.get('wait', 0)))
						client.seconds      = int(time.time() - client.jointime)
						self.http._addUpdate(servername = servername, **client.__dict__.copy())
					else:
						log.debug("Server %s :: Queue update, client updates: %s -> %s %s", servername, queuename, uniqueid, _log)
						client.channel      = kw.get('channel')
						client.queue        = kw.get('queue')
						client.calleridname = kw.get('calleridname')
						client.calleridnum  = kw.get('calleridnum')
						client.position     = kw.get('position')
						client.seconds      = int(time.time() - client.jointime)
						self.http._addUpdate(servername = servername, subaction = 'Update', **client.__dict__.copy())
					server.status.queueClients[clientid] = client
					if event == "Join":
						queue.calls += 1
						self.http._addUpdate(servername = servername, subaction = 'Update', **queue.__dict__.copy())
					if logging.DUMPOBJECTS:
						log.debug("Object Dump:%s", client)
					return
				
				if event == "QueueCallerAbandon":
					uniqueid = kw.get('uniqueid', None)
					if not uniqueid:
						# try to found uniqueid based on channel name
						channel  = kw.get('channel')
						for uniqueid, chan in server.status.channels.items():
							if channel == chan:
								break
					clientid = (queuename, uniqueid) 
					client   = server.status.queueClients.get(clientid)
					if client:
						log.debug("Server %s :: Queue update, client marked as abandonned: %s -> %s %s", servername, queuename, uniqueid, _log)
						client.abandonned == True
						queue.abandoned   += 1
						self.http._addUpdate(servername = servername, subaction = 'Update', **queue.__dict__.copy())
					else:
						log.warning("Server %s :: Queue Client does not exists: %s -> %s", servername, queuename, uniqueid)
					return
				
				if event == "Leave":
					uniqueid = kw.get('uniqueid', None)
					if not uniqueid:
						# try to found uniqueid based on channel name
						channel  = kw.get('channel')
						for uniqueid, chan in server.status.channels.items():
							if channel == chan:
								break
					clientid = (queuename, uniqueid) 
					client   = server.status.queueClients.get(clientid)
					if client:
						queue.calls -= 1
						self.http._addUpdate(servername = servername, subaction = 'Update', **queue.__dict__.copy())
						if not client.abandonned:
							call           = GenericObject("QueueCall")
							call.client    = client.__dict__
							call.member    = None
							call.link      = False
							call.starttime = time.time()
							call.seconds   = int(time.time()) - int(call.starttime)
							server.status.queueCalls[client.uniqueid] = call
						
						log.debug("Server %s :: Queue update, client removed: %s -> %s %s", servername, queuename, uniqueid, _log)
						del server.status.queueClients[clientid]
						self.http._addUpdate(servername = servername, action = 'RemoveQueueClient', uniqueid = client.uniqueid, queue = client.queue)
						if logging.DUMPOBJECTS:
							log.debug("Object Dump:%s", meetme)
					else:
						log.warning("Server %s :: Queue Client does not exists: %s -> %s", servername, queuename, uniqueid)
					return
				
			else:
				log.warning("Server %s :: Queue not found: %s", servername, queuename)
		except:
			log.exception("Server %s :: Unhandled exception updating queue: %s", servername, queuename)
			
	##
	## Parse monast.conf
	##	
	def __parseMonastConfig(self):
		log.log(logging.NOTICE, 'Parsing config file %s' % self.configFile)
		
		config = MyConfigParser()
		config.read(self.configFile)
		
		self.authRequired = config.get('global', 'auth_required') == 'true'
		
		## HTTP Server
		self.bindHost    = config.get('global', 'bind_host')
		self.bindPort    = int(config.get('global', 'bind_port'))
		self.http        = MonastHTTP(self.bindHost, self.bindPort)
		self.http.monast = self
		self.site        = TWebServer.Site(self.http)
		reactor.listenTCP(self.bindPort, self.site, 50, self.bindHost)
		
		## Reading servers sections
		servers = [s for s in config.sections() if s.startswith('server:')]
		servers.sort()
		
		for server in servers:
			servername = server.replace('server:', '').strip()
			username   = config.get(server, 'username')
			password   = config.get(server, 'password')
			
			self.servers[servername] = GenericObject("Server")
			self.servers[servername].servername       = servername
			self.servers[servername].version          = None
			self.servers[servername].lastReload       = 0
			self.servers[servername].hostname         = config.get(server, 'hostname')
			self.servers[servername].hostport         = int(config.get(server, 'hostport'))
			self.servers[servername].username         = config.get(server, 'username')
			self.servers[servername].password         = config.get(server, 'password')
			self.servers[servername].default_context  = config.get(server, 'default_context')
			self.servers[servername].transfer_context = config.get(server, 'transfer_context')
			self.servers[servername].meetme_context   = config.get(server, 'meetme_context')
			self.servers[servername].meetme_prefix    = config.get(server, 'meetme_prefix')
			
			self.servers[servername].connected        = False
			self.servers[servername].factory          = MonastAMIFactory(servername, username, password, self)
			self.servers[servername].ami              = None
			self.servers[servername].taskCheckStatus  = task.LoopingCall(self.taskCheckStatus, servername)
			
			self.servers[servername].status              = GenericObject()
			self.servers[servername].status.meetmes      = {}
			self.servers[servername].status.channels     = {}
			self.servers[servername].status.bridges      = {}
			self.servers[servername].status.peers        = {
				'SIP': {},
				'IAX2': {},
				'DAHDI': {},
				'Khomp': {},
			}
			self.servers[servername].displayUsers        = {}
			self.servers[servername].displayQueues       = {}
			self.servers[servername].status.queues       = {}
			self.servers[servername].status.queueMembers = {}
			self.servers[servername].status.queueClients = {}
			self.servers[servername].status.queueCalls   = {}
			self.servers[servername].status.parkedCalls  = {}
			
		## Peers
		self.displayUsersDefault = config.get('peers', 'default') == 'show'
		try:
			self.sortby = config.get('peers', 'sortby')
		except NoOptionError:
			self.sortby = 'callerid'
			log.error("No option 'sortby' in section: 'peers' of config file, sorting by CallerID")
		
		for user, display in config.items('peers'):
			if user in ('default', 'sortby'):
				continue
			
			servername, user = user.split('/', 1)
			server = self.servers.get(servername)
			if not server:
				continue
			
			tech, peer = user.split('/')
			
			if tech in server.status.peers.keys(): 
				if (self.displayUsersDefault and display == 'hide') or (not self.displayUsersDefault and display == 'show'):
					server.displayUsers[user] = True
					
			if display.startswith('force'):
				status = '--'
				if AST_TECH_STATES.has_key(tech):
					status = AST_TECH_STATES[tech]
				
				tmp      = display.split(',')
				display  = tmp[0].strip()
				callerid = '--'
				if len(tmp) == 2:
					callerid = tmp[1].strip()
					
				self._createPeer(
					servername, 
					channeltype = tech, 
					peername    = peer,
					callerid    = callerid,
					status      = status,
					forced      = True,
					_log        = '(forced peer)'
				)
					
		## Queues
		self.displayQueuesDefault = config.get('queues', 'default') == 'show'
			
		for queue, display in config.items('queues'):
			if queue in ('default'):
				continue
			
			servername, queue = queue.split('/', 1)
			server = self.servers.get(servername)
			if not server:
				continue
			
			if (self.displayQueuesDefault and display == 'hide') or (not self.displayQueuesDefault and display == 'show'):
				server.displayQueues[queue] = True
		
		## User Roles
		self.authUsers = {}
		users = [s for s in config.sections() if s.startswith('user:')]
		for user in users:
			username = user.replace('user:', '').strip()
			try:
				montasUser          = GenericObject("Monast User")
				montasUser.username = username 
				montasUser.secret   = config.get(user, 'secret')
				montasUser.servers  = {}
				
				roles   = [i.strip() for i in config.get(user, 'roles').split(',')]
				servers = [i.strip() for i in config.get(user, 'servers').split(',')]
				
				if config.get(user, 'servers').upper() == 'ALL':
					servers = self.servers.keys()
				
				for server in servers:
					if self.servers.has_key(server):
						try:
							serverRoles = [i.strip() for i in config.get(user, server).split(',')]
							montasUser.servers[server] = serverRoles
						except:
							montasUser.servers[server] = roles
				
				if len(montasUser.servers) == 0:
					log.error("Username %s has errors in config file!" % username)
					continue
				
				self.authUsers[username] = montasUser
			except:
				log.error("Username %s has errors in config file!" % username)
			
		## Start all server factory
		self.__start()
	
	##
	## Request Asterisk Configuration
	##
	def _onAmiCommandFailure(self, reason, servername, message = None):
		if not message:
			message = "AMI Action Error"
		
		errorMessage = reason.getErrorMessage()
		if type(reason.value) == AMICommandFailure and type(reason.value.args[0]) == type(dict()) and reason.value.args[0].has_key('message'):
			errorMessage = reason.value.args[0].get('message')
		
		log.error("Server %s :: %s, reason: %s" % (servername, message, errorMessage))
		
	def __requestAsteriskConfig(self, servername):
		log.info("Server %s :: Requesting Asterisk Configuration..." % servername)
		server = self.servers.get(servername)
		
		## Request Browser Reload
		self.http._addUpdate(servername = servername, action = "Reload", time = 5000)
		
		## Clear Server Status
		server.status.meetmes.clear()
		server.status.channels.clear()
		server.status.bridges.clear()
		server.status.queues.clear()
		server.status.queueMembers.clear()
		server.status.queueClients.clear()
		server.status.queueCalls.clear()
		server.status.parkedCalls.clear()
		for channeltype, peers in server.status.peers.items():
			toRemove = []
			for peername, peer in peers.items():
				if not peer.forced:
					toRemove.append(peername)
			for peername in toRemove:
				del peers[peername]
		
		## Peers (SIP, IAX) :: Process results via handlerEventPeerEntry
		log.debug("Server %s :: Requesting SIP Peers..." % servername)
		server.ami.sendDeferred({'action': 'sippeers'}) \
			.addCallback(server.ami.errorUnlessResponse) \
			.addErrback(self._onAmiCommandFailure, servername, "Error Requesting SIP Peers")

		## Peers IAX different behavior in asterisk 1.4
		if server.version == 1.4:
			def onIax2ShowPeers(result):
				if len(result) > 2:
					for line in result[1:][:-1]:
						peername = line.split(' ', 1)[0].split('/', 1)[0]
						self.handlerEventPeerEntry(server.ami, {'channeltype': 'IAX2', 'objectname': peername, 'status': 'Unknown'})
			log.debug("Server %s :: Requesting IAX Peers (via iax2 show peers)..." % servername)
			server.ami.command('iax2 show peers') \
				.addCallbacks(onIax2ShowPeers, self._onAmiCommandFailure, errbackArgs = (servername, "Error Requesting IAX Peers (via iax2 show peers)"))
		else:		
			log.debug("Server %s :: Requesting IAX Peers..." % servername)
			server.ami.sendDeferred({'action': 'iaxpeers'}) \
				.addCallback(server.ami.errorUnlessResponse) \
				.addErrback(self._onAmiCommandFailure, servername, "Error Requesting IAX Peers")
		
		# DAHDI
		def onDahdiShowChannels(events):
			log.debug("Server %s :: Processing DAHDI Channels..." % servername)
			for event in events:
				user = "DAHDI/%s" % event.get('dahdichannel')
				if (self.displayUsersDefault and not server.displayUsers.has_key(user)) or (not self.displayUsersDefault and server.displayUsers.has_key(user)):
					self._createPeer(
						servername,
						channeltype = 'DAHDI',
						peername    = event.get('dahdichannel'),
						context     = event.get('context'),
						alarm       = event.get('alarm'),
						signalling  = event.get('signalling'),
						dnd         = event.get('dnd')
					)
		def onDahdiShowChannelsFailure(reason, servername, message = None):
			if not "unknown command" in reason.getErrorMessage():
				self._onAmiCommandFailure(reason, servername, message)			

		log.debug("Server %s :: Requesting DAHDI Channels..." % servername)
		server.ami.collectDeferred({'action': 'dahdishowchannels'}, 'DAHDIShowChannelsComplete') \
			.addCallbacks(onDahdiShowChannels, onDahdiShowChannelsFailure, errbackArgs = (servername, "Error Requesting DAHDI Channels"))
		
		# Khomp
		def onKhompChannelsShow(result):
			log.debug("Server %s :: Processing Khomp Channels..." % servername)
			if not 'no such command' in result[0].lower():
				reChannelGSM = re.compile("\|\s+([0-9,]+)\s+\|.*\|\s+([0-9%]+)\s+\|")
				reChannel    = re.compile("\|\s+([0-9,]+)\s+\|")
				for line in result:
					gChannelGSM = reChannelGSM.search(line)
					gChannel    = reChannel.search(line)
					if gChannelGSM:
						board, chanid = gChannelGSM.group(1).split(',')
						user = "Khomp/B%dC%d" % (int(board), int(chanid))
						if (self.displayUsersDefault and not server.displayUsers.has_key(user)) or (not self.displayUsersDefault and server.displayUsers.has_key(user)):
							self._createPeer(
								servername,
								channeltype = 'Khomp',
								peername    = 'B%dC%d' % (int(board), int(chanid)),
								status      = 'Signal: %s' % gChannelGSM.group(2).strip()
							)
					elif gChannel:
						board, chanid = gChannel.group(1).split(',')
						user = "Khomp/B%dC%d" % (int(board), int(chanid))
						if (self.displayUsersDefault and not server.displayUsers.has_key(user)) or (not self.displayUsersDefault and server.displayUsers.has_key(user)):
							self._createPeer(
								servername,
								channeltype = 'Khomp',
								peername    = 'B%dC%d' % (int(board), int(chanid))
							)
			
		log.debug("Server %s :: Requesting Khomp Channels..." % servername)
		server.ami.command('khomp channels show') \
			.addCallbacks(onKhompChannelsShow, self._onAmiCommandFailure, errbackArgs = (servername, "Error Requesting Khomp Channels"))
		
		# Meetme
		def onGetMeetmeConfig(result):
			log.debug("Server %s :: Processing meetme.conf..." % servername)
			for k, v in result.items():
				if v.startswith("conf="):
					meetmeroom = v.replace("conf=", "")
					self._createMeetme(servername, meetme = meetmeroom)

		log.debug("Server %s :: Requesting meetme.conf..." % servername)
		server.ami.sendDeferred({'Action': 'GetConfig', 'Filename': 'meetme.conf'}) \
			.addCallback(server.ami.errorUnlessResponse) \
			.addCallbacks(onGetMeetmeConfig, self._onAmiCommandFailure, errbackArgs = (servername, "Error Requesting meetme.conf"))
		
		# Queues
		def onQueueStatus(events):
			log.debug("Server %s :: Processing Queues..." % servername)
			for event in events:
				eventType = event.get('event')
				if eventType == "QueueParams":
					queuename = event.get('queue')
					if (self.displayQueuesDefault and not server.displayQueues.has_key(queuename)) or (not self.displayQueuesDefault and server.displayQueues.has_key(queuename)):
						self._createQueue(servername, **event)
					continue
		
		log.debug("Server %s :: Requesting Queues..." % servername)
		server.ami.collectDeferred({'Action': 'QueueStatus'}, 'QueueStatusComplete') \
			.addCallbacks(onQueueStatus, self._onAmiCommandFailure, errbackArgs = (servername, "Error Requesting Queue Status"))
		
		## Run Task Channels Status
		reactor.callLater(2, self.taskCheckStatus, servername)
	
	##
	## Tasks
	##
	def taskCheckStatus(self, servername):
		log.info("Server %s :: Requesting asterisk status..." % servername)
		server = self.servers.get(servername)
		
		## Channels Status
		def onStatusComplete(events):
			log.debug("Server %s :: Processing channels status..." % servername)
			channelStatus = {}
			#Sort channels by uniqueid desc
			events.sort(lambda x, y: cmp(y.get('uniqueid'), x.get('uniqueid')))
			for event in events:
				uniqueid        = event.get('uniqueid')
				channel         = event.get('channel')
				bridgedchannel  = event.get('bridgedchannel', event.get('link'))
				seconds         = int(event.get('seconds', 0))
				
				channelStatus[uniqueid] = None
				channelCreated          = self._createChannel(
					servername,
					uniqueid       = uniqueid,
					channel        = channel,
					state          = event.get('channelstatedesc', event.get('state')),
					calleridnum    = event.get('calleridnum'),
					calleridname   = event.get('calleridname'),
					_isCheckStatus = True,
					_log           = "-- By Status Request"
				)
				
				## Create bridge if not exists
				if channelCreated and bridgedchannel:
					for bridgeduniqueid, chan in server.status.channels.items():
						if chan.channel == bridgedchannel:
							self._createBridge(
								servername,
								uniqueid        = uniqueid,
								bridgeduniqueid = bridgeduniqueid,
								channel         = channel,
								bridgedchannel  = bridgedchannel,
								status          = 'Link',
								#starttime       = int(time.time()) - seconds,
								#seconds         = seconds,
								dialtime        = int(time.time()) - seconds,
								linktime        = int(time.time()) - seconds,
								seconds         = seconds,
								_log            = "-- By Status Request"
							)
							break
						
			## Search for lost channels
			lostChannels = [(k, v.channel) for k, v in server.status.channels.items() if not channelStatus.has_key(k)]
			for uniqueid, channel in lostChannels:
				self._removeChannel(servername, uniqueid = uniqueid, channel = channel, _isLostChannel = True, _log = "-- Lost Channel")
					
			## Search for lost bridges
			lostBridges = [
				(b.uniqueid, b.bridgeduniqueid) for b in server.status.bridges.values()
				if not server.status.channels.has_key(b.uniqueid) or not server.status.channels.has_key(b.bridgeduniqueid)
			]
			for uniqueid, bridgeduniqueid in lostBridges:
				self._removeBridge(servername, uniqueid = uniqueid, bridgeduniqueid = bridgeduniqueid, _isLostBridge = True, _log = "-- Lost Bridge")
					
			log.debug("Server %s :: End of channels status..." % servername)
			
		server.ami.status().addCallbacks(onStatusComplete, self._onAmiCommandFailure, errbackArgs = (servername, "Error Requesting Channels Status"))
		
		## Queues
		def onQueueStatusComplete(events):
			log.debug("Server %s :: Processing Queues Status..." % servername)
			for event in events:
				queuename = event.get('queue')
				if (self.displayQueuesDefault and not server.displayQueues.has_key(queuename)) or (not self.displayQueuesDefault and server.displayQueues.has_key(queuename)):
					self._updateQueue(servername, **event)
			for callid, call in server.status.queueCalls.items():
				self.http._addUpdate(servername = servername, **call.__dict__.copy())
		
		log.debug("Server %s :: Requesting Queues Status..." % servername)
		for queuename in server.status.queues.keys():
			server.ami.collectDeferred({'Action': 'QueueStatus', 'Queue': queuename}, 'QueueStatusComplete') \
				.addCallbacks(onQueueStatusComplete, self._onAmiCommandFailure, errbackArgs = (servername, "Error Requesting Queues Status"))
				
		## Parked Calls
		def onParkedCalls(events):
			log.debug("Server %s :: Processing Parked Calls..." % servername)
			self.isParkedCallStatus = False
			# Parked calls was processed by handlerEventParkedCall
		
		log.debug("Server %s :: Requesting Parked Calls..." % servername)
		self.isParkedCallStatus = True
		server.ami.collectDeferred({'Action': 'ParkedCalls'}, 'ParkedCallsComplete') \
			.addCallbacks(onParkedCalls, self._onAmiCommandFailure, errbackArgs = (servername, "Error Requesting Parked Calls"))
		
	##
	## Client Action Handler
	##
	def _processClientActions(self):
		log.debug("Processing Client Actions...")
		while self.clientActions:
			session, action = self.clientActions.pop(0)
			servername      = action['server'][0]
			role, handler   = self.actionHandlers.get(action['action'][0], (None, None))
			if handler:
				if self.authRequired:
					if role in self.authUsers[session.username].servers.get(servername):
						reactor.callWhenRunning(handler, session, action)
					else:
						self.http._addUpdate(servername = servername, sessid = session.uid, action = "RequestError", message = "You do not have permission to execute this action.")
				else:
					reactor.callWhenRunning(handler, session, action)
			else:
				log.error("ClientActionHandler for action %s does not exixts..." % action['action'][0]) 
			
	def clientAction_Originate(self, session, action):
		servername  = action['server'][0]
		source      = action['from'][0]
		destination = action['to'][0] 
		type        = action['type'][0]
		server      = self.servers.get(servername)
		
		channel     = source
		context     = server.default_context
		exten       = None
		priority    = None
		timeout     = None
		callerid    = action.get('callerid', [MONAST_CALLERID])[0]
		account     = None
		application = None
		data        = None
		variable    = {}
		async       = True

		originates  = []
		logs        = []

		if type == "internalCall":
			application = "Dial"
			data        = "%s,30,rTt" % destination
			originates.append((channel, context, exten, priority, timeout, callerid, account, application, data, variable, async))
			logs.append("from %s to %s" % (channel, destination))

		if type == "dial":
			tech, peer = source.split('/')
			peer       = server.status.peers.get(tech).get(peer)
			context    = peer.context
			exten      = destination
			priority   = 1
			variable   = dict([i.split('=', 1) for i in peer.variables])
			originates.append((channel, context, exten, priority, timeout, callerid, account, application, data, variable, async))
			logs.append("from %s to %s@%s" % (channel, exten, context))
		
		if type == "meetmeInviteUser":
			application = "Meetme"
			data        = destination
			originates.append((channel, context, exten, priority, timeout, callerid, account, application, data, variable, async))
			logs.append("Invite from %s to %s(%s)" % (channel, application, data))
		
		if type == "meetmeInviteNumbers":
			dynamic     = not server.status.meetmes.has_key(destination)
			application = "Meetme"
			data        = [destination, "%s,d" % destination][dynamic]
			numbers     = source.replace('\r', '').split('\n')
			for number in [i.strip() for i in numbers if i.strip()]:
				channel     = "Local/%s@%s" % (number, context)
				callerid    = "MonAst Invited <%s>" % (number)
				originates.append((channel, context, exten, priority, timeout, callerid, account, application, data, variable, async))
				logs.append("Invite from %s to %s(%s)" % (channel, application, data))

		for idx, originate in enumerate(originates):
			channel, context, exten, priority, timeout, callerid, account, application, data, variable, async = originate
			log.info("Server %s :: Executting Client Action Originate: %s..." % (servername, logs[idx]))
			server.ami.originate(*originate) \
				.addErrback(self._onAmiCommandFailure, servername, "Error Executting Client Action Originate: %s" % (logs[idx]))
				
	def clientAction_Transfer(self, session, action):
		servername  = action['server'][0]
		source      = action['from'][0]
		destination = action['to'][0] 
		type        = action['type'][0]
		server      = self.servers.get(servername)
		
		channel      = source
		context      = server.default_context
		exten        = destination
		priority     = 1
		extraChannel = None
		
		if type == "meetme":
			extraChannel = action['extrachannel'][0]
			exten        = "%s%s" % (server.meetme_prefix, exten)
			context      = server.meetme_context
		
		log.info("Server %s :: Executting Client Action Transfer: %s -> %s@%s..." % (servername, channel, exten, context))
		server.ami.redirect(channel, context, exten, priority, extraChannel) \
			.addErrback(self._onAmiCommandFailure, servername, "Error Executting Client Action Transfer: %s -> %s@%s" % (channel, exten, context))

	def clientAction_Park(self, session, action):
		servername  = action['server'][0]
		channel     = action['channel'][0]
		announce    = action['announce'][0]
		server      = self.servers.get(servername)
		
		log.info("Server %s :: Executting Client Action Park: %s from %s..." % (servername, channel, announce))
		server.ami.park(channel, announce, "") \
			.addErrback(self._onAmiCommandFailure, servername, "Error Executting Client Action Transfer: %s from %s" % (channel, announce))

	def clientAction_CliCommand(self, session, action):
		servername  = action['server'][0]
		command     = action['command'][0]
		
		server = self.servers.get(servername)
		def _onResponse(response):
			self.http._addUpdate(servername = servername, sessid = session.uid, action = "CliResponse", response = response)
		
		log.info("Server %s :: Executting Client Action CLI Command: %s..." % (servername, command))
		server.ami.command(command) \
			.addCallbacks(_onResponse, self._onAmiCommandFailure, \
			errbackArgs = (servername, "Error Executting Client Action CLI Command '%s'" % command))
		
	def clientAction_RequestInfo(self, session, action):
		servername  = action['server'][0]
		command     = action['command'][0]
		
		server = self.servers.get(servername)
		def _onResponse(response):
			self.http._addUpdate(servername = servername, sessid = session.uid, action = "RequestInfoResponse", response = response)
			
		log.info("Server %s :: Executting Client Action Request Info: %s..." % (servername, command))
		server.ami.command(command) \
			.addCallbacks(_onResponse, self._onAmiCommandFailure, \
			errbackArgs = (servername, "Error Executting Client Action Request Info '%s'" % command))
			
	def clientAction_Hangup(self, session, action):
		servername  = action['server'][0]
		channel     = action['channel'][0]
		
		log.info("Server %s :: Executting Client Action Hangup: %s..." % (servername, channel))
		server = self.servers.get(servername)
		server.ami.hangup(channel) \
			.addErrback(self._onAmiCommandFailure, servername, "Error Executting Hangup on Channel: %s" % channel)
			
	def clientAction_MonitorStart(self, session, action):
		servername  = action['server'][0]
		channel     = action['channel'][0]
		
		log.info("Server %s :: Executting Client Action Monitor Start: %s..." % (servername, channel))
		server = self.servers.get(servername)
		server.ami.monitor(channel, "", "", 1) \
			.addErrback(self._onAmiCommandFailure, servername, "Error Executting Monitor Start on Channel: %s" % channel)
			
	def clientAction_MonitorStop(self, session, action):
		servername  = action['server'][0]
		channel     = action['channel'][0]
		
		log.info("Server %s :: Executting Client Action Monitor Stop: %s..." % (servername, channel))
		server = self.servers.get(servername)
		server.ami.sendDeferred({'action': 'StopMonitor', 'channel': channel}) \
			.addCallback(server.ami.errorUnlessResponse) \
			.addErrback(self._onAmiCommandFailure, servername, "Error Executting Monitor Stop on Channel: %s" % channel)
			
	def clientAction_QueueMemberPause(self, session, action):
		servername = action['server'][0]
		queue      = action['queue'][0]
		location   = action['location'][0]
		
		log.info("Server %s :: Executting Client Action Queue Member Pause: %s -> %s..." % (servername, queue, location))
		server = self.servers.get(servername)
		server.ami.queuePause(queue, location, True) \
			.addErrback(self._onAmiCommandFailure, servername, "Error Executting Queue Member Pause: %s -> %s" % (queue, location))
			
	def clientAction_QueueMemberUnpause(self, session, action):
		servername = action['server'][0]
		queue      = action['queue'][0]
		location   = action['location'][0]
		
		log.info("Server %s :: Executting Client Action Queue Member Unpause: %s -> %s..." % (servername, queue, location))
		server = self.servers.get(servername)
		server.ami.queuePause(queue, location, False) \
			.addErrback(self._onAmiCommandFailure, servername, "Error Executting Queue Member Unpause: %s -> %s" % (queue, location))
			
	def clientAction_QueueMemberAdd(self, session, action):
		servername = action['server'][0]
		queue      = action['queue'][0]
		location   = action['location'][0]
		membername = location
		
		tech, peer = location.split('/')
		peer       = self.servers.get(servername).status.peers.get(tech).get(peer)
		if peer.callerid:
			membername = peer.callerid
		
		log.info("Server %s :: Executting Client Action Queue Member Add: %s -> %s..." % (servername, queue, location))
		server = self.servers.get(servername)
		server.ami.sendDeferred({'action': 'QueueAdd', 'queue': queue, 'interface': location, 'membername': membername}) \
			.addCallback(server.ami.errorUnlessResponse) \
			.addErrback(self._onAmiCommandFailure, servername, "Error Executting Queue Member Add: %s -> %s" % (queue, location))
			
	def clientAction_QueueMemberRemove(self, session, action):
		servername = action['server'][0]
		queue      = action['queue'][0]
		location   = action['location'][0]
		
		log.info("Server %s :: Executting Client Action Queue Member Remove: %s -> %s..." % (servername, queue, location))
		server = self.servers.get(servername)
		server.ami.queueRemove(queue, location) \
			.addErrback(self._onAmiCommandFailure, servername, "Error Executting Queue Member Remove: %s -> %s" % (queue, location))
			
	def clientAction_MeetmeKick(self, session, action):
		servername = action['server'][0]
		meetme     = action['meetme'][0]
		usernum    = action['usernum'][0]
		
		log.info("Server %s :: Executting Client Action Meetme Kick: %s -> %s..." % (servername, meetme, usernum))
		server = self.servers.get(servername)
		server.ami.command("meetme kick %s %s" % (meetme, usernum)) \
			.addErrback(self._onAmiCommandFailure, servername, "Error Executting Client Action Meetme Kick: %s -> %s..." % (meetme, usernum))
		
	
	##
	## Event Handlers
	##
	def handlerEventReload(self, ami, event):
		log.debug("Server %s :: Processing Event Reload..." % ami.servername)
		
		server = self.servers.get(ami.servername)
		if time.time() - server.lastReload > 5:
			server.lastReload = time.time()
			self.__requestAsteriskConfig(ami.servername)
		
	def handlerEventChannelReload(self, ami, event):
		log.debug("Server %s :: Processing Event ChannelReload..." % ami.servername)
		
		server = self.servers.get(ami.servername)
		if time.time() - server.lastReload > 5:
			server.lastReload = time.time()
			self.__requestAsteriskConfig(ami.servername)
		
	def handlerEventPeerEntry(self, ami, event):
		log.debug("Server %s :: Processing Event PeerEntry..." % ami.servername)
		server      = self.servers.get(ami.servername)
		status      = event.get('status')
		channeltype = event.get('channeltype')
		objectname  = event.get('objectname').split('/')[0]
		time        = -1
		
		reTime = re.compile("([0-9]+)\s+ms")
		gTime  = reTime.search(status)
		if gTime:
			time = int(gTime.group(1))
		
		if status.startswith('OK'):
			status = 'Registered'
		elif status.find('(') != -1:
			status = status[0:status.find('(')]
			
		user = '%s/%s' % (channeltype, objectname)
		
		if (self.displayUsersDefault and not server.displayUsers.has_key(user)) or (not self.displayUsersDefault and server.displayUsers.has_key(user)):
			self._createPeer(
				ami.servername,
				channeltype = channeltype,
				peername    = objectname,
				status      = status,
				time        = time
			)
		else:
			user = None
			
		if user:
			type    = ['peer', 'user'][channeltype == 'Skype']
			command = '%s show %s %s' % (channeltype.lower(), type, objectname)
			
			def onShowPeer(response):
				log.debug("Server %s :: Processing %s..." % (ami.servername, command))
				result    = '\n'.join(response)
				callerid  = None
				context   = None
				variables = []
				
				try:
					callerid = re.compile("['\"]").sub("", re.search('Callerid[\s]+:[\s](.*)\n', result).group(1))
					if callerid == ' <>':
						callerid = '--'
				except:
					callerid = '--'
				
				try:
					context = re.search('Context[\s]+:[\s](.*)\n', result).group(1)
				except:
					context = server.default_context
				
				start = False
				for line in response:
					if re.search('Variables[\s+]', line):
						start = True
						continue
					if start:
						gVar = re.search('^[\s]+([^=]*)=(.*)', line)
						if gVar:
							variables.append("%s=%s" % (gVar.group(1).strip(), gVar.group(2).strip()))
				
				self._updatePeer(
					ami.servername, 
					channeltype = channeltype, 
					peername    = objectname,
					callerid    = [callerid, objectname][callerid == "--"],
					context     = context,
					variables   = variables
				)
					
			server.ami.command(command) \
				.addCallbacks(onShowPeer, self._onAmiCommandFailure, \
					errbackArgs = (ami.servername, "Error Executting Command '%s'" % command))
				
	def handlerEventPeerStatus(self, ami, event):
		log.debug("Server %s :: Processing Event PeerStatus..." % ami.servername)
		channel = event.get('peer')
		status  = event.get('peerstatus')
		time    = event.get('time')
		channeltype, peername = channel.split('/', 1)
		
		if time:
			self._updatePeer(ami.servername, channeltype = channeltype, peername = peername, status = status, time = time)
		else:
			self._updatePeer(ami.servername, channeltype = channeltype, peername = peername, status = status)
		
	def handlerEventNewchannel(self, ami, event):
		log.debug("Server %s :: Processing Event Newchannel..." % ami.servername)
		server   = self.servers.get(ami.servername)
		uniqueid = event.get('uniqueid')
		channel  = event.get('channel')
		
		self._createChannel(
			ami.servername,
			uniqueid     = uniqueid,
			channel      = channel,
			state        = event.get('channelstatedesc', event.get('state')),
			calleridnum  = event.get('calleridnum'),
			calleridname = event.get('calleridname'),
			_log         = "-- Newchannel"
		)
		
	def handlerEventNewstate(self, ami, event):
		log.debug("Server %s :: Processing Event Newstate..." % ami.servername)
		server       = self.servers.get(ami.servername)		
		uniqueid     = event.get('uniqueid')
		channel      = event.get('channel')
		state        = event.get('channelstatedesc', event.get('state'))
		calleridnum  = event.get('calleridnum', event.get('callerid'))
		calleridname = event.get('calleridname')
		
		self._updateChannel(
			ami.servername,
			uniqueid     = uniqueid,
			channel      = channel,
			state        = state,
			calleridnum  = calleridnum,
			calleridname = calleridname,
			_log         = "-- State changed to %s" % state
		)
		
	def handlerEventRename(self, ami, event):
		log.debug("Server %s :: Processing Event Rename..." % ami.servername)
		uniqueid = event.get('uniqueid')
		channel  = event.get('channel')
		newname  = event.get('newname')
		
		self._updateChannel(ami.servername, uniqueid = uniqueid, channel = newname, _log = "Channel %s renamed to %s" % (channel, newname))
		bridgekey = self._locateBridge(ami.servername, uniqueid = uniqueid)
		if bridgekey:
			if uniqueid == bridgekey[0]:
				self._updateBridge(ami.servername, uniqueid = bridgekey[0], bridgeduniqueid = bridgekey[1], channel = newname, _log = "Channel %s renamed to %s" % (channel, newname))
			else:
				self._updateBridge(ami.servername, uniqueid = bridgekey[0], bridgeduniqueid = bridgekey[1], bridgedchannel = newname, _log = "Channel %s renamed to %s" % (channel, newname))
				
	def handlerEventMasquerade(self, ami, event):
		log.debug("Server %s :: Processing Event Masquerade..." % ami.servername)
		server        = self.servers.get(ami.servername)	
		cloneUniqueid = event.get('cloneuniqueid')
		
		if not cloneUniqueid:
			log.warn("Server %s :: Detected BUG on Asterisk. Masquerade Event does not have cloneuniqueid and originaluniqueid properties. " % ami.servername \
				+ "See https://issues.asterisk.org/view.php?id=16555 for more informations.")
			return
		
		clone = server.status.channels.get(cloneUniqueid)
		self._createChannel(
			ami.servername,
			uniqueid     = event.get('originaluniqueid'),
			channel      = event.get('original'),
			state        = event.get('originalstate'),
			calleridnum  = clone.calleridnum,
			calleridname = clone.calleridname,
			_log         = "-- Newchannel (Masquerade)"
		)
		
	def handlerEventNewcallerid(self, ami, event):
		log.debug("Server %s :: Processing Event Newcallerid..." % ami.servername)
		server       = self.servers.get(ami.servername)	
		uniqueid     = event.get('uniqueid')
		channel      = event.get('channel')
		calleridnum  = event.get('calleridnum', event.get('callerid'))
		calleridname = event.get('calleridname')
		
		self._updateChannel(
			ami.servername,
			uniqueid     = uniqueid,
			channel      = channel,
			calleridnum  = calleridnum,
			calleridname = calleridname,
			_log         = "-- Callerid updated to '%s <%s>'" % (calleridname, calleridnum)
		)
		bridgekey = self._locateBridge(ami.servername, uniqueid = uniqueid)
		if bridgekey:
			self._updateBridge(ami.servername, uniqueid = bridgekey[0], bridgeduniqueid = bridgekey[1], _log = "-- Touching Bridge...")
		
	def handlerEventHangup(self, ami, event):
		log.debug("Server %s :: Processing Event Hangup..." % ami.servername)
		server   = self.servers.get(ami.servername)
		uniqueid = event.get('uniqueid')
		channel  = event.get('channel')
		
		self._removeChannel(
			ami.servername,
			uniqueid = uniqueid,
			channel  = channel,
			_log     = "-- Hangup"
		)
		
		# Detect QueueCall
		queueCall = server.status.queueCalls.get(uniqueid)
		if queueCall:
			log.debug("Server %s :: Queue update, call hangup: %s -> %s", ami.servername, queueCall.client.get('queue'), uniqueid)
			del server.status.queueCalls[uniqueid]
			if queueCall.member:
				self.http._addUpdate(servername = ami.servername, action = "RemoveQueueCall", uniqueid = uniqueid, queue = queueCall.client.get('queue'), location = queueCall.member.get('location'))
				queue = server.status.queues.get(queueCall.client.get('queue'))
				queue.completed += 1
				self.http._addUpdate(servername = ami.servername, subaction = 'Update', **queue.__dict__.copy())
			if logging.DUMPOBJECTS:
				log.debug("Object Dump:%s", queueCall)
		
	def handlerEventDial(self, ami, event):
		log.debug("Server %s :: Processing Event Dial..." % ami.servername)
		server   = self.servers.get(ami.servername)
		subevent = event.get('subevent', "begin")
		if subevent.lower() == 'begin':
			log.debug("Server %s :: Processing Event Dial -> SubEvent Begin..." % ami.servername)
			self._createBridge(
				ami.servername,
				uniqueid        = event.get('uniqueid', event.get('srcuniqueid')),
				channel         = event.get('channel', event.get('source')),
				bridgeduniqueid = event.get('destuniqueid'),
				bridgedchannel  = event.get('destination'),
				status          = 'Dial',
				dialtime        = int(time.time()),
				#starttime       = 0,
				linktime        = 0,
				_log            = '-- Dial Begin'
			)
		elif subevent.lower() == 'end':
			log.debug("Server %s :: Processing Event Dial -> SubEvent End..." % ami.servername)
			bridgekey = self._locateBridge(ami.servername, uniqueid = event.get('uniqueid'))
			if bridgekey:
				self._removeBridge(ami.servername, uniqueid = bridgekey[0], bridgeduniqueid = bridgekey[1], _log = "-- Dial End")
				
			# Detect QueueCall
			uniqueid = event.get('uniqueid', event.get('srcuniqueid'))
			queueCall = server.status.queueCalls.get(uniqueid)
			if queueCall:
				queueCall.link = False
				if queueCall.member:
					log.debug("Server %s :: Queue update, client -> member call unlink: %s -> %s -> %s", ami.servername, queueCall.client.get('queue'), uniqueid, queueCall.member.get('location'))
					self.http._addUpdate(servername = ami.servername, action = "RemoveQueueCall", uniqueid = uniqueid, queue = queueCall.client.get('queue'), location = queueCall.member.get('location'))
					if logging.DUMPOBJECTS:
						log.debug("Object Dump:%s", queueCall)
		else:
			log.warning("Server %s :: Unhandled Dial SubEvent %s", ami.servername, subevent)
	
	def handlerEventLink(self, ami, event):
		log.debug("Server %s :: Processing Event Link..." % ami.servername)
		server          = self.servers.get(ami.servername)
		uniqueid        = event.get('uniqueid1')
		channel         = event.get('channel1')
		bridgeduniqueid = event.get('uniqueid2')
		bridgedchannel  = event.get('channel2')
		callerid        = event.get('callerid1')
		bridgedcallerid = event.get('callerid2')
		
		bridgekey = self._locateBridge(ami.servername, uniqueid = uniqueid, bridgeduniqueid = bridgeduniqueid)
		if bridgekey:
			linktime = server.status.bridges.get(bridgekey).linktime
			self._updateBridge(
				ami.servername,
				uniqueid        = uniqueid, 
				bridgeduniqueid = bridgeduniqueid,
				status          = 'Link',
				linktime        = [linktime, time.time()][linktime == 0],
				_log            = "-- Status changed to Link"
			)
		else:
			self._createBridge(
				ami.servername,
				uniqueid        = uniqueid, 
				bridgeduniqueid = bridgeduniqueid,
				channel         = channel,
				bridgedchannel  = bridgedchannel,
				status          = 'Link',
				linktime        = int(time.time()),
				_log            = "-- Link"
			)
		
		# Detect QueueCall
		queueCall = server.status.queueCalls.get(uniqueid)
		if queueCall:
			queuename = queueCall.client.get('queue')
			location  = bridgedchannel[:bridgedchannel.rfind('-')]
			member    = server.status.queueMembers.get((queuename, location))
			if member:
				log.debug("Server %s :: Queue update, client -> member call link: %s -> %s -> %s", ami.servername, queuename, uniqueid, location)
				queueCall.member  = member.__dict__
				queueCall.link    = True
				queueCall.seconds = int(time.time()) - int(queueCall.starttime) 
				self.http._addUpdate(servername = ami.servername, **queueCall.__dict__.copy())
				if logging.DUMPOBJECTS:
					log.debug("Object Dump:%s", queueCall)
		
	def handlerEventUnlink(self, ami, event):
		log.debug("Server %s :: Processing Event Unlink..." % ami.servername)
		server          = self.servers.get(ami.servername)
		uniqueid        = event.get('uniqueid1')
		channel         = event.get('channel1')
		bridgeduniqueid = event.get('uniqueid2')
		bridgedchannel  = event.get('channel2')
		self._updateBridge(
			ami.servername, 
			uniqueid        = uniqueid, 
			bridgeduniqueid = bridgeduniqueid,
			channel         = channel,
			bridgedchannel  = bridgedchannel,
			status          = 'Unlink',
			_log            = "-- Status changed to Unlink"
		)
		
		# Detect QueueCall
		queueCall = server.status.queueCalls.get(uniqueid)
		if queueCall:
			queueCall.link = False
			if queueCall.member:
				log.debug("Server %s :: Queue update, client -> member call unlink: %s -> %s -> %s", ami.servername, queueCall.client.get('queue'), uniqueid, queueCall.member.get('location'))
				self.http._addUpdate(servername = ami.servername, action = "RemoveQueueCall", uniqueid = uniqueid, queue = queueCall.client.get('queue'), location = queueCall.member.get('location'))
				if logging.DUMPOBJECTS:
					log.debug("Object Dump:%s", queueCall)
	
	def handlerEventBridge(self, ami, event):
		log.debug("Server %s :: Processing Event Bridge..." % ami.servername)
		self.handlerEventLink(ami, event)
	
	# Meetme Events
	def handlerEventMeetmeJoin(self, ami, event):
		log.debug("Server %s :: Processing Event MeetmeJoin..." % ami.servername)
		meetme = event.get("meetme")
		
		self._updateMeetme(
			ami.servername,
			meetme  = meetme,
			addUser = {
				'uniqueid'     : event.get('uniqueid'), 
				'channel'      : event.get('channel'),
				'usernum'      : event.get("usernum"), 
				'calleridnum'  : event.get("calleridnum"), 
				'calleridname' : event.get("calleridname"),
			}  
		)
		
	# Meetme Events
	def handlerEventMeetmeLeave(self, ami, event):
		log.debug("Server %s :: Processing Event MeetmeLeave..." % ami.servername)
		meetme = event.get("meetme")
		
		self._updateMeetme(
			ami.servername,
			meetme  = meetme,
			removeUser = {
				'uniqueid'     : event.get('uniqueid'), 
				'channel'      : event.get('channel'),
				'usernum'      : event.get("usernum"), 
				'calleridnum'  : event.get("calleridnum"), 
				'calleridname' : event.get("calleridname"),
			}  
		)
		
	# Parked Calls Events
	def handlerEventParkedCall(self, ami, event):
		log.debug("Server %s :: Processing Event ParkedCall..." % ami.servername)
		self._createParkedCall(ami.servername, **event)
		
	def handlerEventUnParkedCall(self, ami, event):
		log.debug("Server %s :: Processing Event UnParkedCall..." % ami.servername)
		self._removeParkedCall(ami.servername, _log = "(Unparked)", **event)
	
	def handlerEventParkedCallTimeOut(self, ami, event):
		log.debug("Server %s :: Processing Event ParkedCallTimeOut..." % ami.servername)
		self._removeParkedCall(ami.servername, _log = "(Timeout)", **event)
	
	def handlerEventParkedCallGiveUp(self, ami, event):
		log.debug("Server %s :: Processing Event ParkedCallGiveUp..." % ami.servername)
		self._removeParkedCall(ami.servername, _log = "(Giveup)", **event)
		
	# Queue Events
	def handlerEventQueueMemberAdded(self, ami, event):
		log.debug("Server %s :: Processing Event QueueMemberAdded..." % ami.servername)
		self._updateQueue(ami.servername, **event)
	
	def handlerEventQueueMemberRemoved(self, ami, event):
		log.debug("Server %s :: Processing Event QueueMemberRemoved..." % ami.servername)
		self._updateQueue(ami.servername, **event)
	
	def handlerEventJoin(self, ami, event):
		log.debug("Server %s :: Processing Event Join..." % ami.servername)
		self._updateQueue(ami.servername, **event)
		
	def handlerEventLeave(self, ami, event):
		log.debug("Server %s :: Processing Event Leave..." % ami.servername)
		self._updateQueue(ami.servername, **event)
		
	def handlerEventQueueCallerAbandon(self, ami, event):
		log.debug("Server %s :: Processing Event QueueCallerAbandon..." % ami.servername)
		self._updateQueue(ami.servername, **event)
		
	def handlerEventQueueMemberStatus(self, ami, event):
		log.debug("Server %s :: Processing Event QueueMemberStatus..." % ami.servername)
		self._updateQueue(ami.servername, **event)
		
	def handlerEventQueueMemberPaused(self, ami, event):
		log.debug("Server %s :: Processing Event QueueMemberPaused..." % ami.servername)
		
		server   = self.servers.get(ami.servername)
		queue    = event.get('queue')
		location = event.get('location')
		member   = server.status.queueMembers.get((queue, location))
		
		event['callstaken'] = member.callstaken
		event['lastcall']   = member.lastcall
		event['penalty']    = member.penalty
		event['status']     = member.status
		
		self._updateQueue(ami.servername, **event)
	
	## Monitor
	def handlerEventMonitorStart(self, ami, event):
		log.debug("Server %s :: Processing Event MonitorStart..." % ami.servername)
		self._updateChannel(ami.servername, uniqueid = event.get('uniqueid'), channel = event.get('channel'), monitor = True, _log = "-- Monitor Started")
	
	def handlerEventMonitorStop(self, ami, event):
		log.debug("Server %s :: Processing Event MonitorStop..." % ami.servername)
		self._updateChannel(ami.servername, uniqueid = event.get('uniqueid'), channel = event.get('channel'), monitor = False, _log = "-- Monitor Stopped")
	
	# Khomp Events
	def handlerEventAntennaLevel(self, ami, event):
		log.debug("Server %s :: Processing Event AntennaLevel..." % ami.servername)
		channel = event.get('channel')
		signal  = event.get('signal')
		channeltype, peername = channel.split('/', 1)
		self._updatePeer(ami.servername, channeltype = channeltype, peername = peername, status = 'Signal: %s' % signal)
		
##
## Daemonizer
##
#MONAST_PID_FILE = '%s/.monast.pid' % sys.argv[0].rsplit('/', 1)[0]
MONAST_PID_FILE = '/var/run/monast.pid'
def createDaemon():
	if os.fork() == 0:
		os.setsid()
		if os.fork() == 0:
			os.chdir(os.getcwd())
			os.umask(0)
		else:
			os._exit(0)
	else:
		os._exit(0)
	
	pid = os.getpid()
	print '\nMonast daemonized with pid %s' % pid
	f = open(MONAST_PID_FILE, 'w')
	f.write('%s' % pid)
	f.close()

##
## Main
##
if __name__ == '__main__':

	opt = optparse.OptionParser()
	opt.add_option('--config',
		dest    = "configFile",
		default = '/etc/monast.conf',
		help    = "use this config file instead of /etc/monast.conf"
	)
	opt.add_option('--info',
		dest   = "info",
		action = "store_true",
		help   = "display INFO messages"
	)
	opt.add_option('--debug',
		dest   = "debug",
		action = "store_true",
		help   = "display DEBUG messages"
	)
	opt.add_option('--debug-ami',
		dest = "debugAMI",
		action = "store_true",
		help = "display DEBUG messages for AMI Factory"
	)
	opt.add_option('--dump-objects',
		dest   = "dump_objects",
		action = "store_true",
		help   = "display DEBUG messages"
	)
	opt.add_option('--colored',
		dest   = "colored",
		action = "store_true",
		help   = "display colored log messages"
	)
	opt.add_option('--daemon',
		dest   = "daemon",
		action = "store_true",
		help   = "deamonize (fork in background)"
	)
	opt.add_option('--logfile',
		dest    = "logfile",
		default = "/var/log/monast.log",
		help    = "use this log file instead of /var/log/monast.log"
	)
	opt.add_option('--stop',
		dest   = "stop",
		action = "store_true",
		help   = "stop Confast (only in daemon mode)"
	)
	
	(options, args) = opt.parse_args()

	if options.stop:
		if os.path.exists(CONFAST_PID_FILE):
			pid = open(CONFAST_PID_FILE, 'r').read()
			os.unlink(CONFAST_PID_FILE)
			os.popen("kill -TERM %d" % int(pid))
			print "Confast stopped..."
			sys.exit(0)
		else:
			print "Confast is not running as daemon..."
			sys.exit(1)
		sys.exit(2)
	
	if options.daemon:
		createDaemon()
		
	if options.info:
		logging.getLogger("").setLevel(logging.INFO)
	
	if options.debug:
		logging.getLogger("").setLevel(logging.DEBUG)
		#logging.FORMAT = "[%(asctime)s] %(levelname)-8s :: [%(module)s.%(funcName)s] :: %(message)s"
		
	if options.debugAMI:
		manager.log.setLevel(logging.DEBUG)
	else:
		manager.log.setLevel(logging.WARNING)
		
	if options.dump_objects:
		logging.DUMPOBJECTS = True
		
	if options.colored:
		logging.COLORED = True
		logging.FORMAT  = "[%(asctime)s] %(levelname)-19s :: %(message)s"
		#if options.debug:
		#	logging.FORMAT = "[%(asctime)s] %(levelname)-19s :: [%(module)s.%(funcName)s] :: %(message)s"
		
	_colorFormatter = ColorFormatter(logging.FORMAT, '%a %b %d %H:%M:%S %Y')
	_logHandler     = None
	if options.daemon:
		logfile = options.logfile
		if not logfile:
			logfile = '/var/log/monast.log'
		_logHandler = logging.FileHandler(logfile)
	else:
		_logHandler = logging.StreamHandler(sys.stdout)
	_logHandler.setFormatter(_colorFormatter)
	logging.getLogger("").addHandler(_logHandler)
	
	log = logging.getLogger("Monast")
	
	if not os.path.exists(options.configFile):
		print '  Config file "%s" not found.' % options.configFile
		print '  Run "%s --help" for help.' % sys.argv[0]
		sys.exit(1)
		
	monast = Monast(options.configFile)
	reactor.run()
	
	_logHandler.close()
	