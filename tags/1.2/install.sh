#!/bin/bash

## default paths
MONASTPATH=/opt/monast
HTMLPATH=/var/www/html/monast
BINPATH=/usr/bin
CONFIGPATH=/etc
INITD=/etc/init.d

if [ "$(whoami)" != "root" ]; then
	echo -e "\nYou must be root to run this instalation script...\n"
	exit 1
fi

echo
echo -n "MonAst base path [${MONASTPATH}]: "
read tmp
if [ "${tmp}" != "" ]; then
	MONASTPATH=$tmp
fi

echo -n "MonAst HTML path [${HTMLPATH}]: "
read tmp
if [ "${tmp}" != "" ]; then
	HTMLPATH=$tmp
fi

inst=1
echo 
if [ -d $MONASTPATH ]; then
	echo -n "MonAst already instaled on this system. Overrite? [y/n]: "
	read tmp
	if [ "${tmp}" != "y" ]; then
		inst=0
	fi
fi
if [ $inst -eq 1 ]; then
	mkdir -p $MONASTPATH
	cp -rf pymon/. $MONASTPATH/
	echo "MonAst instaled at ${MONASTPATH}"
	
	mkdir -p $HTMLPATH
	cp -rf *.php css image template lib js $HTMLPATH/
	echo "HTML files instaled at ${HTMLPATH}"

	if [ ! -L $BINPATH/monast ]; then
		ln -s $MONASTPATH/monast.py $BINPATH/monast
		echo "Symbolic link to monast.py created at ${BINPATH}/monast"
	fi
	
	if [ ! -f /etc/monast.conf ]; then
		cp pymon/monast.conf.sample /etc/monast.conf
		echo "Sample monast.conf created at ${CONFIGPATH}/monast.conf"
	fi

	if [ -f /etc/slackware-version ]; then
		cp contrib/slackware/rc.monast /etc/rc.d/rc.monast
		echo "Instaling rc.d scripts"
	fi

	if [ -f /etc/redhat-release ]; then
		cp contrib/init.d/monast $INITD/monast
		echo "Instaling init.d scripts"
	fi
fi

echo

