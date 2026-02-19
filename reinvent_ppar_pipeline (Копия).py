#!/usr/bin/env python3
"""
REINVENT4 PPARα RL пайплайн с селективностью vs PPARγ
Автоматическая настройка DockStream + REINVENT4
"""

import os
import subprocess
import json
import pandas as pd
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════════
# 1. КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════════════════════════════════════════

CONFIG = {
    "conda_reinvent":  "reinvent4",
    "conda_dockstream": "DockStream",
    "work_dir":        "/home/michael-kaiser/reinvent_docking",
    "dockstream_path": "/home/michael-kaiser/DockStream",
    "prior_file":      "/home/michael-kaiser/REINVENT4/priors/reinvent.prior",
    "targets": {
        "ppar_alpha": "/home/michael-kaiser/reinvent_docking/targets/ppar_alpha.pdb",
        "ppar_gamma": "/home/michael-kaiser/reinvent_docking/targets/ppar_gamma.pdb"
    },
    "test_mode":  True,
    "batch_size": 20
}

# ═══════════════════════════════════════════════════════════════════════════════

def setup_directories():
    work_dir = Path(CONFIG["work_dir"]).expanduser()
    (work_dir / "results").mkdir(parents=True, exist_ok=True)
    (work_dir / "poses").mkdir(parents=True, exist_ok=True)
    (work_dir / "targets").mkdir(parents=True, exist_ok=True)
    print(f"✅ Директории созданы: {work_dir}")
    return work_dir

# ═══════════════════════════════════════════════════════════════════════════════

def prepare_receptors():
    print("🔬 Подготовка рецепторов...")
    work_dir = CONFIG["work_dir"]
    env = CONFIG["conda_dockstream"]
    for target_key, pdbqt_name in [("ppar_alpha", "ppar_alpha.pdbqt"),
                                    ("ppar_gamma", "ppar_gamma.pdbqt")]:
        pdb_path  = CONFIG["targets"][target_key]
        pdbqt_out = f"{work_dir}/targets/{pdbqt_name}"
        cmd = (
            f"conda run -n {env} "
            f"obabel {pdb_path} -O {pdbqt_out} "
            f"-xr --partialcharge gasteiger"
        )
        subprocess.run(cmd, shell=True, check=True)
        print(f"✅ {pdbqt_name} готов")

# ═══════════════════════════════════════════════════════════════════════════════

def create_dockstream_config():
    """Создание dockstream_config.json"""
    user = os.getenv("USER")
    config = {
        "docking": {
            "header": {"logging": {"logfile": "results/dockstream.log"}},
            "ligand_preparation": {
                "embedding_pools": [{
                    "pool_id": "RDkit",
                    "type": "RDkit",
                    "parameters": {"parallelization": {"number_cores": 4}},
                    "input":  {"standardize_smiles": False, "type": "console"},
                    "output": {"conformer_path": "poses/conformers.sdf", "format": "sdf"}
                }]
            },
            "docking_runs": [
                {
                    "backend":     "AutoDockVina",
                    "run_id":      "PPARa",
                    "input_pools": ["RDkit"],
                    "parameters": {
                        "binary_location": f"/home/{user}/anaconda3/envs/{CONFIG['conda_dockstream']}/bin",
                        "parallelization": {"number_cores": 4},
                        "receptor_pdbqt_path": ["targets/ppar_alpha.pdbqt"],
                        "number_poses": 1,
                        "search_space": {
                            "--center_x": 13.861, "--center_y": -12.946, "--center_z": -31.915,
                            "--size_x":   16.842, "--size_y":    9.62,   "--size_z":   22.206
                        }
                    },
                    "output": {
                        "poses":  {"poses_path":  "poses/docked_ppara.sdf"},
                        "scores": {"scores_path": "results/scores_ppara.csv", "overwrite": True}
                    }
                },
                {
                    "backend":     "AutoDockVina",
                    "run_id":      "PPARg",
                    "input_pools": ["RDkit"],
                    "parameters": {
                        "binary_location": f"/home/{user}/anaconda3/envs/{CONFIG['conda_dockstream']}/bin",
                        "parallelization": {"number_cores": 4},
                        "receptor_pdbqt_path": ["targets/ppar_gamma.pdbqt"],
                        "number_poses": 1,
                        "search_space": {
                            "--center_x": 22.553, "--center_y": -7.676,  "--center_z": 26.095,
                            "--size_x":   64.72,  "--size_y":   77.892,  "--size_z":   75.448
                        }
                    },
                    "output": {
                        "poses":  {"poses_path":  "poses/docked_pparg.sdf"},
                        "scores": {"scores_path": "results/scores_pparg.csv", "overwrite": True}
                    }
                }
            ]
        }
    }
    with open(f"{CONFIG['work_dir']}/dockstream_config.json", "w") as f:
        json.dump(config, f, indent=2)
    print("✅ dockstream_config.json создан")

