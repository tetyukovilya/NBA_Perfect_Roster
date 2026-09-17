# NBA Проект

Этот проект анализирует исторические данные игроков NBA/ABA, чтобы определить лучшие общие, атакующие и защитные пятерки игроков. Он выходит за рамки простого ранжирования, моделируя игры между составами с учётом химии игроков (похожести стиля игры и共同 игрового времени).

## Структура репозитория
```
NBA_project/
├─ data/
│   └─ Players.csv          # исходная статистика игроков по сезонам
├─ src/
│   ├─ __init__.py
│   └─ analyze_nba.py       # основной скрипт: загружает данные, считает составы, запускает симуляцию
├─ starting_five_2026.md    # результаты в формате markdown (генерируются analyze_nba.py)
└─ README.md                # этот файл
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
1. **Статистическое ранжирование**
   - Лучшая общая пятерка (по WS)
   - Лучшая атакующая пятерка (по OWS)
   - Лучшая защитная пятерка (по DWS)
   - Дубликаты игроков удаляются – каждый игрок встречается не более одного раза в каждом списке.

2. **Симуляция с учётом химии**
   - Каждому игроку присваиваются нормализованные показатели атаки и защиты.
   - Химия между двумя игроками вычисляется по формуле:
     ```
     химия = w1 * косинусное_схожесть(вектор_навыков_i, вектор_навыков_j)
             + w2 * log(1 + совмесное_игровое_минут_ij)
             - w3 * |usage_i - usage_j|
     ```
     где вектор навыков = [offs, defs, 3p%, ast%, trb%]
   - Podczas posiadania piłki prawdopodobieństwo trafnego rzutu jest zwiększane przez sumę chemii z kolegami z drużyny.
   - Symulowane gry składają się z konfigurowalnej liczby posiadania (domyślnie 100 na mecz).
   - Skrypt przeprowadza rozgrywkę systemem „każdy z każdym” (domyślnie 30 meczów na każdy pojedynek) i raportuje średnią różnicę punktową na mecz.

3. **Вывод в markdown**
   - Результаты записываются в `starting_five_2026.md` с четкими заголовками, таблицами и подведением итогов симуляции.

## Требования
- Python 3.8+
- Только стандартная библиотека (нет внешних зависимостей).  
  Скрипт использует `csv`, `os`, `math`, `random`, `collections`.

## Установка
1. Склонируйте или скопируйте этот репозиторий в желаемое место.
2. Убедитесь, что файл `data/Players.csv` присутствует (он включён в репозиторий).
3. Дополнительных пакетов устанавливать не нужно.

## Использование
Запустите анализ и симуляцию из корня проекта:

```bash
cd путь/к/NBA_project
python src/analyze_nba.py
```

Скрипт выполнит следующие действия:
- Загрузит и нормализует данные игроков.
- Посчитает три лучшие пятерки игроков (без повторяющихся игроков).
- Запустит симуляцию игр между составами с учётом химии.
- Запишет результаты в `starting_five_2026.md`.

### Пример вывода (фрагмент)
```
# Лучшая общая пятерка (Win Shares) – Все время
## Лучшая общая пятерка (WS)
1. **Michael Jordan** (CHI SG, 1988 NBA) WS:21.20 | OBPM:8.80 DBPM:4.20 VORP:12.50 PER:31.7
2. **LeBron James** (CLE SF, 2009 NBA) WS:20.30 | OBPM:9.50 DBPM:3.70 VORP:11.80 PER:31.7
...

# Результаты симуляции (с учётом химии)
Каждая пятерка сыграла 30 матчей против каждой из остальных двух.
Вес бонуса химии: 0.1 (коэффициент масштабирования).

## Общая пятерка
Средняя разница очков за игру против других составов: 8.87 очков

## Атакующая пятерка
Средняя разница очков за игру против других составов: -7.93 очков

