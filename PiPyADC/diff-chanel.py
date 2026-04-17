#!/usr/bin/env python3
"""Example file for class ADS1256 in pipyadc package

ADS1256 AD-converter measuring 4 differential input channels.

Hardware: Waveshare "High Precision AD/DA" board
interfaced to the Raspberry Pi 2B, 3B or 4
 
Ulrich Lukas 2022-06-28 — Modified for 4 differential inputs
"""
import time
import logging
from pipyadc import ADS1256
from pipyadc.utils import TextScreen
from pipyadc.ADS1256_definitions import *
import waveshare_config

logging.basicConfig(level=logging.DEBUG)

print("\x1B[2J\x1B[H")
print(__doc__)
print("\nPress CTRL-C to exit.\n")

screen = TextScreen()

def text_format_4_diff(digits, volts):
    digits_str = ", ".join([f"{i: 8d}" for i in digits])
    volts_str = ", ".join([f"{i: 8.3f}" for i in volts])
    text = (
        "  AIN0-AIN1, AIN2-AIN3, AIN4-AIN5, AIN6-AIN7\n"
        f"{digits_str}\n\n"
        "Values converted to volts:\n"
        f"{volts_str}\n"
    )
    return text

# Define 4 differential input pairs
DIFF_0_1 = POS_AIN0 | NEG_AIN1
DIFF_2_3 = POS_AIN2 | NEG_AIN3
DIFF_4_5 = POS_AIN4 | NEG_AIN5
DIFF_6_7 = POS_AIN6 | NEG_AIN7

CH_SEQUENCE = DIFF_0_1, DIFF_2_3, DIFF_4_5, DIFF_6_7

def loop_forever_measurements(ads):
    while True:
        raw_channels = ads.read_sequence(CH_SEQUENCE)
        voltages = [i * ads.v_per_digit for i in raw_channels]
        screen.put(text_format_4_diff(raw_channels, voltages))
        screen.refresh()
        time.sleep(0.5)

try:
    with ADS1256(waveshare_config) as ads:
        ads.drate = DRATE_100
        ads.cal_self()
        loop_forever_measurements(ads)

except KeyboardInterrupt:
    print("\nUser Exit.\n")
