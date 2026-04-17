from datetime import datetime
import os
import uuid
import xml.dom.minidom as minidom
import xml.etree.ElementTree as ET

def create_seiscomp_inventory(
        station_code="STMKG", network_code="IA", 
        channel_code="SHZ", location_code="00", 
        latitude=-6.2088, longitude=106.8456, elevation=8.0,
        depth=0.0, sample_rate=50.0,
        sensor_description="EGL EG-4.5-II Geophone with ADS1256 on Raspberry Pi 3B+",
        start_date=None,
        digitizer_params=None):
    """
    Create a SeisComP format inventory XML for a custom seismometer setup
    
    Args:
        station_code: Station code (default: STMKG)
        network_code: Network code (default: IA)
        channel_code: Channel code (default: SHZ)
        location_code: Location code (default: "00")
        latitude: Latitude in degrees (default: -6.2088 - Jakarta)
        longitude: Longitude in degrees (default: 106.8456 - Jakarta)
        elevation: Elevation in meters (default: 8.0)
        depth: Sensor depth in meters (default: 0.0)
        sample_rate: Sample rate in Hz (default: 50.0)
        sensor_description: Sensor description
        start_date: Start date in datetime format or string (YYYY-MM-DD HH:MM:SS)
                   If None, will use current time
        digitizer_params: Parameters for the ADS1256 digitizer
        
    Returns:
        Root XML element in SeisComP format
    """
    # Handle start_date
    if start_date is None:
        start_date = datetime.now()
    elif isinstance(start_date, str):
        try:
            start_date = datetime.strptime(start_date, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            raise ValueError("start_date string must be in format 'YYYY-MM-DD HH:MM:SS'")
    elif not isinstance(start_date, datetime):
        raise TypeError("start_date must be either None, a datetime object, or a string in format 'YYYY-MM-DD HH:MM:SS'")
    
    # Format date for XML
    formatted_date = start_date.strftime("%Y-%m-%dT%H:%M:%S.0000Z")
    
    # Default digitizer parameters if not specified
    if digitizer_params is None:
        digitizer_params = {
            'adc_range': 5.0,
            'bit_depth': 24,
            'gain': 1,
            'filter_type': 'SINC3',
            'buffer_enabled': True,
            'dither_enabled': False
        }
    
    # Natural frequency and damping from EG-4.5-II specifications
    natural_freq = 4.5  # Hz
    damping = 0.6      # Damping factor
    
    # Calculate poles for geophone response
    w0 = 2 * 3.14159265359 * natural_freq  # Angular frequency in rad/s
    h = damping
    
    real_pole = -h * w0
    imag_pole = w0 * (1 - h**2)**0.5 if h < 1 else 0
    
    # Total gain calculation
    geophone_gain = 28.8  # V/(m/s) from specs
    
    # Calculate digitizer gain based on ADS1256 parameters
    adc_range = digitizer_params['adc_range']  # Volt (peak-to-peak)
    bit_depth = digitizer_params['bit_depth']  # 24-bit for ADS1256
    adc_gain = digitizer_params['gain']      # Configurable gain
    
    # Calculate counts per volt
    input_voltage_range = adc_range / adc_gain
    counts_per_volt = 2**(bit_depth-1) / (input_voltage_range/2)
    digitizer_gain = counts_per_volt * adc_gain
    
    # Total gain (sensor * digitizer)
    total_gain = geophone_gain * digitizer_gain
    
    # Create the XML structure for SeisComP format
    
    # Root elements
    root = ET.Element("seiscomp")
    root.set("xmlns", "http://geofon.gfz-potsdam.de/ns/seiscomp3-schema/0.11")
    root.set("version", "0.11")
    
    inventory = ET.SubElement(root, "Inventory")
    
    # Sensor element
    sensor = ET.SubElement(inventory, "sensor")
    sensor_public_id = f"{station_code}/SKRIPSI/EG4.5II"
    sensor.set("publicID", sensor_public_id)
    sensor.set("name", "SKRIPSI/EG4.5II")
    sensor.set("response", f"{sensor_public_id}/1")
    
    ET.SubElement(sensor, "model").text = "EG4.5II"
    ET.SubElement(sensor, "manufacturer").text = "EGL-GEO"
    ET.SubElement(sensor, "unit").text = "M/S"
    
    # Datalogger element
    datalogger = ET.SubElement(inventory, "datalogger")
    datalogger_public_id = f"{station_code}/SKRIPSI/ADS1256"
    datalogger.set("publicID", datalogger_public_id)
    datalogger.set("name", "SKRIPSI/ADS1256")
    
    ET.SubElement(datalogger, "digitizerModel").text = "ADS1256"
    ET.SubElement(datalogger, "digitizerManufacturer").text = "Waveshare"
    ET.SubElement(datalogger, "recorderModel").text = "Raspberry Pi 3 Model B+"
    ET.SubElement(datalogger, "recorderManufacturer").text = "Raspberry Pi Foundation"
    ET.SubElement(datalogger, "gain").text = str(int(digitizer_gain))
    
    decimation = ET.SubElement(datalogger, "decimation")
    decimation.set("sampleRateNumerator", str(int(sample_rate)))
    decimation.set("sampleRateDenominator", "1")
    
    filter_chain = ET.SubElement(decimation, "digitalFilterChain")
    filter_chain.text = f"{datalogger_public_id}/1"
    
    # Response PAZ (Poles and Zeros) for the geophone
    response_paz = ET.SubElement(inventory, "responsePAZ")
    response_paz.set("publicID", f"{sensor_public_id}/1")
    response_paz.set("name", f"{sensor_public_id}/1")
    
    ET.SubElement(response_paz, "type").text = "A"
    ET.SubElement(response_paz, "gain").text = str(geophone_gain)
    ET.SubElement(response_paz, "gainFrequency").text = str(natural_freq)
    
    # Normalization factor - this is an approximate value based on the example
    norm_factor = 1586  # From the example XML
    ET.SubElement(response_paz, "normalizationFactor").text = str(norm_factor)
    ET.SubElement(response_paz, "normalizationFrequency").text = str(natural_freq)
    
    ET.SubElement(response_paz, "numberOfZeros").text = "1"
    ET.SubElement(response_paz, "numberOfPoles").text = "2"
    
    # Define zeros and poles
    ET.SubElement(response_paz, "zeros").text = "(0,0)"
    poles_text = f"({real_pole:.3f},{imag_pole:.3f}) ({real_pole:.3f},{-imag_pole:.3f})"
    ET.SubElement(response_paz, "poles").text = poles_text
    
    # Response FIR for the digitizer
    response_fir = ET.SubElement(inventory, "responseFIR")
    response_fir.set("publicID", f"{datalogger_public_id}/1")
    response_fir.set("name", f"{datalogger_public_id}/1")
    
    ET.SubElement(response_fir, "gain").text = "1"
    ET.SubElement(response_fir, "gainFrequency").text = "1"
    ET.SubElement(response_fir, "decimationFactor").text = "1"
    ET.SubElement(response_fir, "delay").text = "15"
    ET.SubElement(response_fir, "correction").text = "15"
    
    # FIR coefficients - using simplified values from example
    coeffs = "0.0001 0.0005 0.0012 0.0023 0.0034 0.0043 0.005 0.0043 0.0034 0.0023 0.0012 0.0005 0.0001"
    ET.SubElement(response_fir, "numberOfCoefficients").text = str(len(coeffs.split()))
    ET.SubElement(response_fir, "symmetry").text = "C"
    ET.SubElement(response_fir, "coefficients").text = coeffs
    
    # Network element
    network = ET.SubElement(inventory, "network")
    network.set("publicID", f"Network#{datetime.now().strftime('%Y%m%d%H%M%S.%f.%d')}")
    network.set("code", network_code)
    
    ET.SubElement(network, "start").text = formatted_date
    ET.SubElement(network, "description").text = "Metadata Custom for Testing Sensors"
    ET.SubElement(network, "institutions").text = "STMKG"
    ET.SubElement(network, "region").text = "Indonesia"
    ET.SubElement(network, "restricted").text = "true"
    ET.SubElement(network, "shared").text = "true"
    
    # Station element
    station = ET.SubElement(network, "station")
    station.set("publicID", f"Station#{datetime.now().strftime('%Y%m%d%H%M%S.%f.%d')}")
    station.set("code", station_code)
    
    ET.SubElement(station, "start").text = formatted_date
    ET.SubElement(station, "description").text = "Tanah Tinggi"
    ET.SubElement(station, "latitude").text = str(latitude)
    ET.SubElement(station, "longitude").text = str(longitude)
    ET.SubElement(station, "elevation").text = str(int(elevation))
    ET.SubElement(station, "place").text = "Tanah Tinggi"
    ET.SubElement(station, "country").text = "Indonesia"
    ET.SubElement(station, "affiliation").text = "STMKG"
    ET.SubElement(station, "type").text = "SP"
    ET.SubElement(station, "restricted").text = "true"
    ET.SubElement(station, "shared").text = "true"
    
    # Sensor location element
    sensor_location = ET.SubElement(station, "sensorLocation")
    sensor_location.set("publicID", f"SensorLocation#{datetime.now().strftime('%Y%m%d%H%M%S.%f.%d')}")
    sensor_location.set("code", location_code)
    
    ET.SubElement(sensor_location, "start").text = formatted_date
    ET.SubElement(sensor_location, "latitude").text = str(latitude)
    ET.SubElement(sensor_location, "longitude").text = str(longitude)
    ET.SubElement(sensor_location, "elevation").text = str(int(elevation))
    
    # Stream element
    stream = ET.SubElement(sensor_location, "stream")
    stream.set("publicID", f"Stream#{datetime.now().strftime('%Y%m%d%H%M%S.%f.%d')}")
    stream.set("code", channel_code)
    stream.set("datalogger", datalogger_public_id)
    stream.set("sensor", sensor_public_id)
    
    ET.SubElement(stream, "start").text = formatted_date
    ET.SubElement(stream, "dataloggerSerialNumber").text = "1234"
    ET.SubElement(stream, "sensorSerialNumber").text = "1234"
    ET.SubElement(stream, "sampleRateNumerator").text = str(int(sample_rate))
    ET.SubElement(stream, "sampleRateDenominator").text = "1"
    ET.SubElement(stream, "depth").text = str(int(depth))
    ET.SubElement(stream, "azimuth").text = "0"
    ET.SubElement(stream, "dip").text = "-90"
    ET.SubElement(stream, "gain").text = str(total_gain)
    ET.SubElement(stream, "gainFrequency").text = str(natural_freq)
    ET.SubElement(stream, "gainUnit").text = "M/S"
    ET.SubElement(stream, "format").text = "Steim2"
    ET.SubElement(stream, "flags").text = "GC"
    ET.SubElement(stream, "restricted").text = "true"
    ET.SubElement(stream, "shared").text = "true"
    
    return root

def get_ads1256_info():
    """
    Get information about the ADS1256 configuration
    
    Returns:
        dictionary with ADS1256 information
    """
    print("\n--- ADS1256 Digitizer Information for Raspberry Pi ---")
    
    # ADC Range
    print("\nSelect ADC input voltage range:")
    print("1: ±2.5V (default)")
    print("2: ±5.0V")
    print("3: ±10.0V (if using external amplifier)")
    print("4: Other (enter value)")
    
    choice = input("Your choice [1-4]: ").strip() or "1"
    
    if choice == "1":
        adc_range = 5.0  # ±2.5V = 5.0V peak-to-peak
    elif choice == "2":
        adc_range = 10.0  # ±5.0V = 10.0V peak-to-peak
    elif choice == "3":
        adc_range = 20.0  # ±10.0V = 20.0V peak-to-peak
    elif choice == "4":
        try:
            adc_range = float(input("Enter peak-to-peak range in Volts: ").strip())
        except ValueError:
            print("Invalid value, using default 5.0V")
            adc_range = 5.0
    else:
        adc_range = 5.0  # Default
    
    # ADS1256 Gain
    print("\nSelect ADS1256 gain:")
    print("1: 1 (default)")
    print("2: 2")
    print("3: 4")
    print("4: 8")
    print("5: 16")
    print("6: 32")
    print("7: 64")
    
    gain_choice = input("Your choice [1-7]: ").strip() or "1"
    gain_map = {"1": 1, "2": 2, "3": 4, "4": 8, "5": 16, "6": 32, "7": 64}
    gain = gain_map.get(gain_choice, 1)
    
    # Filter type
    print("\nSelect ADS1256 digital filter type:")
    print("1: SINC3 (default)")
    print("2: SINC4")
    print("3: No filter")
    
    filter_choice = input("Your choice [1-3]: ").strip() or "1"
    filter_map = {"1": "SINC3", "2": "SINC4", "3": "NONE"}
    filter_type = filter_map.get(filter_choice, "SINC3")
    
    # Buffer enabled
    buffer_choice = input("\nEnable ADS1256 input buffer? (y/n, default: y): ").strip().lower() or "y"
    buffer_enabled = buffer_choice == "y"
    
    # Dither enabled
    dither_choice = input("\nEnable ADS1256 dither feature? (y/n, default: n): ").strip().lower() or "n"
    dither_enabled = dither_choice == "y"
    
    return {
        "adc_range": adc_range,
        "bit_depth": 24,  # ADS1256 is always 24-bit
        "gain": gain,
        "filter_type": filter_type,
        "buffer_enabled": buffer_enabled,
        "dither_enabled": dither_enabled
    }

def save_inventory_to_xml(root, output_dir=".", filename=None):
    """
    Save the inventory to an XML file with pretty formatting
    
    Args:
        root: Root XML element
        output_dir: Output directory (default: ".")
        filename: Output filename (default: None)
        
    Returns:
        Path to the saved XML file
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # Get network and station codes
    inventory = root.find("Inventory")
    network = inventory.find("network")
    station = network.find("station")
    
    network_code = network.get("code")
    station_code = station.get("code")
    
    if filename is None:
        filename = f"{network_code}.{station_code}.xml"
    
    output_path = os.path.join(output_dir, filename)
    
    # Convert ElementTree to string and pretty print
    rough_string = ET.tostring(root, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent="  ")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(pretty_xml)
    
    return output_path

if __name__ == "__main__":
    # Example usage
    print("SeisComP XML Generator for PPSD - EG-4.5-II with ADS1256 on Raspberry Pi")
    print("=====================================================================")
    
    # Default configuration
    network_code = "IA"
    station_code = "STMKG"
    channel_code = "SHZ"
    location_code = "00"
    sample_rate = 50.0
    
    # Input location and station parameters (optional)
    use_default = input("Use default station parameters (y/n)? ").strip().lower() == 'y'
    
    if not use_default:
        network_code = input(f"Network code (default: {network_code}): ").strip() or network_code
        station_code = input(f"Station code (default: {station_code}): ").strip() or station_code
        channel_code = input(f"Channel code (default: {channel_code}): ").strip() or channel_code
        location_code = input(f"Location code (default: {location_code}): ").strip() or location_code
        
        lat_input = input("Latitude (degrees, default: -6.171239): ").strip()
        latitude = float(lat_input) if lat_input else -6.171239
        
        lon_input = input("Longitude (degrees, default: 106.645735): ").strip()
        longitude = float(lon_input) if lon_input else 106.645735
        
        elev_input = input("Elevation (meters, default: 8.0): ").strip()
        elevation = float(elev_input) if elev_input else 8.0
        
        depth_input = input("Sensor depth (meters, default: 0.0): ").strip()
        depth = float(depth_input) if depth_input else 0.0
        
        rate_input = input(f"Sample rate (Hz, default: {sample_rate}): ").strip()
        sample_rate = float(rate_input) if rate_input else sample_rate
        
        # Input start date
        start_date_input = input("Start date (format: YYYY-MM-DD HH:MM:SS, leave empty for current time): ").strip()
        if start_date_input:
            try:
                start_date = datetime.strptime(start_date_input, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                print("Invalid date format. Using current time.")
                start_date = None
        else:
            start_date = None
    else:
        latitude = -6.171239   # Default Jakarta
        longitude = 106.645735 # Default Jakarta
        elevation = 8.0        # Default
        depth = 0.0            # Default
        start_date = None      # Default to current time
    
    # Get ADS1256 information from user
    digitizer_params = get_ads1256_info()
    
    # Complete sensor description
    sensor_description = f"EGL EG-4.5-II Geophone (4.5Hz, 28.8V/m/s) with ADS1256 on Raspberry Pi 3B+"
    
    # Create inventory
    root = create_seiscomp_inventory(
        station_code=station_code,
        network_code=network_code,
        channel_code=channel_code,
        location_code=location_code,
        latitude=latitude,
        longitude=longitude,
        elevation=elevation,
        depth=depth,
        sample_rate=sample_rate,
        sensor_description=sensor_description,
        start_date=start_date,
        digitizer_params=digitizer_params
    )
    
    # Save to XML file
    output_dir = input("Output directory (default: .): ").strip() or "."
    filename = f"{network_code}.{station_code}.xml"
    custom_filename = input(f"Output filename (default: {filename}): ").strip()
    if custom_filename:
        filename = custom_filename
    
    output_path = save_inventory_to_xml(root, output_dir, filename)
    
    print(f"\nXML file saved to: {output_path}")