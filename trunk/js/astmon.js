
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
*     * Neither the name of the <ORGANIZATION> nor the names of its contributors
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

var json      = new JSON();
var ddDivs    = new Array();
var callerIDs = new Array();

String.prototype.trim = function() { return this.replace(/^\s*/, "").replace(/\s*$/, ""); }
//function $(id) { return document.getElementById(id); }

function color(t)
{
	t = t.toLowerCase();
	switch (t)
	{
		case 'down':
        case 'unregistered':
        case 'unreachable':
        case 'unknown':
        	//return 'red';
            return '#ffb0b0';
            
        case 'ring':
        case 'ringing':
        case 'dial':
        case 'lagged':
            //return 'yellow';
            return '#ffffb0';
            
        case 'up':
        case 'link':
        case 'registered':
        case 'reachable':
        case 'unmonitored':
            //return 'green';
            return '#b0ffb0';
    }
    return '#dddddd';
}

function blink(id, cor)
{
	t = 0;
	for (i = 0; i < 5; i++)
	{
		t += 200;
		setTimeout("$('" + id + "').style.backgroundColor = '#ffffff'", t);
		t += 200;
		setTimeout("$('" + id + "').style.backgroundColor = '" + cor + "'", t);
	}
}

var _statusError  = false;
var _statusReload = false; 
function getStatus()
{
	if (_statusError)
	{
		$('_reqStatus').innerHTML = "<font color='red'>Reload needed, Press F5.</font>";
		return;
	}
	if (_statusReload)
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
		onComplete:      function() { $('_reqStatus').innerHTML = 'Complete'; getStatus(); },
		
		onSuccess: function(transport)
		{
			var events = json.decode(transport.responseText);
			for (i = 0; i < events.length; i++)
			{
				Process(json.encode(events[i]));
			}
		},
		onFailure: function()
		{
			_statusError = true;
			alert('getStatus() ERROR');
		}
	});
}

var _countMembers   = 0;
var _countClients   = 0;
var _countCompleted = 0;
var _countAbandoned = 0

