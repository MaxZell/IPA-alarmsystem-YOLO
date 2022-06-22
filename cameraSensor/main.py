import cv2 as cv
import numpy as np
import os
import ast
import time
import imutils
import datetime
import json
import redis
import base64
import logging
import logging.handlers as handlers
from pathlib import Path

"""
yalo.cfg file
channels=1 -> grayscale
channels=3 -> color
"""

# check configuration file
if os.path.exists(Path.cwd() / 'config.json'):
    # read configurations
    with open(Path.cwd() / 'config.json', 'r') as c:
        settings = json.load(c)
else:
    print("Configuration file doesn't exist!")

# logger
logger = logging.getLogger(settings["Application"]["name"])
logger.setLevel(settings["Logging"]["level"])
formatter = logging.Formatter(settings["Logging"]["format"], style='{')
# create logs dir if not exist
if not os.path.exists(Path.cwd() / 'logs'):
    os.makedirs(Path.cwd() / 'logs')
handler = logging.handlers.RotatingFileHandler(
    filename=Path.cwd() / 'logs' / 'cameraSensor.log',
    maxBytes=settings["Logging"]["max_bytes"],
    backupCount=settings["Logging"]["backup_count"],
    encoding='utf-8',
    delay=False)
handler.setFormatter(formatter)
logger.addHandler(handler)

# Redis
r = redis.Redis(host=settings["Redis"]["host"], port=settings["Redis"]["port"], db=settings["Redis"]["db"])

# check redis connection
try:
    r.ping()
    logger.debug("Redis is available")
except redis.ConnectionError:
    logger.error("Redis is unavailable")

# timeout time
timeout = settings["Alarm"]["timeout"]
runtime = 0


def main():
    # load and prepare image
    video = cv.VideoCapture(0)
    is_last_frame = 0
    trigger_status = 0
    logger.info('Service started: Detecting people...')
    while True:
        if r.exists('trigger_status'):
            trigger_status = ast.literal_eval(r.get('trigger_status').decode('utf8'))
        if trigger_status == 1:
            if is_last_frame >= 5:
                check, img = video.read()
                img = imutils.resize(img, width=400)
                is_last_frame = 0
                detect_person(img)
            else:
                # print("not last: " + str(is_last_frame))
                is_last_frame += 1


def detect_person(img):
    # Load names of classes and get random colors
    classes = open('yolo/coco.names').read().strip().split('\n')
    np.random.seed(42)
    # colors = np.random.randint(0, 255, size=(len(classes), 3), dtype='uint8')
    color = (0, 0, 255)

    # Give the configuration and weight files for the model and load the network.
    net = cv.dnn.readNetFromDarknet('yolo/yolov3.cfg', 'yolo/yolov3.weights')
    net.setPreferableBackend(cv.dnn.DNN_BACKEND_OPENCV)
    # net.setPreferableTarget(cv.dnn.DNN_TARGET_CPU)

    # determine the output layer
    ln = net.getLayerNames()
    ln = [ln[i - 1] for i in net.getUnconnectedOutLayers()]

    # construct a blob from the image
    blob = cv.dnn.blobFromImage(img, 1 / 255.0, (416, 416), swapRB=True, crop=False)

    net.setInput(blob)
    start_time = time.time()
    outputs = net.forward(ln)
    end_time = time.time()
    runtime = end_time - start_time

    boxes = []
    confidences = []
    classIDs = []
    h, w = img.shape[:2]

    for output in outputs:
        for detection in output:
            scores = detection[5:]
            classID = np.argmax(scores)
            confidence = scores[classID]
            if confidence > 0.5:
                box = detection[:4] * np.array([w, h, w, h])
                (centerX, centerY, width, height) = box.astype("int")
                x = int(centerX - (width / 2))
                y = int(centerY - (height / 2))
                box = [x, y, int(width), int(height)]
                boxes.append(box)
                confidences.append(float(confidence))
                classIDs.append(classID)

    indices = cv.dnn.NMSBoxes(boxes, confidences, 0.5, 0.4)
    if len(indices) > 0:
        for i in indices.flatten():
            # show only persons
            if classes[classIDs[i]] == 'person':
                (x, y) = (boxes[i][0], boxes[i][1])
                (w, h) = (boxes[i][2], boxes[i][3])
                img = cv.cvtColor(img, cv.COLOR_RGB2GRAY)
                img = cv.cvtColor(img, cv.COLOR_GRAY2RGB)
                cv.rectangle(img, (x, y), (x + w, y + h), color, 2)
                # cv.imwrite(curdate + ".jpg", img)
                print("person detected")
                logger.warning("Person detected!")
                save_image(img)


def save_image(img):
    print("Wait timeout")
    if (timeout - runtime) >= 0:
        time.sleep(timeout - runtime)
    print(runtime)
    _, im_arr = cv.imencode('.jpg', img)
    im_bytes = im_arr.tobytes()
    im_b64 = base64.b64encode(im_bytes).decode("utf-8")
    curdate = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    frame_obj = {
        "timestamp": curdate,
        "frame": im_b64
    }
    frame_json = json.dumps(frame_obj)
    dev = settings["Device"]["name"]
    trigger_status = ast.literal_eval(r.get('trigger_status').decode('utf8'))
    #  system is still active
    if trigger_status == 1:
        r.set('trigger_dev', dev)
        # write frame into redis
        r.set('frame', frame_json)
        print("frame saved to redis")
        print('time: ', runtime)
        logger.debug(f"Runtime: {round(runtime, 3)}")
        logger.info("Frame saved to redis.")
    else:
        logger.info("Person was detected, but system was deactivated")
        print("Person was detected, but system was deactivated")


main()
