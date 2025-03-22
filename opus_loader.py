import ctypes
import os
import platform


def load_opus():
    # On macOS with Apple Silicon, check Homebrew location first
    if platform.system() == "Darwin":
        lib_path = "/opt/homebrew/lib/libopus.0.dylib"
        if os.path.exists(lib_path):
            try:
                return ctypes.CDLL(lib_path)
            except OSError:
                pass
    
    # Fall back to standard library loading
    if platform.system() == "Darwin":
        try:
            return ctypes.CDLL("libopus.0.dylib")
        except OSError:
            pass
    elif platform.system() == "Windows":
        try:
            return ctypes.CDLL("opus.dll")
        except OSError:
            pass
    else:
        try:
            return ctypes.CDLL("libopus.so")
        except OSError:
            pass
    
    raise RuntimeError("Could not load opus library") 