function Process(o)
{
	if ($('debugMsg'))
		$('debugMsg').innerHTML += o + "<br>\r\n";
		
	o = json.decode(o);
	
	if (o['Action'] == 'Error')
	{
		_statusError = true;
		alert(o['Message']);
	}
	
	if (o['Action'] == 'Reload')
	{
		_statusReload = true;
		setTimeout("location.href = 'index.php'", o['time']);
		return;
	}
	
	if (o['Action'] == 'CliResponse')
	{
		$('cliResponse').value += '\r\n' + unescape(decodeURI(o['Response'])).replace(/\<br\>/g, '\r\n');
		$('cliResponse').scrollTop = $('cliResponse').scrollHeight - $('cliResponse').offsetHeight + 10;
		return; 
	}
	
	if (o['Action'] == 'PeerStatus')
	{
		var td = $('peerStatus-' + o['Peer']);
		if (td.innerHTML != o['Status'])
		{
			td.style.backgroundColor = color(o['Status']);
			td.innerHTML             = o['Status'];
		}
		
		var td = $('peerCalls-' + o['Peer']);
		if (td.innerHTML != (o['Calls'] + ' call(s)'))
		{
			td.style.backgroundColor = (o['Calls'] > 0 ? '#ffffb0' : '#b0ffb0');
			td.innerHTML             = o['Calls'] + ' call(s)';
		}
		
		return;
	}
	
	if (o['Action'] == 'NewChannel')
	{
		var div = $(o['Uniqueid']);
		if (!div)
		{
			div           = document.createElement('div');
			div.id        = o['Uniqueid'];
			div.className = 'channelDiv';
			 
			var template = "<table width='350'><tr>";
			template    += "<td id='channel-{Uniqueid}' class='status' width='270'>{Channel}</td>";
			template    += "<td id='channelStatus-{Uniqueid}' bgcolor='{color}' class='status' width='80'>{State}</td>";
			template    += "</tr></table>";
			template     = template.replace(/\{Uniqueid\}/g, o['Uniqueid']);
			template     = template.replace(/\{Channel\}/g, o['Channel']);
			template     = template.replace(/\{State\}/g, o['State']);
			template     = template.replace(/\{color\}/g, color(o['State']));
			
			div.innerHTML = template;
			
			$('channelsDiv').appendChild(div);
			
			ddDivs[o['Uniqueid']]               = new YAHOO.util.DD(o['Uniqueid']);
			ddDivs[o['Uniqueid']].onMouseDown   = setStartPosition;
			ddDivs[o['Uniqueid']].onDragDrop    = channelCallDrop;
			ddDivs[o['Uniqueid']].onInvalidDrop = invalidDrop;
			ddDivs[o['Uniqueid']].onDragOver    = dragOver;
			ddDivs[o['Uniqueid']].onDragOut     = dragOut;
		}
		
		return;
	}
	
	if (o['Action'] == 'Call')
	{
		var template = "<table width='600'><tr>";
		template    += "<td class='status' width='260' id='callChannel-{SrcUniqueID}'>{Source}</td>";
		template    += "<td class='status' width='80' bgcolor='{color}' id='callStatus-{SrcUniqueID}-{DestUniqueID}'>{Status}<br><span style='font-family: monospace;' id='chrono-callStatus-{SrcUniqueID}-{DestUniqueID}'></span></td>";
		template    += "<td class='status' width='260' id='callChannel-{DestUniqueID}'>{Destination}</td>";
		template    += "</tr></table>";
		
		template = template.replace(/\{SrcUniqueID\}/g, o['SrcUniqueID']);
		template = template.replace(/\{DestUniqueID\}/g, o['DestUniqueID']);
		template = template.replace(/\{Source\}/g, o['Source'] + '<br>' + o['CallerIDName'] + ' <' + o['CallerID'] + '>');
		template = template.replace(/\{Destination\}/g, o['Destination'] + (o['CallerID2'] ? '<br> <' + o['CallerID2'] + '>' : ''));
		template = template.replace(/\{Status\}/g, o['Status']);
		template = template.replace(/\{color\}/g, color(o['Status']));
		
		var div       = document.createElement('div');
		div.id        = 'call-' + o['SrcUniqueID'] + '-' + o['DestUniqueID'];
		div.className = 'callDiv'; 
		div.innerHTML = template;
		
		$('callsDiv').appendChild(div);
		if (o['Status'] == 'Link')
			chrono('callStatus-' + o['SrcUniqueID'] + '-' + o['DestUniqueID'], o['Seconds']);
		
		ddDivs[div.id]               = new YAHOO.util.DD(div.id);
		ddDivs[div.id].onMouseDown   = setStartPosition;
		ddDivs[div.id].onDragDrop    = channelCallDrop;
		ddDivs[div.id].onInvalidDrop = invalidDrop;
		ddDivs[div.id].onDragOver    = dragOver;
		ddDivs[div.id].onDragOut     = dragOut;

		return;
	}
	
	if (o['Action'] == 'Hangup')
	{
		var div = $(o['Uniqueid']);
		if (div)
			$('channelsDiv').removeChild(div);
		
		return;
	}
	
	if (o['Action'] == 'NewState')
	{
		var td = $('channelStatus-' + o['Uniqueid']);
		if (td)
		{
			td.innerHTML             = o['State'];
			td.style.backgroundColor = color(o['State']);
		}
		return; 
	}
	
	if (o['Action'] == 'Dial')
	{
		var div = $('call-' + o['SrcUniqueID'] + '-' + o['DestUniqueID']);
		if (!div)
		{
			o['Action'] = 'Call';
			o['Status'] = 'Dial';
			Process(json.encode(o));
		}
		return;
	}
	
	if (o['Action'] == 'Link')
	{
		td = $('callStatus-' + o['Uniqueid1'] + '-' + o['Uniqueid2']);
		if (td)
		{
			td.style.backgroundColor = color('Link');
			td.innerHTML = 'Link<br><span style="font-family: monospace;" id="chrono-' + td.id + '"></span>';
			chrono(td.id, o['Seconds']);
		}
		else
		{
			o['Action']       = 'Call';
			o['Status']       = 'Link';
			o['Source']       = o['Channel1'];
			o['Destination']  = o['Channel2'];
			o['SrcUniqueID']  = o['Uniqueid1'];
			o['DestUniqueID'] = o['Uniqueid2'];
			o['CallerIDName'] = '';
			o['CallerID']     = o['CallerID1'];
			Process(json.encode(o));
		}
		
		return;
	}
	
	if (o['Action'] == 'Unlink')
	{
		stopChrono('callStatus-' + o['Uniqueid1'] + '-' + o['Uniqueid2']);
		$('callsDiv').removeChild($('call-' + o['Uniqueid1'] + '-' + o['Uniqueid2']));
		return;
	}
	
	if (o['Action'] == 'NewCallerid')
	{
		td = $('callChannel-' + o['Uniqueid']);
		if (td)
			td.innerHTML = o['Channel'] + '<br>' + o['CallerIDName'] + ' <' + o['CallerID'] + '>';
		
		return;
	}
	
	if (o['Action'] == 'Rename')
	{
		td = $('channel-' + o['Uniqueid']);
		if (td)
			td.innerHTML = o['Newname'];
			
		td = $('callChannel-' + o['Uniqueid']);
		if (td)
			td.innerHTML = o['Newname'] + '<br>' + o['CallerIDName'] + ' <' + o['CallerID'] + '>';
			
		return;
	}
	
	if (o['Action'] == 'MeetmeJoin')
	{
		var id  = 'meetme-' + o['Meetme'] + '-' + o['Usernum'];
		var div = $(id);
		if (!div)
		{
			div           = document.createElement('div');
			div.id        = id;
			div.className = 'meetmeDiv';
			
			var UserInfo = o['CallerIDName'] + ' <' + o['CallerIDNum'] + '>';		
			if (o['CallerIDName'] == 'None' && o['CallerIDNum'] == 'None')
				UserInfo = o['Channel'];
			 
			var template = "<table width='250'><tr>";
			template    += "<td class='status'>{UserInfo}</td>";
			template    += "</tr></table>";
			template     = template.replace(/\{UserInfo\}/g, UserInfo);
			
			div.innerHTML = template;
			
			$('meetme-' + o['Meetme']).appendChild(div);
			
			ddDivs[id]               = new YAHOO.util.DD(id);
			ddDivs[id].onMouseDown   = setStartPosition;
			ddDivs[id].onDragDrop    = meetmeDrop;
			ddDivs[id].onInvalidDrop = invalidDrop;
			ddDivs[id].onDragOver    = dragOver;
			ddDivs[id].onDragOut     = dragOut;
		}
		
		return;
	}
	
	if (o['Action'] == 'MeetmeLeave')
	{
		var id  = 'meetme-' + o['Meetme'] + '-' + o['Usernum'];
		var div = $(id);
		if (div)
			$('meetme-' + o['Meetme']).removeChild(div);
			
		return;
	}
	
	if (o['Action'] == 'ParkedCall')
	{
		var id  = 'parked-' + o['Exten'];
		var div = $(id);
		if (!div)
		{
			div           = document.createElement('div');
			div.id        = id;
			div.className = 'parkedDiv';
			
			var user = o['From'];
			if (o['From'].lastIndexOf('-') != -1)
				user = o['From'].substring(0, o['From'].lastIndexOf('-'));
			
			var template = "<table width='600'><tr>";
			template    += "<td class='status' align='center' width='80'>{Exten}</td>";
			template    += "<td class='status' align='center' width='260'>{From}<br>{CallerIDFrom}</td>";
			template    += "<td class='status' align='center' width='260'>{Channel}<br>{CallerIDName} <{CallerID}></td>";
			template    += "</tr></table>";
			template     = template.replace(/\{Exten\}/g, o['Exten']);
			template     = template.replace(/\{From\}/g, o['From']);
			template     = template.replace(/\{CallerIDFrom\}/g, callerIDs[user]);
			template     = template.replace(/\{CallerIDName\}/g, o['CallerIDName']);
			template     = template.replace(/\{CallerID\}/g, o['CallerID']);
			template     = template.replace(/\{Channel\}/g, o['Channel']);
			
			div.innerHTML = template;
			
			$('parkedsDiv').appendChild(div);
			
			ddDivs[id]               = new YAHOO.util.DD(id);
			ddDivs[id].onMouseDown   = setStartPosition;
			ddDivs[id].onDragDrop    = parkedCallDrop;
			ddDivs[id].onInvalidDrop = invalidDrop;
			ddDivs[id].onDragOver    = dragOver;
			ddDivs[id].onDragOut     = dragOut;
		}
		
		return;
	}
	
	if (o['Action'] == 'UnparkedCall')
	{
		var id  = 'parked-' + o['Exten'];
		var div = $(id);
		if (div)
			$('parkedsDiv').removeChild(div);
			
		return;
	}
	
	if (o['Action'] == 'AddQueueMember')
	{
		var id  = 'queueMember-' + o['Queue'] + '-' + o['Member'];
		var div = $(id);
		if (!div)
		{
			div           = document.createElement('div');
			div.id        = id;
			div.className = 'queueMembersDiv';
			
			var template = "<table width='250'><tr>";
			template    += "<td class='status' align='center'>{MemberName}</td>";
			template    += "</tr></table>";
			template     = template.replace(/\{MemberName\}/g, o['MemberName']);
			
			div.innerHTML = template;
			
			$('queueMembers-' + o['Queue']).appendChild(div);
			
			_countMembers += 1;
		}
		
		$('queueMembersCount-' + o['Queue']).innerHTML = _countMembers;
		 
		return;
	}
	
	if (o['Action'] == 'RemoveQueueMember')
	{
		var id  = 'queueMember-' + o['Queue'] + '-' + o['Member'];
		var div = $(id);
		if (div)
		{
			$('queueMembers-' + o['Queue']).removeChild(div);
			_countMembers -= 1;
		}
		
		$('queueMembersCount-' + o['Queue']).innerHTML = _countMembers;
		
		return;
	}
	
	if (o['Action'] == 'AddQueueClient')
	{
		var id  = 'queueClient-' + o['Queue'] + '-' + o['Uniqueid'];
		var div = $(id);
		if (!div)
		{
			div           = document.createElement('div');
			div.id        = id;
			div.className = 'queueClientsDiv';
			
			UserInfo = o['Channel'];
			if (o['CallerID'])
				UserInfo = o['CallerIDName'] + ' <' + o['CallerID'] + '>'; 
			
			var template = "<table width='250'><tr>";
			template    += "<td class='status' align='center'>{UserInfo}</td>";
			template    += "</tr></table>";
			template     = template.replace(/\{UserInfo\}/g, UserInfo);
			
			div.innerHTML = template;
			
			$('queueClients-' + o['Queue']).appendChild(div);
		}
		
		$('queueClientsCount-' + o['Queue']).innerHTML = o['Count'];
		$('queueStatsCalls-' + o['Queue']).innerHTML = o['Count'];
		 
		return;
	}
	
	if (o['Action'] == 'RemoveQueueClient')
	{
		var id  = 'queueClient-' + o['Queue'] + '-' + o['Uniqueid'];
		var div = $(id);
		if (div)
			$('queueClients-' + o['Queue']).removeChild(div);
		
		$('queueClientsCount-' + o['Queue']).innerHTML = o['Count'];
		$('queueStatsCalls-' + o['Queue']).innerHTML = o['Count'];
		
		if (o['Cause'] == 'Completed')
		{
			_countCompleted += 1;
			$('queueStatsCompleted-' + o['Queue']).innerHTML = _countCompleted;
		}
		else if (o['Cause'] == 'Abandoned')
		{
			_countAbandoned += 1;
			$('queueStatsAbandoned-' + o['Queue']).innerHTML = _countAbandoned;
		}
		
		return;
	}
	
	if (o['Action'] == 'QueueParams')
	{
		_countCompleted = o['Completed'];
		_countAbandoned = o['Abandoned'];
		
		$('queueStatsMax-' + o['Queue']).innerHTML              = o['Max'];
		$('queueStatsCalls-' + o['Queue']).innerHTML            = o['Calls'];
		$('queueStatsHoldtime-' + o['Queue']).innerHTML         = o['Holdtime'];
		$('queueStatsCompleted-' + o['Queue']).innerHTML        = o['Completed'];
		$('queueStatsAbandoned-' + o['Queue']).innerHTML        = o['Abandoned'];
		$('queueStatsServiceLevel-' + o['Queue']).innerHTML     = o['ServiceLevel'];
		$('queueStatsServicelevelPerf-' + o['Queue']).innerHTML = o['ServicelevelPerf'];
		$('queueStatsWeight-' + o['Queue']).innerHTML           = o['Weight'];
		
		return;
	}
}

