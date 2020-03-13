#!/bin/bash
while :
do
	echo "Press [CTRL+C] to stop.."
	.env/bin/python mjpegsw.py
	sleep 1
done
