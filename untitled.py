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
# 1. КОНФИГУРАЦИЯ (измените пути!)
# ═══════════════════════════════════════════════════════════════════════════════
CONFIG = {
    "conda_reinvent": "reinvent4",      # conda env с REINVENT4
    "conda_dockstream": "DockStream",   # conda env с DockStream
    "work_dir": "~/reinvent_docking",   # рабочая директория
    "dockstream_path": "~/DockStream",  # путь к DockStream
    "targets": {
        "ppar_alpha": "~/reinvent_docking/targets/ppar_alpha.pdb",
        "ppar_gamma": "~/reinvent_docking/targets/ppar_gamma.pdb"
    },
    "test_mode": True,                  # True = 100 молекул, False = полный запуск
    "batch_size": 20
}

# ═══════════════════════════════════════════════════════════════════════════════
def setup_directories():
    """Создание директорий"""
    work_dir = Path(CONFIG["work_dir"]).expanduser()
    (work_dir / "results").mkdir(parents=True, exist_ok=True)
    (work_dir / "poses").mkdir(parents=True, exist_ok=True)
    (work_dir / "targets").mkdir(parents=True, exist_ok=True)
    print(f"✅ Директории созданы: {work_dir}")
    return work_dir

# ═══════════════════════════════════════════════════════════════════════════════
def prepare_receptors():
    """Конвертация PDB → PDBQT"""
    print("🔬 Подготовка рецепторов...")
    
    cmd = f"""
    conda activate {CONFIG['conda_dockstream']}
    obabel {CONFIG['targets']['ppar_alpha']} -O targets/ppar_alpha.pdbqt -xr --partialcharge gasteiger
    obabel {CONFIG['targets']['ppar_gamma']} -O targets/ppar_gamma.pdbqt -xr --partialcharge gasteiger
    """
    
    subprocess.run(cmd, shell=True, cwd=CONFIG["work_dir"], check=True)
    print("✅ Рецепторы подготовлены")