function showHidePannels(e)
{
	$(this.get('value')).style.display = (e.newValue ? 'block' : 'none');
	_state.buttons[this.get('id')] = e.newValue;
	YAHOO.util.Cookie.set('_state', json.encode(_state));
}

// Originate a Call
function originateCall(peer, number, type)
{
	if (!number)
	{
		alert('Destination number not defined!');
		return false;
	}
	
	var ret = function(msg)
	{
		if (msg == 'OK'){
			$('originateNumber').value = '';
			originateDialog.hide();
		}
	}
	
	new Ajax.Request('action.php', 
	{
		method: 'get',
		parameters: {
			reqTime: new Date().getTime(),
			action: 'OriginateCall:::' + peer + ':::' + number + ':::' + type
		},
		onSuccess: function(transport)
		{
			if (transport.responseText == 'OK') 
			{
				$('originateNumber').value = '';
				originateDialog.hide();
			}
		}
	});
}

function originateDial(src, dst, type)
{
	new Ajax.Request('action.php', 
	{
		method: 'get',
		parameters: {
			reqTime: new Date().getTime(),
			action: 'OriginateDial:::' + src + ':::' + dst + ':::' + type
		}
	});
}

//Hangup Call
function hangupCall(chanId)
{
	var msg = "Hangup this Channel?";
	if (chanId.indexOf('call') != -1)
	{
		msg = "Hangup this Call?";
		chanId = chanId.substring(5, chanId.lastIndexOf('-'));
	}
		
	var c = confirm(msg);
	if (c)
	{
		new Ajax.Request('action.php', 
		{
			method: 'get',
			parameters: {
				reqTime: new Date().getTime(),
				action: 'HangupChannel:::' + chanId
			}
		});
	}
}

