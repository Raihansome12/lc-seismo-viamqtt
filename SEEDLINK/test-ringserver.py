#!/usr/bin/env python3
"""
Dummy Seismometer Data Streamer
Generate fake geophone data and send to RingServer for testing
"""

import time
import socket
import struct
import threading
import numpy as np
from queue import Queue, Empty
from obspy import Stream, Trace, UTCDateTime
from obspy.core import Stats
import io

class SeismoStreamer:
    def __init__(self):
        # Config
        self.SAMPLE_RATE = 50  # Hz
        self.STATION_ID = "RPI01"
        self.NETWORK = "AM"
        self.LOCATION = "00"
        self.CHANNEL = "HHZ"
        self.RINGSERVER_HOST = "localhost"
        self.RINGSERVER_PORT = 16000

        self.BUFFER_SIZE = 100  # samples per packet
        self.data_queue = Queue()
        self.running = False

        # Internal phase for sine wave
        self.phase = 0.0
        self.freq = 1.0  # Hz

    def data_acquisition_thread(self):
        """Generate dummy data instead of reading from ADC"""
        print("Starting dummy data acquisition thread...")
        sample_interval = 1.0 / self.SAMPLE_RATE

        while self.running:
            start_time = time.time()

            # Generate a sine wave + random noise
            value = int(
                1000000 * np.sin(2 * np.pi * self.freq * self.phase) +
                np.random.normal(0, 5000)
            )
            self.phase += sample_interval
            timestamp = UTCDateTime.now()

            self.data_queue.put((timestamp, value))

            elapsed = time.time() - start_time
            sleep_time = sample_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def create_miniseed_packet(self, timestamps, data):
        """Create miniSEED packet from data buffer"""
        try:
            stats = Stats()
            stats.network = self.NETWORK
            stats.station = self.STATION_ID
            stats.location = self.LOCATION
            stats.channel = self.CHANNEL
            stats.starttime = timestamps[0]
            stats.sampling_rate = self.SAMPLE_RATE
            stats.npts = len(data)

            trace = Trace(data=np.array(data, dtype=np.int32), header=stats)
            stream = Stream([trace])

            buf = io.BytesIO()
            stream.write(buf, format='MSEED')
            return buf.getvalue()
        except Exception as e:
            print(f"Error creating miniSEED packet: {e}")
            return None

    def send_to_ringserver(self, miniseed_data):
        """Send miniSEED data to RingServer with a new connection for each packet"""
        try:
            # Create a new socket for each packet
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((self.RINGSERVER_HOST, self.RINGSERVER_PORT))
            
            # Create DataLink header for miniSEED packet
            # 'DL' - 2 bytes
            # 'M' - 1 byte for data type
            # data_length - 4 bytes, big-endian unsigned integer
            data_length = len(miniseed_data)
            header = b'DL' + b'M' + struct.pack('!I', data_length)
            
            # Send the header and the miniSEED data
            sock.sendall(header)
            sock.sendall(miniseed_data)
            
            # Close the socket immediately after sending the data
            sock.close()
            
            return True
            
        except Exception as e:
            print(f"Error sending to RingServer: {e}")
            return False

    def streaming_thread(self):
        """Thread for buffering and streaming data"""
        print("Starting streaming thread...")
        timestamps_buffer = []
        data_buffer = []

        while self.running:
            try:
                # Get data from queue (with timeout)
                timestamp, value = self.data_queue.get(timeout=1.0)
                timestamps_buffer.append(timestamp)
                data_buffer.append(value)

                if len(data_buffer) >= self.BUFFER_SIZE:
                    packet = self.create_miniseed_packet(timestamps_buffer, data_buffer)
                    if packet:
                        success = self.send_to_ringserver(packet)
                        if success:
                            print(f"Sent packet: {len(data_buffer)} samples, "
                                  f"time: {timestamps_buffer[0].strftime('%H:%M:%S')}")
                        else:
                            print("Failed to send packet to RingServer")
                    
                    timestamps_buffer.clear()
                    data_buffer.clear()
            except Empty:
                continue
            except Exception as e:
                print(f"Error in streaming thread: {e}")
                time.sleep(1)

    def start_streaming(self):
        """Start the streaming process"""
        print(f"Starting dummy seismometer streaming...")
        print(f"Station: {self.NETWORK}.{self.STATION_ID}.{self.LOCATION}.{self.CHANNEL}")
        print(f"Sample Rate: {self.SAMPLE_RATE} Hz")
        print(f"RingServer: {self.RINGSERVER_HOST}:{self.RINGSERVER_PORT}")

        self.running = True

        acq_thread = threading.Thread(target=self.data_acquisition_thread, daemon=True)
        stream_thread = threading.Thread(target=self.streaming_thread, daemon=True)

        acq_thread.start()
        stream_thread.start()

        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping streaming...")
            self.stop_streaming()

        acq_thread.join(timeout=5)
        stream_thread.join(timeout=5)

    def stop_streaming(self):
        self.running = False
        print("Streaming stopped.")

def main():
    try:
        streamer = SeismoStreamer()
        streamer.start_streaming()
    except KeyboardInterrupt:
        print("\nExiting...")

if __name__ == "__main__":
    main()