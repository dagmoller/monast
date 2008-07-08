
var json   = new JSON();
var ddDivs = new Array();

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
			
			ddDivs[o['Uniqueid']]               = new YAHOO.util.DD(o['Uniqueid']);
			ddDivs[o['Uniqueid']].onMouseDown   = setStartPosition;
			ddDivs[o['Uniqueid']].onDragDrop    = channelCallDrop;
			ddDivs[o['Uniqueid']].onInvalidDrop = invalidDrop;
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
		
		ddDivs[div.id]               = new YAHOO.util.DD(div.id);
		ddDivs[div.id].onMouseDown   = setStartPosition;
		ddDivs[div.id].onDragDrop    = channelCallDrop;
		ddDivs[div.id].onInvalidDrop = invalidDrop;

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
	
	if (o['Action'] == 'Rename')
	{
		td = $('channel-' + o['Uniqueid']);
		if (td)
			td.innerHTML = o['Newname'];
			
		td = $('callChannel-' + o['Uniqueid']);
		if (td)
			td.innerHTML = o['Newname'] + '<br>' + o['CallerIDName'] + ' <' + o['CallerID'] + '>';
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

// Originate a Call
function originateCall(peer, number)
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
		var id = ajaxCall.init(false);
		ajaxCall.setURL(id, 'action.php');
		ajaxCall.addParam(id, 'action', 'HangupChannel:::' + chanId);
		ajaxCall.doCall(id);
	}
}

// Transfer
function transferCall(src, dst, isPeer)
{
	if (isPeer)
	{
		var c = confirm("Transfer call to " + callerIDs[dst] + '?');
		if (!c)
			return;
	}
	var id = ajaxCall.init(false);
	ajaxCall.setURL(id, 'action.php');
	ajaxCall.addParam(id, 'action', 'TransferCall:::' + src + ':::' + dst + ':::' + (isPeer ? 'true' : 'false'));
	ajaxCall.doCall(id);
}

// Yahoo
function setStartPosition(e)
{
	ddDivs[this.id].startPos = YAHOO.util.Dom.getXY(YAHOO.util.Dom.get(this.id));
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
}

function peerDrop(e, id) 
{
	if (id.indexOf('peerDiv-') != -1)
	{
		var src = this.id.replace('peerDiv-', '');
		var dst = id.replace('peerDiv-', '');
		var c   = confirm('Originate a call from "' + callerIDs[src] + '" to "' + callerIDs[dst] + '"?');
		
		if (c)
			originateDial(this.id.replace('peerDiv-', ''), id.replace('peerDiv-', ''));
	}		
	backToStartPosition(this.id);
}

function channelCallDrop(e, id)
{
	if (id == 'trash')
		hangupCall(this.id);
		
	if (id.indexOf('peerDiv-') != -1 && this.id.indexOf('call-') == -1)
		transferCall(this.id, id.substring(8), true);
		
	if (id.indexOf('peerDiv-') != -1 && this.id.indexOf('call-') != -1)
	{
		var ids  = this.id.substring(5).split('-');
		var srcA = $('channel-' + ids[0]).innerHTML;
		var srcB = $('channel-' + ids[1]).innerHTML;
		showTransferDialog(ids[0], srcA, ids[1], srcB, id.substring(8));
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
	originateCall(this.peerId, $('originateNumber').value);
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
	
	transferCall(src, this.destChannel, true);
	this.hide();
}

function showTransferDialog(idA, srcA, idB, srcB, dst)
{
	$('transferDestination').innerHTML = callerIDs[dst];
	$('transferSourceValueA').value    = idA;
	$('transferSourceValueB').value    = idB;
	$('transferSourceValueA').checked  = true;
	$('transferSourceTextA').innerHTML = srcA; 
	$('transferSourceTextB').innerHTML = srcB;
	transferDialog.destChannel         = dst;
	transferDialog.render();
	transferDialog.show();
}
