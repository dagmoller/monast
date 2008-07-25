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
#     * Neither the name of the <ORGANIZATION> nor the names of its contributors
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
import time
import pprint
import socket
import random
import thread
import threading
import traceback
import getopt
import Queue
import log
from ConfigParser import SafeConfigParser

MONAST_CALLERID = "MonAst WEB"

rePeerEntry         = re.compile('Event: PeerEntry|Channeltype: ([^\r^\n^\s]*)|ObjectName: ([^\r^\n^\s]*)|IPaddress: ([^\r^\n^\s]*)|IPport: ([^\r^\n^\s]*)|Status: ([^\r^\n]*)')
rePeerStatus        = re.compile('Event: PeerStatus|Peer: ([^\r^\n^\s]*)|PeerStatus: ([^\r^\n^\s]*)')
reNewChannel        = re.compile('Event: Newchannel|Channel: ([^\r^\n^\s]*)|State: ([^\r^\n^\s]*)|CallerIDNum: ([^\r^\n^\s]*)|CallerIDName: ([^\r^\n]*)|Uniqueid: ([^\r^\n^\s]*)')
reHangup            = re.compile('Event: Hangup|Channel: ([^\r^\n^\s]*)|Uniqueid: ([^\r^\n^\s]*)|Cause: ([^\r^\n^\s]*)|Cause-txt: ([^\r^\n]*)')
reNewState          = re.compile('Event: Newstate|Channel: ([^\r^\n^\s]*)|State: ([^\r^\n^\s]*)|CallerID: ([^\r^\n^\s]*)|CallerIDName: ([^\r^\n^]*)|Uniqueid: ([^\r^\n^\s]*)')
reDial              = re.compile('Event: Dial|Source: ([^\r^\n^\s]*)|Destination: ([^\r^\n^\s]*)|CallerID: ([^\r^\n^\s]*)|CallerIDName: ([^\r^\n]*)|SrcUniqueID: ([^\r^\n^\s]*)|DestUniqueID: ([^\r^\n^\s]*)')
reLink              = re.compile('Event: Link|Channel1: ([^\r^\n^\s]*)|Channel2: ([^\r^\n^\s]*)|Uniqueid1: ([^\r^\n^\s]*)|Uniqueid2: ([^\r^\n^\s]*)|CallerID1: ([^\r^\n^\s]*)|CallerID2: ([^\r^\n^\s]*)')
reUnlink            = re.compile('Event: Unlink|Channel1: ([^\r^\n^\s]*)|Channel2: ([^\r^\n^\s]*)|Uniqueid1: ([^\r^\n^\s]*)|Uniqueid2: ([^\r^\n^\s]*)|CallerID1: ([^\r^\n^\s]*)|CallerID2: ([^\r^\n^\s]*)')
reNewcallerid       = re.compile('Event: Newcallerid|Channel: ([^\r^\n^\s]*)|CallerID: ([^\r^\n^\s]*)|CallerIDName: ([^\r^\n]*)|Uniqueid: ([^\r^\n^\s]*)|CID-CallingPres: ([^\r^\n]*)')
reRename            = re.compile('Event: Rename|Oldname: ([^\r^\n^\s]*)|Newname: ([^\r^\n^\s]*)|Uniqueid: ([^\r^\n^\s]*)')
reMeetmeJoin        = re.compile('Event: MeetmeJoin|Uniqueid: ([^\r^\n^\s]*)|Meetme: ([^\r^\n^\s]*)|Usernum: ([^\r^\n^\s]*)|CallerIDnum: ([^\r^\n^\s]*)|CallerIDname: ([^\r^\n]*)')
reMeetmeLeave       = re.compile('Event: MeetmeLeave|Uniqueid: ([^\r^\n^\s]*)|Meetme: ([^\r^\n^\s]*)|Usernum: ([^\r^\n^\s]*)|Duration: ([^\r^\n^\s]*)')
reStatus            = re.compile('Event: Status|Channel: ([^\r^\n^\s]*)|CallerIDNum: ([^\r^\n^\s]*)|CallerIDName: ([^\r^\n]*)|State: ([^\r^\n^\s]*)|Seconds: ([^\r^\n^\s]*)|Link: ([^\r^\n^\s]*)|Uniqueid: ([^\r^\n^\s]*)')
reReload            = re.compile('Event: Reload|Message: ([^\r^\n]*)')
reChannelReload     = re.compile('Event: ChannelReload|Channel: ([^\r^\n^\s]*)|ReloadReason: ([^\r^\n]*)')
reParkedCall        = re.compile('Event: ParkedCall|Exten: ([^\r^\n^\s]*)|Channel: ([^\r^\n^\s]*)|From: ([^\r^\n^\s]*)|Timeout: ([^\r^\n^\s]*)|CallerID: ([^\r^\n^\s]*)|CallerIDName: ([^\r^\n]*)')
reUnparkedCall      = re.compile('Event: UnParkedCall|Exten: ([^\r^\n^\s]*)|Channel: ([^\r^\n^\s]*)|From: ([^\r^\n^\s]*)|CallerID: ([^\r^\n^\s]*)|CallerIDName: ([^\r^\n]*)')
reParkedCallTimeOut = re.compile('Event: ParkedCallTimeOut|Exten: ([^\r^\n^\s]*)|Channel: ([^\r^\n^\s]*)|CallerID: ([^\r^\n^\s]*)|CallerIDName: ([^\r^\n]*)')
reParkedCallGiveUp  = re.compile('Event: ParkedCallGiveUp|Exten: ([^\r^\n^\s]*)|Channel: ([^\r^\n^\s]*)|CallerID: ([^\r^\n^\s]*)|CallerIDName: ([^\r^\n]*)')


