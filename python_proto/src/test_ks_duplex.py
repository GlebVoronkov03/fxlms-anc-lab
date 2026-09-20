import sounddevice as sd

print("Проверка дуплекса WDM-KS: вход 24, выход 17")
try:
    stream = sd.Stream(
        samplerate=48000,
        blocksize=128,
        device=(24, 17),
        channels=(1, 1),
        dtype='float32'
    )
    print("✅ Поток открыт успешно!")
    stream.close()
except Exception as e:
    print(f"❌ Ошибка: {e}")