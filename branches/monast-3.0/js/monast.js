
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

var ddDivs        = new Array();
var callerIDs     = new Array();
var pausedMembers = new Array();
var toolTips      = {};

String.prototype.trim = function() { return this.replace(/^\s*/, "").replace(/\s*$/, ""); }
//function $(id) { return document.getElementById(id); }

function color(t)
{
	t = t.toLowerCase().trim();
	switch (t)
	{
		case 'down':
        case 'unregistered':
        case 'unreachable':
        case 'unknown':
        case 'unavailable':
        case 'invalid':
        case 'busy':
        case 'logged out':
        	//return 'red';
            return '#ffb0b0';
            
        case 'ring':
        case 'ringing':
        case 'ring, in use':
        case 'in use':
        case 'dial':
        case 'lagged':
        case 'on hold':
            //return 'yellow';
            return '#ffffb0';
            
        case 'up':
        case 'link':
        case 'registered':
        case 'reachable':
        case 'unmonitored':
        case 'not in use':
        case 'logged in':
        case 'no alarm':
            //return 'green';
            return '#b0ffb0';
    }
    
    if (t.indexOf('signal') != -1)
    {
    	var level = t.replace('%', '').replace('signal: ', '');
    	if (level >= 70)
    		return '#b0ffb0';
    	if (level >= 40 && level < 70)
    		return '#ffffb0';
    	if (level < 40)
    		return '#ffb0b0';
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

function changeServer(server)
{
	$('_reqStatus').innerHTML = "Changing Server...";
	new Ajax.Request('action.php', 
	{
		method: 'get',
		parameters: {
			reqTime: new Date().getTime(),
			action: Object.toJSON({Action: 'ChangeServer', Server: server})
		}
	});
}

function getCallerId(peer)
{
	if (callerIDs[peer])
		return callerIDs[peer].replace('&lt;', '<').replace('&gt;', '>');
	return '';
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
			var events = transport.responseJSON;
			for (i = 0; i < events.length; i++)
			{
				try {
					Process(events[i]);
				} catch (e) {
					console.log(e, events[i]);
				}
			}
		},
		onFailure: function()
		{
			_statusError = true;
			doError('!! MonAst ERROR !!\n\nAn error ocurred while requesting status!\nPlease press F5 to reload MonAst.');
		}
	});
}