# ═══════════════════════════════════════════════════════════════════════════════
def create_dockstream_config():
    """Создание dockstream_config.json"""
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
            "docking_runs": [
                {
                    "backend": "AutoDockVina",
                    "run_id": "PPARa",
                    "input_pools": ["RDkit"],
                    "parameters": {
                        "binary_location": f"/home/{os.getenv('USER')}/anaconda3/envs/{CONFIG['conda_dockstream']}/bin",
                        "parallelization": {"number_cores": 4},
                        "receptor_pdbqt_path": ["targets/ppar_alpha.pdbqt"],
                        "number_poses": 1,
                        "search_space": {
                            "--center_x": 10.94, "--center_y": 5.43, "--center_z": -7.50,
                            "--size_x": 18.0, "--size_y": 24.0, "--size_z": 23.0
                        }
                    },
                    "output": {
                        "poses": {"poses_path": "poses/docked_ppara.sdf"},
                        "scores": {"scores_path": "results/scores_ppara.csv", "overwrite": True}
                    }
                },
                {
                    "backend": "AutoDockVina",
                    "run_id": "PPARg",
                    "input_pools": ["RDkit"],
                    "parameters": {
                        "binary_location": f"/home/{os.getenv('USER')}/anaconda3/envs/{CONFIG['conda_dockstream']}/bin",
                        "parallelization": {"number_cores": 4},
                        "receptor_pdbqt_path": ["targets/ppar_gamma.pdbqt"],
                        "number_poses": 1,
                        "search_space": {
                            "--center_x": 0.0, "--center_y": 0.0, "--center_z": 0.0,  # ← НАСТРОЙТЕ!
                            "--size_x": 20.0, "--size_y": 20.0, "--size_z": 20.0
                        }
                    },
                    "output": {
                        "poses": {"poses_path": "poses/docked_pparg.sdf"},
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
    max_steps = 5 if CONFIG["test_mode"] else 100
    
    config = f"""
[parameters]
batch_size = {CONFIG['batch_size']}
sigma = 30.0

[[stage]]
max_score = 1.0
max_steps = {max_steps}
chkpt_file = "results/stage1.chkpt"

[stage.scoring]
type = "geometric_mean"

# PPARα: максимизировать сродство
[[stage.scoring.component]]
[stage.scoring.component.DockStream]
name = "PPARa_affinity"
weight = 1.0

[[stage.scoring.component.DockStream.endpoint]]
name = "PPARa Vina"
weight = 1.0
params.configuration_path = "dockstream_config.json"
params.docker_script_path = "{CONFIG['dockstream_path']}/docker.py"
params.docker_python_path = "/home/{os.getenv('USER')}/anaconda3/envs/{CONFIG['conda_dockstream']}/bin/python"
params.docking_run_name = "PPARa"
transform.type = "reverse_sigmoid"
transform.high = -10.0
transform.low = -5.0
transform.k = 0.5

# PPARγ: минимизировать сродство
[[stage.scoring.component]]
[stage.scoring.component.DockStream]
name = "PPARg_penalty"
weight = 1.0

[[stage.scoring.component.DockStream.endpoint]]
name = "PPARg Vina"
weight = 1.0
params.configuration_path = "dockstream_config.json"
params.docker_script_path = "{CONFIG['dockstream_path']}/docker.py"
params.docker_python_path = "/home/{os.getenv('USER')}/anaconda3/envs/{CONFIG['conda_dockstream']}/bin/python"
params.docking_run_name = "PPARg"
transform.type = "sigmoid"
transform.high = -5.0
transform.low = -10.0
transform.k = 0.5

# Дополнительные фильтры
[[stage.scoring.component]]
[stage.scoring.component.QED]
name = "QED"
weight = 0.5

[[stage.scoring.component]]
[stage.scoring.component.MolecularWeight]
name = "MW"
weight = 0.3
[[stage.scoring.component.MolecularWeight.endpoint]]
transform.type = "double_sigmoid"
transform.high = 500.0
transform.low = 200.0
transform.coef_div = 500.0
transform.coef_si = 20.0
transform.coef_se = 20.0
"""
    
    with open(f"{CONFIG['work_dir']}/rl_ppar_docking.toml", "w") as f:
        f.write(config.strip())
    print("✅ rl_ppar_docking.toml создан")

# ═══════════════════════════════════════════════════════════════════════════════
def test_dockstream():
    """Тестовый запуск DockStream"""
    print("🧪 Тестирование DockStream...")
    
    cmd = f"""
    conda activate {CONFIG['conda_dockstream']}
    cd {CONFIG['work_dir']}
    python {CONFIG['dockstream_path']}/docker.py \\
      -conf dockstream_config.json \\
      -output_prefix test \\
      -smiles "CC(=O)Oc1ccccc1C(=O)O" \\
      -print_scores
    """
    
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print("DockStream test:", result.stdout)
    if result.returncode == 0:
        print("✅ DockStream работает!")
    else:
        print("❌ Ошибка DockStream:", result.stderr)
        return False
    return True

# ═══════════════════════════════════════════════════════════════════════════════
def launch_reinvent():
    """Запуск REINVENT4"""
    print("🚀 Запуск REINVENT4...")
    
    cmd = f"""
    conda activate {CONFIG['conda_reinvent']}
    cd {CONFIG['work_dir']}
    nohup reinvent -l results/rl_run.log rl_ppar_docking.toml > results/reinvent.out 2>&1 &
    echo $! > results/reinvent.pid
    """
    
    subprocess.run(cmd, shell=True, check=True)
    print("✅ REINVENT4 запущен в фоне!")
    print("📊 Мониторинг:")
    print("   tail -f results/rl_run.log")
    print("   tmux attach -t reinvent")

# ═══════════════════════════════════════════════════════════════════════════════
def analyze_results():
    """Анализ результатов"""
    df = pd.read_csv(f"{CONFIG['work_dir']}/results/ppar_rl_1.csv")
    print(f"\n📊 РЕЗУЛЬТАТЫ ({len(df)} молекул):")
    
    top = df.nlargest(10, "total_score")[["smiles", "total_score", "PPARa_affinity", "PPARg_penalty"]]
    print(top.to_string(index=False))
    
    top.to_csv(f"{CONFIG['work_dir']}/results/top10_selective.csv", index=False)
    print("💾 Топ-10 сохранены в top10_selective.csv")

# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("🔬 REINVENT4 PPARα селективный пайплайн")
    print("=" * 60)
    
    work_dir = setup_directories()
    os.chdir(work_dir)
    
    # Измените пути в CONFIG!
    print("⚠️  ПРОВЕРЬТЕ пути в CONFIG!")
    input("Нажмите Enter после проверки...")
    
    prepare_receptors()
    create_dockstream_config()
    create_reinvent_config()
    
    if test_dockstream():
        launch_reinvent()
        print("\n🎉 Пайплайн запущен! Мониторьте:")
        print("   tail -f results/rl_run.log")
        print("   tmux new -s reinvent && tmux attach -t reinvent")
    else:
        print("❌ Ошибка настройки")
