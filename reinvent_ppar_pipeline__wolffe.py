#!/usr/bin/env python3
"""
REINVENT4 RL пайплайн с селективностью между двумя мишенями
Автоматическая настройка DockStream + REINVENT4
"""

import os
import subprocess
import json
import pandas as pd
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════════
# НАСТРОЙКА МИШЕНЕЙ ДЛЯ РАЗНЫХ КЕЙСОВ
# ═══════════════════════════════════════════════════════════════════════════════

# Названия мишеней технические (для файлов, лейблов и т.д.)
TARGET_1_NAME = "ppar_alpha"    # основная мишень (улучшаем) -- например: "ppar_alpha"
TARGET_2_NAME = "ppar_gamma"    # мишень для селективности (ухудшаем) -- например: "ppar_gamma"

# Названия для людей (для вывода и логов)
TARGET_1_LABEL = "PPARα"    # Пишем человеческое название, для вывода на экран
TARGET_2_LABEL = "PPARγ"    # Например: "PPARα"

# Пути к файлам
TARGET_1_PDB = "/mnt/tank/scratch/YOU_USERNAME/targets/ppar_alpha.pdb"     # Меняем название у файла pdb
TARGET_2_PDB = "/mnt/tank/scratch/YOU_USERNAME/targets/ppar_gamma.pdb"     # и пишем ваш username от сервера

# Пути к PDBQT файлам (после обработки Meeko)
TARGET_1_PDBQT = "/mnt/tank/scratch/YOU_USERNAME/targets/ppar_alpha.pdbqt"     # Меняем название у файла pdbqt
TARGET_2_PDBQT = "/mnt/tank/scratch/YOU_USERNAME/targets/ppar_gamma.pdbqt"     # и пишем ваш username от сервера

# ID для docking runs в DockStream
TARGET_1_RUN_ID = "PPARa"   # Например: "PPARa"
TARGET_2_RUN_ID = "PPARg"   # Например: "PPARg"

# НЕ ЗАБУДЬТЕ ПОМЕНЯТЬ ЗДЕСЬ КООРДИНАТЫ НА СВОИ
# Координаты боксов для докинга (настраиваются ПОД КОНКРЕТНЫЕ мишени)
TARGET_1_BOX = {
    "center_x": 13.861, "center_y": -12.946, "center_z": -31.915,
    "size_x": 16.842, "size_y": 9.62, "size_z": 22.206
}

TARGET_2_BOX = {
    "center_x": 22.553, "center_y": -7.676, "center_z": 26.095,
    "size_x": 64.72, "size_y": 77.892, "size_z": 75.448
}

# Настройки трансформации скоров
# Для основной мишени: чем отрицательнее скор, тем лучше (reverse_sigmoid)
TARGET_1_SCORE_HIGH = -10.0  # хороший скор
TARGET_1_SCORE_LOW = -5.0  # плохой скор
TARGET_1_SCORE_K = 0.5

# Для анти-целевой мишени: штрафуем хорошие скоры (sigmoid)
TARGET_2_SCORE_HIGH = -5.0  # плохой скор (не штрафуем)
TARGET_2_SCORE_LOW = -10.0  # хороший скор (штрафуем)
TARGET_2_SCORE_K = 0.5

# ═══════════════════════════════════════════════════════════════════════════════
# Базовая директория — папка где лежит этот скрипт
# ═══════════════════════════════════════════════════════════════════════════════

BASE_DIR = Path(__file__).parent.resolve()

CONDA_BASE = Path(subprocess.run(
    "conda info --base", shell=True, capture_output=True, text=True
).stdout.strip())

