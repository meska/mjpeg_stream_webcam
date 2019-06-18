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

import cv2

from PIL import Image
from netifaces import ifaddresses, AF_INET

capture = None


class CamHandler(BaseHTTPRequestHandler):
    # noinspection PyPep8Naming
    def do_GET(self):
        if self.path.endswith('.mjpg'):
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
    parser.add_argument('-i', '--interface', help='network interface, default en0', type=str, default='en0')
    parser.add_argument('-s', '--size', help='set size', nargs=2, type=int, default=(320, 240))

    params = vars(parser.parse_args())
    params['size'] = (params['size'][0], params['size'][1])
    return params


def main():
    global capture

    params = handle_args()
    ip_addr = ifaddresses(params['interface'])[AF_INET][0]['addr']
    capture = cv2.VideoCapture(params['camera'])
    server = ThreadedHTTPServer((ip_addr, params['port']), CamHandler)

    try:
        print(f"Mjpeg server started on http://{ip_addr}:{params['port']}")
        server.serve_forever()
    except KeyboardInterrupt:
        capture.release()
        server.socket.close()


if __name__ == '__main__':
    main()
