#!/usr/bin/env python3
"""
Seismometer Data Streamer
Streams data from Geophone+ADS1256 to RingServer for SeisComp
"""

import time
import socket
import struct
import threading
import numpy as np
from datetime import datetime, timezone
from queue import Queue, Empty
from pipyadc import ADS1256
from ADS1256_definitions import *
import waveshare_config
from obspy import Stream, Trace, UTCDateTime
from obspy.core import Stats
import io

class SeismoStreamer:
    def __init__(self):
        # Hardware configuration
        self.GEOPHONE = POS_AIN0 | NEG_AIN1
        self.SAMPLE_RATE = 50  # Hz
        self.GAIN = GAIN_1
        
        # Network configuration
        self.STATION_ID = "RPI01"
        self.NETWORK = "AM" 
        self.LOCATION = "00"
        self.CHANNEL = "HHZ"
        self.RINGSERVER_HOST = "localhost"
        self.RINGSERVER_PORT = 16000
        
        # Buffer configuration
        self.BUFFER_SIZE = 100  # samples per packet
        self.data_queue = Queue()
        self.running = False
        
        # Initialize ADC
        self.ads = None
        self.setup_adc()
        
    def setup_adc(self):
        """Configure the ADS1256 with specified parameters"""
        try:
            self.ads = ADS1256(waveshare_config)
            self.ads.drate = DRATE_50  # 50 SPS
            self.ads.pga_gain = 1      # Gain = 1
            self.ads.mux = self.GEOPHONE
            self.ads.sync()
            print("ADC initialized successfully")
        except Exception as e:
            print(f"Error initializing ADC: {e}")
            raise
    
    def data_acquisition_thread(self):
        """Thread for continuous data acquisition"""
        print("Starting data acquisition thread...")
        sample_interval = 1.0 / self.SAMPLE_RATE
        
        while self.running:
            try:
                start_time = time.time()
                
                # Read ADC value
                adc_counts = self.ads.read_async()
                timestamp = UTCDateTime.now()
                
                # Add to queue
                self.data_queue.put((timestamp, adc_counts))
                
                # Maintain sample rate
                elapsed = time.time() - start_time
                sleep_time = sample_interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    
            except Exception as e:
                print(f"Error in data acquisition: {e}")
                time.sleep(0.1)
    
    def create_miniseed_packet(self, timestamps, data):
        """Create miniSEED packet from data buffer"""
        try:
            # Create ObsPy trace
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
            
            # Convert to miniSEED bytes
            miniseed_buffer = io.BytesIO()
            stream.write(miniseed_buffer, format='MSEED')
            
            return miniseed_buffer.getvalue()
            
        except Exception as e:
            print(f"Error creating miniSEED packet: {e}")
            return None
    
    def send_to_ringserver(self, miniseed_data):
        """Send miniSEED data to RingServer"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((self.RINGSERVER_HOST, self.RINGSERVER_PORT))
            
            # Send data length first (4 bytes)
            data_length = len(miniseed_data)
            sock.send(struct.pack('!I', data_length))
            
            # Send miniSEED data
            sock.send(miniseed_data)
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
                try:
                    timestamp, adc_counts = self.data_queue.get(timeout=1.0)
                    timestamps_buffer.append(timestamp)
                    data_buffer.append(adc_counts)
                except Empty:
                    continue
                
                # When buffer is full, create and send packet
                if len(data_buffer) >= self.BUFFER_SIZE:
                    miniseed_packet = self.create_miniseed_packet(
                        timestamps_buffer, data_buffer
                    )
                    
                    if miniseed_packet:
                        success = self.send_to_ringserver(miniseed_packet)
                        if success:
                            print(f"Sent packet: {len(data_buffer)} samples, "
                                  f"time: {timestamps_buffer[0].strftime('%H:%M:%S')}")
                        else:
                            print("Failed to send packet to RingServer")
                    
                    # Clear buffers
                    timestamps_buffer.clear()
                    data_buffer.clear()
                    
            except Exception as e:
                print(f"Error in streaming thread: {e}")
                time.sleep(1)
    
    def start_streaming(self):
        """Start the streaming process"""
        print(f"Starting seismometer streaming...")
        print(f"Station: {self.NETWORK}.{self.STATION_ID}.{self.LOCATION}.{self.CHANNEL}")
        print(f"Sample Rate: {self.SAMPLE_RATE} Hz")
        print(f"RingServer: {self.RINGSERVER_HOST}:{self.RINGSERVER_PORT}")
        
        self.running = True
        
        # Start threads
        acq_thread = threading.Thread(target=self.data_acquisition_thread)
        stream_thread = threading.Thread(target=self.streaming_thread)
        
        acq_thread.daemon = True
        stream_thread.daemon = True
        
        acq_thread.start()
        stream_thread.start()
        
        try:
            # Keep main thread alive
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping streaming...")
            self.stop_streaming()
            
        # Wait for threads to finish
        acq_thread.join(timeout=5)
        stream_thread.join(timeout=5)
    
    def stop_streaming(self):
        """Stop the streaming process"""
        self.running = False
        if self.ads:
            self.ads.stop()
        print("Streaming stopped.")

def main():
    """Main function"""
    try:
        streamer = SeismoStreamer()
        streamer.start_streaming()
    except Exception as e:
        print(f"Error: {e}")
    except KeyboardInterrupt:
        print("\nExiting...")

if __name__ == "__main__":
    main()