def find_dockstream():
    """Автопоиск DockStream в типичных местах"""
    candidates = [
        BASE_DIR / "DockStream",
        BASE_DIR.parent / "DockStream",
        Path.home() / "DockStream",
        Path("/mnt/tank/scratch/wolffe104/DockStream"),
    ]
    for p in candidates:
        if (p / "docker.py").exists():
            print(f"✅ DockStream найден: {p}")
            return str(p)
    raise FileNotFoundError(
        "❌ DockStream не найден! Положите его рядом с проектом или в ~/DockStream"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 1. КОНФИГУРАЦИЯ — менять только имена conda-окружений!
# ═══════════════════════════════════════════════════════════════════════════════

CONFIG = {
    "conda_reinvent": "reinvent4",
    "conda_dockstream": "DockStream",
    "work_dir": str(BASE_DIR),
    "dockstream_path": find_dockstream(),   # ← автопоиск
    "prior_file": str(Path("/mnt/tank/scratch/wolffe104") / "reinvent.prior"),
    "targets": {
        TARGET_1_NAME: str(BASE_DIR / TARGET_1_PDB),
        TARGET_2_NAME: str(BASE_DIR / TARGET_2_PDB),
    },
    "target_pdbqt": {
        TARGET_1_NAME: str(BASE_DIR / TARGET_1_PDBQT),
        TARGET_2_NAME: str(BASE_DIR / TARGET_2_PDBQT),
    },
    "target_labels": {
        TARGET_1_NAME: TARGET_1_LABEL,
        TARGET_2_NAME: TARGET_2_LABEL,
    },
    "target_run_ids": {
        TARGET_1_NAME: TARGET_1_RUN_ID,
        TARGET_2_NAME: TARGET_2_RUN_ID,
    },
    "target_boxes": {
        TARGET_1_NAME: TARGET_1_BOX,
        TARGET_2_NAME: TARGET_2_BOX,
    },
    "target_score_params": {
        TARGET_1_NAME: {
            "transform": "reverse_sigmoid",
            "high": TARGET_1_SCORE_HIGH,
            "low": TARGET_1_SCORE_LOW,
            "k": TARGET_1_SCORE_K
        },
        TARGET_2_NAME: {
            "transform": "sigmoid",
            "high": TARGET_2_SCORE_HIGH,
            "low": TARGET_2_SCORE_LOW,
            "k": TARGET_2_SCORE_K
        }
    },
    "test_mode": True,  # True = 5 шагов, False = 100
    "batch_size": 20
}


# ═══════════════════════════════════════════════════════════════════════════════

def get_conda_bin(env_name):
    """Путь к bin/ нужного conda-окружения"""
    return str(CONDA_BASE / "envs" / env_name / "bin")

def get_conda_python(env_name):
    """Путь к python нужного conda-окружения"""
    return str(CONDA_BASE / "envs" / env_name / "bin" / "python")

# ═══════════════════════════════════════════════════════════════════════════════

def setup_directories():
    work_dir = Path(CONFIG["work_dir"])
    (work_dir / "results").mkdir(parents=True, exist_ok=True)
    (work_dir / "poses").mkdir(parents=True, exist_ok=True)
    (work_dir / "targets").mkdir(parents=True, exist_ok=True)
    print(f"✅ Директории созданы: {work_dir}")
    return work_dir

# ═══════════════════════════════════════════════════════════════════════════════

def prepare_receptors():
    """Подготовка рецепторов через Open Babel (если нужно)"""
    print("🔬 Подготовка рецепторов...")
    work_dir = CONFIG["work_dir"]
    env = CONFIG["conda_dockstream"]

    # Используем имена из настроек
    for target_name in [TARGET_1_NAME, TARGET_2_NAME]:
        pdb_path = CONFIG["targets"][target_name]
        pdbqt_out = CONFIG["target_pdbqt"][target_name]

        # Проверяем, существует ли уже PDBQT (чтобы не перезаписывать Meeko-версию)
        if Path(pdbqt_out).exists():
            print(f"⏭️ {target_name}.pdbqt уже существует, пропускаем")
            continue

        cmd = (
            f"conda run -n {env} "
            f"obabel {pdb_path} -O {pdbqt_out} "
            f"-xr --partialcharge gasteiger"
        )
        subprocess.run(cmd, shell=True, check=True)
        print(f"✅ {target_name}.pdbqt создан")

# ═══════════════════════════════════════════════════════════════════════════════

def create_dockstream_config():
    """Создание dockstream_config.json"""

    # Создаем конфиги для докинга динамически
    docking_runs = []

    for target_name, run_id in CONFIG["target_run_ids"].items():
        box = CONFIG["target_boxes"][target_name]
        pdbqt_file = CONFIG["target_pdbqt"][target_name]

        docking_run = {
            "backend": "AutoDockVina",
            "run_id": run_id,
            "input_pools": ["RDkit"],
            "parameters": {
                "binary_location": get_conda_bin(CONFIG["conda_dockstream"]),
                "parallelization": {"number_cores": 4},
                "receptor_pdbqt_path": [str(Path(pdbqt_file).relative_to(Path(CONFIG["work_dir"])))],
                "number_poses": 1,
                "search_space": {
                    "--center_x": box["center_x"],
                    "--center_y": box["center_y"],
                    "--center_z": box["center_z"],
                    "--size_x": box["size_x"],
                    "--size_y": box["size_y"],
                    "--size_z": box["size_z"]
                }
            },
            "output": {
                "poses": {"poses_path": f"poses/docked_{run_id.lower()}.sdf"},
                "scores": {"scores_path": f"results/scores_{run_id.lower()}.csv", "overwrite": True}
            }
        }
        docking_runs.append(docking_run)

    config = {
        "docking": {
            "header": {"logging": {"logfile": "results/dockstream.log"}},
            "ligand_preparation": {
                "embedding_pools": [{
                    "pool_id": "RDkit",
                    "type": "RDkit",
                    "parameters": {"parallelization": {"number_cores": 4}},
                    "input": {"standardize_smiles": False, "type": "console"},
                    "output": {"conformer_path": "poses/conformers.sdf", "format": "sdf"}
                }]
            },
            "docking_runs": docking_runs
        }
    }

    out = Path(CONFIG["work_dir"]) / "dockstream_config.json"
    with open(out, "w") as f:
        json.dump(config, f, indent=2)
    print(f"✅ dockstream_config.json создан с {len(docking_runs)} docking runs")

# ═══════════════════════════════════════════════════════════════════════════════

def create_reinvent_config():
    """Создание rl_config.toml"""
    max_steps = 5 if CONFIG["test_mode"] else 100
    ds_python = get_conda_python(CONFIG["conda_dockstream"])
    ds_script = str(Path(CONFIG["dockstream_path"]) / "docker.py")
    prior = CONFIG["prior_file"]

    # Создаем компоненты скоров динамически
    scoring_components = []

    # Компонент для основной мишени
    target1_params = CONFIG["target_score_params"][TARGET_1_NAME]
    scoring_components.append(f"""
[[stage.scoring.component]]
[stage.scoring.component.DockStream]
name = "{TARGET_1_NAME}_affinity"
weight = 1.0
[[stage.scoring.component.DockStream.endpoint]]
name = "{TARGET_1_LABEL} Vina"
weight = 1.0
params.configuration_path = "dockstream_config.json"
params.docker_script_path = "{ds_script}"
params.docker_python_path = "{ds_python}"
params.docking_run_name = "{CONFIG['target_run_ids'][TARGET_1_NAME]}"
transform.type = "{target1_params['transform']}"
transform.high = {target1_params['high']}
transform.low = {target1_params['low']}
transform.k = {target1_params['k']}
""")

    # Компонент для анти-целевой мишени
    target2_params = CONFIG["target_score_params"][TARGET_2_NAME]
    scoring_components.append(f"""
[[stage.scoring.component]]
[stage.scoring.component.DockStream]
name = "{TARGET_2_NAME}_penalty"
weight = 1.0
[[stage.scoring.component.DockStream.endpoint]]
name = "{TARGET_2_LABEL} Vina"
weight = 1.0
params.configuration_path = "dockstream_config.json"
params.docker_script_path = "{ds_script}"
params.docker_python_path = "{ds_python}"
params.docking_run_name = "{CONFIG['target_run_ids'][TARGET_2_NAME]}"
transform.type = "{target2_params['transform']}"
transform.high = {target2_params['high']}
transform.low = {target2_params['low']}
transform.k = {target2_params['k']}
""")

    # Добавляем стандартные компоненты
    scoring_components.append("""
[[stage.scoring.component]]
[stage.scoring.component.QED]
[[stage.scoring.component.QED.endpoint]]
name = "QED"
weight = 0.5

[[stage.scoring.component]]
[stage.scoring.component.MolecularWeight]
[[stage.scoring.component.MolecularWeight.endpoint]]
name = "MolecularWeight"
weight = 0.5
[stage.scoring.component.MolecularWeight.endpoint.transform]
type     = "double_sigmoid"
high     = 500.0
low      = 200.0
coef_div = 500.0
coef_si  = 20.0
coef_se  = 20.0

[[stage.scoring.component]]
[stage.scoring.component.custom_alerts]
[[stage.scoring.component.custom_alerts.endpoint]]
name = "custom_alerts"
weight = 1.0
params.smarts = [
  "[*;r8]", "[*;r9]", "[*;r10]",
  "[CH2;X4][N;X3][CH2;X4]",
  "c1ccc2c(c1)ccc(=O)o2"
]
""")

    config = f"""run_type = "staged_learning"

[parameters]
batch_size = {CONFIG['batch_size']}
prior_file = "{prior}"
agent_file = "{prior}"
use_checkpoint = false

[learning_strategy]
type = "dap"
sigma = 128
rate = 0.0001

[diversity_filter]
type = "IdenticalMurckoScaffold"
minscore = 0.4
bucket_size = 25

[[stage]]
max_score = 1.0
max_steps = {max_steps}
chkpt_file = "results/stage1.chkpt"
termination = "simple"

[stage.scoring]
type = "geometric_mean"
{"".join(scoring_components)}
"""

    out = Path(CONFIG["work_dir"]) / "rl_config.toml"
    with open(out, "w") as f:
        f.write(config.strip())
    print(f"✅ rl_config.toml создан ({max_steps} шагов × {CONFIG['batch_size']} молекул)")
    print(f"   Мишени: {TARGET_1_LABEL} (целевая) vs {TARGET_2_LABEL} (селективность)")

# ═══════════════════════════════════════════════════════════════════════════════

def test_dockstream():
    """Тестирование DockStream с одной молекулой"""
    print("🧪 Тестирование DockStream...")
    env = CONFIG["conda_dockstream"]
    work_dir = CONFIG["work_dir"]
    ds_path = CONFIG["dockstream_path"]
    cmd = (
        f"conda run -n {env} python {ds_path}/docker.py "
        f"-conf {work_dir}/dockstream_config.json "
        f"-output_prefix test "
        f"-smiles 'CC(=O)Oc1ccccc1C(=O)O' "
        f"-print_scores"
    )
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=work_dir)
    print("Score:", result.stdout.strip())
    try:
        float(result.stdout.strip().split("\n")[-1])
        print("✅ DockStream работает!")
        return True
    except ValueError:
        print("❌ Ошибка:", result.stderr[-300:])
        return False

