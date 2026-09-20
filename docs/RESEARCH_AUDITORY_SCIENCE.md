# Научная база: восприятие звука, ANC, маскирование, безопасность

Документ для обоснования продукта и ограничений. Включены **подтверждённые публичные источники** (статьи, обзоры в рецензируемых журналах, стандарты ISO/ITU/WHO, открытые PMC).  
Дата сборки: 2026-08-23.  
Правило цитирования в продукте и рекламе: не утверждать «доказано лечит / защищает слух / глушит комнату», если источник этого не говорит.

---

## 1. Главный вывод для инженерии

Задержка **восприятия речи/эха** (порядка 50–200 мс, ITU-T G.114) **не является** пределом для активного шумоподавления.

ANC — это **деструктивная интерференция**. Антишум должен совпасть с шумом по фазе в точке контроля. Допустимая ошибка по времени — доли периода волны:

| Частота | Период | 10° фазы (ориентир) | 30° фазы |
|---|---:|---:|---:|
| 50 Гц | 20 мс | 0.56 мс | 1.67 мс |
| 100 Гц | 10 мс | 0.28 мс | 0.83 мс |
| 250 Гц | 4 мс | 0.11 мс | 0.33 мс |
| 500 Гц | 2 мс | 0.056 мс | 0.17 мс |
| 1000 Гц | 1 мс | 0.028 мс | 0.083 мс |

Задержка 40–400 мс означает, что система «борется» со звуком, которого уже нет. Для **непредсказуемого** широкополосного шума ANC при такой задержке физически невозможен. Для **периодического** низкочастотного шума (вентилятор, гул дороги, компрессор) адаптивный фильтр может предсказывать следующий период — это единственный реалистичный режим speaker-ANC на смартфоне.

Человеческие пороги 2–50 мс относятся к **обнаружению паузы, эха и локализации**, не к условию интерференции.

---

## 2. Физика ANC и зона тишины

### 2.1. Канонические монографии и обзоры

