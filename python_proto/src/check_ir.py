import numpy as np
import matplotlib.pyplot as plt

ir = np.load('sec_path_ir.npy')
fs = 16000
time_ms = np.arange(len(ir)) / fs * 1000

plt.figure(figsize=(12, 4))
plt.plot(time_ms, ir)
plt.xlabel('Время (мс)')
plt.ylabel('Амплитуда')
plt.title('Импульсная характеристика вторичного тракта')
plt.grid(True)

# Найдём пик
peak_idx = np.argmax(np.abs(ir))
peak_time = peak_idx / fs * 1000
plt.axvline(peak_time, color='r', linestyle='--', label=f'Пик на {peak_time:.2f} мс')
plt.legend()
plt.show()

print(f"Длина ИХ: {len(ir)} сэмплов ({len(ir)/fs*1000:.1f} мс)")
print(f"Максимальный пик на {peak_time:.2f} мс, значение: {ir[peak_idx]:.3f}")
print(f"Отношение пик/шум: {20*np.log10(np.abs(ir[peak_idx]) / np.std(ir[:100])):.1f} дБ")