function Process(o)
{
	if ($('debugMsg'))
		$('debugMsg').innerHTML += Object.toJSON(o) + "<br>\r\n";
	
	//
	// Monast NOVO
	//
	if (!Object.isUndefined(o['objecttype']))
	{
		switch (o['objecttype'])
		{
			// Users/Peers
			case "User/Peer":
				var td                   = $('peerStatus-' + o['channel']);
				td.style.backgroundColor = color(o['status']);
				td.innerHTML             = o['status'];
				td.title                 = "Latency: " + o['time'] + " ms";
				
				td                       = $('peerCalls-' + o['channel']);
				td.style.backgroundColor = (o['calls'] > 0 ? '#ffffb0' : '#b0ffb0');
				td.innerHTML             = o['calls'] + ' call(s)';
				
				break;
			
			// Channels
			case "Channel":
				var div = $(o['uniqueid']);
				if (!div)
				{
					div             = document.createElement('div');
					div.id          = o['uniqueid'];
					div.className   = 'channelDiv';
					
					$('channelsDiv').appendChild(div);
				
					ddDivs[o['uniqueid']]               = new YAHOO.util.DD(o['uniqueid']);
					ddDivs[o['uniqueid']].onMouseDown   = setStartPosition;
					ddDivs[o['uniqueid']].onDragDrop    = channelCallDrop;
					ddDivs[o['uniqueid']].onInvalidDrop = invalidDrop;
					ddDivs[o['uniqueid']].onDragOver    = dragOver;
					ddDivs[o['uniqueid']].onDragOut     = dragOut;
					
					_countChannels += 1;
					$('countChannels').innerHTML = _countChannels;
				}
				
				var template_channel = new Template($('Template::Channel').innerHTML);
				var monitor          = "";
				
				if (o['monitor'] == 'True')
				{
					monitor = new Template($('Template::Channel::Monitor').innerHTML);
					monitor = monitor.evaluate(o);
				}
				o['monitor'] = monitor;
				o['color']   = color(o['state']);
				o['channel'] = o['channel'].replace('<', '&lt;').replace('>', '&gt;');
				
				div.innerHTML = template_channel.evaluate(o);
				
				break;
			
			// Bridges
			case "Bridge":
				if (o['status'] == "Unlink")
				{
					o['action'] = "RemoveBridge";
					break;
				}
			
				var id  = "bridge-" + o['uniqueid'] + '+++' + o['bridgeduniqueid'];
				var div = $(id);
				if (!div)
				{
					div           = document.createElement('div');
					div.id        = id;
					div.className = 'callDiv';
					
					$('callsDiv').appendChild(div);
					
					ddDivs[div.id]               = new YAHOO.util.DD(div.id);
					ddDivs[div.id].onMouseDown   = setStartPosition;
					ddDivs[div.id].onDragDrop    = channelCallDrop;
					ddDivs[div.id].onInvalidDrop = invalidDrop;
					ddDivs[div.id].onDragOver    = dragOver;
					ddDivs[div.id].onDragOut     = dragOut;
					
					_countCalls += 1;
					$('countCalls').innerHTML = _countCalls;
				}
				
				o['color']           = color(o['status']);
				o['callerid']        = $('callerid-' + o['uniqueid']) ? $('callerid-' + o['uniqueid']).innerHTML : "";
				o['bridgedcallerid'] = $('callerid-' + o['bridgeduniqueid']) ? $('callerid-' + o['bridgeduniqueid']).innerHTML : "";
				o['channel']         = o['channel'].replace('<', '&lt;').replace('>', '&gt;');
				o['bridgedchannel']  = o['bridgedchannel'].replace('<', '&lt;').replace('>', '&gt;');
				
				var template  = new Template($("Template::Bridge").innerHTML);
				div.innerHTML = template.evaluate(o);
				
				if (o['status'] == 'Link')
				{
					var _t = new Date().getTime() / 1000;
					stopChrono('callStatus-' + o['uniqueid'] + '+++' + o['bridgeduniqueid']);
					chrono('callStatus-' + o['uniqueid'] + '+++' + o['bridgeduniqueid'], _t - o['starttime']);
				}
					
				break;
		}
	}
	
	if (!Object.isUndefined(o['action']))
	{
		switch (o['action'])
		{
			case "Error":
				_statusError = true;
				doError(o['message']);
				return;
				break;
				
			case "Reload":
				_statusReload = true;
				setTimeout("location.href = 'index.php'", o['time']);
				return;
				break;
		
			case "RemoveChannel":
				var div = $(o['uniqueid']);
				if (div)
				{
					$('channelsDiv').removeChild(div);
					_countChannels -= 1;
					$('countChannels').innerHTML = _countChannels;
				}
				break;
				
			case "RemoveBridge":
				var div = $("bridge-" + o['uniqueid'] + '+++' + o['bridgeduniqueid']);
				if (div)
				{
					stopChrono('callStatus-' + o['uniqueid'] + '+++' + o['bridgeduniqueid']);
					$('callsDiv').removeChild(div);
					_countCalls -= 1;
					$('countCalls').innerHTML = _countCalls;
				}
				break;
		}
	}
	
	return;
	//
	//
	//
	
	if (o['Action'] == 'Error')
	{
		_statusError = true;
		doError(o['Message']);
		return;
	}
	
	if (o['Action'] == 'Reload')
	{
		_statusReload = true;
		setTimeout("location.href = 'index.php'", o['Time']);
		return;
	}
	
	if (o['Action'] == 'CliResponse')
	{
		$('cliResponse').value += '\r\n' + unescape(decodeURI(o['Response'])).replace(/\<br\>/g, '\r\n');
		$('cliResponse').scrollTop = $('cliResponse').scrollHeight - $('cliResponse').offsetHeight + 10;
		return; 
	}
	
	if (o['Action'] == 'doAlertError')
		doError(o['Message']);
		
	if (o['Action'] == 'doAlertWarn')
		doWarn(o['Message']);
		
	if (o['Action'] == 'doAlertInfo')
		doAlert(o['Message']);
	
	// Fix all CallerIDs
	if (o['CallerID'])
		o['CallerID'] = o['CallerID'].replace('<unknown>', 'unknown').replace('<', '&lt;').replace('>', '&gt;');
	
	if (o['CallerID1'])
		o['CallerID1'] = o['CallerID1'].replace('<unknown>', 'unknown').replace('<', '&lt;').replace('>', '&gt;');
	
	if (o['CallerID2'])
		o['CallerID2'] = o['CallerID2'].replace('<unknown>', 'unknown').replace('<', '&lt;').replace('>', '&gt;');
		
	if (o['CallerIDName'])
		o['CallerIDName'] = o['CallerIDName'].replace('<unknown>', 'unknown').replace('<', '&lt;').replace('>', '&gt;');
		
	if (o['CallerIDNum'])
		o['CallerIDNum'] = o['CallerIDNum'].replace('<unknown>', 'unknown').replace('<', '&lt;').replace('>', '&gt;');
	
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
			
			var rec = '';
			if (o['Monitor'] == 'True')
				rec = "<a href='javascript:recordStop(\"" + o['Uniqueid'] + "\")' title='Stop Monitor'><img src='image/record.png' border='0' width='8' height='8'></a>&nbsp;&nbsp;";
			
			var template = "<table width='330'><tr>";
			template    += "<td id='channel-{Uniqueid}' class='status' width='260'>{Channel}</td>";
			template    += "<td id='channelStatus-{Uniqueid}' bgcolor='{color}' class='status' width='70'>{State}</td>";
			template    += "</tr></table>";
			template     = template.replace(/\{Uniqueid\}/g, o['Uniqueid']);
			template     = template.replace(/\{Channel\}/g, rec + o['Channel']);
			//template     = template.replace(/\{Channel\}/g, rec + o['Channel'] + '<br>' + o['CallerIDName'] + ' <' + o['CallerIDNum'] + '>');
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
			
			_countChannels += 1;
			$('countChannels').innerHTML = _countChannels;
		}
		
		return;
	}
	
	if (o['Action'] == 'Call')
	{
		var id  = 'call-' + o['SrcUniqueID'] + '+++' + o['DestUniqueID'];
		var div = $(id); 
		if (!div)
		{
			div           = document.createElement('div');
			div.id        = id;
			div.className = 'callDiv';
		
			var template = "<table width='570'><tr>";
			template    += "<td class='status' width='250' id='callChannel-{SrcUniqueID}'>{Source}</td>";
			template    += "<td class='status' width='70' bgcolor='{color}' id='callStatus-{SrcUniqueID}+++{DestUniqueID}'>{Status}<br><span style='font-family: monospace;' id='chrono-callStatus-{SrcUniqueID}+++{DestUniqueID}'></span></td>";
			template    += "<td class='status' width='250' id='callChannel-{DestUniqueID}'>{Destination}</td>";
			template    += "</tr></table>";
			
			if (o['CallerID'])
				o['CallerID1'] = o['CallerIDName'] + ' &lt;' + o['CallerID'] + '&gt;';
			
			template = template.replace(/\{SrcUniqueID\}/g, o['SrcUniqueID']);
			template = template.replace(/\{DestUniqueID\}/g, o['DestUniqueID']);
			template = template.replace(/\{Source\}/g, o['Source'] + (o['CallerID1'] ? '<br>' + o['CallerID1'] : ''));
			template = template.replace(/\{Destination\}/g, o['Destination'] + (o['CallerID2'] ? '<br>' + o['CallerID2'] : ''));
			template = template.replace(/\{Status\}/g, o['Status']);
			template = template.replace(/\{color\}/g, color(o['Status']));
			
			div.innerHTML = template;
			
			$('callsDiv').appendChild(div);
			if (o['Status'] == 'Link')
				chrono('callStatus-' + o['SrcUniqueID'] + '+++' + o['DestUniqueID'], o['Seconds']);
			
			ddDivs[div.id]               = new YAHOO.util.DD(div.id);
			ddDivs[div.id].onMouseDown   = setStartPosition;
			ddDivs[div.id].onDragDrop    = channelCallDrop;
			ddDivs[div.id].onInvalidDrop = invalidDrop;
			ddDivs[div.id].onDragOver    = dragOver;
			ddDivs[div.id].onDragOut     = dragOut;
	
			_countCalls += 1;
			$('countCalls').innerHTML = _countCalls;
		}

		return;
	}
	
	if (o['Action'] == 'Hangup')
	{
		var div = $(o['Uniqueid']);
		if (div)
		{
			$('channelsDiv').removeChild(div);
			_countChannels -= 1;
			$('countChannels').innerHTML = _countChannels;
		}
		
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
		var div = $('call-' + o['SrcUniqueID'] + '+++' + o['DestUniqueID']);
		if (!div)
		{
			o['Action'] = 'Call';
			o['Status'] = 'Dial';
			Process(o);
		}
		return;
	}
	
	if (o['Action'] == 'Link')
	{
		td = $('callStatus-' + o['Uniqueid1'] + '+++' + o['Uniqueid2']);
		if (td)
		{
			td.style.backgroundColor = color('Link');
			if (MONAST_CALL_TIME)
			{
				td.innerHTML = 'Link<br><span style="font-family: monospace;" id="chrono-' + td.id + '"></span>';
				chrono(td.id, o['Seconds']);
			}
			else
			{
				td.innerHTML = 'Link';
			}
		}
		else
		{
			o['Action']       = 'Call';
			o['Status']       = 'Link';
			o['Source']       = o['Channel1'];
			o['Destination']  = o['Channel2'];
			o['SrcUniqueID']  = o['Uniqueid1'];
			o['DestUniqueID'] = o['Uniqueid2'];
			Process(o);
		}
		
		return;
	}
	
	if (o['Action'] == 'Unlink')
	{
		var table = $('call-' + o['Uniqueid1'] + '+++' + o['Uniqueid2']);
		if (table)
		{	
			stopChrono('callStatus-' + o['Uniqueid1'] + '+++' + o['Uniqueid2']);
			$('callsDiv').removeChild(table);
		
			_countCalls -= 1;
			$('countCalls').innerHTML = _countCalls;
		}
		
		return;
	}
	
	if (o['Action'] == 'NewCallerid')
	{
		td = $('callChannel-' + o['Uniqueid']);
		if (td)
			td.innerHTML = o['Channel'] + '<br>' + o['CallerIDName'] + ' &lt;' + o['CallerID'] + '&gt;';
		
		return;
	}
	
	if (o['Action'] == 'Rename')
	{
		td = $('channel-' + o['Uniqueid']);
		if (td)
			td.innerHTML = o['Newname'];
			
		td = $('callChannel-' + o['Uniqueid']);
		if (td)
			td.innerHTML = o['Newname'] + '<br>' + o['CallerIDName'] + ' &lt;' + o['CallerID'] + '&gt';
			
		return;
	}
	
	if (o['Action'] == 'MeetmeCreate')
	{
		var id  = 'meetme-' + o['Meetme'];
		var div = $(id);
		if (!div)
		{
			div           = document.createElement('div');
			div.id        = id;
			div.className = 'meetmeDivWrap';
			
			var template = "<div class='meetmeDiv'><table width='250'><tr>";
			template    += "<td align='center' class='statusHeader'>Meetme \"{Meetme}\" (<span id='countMeetme-{Meetme}'>0</span>)</td>";
			template    += "</tr></table></div>";
			template     = template.replace(/\{Meetme\}/g, o['Meetme']);
			
			div.innerHTML = template;
			
			$('meetmeDivWrapper').appendChild(div);
			
			ddDivs[id] = new YAHOO.util.DDTarget(id);
			_countMeetme[o['Meetme']] = 0;
		}
		
		return;
	}
	
	if (o['Action'] == 'MeetmeDestroy')
	{
		var id  = 'meetme-' + o['Meetme'];
		var div = $(id);
		if (div)
		{
			$('meetmeDivWrapper').removeChild(div);
		}
		
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
			
			var UserInfo = o['CallerIDName'] + ' &lt;' + o['CallerIDNum'] + '&gt;';		
			//if (o['CallerIDName'] == 'None' && o['CallerIDNum'] == 'None')
			if (o['CallerIDName'] == null && o['CallerIDNum'] == null)
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
			
			_countMeetme[o['Meetme']] += 1;
			$('countMeetme-' + o['Meetme']).innerHTML = _countMeetme[o['Meetme']];
		}
		
		return;
	}
	
	if (o['Action'] == 'MeetmeLeave')
	{
		var id  = 'meetme-' + o['Meetme'] + '-' + o['Usernum'];
		var div = $(id);
		if (div)
		{
			$('meetme-' + o['Meetme']).removeChild(div);
			_countMeetme[o['Meetme']] -= 1;
			$('countMeetme-' + o['Meetme']).innerHTML = _countMeetme[o['Meetme']];
		}
			
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
			template    += "<td class='status' align='center' width='260'>{Channel}<br>{CallerIDName} &lt;{CallerID}&gt;</td>";
			template    += "</tr></table>";
			template     = template.replace(/\{Exten\}/g, o['Exten']);
			template     = template.replace(/\{From\}/g, o['From']);
			template     = template.replace(/\{CallerIDFrom\}/g, getCallerId(user));
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
			
			_countParked += 1;
			$('countParked').innerHTML = _countParked;
		}
		
		return;
	}
	
	if (o['Action'] == 'UnparkedCall')
	{
		var id  = 'parked-' + o['Exten'];
		var div = $(id);
		if (div)
		{
			$('parkedsDiv').removeChild(div);
			_countParked -= 1;
			$('countParked').innerHTML = _countParked;
		}
			
		return;
	}
	
	if (o['Action'] == 'AddQueueMember')
	{
		var id  = 'queueMember-' + o['Queue'] + ':::' + o['Member'];
		var div = $(id);
		if (!div)
		{
			div           = document.createElement('div');
			div.id        = id;
			div.className = 'queueMembersDiv';
			
			pausedMembers[o['Queue'] + '-' + o['Member']] = false;
			if (o['Paused'] == '1')
			{
				pausedMembers[o['Queue'] + '-' + o['Member']] = true;
				o['Status'] = 'Paused';
				if (MONAST_CALL_TIME)
					o['Status'] = 'Paused<br><span style="font-family: monospace;" id="chrono-queueMemberStatus-{Queue}-{Member}">00:00:00</span>';
			}
			
			var template = "<table width='300'><tr>";
			template    += "<td class='status' width='170' align='center'><a href='javascript:void(0)' title='Options' onClick='showMemberOptionsMenu(\"{Queue}:::{Member}\")'>{MemberName}</a></td>";
			template    += "<td class='status' width='40' align='center' id='queueMemberCallsTaken-{Queue}-{Member}'>{CallsTaken}</td>";
			template    += "<td class='status' width='90' align='center' id='queueMemberStatus-{Queue}-{Member}' bgcolor='{color}'>{Status}</td>";
			template    += "</tr></table>";
			
			template     = template.replace(/\{Status\}/g, o['Status']);
			template     = template.replace(/\{color\}/g, color(o['Status']));
			template     = template.replace(/\{Queue\}/g, o['Queue']);
			template     = template.replace(/\{Member\}/g, o['Member']);
			template     = template.replace(/\{MemberName\}/g, o['MemberName'].replace('<', '&lt;').replace('>', '&gt;'));
			template     = template.replace(/\{CallsTaken\}/g, o['CallsTaken']);
			
			div.innerHTML = template;
			
			$('queueMembers-' + o['Queue']).appendChild(div);
			
			if (MONAST_CALL_TIME && pausedMembers[o['Queue'] + '-' + o['Member']])
				chrono('queueMemberStatus-' + o['Queue'] + '-' + o['Member'], o['PausedTime'], false);
			
			_countMembers[o['Queue']] += 1;
			
			ddDivs[id]               = new YAHOO.util.DD(id);
			ddDivs[id].onMouseDown   = setStartPosition;
			ddDivs[id].onDragDrop    = queueMemberDrop;
			ddDivs[id].onInvalidDrop = invalidDrop;
			ddDivs[id].onDragOver    = dragOver;
			ddDivs[id].onDragOut     = dragOut;
		}
		
		$('queueMembersCount-' + o['Queue']).innerHTML = _countMembers[o['Queue']];
		 
		return;
	}
	
	if (o['Action'] == 'RemoveQueueMember')
	{
		var id  = 'queueMember-' + o['Queue'] + ':::' + o['Member'];
		var div = $(id);
		if (div)
		{
			stopChrono('queueMemberStatus-' + o['Queue'] + '-' + o['Member']);
			pausedMembers[o['Queue'] + '-' + o['Member']] = false;
			
			$('queueMembers-' + o['Queue']).removeChild(div);
			_countMembers[o['Queue']] -= 1;
		}
		
		$('queueMembersCount-' + o['Queue']).innerHTML = _countMembers[o['Queue']];
		
		return;
	}
	
	if (o['Action'] == 'QueueMemberStatus')
	{
		var td = $('queueMemberCallsTaken-' + o['Queue'] + '-' + o['Member']);
		if (td)
			td.innerHTML = o['CallsTaken'];
			
		var td = $('queueMemberStatus-' + o['Queue'] + '-' + o['Member']);
		if (td)
		{
			if (o['Paused'] == '1')
			{
				o['Status'] = 'Paused';
				if (MONAST_CALL_TIME)
				{
					if (!pausedMembers[o['Queue'] + '-' + o['Member']])
					{
						pausedMembers[o['Queue'] + '-' + o['Member']] = true;
						td.innerHTML = 'Paused<br><span style="font-family: monospace;" id="chrono-' + td.id + '">00:00:00</span>';
						td.style.backgroundColor = color(o['Status']);
						chrono(td.id, o['PausedTime'], false);
					}
				}
				else
				{
					td.innerHTML = o['Status'];
					td.style.backgroundColor = color(o['Status']);
				}
			}
			else if (pausedMembers[o['Queue'] + '-' + o['Member']])
			{
				pausedMembers[o['Queue'] + '-' + o['Member']] = false;
				td.innerHTML = o['Status'];
				td.style.backgroundColor = color(o['Status']);
			}
			else
			{
				td.innerHTML = o['Status'];
				td.style.backgroundColor = color(o['Status']);
			}
		}
			
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
				UserInfo = o['CallerIDName'] + ' &lt;' + o['CallerID'] + '&gt;'; 
			
			var template = "<table width='220'><tr>";
			template    += "<td class='status' align='center'>{UserInfo}<br><span style='font-family: monospace;' id='chrono-{ID}'></span></td>";
			template    += "</tr></table>";
			template     = template.replace(/\{UserInfo\}/g, UserInfo);
			template     = template.replace(/\{ID\}/g, div.id);
			
			div.innerHTML = template;
			
			$('queueClients-' + o['Queue']).appendChild(div);
			
			if (MONAST_CALL_TIME)
				chrono(div.id, o['Wait']);
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
		
		/*if (o['Cause'] == 'Completed')
		{
			_countCompleted[o['Queue']] += 1;
			$('queueStatsCompleted-' + o['Queue']).innerHTML = _countCompleted[o['Queue']];
		}*/
		if (o['Cause'] == 'Abandoned')
		{
			_countAbandoned[o['Queue']] += 1;
			$('queueStatsAbandoned-' + o['Queue']).innerHTML = _countAbandoned[o['Queue']];
		}
		
		stopChrono(id);
		
		return;
	}
	
	if (o['Action'] == 'QueueParams')
	{
		_countCompleted[o['Queue']] = parseInt(o['Completed']);
		_countAbandoned[o['Queue']] = parseInt(o['Abandoned']);
		
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
	
	if (o['Action'] == 'AddQueueMemberCall')
	{
		var id  = 'queueMember-' + o['Queue'] + ':::' + o['Member'];
		var div = $(id);
		if (div)
		{
			var id = 'queueMemberCall-' + o['Queue'] + ':::' + o['Member'] + ':::' + o['Uniqueid'];
			
			if (!$(id))
			{
				UserInfo = o['Channel'];
				if (o['CallerID'])
					UserInfo = o['CallerID'];
			
				var template = "<table width='300' id='queueMemberCall-{Queue}:::{Member}:::{Uniqueid}'><tr>";
				//template    += "<td class='status' width='75' bgcolor='#ffffb0'>Answered</td>";
				//template    += "<td class='status' width='225'>{UserInfo}<br><span style='font-family: monospace;' id='chrono-{ID}'></span></td>";
				template    += "<td class='status' width='213'>{UserInfo}<br><span style='font-family: monospace;' id='chrono-{ID}'></span></td>";
				template    += "<td class='status' width='87' bgcolor='#ffffb0'>Answered</td>";
				template    += "</tr></table>";
				
				template     = template.replace(/\{Queue\}/g, o['Queue']);
				template     = template.replace(/\{Member\}/g, o['Member']);
				template     = template.replace(/\{Uniqueid\}/g, o['Uniqueid']);
				template     = template.replace(/\{UserInfo\}/g, UserInfo);
				template     = template.replace(/\{ID\}/g, id);
	
				div.innerHTML += template;
				
				if (MONAST_CALL_TIME)
					chrono(id, o['Seconds']);
			}
		}
		
		return;
	}
	
	if (o['Action'] == 'RemoveQueueMemberCall')
	{
		var id = 'queueMemberCall-' + o['Queue'] + ':::' + o['Member'] + ':::' + o['Uniqueid'];
		var tb = $(id);
		if (tb)
		{
			$('queueMember-' + o['Queue'] + ':::' + o['Member']).removeChild(tb);
			stopChrono(id);
		}
			
		return;
	}
	
	if (o['Action'] == 'MonitorStart')
	{
		var td = $('channel-' + o['Uniqueid'])
		if (td)
		{
			var rec = "<a href='javascript:recordStop(\"" + o['Uniqueid'] + "\")' title='Stop Monitor'><img src='image/record.png' border='0' width='8' height='8'></a>&nbsp;&nbsp;";
			td.innerHTML = rec + o['Channel'];
		}
		
		return;
	}
	
	if (o['Action'] == 'MonitorStop')
	{
		var td = $('channel-' + o['Uniqueid'])
		if (td)
		{
			td.innerHTML = o['Channel'];
		}
		
		return;
	}
	
	if (o['Action'] == 'UpdateCallDuration')
	{
		var id = 'callStatus-' + o['Uniqueid1'] + '+++' + o['Uniqueid2'];
		stopChrono(id);
		chrono(id, o['Seconds']);
		
		return;
	}
}

