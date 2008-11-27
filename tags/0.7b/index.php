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

require_once 'lib/include.php';

header("Cache-Control: no-cache, must-revalidate");
header("Pragma: no-cache");
header("Expires: -1");

session_start();
setValor('started', time());
setValor('Actions', array());
$sessionId = session_id();
session_write_close();

$json         = new Services_JSON(SERVICES_JSON_LOOSE_TYPE);
$template     = new TemplatePower('template/index.html');
$peerStatus   = array();
$channels     = array();
$calls        = array();
$meetmeRooms  = array();
$meetmeJoins  = array();
$parkedCalls  = array();
$queues       = array();
$queueParams  = array();
$queueMembers = array();
$queueClients = array();
$isStatus     = false;

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
					
				if (strpos($message, 'MeetmeCreate: ') === 0)
				    $meetmeRooms[] = substr($message, strlen('MeetmeCreate: '));
				    
				if (strpos($message, 'MeetmeJoin: ') === 0)
				    $meetmeJoins[] = substr($message, strlen('MeetmeJoin: '));
				    
				if (strpos($message, 'ParkedCall: ') === 0)
				    $parkedCalls[] = substr($message, strlen('ParkedCall: '));
				    
				if (strpos($message, 'Queue: ') === 0)
				    $queues[] = substr($message, strlen('Queue: '));
				    
				if (strpos($message, 'AddQueueMember: ') === 0)
				    $queueMembers[] = substr($message, strlen('AddQueueMember: '));
				    
				if (strpos($message, 'AddQueueClient: ') === 0)
				    $queueClients[] = substr($message, strlen('AddQueueClient: '));
				    
				if (strpos($message, 'QueueParams: ') === 0)
				    $queueParams[] = substr($message, strlen('QueueParams: '));
			}
		}
	}
}

fclose($fp);

$template->prepare();

$template->assign('MONAST_CALL_TIME', MONAST_CALL_TIME ? 'true' : 'false');

if (MONAST_CLI_TAB)
{
	$template->newBlock('cli_tab');
	$template->newBlock('cli_tab_div');
}

if (MONAST_DEBUG_TAB)
{
	$template->newBlock('debug_tab');
	$template->newBlock('debug_tab_div');
}

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
	$tmp = array
	(
		'Action' => 'MeetmeCreate',
		'Meetme' => $meetmeRoom
	);
	
	$template->newBlock('process');
	$template->assign('json', $json->encode($tmp));
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
	list($Source, $Destination, $CallerID, $CallerIDName, $CallerID2, $SrcUniqueID, $DestUniqueID, $Status, $Seconds) = explode(':::', $call);
	$tmp = array
	(
		'Action'       => 'Call',
		'Source'       => $Source, 
		'Destination'  => $Destination, 
		'CallerID'     => $CallerID, 
		'CallerIDName' => $CallerIDName, 
	    'CallerID2'    => $CallerID2,
		'SrcUniqueID'  => $SrcUniqueID, 
		'DestUniqueID' => $DestUniqueID, 
		'Status'       => $Status,
	    'Seconds'      => $Seconds
	);
	
	$template->newBlock('process');
	$template->assign('json', $json->encode($tmp));
}

foreach ($parkedCalls as $park)
{
	list($Exten, $Channel, $From, $Timeout, $CallerID, $CallerIDName) = explode(':::', $park);
	$tmp = array
	(
		'Action'       => 'ParkedCall',
		'Exten'        => $Exten, 
		'Channel'      => $Channel, 
		'From'         => $From, 
		'Timeout'      => $Timeout, 
	    'CallerID'     => $CallerID,
		'CallerIDName' => $CallerIDName, 
	);
	
	$template->newBlock('process');
	$template->assign('json', $json->encode($tmp));
}

foreach ($queues as $queue)
{
	$template->newBlock('queue');
	$template->assign('queue', $queue);
}

foreach ($queueMembers as $member)
{
	list($Queue, $Member, $MemberName, $Penalty, $CallsTaken, $LastCall, $Status, $Paused) = explode(':::', $member);
	$tmp = array
	(
		'Action'     => 'AddQueueMember',
		'Queue'      => $Queue,
		'Member'     => $Member,
		'MemberName' => $MemberName,
		'Penalty'    => $Penalty, 
		'CallsTaken' => $CallsTaken, 
		'LastCall'   => $LastCall, 
		'Status'     => $Status, 
		'Paused'     => $Paused
	);
	
	$template->newBlock('process');
	$template->assign('json', $json->encode($tmp));
}

foreach ($queueClients as $client)
{
	list($Queue, $Uniqueid, $Channel, $CallerID, $CallerIDName, $Position, $Count, $Wait) = explode(':::', $client);
	$tmp = array
	(
		'Action'       => 'AddQueueClient',
		'Queue'        => $Queue,
		'Uniqueid'     => $Uniqueid, 
		'Channel'      => $Channel, 
		'CallerID'     => $CallerID, 
		'CallerIDName' => $CallerIDName, 
		'Position'     => $Position, 
		'Count'        => $Count,
		'Wait'         => $Wait
	);
	
	$template->newBlock('process');
	$template->assign('json', $json->encode($tmp));
}

foreach ($queueParams as $params)
{
	list($Queue, $Max, $Calls, $Holdtime, $Completed, $Abandoned, $ServiceLevel, $ServicelevelPerf, $Weight) = explode(':::', $params);
	$tmp = array
	(
		'Action'           => 'QueueParams',
		'Queue'            => $Queue,
		'Max'              => $Max, 
		'Calls'            => $Calls, 
		'Holdtime'         => $Holdtime, 
		'Completed'        => $Completed, 
		'Abandoned'        => $Abandoned, 
		'ServiceLevel'     => $ServiceLevel,
		'ServicelevelPerf' => $ServicelevelPerf,
		'Weight'           => $Weight
	);
	
	$template->newBlock('process');
	$template->assign('json', $json->encode($tmp));
}

$template->printToScreen();

?>
