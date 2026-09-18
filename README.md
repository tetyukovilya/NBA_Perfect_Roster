# NBA Проект

Этот проект анализирует исторические данные игроков NBA/ABA, чтобы определить лучшие общие, атакующие и защитные пятерки игроков с учётом позиции (по одному игроку на каждую позицию: PG, SG, SF, PF, C) и без повторяющихся игроков.
Помимо простого ранжирования по статистике, проект моделирует игры между составами, учитывая химию игроков (похожесть стиля игры и совместное игровое время).

## Структура репозитория

```
NBA_project/
├─ data/
│   └─ Players.csv          # исходная статистика игроков по сезонам
├─ nba_analysis/            # пакет анализа
│   ├─ __init__.py
│   ├─ cli.py               # командная строка
│   ├─ config.py            # константы и настройки
│   ├─ models.py            # dataclasses Player, Lineup
│   ├─ data_loader.py       # загрузка и нормализация данных
│   ├─ lineup_builder.py    # построение пятерок по позициям
│   ├─ chemistry.py         # расчёт химии между игроками
│   ├─ simulation.py        # симуляция игр
│   ├─ reporter.py          # генерация Markdown-отчётов
│   └─ main.py              # основной pipeline
├─ tests/
│   └─ test_nba_analysis.py # юнит-тесты
├─ starting_five_2026.md    # результаты в формате markdown
├─ pyproject.toml           # конфигурация пакета
├─ README.md                # этот файл
└─ .gitignore
```

## Источник данных

- `data/Players.csv` содержит продвинутую статистику игроков за многие сезоны (включая NBA и ABA).
- Ключевые столбцы, которые используются:
  - `ows` – Offensive Win Shares (наступательные вкладки в победы)
  - `dws` – Defensive Win Shares (оборонные вкладки в победы)
  - `ws` – Win Shares (общие вкладки в победы)
  - `obpm`, `dbpm` – Offensive/Defensive Box Plus/Minus
  - `vorp` – Value Over Replacement Player
  - `per` – Player Efficiency Rating
  - `usg_percent` – Usage Rate (процент использования мяча игроком)
  - `ast_percent`, `stl_percent`, `blk_percent`, `tov_percent`, `reb_percent`, `ts_percent`, `x3p_ar`, `f_tr`, `mp`
  - `player`, `team`, `pos`, `season`, `lg`

## Возможности

1. **Статистическое ранжирование с позициями**
   - Лучшая общая пятерка (по WS) – по одному игроку на каждую позицию
   - Лучшая атакующая пятерка (по OWS) – по одному игроку на каждую позицию
   - Лучшая защитная пятерка (по DWS) – по одному игроку на каждую позицию
   - В каждом списке отсутствуют дубликаты игроков; также нет двух игроков на одной позиции.

2. **Симуляция с учётом химии**
   - Каждому игроку присваиваются нормализованные показатели атаки и защиты.
   - Химия между двумя игроками вычисляется по формуле:
     ```
     химия = w1 * косинусное_схожесть(вектор_навыков_i, вектор_навыков_j)
             + w2 * log(1 + совмесное_игровое_минут_ij)
             - w3 * |usage_i - usage_j|
     ```
     где вектор навыков = [offs, defs, 3p%, ast%, trb%]
   - При владении мячом вероятность успешного броска повышается на величину, равную суммарному показателю сыгранности с партнерами по команде.
   - Симулируемые матчи состоят из настраиваемого количества владений (по умолчанию — 100 за игру).
   - Скрипт проводит серию матчей по круговой системе (по умолчанию — 10 000 игр в рамках противостояния) и вычисляет среднюю разницу в счете за игру.

3. **Вывод в markdown**
   - Результаты записываются в `starting_five_2026.md` с четкими заголовками, таблицами и подведением итогов симуляции.
   - Для каждого игрока указаны:
     - assigned position (позиция, которую мы ему назначили в составе)
     - original position (позиция, указанная в исходном файле Players.csv)
     - команда, сезон, лига
     - значение метрики (WS, OWS или DWS) и дополнительные показатели (OBPM, DBPM, VORP, PER)

## Требования

- Python 3.8+
- Только стандартная библиотека (нет внешних зависимостей для основного функционала).
- Для тестов: `pytest` (устанавливается через `pip install -e .[dev]`)

## Установка