function showHidePannels(e)
{
	$(this.get('value')).className = (e.newValue ? '' : 'yui-hidden');
	_state.buttons[this.get('id')] = e.newValue;
	YAHOO.util.Cookie.set('_state', Object.toJSON(_state));
}

// Originate a Call
function originateCall(peer, number, type)
{
	if (!number)
	{
		doWarn('Destination number not defined!');
		return false;
	}
	
	var ret = function(msg)
	{
		if (msg == 'OK'){
			$('originateNumber').value = '';
			_originateDialog.hide();
		}
	}
	
	new Ajax.Request('action.php', 
	{
		method: 'get',
		parameters: {
			reqTime: new Date().getTime(),
			action: Object.toJSON({Action: 'OriginateCall', Source: peer, Destination: number, Type: type})
		},
		onSuccess: function(transport)
		{
			if (transport.responseText == 'OK') 
			{
				$('originateNumber').value = '';
				_originateDialog.hide();
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
			action: Object.toJSON({Action: 'OriginateDial', Source: src, Destination: dst, Type: type})
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
		chanId = chanId.substring(5, chanId.lastIndexOf('+++'));
	}
	
	doConfirm(msg, function () {
		new Ajax.Request('action.php', 
		{
			method: 'get',
			parameters: {
				reqTime: new Date().getTime(),
				action: Object.toJSON({Action: 'HangupChannel', Uniqueid: chanId})
			}
		});
	});
}

// Rercord a call
function recordCall(chanId)
{
	var msg = "Record this Channel?";
	var mix = 0;
	if (chanId.indexOf('call') != -1)
	{
		msg    = "Record this Call?";
		chanId = chanId.substring(5, chanId.lastIndexOf('+++'));
		mix    = 1;
	}
	
	doConfirm(msg, function () {
		new Ajax.Request('action.php', 
		{
			method: 'get',
			parameters: {
				reqTime: new Date().getTime(),
				action: Object.toJSON({Action: 'MonitorChannel', Uniqueid: chanId, Mix: mix})
			}
		});
	});
}

function recordStop(chanId)
{
	doConfirm('Stop this Record?', function () {
		new Ajax.Request('action.php', 
		{
			method: 'get',
			parameters: {
				reqTime: new Date().getTime(),
				action: Object.toJSON({Action: 'MonitorStop', Uniqueid: chanId})
			}
		});
	});
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
		dest = getCallerId(dst);
	}
	
	doConfirm("Transfer this call to " + comp + dest + '?', function () {
		new Ajax.Request('action.php', 
		{
			method: 'get',
			parameters: {
				reqTime: new Date().getTime(),
				action: Object.toJSON({Action: 'TransferCall', Source: src, Destination: dst, Type: type})
			}
		});
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
			action: Object.toJSON({Action: 'ParkCall', Park: park, Announce: announce})
		}
	});
}

// Meetme kick
function meetmeKick(meetme, usernum)
{
	doConfirm('Kick this user from meetme ' + meetme + '?', function () {
		new Ajax.Request('action.php', 
		{
			method: 'get',
			parameters: {
				reqTime: new Date().getTime(),
				action: Object.toJSON({Action: 'MeetmeKick', Meetme: meetme, Usernum: usernum})
			}
		});
	});
}

// Parked Hangup()
function parkedHangup(exten)
{
	doConfirm('Hangup parked call on exten ' + exten + '?', function () {
		new Ajax.Request('action.php', 
		{
			method: 'get',
			parameters: {
				reqTime: new Date().getTime(),
				action: Object.toJSON({Action: 'ParkedHangup', Exten: exten})
			}
		});
	});
}

// Add/Remove Pause/Unpause Queue members
function queueMemberAdd(queue, member)
{
	doConfirm('Add member ' + (getCallerId(member) ? getCallerId(member) : member) + ' to queue ' + queue + '?', function () {
		new Ajax.Request('action.php', 
		{
			method: 'get',
			parameters: {
				reqTime: new Date().getTime(),
				action: Object.toJSON({Action: 'AddQueueMember', Queue: queue, Member: member})
			}
		});
	});
}

function queueMemberRemove(queue, member)
{
	doConfirm('Remove member ' + (getCallerId(member) ? getCallerId(member) : member) + ' from queue ' + queue + '?', function () {
		new Ajax.Request('action.php', 
		{
			method: 'get',
			parameters: {
				reqTime: new Date().getTime(),
				action: Object.toJSON({Action: 'RemoveQueueMember', Queue: queue, Member: member})
			}
		});
	});
}
function queueMemberRemove2(p_sType, p_aArgs, id)
{
	var tmp = id.split(':::');
	queueMemberRemove(tmp[0], tmp[1]);
}

function queueMemberPause(p_sType, p_aArgs, id)
{
	var tmp    = id.split(':::');
	var queue  = tmp[0];
	var member = tmp[1];

	doConfirm('Pause member ' + (getCallerId(member) ? getCallerId(member) : member) + ' in queue ' + queue + '?', function () {
		new Ajax.Request('action.php', 
		{
			method: 'get',
			parameters: {
				reqTime: new Date().getTime(),
				action: Object.toJSON({Action: 'PauseQueueMember', Queue: queue, Member: member})
			}
		});
	});
}

function queueMemberUnpause(p_sType, p_aArgs, id)
{
	var tmp    = id.split(':::');
	var queue  = tmp[0];
	var member = tmp[1];

	doConfirm('Unpause member ' + (getCallerId(member) ? getCallerId(member) : member) + ' in queue ' + queue + '?', function () {
		new Ajax.Request('action.php', 
		{
			method: 'get',
			parameters: {
				reqTime: new Date().getTime(),
				action: Object.toJSON({Action: 'UnpauseQueueMember', Queue: queue, Member: member})
			}
		});
	});
}

// Skype
function skypeUserLogin(p_sType, p_aArgs, id)
{
	var skypeName = id.replace('Skype/', '');

	doConfirm('Login skype user ' + skypeName + '?', function () {
		new Ajax.Request('action.php', 
		{
			method: 'get',
			parameters: {
				reqTime: new Date().getTime(),
				action: Object.toJSON({Action: 'SkypeLogin', SkypeName: skypeName})
			}
		});
	});
}

function skypeUserLogout(p_sType, p_aArgs, id)
{
	var skypeName = id.replace('Skype/', '');

	doConfirm('Logout skype user ' + skypeName + '?', function () {
		new Ajax.Request('action.php', 
		{
			method: 'get',
			parameters: {
				reqTime: new Date().getTime(),
				action: Object.toJSON({Action: 'SkypeLogout', SkypeName: skypeName})
			}
		});
	});
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
		
		doConfirm('Originate a call from ' + getCallerId(src) + ' to ' + getCallerId(dst) + '?', function () {
			originateDial(src, dst, 'default');
		});
	}
	if (id.indexOf('meetme-') != -1)
	{
		var src = this.id.replace('peerDiv-', '');
		var dst = id.replace('meetme-', '');
		
		doConfirm('Invite ' + getCallerId(src) + ' to meetme ' + dst + '?', function () {
			originateCall(src, dst, 'meetme');
		});
	}
	if (id.indexOf('queueMembersDrop-') != -1)
	{
		var member = this.id.replace('peerDiv-', '');
		var queue  = id.replace('queueMembersDrop-', '');
		queueMemberAdd(queue, member);
	}
	
	backToStartPosition(this.id);
}

