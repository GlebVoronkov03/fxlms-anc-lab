import sounddevice as sd
import numpy as np

def find_best_input_device():
    """Ищет устройство WASAPI с 2 каналами ввода или возвращает устройство по умолчанию."""
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        if dev['max_input_channels'] >= 2 and 'WASAPI' in dev['name']:
            return i
    # fallback – устройство ввода по умолчанию
    return sd.default.device[0]

def analyze_channels(duration=5, samplerate=48000, device=None):
    if device is None:
        device = find_best_input_device()
        print(f"Автоматически выбрано устройство ввода: индекс {device}")
    print("Анализ уровня каналов (тишина или белый шум)...")
    try:
        data = sd.rec(int(duration * samplerate), samplerate=samplerate,
                      channels=2, device=device, dtype='float32')
        sd.wait()
    except Exception as e:
        print(f"Ошибка записи: {e}")
        print("Проверьте, подключены ли микрофоны через сплиттер и видны ли они как стереоустройство.")
        return None, None

    rms_left = np.sqrt(np.mean(data[:, 0]**2))
    rms_right = np.sqrt(np.mean(data[:, 1]**2))
    print(f"RMS Левый: {rms_left:.4f}  |  RMS Правый: {rms_right:.4f}")
    if rms_left > 0.0001 and rms_right > 0.0001:
        diff_db = 20 * np.log10(rms_left / rms_right)
        print(f"Разница: {diff_db:.2f} дБ (положительное – левый громче)")
    else:
        print("Сигнал слишком слабый, проверьте подключение.")
    return rms_left, rms_right

if __name__ == "__main__":
    analyze_channels()