
/*
* Copyright (c) 2008, Diego Aguirre
* All rights reserved.
* 
* Redistribution and use in source and binary forms, with or without modification,
* are permitted provided that the following conditions are met:
* 
*     * Redistributions of source code must retain the above copyright notice, 
*       this list of conditions and the following disclaimer.
*     * Redistributions in binary form must reproduce the above copyright notice, 
*       this list of conditions and the following disclaimer in the documentation 
*       and/or other materials provided with the distribution.
*     * Neither the name of the DagMoller nor the names of its contributors
*       may be used to endorse or promote products derived from this software 
*       without specific prior written permission.
* 
* THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
* ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED 
* WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
* IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, 
* INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, 
* BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, 
* DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF 
* LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE 
* OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED 
* OF THE POSSIBILITY OF SUCH DAMAGE.
*/

// Global Functions
String.prototype.trim = function() { return this.replace(/^\s*/, "").replace(/\s*$/, ""); }

// Monast
var Monast = {
	// Globals
	_contextMenu: new YAHOO.widget.Menu("ContextMenu"),
	// Colors
	getColor: function (status)
	{
		status = status.toLowerCase().trim();
		switch (status)
		{
			// RED
			case 'down':
			case 'unregistered':
			case 'unreachable':
			case 'unknown':
			case 'unavailable':
			case 'invalid':
			case 'busy':
			case 'logged out':
				return '#ffb0b0';
			
			// YELLOW	
			case 'ring':
			case 'ringing':
			case 'ring, in use':
			case 'in use':
			case 'dial':
			case 'lagged':
			case 'on hold':
				return '#ffffb0';
				
			// GREEN
			case 'up':
			case 'link':
			case 'registered':
			case 'reachable':
			case 'unmonitored':
			case 'not in use':
			case 'logged in':
			case 'no alarm':
				return '#b0ffb0';
		}
		if (status.indexOf('signal') != -1)
		{
			var level = status.replace('%', '').replace('signal: ', '');
			if (level >= 70)
				return '#b0ffb0';
			if (level >= 40 && level < 70)
				return '#ffffb0';
			if (level < 40)
				return '#ffb0b0';
	    }
		return '#dddddd';
	},
	
	// Users/Peers
	userspeers: new Hash(),
	processUserpeer: function (u)
	{
		u.id          = md5(u.channel);
		u.statuscolor = this.getColor(u.status);
		u.callscolor  = u.calls > 0 ? this.getColor('in use') : this.getColor('not in use');
		
		if (Object.isUndefined(this.userspeers.get(u.id))) // User does not exists
		{
			var div           = document.createElement('div');
			div.id            = u.id;
			div.className     = 'peerTable';
			div.innerHTML     = new Template($('Template::Userpeer').innerHTML).evaluate(u);
			div.oncontextmenu = function () { return false; };
			div.onmouseup     = function (event)
			{
				var e = event ? event : window.event;
				if (e.button == 2)
					Monast.showUserpeerContextMenu(u.id);
			};
			$('fieldset-' + u.channeltype).appendChild(div);
		}
		else
		{
			$(u.id).innerHTML = new Template($('Template::Userpeer').innerHTML).evaluate(u);
		}
		this.userspeers.set(u.id, u);
	},
	showUserpeerContextMenu: function (id)
	{
		this._contextMenu.clearContent();
		this._contextMenu.cfg.queueProperty("xy", this.getMousePosition(event));
	
		var viewUserpeerInfo = function (p_sType, p_aArgs, p_oValue)
		{
			p_oValue.latency          = p_oValue.time == -1 ? "--" : p_oValue.time + " ms";
			p_oValue.channelVariables = [];
			
			if (p_oValue.variables.length > 0)
			{
				p_oValue.channelVariables.push('<tr><td colspan="2"><hr></td></tr>');
				p_oValue.channelVariables.push('<tr><td colspan="2" class="key" style="text-align: center;">Channel Variables</td></tr>');
			} 
			
			p_oValue.variables.each(function (v) {
				var item = v.split('=', 2);
				p_oValue.channelVariables.push('<tr><td class="key">' + item[0] + ':</td><td>' + item[1] + '</td></tr>');
			});
			
			Monast.doAlert(new Template($("Template::Userpeer::Info").innerHTML).evaluate(p_oValue));
			$("Template::Userpeer::Info::Table").innerHTML = $("Template::Userpeer::Info::Table").innerHTML + p_oValue.channelVariables.join("\n");
		};
		
		var u = this.userspeers.get(id);
		var m = [
			[
				{text: "Originate Call"},
				{text: "View User/Peer Info", onclick: {fn: viewUserpeerInfo, obj: u}}
			]
		];
		this._contextMenu.addItems(m);
		this._contextMenu.setItemGroupTitle("User/Peer: " + u.channel, 0);
		this._contextMenu.render(document.body);
		this._contextMenu.show();
	},
	
	// Channels
	channels: new Hash(),
	processChannel: function (c)
	{
		c.id         = c.uniqueid;
		c.statecolor = this.getColor(c.state);
		c.monitor    = c.monitor == "True" ? new Template($('Template::Channel::Monitor').innerHTML).evaluate(c) : "";
		c._channel   = c.channel.replace('<', '&lt;').replace('>', '&gt;');
		
		if (Object.isUndefined(this.channels.get(c.id))) // Channel does not exists
		{
			var div           = document.createElement('div');
			div.id            = c.id;
			div.className     = 'channelDiv';
			div.innerHTML     = new Template($('Template::Channel').innerHTML).evaluate(c);
			div.oncontextmenu = function () { return false; };
			div.onmouseup     = function (event)
			{
				var e = event ? event : window.event;
				if (e.button == 2)
					Monast.showChannelContextMenu(c.id);
			};
			$('channelsDiv').appendChild(div);
		}
		else
		{
			$(c.id).innerHTML = new Template($('Template::Channel').innerHTML).evaluate(c);
		}
		
		this.channels.set(c.id, c);
		$('countChannels').innerHTML = this.channels.keys().length; 
	},
	removeChannel: function (c)
	{
		var channel = this.channels.unset(c.uniqueid);
		if (!Object.isUndefined(channel))
			$('channelsDiv').removeChild($(channel.id));
		$('countChannels').innerHTML = this.channels.keys().length;
	},
	showChannelContextMenu: function (id)
	{
		this._contextMenu.clearContent();
		this._contextMenu.cfg.queueProperty("xy", this.getMousePosition(event));
	
		var viewChannelInfo = function (p_sType, p_aArgs, p_oValue)
		{
			p_oValue.monitortext = p_oValue.monitor ? "True" : "False";
			Monast.doAlert(new Template($("Template::Channel::Info").innerHTML).evaluate(p_oValue));
		};
	
		var c = this.channels.get(id);
		var m = [
			[
				{text: "Start Monitor", disabled: c.monitor},
				{text: "Stop Monitor", disabled: !c.monitor},
				{text: "Hangup"},
				{text: "View Channel Info", onclick: {fn: viewChannelInfo, obj: c}}
			]
		];
		this._contextMenu.addItems(m);
		this._contextMenu.setItemGroupTitle("Uniqueid:  " + c.uniqueid, 0);
		this._contextMenu.render(document.body);
		this._contextMenu.show();
	},
	
	// Bridges
	bridges: new Hash(),
	processBridge: function (b)
	{
		if (b.status == "Unlink")
		{
			this.removeBridge(b);
			return;
		}
	
		b.id              = md5(b.uniqueid + "+++" + b.bridgeduniqueid);
		b.statuscolor     = this.getColor(b.status);
		b._channel        = b.channel.replace('<', '&lt;').replace('>', '&gt;');
		b._bridgedchannel = b.bridgedchannel.replace('<', '&lt;').replace('>', '&gt;');
		b.callerid        = new Template("#{calleridname} &lt;#{calleridnum}&gt;").evaluate(this.channels.get(b.uniqueid));
		b.bridgedcallerid = new Template("#{calleridname} &lt;#{calleridnum}&gt;").evaluate(this.channels.get(b.bridgeduniqueid));
		
		if (Object.isUndefined(this.bridges.get(b.id))) // Bridge does not exists
		{
			var div       = document.createElement('div');
			div.id        = b.id;
			div.className = 'callDiv';
			div.innerHTML = new Template($("Template::Bridge").innerHTML).evaluate(b);
			$('callsDiv').appendChild(div);
		}
		else
		{
			$(b.id).innerHTML = new Template($("Template::Bridge").innerHTML).evaluate(b);
		}
		
		if (b.status == "Link")
		{
			this.stopChrono(b.id);
			this.startChrono(b.id, (new Date().getTime() / 1000) - b.starttime);
		}
		
		this.bridges.set(b.id, b);
		$('countCalls').innerHTML = this.bridges.keys().length;
	},
	removeBridge: function (b)
	{
		var id     = md5(b.uniqueid + "+++" + b.bridgeduniqueid);
		var bridge = this.bridges.unset(id);
		if (!Object.isUndefined(bridge))
		{
			$('callsDiv').removeChild($(bridge.id));
			this.stopChrono(id);
		}
		$('countCalls').innerHTML = this.bridges.keys().length;
	},
	
	// Meetmes
	meetmes: new Hash(),
	processMeetme: function (m)
	{
		m.id = md5("meetme-" + m.meetme);
		
		if (Object.isUndefined(this.meetmes.get(m.id))) // Meetme does not exists
		{
			var div       = document.createElement('div');
			div.id        = m.id;
			div.className = 'meetmeDivWrap';
			div.innerHTML = new Template($("Template::Meetme").innerHTML).evaluate(m);
			$('meetmeDivWrapper').appendChild(div);
		}
		else
		{
			$(m.id).innerHTML = new Template($("Template::Meetme").innerHTML).evaluate(m);
		}
	
		if (!Object.isArray(m.users))
		{
			var keys = Object.keys(m.users).sort();
			keys.each(function (user) {
				var user          = m.users[user];
				user.userinfo     = (user.calleridnum && user.calleridname) ? new Template("#{calleridname} &lt;#{calleridnum}&gt;").evaluate(user) : user.channel;
				var divUser       = document.createElement("div");
				divUser.className = 'meetmeDiv';
				divUser.innerHTML = new Template($("Template::Meetme::User").innerHTML).evaluate(user);
				$(m.id).appendChild(divUser);
			});
			$("countMeetme-" + m.id).innerHTML = keys.length;
		}

		this.meetmes.set(m.id, m);
	},
	removeMeetme: function (m)
	{
		var id     = md5("meetme-" + m.meetme);
		var meetme = this.meetmes.unset(id);
		if (!Object.isUndefined(meetme))
		{
			$('meetmeDivWrapper').removeChild($(meetme.id));
		}
	},
	
	// Queues
	queuesDual: [],
	queues: new Hash(),
	processQueue: function (q)
	{
		q.id = md5("queue-" + q.queue);
		
		if (Object.isUndefined(this.queues.get(q.id))) // Queue does not exists
		{
			var div       = document.createElement('div');
			div.id        = q.id;
			div.className = "queueDiv";
			div.innerHTML = new Template($("Template::Queue").innerHTML).evaluate(q);
			
			// Lookup Dual Free
			var dualid = null;
			if (this.queuesDual.length == 0)
			{
				this.queuesDual.push([div.id]);
				dualid = "dual::0";
			}
			else
			{
				var l = this.queuesDual.length;
				if (this.queuesDual[l - 1].length < 2)
				{
					this.queuesDual[l - 1].push(div.id);
					dualid = "dual::" + (l - 1);
				}
				else
				{
					this.queuesDual.push([div.id]);
					dualid = "dual::" + l;
				}
			}
			
			var dual = $(dualid);
			if (!dual)
			{
				dual             = document.createElement('div');
				dual.id          = dualid;
				dual.className   = 'queueDualDiv';
			}
			
			dual.appendChild(div);
			$('fieldset-queuedual').appendChild(dual);
		}
		else
		{
			$(q.id).innerHTML = new Template($("Template::Queue").innerHTML).evaluate(q);
		}
		q.members = new Hash();
		q.clients = new Hash();
		this.queues.set(q.id, q);
	},
	processQueueMember: function (m)
	{
		m.id          = md5("queueMember-" + m.queue + '::' + m.location);
		m.queueid     = md5("queue-" + m.queue);
		m.statuscolor = this.getColor(m.statustext); 
		
		var div       = document.createElement('div');
		div.id        = m.id;
		div.className = 'queueMembersDiv';
		div.innerHTML = new Template($("Template::Queue::Member").innerHTML).evaluate(m);
		div.oncontextmenu = function () { return false; };
		div.onmouseup     = function (event)
		{
			var e = event ? event : window.event;
			if (e.button == 2)
				Monast.showQueueMemberContextMenu(m.queueid, m.id);
		};
		$('queueMembers-' + m.queueid).appendChild(div);
		this.queues.get(m.queueid).members.set(m.id, m);
		$('queueMembersCount-' + m.queueid).innerHTML = this.queues.get(m.queueid).members.keys().length;
	},
	removeQueueMember: function (m)
	{
		var id       = md5("queueMember-" + m.queue + '::' + m.location);
		var queueid  = md5("queue-" + m.queue);
		var member = this.queues.get(queueid).members.unset(id);
		if (!Object.isUndefined(member))
		{
			$('queueMembers-' + member.queueid).removeChild($(member.id));
		}
		$('queueMembersCount-' + member.queueid).innerHTML = this.queues.get(member.queueid).members.keys().length;
	},
	showQueueMemberContextMenu: function (queueid, id)
	{
		this._contextMenu.clearContent();
		this._contextMenu.cfg.queueProperty("xy", this.getMousePosition(event));
	
		var viewMemberInfo = function (p_sType, p_aArgs, p_oValue)
		{
			p_oValue.pausedtext   = p_oValue.paused == "1" ? "True" : "False";
			p_oValue.lastcalltext = new Date(p_oValue.lastcall * 1000).toLocaleString();
			Monast.doAlert(new Template($("Template::Queue::Member::Info").innerHTML).evaluate(p_oValue));
		};
		
		var qm = this.queues.get(queueid).members.get(id);
		var m = [
			[
				{text: qm.paused == "0" ? "Pause Member" : "Unpause Member"},
				{text: "Remove Member"},
				{text: "View Member Info", onclick: {fn: viewMemberInfo, obj: qm}}
			]
		];
		this._contextMenu.addItems(m);
		this._contextMenu.setItemGroupTitle("Queue Member:  " + qm.name, 0);
		this._contextMenu.render(document.body);
		this._contextMenu.show();
	},
	processQueueClient: function (c)
	{
		c.id          = md5("queueClient-" + c.queue + '::' + c.uniqueid);
		c.queueid     = md5("queue-" + c.queue);
		c.callerid    = c.channel;
		
		if (c.calleridname)
			c.callerid = c.calleridname + " &lt;" + c.calleridnum + "&gt;";
		
		var div       = document.createElement('div');
		div.id        = c.id;
		div.className = 'queueClientsDiv';
		div.innerHTML = new Template($("Template::Queue::Client").innerHTML).evaluate(c);
		div.oncontextmenu = function () { return false; };
		div.onmouseup     = function (event)
		{
			var e = event ? event : window.event;
			if (e.button == 2)
				Monast.showQueueClientContextMenu(c.queueid, c.id);
		};
		$('queueClients-' + c.queueid).appendChild(div);
		this.queues.get(c.queueid).clients.set(c.id, c);
		$('queueClientsCount-' + c.queueid).innerHTML = this.queues.get(c.queueid).clients.keys().length;
	},
	removeQueueClient: function (c)
	{
		var id       = md5("queueClient-" + c.queue + '::' + c.uniqueid);
		var queueid  = md5("queue-" + c.queue);
		var client   = this.queues.get(queueid).clients.unset(id);
		if (!Object.isUndefined(client))
		{
			$('queueClients-' + client.queueid).removeChild($(client.id));
		}
		$('queueClientsCount-' + client.queueid).innerHTML = this.queues.get(client.queueid).clients.keys().length;
	},
	showQueueClientContextMenu: function (queueid, id)
	{
		this._contextMenu.clearContent();
		this._contextMenu.cfg.queueProperty("xy", this.getMousePosition(event));
	
		var viewClientInfo = function (p_sType, p_aArgs, p_oValue)
		{
			p_oValue.pausedtext = p_oValue.paused == "1" ? "True" : "False";
			p_oValue.waittime   = new Date(p_oValue.jointime * 1000).toLocaleString();
			Monast.doAlert(new Template($("Template::Queue::Client::Info").innerHTML).evaluate(p_oValue));
		};
		
		var qc = this.queues.get(queueid).clients.get(id);
		var c = [
			[
				{text: "Drop Client"},
				{text: "View Client Info", onclick: {fn: viewClientInfo, obj: qc}}
			]
		];
		this._contextMenu.addItems(c);
		this._contextMenu.setItemGroupTitle("Queue Client:  " + qc.callerid, 0);
		this._contextMenu.render(document.body);
		this._contextMenu.show();
	},

	// Process Events
	processEvent: function (event)
	{
		if (!Object.isUndefined(event.objecttype))
		{
			switch (event.objecttype)
			{
				case "User/Peer":
					this.processUserpeer(event);
					break;
					
				case "Channel":
					this.processChannel(event);
					break;
					
				case "Bridge":
					this.processBridge(event);
					break;
					
				case "Meetme":
					this.processMeetme(event);
					break;
					
				case "Queue":
					this.processQueue(event);
					break;
					
				case "QueueMember":
					this.processQueueMember(event);
					break;
					
				case "QueueClient":
					this.processQueueClient(event);
					break;
			}
		}
		
		if (!Object.isUndefined(event.action))
		{
			switch (event.action)
			{
				case "Error":
					this._statusError = true;
					this.doError(event.message);
					return;
					
				case "Reload":
					this._statusReload = true;
					setTimeout("location.href = 'index.php'", event.time);
					return;
					
				case "RemoveChannel":
					this.removeChannel(event);
					break;
					
				case "RemoveBridge":
					this.removeBridge(event);
					break;
					
				case "RemoveMeetme":
					this.removeMeetme(event);
					break;
					
				case "RemoveQueueMember":
					this.removeQueueMember(event);
					break;
					
				case "RemoveQueueClient":
					this.removeQueueClient(event);
					break;
			}
		}
	},
	
	// Request Status via AJAX
	_statusError: false,
	_statusReload: false,
	requestStatus: function ()
	{
		if (this._statusError)
		{
			$('_reqStatus').innerHTML = "<font color='red'>Reload needed, Press F5.</font>";
			return;
		}
		if (this._statusReload)
		{
			$('_reqStatus').innerHTML = "Reloading, please wait.";
			return;
		}
			
		new Ajax.Request('status.php', 
		{
			method: 'get',
			parameters: {
				reqTime: new Date().getTime()
			},
			
			onCreate:        function() { $('_reqStatus').innerHTML = 'Create'; },
			onUninitialized: function() { $('_reqStatus').innerHTML = 'Uninitialized'; },
			onLoading:       function() { $('_reqStatus').innerHTML = 'On Line'; },
			onLoaded:        function() { $('_reqStatus').innerHTML = 'Loaded'; },
			onInteractive:   function() { $('_reqStatus').innerHTML = 'Interactive'; },
			onComplete:      function() { $('_reqStatus').innerHTML = 'Complete'; Monast.requestStatus(); },
			
			onSuccess: function(transport)
			{
				var events = transport.responseJSON;
				events.each(function (event) 
				{
					try
					{
						Monast.processEvent(event);
					}
					catch (e)
					{
						console.log(e, event);
					}
				});
			},
			onFailure: function()
			{
				this._statusError = true;
				doError('!! MonAst ERROR !!\n\nAn error ocurred while requesting status!\nPlease press F5 to reload MonAst.');
			}
		});
	},
	
	// Alerts & Messages
	doAlert: function (message)
	{
		_alert.setHeader('Information');
		_alert.setBody(message);
		_alert.cfg.setProperty("icon", YAHOO.widget.SimpleDialog.ICON_INFO);
		_alert.render();
		_alert.show();
	},
	doError: function (message)
	{
		_alert.setHeader('Error');
		_alert.setBody(message);
		_alert.cfg.setProperty("icon", YAHOO.widget.SimpleDialog.ICON_BLOCK);
		_alert.render();
		_alert.show();
	},
	doWarn: function (message)
	{
		_alert.setHeader('Warning');
		_alert.setBody(message);
		_alert.cfg.setProperty("icon", YAHOO.widget.SimpleDialog.ICON_WARN);
		_alert.render();
		_alert.show();
	},
	doConfirm: function (message, handleYes, handleNo)
	{
		if (!handleNo)
			handleNo = function () { }
	
		var buttons = [
			{text: "Yes", handler: function () { this.hide(); handleYes(); }},
			{text: "No", handler: function () { this.hide(); handleNo(); }}
		];
		
		_confirm.setBody(message);
		_confirm.cfg.setProperty("icon", YAHOO.widget.SimpleDialog.ICON_HELP);
		_confirm.cfg.setProperty("buttons", buttons); 
		_confirm.render();
		_confirm.show();
	},
	
	// Monast INIT
	init: function ()
	{
		YAHOO.util.DDM.mode = YAHOO.util.DDM.POINT;
		
		// CheckBox Buttons for Mixed Pannels
		window.ocheckBoxTab1 = new YAHOO.widget.Button("checkBoxTab1", { label: "Peers/Users" });
		window.ocheckBoxTab1.addListener('checkedChange', this.showHidePannels);
		window.ocheckBoxTab2 = new YAHOO.widget.Button("checkBoxTab2", { label:"Meetme Rooms" });
		window.ocheckBoxTab2.addListener('checkedChange', this.showHidePannels);
		window.ocheckBoxTab3 = new YAHOO.widget.Button("checkBoxTab3", { label:"Channels/Calls" });
		window.ocheckBoxTab3.addListener('checkedChange', this.showHidePannels);
		window.ocheckBoxTab4 = new YAHOO.widget.Button("checkBoxTab4", { label:"Parked Calls" });
		window.ocheckBoxTab4.addListener('checkedChange', this.showHidePannels);
		window.ocheckBoxTab5 = new YAHOO.widget.Button("checkBoxTab5", { label:"Queues" });
		window.ocheckBoxTab5.addListener('checkedChange', this.showHidePannels);
		
		window._buttons = new Array(ocheckBoxTab1, ocheckBoxTab2, ocheckBoxTab3, ocheckBoxTab4, ocheckBoxTab5);
		
		// Cookie to save View state
		window._state = YAHOO.util.Cookie.get("_state");
		if (!_state)
		{
			_state = {activeIndex: 1, buttons: {'checkBoxTab1': false, 'checkBoxTab2': false, 'checkBoxTab3': false, 'checkBoxTab4': false, 'checkBoxTab5': false}};
			YAHOO.util.Cookie.set('_state', Object.toJSON(_state));
		}
		else
		{
			_state = _state.evalJSON();
		}
		
		// TabPannel and Listeners
		window._tabPannel = new YAHOO.widget.TabView('TabPannel');
		_tabPannel.addListener('beforeActiveTabChange', function(e) {
			var pannels = new Array('peersDiv', 'meetmesDiv', 'chanCallDiv', 'parkedCallsDiv', 'queuesDiv');
			pannels.each(function (pannel) {
				$(pannel).className = 'yui-hidden';
			});
		
			var tabs = this.get('tabs');
			tabs.each(function (tab, i) {
				if (tab.get('label') == e.newValue.get('label'))
				{
					_state.activeIndex = i;
					YAHOO.util.Cookie.set('_state', Object.toJSON(_state));
				}
			});
		});
		_tabPannel.getTab(0).addListener('click', function(e) {
			_buttons.each(function (button) {
				button.set('checked', _state.buttons[button.get('id')]);
			});
		});
		_tabPannel.set('activeIndex', _state.activeIndex);
		if (_state.activeIndex == 0)
		{
			_buttons.each(function (button) {
				button.set('checked', _state.buttons[button.get('id')]);
			});
		}
		
		// Drag&Drop ActionsDIV Targets
		window._dTrash  = new YAHOO.util.DDTarget("trash");
		window._dPark   = new YAHOO.util.DDTarget("park");
		window._dRecord = new YAHOO.util.DDTarget("record");
	},
	
	showHidePannels: function (e)
	{
		$(this.get('value')).className = (e.newValue ? '' : 'yui-hidden');
		_state.buttons[this.get('id')] = e.newValue;
		YAHOO.util.Cookie.set('_state', Object.toJSON(_state));
	},
	
	changeServer: function (server)
	{
		$('_reqStatus').innerHTML = "Changing Server...";
		new Ajax.Request('action.php', 
		{
			method: 'get',
			parameters: {
				reqTime: new Date().getTime(),
				action: Object.toJSON({action: 'ChangeServer', server: server})
			}
		});
	},
	
	// Chrono
	_chrono: new Hash(),
	startChrono: function (id, seconds, hideSeconds)
	{
		if (!MONAST_CALL_TIME)
			return;

		var hideSeconds = Object.isUndefined(hideSeconds) ? false : hideSeconds;
		var chrono      = this._chrono.get(id);
		
		if (Object.isUndefined(chrono))
		{
			if (seconds)
			{
				var d  = new Date(seconds * 1000);
				chrono = {hours: d.getUTCHours(), minutes: d.getUTCMinutes(), seconds: d.getUTCSeconds(), run: null, showSeconds: !hideSeconds};
			}
			else
			{
				chrono = {hours: 0, minutes: 0, seconds: 0, run: null, showSeconds: !hideSeconds};
			}
			this._chrono.set(id, chrono);
		}
		else
		{
			if (Object.isUndefined(seconds))
			{
				chrono.seconds += 1;
			}
			else
			{
				var d = new Date(secs * 1000);
				chrono.seconds = d.getUTCSeconds();
				chrono.minutes = d.getUTCMinutes();
				chrono.hours   = d.getUTCHours();
			}
			
			if (chrono.seconds == 60)
			{
				chrono.seconds  = 0;
				chrono.minutes += 1;
			}
			if (chrono.minutes == 60)
			{
				chrono.minutes = 0;
				chrono.hours  += 1;
			}
		}
		
		var seconds = chrono.seconds < 10 ? '0' + chrono.seconds : chrono.seconds;
		var minutes = chrono.minutes < 10 ? '0' + chrono.minutes : chrono.minutes;
		var hours   = chrono.hours < 10 ? '0' + chrono.hours : chrono.hours;

		var f = $('chrono-' + id);
		if (!Object.isUndefined(f))
			f.innerHTML = hours + ':' + minutes + (chrono.showSeconds ? ':' + seconds : '');		

		chrono.run = setTimeout("Monast.startChrono('" + id + "')", 1000);	
	},
	stopChrono: function (id)
	{
		var chrono = this._chrono.unset(id);
		if (!Object.isUndefined(chrono))
			clearTimeout(chrono.run);
	},
	
	// Extra Utils
	getMousePosition: function (event)
	{
		var e    = event ? event : window.event;
		var posx = 0;
		var posy = 0;
		
		// Mozilla
		if (e.pageX || e.pageY) 
		{
			posx = e.pageX;
			posy = e.pageY
		}
		else if (e.clientX || e.clientY) 
		{
			posx = e.clientX + document.body.scrollLeft + document.documentElement.scrollLeft;
			posy = e.clientY + document.body.scrollTop + document.documentElement.scrollTop;
		}
		return [posx, posy];
	}
};
