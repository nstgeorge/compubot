import ctypes
from ctypes import *

import pyogg.opus as opus

from opus_loader import load_opus


# Define the OpusEncoder structure
class OpusEncoder(Structure):
    _fields_ = [("dummy", c_int)]

# Define the OpusDecoder structure
class OpusDecoder(Structure):
    _fields_ = [("dummy", c_int)]

# Load our library
opus.libopus = load_opus()
opus.OpusEncoder = OpusEncoder
opus.OpusDecoder = OpusDecoder

# Define types needed for opus functions
opus_int32 = c_int
opus_int16 = c_int16
opus_uint32 = c_uint32
opus_int64 = c_int64
size_t = c_size_t
c_int_p = POINTER(c_int)
c_float_p = POINTER(c_float)
c_uchar_p = POINTER(c_ubyte)
opus_int16_p = POINTER(opus_int16)

# Set up encoder functions
opus.libopus.opus_encoder_get_size.restype = c_int
opus.libopus.opus_encoder_get_size.argtypes = [c_int]

opus.libopus.opus_encoder_create.restype = POINTER(OpusEncoder)
opus.libopus.opus_encoder_create.argtypes = [opus_int32, c_int, c_int, c_int_p]

opus.libopus.opus_encoder_init.restype = c_int
opus.libopus.opus_encoder_init.argtypes = [POINTER(OpusEncoder), opus_int32, c_int, c_int]

opus.libopus.opus_encode.restype = opus_int32
opus.libopus.opus_encode.argtypes = [POINTER(OpusEncoder), opus_int16_p, c_int, c_uchar_p, opus_int32]

opus.libopus.opus_encode_float.restype = opus_int32
opus.libopus.opus_encode_float.argtypes = [POINTER(OpusEncoder), c_float_p, c_int, c_uchar_p, opus_int32]

opus.libopus.opus_encoder_destroy.restype = None
opus.libopus.opus_encoder_destroy.argtypes = [POINTER(OpusEncoder)]

# Set up decoder functions
opus.libopus.opus_decoder_get_size.restype = c_int
opus.libopus.opus_decoder_get_size.argtypes = [c_int]

opus.libopus.opus_decoder_create.restype = POINTER(OpusDecoder)
opus.libopus.opus_decoder_create.argtypes = [opus_int32, c_int, c_int_p]

opus.libopus.opus_decoder_init.restype = c_int
opus.libopus.opus_decoder_init.argtypes = [POINTER(OpusDecoder), opus_int32, c_int]

opus.libopus.opus_decode.restype = c_int
opus.libopus.opus_decode.argtypes = [POINTER(OpusDecoder), c_uchar_p, opus_int32, opus_int16_p, c_int, c_int]

opus.libopus.opus_decode_float.restype = c_int
opus.libopus.opus_decode_float.argtypes = [POINTER(OpusDecoder), c_uchar_p, opus_int32, c_float_p, c_int, c_int]

opus.libopus.opus_decoder_destroy.restype = None
opus.libopus.opus_decoder_destroy.argtypes = [POINTER(OpusDecoder)]

# Update availability flag
opus.PYOGG_OPUS_AVAIL = True

# Constants
OPUS_APPLICATION_VOIP = opus.OPUS_APPLICATION_VOIP

# Define the functions in the module namespace
def opus_encoder_get_size(channels):
    return opus.libopus.opus_encoder_get_size(channels)

def opus_encoder_create(Fs, channels, application, error):
    return opus.libopus.opus_encoder_create(Fs, channels, application, error)

def opus_encoder_init(st, Fs, channels, application):
    return opus.libopus.opus_encoder_init(st, Fs, channels, application)

def opus_encode(st, pcm, frame_size, data, max_data_bytes):
    return opus.libopus.opus_encode(st, pcm, frame_size, data, max_data_bytes)

def opus_encode_float(st, pcm, frame_size, data, max_data_bytes):
    return opus.libopus.opus_encode_float(st, pcm, frame_size, data, max_data_bytes)

def opus_encoder_destroy(st):
    return opus.libopus.opus_encoder_destroy(st)

# Define decoder functions in the module namespace
def opus_decoder_get_size(channels):
    return opus.libopus.opus_decoder_get_size(channels)

def opus_decoder_create(Fs, channels, error):
    return opus.libopus.opus_decoder_create(Fs, channels, error)

def opus_decoder_init(st, Fs, channels):
    return opus.libopus.opus_decoder_init(st, Fs, channels)

def opus_decode(st, data, len, pcm, frame_size, decodeFEC):
    return opus.libopus.opus_decode(st, data, len, pcm, frame_size, decodeFEC)

def opus_decode_float(st, data, len, pcm, frame_size, decodeFEC):
    return opus.libopus.opus_decode_float(st, data, len, pcm, frame_size, decodeFEC)

def opus_decoder_destroy(st):
    return opus.libopus.opus_decoder_destroy(st)

# Add functions to opus module
opus.opus_encoder_get_size = opus_encoder_get_size
opus.opus_encoder_create = opus_encoder_create
opus.opus_encoder_init = opus_encoder_init
opus.opus_encode = opus_encode
opus.opus_encode_float = opus_encode_float
opus.opus_encoder_destroy = opus_encoder_destroy
opus.opus_decoder_get_size = opus_decoder_get_size
opus.opus_decoder_create = opus_decoder_create
opus.opus_decoder_init = opus_decoder_init
opus.opus_decode = opus_decode
opus.opus_decode_float = opus_decode_float
opus.opus_decoder_destroy = opus_decoder_destroy

# Verify it worked
if not opus.PYOGG_OPUS_AVAIL:
    raise RuntimeError("Failed to patch PyOgg opus library") 