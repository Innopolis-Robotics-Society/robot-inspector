# Робот-инспектор (ROS 2 Humble)

Манипулятор с камерой проверяет деталь по трём критериям, после чего сортирует её в лоток «годно» / «брак»:

1. **Ржавчина** — ResNet-классификатор + UNet-сегментация (ONNX Runtime).
2. **Печатная плата** — YOLO находит компоненты и сравнивает с эталоном, снятым при калибровке (пропавшие / сдвинутые компоненты).
3. **Шестерни** — классическое CV (Hough + подсчёт зубьев), сравнение с эталоном из калибровки.

Деталь считается годной, если: `ржавчины нет` **И** `плата ок` **И** `шестерни ок`.

Сценарий запускается голосовой командой (английский Vosk) или публикацией в `/voice/command`; итог озвучивается через TTS (Kokoro).

---

## Оборудование

- **Манипулятор:** RoboPro RC10 (по умолчанию) или UR (ur3e / ur5e / ur10e / ur16e / ur20 / ur30)
- **Камера:** USB UVC через `v4l2_camera` (по умолчанию `/dev/video0`), закреплена на инструменте
- **Захват:** управляется цифровыми выходами контроллера (`gripper_backend: controller`, пины в `iros_robopro_controller/config/driver.yaml`)
- **Микрофон / динамики** хоста (проброшены в контейнер через PulseAudio)
- **GPU NVIDIA** желателен (YOLO для платы); ржавчина по умолчанию считается на CPU

---

## Пакеты

| Пакет | Назначение |
|---|---|
| `iros_assistant_bringup` | Launch-сценарии (`launch/scenario/inspector.launch.py`, `test_inspector.launch.py`), точки осмотра/сортировки (`launch/world/inspection_poses.launch.py`), обёртка UR (`launch/robots/ur.launch.py`), конфиги RViz |
| `iros_robopro_controller` | Драйвер RoboPro RC10 (`rc_robot_driver`): сервисы `/go_to_frame`, `/gripper_action`, `/gripper_lock`, публикует TF и `tool_pose` / `flange_pose` |
| `iros_cv_session_hub` | Хаб CV: по триггеру вызывает нужный детектор, собирает результат, публикует общий отчёт и `ok`. `launch/cv_stack.launch.py` поднимает весь CV-стек |
| `iros_rust_detect_ros` | Детектор ржавчины (`rust_detect_node`), модели в `onnx_models/` |
| `iros_cv_algorithms` | `pcb_check` (плата, модель `algos/models/yolo11s_best.pt`), `gears_check` (шестерни; алгоритм в `gear_counter.py`) |
| `iros_assistant_behavior` | Узел `inspector`: исполняет рутины из `config/routines.yaml` по командам из `/voice/command` |
| `iros_voice_controlled_robot` | Распознавание речи (Vosk, en), фразы → интенты (`config/tools_config.yaml`), публикует `/voice/command` |
| `iros_text_to_speach` | Озвучивает итоговый отчёт `/cv_hub/report` (Kokoro TTS) |
| `iros_custom_msgs` | `GoToFrame`, `GripperAction`, `MoveToPose`, `DetectObject`, `SetReferenceMesh`; сообщения `PcbCheck`, `Detection2D`, `Statistics`, `ICPAlignmentStatistic` |
| `iros_camera` | Реестр камер (`config/cameras.yaml`) и калибровки — для мультикамерных сценариев |

Пакеты `iros_april_tags`, `iros_tool_recognition`, `iros_ru_voice_recognision`, `launch/bringup.launch.py` и `launch/perception/*` относятся к сценарию робота-ассистента (pick/place) и инспектором не используются.

---

## Быстрый старт

### 1. Контейнер

```bash
git clone -b inspector https://github.com/Innopolis-Robotics-Society/robot-assistants.git
cd robot-assistants
docker compose up terminal          # готовый образ fabook/cv:v0.0.5; Dockerfile в корне (CUDA 12.9)
docker compose exec terminal bash
```

Репозиторий монтируется в контейнер как `/home/mobile/ros2_ws/src`. Нужны: NVIDIA Container Toolkit, `/dev/video0`, `/dev/snd`, X11 (`xhost +local:` на хосте для RViz).

### 2. Сборка

```bash
cd /home/mobile/ros2_ws
colcon build --symlink-install
source install/setup.bash
```

### 3. Сеть до робота (на хосте)

```bash
sudo ./scripts/set_robopro_connection.sh [интерфейс]   # робот 10.10.10.10, хост 10.10.10.1/24
```

Для UR — `scripts/set_ur_connection.sh`.

### 4. Запуск

```bash
# Полный сценарий: камера, TF точек, драйвер робота, CV-стек, голос, TTS, behavior, RViz
ros2 launch iros_assistant_bringup inspector.launch.py

# UR вместо RoboPro
ros2 launch iros_assistant_bringup inspector.launch.py robot_model:=ur10e robot_ip:=<IP>
```

