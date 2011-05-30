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

define("HOSTNAME", "localhost"); // monast.py hostname
define("HOSTPORT", 5039); // monast.py port

define("MONAST_SOCKET_DURATION", 20); // 20 seconds
define("MONAST_BROWSER_REFRESH", 60 * 10); // 10 minutes

define("MONAST_CALL_TIME", true); // enable or disable call timer

define("MONAST_BLINK_ONCHANGE", true); // enable or disable blinking status changes
define("MONAST_BLINK_COUNT", 3); // Number of blinks
define("MONAST_BLINK_INTERVAL", 200); // interval of blinks (in miliseconds)

define("MONAST_KEEP_CALLS_SORTED", true); // Keep calls sorted by link duration (this cause browser to consume more CPU)
define("MONAST_KEEP_PARKEDCALLS_SORTED", true); // Keep parked calls sorted by exten (this cause browser to consume more CPU)

define("MONAST_CLI_TAB", true); // enable or disable Asterisk CLI TAB
define("MONAST_DEBUG_TAB", false); // enable or disable debug TAB

// DOES NOT EDIT THIS LINE
session_name("MONASTSESSID");

?>