1. **Elliott, S. J., Nelson, P. A.** (1993). Active noise control. *IEEE Signal Processing Magazine*, 10(4), 12–35.  
   DOI: [10.1109/79.248551](https://doi.org/10.1109/79.248551)  
   Открытый PDF (ISVR): https://resource.isvr.soton.ac.uk/staff/pubs/Ref%203%20IEEE%20review%201993.pdf  
   **Факт:** снижение >10 дБ вокруг микрофона ошибки обычно только в зоне размером **примерно λ/10** (Elliott et al., 1988; Joseph, 1990). На 100 Гц это ~0.34 м, на 10 кГц — ~3.4 мм.

2. **Elliott, S. J., Joseph, P. F., Bullmore, A. J., Nelson, P. A.** (1988). Active cancellation at a point in a pure tone diffuse sound field. *Journal of Sound and Vibration*, 120(1), 183–189.  
   DOI: [10.1016/0022-460X(88)90343-4](https://doi.org/10.1016/0022-460X(88)90343-4)

3. **Joseph, P., Elliott, S. J., Nelson, P. A.** (1994). Near field zones of quiet. *Journal of Sound and Vibration*, 172(5), 605–627.  
   DOI: [10.1006/jsvi.1994.1202](https://doi.org/10.1006/jsvi.1994.1202)

4. **Nelson, P. A., Elliott, S. J.** (1992). *Active Control of Sound*. Academic Press, San Diego.  
   ISBN 0125154259. Базовая монография по акустике вторичных источников и глобальному vs локальному контролю.

5. **Elliott, S. J.** (2001). *Signal Processing for Active Control*. Academic Press.  
   Алгоритмы, вторичный тракт, причинность, многоканальность.

6. **Kuo, S. M., Morgan, D. R.** (1996). *Active Noise Control Systems: Algorithms and DSP Implementations*. Wiley, New York.  
   Стандарт по FxLMS, идентификации вторичного тракта, feedforward/feedback.

7. **Kuo, S. M., Morgan, D. R.** (1999). Active noise control: a tutorial review. *Proceedings of the IEEE*, 87(6), 943–973.  
   DOI: [10.1109/5.763310](https://doi.org/10.1109/5.763310)

8. **Elliott, S. J., Nelson, P. A.** (1990). The active control of sound. *Electronics & Communication Engineering Journal*, 2(4), 127–136.  
   DOI: [10.1049/ecej_19900032](https://doi.org/10.1049/ecej_19900032)  
   PDF: https://resource.isvr.soton.ac.uk/staff/pubs/PubPDFs/Pub3473.pdf  
   **Факт:** вторичное поле должно совпасть с первичным **и во времени, и в пространстве**. Пространственное совпадение ограничивает верхнюю частоту глобального ANC сотнями герц.

9. **Kajikawa, Y., Gan, W. S., Kuo, S. M.** (2012). Recent advances on active noise control: open issues and innovative applications. *APSIPA Transactions on Signal and Information Processing*, 1, e3.  
   DOI: [10.1017/ATSIP.2012.4](https://doi.org/10.1017/ATSIP.2012.4)  
   https://www.cambridge.org/core/journals/apsipa-transactions-on-signal-and-information-processing/article/recent-advances-on-active-noise-control-open-issues-and-innovative-applications/9E27156562A24026ECD6F6A49A54F53A

### 2.2. Причинность (causality constraint)

Для feedforward: время от опорного микрофона до точки ошибки должно быть **не меньше**, чем сумма акустической задержки динамик→ошибка + электронная задержка.

Упрощённо: `L_ref / c − L_sec / c ≥ τ_elec`.

Скорость звука ≈ 343 м/с:

| Дистанция смартфон → ухо | Акустический бюджет |
|---|---:|
| 10 см | 0.29 мс |
| 30 см | 0.87 мс |
| 50 см | 1.46 мс |
| 1 м | 2.92 мс |
| 2 м | 5.83 мс |

Любая I/O-задержка больше этого бюджета делает **широкополосный** feedforward некаузальным. Узкополосный/периодический шум можно предсказывать — каузальность ослабляется.

Источник формулировки: обзоры Elliott/Nelson; учебная формулировка в диссертациях по ASC (см. также обсуждение Lueg, 1936; Morgan, 1980; Kuo & Morgan, 1996).

### 2.3. Размер зоны тишины (для «дистанции от смартфона»)

Формула продукта: радиус зоны ≈ **λ/10**, λ = c/f.

| Частота | λ | λ/10 (ориентир зоны) |
|---|---:|---:|
| 50 Гц | 6.86 м | 69 см |
| 80 Гц | 4.29 м | 43 см |
| 100 Гц | 3.43 м | 34 см |
| 200 Гц | 1.72 м | 17 см |
| 400 Гц | 0.86 м | 8.6 см |
| 800 Гц | 0.43 м | 4.3 см |
| 2000 Гц | 0.17 м | 1.7 см |

**Следствие для фичи «без наушников»:** реалистично глушить гул 50–200 Гц в пятне у телефона. Речь, дрель, посуду, клавиатуру — нет. Слайдер дистанции должен сужать полосу и честно показывать ожидаемую зону, а не обещать «тишину на 3 метра».

### 2.4. Виртуальный микрофон / virtual sensing (научная основа слайдера дистанции)

10. **Garcia-Bonito, J., Elliott, S. J., Boucher, C. C.** (1997). Generation of zones of quiet using a virtual microphone arrangement. *Journal of the Acoustical Society of America*, 101(6), 3498–3516.  
    DOI: [10.1121/1.418357](https://doi.org/10.1121/1.418357)  
    Зону тишины можно **сдвигать** от физического микрофона ошибки к виртуальной точке (например, к уху), если первичные поля в этих точках похожи.

11. **Shi, D., Gan, W. S., Lam, B., Wen, S.** (и последующие работы группы NTU, 2020–2024). Selective / transferable virtual sensing ANC.  
    Пример: Wang, B. et al. (2024). Transferable Selective Virtual Sensing Active Noise Control Technique Based on Metric Learning. arXiv: [2409.05470](https://arxiv.org/abs/2409.05470)

Это правильная научная рамка для «регулировки дистанции»: не усиливать динамик «наугад», а оценивать ошибку в виртуальной точке.

### 2.5. Personal audio / acoustic contrast (массивы, не один динамик телефона)

12. **Choi, J.-W., Kim, Y.-H.** (2002). Generation of an acoustically bright zone with an illuminated region using multiple sources. *JASA*, 111(4), 1695–1700.

13. **Elliott, S. J., Cheer, J., Murfet, H., Holland, K.** (2010). Minimally radiating sources for personal audio. *JASA*, 128(4), 1721–1728.  
    DOI: [10.1121/1.3479758](https://doi.org/10.1121/1.3479758)

14. **Cheer, J., Elliott, S. J.** и др. — personal audio в авто и на мобильных устройствах (ICASSP / JAES, 2013–2019).  
    Пример: Wallace, D., Cheer, J. (2019). The Design of Personal Audio Systems for Speech Transmission… *ICASSP*. DOI: [10.1109/ICASSP.2019.8683269](https://doi.org/10.1109/ICASSP.2019.8683269)

Один динамик смартфона **не образует** полноценную personal-audio зону. Массив (телефон + наушники / внешняя колонка / два телефона) — отдельная R&D-ветка.

### 2.6. Нейросетевой ANC (не путать с denoising звонка)

15. **Zhang, H., Wang, D. L.** (2021). Deep ANC: A deep learning approach to active noise control. *Neural Networks*, 141, 1–10.  
    DOI: [10.1016/j.neunet.2021.03.037](https://doi.org/10.1016/j.neunet.2021.03.037)  
    PMC: [PMC8328877](https://pmc.ncbi.nlm.nih.gov/articles/PMC8328877/)  
    CRN предсказывает антишум по опорному сигналу; есть стратегия компенсации задержки; зона тишины моделировалась как сфера **радиуса ~5 см**.

16. **Zhang, H., Wang, D. L.** (2023). Deep MCANC. *Neural Networks*, 158, 318–327.  
    DOI: [10.1016/j.neunet.2022.11.029](https://doi.org/10.1016/j.neunet.2022.11.029)  
    PDF: https://pnlwang.github.io/papers/Zhang-Wang.nn23.pdf

17. **Shi, D. et al.** (2023). Generative fixed-filter ANC (GFANC). arXiv: [2303.05788](https://arxiv.org/abs/2303.05788)  
    Лёгкая 1D-CNN на сопроцессоре (в т.ч. телефон) подбирает комбинацию предвычисленных фильтров — практичный путь для мобильного NN-ANC, а не «большая языковая модель».

**Важно:** нейросеть не отменяет λ/10 и каузальность. Она помогает с нелинейностью динамика и сменой типа шума.

Нейросетевое **очищение микрофона для звонка** (RNNoise, DeepFilterNet, Voice Isolation) — другая задача: нет излучения антишума в воздух.

---

## 3. Время: разрешение слуха, эхо, речь

Эти цифры **нельзя** подставлять как бюджет ANC. Они нужны для UI, маскирования, звонков и звуковых сцен.

### 3.1. Обнаружение паузы (gap detection)

18. **Plomp, R.** (1964). Rate of decay of auditory sensation. *JASA*, 36, 277–282.

19. **Shailer, M. J., Moore, B. C. J.** (1983). Gap detection as a function of frequency, bandwidth, and level. *JASA*, 74, 467–473.

20. **Rummell, B. P. et al.** (2014). Cortical activity associated with the detection of temporal gaps in tones. *Frontiers in Neuroscience*.  
    PMC: [PMC4191557](https://pmc.ncbi.nlm.nih.gov/articles/PMC4191557/)  
    **Факт:** within-channel gap threshold обычно **2–3 мс** (Plomp, 1964; Penner, 1977). Between-channel (разные частоты) — до **~50 мс**.

### 3.2. Precedence / Haas / порог эха

21. **Wallach, H., Newman, E. B., Rosenzweig, M. R.** (1949). The precedence effect in sound localization. *American Journal of Psychology*, 62, 315–336.

22. **Haas, H.** (1951). Über den Einfluss eines Einfachechos auf die Hörsamkeit von Sprache. *Acustica*, 1, 49–58. (Haas effect)

23. **Litovsky, R. Y., Colburn, H. S., Yost, W. A., Guzman, S. J.** (1999). The precedence effect. *JASA*, 106(4), 1633–1654.  
    DOI: [10.1121/1.427914](https://doi.org/10.1121/1.427914)

24. **Brown, A. D., Stecker, G. C., Tollin, D. J.** (2015). The precedence effect in sound localization. *Journal of the Association for Research in Otolaryngology*, 16, 1–28.  
    PMC: [PMC4310855](https://pmc.ncbi.nlm.nih.gov/articles/PMC4310855/)  
    **Факт:** порог эха в литературе — примерно **2–100+ мс** в зависимости от стимула; для речи часто десятки мс; для музыки может быть ближе к 100 мс.

### 3.3. Задержка в телефонии (не ANC)

25. **ITU-T Recommendation G.114** (2003/2009). One-way transmission time.  
    https://www.itu.int/rec/T-REC-G.114  
    Ориентир: **<150 мс** в одну сторону — хорошо; 150–400 мс — растущая деградация разговора; >400 мс — плохо.  
    Это про диалог, не про интерференцию.

26. **ITU-T G.131** — talker echo. Эхо >~30–50 мс при достаточном уровне уже слышно как отдельный звук.

---

## 4. Локализация: направление, интенсивность, дистанция

### 4.1. Направление (азимут, высота)

27. **Blauert, J.** (1997, rev.). *Spatial Hearing: The Psychophysics of Human Sound Localization*. MIT Press.  
    Канон: ITD, ILD, спектральные (pinna) cues, конус неразличимости, HRTF.

28. **Middlebrooks, J. C., Green, D. M.** (1991). Sound localization by human listeners. *Annual Review of Psychology*, 42, 135–159.  
    DOI: [10.1146/annurev.ps.42.010191.001031](https://doi.org/10.1146/annurev.ps.42.010191.001031)

29. **Rayleigh, Lord** (1907). On our perception of sound direction. *Philosophical Magazine*, 13, 214–232.  
    Дуплексная теория: ITD на низких частотах, ILD на высоких.

30. **Klumpp, R. G., Eady, H. R.** (1956). Some measurements of interaural time difference thresholds. *JASA*, 28, 859–860.  
    Порог ITD у лучших слушателей порядка **~10 мкс**.

31. **Zwislocki, J., Feldman, R. S.** (1956). Just noticeable differences in dichotic phase. *JASA*, 28, 860–864.

32. **Wightman, F. L., Kistler, D. J.** (1992). The dominant role of low-frequency interaural time differences in sound localization. *JASA*, 91, 1648–1661.

33. **Carlini, A., Bordeau, C., Ambard, M.** (2024). Auditory localization: a comprehensive practical review. *Frontiers in Psychology*, 15, 1408073.  
    DOI: [10.3389/fpsyg.2024.1408073](https://doi.org/10.3389/fpsyg.2024.1408073)  
    Открытый обзор 2024: ITD/ILD, DRR, ближнее поле <1 м.

**Для продукта:** антишум из динамика телефона сам является **новым источником**. Если фаза не совпала, пользователь услышит не «тишину», а смещённый/раздвоенный источник (два динамика: шум + телефон). Это риск безопасности и UX, не только «не сработало».

### 4.2. Интенсивность и громкость

34. **Fletcher, H., Munson, W. A.** (1933). Loudness, its definition, measurement and calculation. *JASA*, 5, 82–108.  
    Исторические equal-loudness contours.

35. **ISO 226:2023.** Acoustics — Normal equal-loudness-level contours.  
    Актуальный стандарт (ревизия 2003→2023, практические отличия ≤0.6 дБ).  
    https://www.iso.org/standard/83117.html

36. **Suzuki, Y., Takeshima, H.** и коллеги — ревизия ISO 226 (публикации 2003/2023).  
    ResearchGate: Revision of ISO 226 from 2003 to 2023.

37. **Moore, B. C. J.** (2012, 6th ed.). *An Introduction to the Psychology of Hearing*. Brill / Emerald.  
    Критические полосы, громкость, маскирование, временное разрешение.

38. **Fastl, H., Zwicker, E.** (2007). *Psychoacoustics: Facts and Models*. Springer.

39. **ISO 532-1 / 532-2** — методы расчёта громкости (Zwicker / Moore-Glasberg). Для дозиметра и UI «насколько громко».

Ориентир JND по уровню: около **0.5–1 дБ** для широкополосного шума на средних уровнях (классическая психоакустика; детали зависят от частоты и уровня — см. Moore).  
Для слайдера громкости/дистанции шаг мельче 1 дБ пользователь почти не заметит.

A-взвешивание (dBA) происходит из контура ~40 phon и **плохо** описывает низкочастотный гул, который как раз является целью speaker-ANC. Для НЧ лучше смотреть dBZ / dBC и phon.

### 4.3. Дистанция

40. **Zahorik, P.** (2002). Assessing auditory distance perception using virtual acoustics. *JASA*, 111, 1832–1846.

41. **Zahorik, P., Brungart, D. S., Bronkhorst, A. W.** (2005). Auditory distance perception in humans: A summary of past and present research. *Acta Acustica united with Acustica*, 91(3), 409–420.  
    **Факт:** оценка дистанции — сжимающая степенная функция; дальние источники систематически **недооцениваются**. Основные куи: уровень, **direct-to-reverberant ratio (DRR)**, знакомость источника, спектр, в ближнем поле — ILD.

42. **Bronkhorst, A. W., Houtgast, T.** (1999). Auditory distance perception in rooms. *Nature*, 397, 517–520.  
    DOI: [10.1038/17374](https://doi.org/10.1038/17374)

43. **Zahorik, P.** (2002). Auditory display of sound source distance. *ICAD*.  
    PDF: http://www.icad.org/Proceedings/2002/Zahonk2002.pdf  
    Для симуляции дистанции важнее качественный DRR, чем индивидуальный HRTF; HRTF критичен для **направления**.

**Для слайдера «дистанция работы»:** пользователь не линейно слышит метры. UI лучше в «у телефона / на столе / у подушки», а внутри — virtual sensing + полоса частот, не «3.00 м».

---

## 5. Маскирование

44. **Fletcher, H.** (1940). Auditory patterns. *Reviews of Modern Physics*, 12, 47–65.  
    Критическая полоса: маскирует в основном шум **в той же полосе**, что и сигнал.

45. **Moore, B. C. J.** (1989/позднее). Critical bands и auditory filters — обзорные главы; классика курса:  
    https://www.cns.nyu.edu/~david/courses/perceptionGrad/Readings/Moore1989.pdf

46. **ANSI S3.5 / Speech Intelligibility Index (SII)** (1997, обновления).  
    Количественная мера, насколько шум/маскер убивает разборчивость речи.

47. Временное маскирование (forward ~100–200 мс, backward короче) — Fastl & Zwicker; обзор Hearing Review Temporal Processing Primer:  
    https://hearingreview.com/practice-building/practice-management/a-temporal-processing-primer

**Следствие:** «пассивное шумоподавление» **без наушников** в приложении — это почти всегда **маскирование** (розовый/коричневый шум, дождь, вентилятор), а не изоляция. Изоляция требует барьера (чаша наушника, беруши, стена). Честно называть слой Masking / Soundscapes, не «passive ANC», если нет наушников.

Маскер должен перекрывать **те же критические полосы**, что и мешающий шум. Розовый шум лучше кроет низ, белый — верх и часто раздражает.

---

## 6. Сон, концентрация, «звуки для релаксации»

Источники **не доказывают**, что приложение лечит бессонницу. Они показывают эффект маскирования/фонового шума в ограниченных выборках.

48. **Messineo, L. et al.** (2017). Broadband Sound Administration Improves Sleep Onset Latency in Healthy Subjects in a Model of Transient Insomnia. *Frontiers in Neurology*, 8, 718.  
    DOI: [10.3389/fneur.2017.00718](https://doi.org/10.3389/fneur.2017.00718)  
    RCT, n=18: широкополосный звук ~46 дБ vs фон ~40 дБ; латентность до N2 снижена (**медиана −38%**). Модель транзиторной инсомнии (лёг спать на 90 мин раньше).

49. **Vincens, N. et al.** (2026). Pink noise reduces impact of traffic noise on sleep and the blood metabolome: a cross-over pilot study. *Communications Medicine*.  
    DOI: [10.1038/s43856-026-01380-5](https://doi.org/10.1038/s43856-026-01380-5)  
    ClinicalTrials.gov: NCT05319262. n=12, PSG. Розовый шум 45 dBA ослабляет фрагментацию сна от транспорта 45–65 dB; **один розовый шум vs тишина значимо сон не ломает**.

50. Протокол ICU-маскирования розовым шумом:  
    *PLOS ONE* (2023). DOI: [10.1371/journal.pone.0286180](https://doi.org/10.1371/journal.pone.0286180)

51. Сравнение берушей и розового шума при прерывистом шуме: Sleep Health / связанные работы группы Basner (ClinicalTrials.gov NCT05774977). Беруши часто **эффективнее** розового шума против пробуждений — аргумент в пользу режима «наушники/беруши + маскер», а не только динамик телефона.

Концентрация / «brown noise for ADHD»: качественных крупных RCT мало; не использовать медицинские формулировки. Допустимо: «фоновый шум, который часть пользователей находит полезным для фокуса», со ссылкой на маскирование отвлекающих транзиентов (та же психоакустика Fletcher/Moore).

Уровень маскера для сна в исследованиях — примерно **40–50 dBA**, не «на всю». Это надо зашить в лимиты и калибровку.

---

## 7. Безопасность слуха и регуляторика (для стора и дисклеймеров)

52. **WHO** (2018). *Environmental Noise Guidelines for the European Region*.  
    https://www.who.int/europe/publications/i/item/9789289053563  
    Досуговый шум: условная рекомендация **70 dB LAeq,24h** среднегодового.

53. **ITU-T H.870** (2018+). Guidelines for safe listening devices/systems.  
    https://www.itu.int/rec/T-REC-H.870  
    Совместный стандарт WHO–ITU:  
    - взрослые: **80 dBA / 40 ч в неделю** (1.6 Pa²h / 7 дней);  
    - чувствительные/дети: **75 dBA / 40 ч**.  
    Рекомендованы дозиметр, лимит громкости, информирование.  
    ANC/изоляция **снижают** нужную громкость музыки — это аргумент *в пользу* наушникового режима, не speaker-ANC.

54. **WHO toolkit for safe listening** (PDF):  
    https://cdn.who.int/media/docs/default-source/documents/health-topics/deafness-and-hearing-loss/toolkit-for-safe-listening-rev1.pdf

55. **NIOSH REL**: 85 dBA за 8 ч (критерий проф. экспозиции). Не путать с досуговым WHO.

56. **Google Play — Health Content and Services**:  
    https://support.google.com/googleplay/android-developer/answer/12261419  
    Если нет регистрации медицинского изделия: в сторе явный дисклеймер  
    *«не медицинское изделие и не диагностирует, не лечит и не предотвращает заболевания»*.  
    Запрещены вводящие в заблуждение health-заявления.

57. **Android 14+ foreground service `microphone`**:  
    https://developer.android.com/develop/background-work/services/fgs/service-types  
    Фоновый микрофон только из видимого UI + постоянное уведомление + декларация в Play Console.

58. **Apple App Store**: Background Modes (`audio`), Privacy Nutrition Labels, микрофон usage string. System-wide перехват чужих звонков на iOS **недоступен** обычным приложениям.

Рекламные формулировки, которые источники **поддерживают**:

- «снижает низкочастотный гул в небольшой зоне у устройства» (Elliott/Joseph, при условии измерения);
- «фоновый звук может ускорить засыпание у части людей» (Messineo 2017, малая выборка);
- «следим за дозой прослушивания по WHO–ITU H.870».

Формулировки, которые источники **опровергают или не поддерживают**:

- «глушим всю комнату / ремонт / любой шум»;
- «задержка 200 мс достаточна для ANC»;
- «лечение бессонницы / СДВГ / защиты слуха как мед. изделие» без регистрации.

---

## 8. Платформенная задержка (инженерия, не психофизика)

59. **PortAudio WASAPI**: exclusive event-driven ~**3 мс** на HD Audio; shared не ниже ~**20 мс** (часто 20–40+ мс).  
    https://files.portaudio.com/docs/v19-doxydocs/pa__win__wasapi_8h_source.html

60. **FlexASIO BACKENDS.md**: внутренний буфер shared pipeline Windows наблюдался как **10 мс**; ниже 10 мс — только exclusive / WDM-KS.  
    https://github.com/dechamps/FlexASIO/blob/master/BACKENDS.md

61. **Android Oboe / AAudio**: exclusive + LowLatency + callback; ориентир Google ~**20 мс** round-trip при правильной конфигурации, сотни мс если режим не low-latency / неверный sample rate.  
    https://developer.android.com/games/sdk/oboe/low-latency-audio  
    https://github.com/google/oboe/blob/main/docs/FullGuide.md

62. **iOS Core Audio / AVAudioEngine**: типичный I/O buffer 64–256 фреймов @ 48 кГц ≈ 1.3–5.3 мс на буфер; полный round-trip обычно несколько мс на встроенном железе, хуже через BT.

63. **Bluetooth Classic A2DP**: часто 100–200+ мс — software-ANC через BT-наушники практически невозможен. **Провод / USB-C / LE Audio (LC3)** — единственные реалистичные наушниковые пути для *нашего* DSP.

64. **WSL/WSLg**: дополнительный hop PulseAudio/PipeWire. Для ANC **не использовать**.

---

## 9. Как эти источники входят в решение

| Модуль продукта | Что берём из науки | Чего не обещаем |
|---|---|---|
| Speaker ANC (фича №1) | λ/10, каузальность, FxLMS, virtual sensing, только НЧ и периодический шум | Тишина комнаты, речь, дрель, >400 Гц на метре |
| Слайдер дистанции | Virtual microphone (Garcia-Bonito); зона сжимается с частотой | Линейные «метры тишины» |
| Наушники | Классический ANC + пассивная изоляция; H.870 | Победа над Bose/Sony без своего DSP-железа |
| «Пассив» без наушников | Маскирование, критические полосы | Acoustic insulation |
| Сон / фокус | Messineo 2017; розовый шум vs транспорт 2026; уровень 40–50 dBA | Лечение инсомнии |
| Звонок / конференция | NN denoising на микрофоне; G.114 для голоса | Room ANC во время звонка |
| Безопасность | ISO 226, H.870, Play Health policy | «Защита слуха» как мед. claim |
| Локализация антишума | Blauert, ITD ~10 мкс | Игнорировать фантомный источник при срыве фазы |

---

## 10. Приоритет чтения (короткий список)

1. Elliott & Nelson, IEEE SPM 1993 (PDF ISVR) — физика зоны.  
2. Kuo & Morgan, Proc. IEEE 1999 — алгоритмы.  
3. Garcia-Bonito et al., JASA 1997 — виртуальный микрофон.  
4. Zhang & Wang, Neural Networks 2021 (PMC8328877) — deep ANC и зона 5 см.  
5. Blauert, *Spatial Hearing* + Zahorik et al. 2005 — пространство и дистанция.  
6. ISO 226:2023 + ITU-T H.870 — громкость и безопасность.  
7. Messineo et al. 2017 + Vincens et al. 2026 — сон и маскирование.  
8. ITU-T G.114 — только для голосовых сценариев.  
9. Oboe low-latency guide + PortAudio WASAPI notes — бюджет задержки на ОС.

Новые статьи добавлять сюда с DOI/PMC и одной строкой «какой модуль продукта это ограничивает».
