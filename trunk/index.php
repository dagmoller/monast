<?php

require_once 'lib/include.php';

session_start();
setValor('started', time());
setValor('Action', '');
session_write_close();

$json       = new Services_JSON(SERVICES_JSON_LOOSE_TYPE);
$template   = new TemplatePower('template/index.html');
$sessionId  = session_id();
$peerStatus = array();
$channels   = array();
$calls      = array();
$isStatus   = false;

$errno  = null;
$errstr = null;
$fp     = @fsockopen(HOSTNAME, HOSTPORT, $errno, $errstr, 60);

if ($errstr)
{
	echo "<b>AstMon ERROR:</b> conectando a " . HOSTNAME . ":" . HOSTPORT . ": " . $errstr;
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
					$channels[] = $message;	

				if (strpos($message, 'Call: ') === 0)
					$calls[] = $message;
			}
		}
	}
}

fclose($fp);

$template->prepare();
foreach ($peerStatus as $idx => $peer)
{
    list($peer, $status, $peerCalls) = explode(':::', $peer);

    $template->newBlock('peer');
    $template->assign('peer', $peer);
    $template->assign('status', $status);
    $template->assign('status-color', color($status));
    $template->assign('calls', "$peerCalls call(s)");
    $template->assign('calls-color', ($peerCalls > 0 ? '#ffffb0' : '#b0ffb0'));
    
    $template->newBlock('peerOptions');
    $template->assign('peer', $peer);
    
    $template->newBlock('peerDragDrop');
    $template->assign('idx', $idx);
    $template->assign('peer', $peer);
}

foreach ($channels as $channel)
{
	$tmp = substr($channel, 12);
	list($Channel, $State, $CallerIDNum, $CallerIDName, $Uniqueid) = explode(':::', $tmp);
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
	$tmp = substr($call, 6);
	list($Source, $Destination, $CallerID, $CallerIDName, $SrcUniqueID, $DestUniqueID, $Status) = explode(':::', $tmp);
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