1. Склонируйте или скопируйте этот репозиторий в желаемое место.
2. Убедитесь, что файл `data/Players.csv` присутствует (он включён в репозиторий).
3. Установите пакет в режиме разработки:

```bash
cd путь/к/NBA_project
pip install -e .
```

Для разработки с тестами:

```bash
pip install -e .[dev]
```

## Использование

### Через командную строку (рекомендуемый способ)

После установки пакета доступна команда `nba-analysis`:

```bash
# Полный анализ с симуляцией 10 000 игр (по умолчанию)
nba-analysis

# Быстрый тест: только 10 игр на матчап
nba-analysis --quick

# Только построить пятерки, без симуляции
nba-analysis --list-lineups

# Настроить параметры
nba-analysis --games 5000 --chem-weight 0.15 --output my_results.md

# Показать справку
nba-analysis --help
```

### Как модуль Python

```python
from nba_analysis import main
main()
```

Или используйте отдельные компоненты:

```python
from nba_analysis.data_loader import load_players, prepare_players, compute_co_play_minutes
from nba_analysis.lineup_builder import lineup_by_position
from nba_analysis.simulation import evaluate_lineup

players = load_players()
players = prepare_players(players)
co_minutes = compute_co_play_minutes(players)

overall = lineup_by_position(players, 'ws')
offense = lineup_by_position(players, 'ows')
defense = lineup_by_position(players, 'dws')

avg_diff = evaluate_lineup(overall, [offense, defense], co_minutes_dict=co_minutes)
```

### Пример вывода (фрагмент)

```
# Best Overall Five (Win Shares) – All Time (One per Position)
1. **Chris Paul** (Assigned Pos: PG, Original Pos: PG, NOH, 2009 NBA) WS:18.30 | OBPM:7.20 DBPM:3.80 VORP:9.90 PER:30.0
2. **Michael Jordan** (Assigned Pos: SG, Original Pos: SG, CHI, 1988 NBA) WS:21.20 | OBPM:8.80 DBPM:4.20 VORP:12.50 PER:31.7
...

# Simulation Results (Chemistry Adjusted)
Each lineup simulated 10000 games against each of the other two lineups.
Chemistry bonus weight: 0.1 (scale factor).

## Overall Lineup
Average point difference per game vs other lineups: 1.85 points

## Offense Lineup
Average point difference per game vs other lineups: -7.92 points

## Defense Lineup
Average point difference per game vs other lineups: 5.97 points
```

## Настройка

Измените константы в `nba_analysis/config.py`:

- `LEAGUE_FG` – средний процент попаданий с поля в лиге.
- `POSSESSIONS_PER_GAME` – количество владений за сыгранную игру в симуляции.
- `NUM_GAMES_SIM` – число игр, которое каждая пятерка проводит против каждой другой.
- `W_SIM`, `W_CO`, `W_USG_DIFF` – веса в формуле химии.
- `CHEMISTRY_BONUS_WEIGHT` – общий масштаб влияния химии на броски.
- `POS_MAP` – маппинг гибридных позиций на стандартные 5.
- `OUTPUT_PATH` – путь к выходному файлу.

## Тестирование

```bash
# Запуск всех тестов
pytest tests/

# С покрытием
pytest tests/ --cov=nba_analysis
```

## Расширение проекта

- **Другие пятерки**: генерировать составы по другим метрикам (например, PER, VORP), вызывая функцию `lineup_by_position` с другим ключом.
- **Более сложная симуляция**: добавить модели штрафных бросков, потерь, фолов, усталости, ротаций составов.
- **Машинное обучение**: рассматривать разницу очков симуляции как метку и обучать регрессионную модель, которая предсказывает эффективность состава напрямую из агрегированной статистики игроков.
- **Визуализация**: строить графы химии, распределения результатов симуляции или тепловые карты win-rate с помощью `matplotlib` или `seaborn` (требуется добавить эти пакеты в `pyproject.toml`).
- **Фильтрация по эпохам**: добавить параметры для выбора только современной NBA, только ABA, или конкретных десятилетий.

## Лицензия

Этот проект предназначен для образовательного и личного использования. Вы свободно можете адаптировать и расширять его по своему усмотрению.

## Благодарности

- Basketball‑Reference и другие открытые источники за базовую статистику.
- Сообщество открытого исходного кода за инструменты и вдохновение.

Приятного анализа данных и моделирования dream team! 🚀