// Transfer
function transferCall(src, dst, type)
{
	var comp = '';
	var dest = '';
	if (type == 'meetme')
	{
		comp = 'meetme ';
		dest = dst;
	}
	else if (type == 'park')
	{
		dest = 'Park';
	}
	else
	{
		dest = callerIDs[dst];
	}
	
	var c = confirm("Transfer call to " + comp + dest + '?');
	if (!c)
		return;

	new Ajax.Request('action.php', 
	{
		method: 'get',
		parameters: {
			reqTime: new Date().getTime(),
			action: 'TransferCall:::' + src + ':::' + dst + ':::' + type
		}
	});
}

// Park
function parkCall(park, announce)
{
	new Ajax.Request('action.php', 
	{
		method: 'get',
		parameters: {
			reqTime: new Date().getTime(),
			action: 'ParkCall:::' + park + ':::' + announce
		}
	});
}

// Meetme kick
function meetmeKick(meetme, usernum)
{
	var c = confirm('Kick this user from meetme ' + meetme + '?');
	if (c)
	{
		new Ajax.Request('action.php', 
		{
			method: 'get',
			parameters: {
				reqTime: new Date().getTime(),
				action: 'MeetmeKick:::' + meetme + ':::' + usernum
			}
		});
	}
}

// Parked Hangup()
function parkedHangup(exten)
{
	var c = confirm('Hangup parked call on exten ' + exten + '?');
	if (c)
	{
		new Ajax.Request('action.php', 
		{
			method: 'get',
			parameters: {
				reqTime: new Date().getTime(),
				action: 'ParkedHangup:::' + exten
			}
		});
	}
}

