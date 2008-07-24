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

ini_set('error_reporting', 'E_ALL & ~E_NOTICE & ~E_WARNING');

set_time_limit(0);

require_once 'lib/include.php';

$json = new Services_JSON(SERVICES_JSON_LOOSE_TYPE);

function parseMsg($msg)
{
	global $json;
	
	if (strpos($msg, 'PeerStatus: ') !== false)
	{
		list($Peer, $Status, $Calls) = explode(':::', substr($msg, 12));
		$saida = array
		(
			'Action' => 'PeerStatus',
			'Peer'   => $Peer,
			'Status' => $Status,
			'Calls'  => $Calls
		);
		return $json->encode($saida);
	}
	
	if (strpos($msg, 'NewChannel: ') !== false)
	{	
		list($Channel, $State, $CallerIDNum, $CallerIDName, $Uniqueid) = explode(':::', substr($msg, 12));
		$saida = array
		(
			'Action'       => 'NewChannel',
			'Channel'      => $Channel, 
			'State'        => $State, 
			'CallerIDNum'  => $CallerIDNum, 
			'CallerIDName' => $CallerIDName, 
			'Uniqueid'     => $Uniqueid
		);
		return $json->encode($saida);
	}
	
	if (strpos($msg, 'NewState: ') !== false)
	{	
		list($Channel, $State, $CallerID, $CallerIDName, $Uniqueid) = explode(':::', substr($msg, 10));
		$saida = array
		(
			'Action'       => 'NewState',
			'Channel'      => $Channel, 
			'State'        => $State, 
			'CallerID'     => $CallerID, 
			'CallerIDName' => $CallerIDName, 
			'Uniqueid'     => $Uniqueid
		);
		return $json->encode($saida);
	}
	
	if (strpos($msg, 'Hangup: ') !== false)
	{	
		list($Channel, $Uniqueid, $Cause, $Cause_txt) = explode(':::', substr($msg, 8));
		$saida = array
		(
			'Action'    => 'Hangup',
			'Channel'   => $Channel, 
			'Uniqueid'  => $Uniqueid, 
			'Cause'     => $Cause, 
			'Cause_txt' => $Cause_txt
		);
		return $json->encode($saida);
	}
	
	if (strpos($msg, 'Dial: ') !== false)
	{	
		list($Source, $Destination, $CallerID, $CallerIDName, $SrcUniqueID, $DestUniqueID) = explode(':::', substr($msg, 6));
		$saida = array
		(
			'Action'       => 'Dial',
			'Source'       => $Source, 
			'Destination'  => $Destination, 
			'CallerID'     => $CallerID, 
			'CallerIDName' => $CallerIDName, 
			'SrcUniqueID'  => $SrcUniqueID, 
			'DestUniqueID' => $DestUniqueID
		);
		return $json->encode($saida);
	}
	
	if (strpos($msg, 'Link: ') !== false)
	{	
		list($Channel1, $Channel2, $Uniqueid1, $Uniqueid2, $CallerID1, $CallerID2, $Seconds) = explode(':::', substr($msg, 6));
		$saida = array
		(
			'Action'    => 'Link',
			'Channel1'  => $Channel1, 
			'Channel2'  => $Channel2, 
			'Uniqueid1' => $Uniqueid1, 
			'Uniqueid2' => $Uniqueid2, 
			'CallerID1' => $CallerID1, 
			'CallerID2' => $CallerID2,
		    'Seconds'   => $Seconds
		);
		return $json->encode($saida);
	}
	
	if (strpos($msg, 'Unlink: ') !== false)
	{	
		list($Channel1, $Channel2, $Uniqueid1, $Uniqueid2, $CallerID1, $CallerID2) = explode(':::', substr($msg, 8));
		$saida = array
		(
			'Action'    => 'Unlink',
			'Channel1'  => $Channel1, 
			'Channel2'  => $Channel2, 
			'Uniqueid1' => $Uniqueid1, 
			'Uniqueid2' => $Uniqueid2, 
			'CallerID1' => $CallerID1, 
			'CallerID2' => $CallerID2
		);
		return $json->encode($saida);
	}
	
	if (strpos($msg, 'NewCallerid: ') !== false)
	{	
		list($Channel, $CallerID, $CallerIDName, $Uniqueid, $CIDCallingPres) = explode(':::', substr($msg, 13));
		$saida = array
		(
			'Action'         => 'NewCallerid',
			'Channel'        => $Channel, 
			'CallerID'       => $CallerID, 
			'CallerIDName'   => $CallerIDName,
			'Uniqueid'       => $Uniqueid,
			'CIDCallingPres' => $CIDCallingPres
		);
		return $json->encode($saida);
	}
	
    if (strpos($msg, 'Rename: ') !== false)
	{	
		list($Oldname, $Newname, $Uniqueid, $CallerIDName, $CallerID) = explode(':::', substr($msg, 8));
		$saida = array
		(
			'Action'       => 'Rename',
			'Oldname'      => $Oldname, 
			'Newname'      => $Newname, 
			'Uniqueid'     => $Uniqueid,
		    'CallerIDName' => $CallerIDName,
			'CallerID'     => $CallerID, 
		);
		return $json->encode($saida);
	}
	
	if (strpos($msg, 'MeetmeJoin: ') !== false)
	{
	    list($Meetme, $Uniqueid, $Usernum, $Channel, $CallerIDNum, $CallerIDName) = explode(':::', substr($msg, 12));
        $saida = array
        (
            'Action'       => 'MeetmeJoin',
            'Meetme'       => $Meetme, 
            'Uniqueid'     => $Uniqueid, 
            'Usernum'      => $Usernum,
            'Channel'      => $Channel,
            'CallerIDNum'  => $CallerIDNum, 
            'CallerIDName' => $CallerIDName
        );
    	return $json->encode($saida);
	}
	
    if (strpos($msg, 'MeetmeLeave: ') !== false)
	{
	    list($Meetme, $Uniqueid, $Usernum, $Duration) = explode(':::', substr($msg, 13));
        $saida = array
        (
            'Action'       => 'MeetmeLeave',
            'Meetme'       => $Meetme, 
            'Uniqueid'     => $Uniqueid, 
            'Usernum'      => $Usernum, 
            'Duration'     => $Duration 
        );
    	return $json->encode($saida);
	}
	
	if (strpos($msg, 'ParkedCall: ') !== false)
	{
	    list($Exten, $Channel, $From, $Timeout, $CallerID, $CallerIDName) = explode(':::', substr($msg, 12));
    	$saida = array
    	(
    		'Action'       => 'ParkedCall',
    		'Exten'        => $Exten, 
    		'Channel'      => $Channel, 
    		'From'         => $From, 
    		'Timeout'      => $Timeout, 
    	    'CallerID'     => $CallerID,
    		'CallerIDName' => $CallerIDName, 
    	);
    	return $json->encode($saida);
	}
	
    if (strpos($msg, 'UnparkedCall: ') !== false)
	{
	    list($Exten) = explode(':::', substr($msg, 14));
    	$saida = array
    	(
    		'Action'       => 'UnparkedCall',
    		'Exten'        => $Exten, 
    	);
    	return $json->encode($saida);
	}
	
	return $json->encode(array('Action' => 'None'));
}

