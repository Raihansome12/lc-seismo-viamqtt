# Seismic Station Configuration
# Raspberry Pi 3 Model B+ with ADS1256

# Station Information
STATION_CONFIG = {
    'network': 'XX',           # Network code
    'station': 'RPI01',        # Station code
    'location': '00',          # Location code
    'channel': 'HHZ',          # Channel code (HH = High gain, High sample rate, Z = vertical)
    'latitude': -6.2088,       # Station latitude (example: Jakarta)
    'longitude': 106.8456,     # Station longitude
    'elevation': 8.0,          # Elevation in meters
    'site_name': 'Raspberry Pi Test Station',
    'operator': 'Seismic Network Indonesia'
}

# ADS1256 Configuration
ADS1256_CONFIG = {
    'sample_rate': 50,         # Samples per second
    'gain': 1,                 # PGA gain
    'channel': 'DIFF_0_1',     # Differential channel AIN0-AIN1
    'spi_speed': 1000000,      # SPI speed in Hz
    'spi_device': 0            # SPI device number
}

# Data Acquisition Settings
ACQUISITION_CONFIG = {
    'duration': 60,            # Default acquisition duration (seconds)
    'buffer_size': 1000,       # Data buffer size
    'save_interval': 300,      # Save data every N seconds
    'data_format': 'mseed',    # Output format
    'compression': True        # Enable data compression
}

# Visualization Settings
VISUALIZATION_CONFIG = {
    'update_interval': 0.1,    # Plot update interval (seconds)
    'display_duration': 30,    # Time window to display (seconds)
    'max_points': 1500,        # Maximum points to plot
    'enable_filtering': True,  # Enable real-time filtering
    'filter_freq': [1.0, 20.0] # Bandpass filter frequencies
}

# Event Detection Settings
EVENT_DETECTION = {
    'sta_length': 1.0,         # Short-term average length (seconds)
    'lta_length': 10.0,        # Long-term average length (seconds)
    'trigger_on': 3.0,         # Trigger on threshold
    'trigger_off': 1.0,        # Trigger off threshold
    'min_event_duration': 2.0  # Minimum event duration (seconds)
}

# SeedLink Settings (for future integration)
SEEDLINK_CONFIG = {
    'server_host': 'localhost',
    'server_port': 18000,
    'stream_format': 'mseed',
    'packet_size': 512,
    'enable_compression': True
}