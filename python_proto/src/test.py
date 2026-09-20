import sounddevice as sd
import numpy as np

def test_channels():
    duration = 3  # секунд
    fs = 48000
    device = 18   # External Mic WASAPI (2 канала)
    print(f"Тест устройства {device}. Говорите/шуршите в один микрофон.")
    data = sd.rec(int(duration * fs), samplerate=fs, channels=2, device=device, dtype='float32')
    sd.wait()
    max_left = np.max(np.abs(data[:, 0]))
    max_right = np.max(np.abs(data[:, 1]))
    print(f"Максимум левого: {max_left:.4f}, правого: {max_right:.4f}")
    if max_left > 0.01 and max_right < 0.001:
        print("✅ Левый активен, правый молчит – разделение есть.")
    elif max_right > 0.01 and max_left < 0.001:
        print("✅ Правый активен, левый молчит – разделение есть (поменяйте местами штекеры для удобства).")
    else:
        print("❌ Оба канала показывают одинаковый сигнал. Разделения нет!")

if __name__ == "__main__":
    test_channels()