session_start();
$sessid = session_id();
session_write_close();

$inicio = time();

$errno  = null;
$errstr = null;
$fp     = @fsockopen(HOSTNAME, HOSTPORT, $errno, $errstr, 60);

if ($errstr)
{
    $error  = "!! MonAst ERROR !!\\n\\nCould not connect to " . HOSTNAME . ":" . HOSTPORT . ": $errstr\\n";
    $error .= "Make sure monast.py is running so the panel can connect to its port properly.";
	echo "<script>alert('$error');</script>";
	die;
}

fwrite($fp, "SESSION: $sessid\r\n");

$isStatus = false;
$isOK     = false;
$hasMsg   = array();
$reload   = false;

while (!feof($fp))
{
	if ($isOK && !$isStatus)
	{
		fwrite($fp, "GET CHANGES\r\n");
		sleep(1);
	}
	
	$messages = fread($fp, 1024 * 64);
	$messages = explode("\r\n", $messages);
	
	foreach ($messages as $idx => $message)
	{
		if ($message)
		{
			if ($message == "OK")
			{
				fwrite($fp, "GET CHANGES\r\n");
				$isOK = true;
			}
			elseif ($message == "BEGIN CHANGES")
			{
				$isStatus = true;
			}
			elseif ($message == "END CHANGES")
			{
				$isStatus = false;
			}
			elseif (strpos($message, 'Reload: ') !== false)
			{
           	    $time = substr($message, 8);
            	$saida = array
        	    (
        	        'Action' => 'Reload',
        	        'time'   => ($time * 1000)
        	    );
        	    print "<script>parent.Process('" . $json->encode($saida) . "');</script>\r\n";
        	    $reload = true;
        	    break;
			}
			elseif ($isStatus)
			{
				$hasMsg = true;
				print "<script>parent.Process('" . parseMsg($message) . "');</script>\r\n";
				//print parseMsg($message);
				ob_flush();
				flush();
			}
		}
	}
	
	if ($reload)
	{
	    fwrite($fp, "BYE\r\n");
	    break;
	}
	
	if ($hasMsg)
	{
		$hasMsg = false;
		usleep(100);
		print str_pad('', 4096);
		ob_flush();
		flush();
	}
	
	session_start();
	$actions = getValor('Actions', 'session');
	if (count($actions) > 0)
	{
	    foreach ($actions as $action)
	    {
	        fwrite($fp, "$action\r\n");
	    }
	    setValor('Actions', array());
	}
	session_write_close();
	
	$now = time();
	if ($now >= ($inicio + MONAST_SOCKET_DURATION) && !$isStatus && $isOK)
	{
		$isOK = false;
		fwrite($fp, "BYE\r\n");
		
		if ($now >= (getValor('started', 'session') + MONAST_BROWSER_REFRESH))
			print "<script>parent.location.href = 'index.php';</script>";
		else		
			print "<script>parent.startIFrame();</script>\r\n";
			
		ob_flush();
		flush();
		break;
	}
}

fclose($fp);

?>
