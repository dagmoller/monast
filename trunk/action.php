<?php

require_once 'lib/include.php';

$json   = new Services_JSON(SERVICES_JSON_LOOSE_TYPE);
$action = getValor('action');

session_start();
$actions   = getValor('Actions', 'session');
$actions[] = $action;
setValor('Actions', $actions);
session_write_close();

echo 'OK';

?>