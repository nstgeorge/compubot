import asyncio
import base64
import ctypes
import json
import logging
import os
import select
import ssl
import struct
import sys
import threading
import time
import uuid
from typing import Any, Dict, Optional, cast

import nacl.bindings
import nacl.secret
import numpy as np
import websocket
from interactions import (ActiveVoiceState, Extension, Member, SlashContext,
                          VoiceState, listen, slash_command)

from pyogg_patch import (OPUS_APPLICATION_VOIP, OpusDecoder, opus_decode,
                         opus_decode_float, opus_decoder_create,
                         opus_decoder_destroy, opus_decoder_init, opus_encode,
                         opus_encoder_create, opus_encoder_destroy,
                         opus_encoder_init)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or ""
url = "wss://api.openai.com/v1/realtime?model=gpt-4o-mini-realtime-preview-2024-12-17"
headers = {
    "Authorization": f"Bearer {OPENAI_API_KEY}",
    "OpenAI-Beta": "realtime=v1"
}

# Discord audio constants
DISCORD_SAMPLE_RATE = 48000
OPENAI_SAMPLE_RATE = 24000
CHANNELS = 2
FRAME_LENGTH = 20  # ms
FRAME_SIZE = int(DISCORD_SAMPLE_RATE * FRAME_LENGTH / 1000)

def resample_audio(audio_data: bytes, from_rate: int, to_rate: int) -> bytes:
    """Resample audio data from one sample rate to another."""
    # Convert bytes to numpy array of 16-bit integers
    audio_array = np.frombuffer(audio_data, dtype=np.int16)
    
    # Calculate resampling ratio
    ratio = to_rate / from_rate
    
    # Calculate number of samples in output
    output_length = int(len(audio_array) * ratio)
    
    # Create time points for interpolation
    original_time = np.linspace(0, len(audio_array), len(audio_array))
    new_time = np.linspace(0, len(audio_array), output_length)
    
    # Resample using linear interpolation
    resampled = np.interp(new_time, original_time, audio_array)
    
    # Convert back to 16-bit integers
    resampled = resampled.astype(np.int16)
    
    # Convert to bytes
    return resampled.tobytes()