| Аргумент | По умолчанию | |
|---|---|---|
| `robot_model` | `robopro` | `robopro` или тип UR (`ur10e`, …) |
| `robot_ip` | `10.10.10.10` | IP робота (для RoboPro IP задаётся в `driver.yaml`) |
| `video_device` | `/dev/video0` | Камера |

**Отладка CV без робота:** `test_inspector.launch.py` — только камера, TF, CV-стек и RViz (`test_inspector.rviz`), без драйвера, голоса и behavior. Детекторы дёргаются вручную через сервисы (см. ниже).

---

## Рабочий цикл

Рутины описаны в `iros_assistant_behavior/config/routines.yaml`. Запуск — голосом или вручную:

```bash
ros2 topic pub --once /voice/command std_msgs/msg/String \
  "{data: '{\"intent\": \"calibration\", \"confidence\": 100}'}"
```

| Интент | Фразы | Что делает |
|---|---|---|
| `calibration` | calibrate, configure | Едет в `poi_pcb` → эталон платы; едет в `poi_gear_common` → эталон шестерён. **Выполнить один раз на эталонной (годной) детали** |
| `inspect` | inspection, check, inspect | Ржавчина (`poi_gear_common`) → плата (`poi_pcb`) → шестерни (`poi_gear_common`) → публикация отчёта → берёт деталь (`pose_pick`) → кладёт в `pose_drop_ok` или `pose_drop_nok` по `/cv_hub/ok` |
| `reset` | clear, reset | Сбрасывает эталоны платы и шестерён |

`confidence` должен быть ≥ `min_confidence` (50). Рутина — это список шагов `service` / `sleep` / `wait_topic` / `branch`; новые сценарии добавляются там же без правки кода.

### Точки (TF)

Все точки — статические TF от `world` в `iros_assistant_bringup/launch/world/inspection_poses.launch.py`:
`pose_up`, `poi_pcb`, `poi_gear_common`, `pose_pick`, `pose_pick_up`, `pose_drop_ok`, `pose_drop_ok_up`, `pose_drop_nok`, `pose_drop_nok_up`.

**При переносе стенда эти координаты нужно перемерить.** Там же — `world_to_base_*` и TCP (`flange_to_tool_*`) в `iros_robopro_controller/config/driver.yaml`.

---

## Сервисы и топики

### Манипулятор (`rc_robot_driver`)

```bash
ros2 service call /go_to_frame iros_custom_msgs/srv/GoToFrame "{frame: 'poi_pcb'}"
ros2 service call /gripper_action iros_custom_msgs/srv/GripperAction "{open: true}"
ros2 service call /gripper_lock std_srvs/srv/SetBool "{data: true}"
```

### CV-хаб (`/iros_cv_session_hub`, все `std_srvs/Trigger`)

| Сервис | Действие |
|---|---|
| `~/run_rust` | вызывает `/rust_detect/run`, слушает 2 с, запоминает результат |
| `~/run_pcb` | вызывает `/pcb_inspector/inference` |
| `~/run_gear` | вызывает `/gears_check/inference` |
| `~/publish` | однократно публикует сохранённые результаты и серию `/cv_hub/ok` |

Выходы (`/cv_hub/...`): `ok` (Bool), `report` (JSON, его озвучивает TTS), `rust/{prob,detected,report}`, `pcb/{annotated,ok,report}`, `gear/{annotated,ok,report}`.

### Детекторы напрямую

| Узел | Сервисы (`Trigger`) | Топики |
|---|---|---|
| `rust_detect_node` | `/rust_detect/run` | `/rust/prob` (Image), `/rust/detected` (Bool) |
| `pcb_inspector` | `~/calibration`, `~/inference`, `~/reset` | `~/annotated` (Image), `~/report` (JSON) |
| `gears_check` | `~/calibration`, `~/inference`, `~/reset` | `~/image`, `~/brightened` (Image), `~/data` (JSON) |

Пороги детекторов — аргументы `cv_stack.launch.py` (`rust_thr`, `rust_conf_thr`, `rust_device`, …) и параметры узлов. Детектор ржавчины можно поднять отдельно: `ros2 launch iros_rust_detect_ros rust_detect.launch.py`.

Без камеры CV-стек можно гонять на папке с картинками: `ros2 launch iros_cv_session_hub cv_stack.launch.py use_debug_publisher:=true image_dir:=/path/to/images`.

---

## Известные проблемы

- В коде есть абсолютные пути `/home/mobile/ros2_ws/...` (модель платы), рассчитанные на контейнер.
- Альтернативная реализация подсчёта шестерён лежит в ветке `dev` (коммит `final_gears`) и сюда не входит.
