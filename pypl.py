#!/usr/bin/env python3
"""
REINVENT4 + DockStream + AutoDock Vina — полный пайплайн
Цель: PPARα (PDB 7E5G) | staged_learning | CPU
Запуск: conda run -n reinvent4 python pipeline.py
"""

import os, json, subprocess, sys
from pathlib import Path

# ═══════════════════ ПУТИ ═══════════════════════════════════
HOME     = Path.home()
WORK     = HOME / "reinvent_docking"
DS_DIR   = HOME / "DockStream"
DS_ENV   = "DockStream"
R4_ENV   = "reinvent4"

TARGETS  = WORK / "targets"
RESULTS  = WORK / "results"
POSES    = WORK / "poses"

REC_RAW  = TARGETS / "ppar_alpha.pdb"
REC_PDB  = TARGETS / "ppar_receptor.pdb"
REC_PDBQT= TARGETS / "ppar_receptor.pdbqt"
DS_CFG   = WORK / "dockstream_config.json"
RL_TOML  = WORK / "rl_ppar_docking.toml"

# Координаты бокса — рассчитаны из лиганда HVX в 7E5G (цепь A)
# X: 8-16 → center 12 | Y: -1 to 12 → center 5.5 | Z: -11 to -1 → center -6
BOX = {"--center_x": 12.0, "--center_y": 5.5, "--center_z": -6.0,
       "--size_x":   25.0, "--size_y":  25.0, "--size_z":   25.0}

# ═══════════════════ УТИЛИТЫ ════════════════════════════════
def run(cmd, env=None, cwd=None, check=True):
    prefix = f"conda run -n {env} " if env else ""
    full = prefix + cmd
    print(f"  $ {full}")
    return subprocess.run(full, shell=True, check=check,
                          cwd=str(cwd or WORK))

def step(n, title):
    print(f"\n{'='*60}\n>>> [{n}/7] {title}\n{'='*60}")

# ═══════════════════ ШАГ 1: Директории ══════════════════════
step(1, "Создание директорий")
for d in [TARGETS, RESULTS, POSES]:
    d.mkdir(parents=True, exist_ok=True)
    print(f"  ✓ {d}")

# ═══════════════════ ШАГ 2: DockStream ══════════════════════
step(2, "Проверка / установка DockStream")

if not DS_DIR.exists():
    run(f"git clone https://github.com/MolecularAI/DockStream {DS_DIR}",
        cwd=HOME)

envs = subprocess.check_output("conda env list", shell=True).decode()
if "DockStream" not in envs:
    print("  Создание окружения из environment.yml ...")
    run(f"conda env create -f {DS_DIR}/environment.yml", cwd=DS_DIR)
    run("conda install -c conda-forge autodock-vina meeko -y", env=DS_ENV)
    run("pip install pdb-tools", env=DS_ENV)
else:
    print("  ✓ Окружение DockStream уже существует")

# ═══════════════════ ШАГ 3: Рецептор ════════════════════════
step(3, "Подготовка рецептора PPARα (7E5G)")

if not REC_RAW.exists():
    run(f"wget -q https://files.rcsb.org/download/7E5G.pdb -O {REC_RAW}")

if not REC_PDB.exists():
    # Выбрать цепь A, удалить гетероатомы, форматировать
    run(f"bash -c \"pdb_selchain -A {REC_RAW} | pdb_delhetatm | pdb_tidy > {REC_PDB}\"",
        env=DS_ENV)

if not REC_PDBQT.exists():
    # ВАЖНО: предупреждения Open Babel о kekule — нормальны, игнорируем
    run(f"obabel {REC_PDB} -O {REC_PDBQT} -xr --partialcharge gasteiger",
        env=DS_ENV)
    print(f"  ✓ PDBQT создан: {REC_PDBQT.name}")

# ═══════════════════ ШАГ 4: dockstream_config.json ══════════
step(4, "Генерация dockstream_config.json")

ds_config = {
  "docking": {
    "header": {
      "logging": {"logfile": str(RESULTS / "dockstream.log")}
    },
    "ligand_preparation": {
      "embedding_pools": [{
        "pool_id": "RDkit",
        "type":    "RDkit",                   # НЕ Corina — не установлен
        "parameters": {
          "prefix_execution": "",
          "parallelization": {"number_cores": 4}
        },
        "input":  {"standardize_smiles": False, "type": "console"},
        "output": {
          # ВАЖНО: указывать ФАЙЛ, а не папку
          "conformer_path": str(POSES / "conformers.sdf"),
          "format": "sdf"
        }
      }]
    },
    "docking_runs": [{
      "backend":     "AutoDockVina",
      "run_id":      "AutoDockVina",
      "input_pools": ["RDkit"],
      "parameters": {
        "binary_location": str(HOME / "anaconda3/envs/DockStream/bin"),
        "parallelization": {"number_cores": 4},
        # ВАЖНО: receptor_pdbqt_path — список, не строка!
        "receptor_pdbqt_path": [str(REC_PDBQT)],
        "number_poses": 3,
        "search_space": BOX
      },
      "output": {
        "poses":  {"poses_path":  str(POSES   / "docked.sdf")},
        "scores": {"scores_path": str(RESULTS / "scores.csv"),
                   "overwrite": True}
      }
    }]
  }
}

