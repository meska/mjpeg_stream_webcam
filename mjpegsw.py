import argparse
import os
import signal
import threading
from io import BytesIO
from threading import Lock
from time import sleep

import imageio
import numpy as np
import psutil
from PIL import Image
from flask import Flask, Response, redirect, send_file, url_for

app = Flask(__name__)
img_lock = Lock()


class CameraControl:
    def __init__(self):
        self.capturing = True
        self.img = None
        self.lock = Lock()
        self.stuck = False
        self.width = None
        self.height = None
        self.rotate_image = False

    def set_rotate_image(self, rotate_image):
        with self.lock:
            self.rotate_image = rotate_image

    def get_rotate_image(self):
        with self.lock:
            return self.rotate_image

    def set_resolution(self, width, height):
        with self.lock:
            self.width = width
            self.height = height

    def get_resolution(self):
        with self.lock:
            return self.width, self.height

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

    def set_stuck(self, stuck):
        with self.lock:
            self.stuck = stuck

    def is_stuck(self):
        with self.lock:
            return self.stuck


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
        camera_control_obj,
        camera,
        capture_width,
        capture_height,
        rotate_image=False,
        delay=0.2,
    ):
        threading.Thread.__init__(self)
        self.camera_control = camera_control_obj
        self.camera = camera
        self.capture_width = capture_width
        self.capture_height = capture_height
        self.rotate_image = rotate_image
        self.delay = delay
        self.reader = None
        self.camera_control.set_resolution(capture_width, capture_height)
        self.camera_control.set_rotate_image(rotate_image)

    def run(self):
        while self.camera_control.is_capturing():
            self.capture()
            sleep(5)
        os._exit(0)

    @staticmethod
    def get_ffmpeg_processes():
        return [
            p
            for p in psutil.process_iter(["pid", "name"])
            if "ffmpeg" in p.info["name"].lower()
        ]

    def get_ffmpeg_pid(self, others):
        ffmpeg_pid = None
        for proc in self.get_ffmpeg_processes():
            if proc.info["pid"] not in [p.info["pid"] for p in others]:
                ffmpeg_pid = proc.info["pid"]
                break
        return ffmpeg_pid

    @staticmethod
    def kill_ffmpeg(ffmpeg_pid=None):
        if ffmpeg_pid:
            os.kill(ffmpeg_pid, signal.SIGKILL)
        else:
            other_pid = None
            for proc in psutil.process_iter(["pid", "name"]):
                if "ffmpeg" in proc.info["name"].lower():
                    other_pid = proc.info["pid"]
                    break
            if other_pid:
                os.kill(ffmpeg_pid, signal.SIGKILL)

    def capture(self):
        previous_frame = None
        same_frame_count = 0
        # same frame limit depends on the delay if no delay is set, limit is 5000 frames
        # 25 frames per second * 5 seconds = 125 frames
        if self.delay > 0:
            same_frame_limit = 25 * self.delay * 5
        else:
            same_frame_limit = 5000

        while self.camera_control.is_capturing():
            try:
                # to not kill other ffmpeg processes opened by other applications
                ffmpeg_processes = self.get_ffmpeg_processes()

                self.reader = imageio.get_reader(f"<video{self.camera}>")
                self.camera_control.set_stuck(False)

                # wait for new ffmpeg process to start from imageio
                while len(self.get_ffmpeg_processes()) == len(ffmpeg_processes):
                    sleep(0.1)

                # store the pid of the current ffmpeg process
                ffmpeg_pid = self.get_ffmpeg_pid(ffmpeg_processes)

                while self.camera_control.is_capturing():
                    try:
                        frame = self.reader.get_next_data()
                        if previous_frame is not None and np.array_equal(
                            frame, previous_frame
                        ):
                            same_frame_count += 1
                            if same_frame_count > same_frame_limit:
                                print(
                                    f"More than {same_frame_limit} frames"
                                    f"are the same as previous. "
                                    "Assuming the stream is stuck. "
                                    "Reopening reader after 5 seconds."
                                )
                                self.camera_control.set_stuck(True)
                                self.kill_ffmpeg(ffmpeg_pid)
                                self.reader.close()
                                sleep(5)
                                # start a new reader
                                ffmpeg_processes = self.get_ffmpeg_processes()

                                self.reader = imageio.get_reader(
                                    f"<video{self.camera}>"
                                )
                                while len(self.get_ffmpeg_processes()) == len(
                                    ffmpeg_processes
                                ):
                                    sleep(0.1)
                                ffmpeg_pid = self.get_ffmpeg_pid(ffmpeg_processes)
                                same_frame_count = 0
                                self.camera_control.set_stuck(False)
                                continue
                        else:
                            same_frame_count = 0
                        previous_frame = frame

                        if self.rotate_image:
                            frame = frame[::-1, ::-1]
                        self.camera_control.update_image(frame)

                        if self.delay > 0:
                            sleep(self.delay)

                    except Exception as e:
                        print("Error capturing frame: " + str(e))
                        break
                self.reader.close()
            except Exception as e:
                print("Error opening video device: " + str(e))
                sleep(5)


def create_stream_frame(cam_control):
    while True:
        img = cam_control.get_image()
        stuck = cam_control.is_stuck()
        width, height = cam_control.get_resolution()
        rotate = cam_control.get_rotate_image()
        if img is not None and not stuck:
            try:
                img = Image.fromarray(img)

                if width and height:
                    img.thumbnail((width, height))

                if rotate:
                    img.rotate(180)

                buffer = BytesIO()
                img.save(buffer, format="JPEG")
                frame = buffer.getvalue()
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
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
    if not camera_control.is_capturing() or camera_control.img is None:
        return send_file(BytesIO(), download_name="snap.jpg", mimetype="image/jpeg")

    img_rgb = camera_control.img
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
        help="camera number, ex. -c 1",
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
        "-d",
        "--delay",
        help="delay between captures (seconds)",
        type=float,
        required=False,
        default=0,
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
    if params["delay"] > 0:
        print(
            "Will be used delay between captures: " + str(params["delay"]) + " seconds"
        )
    camera = CamDaemon(
        camera_control,
        params["camera"],
        params["width"],
        params["height"],
        params["rotate"],
        params["delay"],
    )
    camera.daemon = True
    camera.start()
    try:
        app.run(host=params["ipaddress"], port=params["port"], debug=False)
    except RuntimeError:
        print("Stopping mjpeg server ...")
        camera.join()


if __name__ == "__main__":
    main()
