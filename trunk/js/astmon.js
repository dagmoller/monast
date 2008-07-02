
var json = new JSON();

String.prototype.trim = function() { return this.replace(/^\s*/, "").replace(/\s*$/, ""); }
function $(id) { return document.getElementById(id); }

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

function Process(o)
{
	//console.dir(o);
	$('debugMsg').innerHTML += o + "<br>\r\n";
	o = json.decode(o);
	
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
			
			ddDiv[o['Uniqueid']]               = new YAHOO.util.DD(o['Uniqueid']);
			ddDiv[o['Uniqueid']].startPos      = YAHOO.util.Dom.getXY(YAHOO.util.Dom.get(o['Uniqueid']));
			ddDiv[o['Uniqueid']].onDragDrop    = peerIDrop;
			ddDiv[o['Uniqueid']].onInvalidDrop = peerIDrop;
		}
		
		return;
	}
	
	if (o['Action'] == 'Call')
	{
		var template = "<table width='600'><tr>";
		template    += "<td class='status' width='260' id='callChannel-{SrcUniqueID}'>{Source}</td>";
		template    += "<td class='status' width='80' bgcolor='{color}' id='callStatus-{SrcUniqueID}-{DestUniqueID}'>{Status}</td>";
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
		
		ddDiv[div.id]               = new YAHOO.util.DD(div.id);
		ddDiv[div.id].startPos      = YAHOO.util.Dom.getXY(YAHOO.util.Dom.get(div.id));
		ddDiv[div.id].onDragDrop    = peerIDrop;
		ddDiv[div.id].onInvalidDrop = peerIDrop;
		
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
			td.innerHTML = 'Link';
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
}

function initIFrame()
{
	var iframe = document.getElementById('__frame');
	iframe.src = 'status.php';
}

function startIFrame()
{
	setTimeout('initIFrame()', 1000);
}
//startIFrame(); // deve ser chamado no final da index.html

function showDiv(div)
{
	var divs = new Array('peersDiv', 'chanCallDiv', 'debugMsg');
	for (i = 0; i < divs.length; i++)
	{
		if (divs[i] == div)
			$(divs[i]).style.display = 'block';
		else
			$(divs[i]).style.display = 'none';
	}
}

function showOptions(div, state)
{
	var divs = document.getElementsByTagName('div')
	for (i = 0; i < divs.length; i++)
	{
		if (divs[i].id.indexOf('peerOptions') != -1)
		{
			if (divs[i].id == div)
				divs[i].style.display = (state ? 'block' : 'none');
			else
				divs[i].style.display = 'none';
		}
	}
}

// Originate a Call
function originateCall(peer)
{
	var number = $('originateNum-' + peer).value;
	if (!number)
	{
		alert('Destination number not defined!');
		return false;
	}
	
	var ret = function(msg)
	{
		if (msg == 'OK')
			$('originateNum-' + peer).value = '';
	}
	
	var id = ajaxCall.init(false);
	ajaxCall.setResponseFunction(id, ret);
	ajaxCall.setURL(id, 'action.php');
	ajaxCall.addParam(id, 'action', 'OriginateCall:::' + peer + ':::' + number);
	ajaxCall.doCall(id);
}
function originateDial(src, dst)
{
	var id = ajaxCall.init(false);
	ajaxCall.setURL(id, 'action.php');
	ajaxCall.addParam(id, 'action', 'OriginateDial:::' + src + ':::' + dst);
	ajaxCall.doCall(id);
}

// Yahoo
function backToStartPosition(id)
{
	new YAHOO.util.Motion(  
		id, {  
			points: {
				to: ddDiv[id].startPos
			}
		},
		0.3,
		YAHOO.util.Easing.easeOut
	).animate();
}

function peerDrop(e, id) 
{
	var src = this.id.replace('peerDiv-', '');
	var dst = id.replace('peerDiv-', '');
	var c   = confirm('Originate a call from "' + src + '" to "' + dst + '"?');
	
	if (c)
		originateDial(this.id.replace('peerDiv-', ''), id.replace('peerDiv-', ''));
		
	backToStartPosition(this.id);
}
function peerIDrop(e)
{
	backToStartPosition(this.id);
}