# ═══════════════════════════════════════════════════════════════════════════════

def analyze_results():
    """Анализ результатов с динамическими именами колонок"""
    results_file = Path(CONFIG["work_dir"]) / "results" / "rl_1.csv"

    if not results_file.exists():
        print(f"❌ Файл результатов не найден: {results_file}")
        return

    df = pd.read_csv(results_file)

    # Используем правильные имена колонок из конфига
    col_target1 = f"{TARGET_1_NAME}_affinity"
    col_target2 = f"{TARGET_2_NAME}_penalty"

    top = df.nlargest(10, "total_score")[["smiles", "total_score", col_target1, col_target2]]

    print(f"\n📊 РЕЗУЛЬТАТЫ ({len(df)} молекул):")
    print(f"   Целевая мишень: {TARGET_1_LABEL}")
    print(f"   Селективность vs: {TARGET_2_LABEL}")
    print("-" * 80)
    print(top.to_string(index=False))

    output_file = Path(CONFIG["work_dir"]) / "results" / "top10_selective.csv"
    top.to_csv(output_file, index=False)
    print(f"💾 Топ-10 сохранены в {output_file}")

# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(f"🔬 REINVENT4 {TARGET_1_LABEL} селективный пайплайн")
    print("=" * 60)
    print(f"📁 Рабочая директория: {BASE_DIR}")
    print(f"🐍 Conda base: {CONDA_BASE}")
    print(f"🎯 Целевая мишень: {TARGET_1_LABEL}")
    print(f"⚖️ Селективность vs: {TARGET_2_LABEL}")

    work_dir = setup_directories()
    os.chdir(work_dir)

    prepare_receptors()
    create_dockstream_config()
    create_reinvent_config()

    if test_dockstream():
        print(f"\n✅ Всё готово! Запустите REINVENT вручную:")
        print(f"   cd {BASE_DIR}")
        print(f"   reinvent -l results/rl_run.log rl_config.toml")
    else:
        print("❌ Ошибка DockStream — проверьте конфиг")