## Защитная пятерка
Средняя разница очков за игру против других составов: 13.03 очков
```

## Настройка
- Отрегулируйте константы в начале файла `src/analyze_nba.py`:
  - `LEAGUE_FG` – средний процент попаданий с поля в лиге.
  - `POSSESSIONS_PER_GAME` – количество владений за сыгранную игру в симуляции.
  - `NUM_GAMES_SIM` – число игр, которое каждая пятерка проводит против каждой другой.
  - `W_SIM`, `W_CO`, `W_USG_DIFF` – веса в формуле химии.
- Чтобы изменить путь к выходному файлу, поправьте переменную `OUTPUT_PATH`.

## Расширение проекта
- **Другие пятерки**: генерировать составы по другим метрикам (например, PER, VORP), вызывая `top_unique` с другим ключом.
- **Более сложная симуляция**: добавить модели штрафных бросков, потерь, фолов, усталости, ротаций составов.
- **Машинное обучение**: рассматривать разницу очков симуляции как метку и обучать регрессионную модель, которая предсказывает эффективность состава напрямую из агрегированной статистики игроков.
- **Визуализация**: строить графы химии, распределения результатов симуляции или тепловые карты win-rate с помощью `matplotlib` или `seaborn` (требуется добавить эти пакеты в `requirements.txt`).

## Лицензия
Этот проект предназначен для образовательного и личного использования. Вы свободно можете адаптировать и расширять его по своему усмотрению.

## Благодарности
- Basketball‑Reference и другие открытые источники за базовую статистику.
- Сообщество открытого исходного кода за инструменты и вдохновение.

Приятного анализа данных и моделирования dream team! 🚀

# NBA Project

This project analyzes historical NBA/ABA player data to determine the best overall, offensive, and defensive five‑player line‑ups. It goes beyond simple ranking by simulating games between line‑ups while accounting for player chemistry (playstyle similarity and shared minutes).

## Repository Structure
```
NBA_project/
├─ data/
│   └─ Players.csv          # raw player‑season statistics (source)
├─ src/
│   ├─ __init__.py
│   └─ analyze_nba.py       # main script: loads data, computes line‑ups, runs simulation
├─ starting_five_2026.md    # results in markdown format (generated by analyze_nba.py)
└─ README.md                # this file
```

## Data Source
- `data/Players.csv` contains per‑player advanced statistics for multiple seasons (including NBA and ABA).
- Key columns used:
  - `ows` – Offensive Win Shares
  - `dws` – Defensive Win Shares
  - `ws` – Win Shares (overall)
  - `obpm`, `dbpm` – Offensive/Defensive Box Plus/Minus
  - `vorp` – Value Over Replacement Player
  - `per` – Player Efficiency Rating
  - `usg_percent` – Usage Rate
  - `ast_percent`, `stl_percent`, `blk_percent`, `tov_percent`, `reb_percent`, `ts_percent`, `x3p_ar`, `f_tr`, `mp`
  - `player`, `team`, `pos`, `season`, `lg`

## Features
1. **Statistical Ranking**
   - Best Overall Five (by WS)
   - Best Offensive Five (by OWS)
   - Best Defensive Five (by DWS)
   - Duplicate players are removed – each player appears at most once per list.

2. **Chemistry‑Aware Simulation**
   - Each player receives normalized offensive/defensive skill scores.
   - Chemistry between two players is computed as:
     ```
     chemistry = w1 * cosine_similarity(skill_vec_i, skill_vec_j)
                 + w2 * log(1 + co_play_minutes_ij)
                 - w3 * |usage_i - usage_j|
     ```
     where `skill_vec = [offs, defs, 3p%, ast%, trb%]`
   - During a possession, the ball handler’s shot probability is boosted by the sum of chemistries with his teammates.
   - Simulated games consist of a configurable number of possessions (default 100 per game).
   - The script runs a round‑robin series (30 games per matchup by default) and reports the average point difference per game.

3. **Markdown Output**
   - Results are written to `starting_five_2026.md` with clear headings, tables, and simulation summary.

## Requirements
- Python 3.8+
- Standard library only (no external dependencies).  
  The script uses `csv`, `os`, `math`, `random`, `collections`.

## Installation
1. Clone or copy this repository to your desired location.
2. Ensure the `data/Players.csv` file is present (it is included in the repo).
3. No additional packages are required.

## Usage
Run the analysis and simulation from the project root:

```bash
cd path/to/NBA_project
python src/analyze_nba.py
```

The script will:
- Load and normalize player data.
- Compute the three best five‑player line‑ups (no duplicate players).
- Simulate games between the line‑ups using the chemistry model.
- Write the results to `starting_five_2026.md`.

### Example Output (excerpt)
```
# Best Overall Five (Win Shares) – All Time
## Best Overall Five (WS)
1. **Michael Jordan** (CHI SG, 1988 NBA) WS:21.20 | OBPM:8.80 DBPM:4.20 VORP:12.50 PER:31.7
2. **LeBron James** (CLE SF, 2009 NBA) WS:20.30 | OBPM:9.50 DBPM:3.70 VORP:11.80 PER:31.7
...

# Simulation Results (Chemistry Adjusted)
Each lineup simulated 30 games against each of the other two lineups.
Chemistry bonus weight: 0.1 (scale factor).

## Overall Lineup
Average point difference per game vs other lineups: 8.87 points

## Offense Lineup
Average point difference per game vs other lineups: -7.93 points

## Defense Lineup
Average point difference per game vs other lineups: 13.03 points
```

## Customization
- Adjust constants at the top of `src/analyze_nba.py`:
  - `LEAGUE_FG` – league average field goal percentage.
  - `POSSESSIONS_PER_GAME` – possessions per simulated game.
  - `NUM_GAMES_SIM` – number of games each lineup plays against each opponent.
  - `W_SIM`, `W_CO`, `W_USG_DIFF` – weights for the chemistry formula.
- To change the output file location, modify `OUTPUT_PATH`.

## Extending the Project
- **Additional Line‑ups**: generate line‑ups based on other metrics (e.g., PER, VORP) by calling `top_unique` with a different key.
- **More Sophisticated Simulation**: incorporate play‑by‑play types (free throws, turnovers, fouls), fatigue models, or lineup‑specific rotations.
- **Machine Learning**: treat the simulated point difference as a label and train a regression model to predict lineup performance directly from aggregated player statistics.
- **Visualization**: plot chemistry networks, simulation distributions, or win‑rate heatmaps using `matplotlib` or `seaborn` (would require adding those packages to `requirements.txt`).

## License
This project is for educational and personal use. Feel free to adapt and expand it as you wish.

## Acknowledgments
- Basketball‑Reference and other public sources for the underlying statistics.
- The open‑source community for tools and inspiration.

Enjoy exploring the data and simulating dream teams! 🚀