function channelCallDrop(e, id)
{
	if (id == 'trash')
		hangupCall(this.id);
	
	if (id == 'record')
		recordCall(this.id);
	
	if (id.indexOf('peerDiv-') != -1 && this.id.indexOf('call-') == -1)
		transferCall(this.id, id.substring(8), 'peer');
		
	if (id.indexOf('peerDiv-') != -1 && this.id.indexOf('call-') != -1)
	{
		var ids  = this.id.substring(5).split('+++');
		var srcA = $('callChannel-' + ids[0]).innerHTML.replace(/<br>/ig, ' (').replace(' ( ', ' (') + ')';
		var srcB = $('callChannel-' + ids[1]).innerHTML.replace(/<br>/ig, ' (').replace(' ( ', ' (') + ')';
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
		var ids  = this.id.substring(5).split('+++');
		var srcA = $('callChannel-' + ids[0]).innerHTML.replace(/<br>/ig, ' (').replace(' ( ', '(') + ')';
		var srcB = $('callChannel-' + ids[1]).innerHTML.replace(/<br>/ig, ' (').replace(' ( ', '(') + ')';
		showTransferDialog(ids[0], srcA, ids[1], srcB, 'ParkedCalls');
	}
	
	backToStartPosition(this.id);
}

function meetmeDrop(e, id)
{
	if (id == 'trash')
	{
		var info = this.id.replace('meetme-', '').split('-');
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
		
		doConfirm('Transfer Parked Call on exten ' + parked + ' to ' + getCallerId(source) + '?', function () {
			originateCall(source, parked, 'default');
		});
	}
	
	backToStartPosition(this.id);
}