# ═══════════════════════════════════════════════════════════════════════════════

def create_reinvent_config():
    """Создание rl_ppar_docking.toml"""
    max_steps  = 5 if CONFIG["test_mode"] else 100
    user       = os.getenv("USER")
    ds_python  = f"/home/{user}/anaconda3/envs/{CONFIG['conda_dockstream']}/bin/python"
    ds_script  = f"{CONFIG['dockstream_path']}/docker.py"
    prior      = CONFIG["prior_file"]

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

[[stage.scoring.component]]
[stage.scoring.component.DockStream]
name = "PPARa_affinity"
weight = 1.0
[[stage.scoring.component.DockStream.endpoint]]
name = "PPARa Vina"
weight = 1.0
params.configuration_path = "dockstream_config.json"
params.docker_script_path = "{ds_script}"
params.docker_python_path = "{ds_python}"
params.docking_run_name = "PPARa"
transform.type = "reverse_sigmoid"
transform.high = -10.0
transform.low  = -5.0
transform.k    = 0.5

[[stage.scoring.component]]
[stage.scoring.component.DockStream]
name = "PPARg_penalty"
weight = 1.0
[[stage.scoring.component.DockStream.endpoint]]
name = "PPARg Vina"
weight = 1.0
params.configuration_path = "dockstream_config.json"
params.docker_script_path = "{ds_script}"
params.docker_python_path = "{ds_python}"
params.docking_run_name = "PPARg"
transform.type = "sigmoid"
transform.high = -5.0
transform.low  = -10.0
transform.k    = 0.5

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
"""

    out = f"{CONFIG['work_dir']}/rl_ppar_docking.toml"
    with open(out, "w") as f:
        f.write(config.strip())
    print(f"✅ rl_ppar_docking.toml создан ({max_steps} шагов × {CONFIG['batch_size']} молекул)")

# ═══════════════════════════════════════════════════════════════════════════════

def test_dockstream():
    print("🧪 Тестирование DockStream...")
    env      = CONFIG["conda_dockstream"]
    work_dir = CONFIG["work_dir"]
    ds_path  = CONFIG["dockstream_path"]
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
    df  = pd.read_csv(f"{CONFIG['work_dir']}/results/ppar_rl_1.csv")
    top = df.nlargest(10, "total_score")[["smiles", "total_score", "PPARa_affinity", "PPARg_penalty"]]
    print(f"\n📊 РЕЗУЛЬТАТЫ ({len(df)} молекул):")
    print(top.to_string(index=False))
    top.to_csv(f"{CONFIG['work_dir']}/results/top10_selective.csv", index=False)
    print("💾 Топ-10 сохранены в top10_selective.csv")

# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("🔬 REINVENT4 PPARα селективный пайплайн")
    print("=" * 60)

    work_dir = setup_directories()
    os.chdir(work_dir)

    print("⚠️  ПРОВЕРЬТЕ пути в CONFIG!")
    input("Нажмите Enter после проверки...")

    prepare_receptors()
    create_dockstream_config()
    create_reinvent_config()

    if test_dockstream():
        print("\n✅ Всё готово! Запустите REINVENT вручную:")
        print(f"   cd {CONFIG['work_dir']}")
        print(f"   reinvent -l results/rl_run.log rl_ppar_docking.toml")
    else:
        print("❌ Ошибка DockStream — проверьте конфиг")

