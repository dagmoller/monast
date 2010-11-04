
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
			var div       = document.createElement('div');
			div.id        = u.id;
			div.className = 'peerTable';
			div.innerHTML = new Template($('Template::Userpeer').innerHTML).evaluate(u);
			$('fieldset-' + u.channeltype).appendChild(div);
		}
		else
		{
			$(u.id).innerHTML = new Template($('Template::Userpeer').innerHTML).evaluate(u);
		}
		this.userspeers.set(u.id, u);
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
			var div       = document.createElement('div');
			div.id        = c.id;
			div.className = 'channelDiv';
			div.innerHTML = new Template($('Template::Channel').innerHTML).evaluate(c);
			$('channelsDiv').appendChild(div);
		}
		else
		{
			$(c.id).innerHTML = new Template($('Template::Channel').innerHTML).evaluate(c);
		}
		this.channels.set(c.id, c); 
	},
	removeChannel: function (c)
	{
		var channel = this.channels.unset(c.uniqueid);
		if (!Object.isUndefined(channel))
			$('channelsDiv').removeChild($(channel.id));
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
					setTimeout("location.href = 'index.php'", o.time);
					return;
					
				case "RemoveChannel":
					this.removeChannel(event);
					break;
					
				case "RemoveBridge":
					this.removeBridge(event);
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
		
		// EventListener to move ActionsDIV
		var _onScroll = function ()
		{
			$('actionsDiv').style.top = (document.documentElement.scrollTop + 10) + 'px';
		};
		if (window.addEventListener)
			window.addEventListener('scroll', _onScroll, false);
		else
			window.onscroll = _onScroll;
	},
	
	showHidePannels: function (e)
	{
		$(this.get('value')).className = (e.newValue ? '' : 'yui-hidden');
		_state.buttons[this.get('id')] = e.newValue;
		YAHOO.util.Cookie.set('_state', Object.toJSON(_state));
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
	}
};
