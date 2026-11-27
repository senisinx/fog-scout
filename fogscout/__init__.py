"""Fog Scout – map overlay for Dead by Daylight with OCR map detection."""
import os as _os

__version__ = "1.57.83"

# 1.64.7: onnxruntime (OCR) has Microsoft telemetry built in – also on Linux it sent events to
# mobile.events.data.microsoft.com (measured: 4 tries in 40 s). The map detection must not connect to the
# internet (CLAUDE.md), so it is switched off before onnxruntime is ever loaded. ocr.py also calls
# onnxruntime.disable_telemetry_events() (on Windows: its ETW events).
_os.environ["ORT_DISABLE_TELEMETRY"] = "1"

# 1.8.38 (QA audit, measured): the OCR's one small matrix product (ocr.Recognizer.groups) went to multithreaded
# OpenBLAS, whose threads then spin between the looks – about half a core in the menus for a 1-ms product.
# One thread is faster for it and idles at 0. Set before numpy is loaded; a value the user set stays.
_os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

# 1.57.62 (security review, reproduced): OpenCV looks for optional plugin DLLs on the first parallel operation –
# opencv_core_parallel_{onetbb,tbb,openmp}*.dll first in its own folder, then by bare name through the normal DLL
# search, which ends with PATH. The user's PATH holds folders any program of the user may write to
# (%LOCALAPPDATA%\Microsoft\WindowsApps): a DLL of that name there ran inside Fog Scout – with the administrator
# rights of the scheduled task. OPENCV_CORE_PLUGIN_PATH / OPENCV_OPENCL_RUNTIME (user environment) named such a DLL
# directly. Fog Scout uses none of them: no OpenCV variable from outside counts (the log level is only text), the
# plugin backends get priority 0 (= never loaded, OpenCV's own threads stay) and OpenCL is off – before cv2 loads.
for _key in [k for k in _os.environ if k.upper().startswith("OPENCV_") and k.upper() != "OPENCV_LOG_LEVEL"]:
    del _os.environ[_key]
_os.environ.update({"OPENCV_PARALLEL_PRIORITY_ONETBB": "0", "OPENCV_PARALLEL_PRIORITY_TBB": "0",
                    "OPENCV_PARALLEL_PRIORITY_OPENMP": "0", "OPENCV_OPENCL_RUNTIME": "disabled"})