// Yahoo
function setStartPosition(e)
{
	var el          = $(this.id);
	this.startPos   = YAHOO.util.Dom.getXY(YAHOO.util.Dom.get(this.id));
	this.origZindex = el.getStyle('z-index');
	el.setStyle({'z-index': 10});
}
function backToStartPosition(id)
{
	new YAHOO.util.Motion(  
		id, {  
			points: {
				to: ddDivs[id].startPos
			}
		},
		0.3,
		YAHOO.util.Easing.easeOut
	).animate();
	if (ddDivs[id].origZindex)
		$(id).setStyle({zIndex: ddDivs[id].origZindex});
	if (ddDivs[id].lastOver)
		$(ddDivs[id].lastOver).setStyle({opacity: 1});
}
function dragOver(e, id)
{
	$(id).setStyle({opacity: 0.5});
	this.lastOver = id;
}
function dragOut(e, id)
{
	$(id).setStyle({opacity: 1});
}

function peerDrop(e, id) 
{
	if (id.indexOf('peerDiv-') != -1)
	{
		var src = this.id.replace('peerDiv-', '');
		var dst = id.replace('peerDiv-', '');
		var c   = confirm('Originate a call from "' + callerIDs[src] + '" to "' + callerIDs[dst] + '"?');
		
		if (c)
			originateDial(src, dst, 'default');
	}
	if (id.indexOf('meetme-') != -1)
	{
		var src = this.id.replace('peerDiv-', '');
		var dst = id.replace('meetme-', '');
		var c   = confirm('Invite "' + callerIDs[src] + '" to meetme ' + dst + '?');
		if (c)
			originateCall(src, dst, 'meetme');
	}
	
	backToStartPosition(this.id);
}

