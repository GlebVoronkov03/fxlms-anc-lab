"""Оконный тест независимости каналов микрофона для ANC.

Запускать через run_microphone_test.bat. Все записи и отчёты сохраняются
локально в python_proto/measurements/microphone_tests.
"""

from __future__ import annotations

import csv
import json
import math
import os
import queue
import subprocess
import threading
import time
import tkinter as tk
import winreg
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

import numpy as np
import sounddevice as sd
from scipy.io import wavfile


APP_TITLE = "QuietRadius — тест микрофона"
SAMPLE_RATE = 48_000
BLOCK_SIZE = 256
BASE_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = BASE_DIR / "measurements" / "microphone_tests"
EPS = 1e-12

TESTS = {
    "Живые уровни (без ограничения времени)": {
        "duration": None,
        "instruction": (
            "Говорите или аккуратно постукивайте по капсюлям. "
            "Нажмите «Стоп», когда закончите."
        ),
    },
    "Тишина / собственный шум — 8 секунд": {
        "duration": 8,
        "instruction": (
            "Положите оба капсюля рядом, не касайтесь стола и молчите. "
            "Закройте окна и уберите телефон подальше."
        ),
    },
    "Капсюль A — изоляция канала, 8 секунд": {
        "duration": 8,
        "instruction": (
            "Изолируйте капсюль B мягкой тканью. Говорите вплотную только "
            "в капсюль A или легко постукивайте рядом с ним."
        ),
    },
    "Капсюль B — изоляция канала, 8 секунд": {
        "duration": 8,
        "instruction": (
            "Изолируйте капсюль A мягкой тканью. Говорите вплотную только "
            "в капсюль B или легко постукивайте рядом с ним."
        ),
    },
    "Проверка дублирования L/R — 10 секунд": {
        "duration": 10,
        "instruction": (
            "Первые 4 секунды воздействуйте только на A, затем 2 секунды "
            "тишины, последние 4 секунды — только на B."
        ),
    },
}


def dbfs(value: float) -> float:
    return 20.0 * math.log10(max(abs(value), EPS))


def safe_corr(left: np.ndarray, right: np.ndarray) -> float:
    if len(left) < 2 or np.std(left) < EPS or np.std(right) < EPS:
        return 0.0
    return float(np.corrcoef(left, right)[0, 1])


@dataclass
class TestResult:
    timestamp: str
    test: str
    device: str
    device_index: int
    host_api: str
    sample_rate: int
    channels: int
    duration_s: float
    rms_left_dbfs: float
    rms_right_dbfs: float | None
    peak_left_dbfs: float
    peak_right_dbfs: float | None
    dc_left: float
    dc_right: float | None
    clipping_left_pct: float
    clipping_right_pct: float | None
    correlation_lr: float | None
    difference_dbfs: float | None
    balance_db: float | None
    separation_db: float | None
    verdict: str
    wav_file: str


class MicrophoneTestApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1120x790")
        self.root.minsize(940, 680)

        self.stream: sd.InputStream | None = None
        self.running = False
        self.started_at = 0.0
        self.stop_timer: str | None = None
        self.audio_chunks: list[np.ndarray] = []
        self.level_queue: queue.Queue[tuple[float, float, str]] = queue.Queue()
        self.device_map: dict[str, int] = {}
        self.session_results: list[TestResult] = []
        self.current_context: dict[str, object] = {}
        self.summary_signature = ""

        self.device_var = tk.StringVar()
        self.test_var = tk.StringVar(value=next(iter(TESTS)))
        self.mode_var = tk.StringVar(value="OFF/Smartphone")
        self.status_var = tk.StringVar(value="Готово. Выберите тест.")
        self.timer_var = tk.StringVar(value="00:00")
        self.left_db_var = tk.StringVar(value="−∞ dBFS")
        self.right_db_var = tk.StringVar(value="−∞ dBFS")
        self.instruction_var = tk.StringVar()
        self.windows_status_var = tk.StringVar(value="Проверяю Windows…")

        self._configure_style()
        self._build_ui()
        self.refresh_devices()
        self.refresh_windows_status()
        self._on_test_changed()
        self.root.after(80, self._poll_levels)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure(".", font=("Segoe UI", 11))
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 19))
        style.configure("Heading.TLabel", font=("Segoe UI Semibold", 12))
        style.configure("Instruction.TLabel", font=("Segoe UI Semibold", 13))
        style.configure("Big.TButton", font=("Segoe UI Semibold", 12), padding=(18, 10))
        style.configure("Treeview", rowheight=29, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 10))

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(outer, text=APP_TITLE, style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            outer,
            text=(
                "Без воспроизведения звука и без консоли. "
                "Записи остаются только на этом компьютере."
            ),
        ).pack(anchor=tk.W, pady=(2, 14))

        settings = ttk.LabelFrame(outer, text="1. Настройка", padding=12)
        settings.pack(fill=tk.X)
        settings.columnconfigure(1, weight=1)

        ttk.Label(settings, text="Устройство:").grid(row=0, column=0, sticky=tk.W, padx=(0, 8))
        self.device_combo = ttk.Combobox(
            settings, textvariable=self.device_var, state="readonly", width=72
        )
        self.device_combo.grid(row=0, column=1, sticky=tk.EW)
        ttk.Button(settings, text="Обновить", command=self.refresh_devices).grid(
            row=0, column=2, padx=(8, 0)
        )

        ttk.Label(settings, text="Тест:").grid(row=1, column=0, sticky=tk.W, pady=(10, 0))
        self.test_combo = ttk.Combobox(
            settings,
            textvariable=self.test_var,
            values=list(TESTS),
            state="readonly",
            width=72,
        )
        self.test_combo.grid(row=1, column=1, sticky=tk.EW, pady=(10, 0))
        self.test_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_test_changed())

        ttk.Label(settings, text="Режим BOYA:").grid(
            row=2, column=0, sticky=tk.W, pady=(10, 0)
        )
        mode_frame = ttk.Frame(settings)
        mode_frame.grid(row=2, column=1, sticky=tk.W, pady=(10, 0))
        ttk.Radiobutton(
            mode_frame,
            text="OFF/Smartphone (без батареи)",
            variable=self.mode_var,
            value="OFF/Smartphone",
        ).pack(side=tk.LEFT)
        ttk.Radiobutton(
            mode_frame,
            text="Camera (со свежей LR44)",
            variable=self.mode_var,
            value="Camera",
        ).pack(side=tk.LEFT, padx=(24, 0))

        win_frame = ttk.Frame(settings)
        win_frame.grid(row=3, column=0, columnspan=3, sticky=tk.EW, pady=(12, 0))
        ttk.Label(win_frame, textvariable=self.windows_status_var).pack(side=tk.LEFT)
        ttk.Button(
            win_frame, text="Открыть настройки звука", command=self.open_sound_settings
        ).pack(side=tk.RIGHT)
        ttk.Button(
            win_frame, text="Доступ к микрофону", command=self.open_privacy_settings
        ).pack(side=tk.RIGHT, padx=8)

        instructions = ttk.LabelFrame(outer, text="2. Что делать", padding=12)
        instructions.pack(fill=tk.X, pady=12)
        ttk.Label(
            instructions,
            textvariable=self.instruction_var,
            style="Instruction.TLabel",
            wraplength=1040,
            justify=tk.LEFT,
        ).pack(anchor=tk.W)

        controls = ttk.Frame(outer)
        controls.pack(fill=tk.X)
        self.start_button = ttk.Button(
            controls, text="▶  Старт", style="Big.TButton", command=self.start_test
        )
        self.start_button.pack(side=tk.LEFT)
        self.stop_button = ttk.Button(
            controls,
            text="■  Стоп",
            style="Big.TButton",
            command=self.stop_test,
            state=tk.DISABLED,
        )
        self.stop_button.pack(side=tk.LEFT, padx=10)
        ttk.Label(controls, textvariable=self.status_var, style="Heading.TLabel").pack(
            side=tk.LEFT, padx=14
        )
        ttk.Label(controls, textvariable=self.timer_var, style="Title.TLabel").pack(
            side=tk.RIGHT
        )

        meters = ttk.LabelFrame(outer, text="3. Живые уровни", padding=12)
        meters.pack(fill=tk.X, pady=12)
        meters.columnconfigure(1, weight=1)
        ttk.Label(meters, text="Левый / L", width=13).grid(row=0, column=0, sticky=tk.W)
        self.left_meter = ttk.Progressbar(meters, maximum=60)
        self.left_meter.grid(row=0, column=1, sticky=tk.EW, padx=8)
        ttk.Label(meters, textvariable=self.left_db_var, width=12).grid(row=0, column=2)
        ttk.Label(meters, text="Правый / R", width=13).grid(row=1, column=0, sticky=tk.W)
        self.right_meter = ttk.Progressbar(meters, maximum=60)
        self.right_meter.grid(row=1, column=1, sticky=tk.EW, padx=8, pady=(8, 0))
        ttk.Label(meters, textvariable=self.right_db_var, width=12).grid(
            row=1, column=2, pady=(8, 0)
        )
        ttk.Label(
            meters,
            text="Норма для речи: примерно −30…−12 dBFS. Красного индикатора нет: избегайте 0 dBFS.",
        ).grid(row=2, column=0, columnspan=3, sticky=tk.W, pady=(10, 0))

        results = ttk.LabelFrame(outer, text="4. Результаты текущей сессии", padding=8)
        results.pack(fill=tk.BOTH, expand=True)
        columns = ("test", "left", "right", "corr", "separation", "verdict")
        self.tree = ttk.Treeview(results, columns=columns, show="headings", height=7)
        headings = {
            "test": "Тест / режим",
            "left": "RMS L",
            "right": "RMS R",
            "corr": "Корреляция",
            "separation": "Разделение",
            "verdict": "Вывод",
        }
        widths = {
            "test": 260,
            "left": 90,
            "right": 90,
            "corr": 90,
            "separation": 100,
            "verdict": 360,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor=tk.W)
        scrollbar = ttk.Scrollbar(results, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def refresh_devices(self) -> None:
        current = self.device_var.get()
        self.device_map.clear()
        candidates: list[str] = []
        try:
            host_apis = sd.query_hostapis()
            for index, device in enumerate(sd.query_devices()):
                channels = int(device["max_input_channels"])
                if channels < 1:
                    continue
                host_name = host_apis[device["hostapi"]]["name"]
                label = (
                    f"{index}: {device['name']}  |  {host_name}  |  "
                    f"{channels} ch  |  {int(device['default_samplerate'])} Hz"
                )
                self.device_map[label] = index
                candidates.append(label)
        except Exception as exc:
            messagebox.showerror("Аудиоустройства", f"Не удалось получить список:\n{exc}")
            return

        self.device_combo["values"] = candidates
        preferred = next(
            (
                label
                for label in candidates
                if "MP3-Audio" in label and "WASAPI" in label and "2 ch" in label
            ),
            None,
        )
        if preferred is None:
            preferred = next(
                (
                    label
                    for label in candidates
                    if "External Mic" in label and "WASAPI" in label and "2 ch" in label
                ),
                None,
            )
        if current in candidates:
            self.device_var.set(current)
        elif preferred:
            self.device_var.set(preferred)
        elif candidates:
            self.device_var.set(candidates[0])

    def refresh_windows_status(self) -> None:
        privacy = self._read_privacy_status()
        effects = self._read_external_mic_effects_status()
        self.windows_status_var.set(
            f"Windows: микрофон — {privacy}; эффекты External Mic — {effects}; "
            "формат теста — 2 ch / 48 кГц"
        )

    @staticmethod
    def _read_privacy_status() -> str:
        path = (
            r"SOFTWARE\Microsoft\Windows\CurrentVersion"
            r"\CapabilityAccessManager\ConsentStore\microphone"
        )
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                value, _ = winreg.QueryValueEx(key, "Value")
            return "разрешён" if value == "Allow" else str(value)
        except OSError:
            return "не удалось проверить"

    @staticmethod
    def _read_external_mic_effects_status() -> str:
        capture_path = (
            r"SOFTWARE\Microsoft\Windows\CurrentVersion"
            r"\MMDevices\Audio\Capture"
        )
        name_key = "{a45c254e-df1c-4efd-8020-67d146a850e0},2"
        disable_fx_key = "{1da5d803-d492-4edd-8c23-e0c0ffee7f0e},5"
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, capture_path) as capture:
                count = winreg.QueryInfoKey(capture)[0]
                for i in range(count):
                    endpoint = winreg.EnumKey(capture, i)
                    properties_path = f"{capture_path}\\{endpoint}\\Properties"
                    try:
                        with winreg.OpenKey(
                            winreg.HKEY_LOCAL_MACHINE, properties_path
                        ) as properties:
                            name, _ = winreg.QueryValueEx(properties, name_key)
                    except OSError:
                        continue
                    if name != "External Mic":
                        continue
                    fx_path = f"{capture_path}\\{endpoint}\\FxProperties"
                    try:
                        with winreg.OpenKey(
                            winreg.HKEY_LOCAL_MACHINE, fx_path
                        ) as effects:
                            disabled, _ = winreg.QueryValueEx(effects, disable_fx_key)
                        return "отключены" if int(disabled) == 1 else "включены"
                    except OSError:
                        return "не удалось проверить"
        except OSError:
            pass
        return "endpoint не найден"

    @staticmethod
    def open_sound_settings() -> None:
        os.startfile("ms-settings:sound")  # type: ignore[attr-defined]

    @staticmethod
    def open_privacy_settings() -> None:
        os.startfile("ms-settings:privacy-microphone")  # type: ignore[attr-defined]

    def _on_test_changed(self) -> None:
        self.instruction_var.set(TESTS[self.test_var.get()]["instruction"])

    def start_test(self) -> None:
        if self.running:
            return
        label = self.device_var.get()
        if label not in self.device_map:
            messagebox.showwarning("Устройство", "Выберите устройство ввода.")
            return
        device_index = self.device_map[label]
        info = sd.query_devices(device_index)
        channels = min(2, int(info["max_input_channels"]))
        if channels < 1:
            messagebox.showerror("Устройство", "Устройство не имеет входных каналов.")
            return
        if channels == 1:
            if not messagebox.askyesno(
                "Только один канал",
                "Устройство сообщает только один входной канал. "
                "Тест независимости невозможен. Всё равно запустить уровень?",
            ):
                return
        try:
            sd.check_input_settings(
                device=device_index,
                channels=channels,
                samplerate=SAMPLE_RATE,
                dtype="float32",
            )
            self.audio_chunks.clear()
            while not self.level_queue.empty():
                self.level_queue.get_nowait()
            self.stream = sd.InputStream(
                device=device_index,
                channels=channels,
                samplerate=SAMPLE_RATE,
                blocksize=BLOCK_SIZE,
                dtype="float32",
                latency="low",
                callback=self._audio_callback,
            )
            self.current_context = {
                "test_name": self.test_var.get(),
                "mode_name": self.mode_var.get(),
                "device_label": label,
                "device_index": device_index,
            }
            self.stream.start()
        except Exception as exc:
            self.stream = None
            messagebox.showerror(
                "Не удалось начать запись",
                f"{exc}\n\nЗакройте приложения, которые используют микрофон, "
                "и попробуйте другое WASAPI-устройство.",
            )
            return

        self.running = True
        self.started_at = time.monotonic()
        self.status_var.set(f"Идёт тест • BOYA: {self.mode_var.get()}")
        self.start_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)
        duration = TESTS[self.test_var.get()]["duration"]
        if duration:
            self.stop_timer = self.root.after(int(duration * 1000), self.stop_test)
        self._update_timer()

    def _audio_callback(
        self,
        indata: np.ndarray,
        _frames: int,
        _time_info: sd.CallbackFlags,
        status: sd.CallbackFlags,
    ) -> None:
        if not self.running and self.started_at != 0:
            return
        chunk = indata.copy()
        self.audio_chunks.append(chunk)
        left_rms = float(np.sqrt(np.mean(chunk[:, 0] ** 2)))
        right_rms = (
            float(np.sqrt(np.mean(chunk[:, 1] ** 2))) if chunk.shape[1] > 1 else 0.0
        )
        self.level_queue.put((dbfs(left_rms), dbfs(right_rms), str(status) if status else ""))

    def _poll_levels(self) -> None:
        try:
            latest: tuple[float, float, str] | None = None
            while True:
                latest = self.level_queue.get_nowait()
        except queue.Empty:
            pass
        if latest:
            left, right, status = latest
            self.left_db_var.set(f"{left:.1f} dBFS")
            self.right_db_var.set(f"{right:.1f} dBFS")
            self.left_meter["value"] = max(0.0, min(60.0, left + 60.0))
            self.right_meter["value"] = max(0.0, min(60.0, right + 60.0))
            if status:
                self.status_var.set(f"Аудио: {status}")
        self.root.after(80, self._poll_levels)

    def _update_timer(self) -> None:
        if not self.running:
            return
        elapsed = time.monotonic() - self.started_at
        self.timer_var.set(f"{int(elapsed // 60):02d}:{int(elapsed % 60):02d}")
        self.root.after(200, self._update_timer)

    def stop_test(self) -> None:
        if not self.running:
            return
        self.running = False
        if self.stop_timer:
            self.root.after_cancel(self.stop_timer)
            self.stop_timer = None
        stream = self.stream
        self.stream = None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        self.start_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)
        self.status_var.set("Анализирую и сохраняю…")
        chunks = self.audio_chunks[:]
        self.audio_chunks.clear()
        threading.Thread(
            target=self._analyze_and_save, args=(chunks,), daemon=True
        ).start()

    def _analyze_and_save(self, chunks: list[np.ndarray]) -> None:
        try:
            if not chunks:
                raise ValueError("Нет записанных данных.")
            audio = np.concatenate(chunks, axis=0)
            result = self._analyze(audio)
            self.session_results.append(result)
            self._write_session_csv()
            self.root.after(0, lambda: self._show_result(result))
        except Exception as exc:
            self.root.after(
                0,
                lambda: messagebox.showerror("Анализ", f"Не удалось обработать тест:\n{exc}"),
            )
            self.root.after(0, lambda: self.status_var.set("Ошибка анализа."))

    def _analyze(self, audio: np.ndarray) -> TestResult:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        test_name = str(self.current_context["test_name"])
        safe_name = (
            test_name.split("—")[0]
            .strip()
            .lower()
            .replace(" ", "_")
            .replace("/", "_")
        )
        selected_mode = str(self.current_context["mode_name"])
        mode_name = selected_mode.lower().replace("/", "_")
        stem = f"{timestamp}_{safe_name}_{mode_name}"
        wav_path = OUTPUT_DIR / f"{stem}.wav"

        normalized = np.clip(audio, -1.0, 1.0)
        wavfile.write(wav_path, SAMPLE_RATE, (normalized * 32767).astype(np.int16))

        left = audio[:, 0].astype(np.float64)
        right = audio[:, 1].astype(np.float64) if audio.shape[1] > 1 else None
        rms_l = float(np.sqrt(np.mean(left**2)))
        peak_l = float(np.max(np.abs(left)))
        dc_l = float(np.mean(left))
        clip_l = float(np.mean(np.abs(left) >= 0.999) * 100.0)

        rms_r = peak_r = dc_r = clip_r = corr = diff_level = balance = separation = None
        verdict = "Моно: тест независимости каналов невозможен."
        if right is not None:
            rms_r_raw = float(np.sqrt(np.mean(right**2)))
            peak_r_raw = float(np.max(np.abs(right)))
            rms_r = dbfs(rms_r_raw)
            peak_r = dbfs(peak_r_raw)
            dc_r = float(np.mean(right))
            clip_r = float(np.mean(np.abs(right) >= 0.999) * 100.0)
            corr = safe_corr(left, right)
            difference = left - right
            diff_rms = float(np.sqrt(np.mean(difference**2)))
            diff_level = dbfs(diff_rms)
            balance = dbfs(rms_l) - dbfs(rms_r_raw)
            separation = abs(balance)
            relative_diff = diff_rms / max(rms_l, rms_r_raw, EPS)
            active_test = "Капсюль" in test_name or "дублирования" in test_name
            signal_too_weak = (
                active_test
                and max(dbfs(rms_l), dbfs(rms_r_raw)) < -40.0
                and max(dbfs(peak_l), dbfs(peak_r_raw)) < -25.0
            )

            if clip_l > 0.01 or clip_r > 0.01:
                verdict = "Перегрузка: уменьшите уровень/усиление и повторите."
            elif signal_too_weak:
                verdict = (
                    "Полезный сигнал слишком слабый: вероятно записан шум входа. "
                    "Проверьте батарею, режим и разъём."
                )
            elif relative_diff < 0.001 or (corr > 0.9995 and separation < 0.2):
                verdict = "Каналы практически дублируются (моно-сумма)."
            elif separation >= 15.0:
                verdict = "Хорошее разделение в этом тесте (≥15 дБ)."
            elif separation >= 6.0:
                verdict = "Разделение есть, но слабое; повторите с изоляцией."
            elif corr > 0.98:
                verdict = "Каналы очень похожи; вероятно суммирование или сильный crosstalk."
            else:
                verdict = "Каналы различаются; для вывода выполните тесты A и B."

        device_label = str(self.current_context["device_label"])
        device_index = int(self.current_context["device_index"])
        info = sd.query_devices(device_index)
        host_api = sd.query_hostapis(info["hostapi"])["name"]
        result = TestResult(
            timestamp=timestamp,
            test=f"{test_name} [{selected_mode}]",
            device=str(info["name"]),
            device_index=device_index,
            host_api=str(host_api),
            sample_rate=SAMPLE_RATE,
            channels=audio.shape[1],
            duration_s=len(audio) / SAMPLE_RATE,
            rms_left_dbfs=dbfs(rms_l),
            rms_right_dbfs=rms_r,
            peak_left_dbfs=dbfs(peak_l),
            peak_right_dbfs=peak_r,
            dc_left=dc_l,
            dc_right=dc_r,
            clipping_left_pct=clip_l,
            clipping_right_pct=clip_r,
            correlation_lr=corr,
            difference_dbfs=diff_level,
            balance_db=balance,
            separation_db=separation,
            verdict=verdict,
            wav_file=str(wav_path),
        )
        with (OUTPUT_DIR / f"{stem}.json").open("w", encoding="utf-8") as file:
            json.dump(asdict(result), file, ensure_ascii=False, indent=2)
        return result

    def _write_session_csv(self) -> None:
        path = OUTPUT_DIR / "latest_session.csv"
        if not self.session_results:
            return
        rows = [asdict(item) for item in self.session_results]
        with path.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def _show_result(self, result: TestResult) -> None:
        def fmt(value: float | None, suffix: str = "") -> str:
            return "—" if value is None else f"{value:.2f}{suffix}"

        self.tree.insert(
            "",
            tk.END,
            values=(
                result.test,
                fmt(result.rms_left_dbfs, " dB"),
                fmt(result.rms_right_dbfs, " dB"),
                fmt(result.correlation_lr),
                fmt(result.separation_db, " dB"),
                result.verdict,
            ),
        )
        session_verdict = self._session_independence_verdict()
        self.status_var.set(
            f"Итог: {session_verdict}" if session_verdict else f"Готово: {result.verdict}"
        )

    def _session_independence_verdict(self) -> str | None:
        mode = str(self.current_context.get("mode_name", ""))
        a_results = [
            result
            for result in self.session_results
            if "Капсюль A" in result.test
            and f"[{mode}]" in result.test
            and result.balance_db is not None
        ]
        b_results = [
            result
            for result in self.session_results
            if "Капсюль B" in result.test
            and f"[{mode}]" in result.test
            and result.balance_db is not None
        ]
        if not a_results or not b_results:
            return None
        a = a_results[-1]
        b = b_results[-1]
        signature = f"{a.timestamp}|{b.timestamp}"
        if (
            max(a.rms_left_dbfs, a.rms_right_dbfs or -120.0) < -40.0
            or max(b.rms_left_dbfs, b.rms_right_dbfs or -120.0) < -40.0
        ):
            verdict = (
                f"{mode}: сигнал теста слишком слабый; независимость капсюлей "
                "не подтверждена."
            )
        elif (
            a.separation_db is not None
            and b.separation_db is not None
            and a.separation_db >= 15.0
            and b.separation_db >= 15.0
            and a.balance_db * b.balance_db < 0
        ):
            verdict = f"{mode}: два независимых канала подтверждены."
        elif (
            a.correlation_lr is not None
            and b.correlation_lr is not None
            and a.correlation_lr > 0.9995
            and b.correlation_lr > 0.9995
        ):
            verdict = f"{mode}: каналы дублируются; вход выглядит моно."
        else:
            verdict = f"{mode}: результат неоднозначен, повторите A и B с лучшей изоляцией."
        if signature != self.summary_signature:
            self.summary_signature = signature
            self.tree.insert(
                "",
                tk.END,
                values=("ИТОГ A + B", "—", "—", "—", "—", verdict),
            )
        return verdict

    def _on_close(self) -> None:
        if self.running:
            self.stop_test()
        self.root.after(100, self.root.destroy)


def main() -> None:
    root = tk.Tk()
    MicrophoneTestApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
