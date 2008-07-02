<?php

function color($t)
{
    $t = strtolower($t);
    switch ($t)
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

function getValor($nome, $location = 'request')
{
	$location = '_' . strtoupper($location);
	eval("\$location = &$$location;");
	
	if (isset($location[$nome]))
	{
		return $location[$nome];
	}
	return '';	
}

function setValor($nome, $valor, $location = 'session')
{
	$location = '_' . strtoupper($location);
	eval("\$location = &$$location;");
	
	$location[$nome] = $valor;
}

?>