function channelCallDrop(e, id)
{
	if (id == 'trash')
		hangupCall(this.id);
		
	if (id.indexOf('peerDiv-') != -1 && this.id.indexOf('call-') == -1)
		transferCall(this.id, id.substring(8), 'peer');
		
	if (id.indexOf('peerDiv-') != -1 && this.id.indexOf('call-') != -1)
	{
		var ids  = this.id.substring(5).split('-');
		var srcA = $('channel-' + ids[0]).innerHTML;
		var srcB = $('channel-' + ids[1]).innerHTML;
		showTransferDialog(ids[0], srcA, ids[1], srcB, id.substring(8));
	}
	
	if (id.indexOf('meetme-') != -1)
	{
		if (this.id.indexOf('call-') == -1)
			transferCall(this.id, id.replace('meetme-', ''), 'meetme');
		else
			transferCall(this.id.replace('call-', ''), id.replace('meetme-', ''), 'meetme');
	}
	
	if (this.id.indexOf('call-') != -1 && id == 'park')
	{
		var ids  = this.id.substring(5).split('-');
		var srcA = $('channel-' + ids[0]).innerHTML;
		var srcB = $('channel-' + ids[1]).innerHTML;
		showTransferDialog(ids[0], srcA, ids[1], srcB, 'ParkedCalls');
	}
	
	backToStartPosition(this.id);
}

function meetmeDrop(e, id)
{
	if (id == 'trash')
	{
		var info = this.id.replace('meetme-', '').split('-')
		meetmeKick(info[0], info[1]);
	}
		
	backToStartPosition(this.id);
}

function parkedCallDrop(e, id)
{
	var parked = this.id.replace('parked-', '');
	if (id == 'trash')
		parkedHangup(parked);
	
	if (id.indexOf('peerDiv-') != -1)
	{
		var source = id.replace('peerDiv-', '');
		var c = confirm('Transfer Parked Call on exten ' + parked + ' to ' + callerIDs[source] + '?');
		if (c)
			originateCall(source, parked, 'default');
	}
	
	backToStartPosition(this.id);
}

function invalidDrop(e)
{
	backToStartPosition(this.id);
}

// Originate Dialog
var handleOriginateCancel = function(){
	$('originateNumber').value = '';
	this.hide();
}
var handleOriginate = function(){
	originateCall(this.peerId, $('originateNumber').value, 'default');
}

function showOriginateDialog(p_sType, p_aArgs, peerId)
{
	originateDialog.peerId = peerId;
	originateDialog.cfg.queueProperty("xy", ddDivs['peerDiv-' + peerId].startPos);  
	originateDialog.render();
	originateDialog.show();
}

