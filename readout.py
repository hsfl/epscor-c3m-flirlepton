#!/usr/bin/env python
# -*- coding: utf-8 -*-

from uvctypes import *
import time
import cv2
import numpy as np
from queue import Queue
import platform
import os

BUF_SIZE = 2
q = Queue(BUF_SIZE)
 
SAVE_DIR = "saved_frames_test_3"  # Directory to save frames
FRAME_RATE = 9  # Desired frame rate (frames per second)

# Create the directory if it doesn't exist
if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

def py_frame_callback(frame, userptr):
    array_pointer = cast(frame.contents.data, POINTER(c_uint16 * (frame.contents.width * frame.contents.height)))
    data = np.frombuffer(
        array_pointer.contents, dtype=np.dtype(np.uint16)
    ).reshape(
        frame.contents.height, frame.contents.width
    ) # no copy

    if frame.contents.data_bytes != (2 * frame.contents.width * frame.contents.height):
        return

    if not q.full():
        q.put(data)

PTR_PY_FRAME_CALLBACK = CFUNCTYPE(None, POINTER(uvc_frame), c_void_p)(py_frame_callback)

def ktof(val):
    return (1.8 * ktoc(val) + 32.0)

def ktoc(val):
    return (val - 27315) / 100.0

def raw_to_8bit(data):
    cv2.normalize(data, data, 0, 65535, cv2.NORM_MINMAX)
    np.right_shift(data, 8, data)
    return cv2.cvtColor(np.uint8(data), cv2.COLOR_GRAY2RGB)

def display_temperature(img, val_k, loc, color):
    val = ktof(val_k)
    cv2.putText(img,"{0:.1f} degF".format(val), loc, cv2.FONT_HERSHEY_SIMPLEX, 0.75, color, 2)
    x, y = loc
    cv2.line(img, (x - 2, y), (x + 2, y), color, 1)
    cv2.line(img, (x, y - 2), (x, y + 2), color, 1)

def main():
    ctx = POINTER(uvc_context)()
    dev = POINTER(uvc_device)()
    devh = POINTER(uvc_device_handle)()
    ctrl = uvc_stream_ctrl()

    res = libuvc.uvc_init(byref(ctx), 0)
    if res < 0:
        print("uvc_init error")
        exit(1)

    try:
        res = libuvc.uvc_find_device(ctx, byref(dev), PT_USB_VID, PT_USB_PID, 0)
        if res < 0:
            print("uvc_find_device error - Couldn't find the device, is it plugged in? You should see a Cubeternet Webcam or something new once its plugged in.")
            exit(1)

        try:
            res = libuvc.uvc_open(dev, byref(devh))
            print(devh)
            if res < 0:
                print("uvc_open error - use command 'sudo chmod -R 777 /dev/bus/usb/' as a temporary blanket permission fix for testing.")
                exit(1)

            print("device opened!")

            print_device_info(devh)
            print_device_formats(devh)

            frame_formats = uvc_get_frame_formats_by_guid(devh, VS_FMT_GUID_Y16)
            if len(frame_formats) == 0:
                print("device does not support Y16 - we need this to read out the temperatures properly")
                exit(1)

            libuvc.uvc_get_stream_ctrl_format_size(devh, byref(ctrl), UVC_FRAME_FORMAT_Y16,
                frame_formats[0].wWidth, frame_formats[0].wHeight, int(1e7 / frame_formats[0].dwDefaultFrameInterval)
            )

            res = libuvc.uvc_start_streaming(devh, byref(ctrl), PTR_PY_FRAME_CALLBACK, None, 0)
            if res < 0:
                print("uvc_start_streaming failed: {0}".format(res))
                exit(1)

            try:
                frame_count = 0
                start_time = time.time()

                while True:
                    data = q.get(True, 500)
                    if data is None:
                        break

                    # TODO: Replace per-frame .bin saving with saving all frames to a single .npz file.
                    # Context: Instead of saving each frame as a separate binary file, accumulate frames in a list or array during acquisition.
                    # After acquisition, use np.savez_compressed('frames.npz', frames=np.array(frame_list)) to store all frames in one compressed file.
                    # When loading, use: data = np.load('frames.npz')['frames']
                    # This will make data management and loading much easier for analysis.
                    # Example:
                    #   frame_list = []  # before loop
                    #   ...
                    #   frame_list.append(data)  # inside loop
                    #   ...
                    #   np.savez_compressed('frames.npz', frames=np.array(frame_list))  # after loop

                    data = cv2.resize(data[:, :], (160, 120))
                    minVal, maxVal, minLoc, maxLoc = cv2.minMaxLoc(data)
                    img = raw_to_8bit(data)
                    display_temperature(img, minVal, minLoc, (255, 0, 0))
                    display_temperature(img, maxVal, maxLoc, (0, 0, 255))
                    cv2.imshow('Lepton Radiometry', img)
                    cv2.waitKey(1)

                    # Ensure the desired frame rate
                    elapsed_time = time.time() - start_time
                    expected_time = frame_count / FRAME_RATE
                    if elapsed_time < expected_time:
                        time.sleep(expected_time - elapsed_time)

                    # Break if window is closed
                    if cv2.getWindowProperty('Lepton Radiometry', cv2.WND_PROP_VISIBLE) < 1:
                        break

                cv2.destroyAllWindows()
            finally:
                libuvc.uvc_stop_streaming(devh)

            print("done")
        finally:
            libuvc.uvc_unref_device(dev)
    finally:
        libuvc.uvc_exit(ctx)

if __name__ == '__main__':
    main()
