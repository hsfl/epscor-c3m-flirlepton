#!/usr/bin/env python
# -*- coding: utf-8 -*-

from uvctypes import *

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
    print("macOS denied USB capture access. Run with sudo, or use a signed app with USB capture entitlement.")

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
      print("uvc_find_device error")
      exit(1)

    try:
      res = libuvc.uvc_open(dev, byref(devh))
      if res < 0:
        print_uvc_open_error(res)
        exit(1)

      print_device_info(devh)

    finally:
      libuvc.uvc_unref_device(dev)
  finally:
    libuvc.uvc_exit(ctx)

if __name__ == '__main__':
  main()