DS_CFG.write_text(json.dumps(ds_config, indent=2))
print(f"  ✓ {DS_CFG}")

# ═══════════════════ ШАГ 5: rl_ppar_docking.toml ════════════
step(5, "Генерация rl_ppar_docking.toml")

DS_PY     = HOME / f"anaconda3/envs/{DS_ENV}/bin/python"
DOCKER_PY = DS_DIR / "docker.py"

toml = f"""\
# REINVENT4 Staged Learning + DockStream + AutoDock Vina | PPARα | CPU
run_type = "staged_learning"          # НЕ reinforcement_learning!
device   = "cpu"                      # НЕ use_cuda = false
tb_logdir        = "tb_logs"
json_out_config  = "run_config.json"

[parameters]
prior_file         = "reinvent.prior"
agent_file         = "reinvent.prior"
summary_csv_prefix = "results/ppar_rl"
batch_size         = 32
use_checkpoint     = false
purge_memories     = false

[learning_strategy]
type  = "dap"
sigma = 128
rate  = 0.0001

[diversity_filter]
type               = "IdenticalMurckoScaffold"
bucket_size        = 25
minscore           = 0.4
minsimilarity      = 0.4
penalty_multiplier = 0.5

[[stage]]
max_score  = 1.0
max_steps  = 200
chkpt_file = "results/stage1.chkpt"

[stage.scoring]
type = "geometric_mean"

# ── Компонент 1: DockStream score (вес 0.8) ─────────────────
[[stage.scoring.component]]
[[stage.scoring.component.DockStream.endpoint]]
name   = "PPARa Vina Score"
weight = 0.8
params.configuration_path = "{DS_CFG}"
params.docker_script_path  = "{DOCKER_PY}"
params.docker_python_path  = "{DS_PY}"

[stage.scoring.component.DockStream.endpoint.transform]
type = "reverse_sigmoid"   # Vina: отрицательные значения → лучше
high = 0.0
low  = -12.0
k    = 0.5

# ── Компонент 2: Молекулярная масса (вес 0.2) ────────────────
[[stage.scoring.component]]
[[stage.scoring.component.MolecularWeight.endpoint]]
name   = "MW 300-600"
weight = 0.2

[stage.scoring.component.MolecularWeight.endpoint.transform]
type     = "double_sigmoid"
high     = 600.0
low      = 300.0
coef_div = 500.0
coef_si  = 20.0
coef_se  = 20.0
"""

RL_TOML.write_text(toml)
print(f"  ✓ {RL_TOML}")

# ═══════════════════ ШАГ 6: Тест DockStream ═════════════════
step(6, "Тест DockStream standalone (аспирин → ожидается ≈ -6.3)")

test_cmd = (
    f"python {DOCKER_PY} "
    f"-conf {DS_CFG} "
    f"-output_prefix test "
    f"-smiles 'CC(=O)Oc1ccccc1C(=O)O' "
    f"-print_scores"
)
res = subprocess.run(f"conda run -n {DS_ENV} {test_cmd}",
                     shell=True, capture_output=True, text=True, cwd=str(WORK))

scores = [l.strip() for l in res.stdout.splitlines()
          if l.strip().lstrip('-').replace('.','').isdigit()]
if scores:
    print(f"  ✅ DockStream OK! Vina score = {scores[-1]}")
else:
    print(f"  ❌ Ошибка DockStream:\n{res.stderr[-800:]}")
    sys.exit(1)

# ═══════════════════ ШАГ 7: REINVENT4 ═══════════════════════
step(7, "Запуск REINVENT4 staged_learning")

prior = WORK / "reinvent.prior"
if not prior.exists():
    print("  ❌ Файл reinvent.prior не найден!")
    print("  Скачайте prior-модель вручную:")
    print("  wget https://zenodo.org/records/10930189/files/reinvent.prior \\")
    print(f"    -O {prior}")
    print()
    print("  Или из репозитория REINVENT4 на GitHub (Releases).")
    sys.exit(1)

run(f"reinvent -l results/rl_run.log {RL_TOML}", env=R4_ENV)
print("\n  ✅ Пайплайн завершён!")
print(f"  📊 Результаты: {RESULTS}/")
print(f"  📈 TensorBoard: tensorboard --logdir {WORK}/tb_logs")
