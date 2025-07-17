import numpy as np
import soundfile as sf
from scipy.signal import firwin, lfilter

def build_fir_bandpass(center_freq, fs, bandwidth, numtaps=2048):
    nyq = fs / 2
    low = max(0.001, (center_freq - bandwidth / 2) / nyq)
    high = min(0.999, (center_freq + bandwidth / 2) / nyq)
    return firwin(numtaps, [low, high], pass_zero=False)

def apply_fir_filterbank(audio, fs, num_bands=100, min_freq=20, max_freq=20000):
    output = np.zeros_like(audio)
    center_freqs = np.geomspace(min_freq, max_freq, num=num_bands)
    bandwidth = (max_freq - min_freq) / num_bands

    for i, cf in enumerate(center_freqs):
        taps = build_fir_bandpass(cf, fs, bandwidth, numtaps=2048)
        filtered = lfilter(taps, 1.0, audio)
        output += filtered
        print(f"band {i+1}/{num_bands}: {int(cf)} Hz")

    return output / np.max(np.abs(output))

# config
input_file = 'input.wav'  # replace with your actual file path
output_file = 'output_fir_filterbank.wav'

# load + downmix if stereo
audio, fs = sf.read(input_file)
if audio.ndim > 1:
    audio = np.mean(audio, axis=1)

# process and write
processed = apply_fir_filterbank(audio, fs, num_bands=100)
sf.write(output_file, processed, fs)
