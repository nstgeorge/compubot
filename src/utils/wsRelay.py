import base64
import json
import struct
from typing import Dict, Literal

import websocket


class WebSocketRelay:
    def __init__(self):
        self.connections: Dict[str, Dict[str, websocket.WebSocketApp | Literal["openai", "discord"]]] = {}
        self.pairs: Dict[str, str] = {}  # Maps connection IDs to their paired connections
        
    async def handle_websocket(self, ws: websocket.WebSocketApp, connection_id: str, type: Literal["openai", "discord"]):
        self.connections[connection_id] = {
            "ws": ws,
            "type": type
        }
        
        if connection_id in self.pairs:
            if self.connections[self.pairs[connection_id]]["type"] == "openai":
                pass

        # finally:
        #     # Clean up on disconnect
        #     if connection_id in self.connections:
        #         del self.connections[connection_id]
        #     if connection_id in self.pairs:
        #         del self.pairs[connection_id]

    def openAI_on_message(self, connection_id: str):

        def on_message(ws, message):
            print("Received message:", json.dumps(message, indent=2))
        
        return on_message

    def openAI_on_open(self, connection_id: str):
        print("Connecting to connection_id" + connection_id)

        def on_open(ws):
            print("WebSocket with connection ID " + connection_id + " opened")
        
        return on_open
    
    def discord_on_message(self, connection_id: str):

        def on_message(ws, message):
            print("Received message:", json.dumps(message, indent=2))
        
        return on_message
    
    def float_to_16bit_pcm(self, float32_array):
      clipped = [max(-1.0, min(1.0, x)) for x in float32_array]
      pcm16 = b''.join(struct.pack('<h', int(x * 32767)) for x in clipped)
      return pcm16

    def base64_encode_audio(self, float32_array):
        pcm_bytes = self.float_to_16bit_pcm(float32_array)
        encoded = base64.b64encode(pcm_bytes).decode('ascii')
        return encoded

    def openAI_on_error(self, ws, error):
        print("Error:", error)

    def openAI_on_close(self, ws):
        print("Closed connection to OpenAI")
                
    def pair_connections(self, connection_id1: str, connection_id2: str):
        """Create a bidirectional pipe between two websocket connections"""
        self.pairs[connection_id1] = connection_id2
        self.pairs[connection_id2] = connection_id1