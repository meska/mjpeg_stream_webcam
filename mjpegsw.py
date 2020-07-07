#!/usr/bin/python
"""
Author: Marco Mescalchin
Mjpg stream Server for Mac Webcam
"""
import argparse
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO
from socketserver import ThreadingMixIn
import sys
import logging

import cv2

from PIL import Image

capture = None

file_handler = logging.FileHandler(filename='logs.debug', mode='w')
stdout_handler = logging.StreamHandler(sys.stdout)
handlers = [file_handler, stdout_handler]

logging.basicConfig(
    level=logging.DEBUG, 
    format='%(asctime)s - %(levelname)s - %(module)s - line %(lineno)d - %(message)s',
    handlers=handlers
)


class CamHandler(BaseHTTPRequestHandler):
    # noinspection PyPep8Naming
    def do_GET(self):
        logger = logging.getLogger()
        if self.path == '/favicon.ico':
            return
        logger.debug(f"{self.path}")
        if '.mjpg' in self.path.lower():
            # send video stream
            self.send_response(200)
            self.send_header('Content-type', 'multipart/x-mixed-replace; boundary=--jpgboundary')
            self.end_headers()
            while True:
                try:
                    rc, img = capture.read()
                    if not rc:
                        continue
                    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    jpg = Image.fromarray(img_rgb)
                    tmp_file = BytesIO()
                    jpg.save(tmp_file, 'JPEG')
                    self.wfile.write(b"--jpgboundary")
                    self.end_headers()
                    self.send_header('Content-type', 'image/jpeg')
                    self.send_header('X-Timestamp', time.time())
                    self.send_header('Content-length', str(tmp_file.tell()))
                    self.end_headers()
                    tmp_file.seek(0)
                    self.wfile.write(tmp_file.read())
                except KeyboardInterrupt:
                    break
                except (BrokenPipeError, OSError):
                    pass
            return
        if '.jpg' in self.path.lower():
            # send snapshot
            try:
                rc, img = capture.read()
                if not rc:
                    self.send_response(500)
                    return

                img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                jpg = Image.fromarray(img_rgb)
                tmp_file = BytesIO()
                jpg.save(tmp_file, 'JPEG')

                self.send_response(200)
                self.send_header('Content-type', 'image/jpeg')
                self.send_header('X-Timestamp', time.time())
                self.send_header('Content-length', str(tmp_file.tell()))
                self.end_headers()
                tmp_file.seek(0)
                self.wfile.write(tmp_file.read())
            except (BrokenPipeError, OSError):
                pass
            return
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b'<html><head></head><body>')
            self.wfile.write(b'<img src="/cam.mjpg"/>')
            self.wfile.write(b'</body></html>')
            return


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread."""


def handle_args():
    parser = argparse.ArgumentParser(description='Mjpeg streaming server: mjpegsw -p 8080 --camera 2')
    parser.add_argument('-p', '--port', help='http listening port, default 5001', type=int, default=5001)
    parser.add_argument('-c', '--camera', help='opencv camera number, ex. -c 1', type=int, default=0)
    parser.add_argument('-i', '--ipaddress', help='listening ip address, default all ips', type=str,
                        default='0.0.0.0')
    parser.add_argument('-l', '--height', help='Height resolution for mjpeg streaming server, default to 1280', 
                        type=int, default=1280)
    parser.add_argument('-w', '--width', help='Width resolution for mjpeg streaming server, default to 720', 
                        type=int, default=720)
    parser.add_argument('-f', '--fps', help='fps for the streaming server, default to 60', 
                        type=int, default=60)
    params = vars(parser.parse_args())
    return params


def main():
    global capture

    params = handle_args()
    capture = cv2.VideoCapture(params['camera'])
    capture.set(cv2.CAP_PROP_FPS, params['fps'])
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, params['width'])
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, params['height'])
    
    server = ThreadedHTTPServer((params['ipaddress'], params['port']), CamHandler)
    logger = logging.getLogger()

    try:
        logger.debug(f"Mjpeg server started on http://{params['ipaddress']}:{params['port']}")
        server.serve_forever()
    except KeyboardInterrupt:
        capture.release()
        server.socket.close()


if __name__ == '__main__':
    main()
