
from obspy.core import UTCDateTime
from obspy.core.inventory import Inventory, Network, Station, Channel, Response, InstrumentSensitivity, Site
from obspy.core.inventory.response import PolesZerosResponseStage, CoefficientsTypeResponseStage

def create_stationxml(
    network_code,
    station_code,
    station_latitude,
    station_longitude,
    station_elevation,
    station_start_date,
    channel_code,
    channel_latitude,
    channel_longitude,
    channel_elevation,
    channel_depth,
    channel_azimuth,
    channel_dip,
    sample_rate,
    instrument_sensitivity_value,
    instrument_sensitivity_frequency,
    geophone_poles=None,
    geophone_zeros=None,
    geophone_gain=None,
    ads1256_gain=None
):
    # Create a new Inventory object
    inventory = Inventory(
        networks=[],
        source="DIY Seismometer Project"
    )

    # Create a Network
    network = Network(
        code=network_code,
        description="Experimental DIY Seismometer Network",
        start_date=UTCDateTime(station_start_date)
    )

    # Create a Station
    station = Station(
        code=station_code,
        latitude=station_latitude,
        longitude=station_longitude,
        elevation=station_elevation,
        description="DIY Seismometer Station",
        creation_date=UTCDateTime(station_start_date),
        site=Site(name="Home Lab")
    )

    # Create a Channel
    channel = Channel(
        code=channel_code,
        location_code="",
        latitude=channel_latitude,
        longitude=channel_longitude,
        elevation=channel_elevation,
        depth=channel_depth,
        azimuth=channel_azimuth,
        dip=channel_dip,
        sample_rate=sample_rate,
        start_date=UTCDateTime(station_start_date)
    )

    # Create Response object
    response = Response(instrument_sensitivity=InstrumentSensitivity(
        value=instrument_sensitivity_value,
        frequency=instrument_sensitivity_frequency,
        input_units="M/S",
        output_units="COUNTS"
    ))

    # Add Poles and Zeros for Geophone if provided
    if geophone_poles and geophone_zeros and geophone_gain:
        pz_response = PolesZerosResponseStage(
            stage_sequence_number=1,
            stage_gain=geophone_gain,
            stage_gain_frequency=instrument_sensitivity_frequency,
            pz_transfer_function_type="LAPLACE (HERTZ)",
            input_units="M/S",
            output_units="V",
            poles=geophone_poles,
            zeros=geophone_zeros,
            normalization_factor=geophone_gain,
            normalization_frequency=instrument_sensitivity_frequency
        )
        response.response_stages.append(pz_response)

    # Add Coefficient for ADS1256 gain if provided
    if ads1256_gain:
        coeff_response = CoefficientsTypeResponseStage(
            stage_sequence_number=2,
            stage_gain=ads1256_gain,
            stage_gain_frequency=instrument_sensitivity_frequency,
            input_units="V",
            output_units="COUNTS",
            cf_transfer_function_type="DIGITAL",
            # coefficients=[ads1256_gain] # This argument seems to be problematic
            numerator=[ads1256_gain],
            denominator=[1.0]
        )
        response.response_stages.append(coeff_response)

    channel.response = response

    # Add Channel to Station, Station to Network, and Network to Inventory
    station.channels.append(channel)
    network.stations.append(station)
    inventory.networks.append(network)

    return inventory

if __name__ == "__main__":
    # Example Usage:
    network_code = "XX"
    station_code = "DIY01"
    station_latitude = 34.0522
    station_longitude = -118.2437
    station_elevation = 100.0
    station_start_date = "2025-01-01T00:00:00Z"

    channel_code = "HHZ"
    channel_latitude = 34.0522
    channel_longitude = -118.2437
    channel_elevation = 100.0
    channel_depth = 0.0
    channel_azimuth = 0.0
    channel_dip = -90.0
    sample_rate = 100.0

    # Removed geophone_model, geophone_serial, geophone_installation_date, ads1256_serial, ads1256_installation_date
    # for simplification. Will add back once basic StationXML generation is successful.

    # Example Instrument Sensitivity (Counts per m/s)
    # This is a simplified calculation. For a real system, this needs careful calibration.
    # Assuming Geophone Sensitivity: 75.7 V/m/s (from our hypothetical geophone)
    # Assuming ADS1256 Reference Voltage: 2.5 V
    # Assuming ADS1256 is bipolar, 2^23 counts for 2.5V
    # Counts per Volt = (2**23) / 2.5 = 3355443.2
    # Instrument Sensitivity = 75.7 * 3355443.2 = 253987800.0
    instrument_sensitivity_value = 253987800.0
    instrument_sensitivity_frequency = 1.0

    # Example Geophone Poles and Zeros (for a 10Hz geophone, simplified)
    # These values are highly dependent on the specific geophone model.
    # You would typically get these from the geophone\"s datasheet.
    # Example for a 10Hz geophone (simplified, often more complex)
    # Poles: -6.283 + 4.712j, -6.283 - 4.712j (for 10Hz natural frequency, 0.707 damping)
    # Zeros: 0+0j, 0+0j (for velocity sensor)
    # Normalization Factor (Gain) for the geophone (V/m/s)
    geophone_poles = [-6.283 + 4.712j, -6.283 - 4.712j]
    geophone_zeros = [0+0j, 0+0j]
    geophone_gain = 75.7 # V/m/s

    # ADS1256 Gain (e.g., if PGA is set to 1, then gain is 1)
    # If PGA is set to 2, gain is 2, etc.
    # This is the conversion from Volts to Counts
    ads1256_gain = 3355443.2 # Counts/Volt (for 2.5V Vref, 24-bit bipolar)

    inventory = create_stationxml(
        network_code,
        station_code,
        station_latitude,
        station_longitude,
        station_elevation,
        station_start_date,
        channel_code,
        channel_latitude,
        channel_longitude,
        channel_elevation,
        channel_depth,
        channel_azimuth,
        channel_dip,
        sample_rate,
        instrument_sensitivity_value,
        instrument_sensitivity_frequency,
        geophone_poles=geophone_poles,
        geophone_zeros=geophone_zeros,
        geophone_gain=geophone_gain,
        ads1256_gain=ads1256_gain
    )

    # Save the StationXML to a file
    output_filename = "diy_seismometer_station.xml"
    inventory.write(output_filename, format="StationXML", validate=True)
    print(f"StationXML file \'{output_filename}\' created successfully.")