function queueMemberDrop(e, id)
{
	if (id == 'trash')
	{
		var info = this.id.replace('queueMember-', '').split(':::');
		queueMemberRemove(info[0], info[1]);
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
	_originateDialog.peerId = peerId;
	_originateDialog.cfg.queueProperty("xy", ddDivs['peerDiv-' + peerId].startPos);  
	_originateDialog.render();
	_originateDialog.show();
}

// Peer Options MENU
var _POMENU = new Array();
function showPeerOptionsMenu(id)
{
	if (!_POMENU[id])
	{
		var items = [[
			{text: 'Originate Call', onclick: {fn: showOriginateDialog, obj: id}}
		]];
		
		if (id.indexOf('Skype') != -1)
		{
			items[items.length] = [
				{text: 'Login', onclick: {fn: skypeUserLogin, obj: id}},
				{text: 'Logout', onclick: {fn: skypeUserLogout, obj: id}}
			];
		}
	
		_POMENU[id] = new YAHOO.widget.Menu("peerOptionsMenu-" + id, { xy: YAHOO.util.Dom.getXY(YAHOO.util.Dom.get('peerDiv-' + id)) });
		_POMENU[id].addItems(items);
		
		_POMENU[id].setItemGroupTitle('Options for "' + getCallerId(id) + '"', 0);
		
		if (id.indexOf('Skype') != -1)
		{
			_POMENU[id].setItemGroupTitle('Skype Options', 1);
		}
		
		_POMENU[id].render("peerDiv-" + id);
	}
	else
	{
		_POMENU[id].cfg.queueProperty("xy", YAHOO.util.Dom.getXY(YAHOO.util.Dom.get('peerDiv-' + id)));
	}
	_POMENU[id].show(); 
}

// Queue Member Options MENU
function showMemberOptionsMenu(id)
{
	if (!_POMENU[id])
	{
		_POMENU[id] = new YAHOO.widget.Menu("queueMemberOptionsMenu-" + id, { xy: YAHOO.util.Dom.getXY(YAHOO.util.Dom.get('queueMember-' + id)), zindex: 15 });
		_POMENU[id].addItems([
			{text: 'Pause Member', onclick: {fn: queueMemberPause, obj: id}},
			{text: 'Unpause Member', onclick: {fn: queueMemberUnpause, obj: id}},
			{text: 'Remove Member', onclick: {fn: queueMemberRemove2, obj: id}}
		]);
		_POMENU[id].render(document.body);
	}
	else
	{
		_POMENU[id].cfg.queueProperty("xy", YAHOO.util.Dom.getXY(YAHOO.util.Dom.get('queueMember-' + id)));
	}
	_POMENU[id].show();
	backToStartPosition('queueMember-' + id);
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
		$('transferDestination').innerHTML = 'transfer to ' + getCallerId(dst);
		
	$('transferSourceValueA').value    = idA;
	$('transferSourceValueB').value    = idB;
	$('transferSourceValueA').checked  = true;
	$('transferSourceTextA').innerHTML = srcA; 
	$('transferSourceTextB').innerHTML = srcB;
	_transferDialog.destChannel         = dst;
	_transferDialog.render();
	_transferDialog.show();
}

// Chrono for calls linked
var _chrono = new Array();
function chrono(id, secs, hideSeconds)
{
	if (!MONAST_CALL_TIME)
		return;

	if (hideSeconds == undefined)
		hideSeconds = false;

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
			_chrono[id] = {hours: d.getUTCHours(), mins: d.getUTCMinutes(), secs: d.getUTCSeconds(), run: null, showSeconds: !hideSeconds};
		}
		else
			_chrono[id] = {hours: 0, mins: 0, secs: 0, run: null, showSeconds: !hideSeconds};
	}
	
	var secs  = (_chrono[id].secs < 10 ? '0' + _chrono[id].secs : _chrono[id].secs);
	var mins  = (_chrono[id].mins < 10 ? '0' + _chrono[id].mins : _chrono[id].mins);
	var hours = (_chrono[id].hours < 10 ? '0' + _chrono[id].hours : _chrono[id].hours);
	
	var f = $('chrono-' + id);
	if (f)
		f.innerHTML = hours + ':' + mins + (_chrono[id].showSeconds ? ':' + secs : '');
		
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
	
	if (command)
	{
		new Ajax.Request('action.php', 
		{
			method: 'get',
			parameters: {
				reqTime: new Date().getTime(),
				action: Object.toJSON({Action: 'CliCommand', CliCommand: command})
			}
		});
	}
}

