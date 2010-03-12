#!/usr/bin/python -u

# Copyright (c) 2008, Diego Aguirre
# All rights reserved.
# 
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
# 
#     * Redistributions of source code must retain the above copyright notice, 
#       this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright notice, 
#       this list of conditions and the following disclaimer in the documentation 
#       and/or other materials provided with the distribution.
#     * Neither the name of the DagMoller nor the names of its contributors
#       may be used to endorse or promote products derived from this software 
#       without specific prior written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED 
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
# IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, 
# INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, 
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, 
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF 
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE 
# OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED 
# OF THE POSSIBILITY OF SUCH DAMAGE.

import os
import re
import sys

START_PATH = os.getcwd()
sys.path.append('%s/amapi' % sys.path[0])

import time
import traceback
import socket
import signal
import random
import Queue
import logging
import optparse

from AsteriskManager import AsteriskManagerFactory
from ConfigParser import SafeConfigParser, NoOptionError

from twisted.protocols import basic
from twisted.internet import protocol, reactor, task

import distutils.sysconfig
PYTHON_VERSION = distutils.sysconfig.get_python_version()

try:
	import json
except ImportError:
	import simplejson as json

MONAST_CALLERID = "MonAst WEB"

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

COLORS = {
	'black'  : 30,
	'red'    : 31,
	'green'  : 32,
	'yellow' : 33,
	'blue'   : 34,
	'magenta': 35,
	'cyan'   : 36,
	'white'  : 37
}

## Global Logger
logging.NOTICE = 60
logging.addLevelName(logging.NOTICE, "NOTICE")

LEVEL_COLORS = {
	logging.NOTICE   : 'white',
	logging.INFO     : 'yellow',
	logging.ERROR    : 'red',
	logging.WARNING  : 'magenta',
	logging.DEBUG    : 'cyan',
}

## deamonize
def createDaemon():
	if os.fork() == 0:
		os.setsid()
		if os.fork() == 0:
			os.chdir('/')
			os.umask(0)
		else:
			os._exit(0)
	else:
		os._exit(0)
	
	pid = os.getpid()
	print 'MonAst daemonized with pid %s' % pid
	f = open('/var/run/monast.pid', 'w')
	f.write('%s' % pid)
	f.close()
	

class ColorFormatter(logging.Formatter):
	def __init__(self, fmt = None, datefmt = None):
		logging.Formatter.__init__(self, fmt, datefmt)
		self.colored = hasattr(logging, 'COLORED')
	
	def color(self, levelno, msg):
		if self.colored:
			return '\033[%d;1m%s\033[0m' % (COLORS[LEVEL_COLORS[levelno]], msg)
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
	
		if float(PYTHON_VERSION) >= 2.5:
			record.funcName = self.color(record.levelno, record.funcName)
			
		if record.exc_info:
			record.exc_text = self.color(record.levelno, '>> %s' % self.formatException(record.exc_info).replace('\n', '\n>> '))
		
		return logging.Formatter.format(self, record)


class MyConfigParser(SafeConfigParser):
	def optionxform(self, optionstr):
		return optionstr


class SimpleAmiAuthenticator(basic.LineOnlyReceiver):
	buffer     = []
	amiVersion = None
	onSuccess  = None
	onFailure  = None
	server     = None
	username   = None
	password   = None
	
	def __init__(self, *args, **kwargs):
		self.server    = kwargs['server']
		self.username  = kwargs['username']
		self.password  = kwargs['password']
		self.onSuccess = kwargs['onSuccess']
		self.onFailure = kwargs['onFailure']
		log.info("SimpleAmiAuthenticator.__init__ :: Trying to authenticate user %s on server %s" % (self.username, self.server)) 
		
	def connectionMade(self):
		self._sendLine('Action: Login')
		self._sendLine('Username: %s' % self.username)
		self._sendLine('Secret: %s' % self.password)
		self._sendLine('')
		
	def _sendLine(self, line):
		self.sendLine(line.encode('UTF-8'))
	
	def lineReceived(self, line):
		self.buffer.append(line)
		if not line.strip():
			self.processBuffer()
			
	def processBuffer(self):
		message = {}
		while self.buffer:
			line = self.buffer.pop(0)
			line = line.strip()
			if line:
				if line.endswith('--END COMMAND--'):
					message.setdefault( ' ', []).extend([l for l in line.split('\n') if (l and l != '--END COMMAND--')])
				else:
					if line.startswith('Asterisk Call Manager'):
						self.amiVersion = line[len('Asterisk Call Manager')+1:].strip()
					else:
						try:
							key, value = line.split(':', 1)
						except:
							log.warning("SimpleAmiAuthenticator.procesBuffer :: Improperly formatted line received and ignored: %r" % (line))
						else:
							message[key.strip()] = value.strip()
							
		Response = message.get('Response', None)
		Message  = message.get('Message', None)
		
		if Response == 'Success' and Message == 'Authentication accepted':
			log.info("SimpleAmiAuthenticator.processBuffer :: Authentication accepted for user %s on server %s" % (self.username, self.server))
			self._sendLine('Action: Events')
			self._sendLine('EventMask: off')
			self._sendLine('')
			self._sendLine('Action: Command')
			self._sendLine('Command: manager show user %s' % self.username)
			self._sendLine('')
			return
		
		if Response == 'Error' and Message == 'Authentication failed':
			log.info("SimpleAmiAuthenticator.processBuffer :: Authentication failed for user %s on server %s" % (self.username, self.server))
			self.transport.loseConnection()
			self._onFailure((self.server, False, []))
			return
		
		if Response == 'Follows':
			for line in message[' ']:
				line = line.strip()
				p = re.search('(write|write perm): (.*)', line)
				if p:
					auth = (self.server, True, p.group(2).split(','))
					break
			self._sendLine('Action: Logoff')
			self._sendLine('')
			self.transport.loseConnection()
			self._onSuccess(auth)
		
	def _onSuccess(self, auth):
		if self.onSuccess:
			self.onSuccess(auth)
			
	def _onFailure(self, auth):
		if self.onFailure:
			self.onFailure(auth)


class MonAstProtocol(basic.LineOnlyReceiver):
	
	host    = None
	port    = None
	session = None
	closed  = False
	
	def connectionMade(self):
		peer = self.transport.getPeer()
		self.host = peer.host
		self.port = peer.port
		log.info("MonAstProtocol.connectionMade :: New Client from %s:%s" % (self.host, self.port))
		self.factory.pclients.append(self)
		
	def connectionLost(self, reason):
		if not self.closed:
			log.error("MonAstProtocol.connectionLost :: Connection Lost from %s:%s" % (self.host, self.port))
		self.factory.pclients.remove(self)
	
	def closeClient(self):
		log.info("MonAstProtocol.closeClient :: Closing Connection from %s:%s" % (self.host, self.port))
		self.closed = True
		self.transport.loseConnection()
	
	def lineReceived(self, line):
		log.debug("MonAstProtocol.lineReceived (%s:%s) :: Received: %s" % (self.host, self.port, line))
		if line.upper().startswith('SESSION: '):
			self.session = line[9:]
		self.factory.processClientMessage(self, line)
		
	def sendMessage(self, line):
		log.debug("MonAstProtocol.sendMessage (%s:%s) :: Sending %s" % (self.host, self.port, line))
		self.sendLine(line)
		

