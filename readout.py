from uvctypes import *
import time
import cv2
import numpy as np
from queue import Queue, Empty, Full
import platform
import os


BUF_SIZE = 2
q = Queue(BUF_SIZE)

SAVE_DIR = None
FRAME_RATE = 6  # Desired recording rate; the camera may deliver frames faster.
NPZ_FILE_NAME = None

# Saves frames as individual binary files
def save_frame_to_bin(frame, index):
   file_path = os.path.join(SAVE_DIR, f"frame_{index:04d}.bin")
   frame.astype(np.uint16).tofile(file_path)

# Saves frames in single npz file
def save_frame_to_npz(frame_list):
    file_path = os.path.join(SAVE_DIR, NPZ_FILE_NAME)
    np.savez_compressed(file_path, frames=np.array(frame_list))
    print("Successfully saved frames to " + file_path)

def py_frame_callback(frame, userptr):
   # Validate the native buffer BEFORE reading it: ctypes cannot protect us
   # from reading beyond an allocation, which can terminate Python outright.
   if not frame:
       return
   native_frame = frame.contents
   width, height = native_frame.width, native_frame.height
   if (not native_frame.data or not width or not height
           or native_frame.frame_format != UVC_FRAME_FORMAT_Y16
           or native_frame.data_bytes != 2 * width * height
           or native_frame.step not in (0, 2 * width)):
       return
   if q.full():
       return
   array_pointer = cast(native_frame.data, POINTER(c_uint16 * (width * height)))
   # Copy before returning: libuvc owns and reuses the callback buffer.
   data = np.frombuffer(array_pointer.contents, dtype=np.dtype('<u2')).reshape(
       height, width
   ).copy()
   try:
       q.put_nowait(data)
   except Full:
       pass


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
   cv2.putText(img,"{0:.1f} degF".format(val), loc, cv2.FONT_HERSHEY_SIMPLEX, 1.5, color, 2)
   x, y = loc
   cv2.line(img, (x - 2, y), (x + 2, y), color, 1)
   cv2.line(img, (x, y - 2), (x, y + 2), color, 1)

def print_uvc_open_error(res):
   try:
       libuvc.uvc_strerror.argtypes = [c_int]
       libuvc.uvc_strerror.restype = c_char_p
       err = libuvc.uvc_strerror(res)
       err_str = err.decode() if err else "Unknown error"
   except Exception:
       err_str = "Unknown error"

   print(f"uvc_open error ({res}): {err_str}")
   if platform.system() == "Darwin" and res == -3:
       print("USB access was denied on macOS. The system UVC driver or application sandbox may prevent exclusive access; Camera privacy permission alone may not resolve it.")


def main():
    global SAVE_DIR, NPZ_FILE_NAME
    SAVE_DIR = "saved_frames_test_" + input("Enter directory number: saved_frames_test_")
    NPZ_FILE_NAME = input("Enter a file name (no spaces): ") + ".npz"
    os.makedirs(SAVE_DIR, exist_ok=True)
    # A subsequent capture in this process must not reuse queued old frames.
    while not q.empty():
        q.get_nowait()
    ctx = POINTER(uvc_context)()
    dev = POINTER(uvc_device)()
    devh = POINTER(uvc_device_handle)()
    ctrl = uvc_stream_ctrl()
    frame_list = []

    res = libuvc.uvc_init(byref(ctx), 0)
    if res < 0:
        print("uvc_init error")
        return

    try:
        res = libuvc.uvc_find_device(ctx, byref(dev), PT_USB_VID, PT_USB_PID, 0)
        if res < 0:
            print("uvc_find_device error - Couldn't find the device; is it plugged in?")
            return

        try:
            res = libuvc.uvc_open(dev, byref(devh))
            if res < 0:
                print_uvc_open_error(res)
                return

            try:
                print("device opened!")
                print_device_info(devh)
                print_device_formats(devh)

                frame_formats = uvc_get_frame_formats_by_guid(devh, VS_FMT_GUID_Y16)
                if not frame_formats:
                    print("device does not support Y16 - required for temperature readout")
                    return

                fmt = frame_formats[0]
                res = libuvc.uvc_get_stream_ctrl_format_size(
                    devh, byref(ctrl), UVC_FRAME_FORMAT_Y16,
                    fmt.wWidth, fmt.wHeight, int(1e7 / fmt.dwDefaultFrameInterval)
                )
                if res < 0:
                    print(f"uvc_get_stream_ctrl_format_size failed: {res}")
                    return

                res = libuvc.uvc_start_streaming(
                    devh, byref(ctrl), PTR_PY_FRAME_CALLBACK, None, 0
                )
                if res < 0:
                    print(f"uvc_start_streaming failed: {res}")
                    return

                try:
                    frame_count = 0
                    start_time = time.monotonic()
                    cv2.namedWindow('Lepton Radiometry', cv2.WINDOW_NORMAL)
                    show_temp = True

                    while True:
                        try:
                            try:
                                raw_frame = q.get(timeout=0.5)
                            except Empty:
                                raw_frame = None

                            if raw_frame is not None:
                                # Preserve original 16-bit pixels for analysis.
                                frame_list.append(raw_frame)
                                # save_frame_to_bin(raw_frame, frame_count)
                                frame_count += 1

                                display_frame = cv2.resize(raw_frame, (1280, 960))
                                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(display_frame)
                                img = raw_to_8bit(display_frame)
                                if show_temp:
                                    display_temperature(img, min_val, min_loc, (255, 0, 0))
                                    display_temperature(img, max_val, max_loc, (0, 0, 255))
                                cv2.imshow('Lepton Radiometry', img)

                            key = cv2.waitKey(1) & 0xFF
                            if key == ord('t'):
                                show_temp = not show_temp
                            elif key == ord('q'):
                                break

                            elapsed = time.monotonic() - start_time
                            expected = frame_count / FRAME_RATE
                            if elapsed < expected:
                                time.sleep(expected - elapsed)

                            if cv2.getWindowProperty('Lepton Radiometry', cv2.WND_PROP_VISIBLE) < 1:
                                print("Window closed by user")
                                break
                        except KeyboardInterrupt:
                            print("Camera stopped by user")
                            break
                finally:
                    libuvc.uvc_stop_streaming(devh)
                    try:
                        cv2.destroyAllWindows()
                    finally:
                        if frame_list:
                            save_frame_to_npz(frame_list)
            finally:
                libuvc.uvc_close(devh)
        finally:
            libuvc.uvc_unref_device(dev)
    finally:
        libuvc.uvc_exit(ctx)


if __name__ == '__main__':
    main()