def merge(l):
	out = [None for x in l[0]]
	for t in l:
		for i in range(len(t)):
			if t[i]:
				out[i] = t[i]
	return out

class MyConfigParser(SafeConfigParser):
    def optionxform(self, optionstr):
        return optionstr

class MonAst:

	monastConfigFile = None

	HOSTNAME = None
	HOSTPORT = None
	USERNAME = None
	PASSWORD = None
	
	bindPort       = None
	tranferContext = None
	
	meetmeContext = None
	meetmePrefix  = None
	
	userDisplay = {} 
	
	socketAMI = None
	queueAMI  = Queue.Queue()
	
	connected = False
	run       = True
	
	pingResp  = True
	pingLimit = 60
	
	tRead = None
	tPing = None
	
	socketClient = None
	clientSocks  = {}
	clientQueues = {}
	
	clientSockLock  = threading.RLock()
	clientQueuelock = threading.RLock() 
	
	monitoredUsers     = {}
	monitoredUsersLock = threading.RLock()
	
	channels     = {}
	channelsLock = threading.RLock()
	
	calls     = {}
	callsLock = threading.RLock()
	
	meetme     = {}
	meetmeLock = threading.RLock()
	
	parked     = {}
	parkedLock = threading.RLock()
	
	configFiles    = ['sip.conf', 'iax.conf', 'meetme.conf']
	configFilesPop = []
	
	def send(self, lines):
		if self.connected:
			log.show('Enviando Comando: %s' % '\r\n'.join(lines))
			try:
				self.socketAMI.send('%s\r\n\r\n' % '\r\n'.join(lines))
			except socket.error, e:
				log.error('Erro enviando dados pelo socket: %s' % e)
	
	def ping(self, a, b):
		log.info('Starting Thread ping')
		t = 0
		while self.run:
			time.sleep(1)
			if t >= self.pingLimit and self.connected:
				if self.pingResp:
					log.info('Enviando PING')
					t = 0
					self.pingResp = False
					self.send(['Action: ping'])
				else:
					log.error('sem resposta apos %d segundos' % self.pingLimit)
					self.connected = False
					self.pingResp  = True
					self.close()
					
			t += 1
	
	def read(self, a, b):
		log.info('Starting Thread read')
		msg = ''
		while self.run:
			try:
				msg += self.socketAMI.recv(1024 * 16)
				if msg.endswith('\r\n\r\n'):
					self.parse(msg)
					msg = ''
			except socket.error, e:
				log.error('Thread read :: Erro lendo socket: %s' % e)
				self.connected = False
				time.sleep(10)
			except:
				log.error('\n' + traceback.format_exc())
				self.connected = False
				time.sleep(10)
	
	def connect(self):
		while not self.connected:
			try:
				log.info('Conectando a %s:%d' % (self.HOSTNAME, self.HOSTPORT))
				self.socketAMI = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
				self.socketAMI.connect((self.HOSTNAME, self.HOSTPORT))
				self.connected = True
				self.login()
			except socket.error, e:
				log.error('Erro conectando a %s:%d -- %s' % (self.HOSTNAME, self.HOSTPORT, e))
				time.sleep(30)
		
		for conf in self.configFiles:
			self.send(['Action: GetConfig', 'Filename: %s' % conf])
			self.configFilesPop.append(conf)
		
		if not self.tRead:
			self.tRead = thread.start_new_thread(self.read, ('read', 2))
			self.tPing = thread.start_new_thread(self.ping, ('ping', 2))
			
	def close(self):
		log.info('Fechando socket')
		try:
			self.socketAMI.shutdown(2) # same as socket.SHUT_RDWR
			self.socketAMI.close()
		except socket.error, e:
			log.error('Erro fechando socket: %s' % e)
	
	def login(self):
		log.info('Efetuando login')
		self.send(['Action: login', 'Username: %s' % self.USERNAME, 'Secret: %s' % self.PASSWORD])
		
	def logoff(self):
		log.info('Efetuando logoff')
		self.send(['Action: logoff'])
	
	def parse(self, msg):
		msg = msg.strip()
		if msg:
			enqueue = []
			blocks  = msg.split('\r\n\r\n')
			for block in blocks:
				block = block.strip()
				if block == 'Response: Pong':
					log.info('Recebido PONG')
					self.pingResp = True
					continue
				
				log.show(block)
				
				if block.startswith('Response: Success\r\nCategory-'):
					self.parseConfig(block.replace('Response: Success\r\n', ''), self.configFilesPop.pop(0))
				
				if block.startswith('Response: Follows\r\nPrivilege: Command\r\nActionID:'):
					log.info('Command resposnse detected')
					ActionID = re.compile('ActionID: ([^\r^\n^\s]*)').search(block).group(1)
					Response = block[block.find(ActionID) + len(ActionID):block.find('--END COMMAND--')]
					
					self.clientQueuelock.acquire()
					if self.clientQueues.has_key(ActionID):
						self.clientQueues[ActionID]['q'].put('CliResponse: %s' % Response.replace('\r\n', '<br>'))
					self.clientQueuelock.release()
				
				if block.startswith('Event: PeerEntry\r\n'):
					Channeltype, ObjectName, IPaddress, IPport, Status = merge(rePeerEntry.findall(block))
					
					log.info('Evento PeerEntry detectado para: %s' % ObjectName)
					
					if Status.startswith('OK'):
						Status = 'Registered'
					elif Status.find('(') != -1:
						Status = Status[0:Status.find('(')]
					
					self.monitoredUsersLock.acquire()
					user = '%s/%s' % (Channeltype, ObjectName)
					if self.monitoredUsers.has_key(user):
						self.monitoredUsers[user]['Status'] = Status
					self.monitoredUsersLock.release()
					
				if block.startswith('Event: PeerStatus\r\n'):
					Peer, PeerStatus = merge(rePeerStatus.findall(block))
					
					log.info('Evento PeerStatus detectado para: %s' % Peer)
					
					self.monitoredUsersLock.acquire()
					if self.monitoredUsers.has_key(Peer):
						mu = self.monitoredUsers[Peer]
						mu['Status'] = PeerStatus
						enqueue.append('PeerStatus: %s:::%s:::%s' % (Peer, mu['Status'], mu['Calls']))
					self.monitoredUsersLock.release()
				
				if block.startswith('Event: Newchannel\r\n'):
					Channel, State, CallerIDNum, CallerIDName, Uniqueid = merge(reNewChannel.findall(block))
					
					log.info('Evento NewChannel detectado')
					
					self.channelsLock.acquire()
					self.channels[Uniqueid] = {'Channel': Channel, 'State': State, 'CallerIDNum': CallerIDNum, 'CallerIDName': CallerIDName}
					self.channelsLock.release()
					
					self.monitoredUsersLock.acquire()
					user = Channel
					if Channel.rfind('-') != -1:
						user = Channel[:Channel.rfind('-')]
					if self.monitoredUsers.has_key(user):
						self.monitoredUsers[user]['Calls'] += 1
						enqueue.append('PeerStatus: %s:::%s:::%s' % (user, self.monitoredUsers[user]['Status'], self.monitoredUsers[user]['Calls']))
					self.monitoredUsersLock.release()
					
					enqueue.append('NewChannel: %s:::%s:::%s:::%s:::%s' % (Channel, State, CallerIDNum, CallerIDName, Uniqueid))
				
				if block.startswith('Event: Newstate\r\n'):
					Channel, State, CallerID, CallerIDName, Uniqueid = merge(reNewState.findall(block))
					
					log.info('Evento NewState detectado')
					
					self.channelsLock.acquire()
					try:
						self.channels[Uniqueid]['State'] = State
						enqueue.append('NewState: %s:::%s:::%s:::%s:::%s' % (Channel, State, CallerID, CallerIDName, Uniqueid))
					except:
						pass
					self.channelsLock.release()
				
				if block.startswith('Event: Hangup\r\n'):
					Channel, Uniqueid, Cause, Cause_txt = merge(reHangup.findall(block))
					
					log.info('Evento Hangup detectado')
					
					self.channelsLock.acquire()
					try:
						del self.channels[Uniqueid]
						enqueue.append('Hangup: %s:::%s:::%s:::%s' % (Channel, Uniqueid, Cause, Cause_txt))
					except:
						pass
					self.channelsLock.release()
					
					self.callsLock.acquire()
					toDelete = None
					for id in self.calls:
						if id.find(Uniqueid) != -1 and self.calls[id]['Status'] == 'Dial':
							toDelete = id
							break
					if toDelete:
						del self.calls[toDelete]
						src, dst = toDelete.split('-')
						enqueue.append('Unlink: FAKE:::FAKE:::%s:::%s:::FAKE:::FAKE' % (src, dst))
					self.callsLock.release()
					
					self.monitoredUsersLock.acquire()
					user = Channel
					if Channel.rfind('-') != -1:
						user = Channel[:Channel.rfind('-')]
					if self.monitoredUsers.has_key(user) and self.monitoredUsers[user]['Calls'] > 0:
						self.monitoredUsers[user]['Calls'] -= 1
						enqueue.append('PeerStatus: %s:::%s:::%s' % (user, self.monitoredUsers[user]['Status'], self.monitoredUsers[user]['Calls']))
					self.monitoredUsersLock.release()
					
				if block.startswith('Event: Dial\r\n'):
					Source, Destination, CallerID, CallerIDName, SrcUniqueID, DestUniqueID = merge(reDial.findall(block))
					
					log.info('Evento Dial detectado')
					
					self.callsLock.acquire()
					self.calls['%s-%s' % (SrcUniqueID, DestUniqueID)] = {
						'Source': Source, 'Destination': Destination, 'CallerID': CallerID, 'CallerIDName': CallerIDName, 
						'SrcUniqueID': SrcUniqueID, 'DestUniqueID': DestUniqueID, 'Status': 'Dial', 'startTime': 0
					}
					self.callsLock.release()
					
					enqueue.append('Dial: %s:::%s:::%s:::%s:::%s:::%s' % (Source, Destination, CallerID, CallerIDName, SrcUniqueID, DestUniqueID))
					
				if block.startswith('Event: Link\r\n'):
					Channel1, Channel2, Uniqueid1, Uniqueid2, CallerID1, CallerID2 = merge(reLink.findall(block))
					
					log.info('Evento Link detectado')
					
					self.callsLock.acquire()
					try:
						self.calls['%s-%s' % (Uniqueid1, Uniqueid2)]['Status'] = 'Link'
						if self.calls['%s-%s' % (Uniqueid1, Uniqueid2)]['startTime'] == 0:
							self.calls['%s-%s' % (Uniqueid1, Uniqueid2)]['startTime'] = time.time()
						#enqueue.append('Link: %s:::%s:::%s:::%s:::%s:::%s' % (Channel1, Channel2, Uniqueid1, Uniqueid2, CallerID1, CallerID2))
					except:
						self.calls['%s-%s' % (Uniqueid1, Uniqueid2)] = {
							'Source': Channel1, 'Destination': Channel2, 'CallerID': CallerID1, 'CallerIDName': '', 
							'SrcUniqueID': Uniqueid1, 'DestUniqueID': Uniqueid2, 'Status': 'Link', 'startTime': time.time()
						}
					Seconds = time.time() - self.calls['%s-%s' % (Uniqueid1, Uniqueid2)]['startTime']
					enqueue.append('Link: %s:::%s:::%s:::%s:::%s:::%s:::%d' % (Channel1, Channel2, Uniqueid1, Uniqueid2, CallerID1, CallerID2, Seconds))
					self.callsLock.release()
				
				if block.startswith('Event: Unlink\r\n'):
					Channel1, Channel2, Uniqueid1, Uniqueid2, CallerID1, CallerID2 = merge(reUnlink.findall(block))
					
					log.info('Evento Unlink detectado')
					
					self.callsLock.acquire()
					try:
						del self.calls['%s-%s' % (Uniqueid1, Uniqueid2)]
						enqueue.append('Unlink: %s:::%s:::%s:::%s:::%s:::%s' % (Channel1, Channel2, Uniqueid1, Uniqueid2, CallerID1, CallerID2))
					except:
						pass
					self.callsLock.release()
					
				if block.startswith('Event: Newcallerid\r\n'):
					Channel, CallerID, CallerIDName, Uniqueid, CIDCallingPres = merge(reNewcallerid.findall(block))
					
					log.info('Evento Newcallerid detectado')
					
					self.channelsLock.acquire()
					self.channels[Uniqueid]['CallerIDName'] = CallerIDName
					self.channels[Uniqueid]['CallerIDNum']  = CallerID
					self.channelsLock.release()
					
					enqueue.append('NewCallerid: %s:::%s:::%s:::%s:::%s' % (Channel, CallerID, CallerIDName, Uniqueid, CIDCallingPres))
					
				if block.startswith('Event: Rename\r\n'):
					Oldname, Newname, Uniqueid = merge(reRename.findall(block))
					CallerIDName = ''
					CallerID     = ''
					
					log.info('Evento Rename Detectado')
					
					try:
						self.channelsLock.acquire()
						self.channels[Uniqueid]['Channel'] = Newname
						self.channelsLock.release()
					
						self.callsLock.acquire()
						for call in self.calls:
							SrcUniqueID, DestUniqueID = call.split('-')
							key = None
							if (SrcUniqueID == Uniqueid):
								key = 'Source'
							if (DestUniqueID == Uniqueid):
								key = 'Destination'
							if key:
								self.calls[call][key] = Newname
								CallerIDName = self.calls[call]['CallerIDName']
								CallerID     = self.calls[call]['CallerID']
								break							
						self.callsLock.release()
						
						enqueue.append('Rename: %s:::%s:::%s:::%s:::%s' % (Oldname, Newname, Uniqueid, CallerIDName, CallerID))
					except:
						log.error('Channel %s nao existe em self.channels, ignorado.' % Oldname)
						
				if block.startswith('Event: MeetmeJoin'):
					Uniqueid, Meetme, Usernum, CallerIDNum, CallerIDName = merge(reMeetmeJoin.findall(block))
					
					log.info('Evento MeetmeJoin detectado')
					
					self.meetmeLock.acquire()
					self.channelsLock.acquire()
					self.meetme[Meetme][Usernum] = {'Uniqueid': Uniqueid, 'CallerIDNum': CallerIDNum, 'CallerIDName': CallerIDName}
					ch = self.channels[Uniqueid]
					enqueue.append('MeetmeJoin: %s:::%s:::%s:::%s:::%s:::%s' % (Meetme, Uniqueid, Usernum, ch['Channel'], CallerIDNum, CallerIDName))
					self.channelsLock.release()
					self.meetmeLock.release()
				
				if block.startswith('Event: MeetmeLeave'):
					Uniqueid, Meetme, Usernum, Duration = merge(reMeetmeLeave.findall(block))
					
					log.info('Evento MeetmeLeave detectado')
					
					self.meetmeLock.acquire()
					try:
						del self.meetme[Meetme][Usernum]
						enqueue.append('MeetmeLeave: %s:::%s:::%s:::%s' % (Meetme, Uniqueid, Usernum, Duration))
					except Exception, e:
						log.error('Meetme or Usernum not found in self.meetme[\'%s\'][\'%s\']' % (Meetme, Usernum))
					self.meetmeLock.release()
				
				if block.startswith('Event: Reload'):
					log.info('Event Reload detected')
					for conf in self.configFiles:
						self.send(['Action: GetConfig', 'Filename: %s' % conf])
						self.configFilesPop.append(conf)
						
				if block.startswith('Event: ChannelReload'):
					log.info('Event ChannelReload detected')
					Channel, ReloadReason = merge(reChannelReload.findall(block))
					fileName = None
					if Channel == 'SIP':
						fileName = 'sip.conf'
					
					if fileName:
						self.send(['Action: GetConfig', 'Filename: %s' % fileName])
						self.configFilesPop.append(fileName)
						
						self.clientQueuelock.acquire()
						for session in self.clientQueues:
							self.clientQueues[session]['q'].put('Reload: 10')
						self.clientQueuelock.release()
				
				if block.startswith('Event: ParkedCall\r\n'):
					log.info('Event ParkedCall detected')
					Exten, Channel, From, Timeout, CallerID, CallerIDName = merge(reParkedCall.findall(block))
					
					self.parkedLock.acquire()
					self.parked[Exten] = {'Channel': Channel, 'From': From, 'Timeout': Timeout, 'CallerID': CallerID, 'CallerIDName': CallerIDName}
					enqueue.append('ParkedCall: %s:::%s:::%s:::%s:::%s:::%s' % (Exten, Channel, From, Timeout, CallerID, CallerIDName))
					self.parkedLock.release()
					
				if block.startswith('Event: UnParkedCall\r\n'):
					log.info('Event UnParkedCall detected')
					Exten, Channel, From, CallerID, CallerIDName = merge(reUnparkedCall.findall(block))
					
					self.parkedLock.acquire()
					try:
						del self.parked[Exten]
						enqueue.append('UnparkedCall: %s' % (Exten))
					except:
						log.error('UnParkedCall => Parked Exten not found: %s' % Exten)
					self.parkedLock.release()
				
				if block.startswith('Event: ParkedCallTimeOut\r\n'):
					log.info('Event ParkedCallTimeOut detected')
					Exten, Channel, CallerID, CallerIDName = merge(reParkedCallTimeOut.findall(block))
					
					self.parkedLock.acquire()
					try:
						del self.parked[Exten]
						enqueue.append('UnparkedCall: %s' % (Exten))
					except:
						log.error('ParkedCallTimeOut => Parked Exten not found: %s' % Exten)
					self.parkedLock.release()
				
				if block.startswith('Event: ParkedCallGiveUp\r\n'):
					log.info('Event ParkedCallGiveUp detected')
					Exten, Channel, CallerID, CallerIDName = merge(reParkedCallGiveUp.findall(block))
					
					self.parkedLock.acquire()
					try:
						del self.parked[Exten]
						enqueue.append('UnparkedCall: %s' % (Exten))
					except:
						log.error('ParkedCallGiveUp => Parked Exten not found: %s' % Exten)
					self.parkedLock.release()
				
				## the next 3 blocks (3 ifs), will garante that no channels will be dummed in monast
				## pasrts of this blocks are copied from other blocks like Hangup, Link
				## keep this 3 blocks in last
				if block == 'Response: Success\r\nMessage: Channel status will follow':
					log.info('Cleaning channelStatus')
					self.channelStatus = []
					
				if block == 'Event: StatusComplete':
					log.info('Event StatusComplete detected')
					
					self.channelsLock.acquire()
					self.callsLock.acquire()
					lostChannels = [i for i in self.channels.keys() if i not in self.channelStatus]
					for Uniqueid in lostChannels:
						log.log('Removing lost channel %s' % Uniqueid)
						try:
							Channel = self.channels[Uniqueid]['Channel']
							del self.channels[Uniqueid]
							enqueue.append('Hangup: %s:::%s:::FAKE:::FAKE' % (Channel, Uniqueid))
						except:
							pass
						
						toDelete = None
						for id in self.calls:
							if id.find(Uniqueid) != -1 and self.calls[id]['Status'] == 'Dial':
								toDelete = id
								break
						if toDelete:
							del self.calls[toDelete]
							src, dst = toDelete.split('-')
							enqueue.append('Unlink: FAKE:::FAKE:::%s:::%s:::FAKE:::FAKE' % (src, dst))
						
						self.monitoredUsersLock.acquire()
						user = Channel
						if Channel.rfind('-') != -1:
							user = Channel[:Channel.rfind('-')]
						if self.monitoredUsers.has_key(user) and self.monitoredUsers[user]['Calls'] > 0:
							self.monitoredUsers[user]['Calls'] -= 1
							enqueue.append('PeerStatus: %s:::%s:::%s' % (user, self.monitoredUsers[user]['Status'], self.monitoredUsers[user]['Calls']))
						self.monitoredUsersLock.release()
					self.callsLock.release()
					self.channelsLock.release()
				
				if block.startswith('Event: Status\r\n'):
					Channel, CallerIDNum, CallerIDName, State, Seconds, Link, Uniqueid = merge(reStatus.findall(block))
					
					log.info('Event Status detected')
					
					self.channelStatus.append(Uniqueid)
					
					self.channelsLock.acquire()
					if not self.channels.has_key(Uniqueid):
						self.channels[Uniqueid] = {'Channel': Channel, 'State': State, 'CallerIDNum': CallerIDNum, 'CallerIDName': CallerIDName}
						self.monitoredUsersLock.acquire()
						user = Channel
						if Channel.rfind('-') != -1:
							user = Channel[:Channel.rfind('-')]
						if self.monitoredUsers.has_key(user):
							self.monitoredUsers[user]['Calls'] += 1
							enqueue.append('PeerStatus: %s:::%s:::%s' % (user, self.monitoredUsers[user]['Status'], self.monitoredUsers[user]['Calls']))
						self.monitoredUsersLock.release()
						enqueue.append('NewChannel: %s:::%s:::%s:::%s:::%s' % (Channel, State, CallerIDNum, CallerIDName, Uniqueid))
						if Link:
							for UniqueidLink in self.channels:
								if self.channels[UniqueidLink]['Channel'] == Link:
									self.callsLock.acquire()
									self.calls['%s-%s' % (Uniqueid, UniqueidLink)] = {
										'Source': Channel, 'Destination': Link, 'CallerID': CallerIDNum, 'CallerIDName': CallerIDName, 
										'SrcUniqueID': Uniqueid, 'DestUniqueID': UniqueidLink, 'Status': 'Link', 'startTime': time.time() - int(Seconds)
									}
									self.callsLock.release()
									enqueue.append('Link: %s:::%s:::%s:::%s:::%s:::%s:::%d' % \
												(Channel, Link, Uniqueid, UniqueidLink, CallerIDNum, self.channels[UniqueidLink]['CallerIDNum'], int(Seconds)))
					self.channelsLock.release()
			
			self.clientQueuelock.acquire()
			for msg in enqueue:
				for session in self.clientQueues:
					self.clientQueues[session]['q'].put(msg)
			self.clientQueuelock.release()
	
	def parseConfig(self, msg, type):
		log.info('Parsing %s' % type)
		lines = msg.split('\r\n')
		
		if type in ('sip.conf', 'iax.conf'): # SIP or IAX
			user = None
			tech = None
			if type == 'sip.conf':
				tech = 'SIP'
				self.send(['Action: SIPPeers'])
			if type == 'iax.conf':
				tech = 'IAX2'
				self.send(['Action: IAXPeers'])
			self.monitoredUsersLock.acquire()
			oldUsers = []
			newUsers = []
			# get actual users
			for user in self.monitoredUsers:
				if user.startswith(tech):
					oldUsers.append(user)
			for line in lines:
				if line.startswith('Category-') and not line.endswith(': general') and not line.endswith(': authentication'):
					user = '%s/%s' % (tech, line[line.find(': ') + 2:]) 
					if self.userDisplay['DEFAULT'] and not self.userDisplay.has_key(user):
						self.monitoredUsers[user] = {'Channeltype': tech, 'Status': '--', 'Calls': 0, 'CallerID': '--', 'Context': 'default', 'Variables': []}
					elif not self.userDisplay['DEFAULT'] and self.userDisplay.has_key(user):
						self.monitoredUsers[user] = {'Channeltype': tech, 'Status': '--', 'Calls': 0, 'CallerID': '--', 'Context': 'default', 'Variables': []}
					else:
						user = None

				newUsers.append(user)
				
				if user and line.startswith('Line-'):
					tmp, param = line.split(': ')
					if param.startswith('callerid'):
						quotes = re.compile("['\"]")
						self.monitoredUsers[user]['CallerID'] = quotes.sub("", param[param.find('=')+1:])
					if param.startswith('context'):
						self.monitoredUsers[user]['Context'] = param[param.find('=')+1:]
					if param.startswith('setvar'):
						self.monitoredUsers[user]['Variables'].append(param[param.find('=')+1:])
			for user in [i for i in oldUsers if i not in newUsers]:
				del self.monitoredUsers[user]
			self.monitoredUsersLock.release()
		
		elif type == 'meetme.conf':
			self.meetmeLock.acquire()
			for line in lines:
				if line.startswith('Line-') and line.find('conf=') != -1:
					params = line[line.find('conf=')+5:].split(',')
					self.meetme[params[0]] = {}
			self.meetmeLock.release()
			
			# deve ser executado no parser do ultimo arquivo
			self.clientQueuelock.acquire()
			for session in self.clientQueues:
				self.clientQueues[session]['q'].put('Reload: 10')
			self.clientQueuelock.release()
					
	def clientSocket(self, a, b):
		log.info('Starting Thread clientSocket')
		while self.run:
			try:
				(sc, addr) = self.socketClient.accept()
				log.info('Novo cliente: %s' % str(addr))
				self.clientSockLock.acquire()
				threadId  = 'clientThread-%s' % random.random()
				self.clientSocks[threadId] = thread.start_new_thread(self.clientThread, (threadId, sc, addr))
				self.clientSockLock.release()
			except:
				pass
	
	def clientThread(self, id, sock, addr):
		session  = None
		localRun = True
		count    = 0
		log.info('Starting %s' % id)
		try:
			while self.run and localRun:
				msg = sock.recv(1024)
				if msg.strip():
					msgs = msg.strip().split('\r\n')
					for msg in msgs:
						log.log('Client %s: %s' % (str(addr), msg))
						self.clientQueuelock.acquire()
						if msg.upper().startswith('SESSION: '):
							session = msg[9:]
							if not self.clientQueues.has_key(session):
								self.clientQueues[session] = {'q': Queue.Queue(), 't': time.time()}
								sock.send('NEW SESSION\r\n')
							else:
								self.clientQueues[session]['t'] = time.time()
								sock.send('OK\r\n')
						elif session and msg.upper() == 'GET STATUS':
							self.monitoredUsersLock.acquire()
							self.channelsLock.acquire()
							self.callsLock.acquire()
							self.meetmeLock.acquire()
							self.parkedLock.acquire()
							
							self.clientQueues[session]['t'] = time.time()
							sock.send('BEGIN STATUS\r\n')
							
							users = self.monitoredUsers.keys()
							users.sort()
							for user in users:
								mu = self.monitoredUsers[user]
								CallerID = mu['CallerID']
								if CallerID == '--':
									CallerID = user
								sock.send('PeerStatus: %s:::%s:::%s:::%s\r\n' % (user, mu['Status'], mu['Calls'], CallerID))
							for Uniqueid in self.channels:
								ch = self.channels[Uniqueid]
								sock.send('NewChannel: %s:::%s:::%s:::%s:::%s\r\n' % (ch['Channel'], ch['State'], ch['CallerIDNum'], ch['CallerIDName'], Uniqueid))
							for call in self.calls:
								c = self.calls[call]
								src, dst = call.split('-')
								try:
									sock.send('Call: %s:::%s:::%s:::%s:::%s:::%s:::%s:::%s:::%d\r\n' % (c['Source'], c['Destination'], c['CallerID'], c['CallerIDName'], \
																	self.channels[dst]['CallerIDNum'], c['SrcUniqueID'], c['DestUniqueID'], c['Status'], time.time() - c['startTime']))
								except:
									log.error('-- GET STATUS (formatted Traceback on "for call in self.calls") --\n' + traceback.format_exc())
							meetmeRooms = self.meetme.keys()
							meetmeRooms.sort()
							for meetme in meetmeRooms:
								sock.send('MeetmeRoom: %s\r\n' % meetme)
								for Usernum in self.meetme[meetme]:
									mm = self.meetme[meetme][Usernum]
									ch = self.channels[mm['Uniqueid']]
									sock.send('MeetmeJoin: %s:::%s:::%s:::%s:::%s:::%s\r\n' % (meetme, mm['Uniqueid'], Usernum, ch['Channel'], mm['CallerIDNum'], mm['CallerIDName']))
							
							parkedCalls = self.parked.keys()
							parkedCalls.sort()
							for Exten in parkedCalls:
								pc = self.parked[Exten]
								sock.send('ParkedCall: %s:::%s:::%s:::%s:::%s:::%s' % (Exten, pc['Channel'], pc['From'], pc['Timeout'], pc['CallerID'], pc['CallerIDName']))
							
							sock.send('END STATUS\r\n')
							
							self.parkedLock.release()
							self.meetmeLock.release()
							self.callsLock.release()
							self.channelsLock.release()
							self.monitoredUsersLock.release()
						elif session and msg.upper() == 'GET CHANGES':
							self.clientQueues[session]['t'] = time.time()
							sock.send('BEGIN CHANGES\r\n')
							while True:
								try:
									msg = self.clientQueues[session]['q'].get(False)
									sock.send(msg + '\r\n')
								except Queue.Empty:
									break
							sock.send('END CHANGES\r\n')
						elif session and msg.startswith('OriginateCall'):
							self.monitoredUsersLock.acquire()
							action, src, dst, type = msg.split(':::')
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
							self.send(command)
							self.monitoredUsersLock.release()
						elif session and msg.startswith('OriginateDial'):
							action, src, dst, type = msg.split(':::')
							command = []
							command.append('Action: Originate')
							command.append('Channel: %s' % src)
							command.append('Application: Dial')
							command.append('Data: %s|30|rTt' % dst)
							command.append('CallerID: %s' % MONAST_CALLERID)
							self.send(command)
						elif session and msg.startswith('HangupChannel'):
							self.channelsLock.acquire()
							action, Uniqueid = msg.split(':::')
							try:
								command = []
								command.append('Action: Hangup')
								command.append('Channel: %s' % self.channels[Uniqueid]['Channel'])
								self.send(command)
							except:
								log.error('Uniqueid %s not found on self.channels' % Uniqueid)
							self.channelsLock.release()
						elif session and msg.startswith('TransferCall'):
							action, src, dst, type = msg.split(':::')
							Context      = self.tranferContext
							SrcChannel   = None
							ExtraChannel = None
							if type == 'peer':
								self.channelsLock.acquire()
								SrcChannel  = self.channels[src]['Channel']
								self.channelsLock.release()
								tech, exten = dst.split('/')
								try:
									exten = int(exten)
								except:
									self.monitoredUsersLock.acquire()
									exten = self.monitoredUsers[dst]['CallerID']
									exten = exten[exten.find('<')+1:exten.find('>')]
									self.monitoredUsersLock.release()
							elif type == 'meetme':
								self.channelsLock.acquire()
								tmp = src.split('-')
								if len(tmp) == 2:
									SrcChannel   = self.channels[tmp[0]]['Channel']
									ExtraChannel = self.channels[tmp[1]]['Channel']
								else:
									SrcChannel   = self.channels[tmp[0]]['Channel']
								self.channelsLock.release()
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
							self.send(command)
						elif session and msg.startswith('ParkCall'):
							action, park, announce = msg.split(':::')
							self.channelsLock.acquire()
							ParkChannel   = self.channels[park]['Channel']
							AnouceChannel = self.channels[announce]['Channel']
							self.channelsLock.release()
							command = []
							command.append('Action: Park')
							command.append('Channel: %s' % ParkChannel)
							command.append('Channel2: %s' % AnouceChannel)
							#ommand.append('Timeout: 45')
							self.send(command)							 
						elif session and msg.startswith('MeetmeKick'):
							action, Meetme, Usernum = msg.split(':::')
							command = []
							command.append('Action: Command')
							command.append('Command: meetme kick %s %s' % (Meetme, Usernum))
							self.send(command)
						elif session and msg.startswith('ParkedHangup'):
							action, Exten = msg.split(':::')
							self.parkedLock.acquire()
							try:
								command = []
								command.append('Action: Hangup')
								command.append('Channel: %s' % self.parked[Exten]['Channel'])
								self.send(command)
							except:
								log.error('Exten %s not found on self.parked' % Exten)
							self.parkedLock.release()
						elif session and msg.startswith('CliCommand'):
							action, cliCommand = msg.split(':::')
							command = []
							command.append('Action: Command')
							command.append('Command: %s' % cliCommand)
							command.append('ActionID: %s' % session)
							self.send(command)
						else:
							sock.send('NO SESSION\r\n')	
						self.clientQueuelock.release()
						if msg.upper() == 'BYE':
							localRun = False
				else:
					# POG para encerrar a tread caso o socket do cliente fique louco (acontece)
					count += 1
					if count == 5:
						log.error('clientThread() 5 pools without messages, dropping client...')
						break
		except socket.error, e:
			log.error('Socket ERROR %s: %s' % (id, e))
			for lock in (self.clientQueuelock, self.monitoredUsersLock, self.channelsLock, self.callsLock, self.meetmeLock):
				try:
					lock.release()
				except:
					pass
		try:
			sock.close()
		except:
			pass
		log.info('Encerrando %s' % id)
		self.clientSockLock.acquire()
		del self.clientSocks[id]
		self.clientSockLock.release()
	
	def clienQueueRemover(self, a, b):
		log.info('Starting thread clienQueueRemover')
		while self.run:
			time.sleep(60)
			self.clientQueuelock.acquire()
			dels = []
			now = time.time()
			for session in self.clientQueues:
				past = self.clientQueues[session]['t']
				if int(now - past) > 600:
					dels.append(session)
			for session in dels:
				log.info('Removendo session morta: %s' % session)
				del self.clientQueues[session]
			self.clientQueuelock.release()
	
	def channelChecker(self, a, b):
		log.info('Starting thread channelChecker')
		time.sleep(10)
		while self.run:
			self.send(['Action: Status'])
			time.sleep(60)
	
	def start(self):
		cp = MyConfigParser()
		cp.read(self.monastConfigFile)
		
		self.HOSTNAME = cp.get('global', 'hostname')
		self.HOSTPORT = int(cp.get('global', 'hostport'))
		self.USERNAME = cp.get('global', 'username')
		self.PASSWORD = cp.get('global', 'password')	
		
		self.bindPort       = int(cp.get('global', 'bind_port'))
		self.tranferContext = cp.get('global', 'transfer_context')
		
		self.meetmeContext = cp.get('global', 'meetme_context')
		self.meetmePrefix  = cp.get('global', 'meetme_prefix')
		
		if cp.get('users', 'default') == 'show':
			self.userDisplay['DEFAULT'] = True 
		else:
			self.userDisplay['DEFAULT'] = False
		
		for user, display in cp.items('users'):
			if user.startswith('SIP') or user.startswith('IAX2'): 
				if self.userDisplay['DEFAULT'] and display == 'hide':
					self.userDisplay[user] = True
				if not self.userDisplay['DEFAULT'] and display == 'show':
					self.userDisplay[user] = True
			if display == 'force':
				tech, peer = user.split('/')
				self.monitoredUsers[user] = {'Channeltype': tech, 'Status': '--', 'Calls': 0, 'CallerID': '--', 'Context': 'default', 'Variables': []}
	
		try:
			self.socketClient = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			self.socketClient.bind(('0.0.0.0', self.bindPort))
			self.socketClient.listen(10)
		except socket.error, e:
			log.error("Cound not open socket on port %d, cause: %s" % (self.bindPort, e))
			sys.exit(1)
	
		self.cc  = thread.start_new_thread(self.channelChecker, ('channelChecker', 2))
		self.cs  = thread.start_new_thread(self.clientSocket, ('clientsSocket', 2))
		self.cqr = thread.start_new_thread(self.clienQueueRemover, ('clienQueueRemover', 2))
	
		try:
			while self.run:
				time.sleep(1)
				if not self.connected:
					self.connect()
		except KeyboardInterrupt:
			self.run = False
		
		self.logoff()
		self.close()

		while True:
			time.sleep(0.5)
			canBreak = False
			self.clientSockLock.acquire()
			if len(self.clientSocks) == 0:
				canBreak = True
			self.clientSockLock.release()
			if canBreak:
				break
			
		self.socketClient.shutdown(2) # same as socket.SHUT_RDWR 
		self.socketClient.close()

def _usage():
	
	usage = """
	Usage: %s [options]
	
	Options:
		-h | --help                     => display this help
		-c | --config <config file>     => use alterantive config file instead /etc/monast.conf
	""" % sys.argv[0]
	print usage
	sys.exit()

if __name__ == '__main__':

	try:
		opts, args = getopt.getopt(sys.argv[1:], 'hc:', ['help', 'config='])
	except:
		_usage()
	
	configFile = '/etc/monast.conf'
	
	for o, a in opts:
		if o in ('-h', '--help'):
			_usage()
		if o in ('-c', '--config'):
			configFile = a
			
	if not os.path.exists(configFile):
		print '  Config file "%s" not found.' % configFile
		print '  Run "%s --help" for help.' % sys.argv[0]
		sys.exit(1)

	monast = MonAst()
	monast.monastConfigFile = configFile
	monast.start()