class MonAst(protocol.ServerFactory):
	
	##
	## Internal Params
	##
	
	protocol = MonAstProtocol
	pclients = []
	
	running         = True
	reloading       = False
	
	configFile      = None
	
	AMI             = None
	amiAuthCheck    = {}
	
	bindHost        = None
	bindPort        = None
	
	userDisplay     = {}
	queuesDisplay   = {}
	
	authRequired   = False
	
	servers        = {}
	
	clients        = {}
	clientsAMI     = {}
	
	clientSocks    = {}
	clientQueues   = {}
	parked         = {}
	meetme         = {}
	calls          = {}
	channels       = {}
	monitoredUsers = {}
	queues         = {}

	isParkedStatus = {}
	parkedStatus   = {}
	
	channelStatus = {}
	
	queueMemberStatus = {}
	queueClientStatus = {}
	
	queueMemberCalls  = {}
	queueMemberPaused = {}
	
	queueStatusFirst = {}
	queueStatusOrder = {}
	
	getMeetmeAndParkStatus = {}
	
	sortby = 'callerid'
	
	## My Actions
	actions = {}
		
	##
	## Class Initialization
	##
	def __init__(self, configFile):
		
		log.log(logging.NOTICE, 'MonAst :: Initializing...')
		
		## My Actions
		self.actions = {
			'OriginateCall'      : ('originate', self.clientOriginateCall),
			'OriginateDial'      : ('originate', self.clientOriginateDial),
			'HangupChannel'      : ('originate', self.clientHangupChannel),
			'MonitorChannel'     : ('originate', self.clientMonitorChannel),
			'MonitorStop'        : ('originate', self.clientMonitorStop),
			'TransferCall'       : ('originate', self.clientTransferCall),
			'ParkCall'           : ('originate', self.clientParkCall),
			'MeetmeKick'         : ('originate', self.clientMeetmeKick),
			'ParkedHangup'       : ('originate', self.clientParkedHangup),
			'AddQueueMember'     : ('agent', self.clientAddQueueMember),
			'RemoveQueueMember'  : ('agent', self.clientRemoveQueueMember),
			'PauseQueueMember'   : ('agent', self.clientPauseQueueMember),
			'UnpauseQueueMember' : ('agent', self.clientUnpauseQueueMember),
			'SkypeLogin'         : ('originate', self.clientSkypeLogin),
			'SkypeLogout'        : ('originate', self.clientSkypeLogout),
			'CliCommand'         : ('command', self.clientCliCommand)
		}
		
		self._taskClientQueueRemover = task.LoopingCall(self.taskClientQueueRemover)
		self._taskCheckStatus        = task.LoopingCall(self.taskCheckStatus)
		
		self.configFile = configFile
		self.parseConfig()
		
	
	def startFactory(self):
		
		self._taskClientQueueRemover.start(60, False)
		self._taskCheckStatus.start(60, False)
	
	
	def stopFactory(self):
		pass
		#self._taskClientQueueRemover.stop()
		#self._taskCheckStatus.stop()

	
	def parseConfig(self):
		
		log.log(logging.NOTICE, 'MonAst.parseConfig :: Parsing config')
		
		cp = MyConfigParser()
		cp.read(self.configFile)
		
		servers = [s for s in cp.sections() if s.startswith('server:')]
		for server in servers:
			name = server.replace('server:', '').strip()
			self.servers[name] = {
				'hostname'         : cp.get(server, 'hostname'),
				'hostport'         : int(cp.get(server, 'hostport')),
				'username'         : cp.get(server, 'username'),
				'password'         : cp.get(server, 'password'),
				'default_context'  : cp.get(server, 'default_context'),
				'transfer_context' : cp.get(server, 'transfer_context'),
				'meetme_context'   : cp.get(server, 'meetme_context'),
				'meetme_prefix'    : cp.get(server, 'meetme_prefix')
			}
			
			self.queueMemberStatus[name]      = {}
			self.queueClientStatus[name]      = {}
			self.queueStatusOrder[name]       = []
			self.queueStatusFirst[name]       = False
			self.getMeetmeAndParkStatus[name] = False
		
		self.clearStatus()
		
		self.bindHost       = cp.get('global', 'bind_host')
		self.bindPort       = int(cp.get('global', 'bind_port'))
		
		if cp.get('global', 'auth_required') == 'true':
			self.authRequired = True
		
		## Authentication Users
		users = [s for s in cp.sections() if s.startswith('user:')]
		for user in users:
			try:
				username = user.replace('user:', '').strip() 
				self.clients[username] = {
					'secret'  : cp.get(user, 'secret'), 
					'servers' : {}
				}
				defaultRoles = [r.strip() for r in cp.get(user, 'roles').split(',')]
				userServers  = [s.strip() for s in cp.get(user, 'servers').split(',') if self.servers.has_key(s.strip())]
				if cp.get(user, 'servers').upper() == 'ALL':
					userServers = self.servers.keys()
				for server in userServers:
					try:
						roles = [r.strip() for r in cp.get(user, server).split(',')]
						self.clients[username]['servers'][server] = {'roles': roles}
					except:
						  self.clients[username]['servers'][server] = {'roles': defaultRoles}
			except:
				log.error("MonAst.__init__ :: Username %s has errors in config file!" % user)
		print self.clients
		## Peers
		try:
			self.sortby = cp.get('peers', 'sortby')
		except NoOptionError:
			self.sortby = 'callerid'
			log.error("No option 'sortby' in section: 'peers' of config file, sorting by CallerID")
		
		if cp.get('peers', 'default') == 'show':
			self.userDisplay['DEFAULT'] = True 
		else:
			self.userDisplay['DEFAULT'] = False
		
		for user, display in cp.items('peers'):
			if user in ('default', 'sortby'):
				continue
			server, user = user.split('/', 1)
			if not self.servers.has_key(server):
				continue
			if user.startswith('SIP') or user.startswith('IAX2'): 
				if (self.userDisplay['DEFAULT'] and display == 'hide') or (not self.userDisplay['DEFAULT'] and display == 'show'):
					self.userDisplay[server][user] = True
			
			if display.startswith('force'):
				tech, peer = user.split('/')
				Status = '--'
				if AST_TECH_STATES.has_key(tech):
					Status = AST_TECH_STATES[tech]
				
				tmp      = display.split(',')
				display  = tmp[0].strip()
				CallerID = '--'
				if len(tmp) == 2:
					CallerID = tmp[1].strip()
				
				self.monitoredUsers[server][user] = {
					'Channeltype': tech, 'Status': Status, 'Calls': 0, 'CallerID': CallerID, 'Context': self.servers[server]['default_context'], 'Variables': [], 'forced': True
				}
		
		## Queues
		if cp.get('queues', 'default') == 'show':
			self.queuesDisplay['DEFAULT'] = True
		else:
			self.queuesDisplay['DEFAULT'] = False
			
		for queue, display in cp.items('queues'):
			if queue in ('default'):
				continue
			server, queue = queue.split('/', 1)
			if not self.servers.has_key(server):
				continue
			if (self.queuesDisplay['DEFAULT'] and display == 'hide') or (not self.queuesDisplay['DEFAULT'] and display == 'show'):
				self.queuesDisplay[server][queue] = True
		
		self.AMI = AsteriskManagerFactory()
		
		for server in self.servers:
			s = self.servers[server]
			self.AMI.addServer(server, s['hostname'], s['hostport'], s['username'], s['password'])
		
		self.AMI.registerEventHandler('onAuthenticationAccepted', self.onAuthenticationAccepted)
		
		self.AMI.registerEventHandler('Reload', self.handlerReload)
		self.AMI.registerEventHandler('ChannelReload', self.handlerChannelReload)
		self.AMI.registerEventHandler('PeerEntry', self.handlerPeerEntry)
		self.AMI.registerEventHandler('PeerStatus', self.handlerPeerStatus)
		self.AMI.registerEventHandler('SkypeAccountStatus', self.handlerSkypeAccountStatus)
		self.AMI.registerEventHandler('BranchOnHook', self.handlerBranchOnHook)
		self.AMI.registerEventHandler('BranchOffHook', self.handlerBranchOffHook)
		self.AMI.registerEventHandler('Newchannel', self.handlerNewchannel)
		self.AMI.registerEventHandler('Newstate', self.handlerNewstate)
		self.AMI.registerEventHandler('Hangup', self.handlerHangup)
		self.AMI.registerEventHandler('Dial', self.handlerDial)
		self.AMI.registerEventHandler('Link', self.handlerLink)
		self.AMI.registerEventHandler('Bridge', self.handlerBridge)
		self.AMI.registerEventHandler('Unlink', self.handlerUnlink)
		self.AMI.registerEventHandler('Newcallerid', self.handlerNewcallerid)
		self.AMI.registerEventHandler('NewCallerid', self.handlerNewcallerid)
		self.AMI.registerEventHandler('Rename', self.handlerRename)
		self.AMI.registerEventHandler('MeetmeJoin', self.handlerMeetmeJoin)
		self.AMI.registerEventHandler('MeetmeLeave', self.handlerMeetmeLeave)
		self.AMI.registerEventHandler('ParkedCall', self.handlerParkedCall)
		self.AMI.registerEventHandler('UnParkedCall', self.handlerUnParkedCall)
		self.AMI.registerEventHandler('ParkedCallTimeOut', self.handlerParkedCallTimeOut)
		self.AMI.registerEventHandler('ParkedCallGiveUp', self.handlerParkedCallGiveUp)
		self.AMI.registerEventHandler('ParkedCallsComplete', self.handlerParkedCallsComplete)
		self.AMI.registerEventHandler('Status', self.handlerStatus)
		self.AMI.registerEventHandler('StatusComplete', self.handlerStatusComplete)
		self.AMI.registerEventHandler('QueueMemberAdded', self.handlerQueueMemberAdded)
		self.AMI.registerEventHandler('QueueMemberRemoved', self.handlerQueueMemberRemoved)
		self.AMI.registerEventHandler('Join', self.handlerJoin) # Queue Join
		self.AMI.registerEventHandler('Leave', self.handlerLeave) # Queue Leave
		self.AMI.registerEventHandler('QueueCallerAbandon', self.handlerQueueCallerAbandon)
		self.AMI.registerEventHandler('QueueParams', self.handlerQueueParams)
		self.AMI.registerEventHandler('QueueMember', self.handlerQueueMember)
		self.AMI.registerEventHandler('QueueMemberStatus', self.handlerQueueMemberStatus)
		self.AMI.registerEventHandler('QueueMemberPaused', self.handlerQueueMemberPaused)
		self.AMI.registerEventHandler('QueueEntry', self.handlerQueueEntry)
		self.AMI.registerEventHandler('QueueStatusComplete', self.handlerQueueStatusComplete)
		self.AMI.registerEventHandler('MonitorStart', self.handlerMonitorStart)
		self.AMI.registerEventHandler('MonitorStop', self.handlerMonitorStop)
		
		
	def processClientMessage(self, client, message):
		
		output  = []
		object  = {'Action': None, 'Session': None, 'Username': None}
		
		try:
			object = json.loads(message)
		except:
			pass
		
		isSession = message.upper().startswith('SESSION: ')
		action    = object['Action']
		
		if self.authRequired and action == 'Login':
			session  = object['Session']
			username = object['Username']
			secret   = object['Secret']
			if self.clients.has_key(username):
				if self.clients[username]['secret'] == secret:
					output.append('Authentication Success')
					self.clientQueues[session] = {'q': Queue.Queue(), 't': time.time(), 'servers': self.clients[username]['servers']}
					log.log(logging.NOTICE, 'MonAst.processClientMessage (%s:%s) :: New Authenticated (local) client session %s for %s' % (client.host, client.port, session, username))
				else:
					log.error('MonAst.processClientMessage (%s:%s) :: Invalid username or password for %s (local)' % (client.host, client.port, username))
					output.append('ERROR: Invalid user or secret')
			else:
				if not self.amiAuthCheck.has_key(session):
					self.clientCheckAmiAuth(session, username, secret)
					output.append('WAIT')
				else:
					ok = False
					responses = self.amiAuthCheck[session].items()
					for Server, Auth in responses:
						if Auth:
							ok = True
						else:
							ok = False
							break
						
					if ok:
						hasAuth = False
						for Server, Auth in responses:
							if Auth[0]:
								hasAuth = True
								if self.clientsAMI.has_key(username):
									self.clientsAMI[username]['servers'][Server] = {'roles': Auth[1]}
									if self.clientQueues.has_key(session):
										self.clientQueues[session]['servers'][Server] = self.clientsAMI[username]['servers'][Server]
									else:
										self.clientQueues[session] = {'q': Queue.Queue(), 't': time.time(), 'servers': {Server: self.clientsAMI[username]['servers'][Server]}}
								else:
									self.clientsAMI[username] = {'servers': {Server: {'roles': Auth[1]}}}
									self.clientQueues[session] = {'q': Queue.Queue(), 't': time.time(), 'servers': {Server: self.clientsAMI[username]['servers'][Server]}}
									
						if hasAuth:
							output.append('Authentication Success')
							log.log(logging.NOTICE, 'MonAst.processClientMessage (%s:%s) :: New Authenticated (manager) client session %s for user %s on servers %s' \
								% (client.host, client.port, session, username, ', '.join(self.clientQueues[session]['servers'].keys())))
						else:
							log.error('MonAst.processClientMessage (%s:%s) :: Can not authenticate username %s on any servers (manager)' % (client.host, client.port, username))
							output.append('ERROR: Invalid user or secret')
							
						del self.amiAuthCheck[session]
					else:
						output.append('WAIT')
		
		elif self.authRequired and action == 'Logout':
			try:
				del self.clientQueues[client.session]
				output.append('ERROR: Authentication Required')
			except:
				output.append('ERROR: Invalid session %s for user %s' % (client.session, username))
				log.error('MonAst.processClientMessage (%s:%s) :: Invalid session %s for user %s' % (client.host, client.port, client.session, username))
			
		elif isSession:
			session = message[9:]
			try:
				self.clientQueues[session]['t'] = time.time()
				output.append('OK')
			except KeyError:
				if self.authRequired:
					output.append('ERROR: Authentication Required')
				else:
					output.append('NEW SESSION')
					self.clientQueues[session] = {'q': Queue.Queue(), 't': time.time()}
					log.log(logging.NOTICE, 'MonAst.processClientMessage (%s:%s) :: New client session: %s' % (client.host, client.port, session))
		
		elif client.session and message.upper().startswith('GET STATUS'):
			serverlist = self.clientQueues[client.session]['servers'].keys()
			serverlist.sort()
			servers = None
			try:
				dummy, Server = message.split(': ')
				Server = Server.strip()
				if Server in serverlist:
					servers = [Server]
				elif Server.upper() == 'ALL':
					servers = serverlist
				else:
					servers = [serverlist[0]]				
			except:
				servers = [serverlist[0]]
			output = ['SERVERS: %s' % ', '.join(serverlist)]
			output += self.clientGetStatus(client.session, servers)
		
		elif client.session and message.upper().startswith('GET CHANGES'):
			servers = self.servers.keys()
			if self.clientQueues.has_key(client.session):
				servers = self.clientQueues[client.session]['servers'].keys()
			servers.sort()
			try:
				dummy, Server = message.split(': ')
				Server = Server.strip()
				if Server in servers:
					servers = [Server]
				elif Server.upper() == 'ALL':
					pass
				else:
					servers = [servers[0]]				
			except:
				servers = [servers[0]]
			output += self.clientGetChanges(client.session, servers)
		
		elif message.upper() == 'BYE':
			client.closeClient()

		elif self.actions.has_key(action):
			if self.checkPermission(object, self.actions[action][0]):
				self.actions[action][1](client.session, object)
			
		else:
			output.append('NO SESSION')
			
		## Send messages to client
		if len(output) > 0:
			for line in output:
				client.sendMessage(line)
		
		
	def taskClientQueueRemover(self):
		
		log.info('MonAst.taskClientQueueRemover :: Running...')
		if self.running:
			dels = []
			now = time.time()
			for session in self.clientQueues:
				past = self.clientQueues[session]['t']
				if int(now - past) > 600:
					dels.append(session)
			for session in dels:
				log.log(logging.NOTICE, 'MonAst.taskClientQueueRemover :: Removing dead client session: %s' % session)
				del self.clientQueues[session]
			
			
	def taskCheckStatus(self, **args):
		
		log.info('MonAst.taskCheckStatus :: Running...')
		if self.running:
			Server = args.get('Server', None)
			servers = self.servers.keys()
			if Server:
				servers = [Server]
			
			for Server in servers:
				log.info('MonAst.taskCheckStatus :: Requesting Status for Server %s...' % Server)
	
				self.channelStatus[Server] = []
				self.AMI.execute(Action = {'Action': 'Status'}, Server = Server) # generate Event: Status
					
				self.isParkedStatus[Server] = True
				self.parkedStatus[Server]   = []
				self.AMI.execute(Action = {'Action': 'ParkedCalls'}, Server = Server) # generate Event: ParkedCall
					
				for queue in self.queues[Server]:
					self.queueStatusOrder[Server].append(queue)
					self.queueMemberStatus[Server][queue] = []
					self.queueClientStatus[Server][queue] = []
					self.AMI.execute(Action = {'Action': 'QueueStatus', 'Queue': queue}, Server = Server)
	
	
	def enqueue(self, **args):
		
		if args.has_key('__session'):
			session = args['__session']
			del args['__session']
			self.clientQueues[session]['q'].put(args)
		else:
			for session in self.clientQueues:
				self.clientQueues[session]['q'].put(args)
	
	
	def checkPermission(self, object, role):
		
		Server   = object['Server']
		username = object['Username']
		
		if self.authRequired:
			if (self.clients.has_key(username) and role in self.clients[username]['servers'][Server]['roles']) or (self.clientsAMI.has_key(username) and role in self.clientsAMI[username]['servers'][Server]['roles']):
				return True
			else:
				self.enqueue(__session = object['Session'], Action = 'doAlertError', Message = 'You do not have permission to execute this action.')
				return False
		else:
			return True
	
		
	def parseJson(self, **args):
		
		if args.has_key('CallerID'):
			args['CallerID'] = u'%s' % args['CallerID'].decode('iso8859')
		
		return json.dumps(args)
		
		
	def __sortPeers(self):

		_sortKeys = {
			'user'        : 0,
			'peer'        : 1,
			'callerid'    : 2,
			'calleridname': 3,
			'calleridnum' : 4
		}

		## identify technologies
		techs = {}
		for Server in self.servers:
			techs[Server] = {}
			for user in self.monitoredUsers[Server]:
				tech, peer   = user.split('/')
				
				CallerID     = self.monitoredUsers[Server][user]['CallerID']
				CallerIDName = peer
				CallerIDNum  = peer
				
				if CallerID != '--':
					CallerIDName = CallerID[:CallerID.find('<')].strip()
					CallerIDNum  = CallerID[CallerID.find('<')+1:CallerID.find('>')].strip()
				else:
					CallerID = peer
					
				try:
					techs[Server][tech].append((user, peer, CallerID, CallerIDName, CallerIDNum))
				except KeyError:
					techs[Server][tech] = [(user, peer, CallerID, CallerIDName, CallerIDNum)]
	
			for tech in techs[Server]:
				if self.sortby in ('callerid', 'calleridname', 'calleridnum'):
					usersWithCid    = []
					usersWithoutCid = []
					for user in techs[Server][tech]:
						if user[1] != user[2]:
							usersWithCid.append(user)
						else:
							usersWithoutCid.append(user)
					usersWithCid.sort(lambda x, y: cmp(x[_sortKeys[self.sortby]].lower(), y[_sortKeys[self.sortby]].lower()))
					usersWithoutCid.sort(lambda x, y: cmp(x[_sortKeys[self.sortby]].lower(), y[_sortKeys[self.sortby]].lower()))
					techs[Server][tech] = usersWithCid + usersWithoutCid
				else:
					techs[Server][tech].sort(lambda x, y: cmp(x[_sortKeys[self.sortby]].lower(), y[_sortKeys[self.sortby]].lower()))
				
		return techs
		
	
	##
	## AMI Handlers for Events
	##
	def handlerReload(self, dic):
		
		log.info('MonAst.handlerReload :: Running...')
		self._GetConfig(dic['Server'])
		
		
	def handlerChannelReload(self, dic):
		
		log.info('MonAst.handlerChannelReload :: Running...')

		Channel      = dic.get('ChannelType', dic.get('Channel'))
		ReloadReason = dic['ReloadReason']
		
		self._GetConfig(dic['Server'])
		
		
	def handlerPeerEntry(self, dic):
		
		log.info('MonAst.handlerPeerEntry :: Running...')
				
		Server      = dic['Server']
		Status      = dic['Status']
		Channeltype = dic['Channeltype']
		ObjectName  = dic['ObjectName'].split('/')[0]
		
		if Status.startswith('OK'):
			Status = 'Registered'
		elif Status.find('(') != -1:
			Status = Status[0:Status.find('(')]
		
		user = '%s/%s' % (Channeltype, ObjectName)
		
		if self.userDisplay['DEFAULT'] and not self.userDisplay[Server].has_key(user):
			self.monitoredUsers[Server][user] = {'Channeltype': Channeltype, 'Status': Status, 'Calls': 0, 'CallerID': '--', 'Context': 'default', 'Variables': []}
		elif not self.userDisplay['DEFAULT'] and self.userDisplay[Server].has_key(user):
			self.monitoredUsers[Server][user] = {'Channeltype': Channeltype, 'Status': Status, 'Calls': 0, 'CallerID': '--', 'Context': 'default', 'Variables': []}
		else:
			user = None
		
		if user:
			type = ['peer', 'user'][Channeltype == 'Skype']
			self.AMI.execute(Action = {'Action': 'Command', 'Command': '%s show %s %s' % (Channeltype.lower(), type, ObjectName), 'ActionID': user}, Handler = self._defaultParseConfigPeers, Server = Server)
		
	
	def handlerPeerStatus(self, dic):
		
		log.info('MonAst.handlerPeerStatus :: Running...')
				
		Server     = dic['Server']
		Peer       = dic['Peer']
		PeerStatus = dic['PeerStatus']
		
		if self.monitoredUsers[Server].has_key(Peer):
			mu = self.monitoredUsers[Server][Peer]
			mu['Status'] = PeerStatus
			self.enqueue(Action = 'PeerStatus', Server = Server, Peer = Peer, Status = mu['Status'], Calls = mu['Calls'])
		
		
	def handlerSkypeAccountStatus(self, dic):
		
		log.info('MonAst.handlerSkypeAccountStatus :: Running...')
				
		Server   = dic['Server']
		Username = 'Skype/%s' % dic['Username']
		Status   = dic['Status']
		
		if self.monitoredUsers[Server].has_key(Username):
			mu = self.monitoredUsers[Server][Username]
			mu['Status'] = Status
			self.enqueue(Action = 'PeerStatus', Server = Server, Peer = Username, Status = mu['Status'], Calls = mu['Calls'])
				
					
	def handlerBranchOnHook(self, dic): 

		log.info('MonAst.handlerBranchOnHook :: Running... (On)')

		Server  = dic['Server']
		Channel = dic['Channel']

		user = Channel
		if Channel.rfind('-') != -1:
			user = Channel[:Channel.rfind('-')]
		if self.monitoredUsers[Server].has_key(user):
			mu           = self.monitoredUsers[Server][user]
			mu['Calls']  = 0
			mu['Status'] = "Not in Use"
			self.enqueue(Action = 'PeerStatus', Server = Server, Peer = user, Status = mu['Status'], Calls = mu['Calls'])


	def handlerBranchOffHook(self, dic):

		log.info('MonAst.handlerBranchOffHook :: Running... (Off)')
		
		Server  = dic['Server']
		Channel = dic['Channel']
		
		user = Channel
		if Channel.rfind('-') != -1:
			user = Channel[:Channel.rfind('-')]
		if self.monitoredUsers[Server].has_key(user):
			mu           = self.monitoredUsers[Server][user]
			mu['Status'] = "In Use"
			self.enqueue(Action = 'PeerStatus', Server = Server, Peer = user, Status = mu['Status'], Calls = mu['Calls'])
	
	
	def handlerNewchannel(self, dic):
		
		log.info('MonAst.handlerNewchannel :: Running...')
				
		Server       = dic['Server']
		Channel      = dic['Channel']
		State        = dic.get('ChannelStateDesc', dic.get('State'))
		CallerIDNum  = dic['CallerIDNum']
		CallerIDName = dic['CallerIDName']
		Uniqueid     = dic['Uniqueid']
		Monitor      = False
					
		self.channels[Server][Uniqueid] = {'Channel': Channel, 'State': State, 'CallerIDNum': CallerIDNum, 'CallerIDName': CallerIDName, 'Monitor': Monitor}
		self.enqueue(Action = 'NewChannel', Server = Server, Channel = Channel, State = State, CallerIDNum = CallerIDNum, CallerIDName = CallerIDName, Uniqueid = Uniqueid, Monitor = Monitor)
		
		user = Channel
		if Channel.rfind('-') != -1:
			user = Channel[:Channel.rfind('-')]
		if self.monitoredUsers[Server].has_key(user):
			mu           = self.monitoredUsers[Server][user]
			mu['Calls'] += 1
			self.enqueue(Action = 'PeerStatus', Server = Server, Peer = user, Status = mu['Status'], Calls = mu['Calls'])

		
	def handlerNewstate(self, dic):
		
		log.info('MonAst.handlerNewstate :: Running...')
				
		Server       = dic['Server']
		Channel      = dic['Channel']
		State        = dic.get('ChannelStateDesc', dic.get('State'))
		CallerID     = dic.get('CallerIDNum', dic.get('CallerID'))
		CallerIDName = dic['CallerIDName']
		Uniqueid     = dic['Uniqueid']
					
		try:
			self.channels[Server][Uniqueid]['State']        = State
			self.channels[Server][Uniqueid]['CallerIDNum']  = CallerID
			self.channels[Server][Uniqueid]['CallerIDName'] = CallerIDName
			self.enqueue(Action = 'NewState', Server = Server, Channel = Channel, State = State, CallerID = CallerID, CallerIDName = CallerIDName, Uniqueid = Uniqueid)
		except:
			log.warning("MonAst.handlerNewstate :: Uniqueid %s not found on self.channels['%s']" % (Uniqueid, Server))
		
		
	def handlerHangup(self, dic):
		
		log.info('MonAst.handlerHangup :: Running...')
				
		Server    = dic['Server']
		Channel   = dic['Channel']
		Uniqueid  = dic['Uniqueid']
		Cause     = dic['Cause']
		Cause_txt = dic['Cause-txt']
					
		try:
			del self.channels[Server][Uniqueid]
			self.enqueue(Action = 'Hangup', Server = Server, Channel = Channel, Uniqueid = Uniqueid, Cause = Cause, Cause_txt = Cause_txt)
		except:
			log.warning("MonAst.handlerHangup :: Channel %s not found on self.channels['%s']" % (Uniqueid, Server))
		
		toDelete = None
		for id in self.calls[Server]:
			if Uniqueid in id and self.calls[Server][id]['Status'] in ('Dial', 'Unlink'):
				toDelete = id
				break
		if toDelete:
			del self.calls[Server][toDelete]
			src, dst = toDelete
			self.enqueue(Action = 'Unlink', Server = Server, Channel1 = None, Channel2 = None, Uniqueid1 = src, Uniqueid2 = dst, CallerID1 = None, CallerID2 = None)
		
		user = Channel
		if Channel.rfind('-') != -1:
			user = Channel[:Channel.rfind('-')]
		if self.monitoredUsers[Server].has_key(user) and self.monitoredUsers[Server][user]['Calls'] > 0:
			mu           = self.monitoredUsers[Server][user] 
			mu['Calls'] -= 1
			self.enqueue(Action = 'PeerStatus', Server = Server, Peer = user, Status = mu['Status'], Calls = mu['Calls'])
		
		if self.queueMemberCalls[Server].has_key(Uniqueid):
			Queue  = self.queueMemberCalls[Server][Uniqueid]['Queue']
			Member = self.queueMemberCalls[Server][Uniqueid]['Member']
			del self.queueMemberCalls[Server][Uniqueid]
			self.enqueue(Action = 'RemoveQueueMemberCall', Server = Server, Queue = Queue, Member = Member, Uniqueid = Uniqueid)

	
	def handlerDial(self, dic):
		
		log.info('MonAst.handlerDial :: Running...')
				
		Server   = dic['Server']
		SubEvent = dic.get('SubEvent', None)
		if SubEvent == 'Begin':
			Source       = dic.get('Channel', dic.get('Source'))
			Destination  = dic['Destination']
			CallerID     = dic.get('CallerIDNum', dic.get('CallerID'))
			CallerIDName = dic['CallerIDName']
			SrcUniqueID  = dic.get('UniqueID', dic.get('SrcUniqueID'))
			DestUniqueID = dic['DestUniqueID']
			
			try:
				c = self.channels[Server][SrcUniqueID]
				self.calls[Server][(SrcUniqueID, DestUniqueID)] = {
					'Source': Source, 'Destination': Destination, 'SrcUniqueID': SrcUniqueID, 'DestUniqueID': DestUniqueID, 
					'Status': 'Dial', 'startTime': 0
				}
			except KeyError, e:
				log.warning("MonAst.handlerDial :: Channel %s not found on self.channels['%s']" % (SrcUniqueID, Server))
			
			self.enqueue(Action = 'Dial', Server = Server, Source = Source, Destination = Destination, CallerID = CallerID, CallerIDName = CallerIDName, SrcUniqueID = SrcUniqueID, DestUniqueID = DestUniqueID)
		
		elif SubEvent == 'End':
			Channel  = dic['Channel']
			Uniqueid = dic['UniqueID']
			
			calls = self.calls[Server].keys()
			for call in calls:
				if Uniqueid in call:
					#del self.calls[call]
					self.calls[Server][call]['Status'] == 'Unlink'
					self.enqueue(Action = 'Unlink', Server = Server, Channel1 = None, Channel2 = None, Uniqueid1 = call[0], Uniqueid2 = call[1], CallerID1 = None, CallerID2 = None)
			
			if self.queueMemberCalls[Server].has_key(Uniqueid):
				self.queueMemberCalls[Server][Uniqueid]['Link'] = False
				qmc = self.queueMemberCalls[Server][Uniqueid]
				self.enqueue(Action = 'RemoveQueueMemberCall', Server = Server, Queue = qmc['Queue'], Member = qmc['Member'], Uniqueid = Uniqueid)
			
		else:
			log.info('MonAst.handlerDial :: Unhandled Dial subevent %s' % SubEvent)
		
		
	def handlerLink(self, dic):
		
		log.info('MonAst.handlerLink :: Running...')
				
		Server    = dic['Server']
		Channel1  = dic['Channel1']
		Channel2  = dic['Channel2']
		Uniqueid1 = dic['Uniqueid1']
		Uniqueid2 = dic['Uniqueid2']
		CallerID1 = dic['CallerID1']
		CallerID2 = dic['CallerID2']
		
		try:
			CallerID1 = '%s <%s>' % (self.channels[Server][Uniqueid1]['CallerIDName'], self.channels[Server][Uniqueid1]['CallerIDNum'])
			CallerID2 = '%s <%s>' % (self.channels[Server][Uniqueid2]['CallerIDName'], self.channels[Server][Uniqueid2]['CallerIDNum'])
		except:
			log.warning("MonAst.handlerUnlink :: Uniqueid %s or %s not found on self.channels['%s']" % (Uniqueid1, Uniqueid2, Server))
		
		call = (Uniqueid1, Uniqueid2)
		
		try:
			self.calls[Server][call]['Status'] = 'Link'
			 
			if self.calls[Server][call]['startTime'] == 0:
				self.calls[Server][call]['startTime'] = time.time()
		except:
			self.calls[Server][call] = {
				'Source': Channel1, 'Destination': Channel2, 'SrcUniqueID': Uniqueid1, 'DestUniqueID': Uniqueid2, 
				'Status': 'Link', 'startTime': time.time()
			}
		Seconds = time.time() - self.calls[Server][call]['startTime']
		self.enqueue(Action = 'Link', Server = Server, Channel1 = Channel1, Channel2 = Channel2, Uniqueid1 = Uniqueid1, Uniqueid2 = Uniqueid2, CallerID1 = CallerID1, CallerID2 = CallerID2, Seconds = Seconds)

		if self.queueMemberCalls[Server].has_key(Uniqueid1):
			self.queueMemberCalls[Server][Uniqueid1]['Member'] = Channel2[:Channel2.rfind('-')]
			self.queueMemberCalls[Server][Uniqueid1]['Link']   = True
			qmc = self.queueMemberCalls[Server][Uniqueid1]
			self.enqueue(Action = 'AddQueueMemberCall', Server = Server, Queue = qmc['Queue'], Member = qmc['Member'], Uniqueid = Uniqueid1, Channel = qmc['Channel'], CallerID = CallerID1, Seconds = Seconds)
		
		
	def handlerBridge(self, dic):
		
		log.info('MonAst.handlerBridge :: Running...')
		self.handlerLink(dic)
		
		
	def handlerUnlink(self, dic):
		
		log.info('MonAst.handlerUnlink :: Running...')
				
		Server    = dic['Server']
		Channel1  = dic['Channel1']
		Channel2  = dic['Channel2']
		Uniqueid1 = dic['Uniqueid1']
		Uniqueid2 = dic['Uniqueid2']
		CallerID1 = dic['CallerID1']
		CallerID2 = dic['CallerID2']
		
		try:
			#del self.calls[(Uniqueid1, Uniqueid2)]
			self.calls[Server][(Uniqueid1, Uniqueid2)]['Status'] = 'Unlink'
			self.enqueue(Action = 'Unlink', Server = Server, Channel1 = Channel1, Channel2 = Channel2, Uniqueid1 = Uniqueid1, Uniqueid2 = Uniqueid2, CallerID1 = CallerID1, CallerID2 = CallerID2)
		except:
			log.warning("MonAst.handlerUnlink :: Call %s-%s not found on self.calls['%s']" % (Uniqueid1, Uniqueid2, Server))
		
		if self.queueMemberCalls[Server].has_key(Uniqueid1):
			self.queueMemberCalls[Server][Uniqueid1]['Link'] = False
			qmc = self.queueMemberCalls[Server][Uniqueid1]
			self.enqueue(Action = 'RemoveQueueMemberCall', Server = Server, Queue = qmc['Queue'], Member = qmc['Member'], Uniqueid = Uniqueid1)

		
	def handlerNewcallerid(self, dic):
		
		log.info('MonAst.handlerNewcallerid :: Running...')
				
		Server         = dic['Server']
		Channel        = dic['Channel']
		CallerID       = dic.get('CallerIDNum', dic.get('CallerID'))
		CallerIDName   = dic['CallerIDName']
		Uniqueid       = dic['Uniqueid']
		CIDCallingPres = dic['CID-CallingPres']
		
		try:
			self.channels[Server][Uniqueid]['CallerIDName'] = CallerIDName
			self.channels[Server][Uniqueid]['CallerIDNum']  = CallerID
			self.enqueue(Action = 'NewCallerid', Server = Server, Channel = Channel, CallerID = CallerID, CallerIDName = CallerIDName, Uniqueid = Uniqueid, CIDCallingPres = CIDCallingPres)
		except KeyError:
			log.warning("MonAst.handlerNewcallerid :: UniqueID '%s' not found on self.channels['%s']" % (Uniqueid, Server))
		
		
	def handlerRename(self, dic):
		
		log.info('MonAst.handlerRename :: Running...')
				
		Server       = dic['Server']
		Oldname      = dic.get('Channel', dic.get('Oldname'))
		Newname      = dic['Newname']
		Uniqueid     = dic['Uniqueid']
		CallerIDName = ''
		CallerID     = ''
		
		try:
			
			self.channels[Server][Uniqueid]['Channel'] = Newname
			CallerIDName = self.channels[Server][Uniqueid]['CallerIDName']
			CallerID     = self.channels[Server][Uniqueid]['CallerIDNum']
		
			for call in self.calls[Server]:
				SrcUniqueID, DestUniqueID = call
				key = None
				if (SrcUniqueID == Uniqueid):
					key = 'Source'
				if (DestUniqueID == Uniqueid):
					key = 'Destination'
				if key:
					self.calls[Server][call][key] = Newname
					break							
			
			self.enqueue(Action = 'Rename', Server = Server, Oldname = Oldname, Newname = Newname, Uniqueid = Uniqueid, CallerIDName = CallerIDName, CallerID = CallerID)
		except:
			log.warn("MonAst.handlerRename :: Channel %s not found in self.channels['%s'], ignored." % (Oldname, Server))
			
			
	def handlerMeetmeJoin(self, dic):
		
		log.info('MonAst.handlerMeetmeJoin :: Running...')
				
		Server       = dic['Server']
		Uniqueid     = dic['Uniqueid']
		Meetme       = dic['Meetme']
		Usernum      = dic['Usernum']
		CallerIDNum  = dic.get('CallerIDNum', dic.get('CallerIDnum', None))
		CallerIDName = dic.get('CallerIDName', dic.get('CallerIDname', None))
					
		ch = self.channels[Server][Uniqueid]
		try:
			self.meetme[Server][Meetme]['users'][Usernum] = {'Uniqueid': Uniqueid, 'CallerIDNum': CallerIDNum, 'CallerIDName': CallerIDName}
		except KeyError:
			self.meetme[Server][Meetme] = {
					'dynamic': True,
					'users'  : {Usernum: {'Uniqueid': Uniqueid, 'CallerIDNum': CallerIDNum, 'CallerIDName': CallerIDName}}
			}
			self.enqueue(Action = 'MeetmeCreate', Server = Server, Meetme = Meetme)
		self.enqueue(Action = 'MeetmeJoin', Server = Server, Meetme = Meetme, Uniqueid = Uniqueid, Usernum = Usernum, Channel = ch['Channel'], CallerIDNum = CallerIDNum, CallerIDName = CallerIDName)
		
					
	def handlerMeetmeLeave(self, dic):
		
		log.info('MonAst.handlerMeetmeLeave :: Running...')
				
		Server   = dic['Server']
		Uniqueid = dic['Uniqueid']
		Meetme   = dic['Meetme']
		Usernum  = dic['Usernum']
		Duration = dic['Duration']
					
		try:
			del self.meetme[Server][Meetme]['users'][Usernum]
			self.enqueue(Action = 'MeetmeLeave', Server = Server, Meetme = Meetme, Uniqueid = Uniqueid, Usernum = Usernum, Duration = Duration)
			if (self.meetme[Server][Meetme]['dynamic'] and len(self.meetme[Server][Meetme]['users']) == 0):
				del self.meetme[Server][Meetme]
				self.enqueue(Action = 'MeetmeDestroy', Server = Server, Meetme = Meetme)
		except Exception, e:
			log.warn('MonAst.handlerMeetmeLeave :: Meetme or Usernum not found in self.meetme[\'%s\'][\'%s\'][\'users\'][\'%s\']' % (Server, Meetme, Usernum))
		
		
	def handlerParkedCall(self, dic):
		
		log.info('MonAst.handlerParkedCall :: Running...')
				
		Server       = dic['Server']
		Exten        = dic['Exten']
		Channel      = dic['Channel']
		From         = dic['From']
		Timeout      = dic['Timeout']
		CallerID     = dic.get('CallerIDNum', dic.get('CallerID'))
		CallerIDName = dic['CallerIDName']
					
		if self.isParkedStatus[Server]:
			self.parkedStatus[Server].append(Exten)
			if not self.parked[Server].has_key(Exten):
				self.parked[Server][Exten] = {'Channel': Channel, 'From': From, 'Timeout': Timeout, 'CallerID': CallerID, 'CallerIDName': CallerIDName}
				self.enqueue(Action = 'ParkedCall', Server = Server, Exten = Exten, Channel = Channel, From = From, Timeout = Timeout, CallerID = CallerID, CallerIDName = CallerIDName)
		else:
			self.parked[Server][Exten] = {'Channel': Channel, 'From': From, 'Timeout': Timeout, 'CallerID': CallerID, 'CallerIDName': CallerIDName}
			self.enqueue(Action = 'ParkedCall', Server = Server, Exten = Exten, Channel = Channel, From = From, Timeout = Timeout, CallerID = CallerID, CallerIDName = CallerIDName)
			
					
	def handlerUnParkedCall(self, dic):
		
		log.info('MonAst.handlerUnParkedCall :: Running...')
				
		Server       = dic['Server']
		Exten        = dic['Exten']
		Channel      = dic['Channel']
		From         = dic['From']
		CallerID     = dic.get('CallerIDNum', dic.get('CallerID'))
		CallerIDName = dic['CallerIDName']
					
		try:
			del self.parked[Server][Exten]
			self.enqueue(Action = 'UnparkedCall', Server = Server, Exten = Exten)
		except:
			log.warn('MonAst.handlerUnParkedCall :: Parked Exten %s not found on server %s' % (Exten, Server))
		
	
	def handlerParkedCallTimeOut(self, dic):
		
		log.info('MonAst.handlerParkedCallTimeOut :: Running...')
				
		Server       = dic['Server']
		Exten        = dic['Exten']
		Channel      = dic['Channel']
		CallerID     = dic.get('CallerIDNum', dic.get('CallerID'))
		CallerIDName = dic['CallerIDName']
					
		try:
			del self.parked[Server][Exten]
			self.enqueue(Action = 'UnparkedCall', Server = Server, Exten = Exten)
		except:
			log.warn('MonAst.handlerParkedCallTimeOut :: Parked Exten %s not found on server %s' % (Exten, Server))
		
	
	def handlerParkedCallGiveUp(self, dic):
		
		log.info('MonAst.handlerParkedCallGiveUp :: Running...')
				
		Server       = dic['Server']
		Exten        = dic['Exten']
		Channel      = dic['Channel']
		CallerID     = dic.get('CallerIDNum', dic.get('CallerID'))
		CallerIDName = dic['CallerIDName']
					
		try:
			del self.parked[Server][Exten]
			self.enqueue(Action = 'UnparkedCall', Server = Server, Exten = Exten)
		except:
			log.warn('MonAst.handlerParkedCallGiveUp :: Parked Exten %s not found on server %s' % (Exten, Server))
		
		
	def handlerParkedCallsComplete(self, dic):
		
		log.info('MonAst.handlerParkedCallsComplete :: Running...')

		Server = dic['Server']

		self.isParkedStatus[Server] = False
		
		lostParks = [i for i in self.parked[Server].keys() if i not in self.parkedStatus[Server]]
		for park in lostParks:
			log.warning('MonAst.handlerParkedCallsComplete :: Removing lost parked call %s on server %s' % (park, Server))
			try:
				del self.parked[Server][park]
				self.enqueue(Action = 'UnparkedCall', Server = Server, Exten = park)
			except:
				#pass ## added to debug purposes
				log.exception('MonAst.handlerParkedCallsComplete :: Exception removing lost parked call %s on server %s' % (park, Server))
		
		
	def handlerStatus(self, dic):
		
		log.info('MonAst.handlerStatus :: Running...')
				
		Server       = dic['Server']
		Channel      = dic['Channel']
		CallerIDNum  = dic['CallerIDNum']
		CallerIDName = dic['CallerIDName']
		State        = dic.get('ChannelStateDesc', dic.get('State'))
		Seconds      = dic.get('Seconds', 0)
		Link         = dic.get('BridgedChannel', dic.get('Link', ''))
		Uniqueid     = dic['Uniqueid']
		Monitor      = False
		
		self.channelStatus[Server].append(Uniqueid)
		
		if not self.channels[Server].has_key(Uniqueid):
			self.channels[Server][Uniqueid] = {'Channel': Channel, 'State': State, 'CallerIDNum': CallerIDNum, 'CallerIDName': CallerIDName, 'Monitor': Monitor}
			user = Channel
			if Channel.rfind('-') != -1:
				user = Channel[:Channel.rfind('-')]
			if self.monitoredUsers[Server].has_key(user):
				mu           = self.monitoredUsers[Server][user] 
				mu['Calls'] += 1
				self.enqueue(Action = 'PeerStatus', Server = Server, Peer = user, Status = mu['Status'], Calls = mu['Calls'])
			self.enqueue(Action = 'NewChannel', Server = Server, Channel = Channel, State = State, CallerIDNum = CallerIDNum, CallerIDName = CallerIDName, Uniqueid = Uniqueid, Monitor = Monitor)
			if Link:
				for UniqueidLink in self.channels[Server]:
					if self.channels[Server][UniqueidLink]['Channel'] == Link:
						self.calls[Server][(Uniqueid, UniqueidLink)] = {
							'Source': Channel, 'Destination': Link, 'SrcUniqueID': Uniqueid, 'DestUniqueID': UniqueidLink, 
							'Status': 'Link', 'startTime': time.time() - int(Seconds)
						}
						CallerID1 = '%s <%s>' % (self.channels[Server][Uniqueid]['CallerIDName'], self.channels[Server][Uniqueid]['CallerIDNum'])
						CallerID2 = '%s <%s>' % (self.channels[Server][UniqueidLink]['CallerIDName'], self.channels[Server][UniqueidLink]['CallerIDNum'])
						self.enqueue(Action = 'Link', Server = Server, Channel1 = Channel, Channel2 = Link, Uniqueid1 = Uniqueid, Uniqueid2 = UniqueidLink, CallerID1 = CallerID1, CallerID2 = CallerID2, Seconds = int(Seconds))
		
		## Update call duration
		if self.channels[Server].has_key(Uniqueid) and Seconds > 0 and Link:
			for UniqueidLink in self.channels[Server]:
				if self.channels[Server][UniqueidLink]['Channel'] == Link:
					call = (Uniqueid, UniqueidLink)
					duration = time.time() - self.calls[Server][call]['startTime']
					Seconds  = int(Seconds)
					if duration < (Seconds - 10) or duration > (Seconds + 10):
						self.calls[Server][call]['startTime'] = time.time() - Seconds
						self.enqueue(Action = 'UpdateCallDuration', Server = Server, Uniqueid1 = Uniqueid, Uniqueid2 = UniqueidLink, Seconds = Seconds)
		
		
	def handlerStatusComplete(self, dic):
		
		log.info('MonAst.handlerStatusComplete :: Running...')
				
		Server = dic['Server']
		
		## Search for lost channels
		lostChannels = [i for i in self.channels[Server].keys() if i not in self.channelStatus[Server]]
		for Uniqueid in lostChannels:
			log.warning('MonAst.handlerStatusComplete :: Removing lost channel %s on server %s' % (Uniqueid, Server))
			try:
				Channel = self.channels[Server][Uniqueid]['Channel']
				del self.channels[Server][Uniqueid]
				self.enqueue(Action = 'Hangup', Server = Server, Channel = Channel, Uniqueid = Uniqueid, Cause = None, Cause_txt = None)
			except:
				#pass ## added to debug purposes
				log.exception('MonAst.handlerStatusComplete :: Exception removing lost channel %s on server %s' % (Uniqueid, Server))
			
			## Decrease number of peer calls 
			user = Channel
			if Channel.rfind('-') != -1:
				user = Channel[:Channel.rfind('-')]
			if self.monitoredUsers[Server].has_key(user) and self.monitoredUsers[Server][user]['Calls'] > 0:
				mu           = self.monitoredUsers[Server][user] 
				mu['Calls'] -= 1
				self.enqueue(Action = 'PeerStatus', Server = Server, Peer = user, Status = mu['Status'], Calls = mu['Calls'])
			
		## Search for lost calls
		lostCalls = [call for call in self.calls[Server].keys() if not self.channels[Server].has_key(call[0]) or not self.channels[Server].has_key(call[1])]
		for call in lostCalls:
			log.warning('MonAst.handlerStatusComplete :: Removing lost call %s-%s on server %s' % (call[0], call[1], Server))
			try:
				del self.calls[Server][call]
				self.enqueue(Action = 'Unlink', Server = Server, Channel1 = None, Channel2 = None, Uniqueid1 = call[0], Uniqueid2 = call[1], CallerID1 = None, CallerID2 = None)
			except:
				#pass ## added to debug purposes
				log.exception('MonAst.handlerStatusComplete :: Exception removing lost call %s-%s on server' % (call[0], call[1], Server))
			
		## Search for lost queue member calls
		lostQueueMemberCalls = [Uniqueid for Uniqueid in self.queueMemberCalls[Server] if not self.channels[Server].has_key(Uniqueid)]
		for Uniqueid in lostQueueMemberCalls:
			log.warning('MonAst.handlerStatusComplete :: Removing lost Queue Member Call %s on server' % (Uniqueid, Server))
			try:
				Queue  = self.queueMemberCalls[Server][Uniqueid]['Queue']
				Member = self.queueMemberCalls[Server][Uniqueid]['Member']
				del self.queueMemberCalls[Server][Uniqueid]
				self.enqueue(Action = 'RemoveQueueMemberCall', Server = Server, Queue = Queue, Member = Member, Uniqueid = Uniqueid)
			except:
				#pass ## added to debug purposes
				log.exception('MonAst.handlerStatusComplete :: Exception removing lost Queue Member Call %s on server %s' % (Uniqueid, Server))

		if self.getMeetmeAndParkStatus[Server]:
			self.AMI.execute(Action = {'Action': 'Command', 'Command': 'meetme'}, Handler = self.handlerParseMeetme, Server = Server)
			self.AMI.execute(Action = {'Action': 'Command', 'Command': 'show parkedcalls'}, Handler = self.handlerShowParkedCalls, Server = Server)
			self.getMeetmeAndParkStatus[Server] = False
			
	
	def handlerQueueMember(self, dic):
		
		log.info('MonAst.handlerQueueMember :: Running...')
				
		Server     = dic['Server']
		Queue      = dic['Queue']
		Name       = dic['Name']
		Location   = dic['Location']
		Penalty    = dic['Penalty']
		CallsTaken = dic['CallsTaken']
		LastCall   = dic['LastCall']
		Status     = dic['Status']
		Paused     = dic['Paused']
		
		if (self.queuesDisplay['DEFAULT'] and self.queuesDisplay[Server].has_key(Queue)) or (not self.queuesDisplay['DEFAULT'] and not self.queuesDisplay[Server].has_key(Queue)):
			return
		
		if not self.queues[Server].has_key(Queue):
			log.warning("MonAst.handlerQueueMember :: Can not add location '%s' to queue '%s' on server %s. Queue not found." % (Location, Queue, Server))
			return

		PausedTime = 1
		if Paused == '1':
			if self.queueMemberPaused[Server].has_key(Queue):
				try:
					PausedTime = time.time() - self.queueMemberPaused[Server][Queue][Location]
				except:
					self.queueMemberPaused[Server][Queue][Location] = time.time()
			else:
				self.queueMemberPaused[Server][Queue] = {Location: time.time()}
		else:
			try:
				del self.queueMemberPaused[Server][Queue][Location]
			except:
				pass
		
		try:
			self.queues[Server][Queue]['members'][Location]['Penalty']    = Penalty
			self.queues[Server][Queue]['members'][Location]['CallsTaken'] = CallsTaken
			self.queues[Server][Queue]['members'][Location]['LastCall']   = LastCall
			self.queues[Server][Queue]['members'][Location]['Status']     = Status
			self.queues[Server][Queue]['members'][Location]['Paused']     = Paused
			self.enqueue(Action = 'QueueMemberStatus', Server = Server, Queue = Queue, Member = Location, Penalty = Penalty, CallsTaken = CallsTaken, LastCall = LastCall, Status = AST_DEVICE_STATES[Status], Paused = Paused, PausedTime = PausedTime)
		except KeyError:
			self.queues[Server][Queue]['members'][Location] = {
				'Name': Name, 'Penalty': Penalty, 'CallsTaken': CallsTaken, 'LastCall': LastCall, 'Status': Status, 'Paused': Paused
			}
			self.enqueue(Action = 'AddQueueMember', Server = Server, Queue = Queue, Member = Location, MemberName = Name, Penalty = Penalty, CallsTaken = CallsTaken, LastCall = LastCall, Status = AST_DEVICE_STATES[Status], Paused = Paused, PausedTime = PausedTime)
		self.queueMemberStatus[Server][Queue].append(Location)
		
		
	def handlerQueueMemberStatus(self, dic):
		
		log.info('MonAst.handlerQueueMemberStatus :: Running...')
				
		dic['Name'] = dic['MemberName']
		self.handlerQueueMember(dic)
		
		
	def handlerQueueMemberPaused(self, dic):
		
		log.info('MonAst.handlerQueueMemberPaused :: Running...')
				
		Server   = dic['Server']
		Queue    = dic['Queue']
		Location = dic['Location']
		
		if (self.queuesDisplay['DEFAULT'] and self.queuesDisplay[Server].has_key(Queue)) or (not self.queuesDisplay['DEFAULT'] and not self.queuesDisplay[Server].has_key(Queue)):
			return
		
		dic['Penalty'] = self.queues[Server][Queue]['members'][Location]['Penalty']
		dic['CallsTaken'] = self.queues[Server][Queue]['members'][Location]['CallsTaken']
		dic['LastCall'] = self.queues[Server][Queue]['members'][Location]['LastCall']
		dic['Status'] = self.queues[Server][Queue]['members'][Location]['Status']
		dic['Name'] = dic['MemberName']
		
		self.handlerQueueMember(dic)
		
		
	def handlerQueueEntry(self, dic):
		
		log.info('MonAst.handlerQueueEntry :: Running...')
		
		Server       = dic['Server']
		Queue        = dic['Queue']
		Position     = dic['Position']
		Channel      = dic['Channel']
		CallerID     = dic.get('CallerIDNum', dic.get('CallerID'))
		CallerIDName = dic['CallerIDName']
		Wait         = dic['Wait']
		Uniqueid     = None
		
		if (self.queuesDisplay['DEFAULT'] and self.queuesDisplay[Server].has_key(Queue)) or (not self.queuesDisplay['DEFAULT'] and not self.queuesDisplay[Server].has_key(Queue)):
			return
		
		# I need to get Uniqueid from this entry
		for Uniqueid in self.channels[Server]:
			if self.channels[Server][Uniqueid]['Channel'] == Channel:
				break
		
		self.queueClientStatus[Server][Queue].append(Uniqueid)
		Count = len(self.queueClientStatus[Server][Queue])
		try:
			self.queues[Server][Queue]['clients'][Uniqueid]['Position'] = Position			
		except KeyError:
			self.queues[Server][Queue]['clients'][Uniqueid] = {'Uniqueid': Uniqueid, 'Channel': Channel, 'CallerID': CallerID, 'CallerIDName': CallerIDName, \
													'Position': Position, 'JoinTime': time.time() - int(Wait)}
			self.enqueue(Action = 'AddQueueClient', Server = Server, Queue = Queue, Uniqueid = Uniqueid, Channel = Channel, CallerID = CallerID, CallerIDName = CallerIDName, Position = Position, Count = Count, Wait = Wait)

		
	def handlerQueueMemberAdded(self, dic):
		
		log.info('MonAst.handlerQueueMemberAdded :: Running...')
				
		Server     = dic['Server']
		Queue      = dic['Queue']
		Location   = dic['Location']
		MemberName = dic['MemberName']
		Penalty    = dic['Penalty']
		
		if (self.queuesDisplay['DEFAULT'] and self.queuesDisplay[Server].has_key(Queue)) or (not self.queuesDisplay['DEFAULT'] and not self.queuesDisplay[Server].has_key(Queue)):
			return
		
		self.queues[Server][Queue]['members'][Location] = {'Name': MemberName, 'Penalty': Penalty, 'CallsTaken': 0, 'LastCall': 0, 'Status': '0', 'Paused': 0} 
		self.enqueue(Action = 'AddQueueMember', Server = Server, Queue = Queue, Member = Location, MemberName = MemberName, Penalty = Penalty, CallsTaken = 0, LastCall = 0, Status = AST_DEVICE_STATES['0'], Paused = 0)
		
		
	def handlerQueueMemberRemoved(self, dic):
		
		log.info('MonAst.handlerQueueMemberRemoved :: Running...')
				
		Server     = dic['Server']
		Queue      = dic['Queue']
		Location   = dic['Location']
		MemberName = dic['MemberName']
		
		if (self.queuesDisplay['DEFAULT'] and self.queuesDisplay[Server].has_key(Queue)) or (not self.queuesDisplay['DEFAULT'] and not self.queuesDisplay[Server].has_key(Queue)):
			return
		
		try:
			del self.queues[Server][Queue]['members'][Location]
			self.enqueue(Action = 'RemoveQueueMember', Server = Server, Queue = Queue, Member = Location, MemberName = MemberName)
		except KeyError:
			log.warn("MonAst.handlerQueueMemberRemoved :: Queue or Member not found in self.queues['%s']['%s']['members']['%s']" % (Server, Queue, Location))
		
		
	def handlerJoin(self, dic): # Queue Join
		
		log.info('MonAst.handlerJoin :: Running...')
				
		Server       = dic['Server']
		Channel      = dic['Channel']
		CallerID     = dic.get('CallerIDNum', dic.get('CallerID'))
		CallerIDName = dic['CallerIDName']
		Queue        = dic['Queue']
		Position     = dic['Position']
		Count        = dic['Count']
		Uniqueid     = dic['Uniqueid']
		
		if (self.queuesDisplay['DEFAULT'] and self.queuesDisplay[Server].has_key(Queue)) or (not self.queuesDisplay['DEFAULT'] and not self.queuesDisplay[Server].has_key(Queue)):
			return
		
		try:
			self.queues[Server][Queue]['clients'][Uniqueid] = {'Uniqueid': Uniqueid, 'Channel': Channel, 'CallerID': CallerID, 'CallerIDName': CallerIDName, \
													'Position': Position, 'JoinTime': time.time()}
			self.queues[Server][Queue]['stats']['Calls'] += 1
			self.enqueue(Action = 'AddQueueClient', Server = Server, Queue = Queue, Uniqueid = Uniqueid, Channel = Channel, CallerID = CallerID, CallerIDName = CallerIDName, Position = Position, Count = Count, Wait = 0)
		except KeyError:
			log.warning("MonAst.handlerJoin :: Queue '%s' not found on server %s" % (Queue, Server))
		
	
	def handlerLeave(self, dic): # Queue Leave
		
		log.info('MonAst.handlerLeave :: Running...')
			
		Server       = dic['Server']
		Channel      = dic['Channel']
		Queue        = dic['Queue']
		Count        = dic['Count']
		Uniqueid     = dic['Uniqueid']
		
		if (self.queuesDisplay['DEFAULT'] and self.queuesDisplay[Server].has_key(Queue)) or (not self.queuesDisplay['DEFAULT'] and not self.queuesDisplay[Server].has_key(Queue)):
			return
		
		try:
			cause = ''
			if self.queues[Server][Queue]['clients'][Uniqueid].has_key('Abandoned'):
				cause = 'Abandoned'
				self.queues[Server][Queue]['stats']['Abandoned'] += 1
			else:
				cause = 'Completed'
				self.queues[Server][Queue]['stats']['Completed'] += 1
				self.queueMemberCalls[Server][Uniqueid] = {'Queue': Queue, 'Channel': Channel, 'Member': None, 'Link': False}
			self.queues[Server][Queue]['stats']['Calls'] -= 1
			
			del self.queues[Server][Queue]['clients'][Uniqueid]
			self.enqueue(Action = 'RemoveQueueClient', Server = Server, Queue = Queue, Uniqueid = Uniqueid, Channel = Channel, Count = Count, Cause = cause)
		except KeyError:
			log.warn("MonAst.handlerLeave :: Queue or Client not found in self.queues['%s']['%s']['clients']['%s']" % (Server, Queue, Uniqueid))
		
		
	def handlerQueueCallerAbandon(self, dic):
		
		log.info('MonAst.handlerQueueCallerAbandon :: Running...')
				
		Server   = dic['Server']
		Queue    = dic['Queue']
		Uniqueid = dic['Uniqueid']
		
		if (self.queuesDisplay['DEFAULT'] and self.queuesDisplay[Server].has_key(Queue)) or (not self.queuesDisplay['DEFAULT'] and not self.queuesDisplay[Server].has_key(Queue)):
			return
		
		try:
			self.queues[Server][Queue]['clients'][Uniqueid]['Abandoned'] = True
		except KeyError:
			log.warn("MonAst.handlerQueueCallerAbandon :: Queue or Client found in self.queues['%s']['%s']['clients']['%s']" % (Server, Queue, Uniqueid))
		
		#self.enqueue(Action = 'AbandonedQueueClient', Uniqueid = Uniqueid)
		
		
	def handlerQueueParams(self, dic):
		
		log.info('MonAst.handlerQueueParams :: Running...')
				
		Server           = dic['Server']
		Queue            = dic['Queue']
		Max              = int(dic['Max'])
		Calls            = int(dic['Calls'])
		Holdtime         = int(dic['Holdtime'])
		Completed        = int(dic['Completed'])
		Abandoned        = int(dic['Abandoned'])
		ServiceLevel     = int(dic['ServiceLevel'])
		ServicelevelPerf = float(dic['ServicelevelPerf'].replace(',', '.'))
		Weight           = int(dic['Weight'])
		
		if (self.queuesDisplay['DEFAULT'] and self.queuesDisplay[Server].has_key(Queue)) or (not self.queuesDisplay['DEFAULT'] and not self.queuesDisplay[Server].has_key(Queue)):
			return
		
		if self.queues[Server].has_key(Queue):
			self.queues[Server][Queue]['stats']['Max']              = Max
			self.queues[Server][Queue]['stats']['Calls']            = Calls
			self.queues[Server][Queue]['stats']['Holdtime']         = Holdtime
			self.queues[Server][Queue]['stats']['Completed']        = Completed
			self.queues[Server][Queue]['stats']['Abandoned']        = Abandoned
			self.queues[Server][Queue]['stats']['ServiceLevel']     = ServiceLevel
			self.queues[Server][Queue]['stats']['ServicelevelPerf'] = ServicelevelPerf
			self.queues[Server][Queue]['stats']['Weight']           = Weight
		else:
			self.queues[Server][Queue] = {
				'members': {}, 
				'clients': {}, 
				'stats': {
					'Max': Max, 'Calls': Calls, 'Holdtime': Holdtime, 'Completed': Completed, 'Abandoned': Abandoned, 'ServiceLevel': ServiceLevel, \
					'ServicelevelPerf': ServicelevelPerf, 'Weight': Weight
				}
			}
			self.queueMemberStatus[Server][Queue] = []
			self.queueClientStatus[Server][Queue] = []
			self.queueStatusFirst[Server]         = True
			self.queueStatusOrder[Server].append(Queue)
			
		self.enqueue(Action = 'QueueParams', Server = Server, Queue = Queue, Max = Max, Calls = Calls, Holdtime = Holdtime, Completed = Completed, Abandoned = Abandoned, ServiceLevel = ServiceLevel, ServicelevelPerf = ServicelevelPerf, Weight = Weight)
			
		
	def handlerQueueStatusComplete(self, dic):
		
		log.info('MonAst.handlerQueueStatusComplete :: Running...')
		
		Server = dic['Server']
		
		size = 0
		if self.queueStatusFirst[Server]:
			size = len(self.queueStatusOrder[Server])
			self.queueStatusFirst[Server] = False
		elif len(self.queueStatusOrder[Server]) > 0:
			size = 1			
		
		for i in xrange(size):
			try:
				queue       = self.queueStatusOrder[Server].pop(0)
				lostMembers = [i for i in self.queues[Server][queue]['members'].keys() if i not in self.queueMemberStatus[Server][queue]]
				for member in lostMembers:
					log.log(logging.NOTICE, 'MonAst.handlerQueueStatusComplete :: Removing lost member %s from queue %s on server %s' % (member, queue, Server))
					del self.queues[Server][queue]['members'][member]
					self.enqueue(Action = 'RemoveQueueMember', Server = Server, Queue = queue, Member = member, MemberName = None)
				
				lostClients = [i for i in self.queues[Server][queue]['clients'].keys() if i not in self.queueClientStatus[Server][queue]]
				for client in lostClients:
					log.log(logging.NOTICE, 'MonAst.handlerQueueStatusComplete :: Removing lost client %s from queue %s on server %s' % (client, queue, Server))
					Channel = self.queues[Server][queue]['clients'][client]['Channel']
					del self.queues[Server][queue]['clients'][client]
					Count = len(self.queues[Server][queue]['clients'])
					self.enqueue(Action = 'RemoveQueueClient', Server = Server, Queue = queue, Uniqueid = client, Channel = Channel, Count = Count, Cause = None)
			except:
				log.exception('MonAst.handlerQueueStatusComplete :: Unhandled Exception')
	
	
	def handlerMonitorStart(self, dic):
		
		log.info('MonAst.handlerMonitorStart :: Running...')
				
		Server   = dic['Server']
		Channel  = dic['Channel']
		Uniqueid = dic['Uniqueid']
		
		try:
			self.channels[Server][Uniqueid]['Monitor'] = True
			self.enqueue(Action = 'MonitorStart', Server = Server, Channel = Channel, Uniqueid = Uniqueid)
		except:
			log.warning('MonAst.handlerMonitorStart :: Uniqueid %s not found in self.channels[\'%s\']' % (Uniqueid, Server))
		
		
	def handlerMonitorStop(self, dic):
		
		log.info('MonAst.handlerMonitorStart :: Running...')
				
		Server   = dic['Server']
		Channel  = dic['Channel']
		Uniqueid = dic['Uniqueid']
		
		try:
			self.channels[Server][Uniqueid]['Monitor'] = False
			self.enqueue(Action = 'MonitorStop', Server = Server, Channel = Channel, Uniqueid = Uniqueid)
		except:
			log.warning('MonAst.handlerMonitorStop :: Uniqueid %s not found in self.channels[\'%s\']' % (Uniqueid, Server))
		
		
	##
	## AMI handlers for Actions/Commands
	##
	def _defaultParseConfigPeers(self, dic):
		
		log.info('MonAst._defaultParseConfigPeers :: Running...')
		result = '\n'.join(dic[' '])
		
		Server = dic['Server']
		user   = dic['ActionID']
		
		CallerID  = None
		Context   = None
		Variables = None
		
		try:
			CallerID = re.compile("['\"]").sub("", re.search('Callerid[\s]+:[\s](.*)\n', result).group(1))
			if CallerID == ' <>':
				CallerID = '--'
		except:
			CallerID = '--'
		
		try:
			Context = re.search('Context[\s]+:[\s](.*)\n', result).group(1)
		except:
			Context = 'default'
		
		try:
			tmp       = result[result.find('Variables'):]
			tmp       = tmp[tmp.find(':\n') + 2:]
			Variables = re.compile('^[\s]+(.*)\n', re.MULTILINE)
			Variables = Variables.findall(tmp)
			Variables = [i.replace(' = ', '=') for i in Variables]
		except:
			Variables = []
		
		if self.monitoredUsers[Server].has_key(user):
			self.monitoredUsers[Server][user]['CallerID']  = CallerID
			self.monitoredUsers[Server][user]['Context']   = Context
			self.monitoredUsers[Server][user]['Variables'] = Variables
		
		
	def handlerParseIAXPeers(self, dic):
		
		log.info('MonAst.handlerParseIAXPeers :: Running...')
			
		if not dic.has_key(' '):
			return
		
		for line in dic[' ']:
			name = re.search('^([^\s]*).*', line).group(1)
			if name.find('/') != -1:
				name = name[:name.find('/')]
			
			self.handlerPeerEntry({'Channeltype': 'IAX2', 'ObjectName': name, 'Status': '--', 'Server': Server})
			
			
	def handlerParseSkypeUsers(self, dic):
		
		log.info('MonAst.handlerParseSkypeUsers :: Running...')
		
		Server   = dic['Server']
		response = dic[' ']
		
		if 'Skype Users' in response:
			users = response.split('\n')[1:-1]
			for user, status in [i.split(': ') for i in users]:
				self.handlerPeerEntry({'Channeltype': 'Skype', 'ObjectName': user, 'Status': status, 'Server': Server})
				
	
	def handlerGetConfigMeetme(self, dic):
		
		log.info('MonAst.handlerGetConfigMeetme :: Parsing config...')
		
		Server = dic['Server']
		
		for key, value in dic.items():
			if key.startswith('Line-') and value.find('conf=') != -1:
				params = value.replace('conf=', '').split(',')
				self.meetme[Server][params[0]] = {'dynamic': False, 'users': {}}
		
		
	def handlerParseMeetme(self, dic):
		
		log.info('MonAst.handlerParseMeetme :: Parsing meetme...')

		Server   = dic['Server']
		reMeetme = re.compile('([^\s]*)[\s]+([^\s]*)[\s]+([^\s]*)[\s]+([^\s]*)[\s]+([^\s]*)')

		try:
			meetmes = dic[' '][1:-1]
			if len(meetmes) > 0:
				meetmes = meetmes[:-1]
			for meetme in meetmes:
				try:
					gMeetme = reMeetme.match(meetme)
					conf    = gMeetme.group(1)
					type    = gMeetme.group(5)
					
					if not self.meetme[Server].has_key(conf):
						dynamic = False
						if type.lower() == 'dynamic':
							dynamic = True
						self.meetme[Server][conf] = {'dynamic': dynamic, 'users': {}}
						self.enqueue(Action = 'MeetmeCreate', Server = Server, Meetme = conf)
						
					self.AMI.execute(Action = {'Action': 'Command', 'Command': 'meetme list %s concise' % conf, 'ActionID': 'meetmeList-%s' % conf}, Handler = self.handlerParseMeetmeConcise, Server = Server)				
				except:
					log.warn("MonAst.handlerParseMeetme :: Can't parse meetme line: %s on server %s" % (meetme, Server))
		except:
			log.exception("MonAst.handlerParseMeetme :: Unhandled Exception")
		
		
	def handlerParseMeetmeConcise(self, dic):

		log.info('MonAst.handlerParseMeetmeConcise :: Parsing meetme concise...')

		Server = dic['Server']
		meetme = dic['ActionID'].replace('meetmeList-', '')
		users  = dic[' '][:-1]
		
		for user in users:
			user = user.split('!')
			if self.meetme[Server].has_key(meetme):
				# locate UniqueID for this channel
				for Uniqueid in self.channels[Server]:
					if self.channels[Server][Uniqueid]['Channel'] == user[3]:
						self.meetme[Server][meetme]['users'][user[0]] = {'Uniqueid': Uniqueid, 'CallerIDNum': user[1], 'CallerIDName': user[2]}
						self.enqueue(Action = 'MeetmeJoin', Server = Server, Meetme = meetme, Uniqueid = Uniqueid, Usernum = user[0], Channel = user[3], CallerIDNum = user[1], CallerIDName = user[2])
						break
		
		
	def handlerShowParkedCalls(self, dic):
		
		log.info('MonAst.handlerShowParkedCalls :: Parsing parkedcalls...')
		
		reParked = re.compile('([0-9]+)[\s]+([^\s]*).*([^\s][0-9]+s)')
		
		Server  = dic['Server'] 
		parkeds = dic[' ']
		
		for park in parkeds:
			gParked = reParked.match(park)
			if gParked:
				Exten   = gParked.group(1)
				Channel = gParked.group(2)
				Timeout = gParked.group(3).replace('s', '')
				
				# search callerid for this channel
				c = None
				for Uniqueid in self.channels[Server]:
					if self.channels[Server][Uniqueid]['Channel'] == Channel:
						c = self.channels[Server][Uniqueid]
						break
					
				if c:
					self.parked[Server][Exten] = {'Channel': c['Channel'], 'From': 'Undefined', 'Timeout': Timeout, 'CallerID': c['CallerIDNum'], 'CallerIDName': c['CallerIDName']}
					self.enqueue(Action = 'ParkedCall', Server = Server, Exten = Exten, Channel = Channel, From = 'Undefined', Timeout = Timeout, CallerID = c['CallerIDNum'], CallerIDName = c['CallerIDName'])
				else:
					log.warn('MonAst.handlerShowParkedCalls :: No Channel found for parked call exten %s on server %s' % (Exten, Server))
				
	
	def handlerCliCommand(self, dic):
		
		log.info('MonAst.handlerCliCommand :: Running...')

		Server   = dic['Server']
		ActionID = dic['ActionID']
		Response = dic[' ']

		self.enqueue(Action = 'CliResponse', Server = Server, Response = '<br>'.join(Response), __session = ActionID)
	
	
	##
	## Handlers for Client Commands
	##
	def clientGetStatus(self, session, servers):
		
		log.info('MonAst.clientGetStatus (%s) :: Running...' % session)
		
		output = []
		theEnd = []
		
		try:
			self.clientQueues[session]['t'] = time.time()
			output.append('BEGIN STATUS')
			
			users = self.__sortPeers()
			
			for Server in servers:
				techs = users[Server].keys()
				techs.sort()
				for tech in techs:
					for user in users[Server][tech]:
						mu = self.monitoredUsers[Server][user[0]]
						output.append(self.parseJson(Action = 'PeerStatus', Server = Server, Peer = user[0], Status = mu['Status'], Calls = mu['Calls'], CallerID = user[2]))
				
				chans = self.channels[Server].keys()
				chans.sort()			
				for Uniqueid in chans:
					ch = self.channels[Server][Uniqueid]
					output.append(self.parseJson(Action = 'NewChannel', Server = Server, Channel = ch['Channel'], State = ch['State'], CallerIDNum = ch['CallerIDNum'], CallerIDName = ch['CallerIDName'], Uniqueid = Uniqueid, Monitor = ch['Monitor']))
				
				orderedCalls = self.calls[Server].keys()
				orderedCalls.sort(lambda x, y: cmp(self.calls[Server][x]['startTime'], self.calls[Server][y]['startTime']))
				for call in orderedCalls:
					c = self.calls[Server][call]
					src, dst = call
				
					CallerID1 = ''
					CallerID2 = ''
					
					try:
						CallerID1 = '%s <%s>' % (self.channels[Server][src]['CallerIDName'], self.channels[Server][src]['CallerIDNum'])
						CallerID2 = '%s <%s>' % (self.channels[Server][dst]['CallerIDName'], self.channels[Server][dst]['CallerIDNum'])
					except KeyError:
						log.warning('MonAst.clientGetStatus (%s) :: UniqueID %s or %s not found on self.channels[\'%s\']' % (session, src, dst, Server))
					
					try:
						if c['Status'] != 'Unlink':
							output.append(self.parseJson(Action = 'Call', Server = Server, Source = c['Source'], Destination = c['Destination'], \
								CallerID1 = CallerID1, CallerID2 = CallerID2, SrcUniqueID = c['SrcUniqueID'], DestUniqueID = c['DestUniqueID'], Status = c['Status'], Seconds = time.time() - c['startTime']))
					except:
						log.exception('MonAst.clientGetStatus (%s) :: Unhandled Exception' % session)
						
					if self.queueMemberCalls[Server].has_key(src) and self.queueMemberCalls[Server][src]['Link']:
						qmc = self.queueMemberCalls[Server][src]
						theEnd.append(self.parseJson(Action = 'AddQueueMemberCall', Server = Server, Queue = qmc['Queue'], Member = qmc['Member'], Uniqueid = src, Channel = qmc['Channel'], CallerID = CallerID1, Seconds = time.time() - c['startTime']))
					
				meetmeRooms = self.meetme[Server].keys()
				meetmeRooms.sort()
				for meetme in meetmeRooms:
					output.append(self.parseJson(Action = 'MeetmeCreate', Server = Server, Meetme = meetme))
					for Usernum in self.meetme[Server][meetme]['users']:
						mm = self.meetme[Server][meetme]['users'][Usernum]
						ch = self.channels[Server][mm['Uniqueid']]
						output.append(self.parseJson(Action = 'MeetmeJoin', Server = Server, Meetme = meetme, Uniqueid = mm['Uniqueid'], Usernum = Usernum, Channel = ch['Channel'], CallerIDNum = mm['CallerIDNum'], CallerIDName = mm['CallerIDName']))
				
				parkedCalls = self.parked[Server].keys()
				parkedCalls.sort()
				for Exten in parkedCalls:
					pc = self.parked[Server][Exten]
					output.append(self.parseJson(Action = 'ParkedCall', Server = Server, Exten = Exten, Channel = pc['Channel'], From = pc['From'], Timeout = pc['Timeout'], CallerID = pc['CallerID'], CallerIDName = pc['CallerIDName']))
					
				queues = self.queues[Server].keys()
				queues.sort()
				for queue in queues:
					q = self.queues[Server][queue]
					output.append(self.parseJson(Action = 'Queue', Server = Server, Queue = queue))
					members = q['members'].keys()
					members.sort()
					for member in members:
						m = q['members'][member]
						PausedTime = 1
						try:
							PausedTime = time.time() - self.queueMemberPaused[Server][queue][member]
						except:
							pass
						output.append(self.parseJson(Action = 'AddQueueMember', Server = Server, Queue = queue, Member = member, MemberName = m['Name'], \
							Penalty = m['Penalty'], CallsTaken = m['CallsTaken'], LastCall = m['LastCall'], Status = AST_DEVICE_STATES[m['Status']], Paused = m['Paused'], PausedTime = PausedTime))
						
					clients = q['clients'].values()
					clients.sort(lambda x, y: cmp(x['Position'], y['Position']))
					for i in xrange(len(clients)):
						c = clients[i]
						output.append(self.parseJson(Action = 'AddQueueClient', Server = Server, Queue = queue, Uniqueid = c['Uniqueid'], Channel = c['Channel'], CallerID = c['CallerID'], \
										CallerIDName = c['CallerIDName'], Position = c['Position'], Count = i, Wait = time.time() - c['JoinTime']))
						
					Max              = q['stats']['Max']
					Calls            = q['stats']['Calls']
					Holdtime         = q['stats']['Holdtime']
					Completed        = q['stats']['Completed']
					Abandoned        = q['stats']['Abandoned']
					ServiceLevel     = q['stats']['ServiceLevel']
					ServicelevelPerf = q['stats']['ServicelevelPerf']
					Weight           = q['stats']['Weight']
					
					output.append(self.parseJson(Action = 'QueueParams', Server = Server, Queue = queue, Max = Max, Calls = Calls, Holdtime = Holdtime, Completed = Completed, Abandoned = Abandoned, ServiceLevel = ServiceLevel, ServicelevelPerf = ServicelevelPerf, Weight = Weight))
			
			output += theEnd
			output.append('END STATUS')
		except:
			log.exception('MonAst.clientGetStatus (%s) :: Unhandled Exception' % session)
		
		return output
	
	
	def clientGetChanges(self, session, servers):
		
		log.info('MonAst.clientGetChanges (%s) :: Running...' % session)
		
		output = []
		
		if self.clientQueues.has_key(session):
			self.clientQueues[session]['t'] = time.time()
			while True:
				try:
					obj = self.clientQueues[session]['q'].get(False)
					if obj.has_key('Server'):
						if obj['Server'] in servers:
							output.append(json.dumps(obj))
					else:
						output.append(json.dumps(obj))
				except Queue.Empty:
					break
		
		if len(output) > 0:
			output.insert(0, 'BEGIN CHANGES')
			output.append('END CHANGES')
		else:
			output.append('NO CHANGES')
		
		return output
	
	
	def clientOriginateCall(self, session, object):
		
		log.info('MonAst.clientOriginateCall (%s) :: Running...' % session)
		Server = object['Server']
		src    = object['Source']
		dst    = object['Destination']
		type   = object['Type']
		
		Context = self.monitoredUsers[Server][src]['Context']
		if type == 'meetme':
			Context = self.servers[Server]['meetme_context']
			dst     = '%s%s' % (self.servers[Server]['meetme_prefix'], dst)
		command = {}
		command['Action']   = 'Originate'
		command['Channel']  = src
		command['Exten']    = dst
		command['Context']  = Context
		command['Priority'] = 1
		command['CallerID'] = MONAST_CALLERID
		for var in self.monitoredUsers[Server][src]['Variables']:
			command['Variable'] = var
		log.debug('MonAst.clientOriginateCall (%s) :: From %s to exten %s@%s on server %s' % (session, src, dst, Context, Server))
		self.AMI.execute(Action = command, Server = Server)
		
	
	def clientOriginateDial(self, session, object):
				
		log.info('MonAst.clientOriginateDial (%s) :: Running...' % session)
		Server = object['Server']
		src    = object['Source']
		dst    = object['Destination']

		command = {}
		command['Action']      = 'Originate'
		command['Channel']     = src
		command['Application'] = 'Dial'
		command['Data']        = '%s,30,rTt' % dst
		command['CallerID']    = MONAST_CALLERID
		
		log.debug('MonAst.clientOriginateDial (%s) :: From %s to %s on server %s' % (session, src, dst, Server))
		self.AMI.execute(Action = command, Server = Server)
		
		
	def clientHangupChannel(self, session, object):
		
		log.info('MonAst.clientHangupChannel (%s) :: Running...' % session)
		Server   = object['Server']
		Uniqueid = object['Uniqueid']
		
		try:
			Channel = self.channels[Server][Uniqueid]['Channel']
			command = {}
			command['Action']  = 'Hangup'
			command['Channel'] = Channel
			log.debug('MonAst.clientHangupChannel (%s) :: Hangup channel %s on server %s' % (session, Channel, Server))
			self.AMI.execute(Action = command, Server = Server)
		except:
			log.warn('MonAst.clientHangupChannel (%s) :: Uniqueid %s not found on self.channels[\'%s\']' % (session, Uniqueid, Server))
		
		
	def clientMonitorChannel(self, session, object):
		
		log.info('MonAst.clientMonitorChannel (%s) :: Running...' % session)
		Server   = object['Server']
		Uniqueid = object['Uniqueid']
		mix      = object['Mix']
		
		try:
			Channel = self.channels[Server][Uniqueid]['Channel']
			command = {}
			command['Action']  = 'Monitor'
			command['Channel'] = Channel
			command['File']    = 'MonAst-Monitor.%s' % Channel.replace('/', '-')
			command['Format']  = 'wav49'
			tt = 'without'
			if int(mix) == 1:
				command['Mix'] = 1
				tt = 'with'
			log.debug('MonAst.clientMonitorChannel (%s) :: Monitoring channel %s %s Mix on server %s' % (session, Channel, tt, Server))
			self.AMI.execute(Action = command, Server = Server)
		except:
			log.warn('MonAst.clientMonitorChannel (%s) :: Uniqueid %s not found on self.channels[\'%s\']' % (session, Uniqueid, Server))
		
		
	def clientMonitorStop(self, session, object):
		
		log.info('MonAst.clientMonitorStop (%s) :: Running...' % session)
		Server   = object['Server']
		Uniqueid = object['Uniqueid']
		
		try:
			self.channels[Server][Uniqueid]['Monitor'] = False
			Channel = self.channels[Server][Uniqueid]['Channel']
			command = {}
			command['Action'] = 'StopMonitor'
			command['Channel'] = Channel
			log.debug('MonAst.clientMonitorStop (%s) :: Stop Monitor on channel %s on server %s' % (session, Channel, Server))
			self.AMI.execute(Action = command, Server = Server)
		except:
			log.warn('MonAst.clientMonitorStop (%s) :: Uniqueid %s not found on self.channels[\'%s\']' % (session, Uniqueid, Server))
	
	
	def clientTransferCall(self, session, object):
		
		log.info('MonAst.clientTransferCall (%s) :: Running...' % session)
		Server = object['Server']
		src    = object['Source']
		dst    = object['Destination']
		type   = object['Type']

		Context      = self.servers[Server]['transfer_context']
		SrcChannel   = None
		ExtraChannel = None
		if type == 'peer':
			try:
				SrcChannel  = self.channels[Server][src]['Channel']
			except KeyError:
				log.error('MonAst.clientTransferCall (%s) :: Channel %s not found on self.channels[\'%s\']. Transfer failed! (peer)' % (session, src, Server))
				return
			tech, exten = dst.split('/')
			try:
				exten = int(exten)
			except:
				exten = self.monitoredUsers[Server][dst]['CallerID']
				exten = exten[exten.find('<')+1:exten.find('>')]
				
		elif type == 'meetme':
			try:
				tmp = src.split('+++')
				if len(tmp) == 2:
					SrcChannel   = self.channels[Server][tmp[0]]['Channel']
					ExtraChannel = self.channels[Server][tmp[1]]['Channel']
				else:
					SrcChannel   = self.channels[Server][tmp[0]]['Channel']
			except KeyError, e:
				log.error('MonAst.clientTransferCall (%s) :: Channel %s not found on self.channels[\'%s\']. Transfer failed! (meetme)' % (session, e, Server))
				return
			
			Context = self.servers[Server]['meetme_context']
			exten   = '%s%s' % (self.servers[Server]['meetme_prefix'], dst)

		command = {}
		command['Action']  = 'Redirect'
		command['Channel'] = SrcChannel
		if ExtraChannel:
			command['ExtraChannel'] = ExtraChannel
		command['Exten']    = exten
		command['Context']  = Context
		command['Priority'] = 1
		
		log.debug('MonAst.clientTransferCall (%s) :: Transferring %s and %s to %s@%s on server %s' % (session, SrcChannel, ExtraChannel, exten, Context, Server))
		self.AMI.execute(Action = command, Server = Server)
	
	
	def clientParkCall(self, session, object):

		log.info('MonAst.clientParkCall (%s) :: Running...' % session)
		Server   = object['Server']
		park     = object['Park']
		announce = object['Announce']

		ParkChannel   = self.channels[Server][park]['Channel']
		AnouceChannel = self.channels[Server][announce]['Channel']
		command = {}
		command['Action']   = 'Park'
		command['Channel']  = ParkChannel
		command['Channel2'] = AnouceChannel
		#ommand['Timeout'] = 45
		log.debug('MonAst.clientParkCall (%s) :: Parking Channel %s and announcing to %s on server %s' % (session, ParkChannel, AnouceChannel, Server))
		self.AMI.execute(Action = command, Server = Server)	
	
	
	def clientMeetmeKick(self, session, object):
		
		log.info('MonAst.clientMeetmeKick (%s) :: Running...' % session)
		Server  = object['Server']
		Meetme  = object['Meetme']
		Usernum = object['Usernum']
		
		command = {}
		command['Action']  = 'Command'
		command['Command'] = 'meetme kick %s %s' % (Meetme, Usernum)
		log.debug('MonAst.clientMeetmeKick (%s) :: Kiking usernum %s from meetme %s on server %s' % (session, Usernum, Meetme, Server))
		self.AMI.execute(Action = command, Server = Server)
	
	
	def clientParkedHangup(self, session, object):
		
		log.info('MonAst.clientParkedHangup (%s) :: Running...' % session)
		Server = object['Server']
		Exten  = object['Exten']
		
		try:
			Channel = self.parked[Server][Exten]['Channel']
			command = {}
			command['Action']  = 'Hangup'
			command['Channel'] = Channel
			log.debug('MonAst.clientParkedHangup (%s) :: Hangup parcked channel %s on server %s' % (session, Channel, Server))
			self.AMI.execute(Action = command, Server = Server)
		except:
			log.warn('MonAst.clientParkedHangup (%s) :: Exten %s not found on self.parked[\'%s\']' % (session, Exten, Server))
		
		
	def clientAddQueueMember(self, session, object):
		
		log.info('MonAst.clientAddQueueMember (%s) :: Running...' % session)
		Server = object['Server']
		queue  = object['Queue']
		member = object['Member']
		
		MemberName = self.monitoredUsers[Server][member]['CallerID']
		if MemberName == '--':
			MemberName = member
		command = {}
		command['Action']     = 'QueueAdd'
		command['Queue']      = queue
		command['Interface']  = member
		#command['Penalty']    = 10
		command['MemberName'] = MemberName
		log.debug('MonAst.clientAddQueueMember (%s) :: Adding member %s to queue %s on server %s' % (session, member, queue, Server))
		self.AMI.execute(Action = command, Server = Server)
		
		
	def clientRemoveQueueMember(self, session, object):
		
		log.info('MonAst.clientRemoveQueueMember (%s) :: Running...' % session)
		Server = object['Server']
		queue  = object['Queue']
		member = object['Member']
		
		command = {}
		command['Action']    = 'QueueRemove'
		command['Queue']     = queue
		command['Interface'] = member
		log.debug('MonAst.clientRemoveQueueMember (%s) :: Removing member %s from queue %s on server %s' % (session, member, queue, Server))
		self.AMI.execute(Action = command, Server = Server)
		
		
	def clientPauseQueueMember(self, session, object):
		
		log.info('MonAst.clientPauseQueueMember (%s) :: Running...' % session)
		Server = object['Server']
		queue  = object['Queue']
		member = object['Member']
		
		command = {}
		command['Action']    = 'QueuePause'
		command['Queue']     = queue
		command['Interface'] = member
		command['Paused']    = 1
		log.debug('MonAst.clientAddQueueMember (%s) :: Pausing member %s on queue %s on server %s' % (session, member, queue, Server))
		self.AMI.execute(Action = command, Server = Server)
		
		
	def clientUnpauseQueueMember(self, session, object):
		
		log.info('MonAst.clientPauseQueueMember (%s) :: Running...' % session)
		Server = object['Server']
		queue  = object['Queue']
		member = object['Member']
		
		command = {}
		command['Action']    = 'QueuePause'
		command['Queue']     = queue
		command['Interface'] = member
		command['Paused']    = 0
		log.debug('MonAst.clientUnpauseQueueMember (%s) :: Unpausing member %s on queue %s on server %s' % (session, member, queue, Server))
		self.AMI.execute(Action = command, Server = Server)
		
		
	def clientSkypeLogin(self, session, object):
		
		log.info('MonAst.clientSkypeLogin (%s) :: Running...' % session)
		Server    = object['Server']
		skypeName = object['SkypeName']
		
		command = {}
		command['Action']  = 'Command'
		command['Command'] = 'skype login user %s' % skypeName
		log.debug('MonAst.clientSkypeLogin (%s) :: Login skype user %s on server %s' % (session, skypeName, Server))
		self.AMI.execute(Action = command, Server = Server)
	
	
	def clientSkypeLogout(self, session, object):
		
		log.info('MonAst.clientSkypeLogout (%s) :: Running...' % session)
		Server    = object['Server']
		skypeName = object['SkypeName']
		
		command = {}
		command['Action']  = 'Command'
		command['Command'] = 'skype logout user %s' % skypeName
		log.debug('MonAst.clientSkypeLogout (%s) :: Logout skype user %s on server %s' % (session, skypeName, Server))
		self.AMI.execute(Action = command, Server = Server)
		
	
	def clientCliCommand(self, session, object):
		
		log.info('MonAst.clientCliCommand (%s) :: Running...' % session)
		Server     = object['Server']
		cliCommand = object['CliCommand']
		
		command = {}
		command['Action']   = 'Command'
		command['Command']  = cliCommand
		command['ActionID'] = object['Session']
		log.debug('MonAst.clientCliCommand (%s) :: Executing CLI command: %s on server %s' % (session, cliCommand, Server))
		self.AMI.execute(Action = command, Handler = self.handlerCliCommand, Server = Server)
	
	
	def clientCheckAmiAuth(self, session, username, password):
		
		log.info('MonAst.clientCheckAmiAuth (%s) :: Running...' % session)
		
		def onSuccess(auth):
			Server, auth, roles = auth
			self.amiAuthCheck[session][Server] = (auth, roles)
			
		def onFailure(auth):
			Server, auth, roles = auth
			self.amiAuthCheck[session][Server] = (auth, roles)
			
		def onError(*args, **kwargs):
			Server = kwargs['Server']
			self.amiAuthCheck[session][Server] = (False, [])
		
		self.amiAuthCheck[session] = {}
		for Server in self.servers:
			self.amiAuthCheck[session][Server] = False
			c = protocol.ClientCreator(reactor, SimpleAmiAuthenticator, server = Server, username = username, password = password, onSuccess = onSuccess, onFailure = onFailure)
			d = c.connectTCP(self.servers[Server]['hostname'], self.servers[Server]['hostport'], 5)
			d.addErrback(onError, Server = Server)
			

	def onAuthenticationAccepted(self, message):
		
		log.info('MonAst.onAuthenticationAccepted :: Running for Server %s' % message['Server'])
		self._GetConfig(message['Server'])
		
	
	def _GetConfig(self, Server = None, sendReload = True):
		
		log.info('MonAst._GetConfig :: Requesting Asterisk Configuration (reload clients: %s)' % sendReload)
		
		servers = self.servers.keys()
		if Server:
			servers = [Server]
		
		for Server in servers:
			users = self.monitoredUsers[Server].keys()
			for user in users:
				if not self.monitoredUsers[Server][user].has_key('forced'):
					del self.monitoredUsers[Server][user]
		
		for Server in servers:
			self.meetme[Server]   = {}
			self.parked[Server]   = {}
			self.queues[Server]   = {}
			self.calls[Server]    = {}
			self.channels[Server] = {}
		
			self.AMI.execute(Action = {'Action': 'SIPpeers'}, Server = Server)
			self.AMI.execute(Action = {'Action': 'IAXpeers'}, Handler = self.handlerParseIAXPeers, Server = Server)
			self.AMI.execute(Action = {'Action': 'Command', 'Command': 'skype show users'}, Handler = self.handlerParseSkypeUsers, Server = Server)
			self.AMI.execute(Action = {'Action': 'GetConfig', 'Filename': 'meetme.conf'}, Handler = self.handlerGetConfigMeetme, Server = Server)
			self.AMI.execute(Action = {'Action': 'QueueStatus'}, Server = Server)
		
		#self._taskCheckStatus.stop()
		#self._taskCheckStatus.start(60, False)
		reactor.callLater(2, self.taskCheckStatus, Server = Server)
		
		# Meetme and Parked Status will be parsed after handlerStatusComplete
		self.getMeetmeAndParkStatus[Server] = True

		if sendReload:
			#for session in self.clientQueues:
			#	self.clientQueues[session]['q'].put(self.parseJson(Action = 'Reload', Time = 10000))
			self.enqueue(Action = 'Reload', Time = 10000)
	
	
	def clearStatus(self):
		
		log.info('MonAst.clearStatus :: Cleaning all servers status')
		
		self.userDisplay       = {}
		self.monitoredUsers    = {}
		self.parked            = {}
		self.meetme            = {}
		self.calls             = {}
		self.channels          = {}
		self.queuesDisplay     = {}
		self.queues            = {}
		self.queueMemberCalls  = {}
		self.queueMemberPaused = {}
		
		for server in self.servers:
			self.userDisplay[server]       = {}
			self.monitoredUsers[server]    = {}
			self.parked[server]            = {}
			self.meetme[server]            = {}
			self.calls[server]             = {}
			self.channels[server]          = {}
			self.queuesDisplay[server]     = {}
			self.queues[server]            = {}
			self.queueMemberCalls[server]  = {}
			self.queueMemberPaused[server] = {}
	
	
	def start(self):
		
		signal.signal(signal.SIGUSR1, self._sigUSR1)
		signal.signal(signal.SIGTERM, self._sigTERM)
		signal.signal(signal.SIGINT, self._sigTERM)
		signal.signal(signal.SIGHUP, self._sigHUP)
		
		self.AMI.start()
		
		reactor.listenTCP(self.bindPort, self)
		reactor.run()
			
		self.running = False
			
		self.AMI.close()
		
		log.log(logging.NOTICE, 'Monast :: Finished...')
	
	
	def _sigUSR1(self, *args):
		
		log.log(logging.NOTICE, 'MonAst :: Received SIGUSR1 -- Dumping Vars...')
	
		log.log(logging.NOTICE, 'self.monitoredUsers = %s' % repr(self.monitoredUsers))
		log.log(logging.NOTICE, 'self.meetme = %s' % repr(self.meetme))
		log.log(logging.NOTICE, 'self.parked = %s' % repr(self.parked))
		log.log(logging.NOTICE, 'self.queues = %s' % repr(self.queues))
		log.log(logging.NOTICE, 'self.queueMemberStatus = %s' % repr(self.queueMemberStatus))
		log.log(logging.NOTICE, 'self.queueMemberCalls = %s' % repr(self.queueMemberCalls))
		log.log(logging.NOTICE, 'self.queueClientStatus = %s' % repr(self.queueClientStatus))
		log.log(logging.NOTICE, 'self.channels = %s' % repr(self.channels))
		log.log(logging.NOTICE, 'self.calls = %s' % repr(self.calls))
		
		
	def _sigTERM(self, *args):
		
		log.log(logging.NOTICE, 'MonAst :: Received SIGTERM -- Shutting Down...')
		self.running = False
		self.AMI.close()
		self.stopFactory()
		reactor.stop()
		
		
	def _sigHUP(self, *args):
		
		log.log(logging.NOTICE, 'MonAst :: Received SIGHUP -- Reloading...')
		if self.reloading:
			log.log(logging.NOTICE, 'MonAst._sigHUP :: Already reloading...')
			return
			
		self.reloading = True
		
		self.enqueue(Action = 'Reload', Time = 10000)

		self.AMI.close()
		
		self.clearStatus()
		
		self.parseConfig()
		
		#self.AMI.start()
		reactor.callLater(1, self.AMI.start)
		
		self.reloading = False	
	
	
