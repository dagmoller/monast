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
import thread
import threading
import traceback
import socket
import signal
import random
import Queue
import logging
import optparse
from AsteriskManager import AsteriskManager
from ConfigParser import SafeConfigParser, NoOptionError

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
	
	
class MonAst:
	
	##
	## Internal Params
	##
	
	running         = True
	reloading       = False
	
	configFile      = None
	
	AMI             = None
	
	bindHost        = None
	bindPort        = None
	socketClient    = None
	
	defaultContext  = None
	transferContext = None
	
	meetmeContext   = None
	meetmePrefix    = None
	
	userDisplay     = {}
	
	#enqueue        = Queue.Queue()
	
	clientSocks    = {}
	clientQueues   = {}
	parked         = {}
	meetme         = {}
	calls          = {}
	channels       = {}
	monitoredUsers = {}
	queues         = {}

	clientSockLock     = threading.RLock()
	clientQueuelock    = threading.RLock()
	parkedLock         = threading.RLock()
	meetmeLock         = threading.RLock()
	callsLock          = threading.RLock()
	channelsLock       = threading.RLock()
	monitoredUsersLock = threading.RLock()
	queuesLock         = threading.RLock()
	
	channelStatus = []
	
	queueMemberStatus = {}
	queueClientStatus = {}
	
	queueMemberCalls  = {}
	
	queueStatusFirst = False
	queueStatusOrder = []
	
	getMeetmeAndParkStatus = False
	getChannelsCallsStatus = False
	
	sortby = 'callerid'
	
	##
	## Class Initialization
	##
	def __init__(self, configFile):
		
		log.log(logging.NOTICE, 'MonAst :: Initializing...')
		
		self.configFile = configFile
		self.parseConfig()
		
	
	def list2Dict(self, lines):
		dic = {}
		for line in lines:
			tmp = line.split(':')
			if len(tmp) == 1:
				dic[tmp[0].strip()] = ''
			elif len(tmp) == 2:
				dic[tmp[0].strip()] = tmp[1].strip()
			elif len(tmp) >= 3:
				dic[tmp[0].strip()] = ''.join(tmp[1:])
									
		return dic
	
	
	def parseConfig(self):
		
		log.log(logging.NOTICE, 'MonAst.parseConfig :: Parsing config')
		
		cp = MyConfigParser()
		cp.read(self.configFile)
		
		host     = cp.get('global', 'hostname')
		port     = int(cp.get('global', 'hostport'))
		username = cp.get('global', 'username')
		password = cp.get('global', 'password')
		
		self.bindHost       = cp.get('global', 'bind_host')
		self.bindPort       = int(cp.get('global', 'bind_port'))
		
		self.defaultContext  = cp.get('global', 'default_context')
		self.transferContext = cp.get('global', 'transfer_context')
		
		self.meetmeContext = cp.get('global', 'meetme_context')
		self.meetmePrefix  = cp.get('global', 'meetme_prefix')
		
		try:
			self.sortby = cp.get('users', 'sortby')
		except NoOptionError:
			self.sortby = 'callerid'
			log.error("No option 'sortby' in section: 'users' of config file, sorting by CallerID")
		
		if cp.get('users', 'default') == 'show':
			self.userDisplay['DEFAULT'] = True 
		else:
			self.userDisplay['DEFAULT'] = False
		
		for user, display in cp.items('users'):
			if user.startswith('SIP') or user.startswith('IAX2'): 
				if (self.userDisplay['DEFAULT'] and display == 'hide') or (not self.userDisplay['DEFAULT'] and display == 'show'):
					self.userDisplay[user] = True
			
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
				
				self.monitoredUsers[user] = {
					'Channeltype': tech, 'Status': Status, 'Calls': 0, 'CallerID': CallerID, 'Context': self.defaultContext, 'Variables': [], 'forced': True
				}
				
		try:
			self.socketClient = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			self.socketClient.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
			self.socketClient.bind((self.bindHost, self.bindPort))
			self.socketClient.listen(10)
		except socket.error, e:
			log.error("MonAst.__init__ :: Cound not open socket on port %d, cause: %s" % (self.bindPort, e))
			sys.exit(1)
			
		self.AMI = AsteriskManager(host, port, username, password)
		
		self.AMI.registerEventHandler('_AUTHENTICATED', self._GetConfig)
		
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
		
	
	def threadSocketClient(self, name, params):
		
		log.info('MonAst.threadClientSocket :: Starting Thread...')
		while self.running:
			try:
				(sc, addr) = self.socketClient.accept()
				log.info('MonAst.threadSocketClient :: New client connection: %s' % str(addr))
				self.clientSockLock.acquire()
				threadId  = 'threadClient-%s' % random.random()
				self.clientSocks[threadId] = thread.start_new_thread(self.threadClient, (threadId, sc, addr))
				self.clientSockLock.release()
			except:
				if not self.reloading:
					log.exception('MonAst.threadClientSocket :: Unhandled Exception')
				
				
	def threadClient(self, threadId, sock, addr):
		
		log.info('MonAst.threadClient (%s) :: Starting Thread...' % threadId)
		session      = None
		localRunning = True
		count        = 0
		
		try:
			while self.running and localRunning:
				message = sock.recv(1024)
				if message.strip():
					messages = message.strip().split('\r\n')
					for message in messages:
						log.debug('MonAst.threadClient (%s) :: Received: %s' % (threadId, message))
						
						output = []
						object = {'Action': None}
						try:
							object = json.loads(message)
						except:
							pass
						
						if message.upper().startswith('SESSION: '):
							session = message[9:]
							self.clientQueuelock.acquire()
							try:
								self.clientQueues[session]['t'] = time.time()
								output.append('OK')
							except KeyError:
								self.clientQueues[session] = {'q': Queue.Queue(), 't': time.time()}
								output.append('NEW SESSION')
								log.log(logging.NOTICE, 'MonAst.threadClient (%s) :: New client session: %s' % (threadId, session))
							self.clientQueuelock.release()
						
						elif session and message.upper() == 'GET STATUS':
							output = self.clientGetStatus(threadId, session)
						
						elif session and message.upper() == 'GET CHANGES':
							output = self.clientGetChanges(threadId, session)
						
						elif session and object['Action'] == 'OriginateCall':
							self.clientOriginateCall(threadId, object)
							
						elif session and object['Action'] == 'OriginateDial':
							self.clientOriginateDial(threadId, object)
							
						elif session and object['Action'] == 'HangupChannel':
							self.clientHangupChannel(threadId, object)
							
						elif session and object['Action'] == 'MonitorChannel':
							self.clientMonitorChannel(threadId, object)
							
						elif session and object['Action'] == 'MonitorStop':
							self.clientMonitorStop(threadId, object)
						
						elif session and object['Action'] == 'TransferCall':
							self.clientTransferCall(threadId, object)
						
						elif session and object['Action'] == 'ParkCall':
							self.clientParkCall(threadId, object)
						
						elif session and object['Action'] == 'MeetmeKick':
							self.clientMeetmeKick(threadId, object)
						
						elif session and object['Action'] == 'ParkedHangup':
							self.clientParkedHangup(threadId, object)
							
						elif session and object['Action'] == 'AddQueueMember':
							self.clientAddQueueMember(threadId, object)
							
						elif session and object['Action'] == 'RemoveQueueMember':
							self.clientRemoveQueueMember(threadId, object)
							
						elif session and object['Action'] == 'PauseQueueMember':
							self.clientPauseQueueMember(threadId, object)
							
						elif session and object['Action'] == 'UnpauseQueueMember':
							self.clientUnpauseQueueMember(threadId, object)
						
						elif session and object['Action'] == 'SkypeLogin':
							self.clientSkypeLogin(threadId, object)
							
						elif session and object['Action'] == 'SkypeLogout':
							self.clientSkypeLogout(threadId, object)
						
						elif session and object['Action'] == 'CliCommand':
							self.clientCliCommand(threadId, object, session)
						
						elif message.upper() == 'BYE':
							localRunning = False
							
						else:
							output.append('NO SESSION')
							
						## Send messages to client
						if len(output) > 0:
							#log.debug('MonAst.threadClient (%s) :: Sending: %s\r\n' % (threadId, '\r\n'.join(output)))
							#sock.send('%s\r\n' % '\r\n'.join(output))
							log.debug('MonAst.threadClient (%s) :: Sending: %s' % (threadId, '\r\n'.join(output)))
							sock.send('\r\n'.join(output))
				
				else:
					count += 1
					if count == 10:
						log.error('MonAst.threadClient (%s) :: Lost connection, dropping client.' % threadId)
						break
					
		except socket.error, e:
			log.error('MonAst.threadClient (%s) :: Socket Error: %s' % (threadId, e))
		except:
			log.exception('MonAst.threadClient (%s) :: Unhandled Exception' % threadId)
			
		try:
			sock.close()
		except:
			pass
		
		log.info('MonAst.threadClient (%s) :: Finishing Thread...' % threadId)
		
		self.clientSockLock.acquire()
		del self.clientSocks[threadId]
		self.clientSockLock.release()
		
		
	def threadClientQueueRemover(self, name, params):
		
		log.info('MonAst.threadClientQueueRemover :: Starting Thread...')
		while self.running:
			time.sleep(60)
			self.clientQueuelock.acquire()
			dels = []
			now = time.time()
			for session in self.clientQueues:
				past = self.clientQueues[session]['t']
				if int(now - past) > 600:
					dels.append(session)
			for session in dels:
				log.log(logging.NOTICE, 'MonAst.threadClientQueueRemover :: Removing dead client session: %s' % session)
				del self.clientQueues[session]
			self.clientQueuelock.release()
			
			
	def threadCheckStatus(self, name, params):
		
		log.info('MonAst.threadCheckStatus :: Starting Thread...')
		time.sleep(10)
		count = 60
		while self.running:
			time.sleep(1)
			if self.getChannelsCallsStatus:
				self.getChannelsCallsStatus = False
				time.sleep(10)
			elif count < 60:
				count += 1
				continue
			
			count = 0
			
			log.info('MonAst.threadCheckStatus :: Requesting Status...')
			if not self.AMI.isConnected or not self.AMI.isAuthenticated:
				log.warning('MonAst.threadCheckStatus :: AMI Not Connected...')
				continue
			
			self.channelStatus = []
			self.AMI.execute(['Action: Status']) # generate Event: Status
			
			self.queuesLock.acquire()
			for queue in self.queues:
				self.queueStatusOrder.append(queue)
				self.queueMemberStatus[queue] = []
				self.queueClientStatus[queue] = []
				self.AMI.execute(['Action: QueueStatus', 'Queue: %s' % queue])
			self.queuesLock.release()
	
	
	def enqueue(self, **args):
		
		self.clientQueuelock.acquire()
		if args.has_key('__session'):
			session = args['__session']
			del args['__session']
			self.clientQueues[session]['q'].put(json.dumps(args))
		else:
			for session in self.clientQueues:
				self.clientQueues[session]['q'].put(json.dumps(args))
		self.clientQueuelock.release()
		
		
	def parseJson(self, **args):
		
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
		techs           = {}
		for user in self.monitoredUsers:
			tech, peer   = user.split('/')
			
			CallerID     = self.monitoredUsers[user]['CallerID']
			CallerIDName = peer
			CallerIDNum  = peer
			
			if CallerID != '--':
				CallerIDName = CallerID[:CallerID.find('<')].strip()
				CallerIDNum  = CallerID[CallerID.find('<')+1:CallerID.find('>')].strip()
			else:
				CallerID = peer
				
			try:
				techs[tech].append((user, peer, CallerID, CallerIDName, CallerIDNum))
			except KeyError:
				techs[tech] = [(user, peer, CallerID, CallerIDName, CallerIDNum)]

		for tech in techs:
			if self.sortby in ('callerid', 'calleridname', 'calleridnum'):
				usersWithCid    = []
				usersWithoutCid = []
				for user in techs[tech]:
					if user[1] != user[2]:
						usersWithCid.append(user)
					else:
						usersWithoutCid.append(user)
				usersWithCid.sort(lambda x, y: cmp(x[_sortKeys[self.sortby]].lower(), y[_sortKeys[self.sortby]].lower()))
				usersWithoutCid.sort(lambda x, y: cmp(x[_sortKeys[self.sortby]].lower(), y[_sortKeys[self.sortby]].lower()))
				techs[tech] = usersWithCid + usersWithoutCid
			else:
				techs[tech].sort(lambda x, y: cmp(x[_sortKeys[self.sortby]].lower(), y[_sortKeys[self.sortby]].lower()))
				
		return techs
		
	
	##
	## AMI Handlers for Events
	##
	def handlerReload(self, lines):
		
		log.info('MonAst.handlerReload :: Running...')
		self._GetConfig()
		
		
	def handlerChannelReload(self, lines):
		
		log.info('MonAst.handlerChannelReload :: Running...')
		dic = self.list2Dict(lines)
		
		Channel      = dic.get('ChannelType', dic.get('Channel'))
		ReloadReason = dic['ReloadReason']
		
		self._GetConfig()
		
		
	def handlerPeerEntry(self, lines):
		
		log.info('MonAst.handlerPeerEntry :: Running...')
		dic = self.list2Dict(lines)
		
		Status      = dic['Status']
		Channeltype = dic['Channeltype']
		ObjectName  = dic['ObjectName'].split('/')[0]
		
		if Status.startswith('OK'):
			Status = 'Registered'
		elif Status.find('(') != -1:
			Status = Status[0:Status.find('(')]
		
		self.monitoredUsersLock.acquire()
		user = '%s/%s' % (Channeltype, ObjectName)
		
		if self.userDisplay['DEFAULT'] and not self.userDisplay.has_key(user):
			self.monitoredUsers[user] = {'Channeltype': Channeltype, 'Status': Status, 'Calls': 0, 'CallerID': '--', 'Context': 'default', 'Variables': []}
		elif not self.userDisplay['DEFAULT'] and self.userDisplay.has_key(user):
			self.monitoredUsers[user] = {'Channeltype': Channeltype, 'Status': Status, 'Calls': 0, 'CallerID': '--', 'Context': 'default', 'Variables': []}
		else:
			user = None
		
		if user:
			type = ['peer', 'user'][Channeltype == 'Skype']
			self.AMI.execute(['Action: Command', 'Command: %s show %s %s' % (Channeltype.lower(), type, ObjectName)], self._defaultParseConfigPeers, user)
		
		self.monitoredUsersLock.release()
		
	
	def handlerPeerStatus(self, lines):
		
		log.info('MonAst.handlerPeerStatus :: Running...')
		dic = self.list2Dict(lines)
		
		Peer       = dic['Peer']
		PeerStatus = dic['PeerStatus']
		
		self.monitoredUsersLock.acquire()
		if self.monitoredUsers.has_key(Peer):
			mu = self.monitoredUsers[Peer]
			mu['Status'] = PeerStatus
			self.enqueue(Action = 'PeerStatus', Peer = Peer, Status = mu['Status'], Calls = mu['Calls'])
		self.monitoredUsersLock.release()
		
		
	def handlerSkypeAccountStatus(self, lines):
		
		log.info('MonAst.handlerSkypeAccountStatus :: Running...')
		dic = self.list2Dict(lines)
		
		Username = 'Skype/%s' % dic['Username']
		Status   = dic['Status']
		
		self.monitoredUsersLock.acquire()
		if self.monitoredUsers.has_key(Username):
			mu = self.monitoredUsers[Username]
			mu['Status'] = Status
			self.enqueue(Action = 'PeerStatus', Peer = Username, Status = mu['Status'], Calls = mu['Calls'])
		self.monitoredUsersLock.release()
				
					
	def handlerBranchOnHook(self, lines): 

		log.info('MonAst.handlerBranchOnHook :: Running... (On)')
		dic = self.list2Dict(lines) 

		Channel = dic['Channel']

		self.monitoredUsersLock.acquire()
		user = Channel
		if Channel.rfind('-') != -1:
			user = Channel[:Channel.rfind('-')]
		if self.monitoredUsers.has_key(user):
			mu           = self.monitoredUsers[user]
			mu['Calls']  = 0
			mu['Status'] = "Not in Use"
			self.enqueue(Action = 'PeerStatus', Peer = user, Status = mu['Status'], Calls = mu['Calls'])
		self.monitoredUsersLock.release()


	def handlerBranchOffHook(self, lines):

		log.info('MonAst.handlerBranchOffHook :: Running... (Off)')
		dic = self.list2Dict(lines)

		Channel = dic['Channel']
		
		self.monitoredUsersLock.acquire()
		user = Channel
		if Channel.rfind('-') != -1:
			user = Channel[:Channel.rfind('-')]
		if self.monitoredUsers.has_key(user):
			mu           = self.monitoredUsers[user]
			mu['Status'] = "In Use"
			self.enqueue(Action = 'PeerStatus', Peer = user, Status = mu['Status'], Calls = mu['Calls'])
		self.monitoredUsersLock.release()
	
	
	def handlerNewchannel(self, lines):
		
		log.info('MonAst.handlerNewchannel :: Running...')
		dic = self.list2Dict(lines)
		
		Channel      = dic['Channel']
		State        = dic.get('ChannelStateDesc', dic.get('State'))
		CallerIDNum  = dic['CallerIDNum']
		CallerIDName = dic['CallerIDName']
		Uniqueid     = dic['Uniqueid']
		Monitor      = False
					
		self.channelsLock.acquire()
		self.monitoredUsersLock.acquire()
		
		self.channels[Uniqueid] = {'Channel': Channel, 'State': State, 'CallerIDNum': CallerIDNum, 'CallerIDName': CallerIDName, 'Monitor': Monitor}
		self.enqueue(Action = 'NewChannel', Channel = Channel, State = State, CallerIDNum = CallerIDNum, CallerIDName = CallerIDName, Uniqueid = Uniqueid, Monitor = Monitor)
		
		user = Channel
		if Channel.rfind('-') != -1:
			user = Channel[:Channel.rfind('-')]
		if self.monitoredUsers.has_key(user):
			mu           = self.monitoredUsers[user]
			mu['Calls'] += 1
			self.enqueue(Action = 'PeerStatus', Peer = user, Status = mu['Status'], Calls = mu['Calls'])

		self.monitoredUsersLock.release()
		self.channelsLock.release()
		
		
	def handlerNewstate(self, lines):
		
		log.info('MonAst.handlerNewstate :: Running...')
		dic = self.list2Dict(lines)
		
		Channel      = dic['Channel']
		State        = dic.get('ChannelStateDesc', dic.get('State'))
		CallerID     = dic.get('CallerIDNum', dic.get('CallerID'))
		CallerIDName = dic['CallerIDName']
		Uniqueid     = dic['Uniqueid']
					
		self.channelsLock.acquire()
		try:
			self.channels[Uniqueid]['State']        = State
			self.channels[Uniqueid]['CallerIDNum']  = CallerID
			self.channels[Uniqueid]['CallerIDName'] = CallerIDName
			self.enqueue(Action = 'NewState', Channel = Channel, State = State, CallerID = CallerID, CallerIDName = CallerIDName, Uniqueid = Uniqueid)
		except:
			log.warning("MonAst.handlerNewstate :: Uniqueid %s not found on self.channels" % Uniqueid)
		self.channelsLock.release()
		
		
	def handlerHangup(self, lines):
		
		log.info('MonAst.handlerHangup :: Running...')
		dic = self.list2Dict(lines)
		
		Channel   = dic['Channel']
		Uniqueid  = dic['Uniqueid']
		Cause     = dic['Cause']
		Cause_txt = dic['Cause-txt']
					
		self.channelsLock.acquire()
		self.callsLock.acquire()
		self.monitoredUsersLock.acquire()
		self.queuesLock.acquire()
		
		try:
			del self.channels[Uniqueid]
			self.enqueue(Action = 'Hangup', Channel = Channel, Uniqueid = Uniqueid, Cause = Cause, Cause_txt = Cause_txt)
		except:
			log.warning("MonAst.handlerHangup :: Channel %s not found on self.channels" % Uniqueid)
		
		toDelete = None
		for id in self.calls:
			if Uniqueid in id and self.calls[id]['Status'] in ('Dial', 'Unlink'):
				toDelete = id
				break
		if toDelete:
			del self.calls[toDelete]
			src, dst = toDelete
			self.enqueue(Action = 'Unlink', Channel1 = None, Channel2 = None, Uniqueid1 = src, Uniqueid2 = dst, CallerID1 = None, CallerID2 = None)
		
		user = Channel
		if Channel.rfind('-') != -1:
			user = Channel[:Channel.rfind('-')]
		if self.monitoredUsers.has_key(user) and self.monitoredUsers[user]['Calls'] > 0:
			mu           = self.monitoredUsers[user] 
			mu['Calls'] -= 1
			self.enqueue(Action = 'PeerStatus', Peer = user, Status = mu['Status'], Calls = mu['Calls'])
		
		if self.queueMemberCalls.has_key(Uniqueid):
			Queue  = self.queueMemberCalls[Uniqueid]['Queue']
			Member = self.queueMemberCalls[Uniqueid]['Member']
			del self.queueMemberCalls[Uniqueid]
			self.enqueue(Action = 'RemoveQueueMemberCall', Queue = Queue, Member = Member, Uniqueid = Uniqueid)

		self.queuesLock.release()
		self.monitoredUsersLock.release()
		self.callsLock.release()
		self.channelsLock.release()
		
		
	def handlerDial(self, lines):
		
		log.info('MonAst.handlerDial :: Running...')
		dic = self.list2Dict(lines)
		
		self.callsLock.acquire()
		self.channelsLock.acquire()
		self.queuesLock.acquire()
		
		SubEvent = dic.get('SubEvent', None)
		if SubEvent == 'Begin':
			Source       = dic.get('Channel', dic.get('Source'))
			Destination  = dic['Destination']
			CallerID     = dic.get('CallerIDNum', dic.get('CallerID'))
			CallerIDName = dic['CallerIDName']
			SrcUniqueID  = dic.get('UniqueID', dic.get('SrcUniqueID'))
			DestUniqueID = dic['DestUniqueID']
						
			c = self.channels[SrcUniqueID]
			self.calls[(SrcUniqueID, DestUniqueID)] = {
				'Source': Source, 'Destination': Destination, 'SrcUniqueID': SrcUniqueID, 'DestUniqueID': DestUniqueID, 
				'Status': 'Dial', 'startTime': 0
			}
			
			self.enqueue(Action = 'Dial', Source = Source, Destination = Destination, CallerID = CallerID, CallerIDName = CallerIDName, SrcUniqueID = SrcUniqueID, DestUniqueID = DestUniqueID)
		
		elif SubEvent == 'End':
			Channel  = dic['Channel']
			Uniqueid = dic['UniqueID']
			
			calls = self.calls.keys()
			for call in calls:
				if Uniqueid in call:
					#del self.calls[call]
					self.calls[call]['Status'] == 'Unlink'
					self.enqueue(Action = 'Unlink', Channel1 = None, Channel2 = None, Uniqueid1 = call[0], Uniqueid2 = call[1], CallerID1 = None, CallerID2 = None)
			
			if self.queueMemberCalls.has_key(Uniqueid):
				self.queueMemberCalls[Uniqueid]['Link'] = False
				qmc = self.queueMemberCalls[Uniqueid]
				self.enqueue(Action = 'RemoveQueueMemberCall', Queue = qmc['Queue'], Member = qmc['Member'], Uniqueid = Uniqueid)
			
		else:
			log.info('MonAst.handlerDial :: Unhandled Dial subevent %s' % SubEvent)
		
		self.queuesLock.release()
		self.channelsLock.release()
		self.callsLock.release()
		
		
	def handlerLink(self, lines):
		
		log.info('MonAst.handlerLink :: Running...')
		dic = self.list2Dict(lines)
		
		Channel1  = dic['Channel1']
		Channel2  = dic['Channel2']
		Uniqueid1 = dic['Uniqueid1']
		Uniqueid2 = dic['Uniqueid2']
		CallerID1 = dic['CallerID1']
		CallerID2 = dic['CallerID2']
		
		self.channelsLock.acquire()
		self.callsLock.acquire()
		self.queuesLock.acquire()
		
		try:
			CallerID1 = '%s <%s>' % (self.channels[Uniqueid1]['CallerIDName'], self.channels[Uniqueid1]['CallerIDNum'])
			CallerID2 = '%s <%s>' % (self.channels[Uniqueid2]['CallerIDName'], self.channels[Uniqueid2]['CallerIDNum'])
		except:
			log.warning("MonAst.handlerUnlink :: Uniqueid %s or %s not found on self.channels" % (Uniqueid1, Uniqueid2))
		
		call = (Uniqueid1, Uniqueid2)
		
		try:
			self.calls[call]['Status'] = 'Link'
			 
			if self.calls[call]['startTime'] == 0:
				self.calls[call]['startTime'] = time.time()
		except:
			self.calls[call] = {
				'Source': Channel1, 'Destination': Channel2, 'SrcUniqueID': Uniqueid1, 'DestUniqueID': Uniqueid2, 
				'Status': 'Link', 'startTime': time.time()
			}
		Seconds = time.time() - self.calls[call]['startTime']
		self.enqueue(Action = 'Link', Channel1 = Channel1, Channel2 = Channel2, Uniqueid1 = Uniqueid1, Uniqueid2 = Uniqueid2, CallerID1 = CallerID1, CallerID2 = CallerID2, Seconds = Seconds)

		if self.queueMemberCalls.has_key(Uniqueid1):
			self.queueMemberCalls[Uniqueid1]['Member'] = Channel2[:Channel2.rfind('-')]
			self.queueMemberCalls[Uniqueid1]['Link']   = True
			qmc = self.queueMemberCalls[Uniqueid1]
			self.enqueue(Action = 'AddQueueMemberCall', Queue = qmc['Queue'], Member = qmc['Member'], Uniqueid = Uniqueid1, Channel = qmc['Channel'], CallerID = CallerID1, Seconds = Seconds)
		
		self.queuesLock.release()
		self.callsLock.release()
		self.channelsLock.release()
		
		
	def handlerBridge(self, lines):
		
		log.info('MonAst.handlerBridge :: Running...')
		self.handlerLink(lines)
		
		
	def handlerUnlink(self, lines):
		
		log.info('MonAst.handlerUnlink :: Running...')
		dic = self.list2Dict(lines)
		
		Channel1  = dic['Channel1']
		Channel2  = dic['Channel2']
		Uniqueid1 = dic['Uniqueid1']
		Uniqueid2 = dic['Uniqueid2']
		CallerID1 = dic['CallerID1']
		CallerID2 = dic['CallerID2']
		
		self.callsLock.acquire()
		self.queuesLock.acquire()
		
		try:
			#del self.calls[(Uniqueid1, Uniqueid2)]
			self.calls[(Uniqueid1, Uniqueid2)]['Status'] = 'Unlink'
			self.enqueue(Action = 'Unlink', Channel1 = Channel1, Channel2 = Channel2, Uniqueid1 = Uniqueid1, Uniqueid2 = Uniqueid2, CallerID1 = CallerID1, CallerID2 = CallerID2)
		except:
			log.warning("MonAst.handlerUnlink :: Call %s-%s not found on self.calls" % (Uniqueid1, Uniqueid2))
		
		if self.queueMemberCalls.has_key(Uniqueid1):
			self.queueMemberCalls[Uniqueid1]['Link'] = False
			qmc = self.queueMemberCalls[Uniqueid1]
			self.enqueue(Action = 'RemoveQueueMemberCall', Queue = qmc['Queue'], Member = qmc['Member'], Uniqueid = Uniqueid1)

		self.queuesLock.release()
		self.callsLock.release()
		
		
	def handlerNewcallerid(self, lines):
		
		log.info('MonAst.handlerNewcallerid :: Running...')
		dic = self.list2Dict(lines)
		
		Channel        = dic['Channel']
		CallerID       = dic.get('CallerIDNum', dic.get('CallerID'))
		CallerIDName   = dic['CallerIDName']
		Uniqueid       = dic['Uniqueid']
		CIDCallingPres = dic['CID-CallingPres']
		
		self.channelsLock.acquire()
		try:
			self.channels[Uniqueid]['CallerIDName'] = CallerIDName
			self.channels[Uniqueid]['CallerIDNum']  = CallerID
			self.enqueue(Action = 'NewCallerid', Channel = Channel, CallerID = CallerID, CallerIDName = CallerIDName, Uniqueid = Uniqueid, CIDCallingPres = CIDCallingPres)
		except KeyError:
			log.warning("MonAst.handlerNewcallerid :: UniqueID '%s' not found on self.channels" % Uniqueid)
		self.channelsLock.release()
		
		
	def handlerRename(self, lines):
		
		log.info('MonAst.handlerRename :: Running...')
		dic = self.list2Dict(lines)
		
		Oldname      = dic.get('Channel', dic.get('Oldname'))
		Newname      = dic['Newname']
		Uniqueid     = dic['Uniqueid']
		CallerIDName = ''
		CallerID     = ''
		
		self.channelsLock.acquire()
		self.callsLock.acquire()
		
		try:
			
			self.channels[Uniqueid]['Channel'] = Newname
			CallerIDName = self.channels[Uniqueid]['CallerIDName']
			CallerID     = self.channels[Uniqueid]['CallerIDNum']
		
			for call in self.calls:
				SrcUniqueID, DestUniqueID = call
				key = None
				if (SrcUniqueID == Uniqueid):
					key = 'Source'
				if (DestUniqueID == Uniqueid):
					key = 'Destination'
				if key:
					self.calls[call][key] = Newname
					break							
			
			self.enqueue(Action = 'Rename', Oldname = Oldname, Newname = Newname, Uniqueid = Uniqueid, CallerIDName = CallerIDName, CallerID = CallerID)
		except:
			log.warn('MonAst.handlerRename :: Channel %s not found in self.channels, ignored.' % Oldname)
			
		self.callsLock.release()
		self.channelsLock.release()
			
			
	def handlerMeetmeJoin(self, lines):
		
		log.info('MonAst.handlerMeetmeJoin :: Running...')
		dic = self.list2Dict(lines)
		
		Uniqueid     = dic['Uniqueid']
		Meetme       = dic['Meetme']
		Usernum      = dic['Usernum']
		CallerIDNum  = dic.get('CallerIDNum', dic.get('CallerIDnum', None))
		CallerIDName = dic.get('CallerIDName', dic.get('CallerIDname', None))
					
		self.meetmeLock.acquire()
		self.channelsLock.acquire()
		
		ch = self.channels[Uniqueid]
		try:
			self.meetme[Meetme]['users'][Usernum] = {'Uniqueid': Uniqueid, 'CallerIDNum': CallerIDNum, 'CallerIDName': CallerIDName}
		except KeyError:
			self.meetme[Meetme] = {
					'dynamic': True,
					'users'  : {Usernum: {'Uniqueid': Uniqueid, 'CallerIDNum': CallerIDNum, 'CallerIDName': CallerIDName}}
			}
			self.enqueue(Action = 'MeetmeCreate', Meetme = Meetme)
		self.enqueue(Action = 'MeetmeJoin', Meetme = Meetme, Uniqueid = Uniqueid, Usernum = Usernum, Channel = ch['Channel'], CallerIDNum = CallerIDNum, CallerIDName = CallerIDName)
		
		self.channelsLock.release()
		self.meetmeLock.release()
					
					
	def handlerMeetmeLeave(self, lines):
		
		log.info('MonAst.handlerMeetmeLeave :: Running...')
		dic = self.list2Dict(lines)
		
		Uniqueid = dic['Uniqueid']
		Meetme   = dic['Meetme']
		Usernum  = dic['Usernum']
		Duration = dic['Duration']
					
		self.meetmeLock.acquire()
		try:
			del self.meetme[Meetme]['users'][Usernum]
			self.enqueue(Action = 'MeetmeLeave', Meetme = Meetme, Uniqueid = Uniqueid, Usernum = Usernum, Duration = Duration)
			if (self.meetme[Meetme]['dynamic'] and len(self.meetme[Meetme]['users']) == 0):
				del self.meetme[Meetme]
				self.enqueue(Action = 'MeetmeDestroy', Meetme = Meetme)
		except Exception, e:
			log.warn('MonAst.handlerMeetmeLeave :: Meetme or Usernum not found in self.meetme[\'%s\'][\'users\'][\'%s\']' % (Meetme, Usernum))
		self.meetmeLock.release()
		
		
	def handlerParkedCall(self, lines):
		
		log.info('MonAst.handlerParkedCall :: Running...')
		dic = self.list2Dict(lines)
		
		Exten        = dic['Exten']
		Channel      = dic['Channel']
		From         = dic['From']
		Timeout      = dic['Timeout']
		CallerID     = dic.get('CallerIDNum', dic.get('CallerID'))
		CallerIDName = dic['CallerIDName']
					
		self.parkedLock.acquire()
		self.parked[Exten] = {'Channel': Channel, 'From': From, 'Timeout': Timeout, 'CallerID': CallerID, 'CallerIDName': CallerIDName}
		self.enqueue(Action = 'ParkedCall', Exten = Exten, Channel = Channel, From = From, Timeout = Timeout, CallerID = CallerID, CallerIDName = CallerIDName)
		self.parkedLock.release()
					
					
	def handlerUnParkedCall(self, lines):
		
		log.info('MonAst.handlerUnParkedCall :: Running...')
		dic = self.list2Dict(lines)
		
		Exten        = dic['Exten']
		Channel      = dic['Channel']
		From         = dic['From']
		CallerID     = dic.get('CallerIDNum', dic.get('CallerID'))
		CallerIDName = dic['CallerIDName']
					
		self.parkedLock.acquire()
		try:
			del self.parked[Exten]
			self.enqueue(Action = 'UnparkedCall', Exten = Exten)
		except:
			log.warn('MonAst.handlerUnParkedCall :: Parked Exten not found: %s' % Exten)
		self.parkedLock.release()
		
	
	def handlerParkedCallTimeOut(self, lines):
		
		log.info('MonAst.handlerParkedCallTimeOut :: Running...')
		dic = self.list2Dict(lines)
		
		Exten        = dic['Exten']
		Channel      = dic['Channel']
		CallerID     = dic.get('CallerIDNum', dic.get('CallerID'))
		CallerIDName = dic['CallerIDName']
					
		self.parkedLock.acquire()
		try:
			del self.parked[Exten]
			self.enqueue(Action = 'UnparkedCall', Exten = Exten)
		except:
			log.warn('MonAst.handlerParkedCallTimeOut :: Parked Exten not found: %s' % Exten)
		self.parkedLock.release()
		
	
	def handlerParkedCallGiveUp(self, lines):
		
		log.info('MonAst.handlerParkedCallGiveUp :: Running...')
		dic = self.list2Dict(lines)
		
		Exten        = dic['Exten']
		Channel      = dic['Channel']
		CallerID     = dic.get('CallerIDNum', dic.get('CallerID'))
		CallerIDName = dic['CallerIDName']
					
		self.parkedLock.acquire()
		try:
			del self.parked[Exten]
			self.enqueue(Action = 'UnparkedCall', Exten = Exten)
		except:
			log.warn('MonAst.handlerParkedCallGiveUp :: Parked Exten not found: %s' % Exten)
		self.parkedLock.release()
		
		
	def handlerStatus(self, lines):
		
		log.info('MonAst.handlerStatus :: Running...')
		dic = self.list2Dict(lines)
		
		Channel      = dic['Channel']
		CallerIDNum  = dic['CallerIDNum']
		CallerIDName = dic['CallerIDName']
		State        = dic.get('ChannelStateDesc', dic.get('State'))
		Seconds      = dic.get('Seconds', 0)
		Link         = dic.get('BridgedChannel', dic.get('Link', ''))
		Uniqueid     = dic['Uniqueid']
		Monitor      = False
		
		self.channelsLock.acquire()
		self.callsLock.acquire()
		self.monitoredUsersLock.acquire()
		
		self.channelStatus.append(Uniqueid)
		
		if not self.channels.has_key(Uniqueid):
			self.channels[Uniqueid] = {'Channel': Channel, 'State': State, 'CallerIDNum': CallerIDNum, 'CallerIDName': CallerIDName, 'Monitor': Monitor}
			user = Channel
			if Channel.rfind('-') != -1:
				user = Channel[:Channel.rfind('-')]
			if self.monitoredUsers.has_key(user):
				mu           = self.monitoredUsers[user] 
				mu['Calls'] += 1
				self.enqueue(Action = 'PeerStatus', Peer = user, Status = mu['Status'], Calls = mu['Calls'])
			self.enqueue(Action = 'NewChannel', Channel = Channel, State = State, CallerIDNum = CallerIDNum, CallerIDName = CallerIDName, Uniqueid = Uniqueid, Monitor = Monitor)
			if Link:
				for UniqueidLink in self.channels:
					if self.channels[UniqueidLink]['Channel'] == Link:
						self.calls[(Uniqueid, UniqueidLink)] = {
							'Source': Channel, 'Destination': Link, 'SrcUniqueID': Uniqueid, 'DestUniqueID': UniqueidLink, 
							'Status': 'Link', 'startTime': time.time() - int(Seconds)
						}
						CallerID1 = '%s <%s>' % (self.channels[Uniqueid]['CallerIDName'], self.channels[Uniqueid]['CallerIDNum'])
						CallerID2 = '%s <%s>' % (self.channels[UniqueidLink]['CallerIDName'], self.channels[UniqueidLink]['CallerIDNum'])
						self.enqueue(Action = 'Link', Channel1 = Channel, Channel2 = Link, Uniqueid1 = Uniqueid, Uniqueid2 = UniqueidLink, CallerID1 = CallerID1, CallerID2 = CallerID2, Seconds = int(Seconds))
		
		## Update call duration
		if self.channels.has_key(Uniqueid) and Seconds > 0 and Link:
			for UniqueidLink in self.channels:
				if self.channels[UniqueidLink]['Channel'] == Link:
					call = (Uniqueid, UniqueidLink)
					duration = time.time() - self.calls[call]['startTime']
					Seconds  = int(Seconds)
					if duration < (Seconds - 10) or duration > (Seconds + 10):
						self.calls[call]['startTime'] = time.time() - Seconds
						self.enqueue(Action = 'UpdateCallDuration', Uniqueid1 = Uniqueid, Uniqueid2 = UniqueidLink, Seconds = Seconds)
		
		self.monitoredUsersLock.release()
		self.callsLock.release()
		self.channelsLock.release()
		
		
	def handlerStatusComplete(self, lines):
		
		log.info('MonAst.handlerStatusComplete :: Running...')
		dic = self.list2Dict(lines)
		
		self.channelsLock.acquire()
		self.callsLock.acquire()
		self.queuesLock.acquire()
		self.monitoredUsersLock.acquire()
		
		## Search for lost channels
		lostChannels = [i for i in self.channels.keys() if i not in self.channelStatus]
		for Uniqueid in lostChannels:
			log.warning('MonAst.handlerStatusComplete :: Removing lost channel %s' % Uniqueid)
			try:
				Channel = self.channels[Uniqueid]['Channel']
				del self.channels[Uniqueid]
				self.enqueue(Action = 'Hangup', Channel = Channel, Uniqueid = Uniqueid, Cause = None, Cause_txt = None)
			except:
				#pass ## added to debug purposes
				log.exception('MonAst.handlerStatusComplete :: Exception removing lost channel %s' % Uniqueid)
			
			## Decrease number of peer calls 
			user = Channel
			if Channel.rfind('-') != -1:
				user = Channel[:Channel.rfind('-')]
			if self.monitoredUsers.has_key(user) and self.monitoredUsers[user]['Calls'] > 0:
				mu           = self.monitoredUsers[user] 
				mu['Calls'] -= 1
				self.enqueue(Action = 'PeerStatus', Peer = user, Status = mu['Status'], Calls = mu['Calls'])
			
		## Search for lost calls
		lostCalls = [call for call in self.calls.keys() if not self.channels.has_key(call[0]) or not self.channels.has_key(call[1])]
		for call in lostCalls:
			log.warning('MonAst.handlerStatusComplete :: Removing lost call %s-%s' % (call[0], call[1]))
			try:
				del self.calls[call]
				self.enqueue(Action = 'Unlink', Channel1 = None, Channel2 = None, Uniqueid1 = call[0], Uniqueid2 = call[1], CallerID1 = None, CallerID2 = None)
			except:
				#pass ## added to debug purposes
				log.exception('MonAst.handlerStatusComplete :: Exception removing lost call %s-%s' % (call[0], call[1]))
			
		## Search for lost queue member calls
		lostQueueMemberCalls = [Uniqueid for Uniqueid in self.queueMemberCalls if not self.channels.has_key(Uniqueid)]
		for Uniqueid in lostQueueMemberCalls:
			log.warning('MonAst.handlerStatusComplete :: Removing lost Queue Member Call %s' % Uniqueid)
			try:
				Queue  = self.queueMemberCalls[Uniqueid]['Queue']
				Member = self.queueMemberCalls[Uniqueid]['Member']
				del self.queueMemberCalls[Uniqueid]
				self.enqueue(Action = 'RemoveQueueMemberCall', Queue = Queue, Member = Member, Uniqueid = Uniqueid)
			except:
				#pass ## added to debug purposes
				log.exception('MonAst.handlerStatusComplete :: Exception removing lost Queue Member Call %s' % Uniqueid)

		if self.getMeetmeAndParkStatus:
			self.AMI.execute(['Action: Command', 'Command: meetme'], self.handlerParseMeetme)
			self.AMI.execute(['Action: Command', 'Command: show parkedcalls'], self.handlerShowParkedCalls)
			self.getMeetmeAndParkStatus = False
			
		self.monitoredUsersLock.release()
		self.queuesLock.release()	
		self.callsLock.release()
		self.channelsLock.release()
	
	
	def handlerQueueMember(self, lines):
		
		log.info('MonAst.handlerQueueMember :: Running...')
		dic = self.list2Dict(lines)
		
		Queue      = dic['Queue']
		Name       = dic['Name']
		Location   = dic['Location']
		Penalty    = dic['Penalty']
		CallsTaken = dic['CallsTaken']
		LastCall   = dic['LastCall']
		Status     = dic['Status']
		Paused     = dic['Paused']
		
		self.queuesLock.acquire()
		if not self.queues.has_key(Queue):
			log.warning("MonAst.handlerQueueMember :: Can not add location '%s' to queue '%s'. Queue not found." % (Location, Queue))
			self.queuesLock.release()
			return
		
		try:
			self.queues[Queue]['members'][Location]['Penalty']    = Penalty
			self.queues[Queue]['members'][Location]['CallsTaken'] = CallsTaken
			self.queues[Queue]['members'][Location]['LastCall']   = LastCall
			self.queues[Queue]['members'][Location]['Status']     = Status
			self.queues[Queue]['members'][Location]['Paused']     = Paused
			self.enqueue(Action = 'QueueMemberStatus', Queue = Queue, Member = Location, Penalty = Penalty, CallsTaken = CallsTaken, LastCall = LastCall, Status = AST_DEVICE_STATES[Status], Paused = Paused)
		except KeyError:
			self.queues[Queue]['members'][Location] = {
				'Name': Name, 'Penalty': Penalty, 'CallsTaken': CallsTaken, 'LastCall': LastCall, 'Status': Status, 'Paused': Paused
			}
			self.enqueue(Action = 'AddQueueMember', Queue = Queue, Member = Location, MemberName = Name, Penalty = Penalty, CallsTaken = CallsTaken, LastCall = LastCall, Status = AST_DEVICE_STATES[Status], Paused = Paused)
		self.queueMemberStatus[Queue].append(Location)
		self.queuesLock.release()
		
		
	def handlerQueueMemberStatus(self, lines):
		
		log.info('MonAst.handlerQueueMemberStatus :: Running...')
		dic = self.list2Dict(lines)
		
		lines.append('Name: %s' % dic['MemberName'])
		self.handlerQueueMember(lines)
		
		
	def handlerQueueMemberPaused(self, lines):
		
		log.info('MonAst.handlerQueueMemberPaused :: Running...')
		dic = self.list2Dict(lines)
		
		Queue    = dic['Queue']
		Location = dic['Location']
		
		self.queuesLock.acquire()
		lines.append('Penalty: %s' % self.queues[Queue]['members'][Location]['Penalty'])
		lines.append('CallsTaken: %s' % self.queues[Queue]['members'][Location]['CallsTaken'])
		lines.append('LastCall: %s' % self.queues[Queue]['members'][Location]['LastCall'])
		lines.append('Status: %s' % self.queues[Queue]['members'][Location]['Status'])
		lines.append('Name: %s' % dic['MemberName'])
		self.queuesLock.release()
		
		self.handlerQueueMember(lines)
		
		
	def handlerQueueEntry(self, lines):
		
		log.info('MonAst.handlerQueueEntry :: Running...')
		dic = self.list2Dict(lines)
		
		Queue        = dic['Queue']
		Position     = dic['Position']
		Channel      = dic['Channel']
		CallerID     = dic.get('CallerIDNum', dic.get('CallerID'))
		CallerIDName = dic['CallerIDName']
		Wait         = dic['Wait']
		Uniqueid     = None
		
		# I need to get Uniqueid from this entry
		self.channelsLock.acquire()
		self.queuesLock.acquire()
		
		for Uniqueid in self.channels:
			if self.channels[Uniqueid]['Channel'] == Channel:
				break
		
		self.queueClientStatus[Queue].append(Uniqueid)
		Count = len(self.queueClientStatus[Queue])
		try:
			self.queues[Queue]['clients'][Uniqueid]['Position'] = Position			
		except KeyError:
			self.queues[Queue]['clients'][Uniqueid] = {'Uniqueid': Uniqueid, 'Channel': Channel, 'CallerID': CallerID, 'CallerIDName': CallerIDName, \
													'Position': Position, 'JoinTime': time.time() - int(Wait)}
			self.enqueue(Action = 'AddQueueClient', Queue = Queue, Uniqueid = Uniqueid, Channel = Channel, CallerID = CallerID, CallerIDName = CallerIDName, Position = Position, Count = Count, Wait = Wait)

		self.queuesLock.release()
		self.channelsLock.release()
		
		
	def handlerQueueMemberAdded(self, lines):
		
		log.info('MonAst.handlerQueueMemberAdded :: Running...')
		dic = self.list2Dict(lines)
		
		Queue      = dic['Queue']
		Location   = dic['Location']
		MemberName = dic['MemberName']
		Penalty    = dic['Penalty']
		
		self.queuesLock.acquire()
		self.queues[Queue]['members'][Location] = {'Name': MemberName, 'Penalty': Penalty, 'CallsTaken': 0, 'LastCall': 0, 'Status': '0', 'Paused': 0} 
		self.enqueue(Action = 'AddQueueMember', Queue = Queue, Member = Location, MemberName = MemberName, Penalty = Penalty, CallsTaken = 0, LastCall = 0, Status = AST_DEVICE_STATES['0'], Paused = 0)
		self.queuesLock.release()
		
		
	def handlerQueueMemberRemoved(self, lines):
		
		log.info('MonAst.handlerQueueMemberRemoved :: Running...')
		dic = self.list2Dict(lines)
		
		Queue      = dic['Queue']
		Location   = dic['Location']
		MemberName = dic['MemberName']
		
		self.queuesLock.acquire()
		try:
			del self.queues[Queue]['members'][Location]
			self.enqueue(Action = 'RemoveQueueMember', Queue = Queue, Member = Location, MemberName = MemberName)
		except KeyError:
			log.warn("MonAst.handlerQueueMemberRemoved :: Queue or Member not found in self.queues['%s']['members']['%s']" % (Queue, Location))
		self.queuesLock.release()
		
		
	def handlerJoin(self, lines): # Queue Join
		
		log.info('MonAst.handlerJoin :: Running...')
		dic = self.list2Dict(lines)
		
		Channel      = dic['Channel']
		CallerID     = dic.get('CallerIDNum', dic.get('CallerID'))
		CallerIDName = dic['CallerIDName']
		Queue        = dic['Queue']
		Position     = dic['Position']
		Count        = dic['Count']
		Uniqueid     = dic['Uniqueid']
		
		self.queuesLock.acquire()
		try:
			self.queues[Queue]['clients'][Uniqueid] = {'Uniqueid': Uniqueid, 'Channel': Channel, 'CallerID': CallerID, 'CallerIDName': CallerIDName, \
													'Position': Position, 'JoinTime': time.time()}
			self.queues[Queue]['stats']['Calls'] += 1
			self.enqueue(Action = 'AddQueueClient', Queue = Queue, Uniqueid = Uniqueid, Channel = Channel, CallerID = CallerID, CallerIDName = CallerIDName, Position = Position, Count = Count, Wait = 0)
		except KeyError:
			log.warning("MonAst.handlerJoin :: Queue '%s' not found." % Queue)
		self.queuesLock.release()
		
	
	def handlerLeave(self, lines): # Queue Leave
		
		log.info('MonAst.handlerLeave :: Running...')
		dic = self.list2Dict(lines)
	
		Channel      = dic['Channel']
		Queue        = dic['Queue']
		Count        = dic['Count']
		Uniqueid     = dic['Uniqueid']
		
		self.queuesLock.acquire()
		try:
			cause = ''
			if self.queues[Queue]['clients'][Uniqueid].has_key('Abandoned'):
				cause = 'Abandoned'
				self.queues[Queue]['stats']['Abandoned'] += 1
			else:
				cause = 'Completed'
				self.queues[Queue]['stats']['Completed'] += 1
				self.queueMemberCalls[Uniqueid] = {'Queue': Queue, 'Channel': Channel, 'Member': None, 'Link': False}
			self.queues[Queue]['stats']['Calls'] -= 1
			
			del self.queues[Queue]['clients'][Uniqueid]
			self.enqueue(Action = 'RemoveQueueClient', Queue = Queue, Uniqueid = Uniqueid, Channel = Channel, Count = Count, Cause = cause)
		except KeyError:
			log.warn("MonAst.handlerLeave :: Queue or Client not found in self.queues['%s']['clients']['%s']" % (Queue, Uniqueid))
		self.queuesLock.release()
		
		
	def handlerQueueCallerAbandon(self, lines):
		
		log.info('MonAst.handlerQueueCallerAbandon :: Running...')
		dic = self.list2Dict(lines)
		
		Queue    = dic['Queue']
		Uniqueid = dic['Uniqueid']
		
		self.queuesLock.acquire()
		self.queues[Queue]['clients'][Uniqueid]['Abandoned'] = True
		self.queuesLock.release()
		
		#self.enqueue(Action = 'AbandonedQueueClient', Uniqueid = Uniqueid)
		
		
	def handlerQueueParams(self, lines):
		
		log.info('MonAst.handlerQueueParams :: Running...')
		dic = self.list2Dict(lines)
		
		Queue            = dic['Queue']
		Max              = int(dic['Max'])
		Calls            = int(dic['Calls'])
		Holdtime         = int(dic['Holdtime'])
		Completed        = int(dic['Completed'])
		Abandoned        = int(dic['Abandoned'])
		ServiceLevel     = int(dic['ServiceLevel'])
		ServicelevelPerf = float(dic['ServicelevelPerf'].replace(',', '.'))
		Weight           = int(dic['Weight'])
		
		self.queuesLock.acquire()
		if self.queues.has_key(Queue):
			self.queues[Queue]['stats']['Max']              = Max
			self.queues[Queue]['stats']['Calls']            = Calls
			self.queues[Queue]['stats']['Holdtime']         = Holdtime
			self.queues[Queue]['stats']['Completed']        = Completed
			self.queues[Queue]['stats']['Abandoned']        = Abandoned
			self.queues[Queue]['stats']['ServiceLevel']     = ServiceLevel
			self.queues[Queue]['stats']['ServicelevelPerf'] = ServicelevelPerf
			self.queues[Queue]['stats']['Weight']           = Weight
		else:
			self.queues[Queue] = {
				'members': {}, 
				'clients': {}, 
				'stats': {
					'Max': Max, 'Calls': Calls, 'Holdtime': Holdtime, 'Completed': Completed, 'Abandoned': Abandoned, 'ServiceLevel': ServiceLevel, \
					'ServicelevelPerf': ServicelevelPerf, 'Weight': Weight
				}
			}
			self.queueMemberStatus[Queue] = []
			self.queueClientStatus[Queue] = []
			self.queueStatusFirst         = True
			self.queueStatusOrder.append(Queue)
			
		self.enqueue(Action = 'QueueParams', Queue = Queue, Max = Max, Calls = Calls, Holdtime = Holdtime, Completed = Completed, Abandoned = Abandoned, ServiceLevel = ServiceLevel, ServicelevelPerf = ServicelevelPerf, Weight = Weight)
			
		self.queuesLock.release()
		
		
	def handlerQueueStatusComplete(self, lines):
		
		log.info('MonAst.handlerQueueStatusComplete :: Running...')
		
		self.queuesLock.acquire()
		
		size = 0
		if self.queueStatusFirst:
			size = len(self.queueStatusOrder)
			self.queueStatusFirst = False
		elif len(self.queueStatusOrder) > 0:
			size = 1			
		
		for i in xrange(size):
			try:
				queue       = self.queueStatusOrder.pop(0)
				lostMembers = [i for i in self.queues[queue]['members'].keys() if i not in self.queueMemberStatus[queue]]
				for member in lostMembers:
					log.log(logging.NOTICE, 'MonAst.handlerQueueStatusComplete :: Removing lost member %s from queue %s' % (member, queue))
					del self.queues[queue]['members'][member]
					self.enqueue(Action = 'RemoveQueueMember', Queue = queue, Member = member, MemberName = None)
				
				lostClients = [i for i in self.queues[queue]['clients'].keys() if i not in self.queueClientStatus[queue]]
				for client in lostClients:
					log.log(logging.NOTICE, 'MonAst.handlerQueueStatusComplete :: Removing lost client %s from queue %s' % (client, queue))
					Channel = self.queues[queue]['clients'][client]['Channel']
					del self.queues[queue]['clients'][client]
					Count = len(self.queues[queue]['clients'])
					self.enqueue(Action = 'RemoveQueueClient', Queue = queue, Uniqueid = client, Channel = Channel, Count = Count, Cause = None)
			except:
				log.exception('MonAst.handlerQueueStatusComplete :: Unhandled Exception')
		self.queuesLock.release()
	
	
	def handlerMonitorStart(self, lines):
		
		log.info('MonAst.handlerMonitorStart :: Running...')
		dic = self.list2Dict(lines)
		
		Channel  = dic['Channel']
		Uniqueid = dic['Uniqueid']
		
		self.channelsLock.acquire()
		try:
			self.channels[Uniqueid]['Monitor'] = True
			self.enqueue(Action = 'MonitorStart', Channel = Channel, Uniqueid = Uniqueid)
		except:
			log.warning('MonAst.handlerMonitorStart :: Uniqueid %s not found in self.channels' % Uniqueid)
		self.channelsLock.release()
		
		
	def handlerMonitorStop(self, lines):
		
		log.info('MonAst.handlerMonitorStart :: Running...')
		dic = self.list2Dict(lines)
		
		Channel  = dic['Channel']
		Uniqueid = dic['Uniqueid']
		
		self.channelsLock.acquire()
		try:
			self.channels[Uniqueid]['Monitor'] = False
			self.enqueue(Action = 'MonitorStop', Channel = Channel, Uniqueid = Uniqueid)
		except:
			log.warning('MonAst.handlerMonitorStop :: Uniqueid %s not found in self.channels' % Uniqueid)
		self.channelsLock.release()
		
		
	##
	## AMI handlers for Actions/Commands
	##
	def _defaultParseConfigPeers(self, lines):
		
		log.info('MonAst._defaultParseConfigPeers :: Running...')
		result = lines[3]
		
		user = lines[2].split(': ')[1]
		
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
		
		self.monitoredUsersLock.acquire()
		if self.monitoredUsers.has_key(user):
			self.monitoredUsers[user]['CallerID']  = CallerID
			self.monitoredUsers[user]['Context']   = Context
			self.monitoredUsers[user]['Variables'] = Variables
		self.monitoredUsersLock.release()
		
		
	def handlerParseIAXPeers(self, lines):
		
		log.info('MonAst.handlerParseIAXPeers :: Running...')
		
		for line in lines[2:-1]:
			name = re.search('^([^\s]*).*', line).group(1)
			if name.find('/') != -1:
				name = name[:name.find('/')]
			
			self.handlerPeerEntry(['Channeltype: IAX2', 'ObjectName: %s' % name, 'Status: --'])
			
			
	def handlerParseSkypeUsers(self, lines):
		
		log.info('MonAst.handlerParseSkypeUsers :: Running...')
		
		response = lines[3]
		if 'Skype Users' in response:
			users = response.split('\n')[1:-1]
			for user, status in [i.split(': ') for i in users]:
				self.handlerPeerEntry(['Channeltype: Skype', 'ObjectName: %s' % user, 'Status: %s' % status])
				
	
	def handlerGetConfigMeetme(self, lines):
		
		log.info('MonAst.handlerGetConfigMeetme :: Parsing config...')
		
		self.meetmeLock.acquire()
		for line in lines:
			if line.startswith('Line-') and line.find('conf=') != -1:
				params = line[line.find('conf=')+5:].split(',')
				self.meetme[params[0]] = {'dynamic': False, 'users': {}}
		self.meetmeLock.release()
		
		
	def handlerParseMeetme(self, lines):
		
		log.info('MonAst.handlerParseMeetme :: Parsing meetme...')
		
		reMeetme = re.compile('([^\s]*)[\s]+([^\s]*)[\s]+([^\s]*)[\s]+([^\s]*)[\s]+([^\s]*)')
		
		self.meetmeLock.acquire()
		try:
			meetmes = lines[3].split('\n')[1:-1]
			if len(meetmes) > 0:
				meetmes = meetmes[:-1]
			for meetme in meetmes:
				try:
					gMeetme = reMeetme.match(meetme)
					conf    = gMeetme.group(1)
					type    = gMeetme.group(5)
					
					if not self.meetme.has_key(conf):
						dynamic = False
						if type.lower() == 'dynamic':
							dynamic = True
						self.meetme[conf] = {'dynamic': dynamic, 'users': {}}
						self.enqueue(Action = 'MeetmeCreate', Meetme = conf)
						
					self.AMI.execute(['Action: Command', 'Command: meetme list %s concise' % conf], self.handlerParseMeetmeConcise, 'meetmeList-%s' % conf)				
				except:
					log.warn("MonAst.handlerParseMeetme :: Can't parse meetme line: %s" % meetme)
		except:
			log.exception("MonAst.handlerParseMeetme :: Unhandled Exception")
		self.meetmeLock.release()
		
		
	def handlerParseMeetmeConcise(self, lines):

		log.info('MonAst.handlerParseMeetmeConcise :: Parsing meetme concise...')

		self.meetmeLock.acquire()
		self.channelsLock.acquire()
		meetme = lines[2][10:].replace('meetmeList-', '')
		users  = lines[3].replace('--END COMMAND--', '').split('\n')[:-1]
		for user in users:
			user = user.split('!')
			if self.meetme.has_key(meetme):
				# locate UniqueID for this channel
				for Uniqueid in self.channels:
					if self.channels[Uniqueid]['Channel'] == user[3]:
						self.meetme[meetme]['users'][user[0]] = {'Uniqueid': Uniqueid, 'CallerIDNum': user[1], 'CallerIDName': user[2]}
						self.enqueue(Action = 'MeetmeJoin', Meetme = meetme, Uniqueid = Uniqueid, Usernum = user[0], Channel = user[3], CallerIDNum = user[1], CallerIDName = user[2])
						break
		self.channelsLock.release()
		self.meetmeLock.release()
		
		
	def handlerShowParkedCalls(self, lines):
		
		log.info('MonAst.handlerShowParkedCalls :: Parsing parkedcalls...')
		
		reParked = re.compile('([0-9]+)[\s]+([^\s]*).*([^\s][0-9]+s)')
		
		self.parkedLock.acquire()
		self.channelsLock.acquire()
		parkeds = lines[3].split('\n')[1:-2]
		for park in parkeds:
			gParked = reParked.match(park)
			if gParked:
				Exten   = gParked.group(1)
				Channel = gParked.group(2)
				Timeout = gParked.group(3).replace('s', '')
				
				# search callerid for this channel
				c = None
				for Uniqueid in self.channels:
					if self.channels[Uniqueid]['Channel'] == Channel:
						c = self.channels[Uniqueid]
						break
					
				if c:
					self.parked[Exten] = {'Channel': c['Channel'], 'From': 'Undefined', 'Timeout': Timeout, 'CallerID': c['CallerIDNum'], 'CallerIDName': c['CallerIDName']}
					self.enqueue(Action = 'ParkedCall', Exten = Exten, Channel = Channel, From = 'Undefined', Timeout = Timeout, CallerID = c['CallerIDNum'], CallerIDName = c['CallerIDName'])
				else:
					log.warn('MonAst.handlerShowParkedCalls :: No Channel found for parked call exten %s' % Exten)
				
		self.channelsLock.release()
		self.parkedLock.release()
	
	
	def handlerCliCommand(self, lines):
		
		log.info('MonAst.handlerCliCommand :: Running...')

		ActionID = lines[2][10:]
		Response = lines[3].replace('--END COMMAND--', '')

		self.enqueue(Action = 'CliResponse', Response = Response.replace('\n', '<br>'), __session = ActionID)
	
	
	##
	## Handlers for Client Commands
	##
	def clientGetStatus(self, threadId, session):
		
		log.info('MonAst.clientGetStatus (%s) :: Running...' % threadId)
		
		output = []
		theEnd = []
		
		self.clientQueuelock.acquire()
		self.monitoredUsersLock.acquire()
		self.channelsLock.acquire()
		self.callsLock.acquire()
		self.meetmeLock.acquire()
		self.parkedLock.acquire()
		self.queuesLock.acquire()
		
		try:
			self.clientQueues[session]['t'] = time.time()
			output.append('BEGIN STATUS')
			
			users = self.__sortPeers()
			techs = users.keys()
			techs.sort()
			for tech in techs:
				for user in users[tech]:
					mu = self.monitoredUsers[user[0]]
					output.append(self.parseJson(Action = 'PeerStatus', Peer = user[0], Status = mu['Status'], Calls = mu['Calls'], CallerID = user[2]))
			
			chans = self.channels.keys()
			chans.sort()			
			for Uniqueid in chans:
				ch = self.channels[Uniqueid]
				output.append(self.parseJson(Action = 'NewChannel', Channel = ch['Channel'], State = ch['State'], CallerIDNum = ch['CallerIDNum'], CallerIDName = ch['CallerIDName'], Uniqueid = Uniqueid, Monitor = ch['Monitor']))
			
			orderedCalls = self.calls.keys()
			orderedCalls.sort(lambda x, y: cmp(self.calls[x]['startTime'], self.calls[y]['startTime']))
			for call in orderedCalls:
				c = self.calls[call]
				src, dst = call
			
				CallerID1 = ''
				CallerID2 = ''
				
				try:
					CallerID1 = '%s <%s>' % (self.channels[src]['CallerIDName'], self.channels[src]['CallerIDNum'])
					CallerID2 = '%s <%s>' % (self.channels[dst]['CallerIDName'], self.channels[dst]['CallerIDNum'])
				except KeyError:
					log.warning('MonAst.clientGetStatus (%s) :: UniqueID %s or %s not found on self.channels' % (threadId, src, dst))
				
				try:
					if c['Status'] != 'Unlink':
						output.append(self.parseJson(Action = 'Call', Source = c['Source'], Destination = c['Destination'], \
							CallerID1 = CallerID1, CallerID2 = CallerID2, SrcUniqueID = c['SrcUniqueID'], DestUniqueID = c['DestUniqueID'], Status = c['Status'], Seconds = time.time() - c['startTime']))
				except:
					log.exception('MonAst.clientGetStatus (%s) :: Unhandled Exception' % threadId)
					
				if self.queueMemberCalls.has_key(src) and self.queueMemberCalls[src]['Link']:
					qmc = self.queueMemberCalls[src]
					theEnd.append(self.parseJson(Action = 'AddQueueMemberCall', Queue = qmc['Queue'], Member = qmc['Member'], Uniqueid = src, Channel = qmc['Channel'], CallerID = CallerID1, Seconds = time.time() - c['startTime']))
				
			meetmeRooms = self.meetme.keys()
			meetmeRooms.sort()
			for meetme in meetmeRooms:
				output.append(self.parseJson(Action = 'MeetmeCreate', Meetme = meetme))
				for Usernum in self.meetme[meetme]['users']:
					mm = self.meetme[meetme]['users'][Usernum]
					ch = self.channels[mm['Uniqueid']]
					output.append(self.parseJson(Action = 'MeetmeJoin', Meetme = meetme, Uniqueid = mm['Uniqueid'], Usernum = Usernum, Channel = ch['Channel'], CallerIDNum = mm['CallerIDNum'], CallerIDName = mm['CallerIDName']))
			
			parkedCalls = self.parked.keys()
			parkedCalls.sort()
			for Exten in parkedCalls:
				pc = self.parked[Exten]
				output.append(self.parseJson(Action = 'ParkedCall', Exten = Exten, Channel = pc['Channel'], From = pc['From'], Timeout = pc['Timeout'], CallerID = pc['CallerID'], CallerIDName = pc['CallerIDName']))
				
			queues = self.queues.keys()
			queues.sort()
			for queue in queues:
				q = self.queues[queue]
				output.append(self.parseJson(Action = 'Queue', Queue = queue))
				members = q['members'].keys()
				members.sort()
				for member in members:
					m = q['members'][member]
					output.append(self.parseJson(Action = 'AddQueueMember', Queue = queue, Member = member, MemberName = m['Name'], \
						Penalty = m['Penalty'], CallsTaken = m['CallsTaken'], LastCall = m['LastCall'], Status = AST_DEVICE_STATES[m['Status']], Paused = m['Paused']))
					
				clients = q['clients'].values()
				clients.sort(lambda x, y: cmp(x['Position'], y['Position']))
				for i in xrange(len(clients)):
					c = clients[i]
					output.append(self.parseJson(Action = 'AddQueueClient', Queue = queue, Uniqueid = c['Uniqueid'], Channel = c['Channel'], CallerID = c['CallerID'], \
									CallerIDName = c['CallerIDName'], Position = c['Position'], Count = i, Wait = time.time() - c['JoinTime']))
					
				Max              = q['stats']['Max']
				Calls            = q['stats']['Calls']
				Holdtime         = q['stats']['Holdtime']
				Completed        = q['stats']['Completed']
				Abandoned        = q['stats']['Abandoned']
				ServiceLevel     = q['stats']['ServiceLevel']
				ServicelevelPerf = q['stats']['ServicelevelPerf']
				Weight           = q['stats']['Weight']
				
				output.append(self.parseJson(Action = 'QueueParams', Queue = queue, Max = Max, Calls = Calls, Holdtime = Holdtime, Completed = Completed, Abandoned = Abandoned, ServiceLevel = ServiceLevel, ServicelevelPerf = ServicelevelPerf, Weight = Weight))
			
			output += theEnd
			output.append('END STATUS')
		except:
			log.exception('MonAst.clientGetStatus (%s) :: Unhandled Exception' % threadId)
		
		self.queuesLock.release()
		self.parkedLock.release()
		self.meetmeLock.release()
		self.callsLock.release()
		self.channelsLock.release()
		self.monitoredUsersLock.release()
		self.clientQueuelock.release()
	
		return output
	
	
	def clientGetChanges(self, threadId, session):
		
		log.info('MonAst.clientGetChanges (%s) :: Running...' % threadId)
		
		output = []
		
		self.clientQueuelock.acquire()
		self.clientQueues[session]['t'] = time.time()
		#output.append('BEGIN CHANGES')
		while True:
			try:
				msg = self.clientQueues[session]['q'].get(False)
				output.append(msg)
			except Queue.Empty:
				break
		#output.append('END CHANGES')
		self.clientQueuelock.release()
		
		if len(output) > 0:
			output.insert(0, 'BEGIN CHANGES')
			output.append('END CHANGES')
		else:
			output.append('NO CHANGES')
		
		return output
	
	
	def clientOriginateCall(self, threadId, object):
		
		log.info('MonAst.clientOriginateCall (%s) :: Running...' % threadId)
		src  = object['Source']
		dst  = object['Destination']
		type = object['Type']
		
		self.monitoredUsersLock.acquire()
		Context = self.monitoredUsers[src]['Context']
		if type == 'meetme':
			Context = self.meetmeContext
			dst     = '%s%s' % (self.meetmePrefix, dst)
		command = []
		command.append('Action: Originate')
		command.append('Channel: %s' % src)
		command.append('Exten: %s' % dst)
		command.append('Context: %s' % Context)
		command.append('Priority: 1')
		command.append('CallerID: %s' % MONAST_CALLERID)
		for var in self.monitoredUsers[src]['Variables']:
			command.append('Variable: %s' % var)
		log.debug('MonAst.clientOriginateCall (%s) :: From %s to exten %s@%s' % (threadId, src, dst, Context))
		self.AMI.execute(command)
		self.monitoredUsersLock.release()
		
	
	def clientOriginateDial(self, threadId, object):
		
		log.info('MonAst.clientOriginateDial (%s) :: Running...' % threadId)
		src = object['Source']
		dst = object['Destination']

		command = []
		command.append('Action: Originate')
		command.append('Channel: %s' % src)
		command.append('Application: Dial')
		command.append('Data: %s,30,rTt' % dst)
		command.append('CallerID: %s' % MONAST_CALLERID)
		
		log.debug('MonAst.clientOriginateDial (%s) :: From %s to %s' % (threadId, src, dst))
		self.AMI.execute(command)
		
		
	def clientHangupChannel(self, threadId, object):
		
		log.info('MonAst.clientHangupChannel (%s) :: Running...' % threadId)
		Uniqueid = object['Uniqueid']
		
		self.channelsLock.acquire()
		try:
			Channel = self.channels[Uniqueid]['Channel']
			command = []
			command.append('Action: Hangup')
			command.append('Channel: %s' % Channel)
			log.debug('MonAst.clientHangupChannel (%s) :: Hangup channel %s' % (threadId, Channel))
			self.AMI.execute(command)
		except:
			log.warn('MonAst.clientHangupChannel (%s) :: Uniqueid %s not found on self.channels' % (threadId, Uniqueid))
		self.channelsLock.release()
		
		
	def clientMonitorChannel(self, threadId, object):
		
		log.info('MonAst.clientMonitorChannel (%s) :: Running...' % threadId)
		Uniqueid = object['Uniqueid']
		mix      = object['Mix']
		
		self.channelsLock.acquire()
		try:
			Channel = self.channels[Uniqueid]['Channel']
			command = []
			command.append('Action: Monitor')
			command.append('Channel: %s' % Channel)
			command.append('File: MonAst-Monitor.%s' % Channel.replace('/', '-'))
			command.append('Format: wav49')
			tt = 'without'
			if int(mix) == 1:
				command.append('Mix: 1')
				tt = 'with'
			log.debug('MonAst.clientMonitorChannel (%s) :: Monitoring channel %s %s Mix' % (threadId, Channel, tt))
			self.AMI.execute(command)
		except:
			log.warn('MonAst.clientMonitorChannel (%s) :: Uniqueid %s not found on self.channels' % (threadId, Uniqueid))
		self.channelsLock.release()
		
		
	def clientMonitorStop(self, threadId, object):
		
		log.info('MonAst.clientMonitorStop (%s) :: Running...' % threadId)
		Uniqueid = object['Uniqueid']
		
		self.channelsLock.acquire()
		try:
			self.channels[Uniqueid]['Monitor'] = False
			Channel = self.channels[Uniqueid]['Channel']
			command = []
			command.append('Action: StopMonitor')
			command.append('Channel: %s' % Channel)
			log.debug('MonAst.clientMonitorStop (%s) :: Stop Monitor on channel %s' % (threadId, Channel))
			self.AMI.execute(command)
		except:
			log.warn('MonAst.clientMonitorStop (%s) :: Uniqueid %s not found on self.channels' % (threadId, Uniqueid))
		self.channelsLock.release()
	
	
	def clientTransferCall(self, threadId, object):
		
		log.info('MonAst.clientTransferCall (%s) :: Running...' % threadId)
		src  = object['Source']
		dst  = object['Destination']
		type = object['Type']

		self.channelsLock.acquire()
		self.monitoredUsersLock.acquire()
							
		Context      = self.transferContext
		SrcChannel   = None
		ExtraChannel = None
		if type == 'peer':
			try:
				SrcChannel  = self.channels[src]['Channel']
			except KeyError:
				log.error('MonAst.clientTransferCall (%s) :: Channel %s not found on self.channels. Transfer failed! (peer)' % (threadId, src))
				return
			tech, exten = dst.split('/')
			try:
				exten = int(exten)
			except:
				exten = self.monitoredUsers[dst]['CallerID']
				exten = exten[exten.find('<')+1:exten.find('>')]
				
		elif type == 'meetme':
			try:
				tmp = src.split('+++')
				if len(tmp) == 2:
					SrcChannel   = self.channels[tmp[0]]['Channel']
					ExtraChannel = self.channels[tmp[1]]['Channel']
				else:
					SrcChannel   = self.channels[tmp[0]]['Channel']
			except KeyError, e:
				log.error('MonAst.clientTransferCall (%s) :: Channel %s not found on self.channels. Transfer failed! (meetme)' % (threadId, e))
				return
			
			Context = self.meetmeContext
			exten   = '%s%s' % (self.meetmePrefix, dst)

		command = []
		command.append('Action: Redirect')
		command.append('Channel: %s' % SrcChannel)
		if ExtraChannel:
			command.append('ExtraChannel: %s' % ExtraChannel)
		command.append('Exten: %s' % exten)
		command.append('Context: %s' % Context)
		command.append('Priority: 1')
		
		self.monitoredUsersLock.release()
		self.channelsLock.release()
		
		log.debug('MonAst.clientTransferCall (%s) :: Transferring %s and %s to %s@%s' % (threadId, SrcChannel, ExtraChannel, exten, Context))
		self.AMI.execute(command)
	
	
	def clientParkCall(self, threadId, object):

		log.info('MonAst.clientParkCall (%s) :: Running...' % threadId)
		park     = object['Park']
		announce = object['Announce']

		self.channelsLock.acquire()
		ParkChannel   = self.channels[park]['Channel']
		AnouceChannel = self.channels[announce]['Channel']
		self.channelsLock.release()
		command = []
		command.append('Action: Park')
		command.append('Channel: %s' % ParkChannel)
		command.append('Channel2: %s' % AnouceChannel)
		#ommand.append('Timeout: 45')
		log.debug('MonAst.clientParkCall (%s) :: Parking Channel %s and announcing to %s' % (threadId, ParkChannel, AnouceChannel))
		self.AMI.execute(command)	
	
	
	def clientMeetmeKick(self, threadId, object):
		
		log.info('MonAst.clientMeetmeKick (%s) :: Running...' % threadId)
		Meetme  = object['Meetme']
		Usernum = object['Usernum']
		
		command = []
		command.append('Action: Command')
		command.append('Command: meetme kick %s %s' % (Meetme, Usernum))
		log.debug('MonAst.clientMeetmeKick (%s) :: Kiking usernum %s from meetme %s' % (threadId, Usernum, Meetme))
		self.AMI.execute(command)
	
	
	def clientParkedHangup(self, threadId, object):
		
		log.info('MonAst.clientParkedHangup (%s) :: Running...' % threadId)
		Exten = object['Exten']
		
		self.parkedLock.acquire()
		try:
			Channel = self.parked[Exten]['Channel']
			command = []
			command.append('Action: Hangup')
			command.append('Channel: %s' % Channel)
			log.debug('MonAst.clientParkedHangup (%s) :: Hangup parcked channel %s' % (threadId, Channel))
			self.AMI.execute(command)
		except:
			log.warn('MonAst.clientParkedHangup (%s) :: Exten %s not found on self.parked' % (threadId, Exten))
		self.parkedLock.release()
		
		
	def clientAddQueueMember(self, threadId, object):
		
		log.info('MonAst.clientAddQueueMember (%s) :: Running...' % threadId)
		queue  = object['Queue']
		member = object['Member']
		
		self.monitoredUsersLock.acquire()
		MemberName = self.monitoredUsers[member]['CallerID']
		if MemberName == '--':
			MemberName = member
		command = []
		command.append('Action: QueueAdd')
		command.append('Queue: %s' % queue)
		command.append('Interface: %s' % member)
		#command.append('Penalty: 10')
		command.append('MemberName: %s' % MemberName)
		log.debug('MonAst.clientAddQueueMember (%s) :: Adding member %s to queue %s' % (threadId, member, queue))
		self.AMI.execute(command)
		self.monitoredUsersLock.release()
		
		
	def clientRemoveQueueMember(self, threadId, object):
		
		log.info('MonAst.clientRemoveQueueMember (%s) :: Running...' % threadId)
		queue  = object['Queue']
		member = object['Member']
		
		command = []
		command.append('Action: QueueRemove')
		command.append('Queue: %s' % queue)
		command.append('Interface: %s' % member)
		log.debug('MonAst.clientRemoveQueueMember (%s) :: Removing member %s from queue %s' % (threadId, member, queue))
		self.AMI.execute(command)
		
		
	def clientPauseQueueMember(self, threadId, object):
		
		log.info('MonAst.clientPauseQueueMember (%s) :: Running...' % threadId)
		queue  = object['Queue']
		member = object['Member']
		
		command = []
		command.append('Action: QueuePause')
		command.append('Queue: %s' % queue)
		command.append('Interface: %s' % member)
		command.append('Paused: 1')
		log.debug('MonAst.clientAddQueueMember (%s) :: Pausing member %s on queue %s' % (threadId, member, queue))
		self.AMI.execute(command)
		
	def clientUnpauseQueueMember(self, threadId, object):
		
		log.info('MonAst.clientPauseQueueMember (%s) :: Running...' % threadId)
		queue  = object['Queue']
		member = object['Member']
		
		command = []
		command.append('Action: QueuePause')
		command.append('Queue: %s' % queue)
		command.append('Interface: %s' % member)
		command.append('Paused: 0')
		log.debug('MonAst.clientUnpauseQueueMember (%s) :: Unpausing member %s on queue %s' % (threadId, member, queue))
		self.AMI.execute(command)
		
		
	def clientSkypeLogin(self, threadId, object):
		
		log.info('MonAst.clientSkypeLogin (%s) :: Running...' % threadId)
		skypeName = object['SkypeName']
		
		command = []
		command.append('Action: Command')
		command.append('Command: skype login user %s' % skypeName)
		log.debug('MonAst.clientSkypeLogin (%s) :: Login skype user %s' % (threadId, skypeName))
		self.AMI.execute(command)
	
	
	def clientSkypeLogout(self, threadId, object):
		
		log.info('MonAst.clientSkypeLogout (%s) :: Running...' % threadId)
		skypeName = object['SkypeName']
		
		command = []
		command.append('Action: Command')
		command.append('Command: skype logout user %s' % skypeName)
		log.debug('MonAst.clientSkypeLogout (%s) :: Logout skype user %s' % (threadId, skypeName))
		self.AMI.execute(command)
		
	
	def clientCliCommand(self, threadId, object, session):
		
		log.info('MonAst.clientCliCommand (%s) :: Running...' % threadId)
		cliCommand = object['CliCommand']
		
		command = []
		command.append('Action: Command')
		command.append('Command: %s' % cliCommand)
		#command.append('ActionID: %s' % session)
		log.debug('MonAst.clientCliCommand (%s) :: Executing CLI command: %s' % (threadId, cliCommand))
		self.AMI.execute(command, self.handlerCliCommand, session)
	
	
	def _GetConfig(self, sendReload = True):
		
		log.info('MonAst._GetConfig :: Requesting Asterisk Configuration (reload clients: %s)' % sendReload)
		
		self.clientQueuelock.acquire()
		self.monitoredUsersLock.acquire()
		self.meetmeLock.acquire()
		self.parkedLock.acquire()
		self.queuesLock.acquire()
		self.callsLock.acquire()
		self.channelsLock.acquire()
		
		users = self.monitoredUsers.keys()
		for user in users:
			if not self.monitoredUsers[user].has_key('forced'):
				del self.monitoredUsers[user]
		
		self.meetme   = {}
		self.parked   = {}
		self.queues   = {}
		self.calls    = {}
		self.channels = {}
		
		self.AMI.execute(['Action: SIPpeers'])
		self.AMI.execute(['Action: IAXpeers'], self.handlerParseIAXPeers)
		self.AMI.execute(['Action: Command', 'Command: skype show users'], self.handlerParseSkypeUsers)
		self.AMI.execute(['Action: GetConfig', 'Filename: meetme.conf'], self.handlerGetConfigMeetme)
		self.AMI.execute(['Action: QueueStatus'])
		
		self.getChannelsCallsStatus = True
		
		# Meetme and Parked Status will be parsed after handlerStatusComplete
		self.getMeetmeAndParkStatus = True

		if sendReload:
			for session in self.clientQueues:
				self.clientQueues[session]['q'].put(self.parseJson(Action = 'Reload', Time = 10000))
		
		self.channelsLock.release()
		self.callsLock.release()
		self.queuesLock.release()
		self.parkedLock.release()
		self.meetmeLock.release()
		self.monitoredUsersLock.release()
		self.clientQueuelock.release()
		
	
	def start(self):
		
		signal.signal(signal.SIGUSR1, self._sigUSR1)
		signal.signal(signal.SIGTERM, self._sigTERM)
		signal.signal(signal.SIGHUP, self._sigHUP)
		
		self.AMI.start()
		
		try:
			while not self.AMI.isConnected or not self.AMI.isAuthenticated:
				time.sleep(1)
			
			self.tcc  = thread.start_new_thread(self.threadCheckStatus, ('threadCheckStatus', 2))
			self.tcs  = thread.start_new_thread(self.threadSocketClient, ('threadSocketClient', 2))
			self.tcqr = thread.start_new_thread(self.threadClientQueueRemover, ('threadClientQueueRemover', 2))
			
			#self._GetConfig() # Commented, this now is executted when monast is authenticated in AMI
				
			while self.running:
				time.sleep(1)
		except KeyboardInterrupt:
			log.info('MonAst.start :: Received KeyboardInterrupt -- Shutting Down')
			self.running = False
			
		self.AMI.close()
		
		while self.AMI.isConnected:
			time.sleep(1)
		
		log.log(logging.NOTICE, 'Monast :: Finished...')
	
	
	def _sigUSR1(self, *args):
		
		log.log(logging.NOTICE, 'MonAst :: Received SIGUSR1 -- Dumping Vars...')
	
		self.monitoredUsersLock.acquire()
		self.meetmeLock.acquire()
		self.parkedLock.acquire()
		self.queuesLock.acquire()
		self.channelsLock.acquire()
		self.callsLock.acquire()
		
		log.log(logging.NOTICE, 'self.monitoredUsers = %s' % repr(self.monitoredUsers))
		log.log(logging.NOTICE, 'self.meetme = %s' % repr(self.meetme))
		log.log(logging.NOTICE, 'self.parked = %s' % repr(self.parked))
		log.log(logging.NOTICE, 'self.queues = %s' % repr(self.queues))
		log.log(logging.NOTICE, 'self.queueMemberStatus = %s' % repr(self.queueMemberStatus))
		log.log(logging.NOTICE, 'self.queueMemberCalls = %s' % repr(self.queueMemberCalls))
		log.log(logging.NOTICE, 'self.queueClientStatus = %s' % repr(self.queueClientStatus))
		log.log(logging.NOTICE, 'self.channels = %s' % repr(self.channels))
		log.log(logging.NOTICE, 'self.calls = %s' % repr(self.calls))
		
		self.callsLock.release()
		self.channelsLock.release()
		self.queuesLock.release()
		self.parkedLock.release()
		self.meetmeLock.release()
		self.monitoredUsersLock.release()
		
		
	def _sigTERM(self, *args):
		
		log.log(logging.NOTICE, 'MonAst :: Received SIGTERM -- Shutting Down...')
		self.running = False
		
		
	def _sigHUP(self, *args):
		
		log.log(logging.NOTICE, 'MonAst :: Received SIGHUP -- Reloading...')
		if self.reloading:
			log.log(logging.NOTICE, 'MonAst._sigHUP :: Already reloading...')
			return
			
		self.reloading = True
		
		self.enqueue(Action = 'Reload', Time = 10000)

		self.AMI.close()
		while self.AMI.isConnected:
			time.sleep(1)
		
		self.socketClient.shutdown(2)
		self.socketClient.close()
		
		self.monitoredUsersLock.acquire()
		self.parkedLock.acquire()
		self.meetmeLock.acquire()
		self.callsLock.acquire()
		self.channelsLock.acquire()
		self.monitoredUsersLock.acquire()
		self.queuesLock.acquire()
		
		self.userDisplay    = {}
		self.monitoredUsers = {}
		self.parked         = {}
		self.meetme         = {}
		self.calls          = {}
		self.channels       = {}
		self.monitoredUsers = {}
		self.queues         = {}
		
		self.parkedLock.release()
		self.meetmeLock.release()
		self.callsLock.release()
		self.channelsLock.release()
		self.monitoredUsersLock.release()
		self.queuesLock.release()
		self.monitoredUsersLock.release()

		self.parseConfig()
		self.AMI.start()
		self._GetConfig(False)
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
