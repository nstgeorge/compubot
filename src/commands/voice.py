import asyncio
import base64
import ctypes
import json
import logging
import os
import select
import ssl
import struct
import threading
import time
import wave
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import websocket
from interactions import (ActiveVoiceState, Extension, Member, SlashContext,
                          listen, slash_command)
from interactions.api.voice.encryption import Decryption, Encryption
from interactions.api.voice.opus import (Decoder, Encoder, EncoderCTL,
                                         EncoderStructurePointer, OpusConfig,
                                         OpusError, load_opus)

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
    """Resample audio data from one sample rate to another and convert to mono if needed."""
    # Convert bytes to numpy array of 16-bit integers
    audio_array = np.frombuffer(audio_data, dtype=np.int16)
    
    # Convert stereo to mono by reshaping and averaging channels
    if len(audio_array) % 2 == 0:  # Ensure we have pairs of samples
        audio_array = audio_array.reshape(-1, 2)
        audio_array = audio_array.mean(axis=1).astype(np.int16)
    
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
        self.queue_tasks: Dict[int, asyncio.Task] = {}  # Store reference to queue processing tasks per guild
        self.last_timestamps = {}  # Track last timestamp per SSRC
        self.speaking_states: Dict[int, bool] = {}  # Track speaking state per guild
        self.wav_files: Dict[int, tuple[wave.Wave_write, wave.Wave_write]] = {}  # Track WAV files per guild
        self.reconnect_counts: Dict[int, int] = {}  # Track reconnection attempts per guild
        
        # Initialize Opus decoder and encoder
        try:
            # Initialize decoders as defaultdict
            self.decoders = defaultdict(lambda: Decoder())
            
            # Initialize encoders as regular dict
            self.encoders = {}
            
            # Initialize encryption/decryption (will be configured per guild)
            self.encryptor: Dict[int, Encryption] = {}
            self.decryptor: Dict[int, Decryption] = {}
            
        except Exception as e:
            logging.error(f"Failed to initialize Opus encoder/decoder: {e}")
            # Clean up any partially initialized resources
            self.decoders.clear()
            self.encoders.clear()
            raise

    def encode_pcm_to_opus(self, pcm_data: bytes, guild_id: int, ssrc_key: str) -> Optional[bytes]:
        """Encode PCM data to Opus format"""
        # Create encoder if it doesn't exist
        if ssrc_key not in self.encoders:
            print("[VOICE DEBUG] Creating new encoder for SSRC", ssrc_key)
            self.encoders[ssrc_key] = Encoder()
            print("[VOICE DEBUG] Encoder created successfully")
        
        # Get encoder
        encoder = self.encoders[ssrc_key]
        
        # Verify input data size matches expected frame size
        expected_size = FRAME_SIZE * CHANNELS * 2  # 2 bytes per sample = 3840 bytes
        if len(pcm_data) != expected_size:
            logging.error(f"PCM data size mismatch: got {len(pcm_data)} bytes, expected {expected_size}")
            return None
        
        # Ensure PCM data is properly formatted (16-bit signed integers)
        try:
            # Convert to numpy array for processing
            audio_array = np.frombuffer(pcm_data, dtype=np.int16)
            
            # Ensure values are within valid range (-32768 to 32767)
            audio_array = np.clip(audio_array, -32768, 32767)
            
            # Convert back to bytes
            pcm_data = audio_array.tobytes()
        except Exception as e:
            logging.error(f"Failed to process PCM data: {e}")
            return None
        
        # Encode PCM to Opus
        opus_data = encoder.encode(pcm_data)
        if not opus_data:
            logging.error("Failed to encode PCM data")
            return None
        
        return opus_data

    async def process_discord_audio_queue(self, guild_id: int):
        """Process audio packets from the queue and send them to Discord."""
        try:
            logging.info(f"Starting audio queue processing task for guild {guild_id}")
            while True:
                if guild_id not in self.voice_states:
                    logging.info(f"Voice state gone for guild {guild_id}, stopping queue processing")
                    break
                    
                voice_state = self.voice_states[guild_id][0]
                if not voice_state or not voice_state.ws or not voice_state.ws.socket:
                    logging.error("Voice connection not available")
                    await asyncio.sleep(1)
                    continue
                
                try:
                    # Get data from queue with a timeout
                    try:
                        pcm_data = await asyncio.wait_for(
                            self.audio_queue[guild_id].get(),
                            timeout=0.5  # Wait up to 0.5 seconds for data
                        )
                        logging.debug(f"Got {len(pcm_data)} bytes from queue for guild {guild_id}")
                    except asyncio.TimeoutError:
                        # No data available, just continue
                        continue
                    
                    # Process and send the audio data
                    await self.send_audio_packet(voice_state, pcm_data)
                    logging.debug(f"Sent audio packet to Discord for guild {guild_id}")
                    
                    # Mark task as done
                    self.audio_queue[guild_id].task_done()
                    
                except Exception as e:
                    logging.error(f"Error processing audio queue: {type(e).__name__}: {str(e)}", exc_info=True)
                    await asyncio.sleep(0.1)  # Sleep longer on error
                    
        except Exception as e:
            logging.error(f"Fatal error in audio queue processing: {type(e).__name__}: {str(e)}", exc_info=True)
        finally:
            if guild_id in self.queue_tasks:
                del self.queue_tasks[guild_id]
            logging.info(f"Audio queue processing task stopped for guild {guild_id}")

    def start_discord_audio_queue(self, guild_id: int):
        """Start the audio queue processing task for a guild."""
        if guild_id not in self.queue_tasks or self.queue_tasks[guild_id].done():
            self.queue_tasks[guild_id] = asyncio.create_task(self.process_discord_audio_queue(guild_id))
            logging.info(f"Started audio queue processing for guild {guild_id}")

    def decode_opus_to_pcm(self, opus_data: bytes, guild_id: int, nonce: bytes, ssrc_key: str) -> Optional[bytes]:
        """Decode Opus data to PCM format with optional decryption"""
        if not self.decoders or not self.decoders.get(ssrc_key):
            logging.error(f"No decoder found for SSRC {ssrc_key}")
            return None
            
        try:
            # Decrypt if we have a decryptor for this guild
            if guild_id in self.decryptor and self.decryptor[guild_id]:
                try:
                    opus_data = self.decryptor[guild_id].decrypt("xsalsa20_poly1305_lite", b"", opus_data)
                except Exception as e:
                    logging.error(f"Failed to decrypt Opus data: {e}")
                    return None
            
            # Decode Opus to PCM using SSRC-specific decoder
            pcm_data = self.decoders[ssrc_key].decode(opus_data)
            if not pcm_data:
                logging.error("Failed to decode Opus data")
                return None
                
            # Verify output data size matches expected frame size
            expected_size = self.decoders[ssrc_key].frame_size
            if len(pcm_data) != expected_size:
                logging.error(f"Decoded PCM data size mismatch: {len(pcm_data)} != {expected_size}")
                return None
                
            return pcm_data
        except Exception as e:
            logging.error(f"Failed to decode Opus to PCM: {e}")
            return None

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
                if not self.reconnect_openai_ws(guild_id):
                    logging.error("Failed to reconnect to OpenAI")
                    return
                openai_ws = self.voice_states[guild_id][1]

            # Only process if WebSocket is ready
            if not self.ws_ready[guild_id].is_set():
                logging.debug("OpenAI WebSocket not ready yet, skipping voice packet")
                return

            # Check packet type (should be 0x78 for voice data)
            packet_type = data[1]
            if packet_type != 0x78:  # Not a voice packet
                return

            # Extract header info
            sequence = int.from_bytes(data[2:4], byteorder='big')
            timestamp = int.from_bytes(data[4:8], byteorder='big')
            ssrc = int.from_bytes(data[8:12], byteorder='big')
            ssrc_key = f"{guild_id}_{ssrc}"

            # Get raw opus data and decrypt
            raw_opus = data[12:]
            decrypted_data = self.decryptor[guild_id].decrypt("xsalsa20_poly1305_lite", b"", raw_opus)
            
            # Handle RTP header extension
            opus_data = decrypted_data
            if len(decrypted_data) >= 4 and decrypted_data[0] == 0xBE and decrypted_data[1] == 0xDE:
                header_ext_length = int.from_bytes(decrypted_data[2:4], byteorder='big')
                ext_size = 4 + (4 * header_ext_length)
                if len(decrypted_data) >= ext_size:
                    opus_data = decrypted_data[ext_size:]

            # Decode to PCM
            pcm_data = self.decoders[ssrc_key].decode(opus_data)
            if pcm_data:
                # Write to WAV files if we're recording
                if guild_id in self.wav_files:
                    original_wav, resampled_wav = self.wav_files[guild_id]
                    original_wav.writeframes(pcm_data)
                    
                    # Resample for ChatGPT (48kHz -> 24kHz)
                    resampled_data = resample_audio(pcm_data, DISCORD_SAMPLE_RATE, OPENAI_SAMPLE_RATE)
                    resampled_wav.writeframes(resampled_data)
                    
                    # Convert to base64 and send to ChatGPT
                    encoded_audio = base64.b64encode(resampled_data).decode('ascii')
                    message = {
                        "type": "input_audio_buffer.append",
                        "audio": encoded_audio
                    }
                    
                    if not self.send_audio_to_openai(openai_ws, message, guild_id):
                        logging.error("Failed to send audio to ChatGPT")

        except Exception as e:
            logging.error(f"Error processing audio packet {sequence}: {e}", exc_info=True)

    async def send_audio_packet(self, voice_state: ActiveVoiceState, pcm_data: bytes):
        """Send an audio packet to Discord."""
        try:
            if not voice_state or not voice_state.ws or not voice_state.ws.socket:
                logging.error("Voice state, WebSocket, or socket not available")
                return
                
            # Get guild ID from voice state
            guild_id = voice_state.channel.guild.id
            ssrc = voice_state.ws.ssrc
            ssrc_key = f"{guild_id}_{ssrc}"  # Create unique key for this SSRC
                
            # Log initial packet info
            sequence = getattr(voice_state.ws, 'sequence', 0)
            if sequence % 500 == 0:  # Reduced from every 100 to every 500 packets
                logging.info(f"Processed {sequence} audio packets")

            # Send speaking packet only if we weren't speaking before
            if not self.speaking_states.get(guild_id, False):
                try:
                    await voice_state.ws.speaking(True)
                    self.speaking_states[guild_id] = True
                    logging.debug("Started speaking")
                except Exception as e:
                    logging.error(f"Failed to send speaking packet: {e}")
                    return

            # Process one frame at a time
            frame_size = FRAME_SIZE * CHANNELS * 2  # 2 bytes per sample = 3840 bytes
            frames = []
            start_time = time.perf_counter()
            loops = 0
            
            # Split data into proper frame sizes
            for i in range(0, len(pcm_data), frame_size):
                frame = pcm_data[i:i + frame_size]
                if len(frame) < frame_size:
                    # Pad last frame if needed
                    frame = frame + b'\x00' * (frame_size - len(frame))
                
                # Encode PCM to Opus using SSRC-specific encoder
                encoded_data = self.encode_pcm_to_opus(frame, guild_id, ssrc_key)
                if not encoded_data:
                    continue
                
                # Store frame data
                frames.append((encoded_data, sequence))
                
                # Update sequence for next packet
                sequence = (sequence + 1) & 0xFFFF  # Wrap at 16 bits
                voice_state.ws.timestamp = (voice_state.ws.timestamp + FRAME_SIZE) & 0xFFFFFFFF  # Wrap at 32 bits
            
            # Now send all frames with proper timing
            for opus_data, seq in frames:
                if seq % 500 == 0:  # Log less frequently
                    logging.info(f"Sending audio packet (sequence: {seq})")
                try:
                    # Check if socket is still valid before sending
                    if not voice_state.ws or not voice_state.ws.socket or voice_state.ws.socket.fileno() == -1:
                        logging.error("Voice socket disconnected, stopping audio send")
                        return
                        
                    # Use the voice gateway's send_packet method which handles packet generation and encryption
                    voice_state.ws.send_packet(opus_data, self.encoders[ssrc_key], needs_encode=False)
                    
                    # Use proper timing between packets
                    loops += 1
                    await asyncio.sleep(max(0.0, start_time + (FRAME_LENGTH/1000 * loops) - time.perf_counter()))
                    
                except (OSError, ConnectionError) as e:
                    logging.error(f"Failed to send audio packet: {e}")
                    # Try to stop speaking if we encounter a connection error
                    try:
                        if self.speaking_states.get(guild_id, False):
                            await voice_state.ws.speaking(False)
                            self.speaking_states[guild_id] = False
                            logging.debug("Stopped speaking due to connection error")
                    except:
                        pass
                    return
            
            # Update voice state sequence
            voice_state.ws.sequence = sequence
            
            # Send stop speaking packet since we're done
            if self.speaking_states.get(guild_id, False):
                try:
                    await voice_state.ws.speaking(False)
                    self.speaking_states[guild_id] = False
                    logging.debug("Stopped speaking")
                except Exception as e:
                    logging.error(f"Failed to send stop speaking packet: {e}")
            
        except Exception as e:
            logging.error(f"Error sending audio packet: {type(e).__name__}: {str(e)}", exc_info=True)

    def reconnect_openai_ws(self, guild_id: int):
        """Attempt to reconnect the OpenAI WebSocket."""
        try:
            if guild_id not in self.voice_states:
                logging.error(f"No voice state found for guild {guild_id}")
                return False

            # Check reconnection count
            reconnect_count = self.reconnect_counts.get(guild_id, 0)
            if reconnect_count >= 3:
                logging.error("Too many reconnection attempts, stopping reconnection")
                return False
            
            # Increment reconnection count
            self.reconnect_counts[guild_id] = reconnect_count + 1
            
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

            logging.info(f"Successfully reconnected WebSocket for guild {guild_id} (attempt {self.reconnect_counts[guild_id]})")
            return True

        except Exception as e:
            logging.error(f"Error reconnecting WebSocket: {e}")
            return False

    def send_audio_to_openai(self, openai_ws: websocket.WebSocketApp, message: dict, guild_id: int) -> bool:
        """Safely send audio data to OpenAI with connection handling."""
        try:
            # Check WebSocket state
            if not openai_ws or not openai_ws.sock or not openai_ws.sock.connected:
                logging.warning("WebSocket not connected, attempting reconnect")
                if not self.reconnect_openai_ws(guild_id):
                    return False
                
                # Get the new WebSocket and verify it
                if guild_id not in self.voice_states:
                    logging.error(f"No voice state found for guild {guild_id} after reconnect")
                    return False
                    
                openai_ws = self.voice_states[guild_id][1]

            # Try to send the message
            try:
                if not openai_ws.sock:
                    logging.error("WebSocket socket is None")
                    return False
                    
                json_data = json.dumps(message)
                openai_ws.sock.send(json_data.encode())
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

        try:
            # Create debug directory if it doesn't exist
            debug_dir = Path("debug_audio")
            debug_dir.mkdir(exist_ok=True)
            
            # Create WAV files for this recording session - one for original and one for resampled
            timestamp = int(time.time())
            original_wav_path = debug_dir / f"recording_original_{guild_id}_{timestamp}.wav"
            resampled_wav_path = debug_dir / f"recording_resampled_{guild_id}_{timestamp}.wav"
            
            # Open original WAV file (48kHz)
            original_wav = wave.open(str(original_wav_path), "wb")
            original_wav.setnchannels(CHANNELS)
            original_wav.setsampwidth(2)  # 2 bytes per sample
            original_wav.setframerate(DISCORD_SAMPLE_RATE)
            
            # Open resampled WAV file (24kHz)
            resampled_wav = wave.open(str(resampled_wav_path), "wb")
            resampled_wav.setnchannels(CHANNELS)
            resampled_wav.setsampwidth(2)  # 2 bytes per sample
            resampled_wav.setframerate(OPENAI_SAMPLE_RATE)
            
            # Store both WAV files
            self.wav_files[guild_id] = (original_wav, resampled_wav)
            
            logging.info(f"Started recording to {original_wav_path} and {resampled_wav_path}")
            
            # Wait for OpenAI WebSocket to be ready
            if not self.ws_ready[guild_id].wait(timeout=10.0):
                logging.error("OpenAI WebSocket connection timed out")
                return

            sock = voice_state.ws.socket
            sock.setblocking(False)

            # Clear any existing data in the socket
            try:
                cleared_packets = 0
                while sock.recv(4096):
                    cleared_packets += 1
                logging.info(f"Cleared {cleared_packets} packets from socket buffer")
            except (BlockingIOError, ConnectionError):
                pass

            logging.info("Starting audio stream for guild %d", guild_id)
            self.recording = True
            packet_count = 0
            last_log_time = time.time()
            last_packet_time = time.time()

            while self.recording:
                try:
                    ready, _, err = select.select([sock], [], [sock], 0.01)
                    if err:
                        logging.error("Socket error while streaming: %s", err)
                        break
                    if not ready:
                        if time.time() - last_packet_time > 5:
                            logging.warning("No audio packets received in the last 5 seconds")
                            last_packet_time = time.time()
                        continue

                    data = sock.recv(4096)
                    if data:
                        last_packet_time = time.time()
                        packet_count += 1
                        current_time = time.time()
                        if current_time - last_log_time >= 5:
                            logging.info(f"Received {packet_count} packets in last 5 seconds")
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
            # Close both WAV files
            if guild_id in self.wav_files:
                original_wav, resampled_wav = self.wav_files[guild_id]
                original_wav.close()
                resampled_wav.close()
                del self.wav_files[guild_id]
            logging.info("Stopped audio stream for guild %d", guild_id)

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
                logging.info("OpenAI session created successfully")
                if hasattr(ws, 'guild_id') and ws.guild_id in self.ws_ready:
                    self.ws_ready[ws.guild_id].set()
                else:
                    logging.error("Could not set WebSocket ready event - missing guild_id")
                    
            elif msg_type == "error":
                error_msg = msg.get("error", {}).get("message", "Unknown error")
                error_code = msg.get("error", {}).get("code", "Unknown code")
                logging.error("OpenAI error: %s (code: %s)", error_msg, error_code)
                if hasattr(ws, 'guild_id') and ws.guild_id in self.ws_ready:
                    self.ws_ready[ws.guild_id].clear()
            
            elif msg_type == "response.created":
                logging.info("OpenAI started speaking")
            
            elif msg_type == "response.done":
                logging.info("OpenAI finished speaking: \"{}\"".format(msg["response"]["output"][0]["content"][0]["transcript"]))
            
            elif msg_type == "response.text.delta":
                text = msg.get("text", "")
                if text.strip():  # Only log non-empty text
                    logging.info(f"OpenAI: {text}")
            
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
                    
                    # Get the voice state for this guild
                    if not hasattr(ws, 'guild_id'):
                        logging.error("No guild_id found in WebSocket for audio response")
                        return
                        
                    guild_id = ws.guild_id
                    if guild_id not in self.voice_states:
                        logging.error(f"No voice state found for guild {guild_id}")
                        return
                        
                    # Convert from mono 24kHz to stereo 48kHz
                    # First convert to numpy array
                    audio_array = np.frombuffer(pcm_data, dtype=np.int16)
                    
                    # Resample from 24kHz to 48kHz
                    ratio = DISCORD_SAMPLE_RATE / OPENAI_SAMPLE_RATE
                    output_length = int(len(audio_array) * ratio)
                    original_time = np.linspace(0, len(audio_array), len(audio_array))
                    new_time = np.linspace(0, len(audio_array), output_length)
                    resampled = np.interp(new_time, original_time, audio_array)
                    
                    # Convert mono to stereo by duplicating the channel
                    stereo = np.column_stack((resampled, resampled)).flatten()
                    
                    # Convert back to 16-bit integers and then to bytes
                    resampled_data = stereo.astype(np.int16).tobytes()
                    
                    # Write to WAV files if we're recording
                    if guild_id in self.wav_files:
                        original_wav, resampled_wav = self.wav_files[guild_id]
                        original_wav.writeframes(pcm_data)
                        resampled_wav.writeframes(resampled_data)
                    
                    # Ensure queue exists and queue processing task is running
                    if guild_id not in self.audio_queue:
                        self.audio_queue[guild_id] = asyncio.Queue(maxsize=1000)
                    if guild_id not in self.queue_tasks or self.queue_tasks[guild_id].done():
                        self.start_discord_audio_queue(guild_id)
                    
                    # Add to queue without waiting for result
                    def queue_audio():
                        try:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            loop.run_until_complete(self.audio_queue[guild_id].put(resampled_data))
                            loop.close()
                            logging.debug(f"Queued {len(resampled_data)} bytes for Discord")
                        except Exception as e:
                            logging.error(f"Error queueing audio data: {type(e).__name__}: {str(e)}")
                    
                    # Run in a separate thread to avoid blocking
                    threading.Thread(target=queue_audio, daemon=True).start()
                    
                except Exception as e:
                    logging.error(f"Error processing audio response: {type(e).__name__}: {str(e)}", exc_info=True)
            
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
                                "threshold": 0.5,
                                "prefix_padding_ms": 300,
                                "silence_duration_ms": 200,
                                "create_response": True,
                                "interrupt_response": True
                            },
                            "voice": "alloy",
                            "instructions": "You are a helpful AI assistant in a Discord voice chat. Keep your responses concise and natural.",
                            "modalities": ["audio", "text"],
                            "temperature": 0.8,
                            "input_audio_format": "pcm16",  # 16-bit PCM
                            "output_audio_format": "pcm16"  # 16-bit PCM
                        }
                    }
                    if ws and ws.sock:
                        logging.info("Sending session configuration to OpenAI")
                        logging.debug(f"Config: {json.dumps(session_config, indent=2)}")
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

            # Check if voice gateway is properly initialized
            if not voice_state.ws or not hasattr(voice_state.ws, 'socket'):
                logging.error("Voice gateway not properly initialized")
                await ctx.send("Failed to initialize voice gateway. This might be a temporary issue.")
                return

            # Create the recorder
            recorder = voice_state.create_recorder()
            voice_state.recorder = recorder  # type: ignore
            
            # Initialize audio queue for this guild with a max size
            self.audio_queue[guild_id] = asyncio.Queue(maxsize=100)  # Limit queue size to prevent memory issues
            
            # Ensure queue processing task is running
            self.start_discord_audio_queue(guild_id)
            
            # Create the ready event before initializing the WebSocket
            self.ws_ready[guild_id] = threading.Event()

            # Set up encryption/decryption using the voice state's secret key
            if voice_state.ws and voice_state.ws.secret:
                self.encryptor[guild_id] = Encryption(voice_state.ws.secret)
                self.decryptor[guild_id] = Decryption(voice_state.ws.secret)
                logging.info("Initialized encryption for guild %d", guild_id)

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
            logging.error("Failed to join voice channel: %s", e, exc_info=True)
            # Clean up any partial connections/state
            if guild_id in self.voice_states:
                del self.voice_states[guild_id]
            if guild_id in self.socket_threads:
                del self.socket_threads[guild_id]
            if guild_id in self.ws_ready:
                del self.ws_ready[guild_id]
            if guild_id in self.encryptor:
                del self.encryptor[guild_id]
            if guild_id in self.decryptor:
                del self.decryptor[guild_id]
            
            error_msg = str(e)
            if "socket is not defined" in error_msg:
                await ctx.send("There seems to be an issue with the voice system. Please try again in a few minutes.")
            else:
                await ctx.send(f"Failed to join voice channel: {error_msg}")
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
            
            # Close both WAV files
            if guild_id in self.wav_files:
                original_wav, resampled_wav = self.wav_files[guild_id]
                original_wav.close()
                resampled_wav.close()
                del self.wav_files[guild_id]
            
            # Clean up WebSocket ready event
            if guild_id in self.ws_ready:
                del self.ws_ready[guild_id]
                
            # Clean up encryption/decryption
            if guild_id in self.encryptor:
                del self.encryptor[guild_id]
            if guild_id in self.decryptor:
                del self.decryptor[guild_id]
                
            # Clean up speaking state
            if guild_id in self.speaking_states:
                del self.speaking_states[guild_id]
                
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
        """Clean up resources when the object is destroyed"""
        # Clear the decoders and encoders dictionaries
        if hasattr(self, 'decoders'):
            self.decoders.clear()
        if hasattr(self, 'encoders'):
            self.encoders.clear()

