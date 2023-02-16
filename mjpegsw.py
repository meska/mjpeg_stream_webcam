#!/usr/bin/python
"""
Author: Marco Mescalchin
Mjpg stream Server for Mac Webcam
"""
import argparse
from flask import Flask, send_file, Response
import cv2
from io import BytesIO
from PIL import Image

app = Flask(__name__)

# Define the camera here
capture = None


def createStreamFrame():
    while True:
        success, frame = capture.read()  # read the camera frame
        if not success:
            break
        else:
            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')  # concat frame one by one and show result


@app.route("/")
def hello_world():
    return "<p>Hello, World!</p>"


@app.route("/snap.jpg")
def snap():
    try:
        success, frame = capture.read()
        if not success:
            return 500

        imgRgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        jpeg = Image.fromarray(imgRgb)
        bufferFile = BytesIO()
        jpeg.save(bufferFile, 'JPEG')
        bufferFile.seek(0)

        return send_file(
            bufferFile,
            download_name='snap.jpg',
            mimetype='image/jpeg'
        )
    except (BrokenPipeError, OSError):
        pass
    return


@app.route("/cam.mjpg")
def video():
    return Response(createStreamFrame(), mimetype='multipart/x-mixed-replace; boundary=frame')


def handle_args():
    parser = argparse.ArgumentParser(
        description='Mjpeg streaming server: mjpegsw -p 8080 --camera 2')
    parser.add_argument(
        '-p', '--port', help='http listening port, default 5001', type=int, default=5001)
    parser.add_argument(
        '-c', '--camera', help='opencv camera number, ex. -c 1', type=int, default=0)
    parser.add_argument('-i', '--ipaddress', help='listening ip address, default all ips', type=str,
                        default='127.0.0.1')
    params = vars(parser.parse_args())
    return params


def main():
    global capture
    params = handle_args()

    try:
        capture = cv2.VideoCapture(params['camera'])
        # Start the flask server
        app.run(host=params['ipaddress'], port=params['port'], debug=False)

    except KeyboardInterrupt:
        capture.release()


if __name__ == '__main__':
    main()
