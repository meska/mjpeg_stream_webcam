repeat
  try
    do shell script "cd ~/mjpeg_stream_webcam/ &&  ~/OctoPrint/venv/bin/python mjpegsw.py --camera 0 --port 5001 --ipaddres 10.0.1.2"
    delay 5
  on error errorMessage number errorNumber

  end try
end repeat