// Peer Options MENU
var _POMENU = new Array();
function showPeerOptionsMenu(id)
{
	if (!_POMENU[id])
	{
		_POMENU[id] = new YAHOO.widget.Menu("peerOptionsMenu-" + id, { xy: ddDivs['peerDiv-' + id].startPos });
		_POMENU[id].addItems([
			{text: 'Originate Call', onclick: {fn: showOriginateDialog, obj: id}}
		]);
		_POMENU[id].setItemGroupTitle('Options for "' + callerIDs[id] + '"', 0);
		_POMENU[id].render("peerDiv-" + id);
	}
	_POMENU[id].show(); 
}

// Transfer Dialog
var handleTransferCancel = function(){
	this.hide();
}
var handleTransfer = function(){
	var src = null;
	if ($('transferSourceValueA').checked)
		src = $('transferSourceValueA').value;
	else
		src = $('transferSourceValueB').value;
	
	var type = 'peer';
	if (this.destChannel == 'ParkedCalls')
	{
		type = 'park'
		this.destChannel = $('transferSourceValueA').value
		if (src == $('transferSourceValueA').value)
			this.destChannel = $('transferSourceValueB').value
			
		parkCall(src, this.destChannel);
		this.hide();
		return;
	}
	
	transferCall(src, this.destChannel, type);
	this.hide();
}

function showTransferDialog(idA, srcA, idB, srcB, dst)
{
	if (dst == 'ParkedCalls')
	{
		$('transferDestination').innerHTML = 'Park';
	}
	else
		$('transferDestination').innerHTML = 'transfer to "' + callerIDs[dst] + '"';
		
	$('transferSourceValueA').value    = idA;
	$('transferSourceValueB').value    = idB;
	$('transferSourceValueA').checked  = true;
	$('transferSourceTextA').innerHTML = srcA; 
	$('transferSourceTextB').innerHTML = srcB;
	transferDialog.destChannel         = dst;
	transferDialog.render();
	transferDialog.show();
}

// Chrono for calls linked
var _chrono = new Array();
function chrono(id, secs)
{
	if (!MONAST_CALL_TIME)
		return;

	if (_chrono[id])
	{
		if (secs && secs > 0)
		{
			var d = new Date(secs * 1000);
			_chrono[id].secs  = d.getUTCSeconds();
			_chrono[id].mins  = d.getUTCMinutes();
			_chrono[id].hours = d.getUTCHours();
		}
		else
			_chrono[id].secs += 1;
			
		if (_chrono[id].secs == 60)
		{
			_chrono[id].secs  = 0;
			_chrono[id].mins += 1;
		}
		if (_chrono[id].mins == 60)
		{
			_chrono[id].mins   = 0;
			_chrono[id].hours += 1;
		}
	}
	else
	{
		if (secs)
		{
			var d = new Date(secs * 1000);
			_chrono[id] = {hours: d.getUTCHours(), mins: d.getUTCMinutes(), secs: d.getUTCSeconds(), run: null};
		}
		else
			_chrono[id] = {hours: 0, mins: 0, secs: 0, run: null};
	}
	
	var secs  = (_chrono[id].secs < 10 ? '0' + _chrono[id].secs : _chrono[id].secs);
	var mins  = (_chrono[id].mins < 10 ? '0' + _chrono[id].mins : _chrono[id].mins);
	var hours = (_chrono[id].hours < 10 ? '0' + _chrono[id].hours : _chrono[id].hours);
		
	$('chrono-' + id).innerHTML = hours + ':' + mins + ':' + secs;
		
	_chrono[id].run = setTimeout('chrono("' + id + '")', 1000);
}
function stopChrono(id)
{
	if (_chrono[id])
		clearTimeout(_chrono[id].run);
}

function sendCliCommandOnEnter(e)
{
	if (e.keyCode == 13 && $('cliCommand').value.trim()) //Enter
		sendCliCommand();
		
	return true;
}
function sendCliCommand()
{		
	var command = $('cliCommand').value;
	$('cliCommand').value = '';
	
	$('cliResponse').value += '\r\n> ' + command;
	$('cliResponse').scrollTop = $('cliResponse').scrollHeight - $('cliResponse').offsetHeight + 10;
	
	new Ajax.Request('action.php', 
	{
		method: 'get',
		parameters: {
			reqTime: new Date().getTime(),
			action: 'CliCommand:::' + command
		}
	});
}
