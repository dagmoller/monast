<?php

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
		list($Channel1, $Channel2, $Uniqueid1, $Uniqueid2, $CallerID1, $CallerID2) = explode(':::', substr($msg, 6));
		$saida = array
		(
			'Action'    => 'Link',
			'Channel1'  => $Channel1, 
			'Channel2'  => $Channel2, 
			'Uniqueid1' => $Uniqueid1, 
			'Uniqueid2' => $Uniqueid2, 
			'CallerID1' => $CallerID1, 
			'CallerID2' => $CallerID2
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
	
	return $json->encode(array('Action' => 'None'));
}

session_start();
$sessid = session_id();
session_write_close();

$timeout = 20;
$refresh = 60 * 10;
$inicio  = time();

$errno  = null;
$errstr = null;
$fp     = @fsockopen(HOSTNAME, HOSTPORT, $errno, $errstr, 60);

if ($errstr)
{
	echo "<script>alert('AstMon ERROR: conectando a " . HOSTNAME . ":" . HOSTPORT . ": " . $errstr . "');</script>";
	die;
}

fwrite($fp, "SESSION: $sessid\r\n");

$isStatus = false;
$isOK     = false;
$hasMsg   = array();

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
	
	if ($hasMsg)
	{
		$hasMsg = false;
		usleep(100);
		print str_pad('', 4096);
		ob_flush();
		flush();
	}
	
	session_start();
	$action = getValor('Action', 'session');
	if ($action)
	{
	    fwrite($fp, "$action\r\n");
	    setValor('Action', '');
	}
	session_write_close();
	
	$now = time();
	if ($now >= ($inicio + $timeout) && !$isStatus && $isOK)
	{
		$isOK = false;
		fwrite($fp, "BYE\r\n");
		
		if ($now >= (getValor('started', 'session') + $refresh))
			print "<script>parent.location.reload();</script>";
		else		
			print "<script>parent.startIFrame();</script>\r\n";
			
		ob_flush();
		flush();
		break;
	}
}

fclose($fp);

?>