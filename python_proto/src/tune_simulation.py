import numpy as np
import scipy.signal as sps
import matplotlib.pyplot as plt
from fxlms_sim import FxLMS, create_realistic_sec_path

def evaluate(mu, filter_len, fs=16000):
    # Генерируем тестовый сигнал
    duration = 3.0
    t = np.arange(int(fs * duration)) / fs
    noise = 0.3 * np.sin(2 * np.pi * 100 * t) + 0.03 * np.random.randn(len(t))
    
    sec_path = create_realistic_sec_path(fs)
    primary_delay = int(0.003 * fs)
    primary_path = np.zeros(primary_delay + 20)
    primary_path[primary_delay] = 0.8
    primary_path[primary_delay + 10] = 0.1
    d_signal = np.convolve(noise, primary_path, mode='same')
    
    fxlms = FxLMS(filter_len, sec_path, mu)
    e_out = np.zeros(len(noise))
    
    for i, x in enumerate(noise):
        y, e = fxlms.step(x, d_signal[i])
        e_out[i] = e
        
        # Ранняя остановка при расходимости
        if np.abs(e) > 10.0:
            return 999.0  # штраф
    
    rms_residual = np.sqrt(np.mean(e_out**2))
    return rms_residual

# Сетка параметров
mus = [1e-6, 5e-6, 1e-5, 5e-5, 1e-4, 5e-4, 1e-3]
filter_lens = [32, 64, 128, 256, 512]

best_rms = float('inf')
best_params = (None, None)

print("Подбор параметров...")
for mu in mus:
    for fl in filter_lens:
        rms = evaluate(mu, fl)
        print(f"mu={mu:.0e}, len={fl:3d} -> RMS={rms:.4f}")
        if rms < best_rms:
            best_rms = rms
            best_params = (mu, fl)

print(f"\nЛучшие параметры: mu={best_params[0]}, filter_len={best_params[1]}, RMS={best_rms:.4f}")