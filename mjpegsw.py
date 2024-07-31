#!/usr/bin/python
"""
Author: Marco Mescalchin
Mjpg stream Server for Mac Webcam
"""
import argparse
import os
import signal
import threading
from io import BytesIO
from threading import Lock
from time import sleep

import cv2
from PIL import Image
from flask import Flask, Response, redirect, send_file, url_for

app = Flask(__name__)
img_lock = Lock()


class CameraControl:
    def __init__(self):
        self.capturing = True
        self.img = None
        self.lock = Lock()

    def stop_capturing(self):
        with self.lock:
            self.capturing = False

    def start_capturing(self):
        with self.lock:
            self.capturing = True

    def update_image(self, new_img):
        with self.lock:
            self.img = new_img

    def get_image(self):
        with self.lock:
            return self.img

    def is_capturing(self):
        with self.lock:
            return self.capturing


camera_control = CameraControl()


def signal_handler_sigint(signal_number, frame):
    print("Stopping camera ...")
    camera_control.stop_capturing()
    sleep(0.5)
    raise RuntimeError("SIGINT received")


signal.signal(signal.SIGINT, signal_handler_sigint)


class CamDaemon(threading.Thread):
    def __init__(
        self,
        camera_control,
        camera,
        capture_width,
        capture_height,
        capture_api,
        rotate_image=False,
        delay=0.2,
    ):
        threading.Thread.__init__(self)
        self.camera_control = camera_control
        self.camera = camera
        self.capture_width = capture_width
        self.capture_height = capture_height
        self.rotate_image = rotate_image
        self.capture_api = capture_api
        self.delay = delay

    def run(self):
        while self.camera_control.is_capturing():
            self.capture()
            sleep(5)
        # when cv2 crashes, it does not release the camera, so we need to exit
        os._exit(0)

    def capture(self):
        if self.capture_api and hasattr(cv2, self.capture_api):
            capture = cv2.VideoCapture(self.camera, getattr(cv2, self.capture_api))
        else:
            capture = cv2.VideoCapture(self.camera)
        if self.capture_width:
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.capture_width)
        if self.capture_height:
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.capture_height)
        capture.setExceptionMode(True)
        while self.camera_control.is_capturing():
            try:
                ret, frame = capture.read()
                if self.rotate_image:
                    frame = cv2.rotate(frame, cv2.ROTATE_180)
                if ret:
                    self.camera_control.update_image(frame)
                if self.delay > 0:
                    sleep(self.delay)
            except Exception as e:
                print("Error: " + str(e))
                self.camera_control.stop_capturing()
                break
        capture.release()


def create_stream_frame(camera_control):
    while True:
        img = camera_control.get_image()
        if img is not None:
            try:
                _, _buffer = cv2.imencode(".jpg", img)
                frame = _buffer.tobytes()
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")
            except Exception as e:
                print("Failed to encode image: " + str(e))
                continue
        sleep(0.1)


@app.route("/")
def hello_world():
    return redirect(url_for("video"))


@app.route("/cam.mjpg")
def video():
    return Response(
        create_stream_frame(camera_control),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/snap.jpg")
def snap():
    # check if camera is capturing and return an empty buffer if not instead of an error
    if not camera_control.is_capturing() or camera_control.img is None:
        return send_file(BytesIO(), download_name="snap.jpg", mimetype="image/jpeg")

    img_rgb = cv2.cvtColor(camera_control.img, cv2.COLOR_BGR2RGB)
    jpeg = Image.fromarray(img_rgb)
    buffer_file = BytesIO()
    jpeg.save(buffer_file, "JPEG")
    buffer_file.seek(0)

    return send_file(buffer_file, download_name="snap.jpg", mimetype="image/jpeg")


def handle_args():
    parser = argparse.ArgumentParser(
        description="Mjpeg streaming server: mjpegsw -p 8080 --camera 2"
    )
    parser.add_argument(
        "-p",
        "--port",
        help="http listening port, default 5001",
        type=int,
        default=5001,
    )
    parser.add_argument(
        "-c",
        "--camera",
        help="opencv camera number, ex. -c 1",
        type=int,
        default=0,
    )
    parser.add_argument(
        "-i",
        "--ipaddress",
        help="listening ip address, default all ips",
        type=str,
        default="127.0.0.1",
    )
    parser.add_argument(
        "-w",
        "--width",
        help="capture resolution width",
        type=int,
        required=False,
    )
    parser.add_argument(
        "-x",
        "--height",
        help="capture resolution height",
        type=int,
        required=False,
    )
    parser.add_argument(
        "-r",
        "--rotate",
        help="rotate image 180 degrees",
        action="store_true",
    )
    parser.add_argument(
        "-a",
        "--capture_api",
        help="specific api for capture",
        type=str,
        required=False,
    )
    parser.add_argument(
        "-d",
        "--delay",
        help="delay between captures (seconds)",
        type=float,
        required=False,
        default=1,
    )
    params = vars(parser.parse_args())
    return params


def main():
    params = handle_args()
    if params["height"]:
        print("Image height set to: " + str(params["height"]))
    if params["width"]:
        print("Image width set to: " + str(params["width"]))
    if params["rotate"]:
        print("Image will be rotated 180 degrees")
    if params["capture_api"]:
        print("Will be used capture api: " + params["capture_api"])
    if params["delay"] > 0:
        print(
            "Will be used delay between captures: " + str(params["delay"]) + " seconds"
        )
    # starts camera daemon thread
    camera = CamDaemon(
        camera_control,
        params["camera"],
        params["width"],
        params["height"],
        params["capture_api"],
        params["rotate"],
        params["delay"],
    )
    camera.daemon = True
    camera.start()
    try:
        # starts flask server
        app.run(host=params["ipaddress"], port=params["port"], debug=False)
    except RuntimeError:
        print("Stopping mjpeg server ...")
        camera.join()


if __name__ == "__main__":
    main()