// Alerts and Confirmations
function doAlert(message)
{
	_alert.setHeader('Information');
	_alert.setBody(message);
	_alert.cfg.setProperty("icon", YAHOO.widget.SimpleDialog.ICON_INFO);
	_alert.render();
	_alert.show();
}
function doError(message)
{
	_alert.setHeader('Error');
	_alert.setBody(message);
	_alert.cfg.setProperty("icon", YAHOO.widget.SimpleDialog.ICON_BLOCK);
	_alert.render();
	_alert.show();
}
function doWarn(message)
{
	_alert.setHeader('Warning');
	_alert.setBody(message);
	_alert.cfg.setProperty("icon", YAHOO.widget.SimpleDialog.ICON_WARN);
	_alert.render();
	_alert.show();
}
function doConfirm(message, handleYes, handleNo)
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
}

// Auth
function doLogin()
{
	var username = $('_username').value;
	var secret   = $('_secret').value;
	
	if (!username)
	{
		doAlert('You must define an user.');
		$('_reqStatus').innerHTML = "<font color='red'>User not defined!</font>";
	}
	else
	{
		new Ajax.Request('login.php', {
			method: 'post',
			parameters: {
				reqTime: new Date().getTime(),
				username: username,
				secret: secret
			},
			onCreate: function () {
				$('_reqStatus').innerHTML = 'Authenticating, please wait...';
			},
			onSuccess: function (r) {
				var json = r.responseJSON;
				if (json['error'])
				{
					$('_reqStatus').innerHTML = "<font color='red'>Monast Error!</font>";;
					doError(json['error']);
				}
					
				if (json['success'])
				{
					$('_reqStatus').innerHTML = "Authenticated, reloading...";
					setTimeout("location.href = 'index.php'", 1000);
				}
			}
		});
	}
	return false;
}
function doLogout()
{
	new Ajax.Request('action.php', 
	{
		method: 'get',
		parameters: {
			reqTime: new Date().getTime(),
			action: Object.toJSON({Action: 'Logout'})
		}
	});
}
