#!/usr/bin/python -u

import os

srcpath = '/home/aguirre/Downloads/yui-2.9.0'
dstpath = '/home/aguirre/public_html/monast/lib/yui-2.9.0'

files = [
	## CSS
	'build/fonts/fonts-min.css', 
	'build/container/assets/skins/sam/container.css', 
	'build/menu/assets/skins/sam/menu.css', 
	'build/button/assets/skins/sam/button.css', 
	'build/tabview/assets/skins/sam/tabview.css',
	
	## JS
	'build/yahoo/yahoo-min.js', 
	'build/dom/dom-min.js', 
	'build/event/event-min.js', 
	'build/animation/animation-min.js', 
	'build/dragdrop/dragdrop-min.js', 
	'build/container/container-min.js', 
	'build/menu/menu-min.js', 
	'build/element/element-min.js', 
	'build/button/button-min.js', 
	'build/cookie/cookie-min.js', 
	'build/tabview/tabview-min.js',
	
	## Extras
	'build/assets/skins/sam/sprite.png',
	'build/menu/assets/skins/sam/menuitem_submenuindicator.png',
]

for file in files:
	destdir  = '%s/%s' % (dstpath, file[:file.rfind('/')])
	destfile = file[file.rfind('/'):]
	
	if not os.path.exists(destdir):
		os.makedirs(destdir)
		
	# copy files
	cmd = 'cp "%s/%s" "%s/%s"' % (srcpath, file, dstpath, file)
	print cmd
	os.popen(cmd).read()
	
	# copy images
	#origem = '%s/%s' % (srcpath, file[:file.find('/')])
	#for root, dirs, files in os.walk(origem):
		#for f in files:
			#if f.find('.png') != -1 or f.find('.gif') != -1:
				#print f
	
