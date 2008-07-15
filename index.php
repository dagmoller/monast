<?php

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

require_once 'lib/include.php';

session_start();
setValor('started', time());
setValor('Actions', array());
session_write_close();

$json        = new Services_JSON(SERVICES_JSON_LOOSE_TYPE);
$template    = new TemplatePower('template/index.html');
$sessionId   = session_id();
$peerStatus  = array();
$channels    = array();
$calls       = array();
$meetmeRooms = array();
$meetmeJoins = array();
$isStatus    = false;

$errno  = null;
$errstr = null;
$fp     = @fsockopen(HOSTNAME, HOSTPORT, $errno, $errstr, 60);

if ($errstr)
{
	echo "<title>Monast Error</title>\n";
	echo "<h1>Monast Error</h1>\n<p>Could not connect to " . HOSTNAME . ":" . HOSTPORT . " (" . $errstr . ").</p>\n";
	echo "<p>Make sure monast.py is running so the panel can connect to its port properly.</p>";
	die;
}

fwrite($fp, "SESSION: $sessionId\r\n");

while (!feof($fp))
{
	$messages = fread($fp, 1024 * 64);
	$messages = explode("\r\n", $messages);
	
	foreach ($messages as $idx => $message)
	{
		if ($message)
		{
			if ($message == "NEW SESSION" || $message == "OK")
			{
				fwrite($fp, "GET STATUS\r\n");
			}
			elseif ($message == "BEGIN STATUS")
			{
				$isStatus = true;
			}
			elseif ($message == "END STATUS")
			{
				$isStatus = false;
				fwrite($fp, "BYE\r\n");
			}
			elseif ($isStatus)
			{
				if (strpos($message, 'PeerStatus: ') === 0)
					$peerStatus[] = substr($message, strlen('PeerStatus: '));

				if (strpos($message, 'NewChannel: ') === 0)
					$channels[] = substr($message, strlen('NewChannel: '));	

				if (strpos($message, 'Call: ') === 0)
					$calls[] = substr($message, strlen('Call: '));	
					
				if (strpos($message, 'MeetmeRoom: ') === 0)
				    $meetmeRooms[] = substr($message, strlen('MeetmeRoom: '));
				    
				if (strpos($message, 'MeetmeJoin: ') === 0)
				    $meetmeJoins[] = substr($message, strlen('MeetmeJoin: '));
			}
		}
	}
}

fclose($fp);

$template->prepare();
foreach ($peerStatus as $idx => $peer)
{
    list($peer, $status, $peerCalls, $CallerID) = explode(':::', $peer);

    $template->newBlock('peer');
    $template->assign('peer', $peer);
    $template->assign('CallerID', $CallerID);
    $template->assign('status', $status);
    $template->assign('status-color', color($status));
    $template->assign('calls', "$peerCalls call(s)");
    $template->assign('calls-color', ($peerCalls > 0 ? '#ffffb0' : '#b0ffb0'));
}

foreach ($meetmeRooms as $idx => $meetmeRoom)
{
    $template->newBlock('meetme');
    $template->assign('meetme', $meetmeRoom);
}

foreach ($meetmeJoins as $idx => $meetmeJoin)
{
    list($Meetme, $Uniqueid, $Usernum, $Channel, $CallerIDNum, $CallerIDName) = explode(':::', $meetmeJoin);
    $tmp = array
    (
        'Action'       => 'MeetmeJoin',
        'Meetme'       => $Meetme, 
        'Uniqueid'     => $Uniqueid, 
        'Usernum'      => $Usernum,
        'Channel'      => $Channel,
        'CallerIDNum'  => $CallerIDNum, 
        'CallerIDName' => $CallerIDName
    );
    
    $template->newBlock('process');
	$template->assign('json', $json->encode($tmp));
}

foreach ($channels as $channel)
{
	list($Channel, $State, $CallerIDNum, $CallerIDName, $Uniqueid) = explode(':::', $channel);
	$tmp = array
	(
		'Action'       => 'NewChannel',
		'Channel'      => $Channel, 
		'State'        => $State, 
		'CallerIDNum'  => $CallerIDNum, 
		'CallerIDName' => $CallerIDName, 
		'Uniqueid'     => $Uniqueid
	); 
	
	$template->newBlock('process');
	$template->assign('json', $json->encode($tmp));
}

foreach ($calls as $call)
{
	list($Source, $Destination, $CallerID, $CallerIDName, $SrcUniqueID, $DestUniqueID, $Status) = explode(':::', $call);
	$tmp = array
	(
		'Action'       => 'Call',
		'Source'       => $Source, 
		'Destination'  => $Destination, 
		'CallerID'     => $CallerID, 
		'CallerIDName' => $CallerIDName, 
		'SrcUniqueID'  => $SrcUniqueID, 
		'DestUniqueID' => $DestUniqueID, 
		'Status'       => $Status
	);
	
	$template->newBlock('process');
	$template->assign('json', $json->encode($tmp));
}

$template->printToScreen();

?>
