import numpy as np
import sounddevice as sd
import scipy.signal as sps
import matplotlib.pyplot as plt

fs = 48000
duration = 3.0

t = np.arange(int(fs * duration)) / fs
f0, f1 = 20.0, fs/2.0 * 0.9
sweep = sps.chirp(t, f0, duration, f1, method='logarithmic', phi=-90)
fade_len = int(0.01 * fs)
fade = np.hanning(2 * fade_len)
sweep[:fade_len] *= fade[:fade_len]
sweep[-fade_len:] *= fade[fade_len:]

recorded = np.zeros(len(sweep), dtype=np.float32)
pos = 0

def callback(indata, outdata, frames, time_info, status):
    global pos
    if status:
        print(f"Status: {status}")
    end = pos + frames
    if end <= len(sweep):
        outdata[:, 0] = sweep[pos:end]
        recorded[pos:end] = indata[:, 0]
    else:
        rem = len(sweep) - pos
        if rem > 0:
            outdata[:rem, 0] = sweep[pos:]
            recorded[pos:] = indata[:rem, 0]
        outdata[rem:, 0] = 0
    pos += frames

print("Открытие WASAPI shared через устройства по умолчанию...")
try:
    stream = sd.Stream(
        samplerate=fs,
        blocksize=256,
        device=(18, 15),   # 11 – Mic WASAPI, 10 – Speakers WASAPI
        channels=(1, 1),
        callback=callback,
        dtype='float32'
    )
    print("✅ Поток открыт успешно!")
except Exception as e:
    print(f"❌ Ошибка: {e}")
    exit()

with stream:
    print("Идёт запись свипа...")
    sd.sleep(int(duration * 1000) + 500)

inv_filter = sweep[::-1] * np.exp(np.linspace(0, np.log(f1/f0), len(sweep)))
ir = sps.fftconvolve(recorded, inv_filter, mode='full')
ir = ir[:int(0.05 * fs)]
ir = ir / np.max(np.abs(ir))

# Инвертируем, если пик отрицательный
peak_idx = np.argmax(np.abs(ir))
if ir[peak_idx] < 0:
    ir = -ir
    print("ИХ инвертирована для положительного пика.")

time_ms = np.arange(len(ir)) / fs * 1000
plt.plot(time_ms, ir)
plt.xlabel('Время (мс)')
plt.title('Импульсная характеристика')
plt.grid(True)
plt.axvline(peak_idx/fs*1000, color='r', linestyle='--')
plt.show()

np.save('sec_path_ir.npy', ir)
print(f"ИХ сохранена. Пик на {peak_idx/fs*1000:.2f} мс")