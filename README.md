# mjpeg_stream_webcam
Webcam Streamer for Octoprint


I made this script for streaming an usb webcam to mjpeg suitable for OctoPrint on a mac, but it will probably work on
linux and windows too.


Tested on python 3.7

Installation:

clone the repository on your drive
create a virtualenv with python 3.7
install requirements with pip install -r requirements.txt
run the script with python mjpegsw.py

on octoprint you can use http://localhost:5001/cam.mjpg for stream url and http://localhost:5001/snap.jpg for snapshot url.