class Voice(Extension):
    def __init__(self, client):
        self.client = client
        self.voice_states: Dict[int, tuple[ActiveVoiceState, websocket.WebSocketApp]] = {}
        self.recording = False
        self.ws_ready: Dict[int, threading.Event] = {}  # Track WebSocket readiness per guild
        self.socket_threads: Dict[int, threading.Thread] = {}  # Track audio streaming threads per guild
        self.audio_queue: Dict[int, asyncio.Queue] = {}  # Queue for audio packets per guild
        self.packet_queue: Dict[int, Dict[int, bytes]] = {}  # Queue for packets per guild, keyed by sequence
        self.last_sequence: Dict[int, int] = {}  # Last processed sequence per guild
        self.main_loop = asyncio.get_event_loop()  # Store reference to main event loop
        self.queue_task = None  # Store reference to queue processing task
        self._incr_nonce = 0  # Incremental nonce for xsalsa20_poly1305
        self.recording_files: Dict[int, Dict[str, Any]] = {}  # Track recording files per guild
        self.wav_buffer: Dict[int, bytes] = {}  # Buffer for accumulating PCM data for WAV files
        self.total_samples: Dict[int, int] = {}  # Track total samples written for each guild
        self.last_timestamps = {}  # Track last timestamp per SSRC
        
        # Initialize Opus decoder
        error = ctypes.pointer(ctypes.c_int(0))
        self.decoder = opus_decoder_create(DISCORD_SAMPLE_RATE, CHANNELS, error)
        if error.contents.value != 0:
            raise RuntimeError(f"Failed to create Opus decoder: error {error.contents.value}")
        
        # Initialize the decoder
        result = opus_decoder_init(self.decoder, DISCORD_SAMPLE_RATE, CHANNELS)
        if result != 0:
            opus_decoder_destroy(self.decoder)
            raise RuntimeError(f"Failed to initialize Opus decoder: error {result}")
            
        # Initialize Opus encoder for sending audio back to Discord
        self.encoder = opus_encoder_create(DISCORD_SAMPLE_RATE, CHANNELS, OPUS_APPLICATION_VOIP, error)
        if error.contents.value != 0:
            raise RuntimeError(f"Failed to create Opus encoder: error {error.contents.value}")
            
        # Initialize the encoder
        result = opus_encoder_init(self.encoder, DISCORD_SAMPLE_RATE, CHANNELS, OPUS_APPLICATION_VOIP)
        if result != 0:
            opus_encoder_destroy(self.encoder)
            raise RuntimeError(f"Failed to initialize Opus encoder: error {result}")
            
        # Start the audio processing task
        self.start_queue_processing()

    def start_queue_processing(self):
        """Start the audio queue processing task."""
        try:
            if self.queue_task is None or self.queue_task.done():
                logging.info("Starting audio queue processing task")
                # Create and run the task in the event loop
                self.queue_task = asyncio.run_coroutine_threadsafe(
                    self.process_audio_queue(),
                    self.main_loop
                )
                # Verify the task started
                if self.queue_task.done():
                    exception = self.queue_task.exception()
                    if exception:
                        logging.error(f"Queue processing task failed to start: {exception}")
                    else:
                        logging.error("Queue processing task completed immediately")
                else:
                    logging.info("Audio queue processing task started successfully")
            else:
                logging.info("Audio queue processing task already running")
        except Exception as e:
            logging.error(f"Error in start_queue_processing: {e}", exc_info=True)

    async def process_audio_queue(self):
        """Process audio packets from the queue."""
        logging.info("Audio queue processing task started")
        try:
            while True:
                try:
                    # Process queues for all guilds
                    for guild_id, (voice_state, _) in self.voice_states.items():
                        if guild_id in self.audio_queue:
                            queue = self.audio_queue[guild_id]
                            try:
                                # Try to get data from queue without blocking
                                pcm_data = queue.get_nowait()
                                logging.info(f"Got {len(pcm_data)} bytes from queue for guild {guild_id}")
                                if voice_state and voice_state.ws and voice_state.ws.socket:
                                    try:
                                        await self.send_audio_packet(voice_state, pcm_data)
                                        logging.info(f"Sent audio packet to Discord for guild {guild_id}")
                                    except Exception as e:
                                        logging.error(f"Error sending audio packet: {e}", exc_info=True)
                                else:
                                    logging.error(f"Voice connection not available for guild {guild_id}")
                                queue.task_done()
                            except asyncio.QueueEmpty:
                                # No data in queue, continue to next guild
                                pass
                    
                    # Sleep briefly to avoid busy-waiting
                    await asyncio.sleep(0.001)
                except Exception as e:
                    logging.error(f"Error in audio queue processing loop: {e}", exc_info=True)
                    await asyncio.sleep(1)  # Wait longer on error
        except Exception as e:
            logging.error(f"Fatal error in audio queue processing task: {e}", exc_info=True)
            # Try to restart the task
            self.start_queue_processing()

    def decode_opus_to_pcm(self, opus_data: bytes) -> bytes:
        """Decode Opus packet to PCM format."""
        try:
            # Create buffer for decoded PCM data
            # Maximum frame size for Opus is 120ms at 48kHz
            max_frame_size = int(DISCORD_SAMPLE_RATE * 0.120)  # 120ms at 48kHz
            pcm_size = max_frame_size * CHANNELS  # Account for stereo
            pcm_buffer = (ctypes.c_int16 * pcm_size)()
            
            # Log detailed Opus packet info
            if len(opus_data) >= 2:
                toc = opus_data[0]
                frame_count = opus_data[1]
                
                # Parse TOC byte
                frame_size_bits = toc & 0x03
                num_frames_bits = (toc >> 2) & 0x03
                config_bits = (toc >> 4) & 0x0F
                
                # Calculate frame size
                frame_size = 20  # Default to 20ms
                if frame_size_bits == 0:
                    frame_size = 10
                elif frame_size_bits == 1:
                    frame_size = 20
                elif frame_size_bits == 2:
                    frame_size = 40
                elif frame_size_bits == 3:
                    # Variable frames - use frame count byte
                    num_frames = frame_count
                
                # Calculate number of frames
                num_frames = 1  # Default to 1 frame
                if num_frames_bits == 0:
                    num_frames = 1
                elif num_frames_bits == 1:
                    num_frames = 2
                elif num_frames_bits == 2:
                    num_frames = 3
                elif num_frames_bits == 3:
                    # Variable frames - use frame count byte
                    num_frames = frame_count
                
                logging.debug(f"Opus TOC Analysis:")
                logging.debug(f"  TOC byte: {toc:02x}")
                logging.debug(f"  Frame size bits: {frame_size_bits} ({frame_size}ms)")
                logging.debug(f"  Num frames bits: {num_frames_bits}")
                logging.debug(f"  Config bits: {config_bits:02x}")
                logging.debug(f"  Frame count byte: {frame_count:02x}")
                logging.debug(f"  Calculated frames: {num_frames}")
                
                # Calculate expected frame size in samples
                frame_size_samples = int(DISCORD_SAMPLE_RATE * frame_size / 1000)
                logging.debug(f"  Expected frame size: {frame_size_samples} samples")
                
                # For variable frames, we need to calculate the total packet size
                if num_frames_bits == 3:  # Variable frames
                    # Each frame has a size byte followed by the frame data
                    # The size is encoded as (size - 1) in the size byte
                    total_size = 2  # TOC + frame count
                    current_pos = 2
                    
                    for _ in range(num_frames):
                        if current_pos >= len(opus_data):
                            logging.error("Packet truncated during frame size calculation")
                            return b''
                        size_byte = opus_data[current_pos]
                        frame_size_bytes = size_byte + 1
                        total_size += frame_size_bytes + 1  # +1 for the size byte
                        current_pos += frame_size_bytes + 1
                    
                    if total_size != len(opus_data):
                        logging.warning(f"Packet size mismatch: expected {total_size}, got {len(opus_data)}")
                        # Use the actual packet size instead
                        total_size = len(opus_data)
                    
                    logging.debug(f"Calculated total packet size: {total_size} bytes")
            
            # Convert opus_data bytes to ctypes array
            opus_buffer = (ctypes.c_ubyte * len(opus_data))(*opus_data)
            
            # Log opus packet info
            logging.debug(f"Decoding opus packet of {len(opus_data)} bytes (buffer size: {pcm_size} samples)")
            logging.debug(f"Opus packet hex: {opus_data.hex()}")
            
            # Decode Opus packet to PCM
            decoded_samples = opus_decode(
                self.decoder,
                opus_buffer,
                len(opus_data),
                pcm_buffer,
                max_frame_size,  # Use maximum possible frame size
                0  # No FEC
            )
            
            if decoded_samples < 0:
                error_codes = {
                    -1: "OPUS_BAD_ARG",
                    -2: "OPUS_BUFFER_TOO_SMALL",
                    -3: "OPUS_INTERNAL_ERROR",
                    -4: "OPUS_INVALID_PACKET",
                    -5: "OPUS_UNIMPLEMENTED",
                    -6: "OPUS_INVALID_STATE",
                    -7: "OPUS_ALLOC_FAIL",
                }
                error_name = error_codes.get(decoded_samples, "UNKNOWN_ERROR")
                logging.error(f"Error decoding Opus packet: {error_name} ({decoded_samples}) (opus size: {len(opus_data)})")
                return b''
                
            # Convert to bytes - only take the actual decoded samples
            pcm_bytes = bytes(pcm_buffer)[:decoded_samples * CHANNELS * 2]  # 2 bytes per sample
            logging.debug(f"Successfully decoded {decoded_samples} samples ({len(pcm_bytes)} bytes)")
            
            # Apply a simple low-pass filter to reduce high-frequency noise
            pcm_array = np.frombuffer(pcm_bytes, dtype=np.int16)
            # Simple moving average filter
            window_size = 3
            kernel = np.ones(window_size) / window_size
            filtered = np.convolve(pcm_array, kernel, mode='same')
            # Convert back to int16
            filtered = filtered.astype(np.int16)
            pcm_bytes = filtered.tobytes()
            
            return pcm_bytes
            
        except Exception as e:
            logging.error(f"Error decoding Opus packet: {e}")
            return b''

    def float_to_16bit_pcm(self, float32_array):
        """Convert float32 array to 16-bit PCM."""
        clipped = [max(-1.0, min(1.0, x)) for x in float32_array]
        pcm16 = b''.join(struct.pack('<h', int(x * 32767)) for x in clipped)
        return pcm16

    def base64_encode_audio(self, audio_data: Any) -> str:
        """Convert audio data to base64 encoded string."""
        if isinstance(audio_data, bytes):
            return base64.b64encode(audio_data).decode('ascii')
        elif hasattr(audio_data, 'read'):  # Handle BytesIO
            return base64.b64encode(audio_data.read()).decode('ascii')
        elif isinstance(audio_data, str):  # Handle file paths
            with open(audio_data, 'rb') as f:
                return base64.b64encode(f.read()).decode('ascii')
        else:
            raise ValueError(f"Unsupported audio data type: {type(audio_data)}")

    def process_audio_data(self, data: bytes, openai_ws: websocket.WebSocketApp, guild_id: int):
        """Process raw audio data and send it to OpenAI"""
        try:
            # Check WebSocket state first
            if not openai_ws or not openai_ws.sock or not openai_ws.sock.connected:
                if guild_id in self.ws_ready:
                    self.ws_ready[guild_id].clear()
                logging.warning("OpenAI WebSocket not connected, attempting reconnect")
                self.reconnect_openai_ws(guild_id)
                return

            # Only process if WebSocket is ready
            if not self.ws_ready[guild_id].is_set():
                logging.debug("OpenAI WebSocket not ready yet, skipping voice packet")
                return

            # Discord voice packet structure:
            # | Version | Type | Sequence | Timestamp | SSRC | Encrypted Opus Data |
            # |   1     |   1  |    2     |     4     |  4   |        rest         |
            if len(data) < 12:  # Minimum packet size
                logging.debug(f"Packet too small: {len(data)} bytes")
                return

            # Check packet type (0x78 for voice data)
            packet_type = data[1]
            if packet_type != 0x78:  # Not a voice packet, ignore silently
                return

            # Extract header info
            sequence = int.from_bytes(data[2:4], byteorder='big')
            timestamp = int.from_bytes(data[4:8], byteorder='big')
            ssrc = int.from_bytes(data[8:12], byteorder='big')

            # Initialize packet queue for this guild if needed
            if guild_id not in self.packet_queue:
                self.packet_queue[guild_id] = {}
                self.last_sequence[guild_id] = sequence - 1

            # Add packet to queue
            self.packet_queue[guild_id][sequence] = data

            # Process packets in order
            while True:
                next_seq = (self.last_sequence[guild_id] + 1) & 0xFFFF  # Wrap at 16 bits
                if next_seq not in self.packet_queue[guild_id]:
                    break

                # Get the next packet in sequence
                data = self.packet_queue[guild_id].pop(next_seq)
                self.last_sequence[guild_id] = next_seq

                # Process the packet
                self._process_single_packet(data, openai_ws, guild_id)

                # Clean up old packets (keep only the last 1000)
                if len(self.packet_queue[guild_id]) > 1000:
                    oldest_seq = min(self.packet_queue[guild_id].keys())
                    del self.packet_queue[guild_id][oldest_seq]

        except Exception as e:
            logging.error(f"Error processing audio: {e}", exc_info=True)

    def write_wav_header(self, file, num_samples: int, sample_rate: int, channels: int):
        """Write WAV header to file."""
        # WAV header parameters
        header_size = 44
        data_size = num_samples * channels * 2  # 2 bytes per sample
        file_size = header_size + data_size
        
        # Write WAV header
        file.write(b'RIFF')  # ChunkID
        file.write(struct.pack('<I', file_size - 8))  # ChunkSize
        file.write(b'WAVE')  # Format
        file.write(b'fmt ')  # Subchunk1ID
        file.write(struct.pack('<I', 16))  # Subchunk1Size
        file.write(struct.pack('<H', 1))  # AudioFormat (1 for PCM)
        file.write(struct.pack('<H', channels))  # NumChannels
        file.write(struct.pack('<I', sample_rate))  # SampleRate
        file.write(struct.pack('<I', sample_rate * channels * 2))  # ByteRate
        file.write(struct.pack('<H', channels * 2))  # BlockAlign
        file.write(struct.pack('<H', 16))  # BitsPerSample
        file.write(b'data')  # Subchunk2ID
        file.write(struct.pack('<I', data_size))  # Subchunk2Size

    def _process_single_packet(self, data: bytes, openai_ws: websocket.WebSocketApp, guild_id: int):
        """Process a single audio packet."""
        try:
            # Extract header info
            sequence = int.from_bytes(data[2:4], byteorder='big')
            timestamp = int.from_bytes(data[4:8], byteorder='big')
            ssrc = int.from_bytes(data[8:12], byteorder='big')

            # Initialize recording files if needed
            if guild_id not in self.recording_files:
                timestamp_str = time.strftime("%Y%m%d_%H%M%S")
                self.recording_files[guild_id] = {
                    'raw': open(f'recordings/raw_{guild_id}_{timestamp_str}.bin', 'wb'),
                    'opus': open(f'recordings/opus_{guild_id}_{timestamp_str}.bin', 'wb'),
                    'wav': open(f'recordings/audio_{guild_id}_{timestamp_str}.wav', 'wb')
                }
                # Initialize WAV header with a placeholder size
                self.write_wav_header(self.recording_files[guild_id]['wav'], 0, OPENAI_SAMPLE_RATE, CHANNELS)
                self.wav_buffer[guild_id] = b''
                self.total_samples[guild_id] = 0  # Track total samples written
                logging.info(f"Initialized recording files for guild {guild_id}")

            # Get voice state for decryption
            voice_state = self.voice_states[guild_id][0]
            if not voice_state or not voice_state.ws:
                logging.error("Voice state not available for decryption")
                return

            # Extract header and encrypted data
            header = data[:12]  # First 12 bytes are the header
            encrypted_data = data[12:]
            if len(encrypted_data) < 4:  # Need at least the nonce
                logging.debug("Encrypted data too small")
                return

            # Save raw packet
            self.recording_files[guild_id]['raw'].write(data)

            try:
                # Get the decoder for this SSRC if we don't have it yet
                if not hasattr(self, '_decoders'):
                    self._decoders = {}
                if ssrc not in self._decoders:
                    if not voice_state.recorder:
                        logging.error("No recorder available for voice state")
                        return
                    self._decoders[ssrc] = voice_state.recorder.get_decoder(ssrc)

                # Log packet details before decryption
                logging.debug(f"Processing packet - seq: {sequence}, ts: {timestamp}, ssrc: {ssrc}")
                logging.debug(f"Header size: {len(header)} bytes, Encrypted data size: {len(encrypted_data)} bytes")
                logging.debug(f"Header bytes: {header.hex()}")
                logging.debug(f"Encrypted data bytes: {encrypted_data.hex()}")
                
                # Validate header format
                version = header[0] & 0xC0  # Get the version bits (top 2 bits)
                if version != 0x80:  # Version should be 2 (0x80)
                    logging.error(f"Invalid header version: {header[0]:02x} (expected 0x80)")
                    return
                    
                # The type should be 0x78 for voice data
                if header[1] != 0x78:
                    logging.error(f"Invalid header type: {header[1]:02x} (expected 0x78)")
                    return

                # Decrypt the data using the voice state's recorder
                try:
                    logging.debug(f"Attempting to decrypt packet - header: {header.hex()}, encrypted data: {encrypted_data[:16].hex()}...")
                    decrypted_data = voice_state.recorder.decrypt(header, encrypted_data)
                    logging.debug(f"Decrypted {len(decrypted_data)} bytes of Opus data")
                    logging.debug(f"First 16 bytes of decrypted data: {decrypted_data[:16].hex()}")
                    
                    # Save decrypted Opus data
                    self.recording_files[guild_id]['opus'].write(decrypted_data)
                    
                    # Validate decrypted data
                    if len(decrypted_data) < 2:  # Opus packets should be at least 2 bytes
                        logging.error(f"Decrypted data too small: {len(decrypted_data)} bytes")
                        return
                        
                    # Log first few bytes of decrypted data for debugging
                    logging.debug(f"First bytes of decrypted data: {decrypted_data[:4].hex()}")
                    
                    # Check if this is a silent packet
                    if len(decrypted_data) <= 15 and decrypted_data.startswith(b'\xbe\xde\x00\x02'):
                        logging.debug("Detected silent packet")
                        return b''  # Return empty PCM data for silent packets
                    
                    # For audio packets, try decoding starting at the first byte after bede0002
                    if len(decrypted_data) > 15:
                        logging.debug("Starting decode after Discord header")
                        # Start at the first byte after bede0002
                        opus_data = decrypted_data[4:]
                    else:
                        opus_data = decrypted_data
                    
                    # Log the actual Opus packet we're trying to decode
                    logging.debug(f"Opus packet to decode: {opus_data.hex()}")
                    
                    # Create buffer for decoded PCM data
                    # Maximum frame size for Opus is 120ms at 48kHz
                    max_frame_size = int(DISCORD_SAMPLE_RATE * 0.120)  # 120ms at 48kHz
                    pcm_size = max_frame_size * CHANNELS  # Account for stereo
                    pcm_buffer = (ctypes.c_int16 * pcm_size)()
                    
                    # Convert opus_data bytes to ctypes array
                    opus_buffer = (ctypes.c_ubyte * len(opus_data))(*opus_data)
                    
                    # Log opus packet info
                    logging.debug(f"Decoding opus packet of {len(opus_data)} bytes (buffer size: {pcm_size} samples)")
                    
                    # Decode Opus packet to PCM
                    decoded_samples = opus_decode(
                        self.decoder,
                        opus_buffer,
                        len(opus_data),
                        pcm_buffer,
                        max_frame_size,  # Use maximum possible frame size
                        0  # No FEC
                    )
                    
                    if decoded_samples < 0:
                        error_codes = {
                            -1: "OPUS_BAD_ARG",
                            -2: "OPUS_BUFFER_TOO_SMALL",
                            -3: "OPUS_INTERNAL_ERROR",
                            -4: "OPUS_INVALID_PACKET",
                            -5: "OPUS_UNIMPLEMENTED",
                            -6: "OPUS_INVALID_STATE",
                            -7: "OPUS_ALLOC_FAIL",
                        }
                        error_name = error_codes.get(decoded_samples, "UNKNOWN_ERROR")
                        logging.error(f"Error decoding Opus packet: {error_name} ({decoded_samples}) (opus size: {len(opus_data)})")
                        logging.error(f"First byte of Opus data: {opus_data[0]:02x}")
                        return b''
                        
                    # Convert to bytes - only take the actual decoded samples
                    pcm_bytes = bytes(pcm_buffer)[:decoded_samples * CHANNELS * 2]  # 2 bytes per sample
                    logging.debug(f"Successfully decoded {decoded_samples} samples ({len(pcm_bytes)} bytes)")
                    
                    # First resample the audio to 24kHz
                    resampled_data = resample_audio(pcm_bytes, DISCORD_SAMPLE_RATE, OPENAI_SAMPLE_RATE)
                    resampled_samples = len(resampled_data) // (2 * CHANNELS)
                    
                    # Write to WAV file
                    self.recording_files[guild_id]['wav'].write(resampled_data)
                    self.total_samples[guild_id] += resampled_samples
                    
                    # Update WAV header with current size
                    wav_file = self.recording_files[guild_id]['wav']
                    wav_file.seek(0)
                    self.write_wav_header(wav_file, self.total_samples[guild_id], OPENAI_SAMPLE_RATE, CHANNELS)
                    wav_file.seek(0, 2)  # Seek back to end of file
                    
                    # For ChatGPT, we'll send smaller chunks without silence
                    # Calculate chunk size (100ms at 24kHz)
                    chunk_samples = int(0.1 * OPENAI_SAMPLE_RATE)  # 100ms at 24kHz
                    chunk_bytes = chunk_samples * CHANNELS * 2  # 2 bytes per sample
                    
                    # Send chunks to ChatGPT
                    for i in range(0, len(resampled_data), chunk_bytes):
                        chunk = resampled_data[i:i + chunk_bytes]
                        if len(chunk) < chunk_bytes:  # Skip partial chunks
                            continue
                            
                        # Convert chunk to base64
                        encoded_audio = base64.b64encode(chunk).decode('ascii')
                        
                        # Only check for minimum size to ensure we have valid audio
                        audio_size = len(encoded_audio)
                        if audio_size < 100:  # Too small to be valid audio
                            logging.debug(f"Audio chunk too small: {audio_size} bytes")
                            continue
                        
                        message = {
                            "audio": encoded_audio,
                            "type": "input_audio_buffer.append"
                        }

                        # Send the audio chunk with retry logic
                        if not self.send_audio_to_openai(openai_ws, message, guild_id):
                            logging.warning("Failed to send audio chunk to OpenAI")
                            return

                        # Log audio sends periodically (every 50 packets)
                        if sequence % 50 == 0:
                            logging.info(f"Sent audio chunk - seq: {sequence}, samples: {chunk_samples}, size: {audio_size}")
                        # Add a debug log for every packet
                        logging.debug(f"Processed chunk - seq: {sequence}, samples: {chunk_samples}, size: {audio_size}")

                except Exception as e:
                    logging.error(f"Error decrypting/processing packet: {e}", exc_info=True)
                    return

            except Exception as e:
                logging.error(f"Error processing audio: {e}", exc_info=True)

        except Exception as e:
            logging.error(f"Error processing audio: {e}", exc_info=True)

    def reconnect_openai_ws(self, guild_id: int):
        """Attempt to reconnect the OpenAI WebSocket."""
        try:
            if guild_id not in self.voice_states:
                logging.error(f"No voice state found for guild {guild_id}")
                return

            # Get the existing WebSocket
            _, old_ws = self.voice_states[guild_id]
            
            # Close the old connection if it exists
            if old_ws:
                try:
                    old_ws.close()
                except:
                    pass

            # Initialize new OpenAI WebSocket connection
            new_ws = websocket.WebSocketApp(
                url,
                header=headers,
                on_open=self.get_on_openai_open(guild_id),
                on_message=self.on_openai_message,
                on_error=self.on_openai_error,
                on_close=self.on_openai_close
            )
            
            # Enable ping/pong for connection keepalive
            new_ws.keep_running = True
            new_ws.ping_interval = 30
            new_ws.ping_timeout = 10
            
            # Start the WebSocket connection in a separate thread
            ws_thread = threading.Thread(target=lambda: self.run_websocket(new_ws))
            ws_thread.daemon = True
            ws_thread.start()

            # Update the voice state with the new WebSocket
            voice_state = self.voice_states[guild_id][0]
            self.voice_states[guild_id] = (voice_state, new_ws)

            # Wait for the new connection to be ready
            if not self.ws_ready[guild_id].wait(timeout=5.0):
                logging.error(f"Reconnection timed out for guild {guild_id}")
                return False

            logging.info(f"Successfully reconnected WebSocket for guild {guild_id}")
            return True

        except Exception as e:
            logging.error(f"Error reconnecting WebSocket: {e}")
            return False

    def send_audio_to_openai(self, openai_ws: websocket.WebSocketApp, message: dict, guild_id: int) -> bool:
        """Safely send audio data to OpenAI with connection handling."""
        try:
            if not openai_ws or not openai_ws.sock or not openai_ws.sock.connected:
                logging.warning("WebSocket not connected, attempting reconnect")
                if not self.reconnect_openai_ws(guild_id):
                    return False
                # Get the new WebSocket
                openai_ws = self.voice_states[guild_id][1]

            # Try to send the message
            try:
                openai_ws.sock.send(json.dumps(message).encode())
                return True
            except (websocket.WebSocketConnectionClosedException, ssl.SSLError) as e:
                logging.error(f"Error sending data: {e}")
                self.ws_ready[guild_id].clear()
                return False

        except Exception as e:
            logging.error(f"Error in send_audio_to_openai: {e}")
            return False

    def stream_audio(self, voice_state: ActiveVoiceState, openai_ws: websocket.WebSocketApp, guild_id: int):
        """Stream audio from the voice connection to OpenAI"""
        if not voice_state or not voice_state.ws or not voice_state.ws.socket:
            logging.error("Voice connection or WebSocket not available")
            return

        # Wait for OpenAI WebSocket to be ready
        if not self.ws_ready[guild_id].wait(timeout=10.0):
            logging.error("OpenAI WebSocket connection timed out")
            return

        try:
            sock = voice_state.ws.socket
            sock.setblocking(False)

            # Clear any existing data in the socket
            try:
                while sock.recv(4096):
                    pass
            except (BlockingIOError, ConnectionError):
                pass

            logging.info("Starting audio stream for guild %d", guild_id)
            self.recording = True
            packet_count = 0
            last_log_time = time.time()

            while self.recording:
                try:
                    ready, _, err = select.select([sock], [], [sock], 0.01)
                    if err:
                        logging.error("Socket error while streaming: %s", err)
                        break
                    if not ready:
                        continue

                    data = sock.recv(4096)
                    if data:
                        packet_count += 1
                        # Log stats every 5 seconds
                        current_time = time.time()
                        if current_time - last_log_time >= 5:
                            logging.info(f"Processed {packet_count} packets in last 5 seconds")
                            packet_count = 0
                            last_log_time = current_time
                            
                        self.process_audio_data(data, openai_ws, guild_id)
                except BlockingIOError:
                    continue
                except (ConnectionError, OSError) as e:
                    logging.error(f"Socket error while streaming: {e}")
                    break

        except Exception as e:
            logging.error(f"Error in audio stream: {e}")
        finally:
            self.recording = False
            logging.info("Stopped audio stream for guild %d", guild_id)

    def encode_pcm_to_opus(self, pcm_data: bytes) -> bytes:
        """Encode PCM data to Opus format."""
        try:
            # Create buffer for encoded Opus data
            # Maximum size for a 20ms frame at 48kHz stereo
            max_data_bytes = 1275  # Typical max size for Opus frame
            opus_buffer = (ctypes.c_uint8 * max_data_bytes)()
            
            # Convert PCM bytes to ctypes array
            frame_size = FRAME_SIZE
            pcm_array = (ctypes.c_int16 * frame_size)()
            ctypes.memmove(pcm_array, pcm_data, min(len(pcm_data), len(pcm_array) * 2))
            
            # Encode PCM to Opus
            encoded_bytes = opus_encode(
                self.encoder,
                pcm_array,
                frame_size,
                opus_buffer,
                max_data_bytes
            )
            
            if encoded_bytes < 0:
                logging.error(f"Error encoding PCM to Opus: {encoded_bytes}")
                return b''
                
            # Return the encoded data
            return bytes(opus_buffer[:encoded_bytes])
        except Exception as e:
            logging.error(f"Error encoding PCM to Opus: {e}")
            return b''

    async def send_audio_packet(self, voice_state: ActiveVoiceState, pcm_data: bytes):
        """Send an audio packet to Discord."""
        try:
            if not voice_state or not voice_state.ws or not voice_state.ws.socket:
                logging.error("Voice state, WebSocket, or socket not available")
                return
                
            # Log initial packet info
            logging.info(f"Preparing to send audio packet of {len(pcm_data)} bytes")
                
            # Send speaking packet first
            speaking_packet = {
                "op": 5,  # Speaking opcode
                "d": {
                    "speaking": 1,  # 1 for speaking, 0 for not speaking
                    "delay": 0,
                    "ssrc": getattr(voice_state.ws, 'ssrc', 0)
                }
            }
            voice_state.ws.socket.send(json.dumps(speaking_packet).encode())
            logging.debug("Sent speaking packet")
                
            # Convert PCM bytes to ctypes array
            frame_size = FRAME_SIZE  # 20ms at 48kHz
            pcm_array = (ctypes.c_int16 * (frame_size * CHANNELS))()  # Account for stereo
            
            # Only process one frame at a time
            bytes_per_frame = frame_size * CHANNELS * 2  # 2 bytes per sample
            if len(pcm_data) < bytes_per_frame:
                logging.warning(f"PCM data too small for a frame: {len(pcm_data)} bytes")
                # Send stop speaking packet since we're done
                stop_speaking_packet = {
                    "op": 5,
                    "d": {
                        "speaking": 0,  # 0 for not speaking
                        "delay": 0,
                        "ssrc": getattr(voice_state.ws, 'ssrc', 0)
                    }
                }
                voice_state.ws.socket.send(json.dumps(stop_speaking_packet).encode())
                return
                
            # Copy just one frame of data
            ctypes.memmove(pcm_array, pcm_data[:bytes_per_frame], bytes_per_frame)
            logging.debug(f"Copied {bytes_per_frame} bytes into PCM array")
            
            # Create buffer for encoded Opus data
            max_data_bytes = 1275  # Typical max size for Opus frame
            opus_buffer = (ctypes.c_uint8 * max_data_bytes)()
            
            # Encode PCM to Opus
            encoded_bytes = opus_encode(
                self.encoder,
                pcm_array,
                frame_size,
                opus_buffer,
                max_data_bytes
            )
            
            if encoded_bytes < 0:
                logging.error(f"Error encoding audio to Opus: {encoded_bytes}")
                return
                
            # Get the encoded data
            encoded_data = bytes(opus_buffer[:encoded_bytes])
            logging.info(f"Encoded {frame_size} PCM samples to {len(encoded_data)} bytes of Opus data")
            
            # Get sequence and timestamp
            sequence = getattr(voice_state.ws, 'sequence', 0)
            timestamp = getattr(voice_state.ws, 'timestamp', 0)
            ssrc = getattr(voice_state.ws, 'ssrc', 0)
            logging.debug(f"Using sequence: {sequence}, timestamp: {timestamp}, ssrc: {ssrc}")
            
            # Create RTP header
            header = bytearray(12)  # 12 byte header
            header[0] = 0x80  # Version
            header[1] = 0x78  # Type (0x78 for voice)
            header[2:4] = sequence.to_bytes(2, byteorder='big')
            header[4:8] = timestamp.to_bytes(4, byteorder='big')
            header[8:12] = ssrc.to_bytes(4, byteorder='big')
            
            # Create nonce for encryption
            nonce = bytearray(24)  # 24 bytes for xsalsa20_poly1305
            nonce[0:12] = header  # Copy header into nonce
            nonce[12:] = self._incr_nonce.to_bytes(12, byteorder='little')  # Add counter
            self._incr_nonce += 1
            
            # Get the secret key from the voice state
            secret_key = getattr(voice_state.ws, 'secret', None) or getattr(voice_state.ws, 'secret_key', None)
            if not secret_key:
                raise RuntimeError("No secret key available from voice connection")
            # Convert secret key to bytes
            if isinstance(secret_key, str):
                secret_key = bytes.fromhex(secret_key)
            elif isinstance(secret_key, list):
                secret_key = bytes(secret_key)
            # Ensure secret key is exactly 32 bytes
            if len(secret_key) != 32:
                raise ValueError(f"Secret key must be 32 bytes, got {len(secret_key)} bytes")
            
            # Create a buffer for the encrypted data
            encrypted_data = bytearray(len(encoded_data) + 16)  # +16 for the Poly1305 tag
            
            # Encrypt using XSalsa20 Poly1305 Lite
            result = nacl.bindings.crypto_secretbox(
                bytes(nonce),
                encoded_data,
                secret_key
            )
            
            if not result:
                raise ValueError("Encryption failed")
            
            # Send the packet
            packet = header + bytes(result)
            logging.info(f"Sending audio packet: {len(packet)} bytes (header: 12, opus: {len(encrypted_data)})")
            voice_state.ws.socket.send(packet)
            
            # Update sequence and timestamp
            voice_state.ws.sequence = (sequence + 1) & 0xFFFF  # Wrap at 16 bits
            voice_state.ws.timestamp = (timestamp + frame_size) & 0xFFFFFFFF  # Wrap at 32 bits
            
            # If there's more data, schedule the next frame
            remaining_bytes = len(pcm_data) - bytes_per_frame
            if remaining_bytes > 0:
                logging.debug(f"Scheduling next frame, {remaining_bytes} bytes remaining")
                asyncio.get_event_loop().call_soon_threadsafe(
                    self.send_audio_packet,
                    voice_state,
                    pcm_data[bytes_per_frame:]
                )
            else:
                # Send stop speaking packet since we're done with all frames
                stop_speaking_packet = {
                    "op": 5,
                    "d": {
                        "speaking": 0,  # 0 for not speaking
                        "delay": 0,
                        "ssrc": getattr(voice_state.ws, 'ssrc', 0)
                    }
                }
                voice_state.ws.socket.send(json.dumps(stop_speaking_packet).encode())
                logging.debug("Sent stop speaking packet")
        except Exception as e:
            logging.error(f"Error sending audio packet: {e}", exc_info=True)

    def run_websocket(self, ws):
        """Run the WebSocket with its own event loop"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        ws.run_forever(ping_interval=30, ping_timeout=10)
        loop.close()

    def on_openai_message(self, ws, message):
        """Handle messages from OpenAI"""
        try:
            msg = json.loads(message)
            msg_type = msg.get("type", "")
            
            if msg_type == "session.created":
                logging.info("Session created successfully")
                if hasattr(ws, 'guild_id') and ws.guild_id in self.ws_ready:
                    self.ws_ready[ws.guild_id].set()
                    logging.info("WebSocket ready event set for guild %d after session creation", ws.guild_id)
                else:
                    logging.error("Could not set WebSocket ready event - missing guild_id or event")
                    
            elif msg_type == "error":
                error_msg = msg.get("error", {}).get("message", "Unknown error")
                error_code = msg.get("error", {}).get("code", "Unknown code")
                logging.error("OpenAI error: %s (code: %s)", error_msg, error_code)
                if hasattr(ws, 'guild_id') and ws.guild_id in self.ws_ready:
                    self.ws_ready[ws.guild_id].clear()
            
            elif msg_type == "response.created":
                logging.info("OpenAI started speaking")
                logging.debug("Full response.created message: %s", json.dumps(msg, indent=2))
            
            elif msg_type == "response.done":
                logging.info("OpenAI finished speaking")
                logging.debug("Full response.done message: %s", json.dumps(msg, indent=2))
            
            elif msg_type == "response.text.delta":
                text = msg.get("text", "")
                logging.info(f"OpenAI text response: {text}")
                logging.debug("Full response.text message: %s", json.dumps(msg, indent=2))
            
            elif msg_type == "response.audio.delta":
                try:
                    # Get the base64 encoded audio data
                    b64encoded_audio = msg.get("delta", "")
                    logging.info(f"Received audio delta with {len(b64encoded_audio)} bytes of base64 data")
                    
                    if not b64encoded_audio:
                        logging.warning("Received empty audio delta")
                        return
                        
                    # Decode base64 to PCM bytes
                    pcm_data = base64.b64decode(b64encoded_audio)
                    logging.info(f"Decoded {len(pcm_data)} bytes of PCM data")
                    
                    # Get the voice state for this guild
                    if not hasattr(ws, 'guild_id'):
                        logging.error("No guild_id found in WebSocket for audio response")
                        return
                        
                    guild_id = ws.guild_id
                    if guild_id not in self.voice_states:
                        logging.error(f"No voice state found for guild {guild_id}")
                        return
                        
                    # Resample from 24kHz to 48kHz
                    resampled_data = resample_audio(pcm_data, OPENAI_SAMPLE_RATE, DISCORD_SAMPLE_RATE)
                    logging.info(f"Resampled to {len(resampled_data)} bytes of PCM data")
                        
                    # Initialize queue if needed
                    if guild_id not in self.audio_queue:
                        logging.warning(f"Creating new audio queue for guild {guild_id}")
                        self.audio_queue[guild_id] = asyncio.Queue(maxsize=100)
                    
                    # Get the queue
                    queue = self.audio_queue[guild_id]
                    
                    # Try to add to queue without blocking
                    try:
                        # Use put_nowait to avoid blocking
                        queue.put_nowait(resampled_data)
                        logging.info(f"Added {len(resampled_data)} bytes to queue (size: {queue.qsize()})")
                    except asyncio.QueueFull:
                        logging.warning(f"Queue full for guild {guild_id}, dropping audio packet")
                    except Exception as e:
                        logging.error(f"Error adding to queue: {e}", exc_info=True)
                    
                except Exception as e:
                    logging.error(f"Error processing audio response: {e}", exc_info=True)
            
            else:
                logging.debug(f"Received message type: {msg_type}")
                # logging.debug("Full message: %s", json.dumps(msg, indent=2))
                
        except Exception as e:
            logging.error("Error processing OpenAI message: %s", e)

    def on_openai_error(self, ws, error):
        """Handle OpenAI websocket errors"""
        logging.error("OpenAI WebSocket error: %s", error)
        # If we have a guild_id in the ws object, mark it as not ready
        if hasattr(ws, 'guild_id') and ws.guild_id in self.ws_ready:
            self.ws_ready[ws.guild_id].clear()

    def on_openai_close(self, ws, close_status_code, close_msg):
        """Handle OpenAI websocket closure"""
        logging.warning("OpenAI WebSocket connection closed with code %s: %s", close_status_code, close_msg)
        # If we have a guild_id in the ws object, mark it as not ready
        if hasattr(ws, 'guild_id') and ws.guild_id in self.ws_ready:
            self.ws_ready[ws.guild_id].clear()

    def get_on_openai_open(self, guild_id: int):
        """Get on_open handler for specific guild"""
        def on_open(ws):
            try:
                logging.info("OpenAI WebSocket connection opened for guild %d", guild_id)
                # Store guild_id in the websocket object for error handling
                ws.guild_id = guild_id
                
                if guild_id in self.ws_ready:
                    # Send initial configuration
                    session_config = {
                        "type": "session.update",
                        "session": {
                            "turn_detection": {
                                "type": "server_vad",
                                "threshold": 0.5,  # Match OpenAI's setting
                                "prefix_padding_ms": 300,  # Match OpenAI's setting
                                "silence_duration_ms": 200,  # Match OpenAI's setting
                                "create_response": True,
                                "interrupt_response": True
                            },
                            "voice": "alloy",
                            "instructions": "You are a helpful AI assistant in a Discord voice chat. Keep your responses concise and natural.",
                            "modalities": ["audio", "text"],
                            "temperature": 0.8,
                            "input_audio_format": "pcm16",  # 16-bit PCM
                            "output_audio_format": "pcm16",  # 16-bit PCM
                            # We cannot specify the sample rate or channels here, it's handled by the voice state
                        }
                    }
                    if ws and ws.sock:
                        logging.debug("Sending session configuration: %s", json.dumps(session_config, indent=2))
                        ws.sock.send(json.dumps(session_config).encode())
                        logging.info("Sent session configuration to OpenAI")
                        
                    else:
                        logging.error("WebSocket or socket not available for guild %d", guild_id)
                else:
                    logging.error("No WebSocket ready event found for guild %d", guild_id)
            except Exception as e:
                logging.error("Error in OpenAI WebSocket on_open: %s", str(e), exc_info=True)
                if guild_id in self.ws_ready:
                    self.ws_ready[guild_id].clear()
        return on_open

    @slash_command(
        name="join",
        description="have compubot join my voice channel",
        options=[]
    )
    async def join_voice(self, ctx: SlashContext) -> None:
        """Join the user's voice channel."""
        if not isinstance(ctx.author, Member) or not ctx.author.voice:
            await ctx.send("You must be in a voice channel to use this command!")
            return

        try:
            logging.info("Attempting to join voice channel for guild %s", ctx.guild_id)
            # Get the voice state and connect
            voice_state = await ctx.author.voice.channel.connect()
            guild_id = int(ctx.guild_id) if ctx.guild_id else 0
            
            # Wait for voice connection to be ready
            for i in range(10):  # Try for up to 5 seconds
                if voice_state.connected:
                    logging.info("Voice connection is ready after %d attempts", i + 1)
                    break
                logging.debug("Waiting for voice connection... attempt %d", i + 1)
                await asyncio.sleep(0.5)
            
            if not voice_state.connected:
                logging.error("Voice connection failed to become ready")
                await ctx.send("Failed to establish voice connection. Please try again.")
                return

            # Create the recorder
            recorder = voice_state.create_recorder()
            voice_state.recorder = recorder  # type: ignore
            
            # Initialize audio queue for this guild with a max size
            self.audio_queue[guild_id] = asyncio.Queue(maxsize=100)  # Limit queue size to prevent memory issues
            
            # Ensure queue processing task is running
            self.start_queue_processing()
            
            # Create the ready event before initializing the WebSocket
            self.ws_ready[guild_id] = threading.Event()

            # Initialize OpenAI WebSocket connection
            openai_ws = websocket.WebSocketApp(
                url,
                header=headers,
                on_open=self.get_on_openai_open(guild_id),
                on_message=self.on_openai_message,
                on_error=self.on_openai_error,
                on_close=self.on_openai_close
            )
            
            # Enable ping/pong for connection keepalive
            openai_ws.keep_running = True
            openai_ws.ping_interval = 30
            openai_ws.ping_timeout = 10
            
            # Start the WebSocket connection in a separate thread
            ws_thread = threading.Thread(target=lambda: self.run_websocket(openai_ws))
            ws_thread.daemon = True
            ws_thread.start()

            # Wait for WebSocket to be ready with a longer timeout
            logging.info("Waiting for ws connection")
            if not self.ws_ready[guild_id].wait(timeout=20.0):
                logging.error("OpenAI WebSocket connection timed out for guild %d", guild_id)
                await ctx.send("Failed to establish connection to AI service. Please try again.")
                # Clean up the failed connection
                openai_ws.close()
                if guild_id in self.ws_ready:
                    del self.ws_ready[guild_id]
                return

            # Store voice state and WebSocket for this guild
            self.voice_states[guild_id] = (voice_state, openai_ws)

            # Start streaming audio in a separate thread
            self.socket_threads[guild_id] = threading.Thread(
                target=self.stream_audio,
                args=(voice_state, openai_ws, guild_id),
                daemon=True
            )
            self.socket_threads[guild_id].start()

            await ctx.send("Connected to voice channel and started streaming!")
            logging.info("Successfully joined voice channel for guild %d", guild_id)

        except Exception as e:
            logging.error("Failed to join voice channel: %s", e)
            # Clean up any partial connections/state
            if guild_id in self.voice_states:
                del self.voice_states[guild_id]
            if guild_id in self.socket_threads:
                del self.socket_threads[guild_id]
            if guild_id in self.ws_ready:
                del self.ws_ready[guild_id]
            
            await ctx.send(f"Failed to join voice channel: {str(e)}")
            return

    @slash_command(
        name="leave",
        description="have compubot leave the voice channel",
        options=[]
    )
    async def leave_voice(self, ctx: SlashContext):
        guild_id = int(ctx.guild_id) if ctx.guild_id else 0
        if guild_id not in self.voice_states:
            await ctx.send("I'm not in a voice channel!")
            return
            
        try:
            voice_connection, openai_ws = self.voice_states[guild_id]
            self.recording = False
            
            # Wait for audio streaming thread to finish
            if guild_id in self.socket_threads:
                self.socket_threads[guild_id].join(timeout=1.0)
                del self.socket_threads[guild_id]
            
            # Clean up WebSocket ready event
            if guild_id in self.ws_ready:
                del self.ws_ready[guild_id]
                
            # Write remaining PCM data to WAV file and close files
            if guild_id in self.recording_files:
                if self.wav_buffer[guild_id]:
                    self.recording_files[guild_id]['wav'].write(self.wav_buffer[guild_id])
                
                # Update WAV header with final size
                wav_file = self.recording_files[guild_id]['wav']
                wav_file.seek(0)
                self.write_wav_header(wav_file, self.total_samples[guild_id], OPENAI_SAMPLE_RATE, CHANNELS)
                
                # Close all files
                for file in self.recording_files[guild_id].values():
                    file.close()
                del self.recording_files[guild_id]
                del self.wav_buffer[guild_id]
                del self.total_samples[guild_id]
                
            await voice_connection.disconnect()
            openai_ws.close()
            del self.voice_states[guild_id]
            await ctx.send("Left the voice channel!")
        except Exception as e:
            await ctx.send(f"Error leaving voice channel: {str(e)}")

    @listen()
    async def on_voice_state_update(self, event):
        # Handle voice state updates here (join/leave/mute/etc)
        pass

    def __del__(self):
        """Clean up Opus encoder and decoder when the object is destroyed"""
        if hasattr(self, 'decoder'):
            opus_decoder_destroy(self.decoder)
        if hasattr(self, 'encoder'):
            opus_encoder_destroy(self.encoder)

