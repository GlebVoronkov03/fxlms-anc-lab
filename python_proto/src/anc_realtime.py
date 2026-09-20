import numpy as np
import sounddevice as sd
import scipy.signal as sps
import time

class FxLMS_RT:
    def __init__(self, filter_len, sec_path, mu=0.001):
        self.filter_len = filter_len
        self.mu = mu
        self.w = np.zeros(filter_len)
        self.sec_path = sec_path
        self.sec_len = len(sec_path)
        
        # Буферы
        self.x_buf = np.zeros(filter_len)
        self.x_filt_buf = np.zeros(self.sec_len)
        
    def process(self, x, d):
        """
        Принимает один сэмпл x (опорный) и d (ошибка).
        Возвращает y (антишум).
        """
        # Сдвиг буфера x
        self.x_buf[1:] = self.x_buf[:-1]
        self.x_buf[0] = x
        
        # Генерация антишума
        y = np.dot(self.w, self.x_buf)
        
        # Фильтрация y через вторичный тракт для вычисления ошибки
        self.x_filt_buf[1:] = self.x_filt_buf[:-1]
        self.x_filt_buf[0] = y
        y_filt = np.dot(self.sec_path, self.x_filt_buf)
        
        e = d - y_filt
        
        # Формирование x_filt для обновления весов
        x_filt = sps.lfilter(self.sec_path, 1, self.x_buf)[::-1][:self.filter_len]
        
        # Обновление весов
        self.w += self.mu * e * x_filt
        
        return y

def audio_callback(indata, outdata, frames, time_info, status, fxlms):
    """
    Callback функция для sounddevice.
    indata[:,0] - опорный микрофон
    indata[:,1] - микрофон ошибки
    outdata[:,0] - выход на динамик
    """
    if status:
        print(f"Status: {status}")
    
    # Копируем данные (во избежание проблем с памятью)
    x_chunk = indata[:, 0].copy()
    d_chunk = indata[:, 1].copy()
    
    y_chunk = np.zeros(frames, dtype=np.float32)
    
    for i in range(frames):
        y_chunk[i] = fxlms.process(x_chunk[i], d_chunk[i])
    
    # Выводим антишум на первый канал
    outdata[:, 0] = y_chunk
    # Остальные каналы обнуляем
    outdata[:, 1:] = 0

def main():
    # ========== НАСТРОЙКИ (ИЗМЕНИТЕ ПОД СВОЁ ОБОРУДОВАНИЕ) ==========
    # Вставьте сюда индексы устройств из вывода list_devices.py
    INPUT_DEVICE = 1   # Например: 4 (для ASIO) или "Windows WASAPI"
    OUTPUT_DEVICE = 4  # Обычно совпадает с INPUT_DEVICE при использовании ASIO
    
    SAMPLE_RATE = 16000      # Частота дискретизации (можно 8000 для экономии CPU)
    BLOCKSIZE = 256          # Размер блока. Меньше = меньше задержка, но выше нагрузка
    FILTER_LEN = len(sec_path)        # Длина адаптивного фильтра
    MU = 1e-5               # Шаг адаптации (подбирается экспериментально)
    # ===============================================================
    
    # Загружаем или создаём модель вторичного тракта
    # Временно используем реалистичную модель (как в симуляции)
    sec_len = 128
    sec_path = np.zeros(sec_len)
    delay_direct = int(0.002 * SAMPLE_RATE)  # 2 мс
    sec_path[delay_direct] = 0.6
    sec_path[delay_direct + 4] = 0.2
    sec_path[delay_direct + 8] = 0.1
    # Нормализация
    sec_path /= np.max(np.abs(sec_path))
    
    fxlms = FxLMS_RT(FILTER_LEN, sec_path, MU)
    
    # Попытка открыть поток с WASAPI exclusive (если устройство не ASIO)
    try:
        if isinstance(INPUT_DEVICE, str) and "WASAPI" in INPUT_DEVICE:
            # Для WASAPI можно попробовать эксклюзивный режим
            import sounddevice as sd_wasapi
            stream = sd_wasapi.Stream(
                samplerate=SAMPLE_RATE,
                blocksize=BLOCKSIZE,
                device=(INPUT_DEVICE, OUTPUT_DEVICE),
                channels=(2, 2),  # 2 входа, 2 выхода
                callback=lambda *args: audio_callback(*args, fxlms=fxlms),
                dtype='float32',
                extra_settings=sd_wasapi.WasapiSettings(exclusive=True)
            )
        else:
            stream = sd.Stream(
                samplerate=SAMPLE_RATE,
                blocksize=BLOCKSIZE,
                device=(INPUT_DEVICE, OUTPUT_DEVICE),
                channels=(2, 2),
                callback=lambda *args: audio_callback(*args, fxlms=fxlms),
                dtype='float32'
            )
    except Exception as e:
        print(f"Ошибка при создании потока: {e}")
        print("Попробуйте указать другие индексы устройств или использовать MME (большая задержка).")
        return
    
    print(f"Используется входное устройство: {INPUT_DEVICE}")
    print(f"Используется выходное устройство: {OUTPUT_DEVICE}")
    print(f"Частота дискретизации: {SAMPLE_RATE} Гц, размер блока: {BLOCKSIZE}")
    print("Запуск ANC. Нажмите Ctrl+C для остановки.")
    
    with stream:
        try:
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nОстановка...")
    
    print("Поток остановлен.")

if __name__ == "__main__":
    # Перед запуском выведем список устройств для удобства
    print("Доступные устройства:")
    print(sd.query_devices())
    print("\nУкажите INPUT_DEVICE и OUTPUT_DEVICE в коде и перезапустите.")
    # Раскомментируйте следующую строку после настройки индексов
    main()