if __name__ == '__main__':

	opt = optparse.OptionParser()
	opt.add_option('-c', '--config',
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
	opt.add_option('--colored',
		dest   = "colored",
		action = "store_true",
		help   = "display colored log messages"
	)
	opt.add_option('-d', '--daemon',
		dest   = "daemon",
		action = "store_true",
		help   = "deamonize (fork in background)"
	)
	opt.add_option('-l', '--logfile',
		dest    = "logfile",
		default = "/var/log/monast.log",
		help    = "use this log file instead of /var/log/monast.log"
	)
	
	(options, args) = opt.parse_args()

	if not options.configFile.startswith('/'):
		options.configFile = '%s/%s' % (START_PATH, options.configFile)

	if not options.logfile.startswith('/'):
		options.logfile = '%s/%s' % (START_PATH, options.logfile)

	if not os.path.exists(options.configFile):
		print '  Config file "%s" not found.' % options.configFile
		print '  Run "%s --help" for help.' % sys.argv[0]
		sys.exit(1)

	if options.daemon:
		createDaemon()

	if options.info:
		logging.getLogger("").setLevel(logging.INFO)
		
	if options.debug:
		logging.getLogger("").setLevel(logging.DEBUG)
	
	basicLogFormat = "[%(asctime)s] %(levelname)-8s :: %(message)s"
	
	if options.colored:
		logging.COLORED = True
		basicLogFormat  = "[%(asctime)s] %(levelname)-19s :: %(message)s"
	
	fmt  = ColorFormatter(basicLogFormat, '%a %b %d %H:%M:%S %Y')
	hdlr = None
	if options.daemon:
		hdlr = logging.FileHandler(options.logfile)
	else:
		hdlr = logging.StreamHandler(sys.stdout)
	hdlr.setFormatter(fmt)
	if (len(logging.getLogger("").handlers) == 1):
		logging.getLogger("").handlers[0] = hdlr
	else:
		logging.getLogger("").addHandler(hdlr)
	
	log = logging.getLogger("MonAst")

	monast = MonAst(options.configFile)
	monast.start()

	hdlr.close()
