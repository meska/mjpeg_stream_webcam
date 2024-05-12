#!/usr/bin/python
"""
Author: Marco Mescalchin
Mjpg stream Server for Mac Webcam
"""
import argparse
from time import sleep
import signal

from flask import Flask, redirect, send_file, Response, url_for
import cv2
from io import BytesIO
from PIL import Image
import threading

app = Flask(__name__)
img = []
capturing = True


# noinspection PyUnusedLocal
def signal_handler_sigint(signal_number, frame):
    print("Stopping camera ...")
    global capturing
    capturing = False
    sleep(0.5)
    raise RuntimeError("SIGINT received")


signal.signal(signal.SIGINT, signal_handler_sigint)


class CamDaemon(threading.Thread):
    def __init__(self, camera, capture_width, capture_height, rotate_image=False):
        threading.Thread.__init__(self)
        self.camera = camera
        self.capture_width = capture_width
        self.capture_height = capture_height
        self.rotate_image = rotate_image

    def run(self):
        global img
        global capturing

        # capture = cv2.VideoCapture(self.camera, cv2.CAP_V4L2) # TODO: put it in options, if needed
        capture = cv2.VideoCapture(self.camera)
        if self.capture_width:
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.capture_width)
        if self.capture_height:
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.capture_height)
        y = 0
        while capturing:
            ret, frame = capture.read()
            if self.rotate_image:
                frame = cv2.rotate(frame, cv2.ROTATE_180)
            if ret:
                img = frame
            else:
                y += 1
                if y > 5:
                    print("Camera Error")
                    y = 0
        capture.release()


def create_stream_frame():
    while True:
        ret, _buffer = cv2.imencode('.jpg', img)
        frame = _buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')  # concat frame one by one and show result


@app.route("/")
def hello_world():
    return redirect(url_for('video'))


@app.route("/snap.jpg")
def snap():
    try:
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        jpeg = Image.fromarray(img_rgb)
        buffer_file = BytesIO()
        jpeg.save(buffer_file, 'JPEG')
        buffer_file.seek(0)

        return send_file(
            buffer_file,
            download_name='snap.jpg',
            mimetype='image/jpeg'
        )
    except OSError:
        pass


@app.route("/cam.mjpg")
def video():
    return Response(create_stream_frame(), mimetype='multipart/x-mixed-replace; boundary=frame')


def handle_args():
    parser = argparse.ArgumentParser(
        description='Mjpeg streaming server: mjpegsw -p 8080 --camera 2')
    parser.add_argument(
        '-p', '--port', help='http listening port, default 5001', type=int, default=5001)
    parser.add_argument(
        '-c', '--camera', help='opencv camera number, ex. -c 1', type=int, default=0)
    parser.add_argument('-i', '--ipaddress', help='listening ip address, default all ips', type=str,
                        default='127.0.0.1')
    parser.add_argument('-w', '--width', help='capture resolution width', type=int, required=False)
    parser.add_argument('-x', '--height', help='capture resolution height', type=int, required=False)
    parser.add_argument('-r', '--rotate', help='rotate image 180 degrees', action='store_true')
    params = vars(parser.parse_args())
    return params


def main():
    params = handle_args()
    if params['height']:
        print("Image height set to: " + str(params['height']))
    if params['width']:
        print("Image width set to: " + str(params['width']))
    if params['rotate']:
        print("Image will be rotated 180 degrees")
    # starts camera daemon thread
    camera = CamDaemon(params['camera'], params['width'], params['height'], params['rotate'])
    camera.daemon = True
    camera.start()
    try:
        # starts flask server
        app.run(host=params['ipaddress'], port=params['port'], debug=False)
    except RuntimeError:
        print("Stopping mjpeg server ...")
        camera.join()


if __name__ == '__main__':
    main()
