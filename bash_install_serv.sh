#!/bin/bash
#SBATCH -p aichem
#SBATCH --cpus-per-task=16
#SBATCH --time=48:00:00
#SBATCH --grep=gpu:1
#SBATCH -p aihub

set -e  # остановка при ошибке

# Цвета
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

# Устанавливаем путь установки
export INSTALL_DIR="/mnt/tank/scratch/wolffe104"
cd $INSTALL_DIR

echo -e "${BLUE}📁 Установка в: $INSTALL_DIR${NC}"

# 1. ПАПКИ
echo -e "\n${BLUE}📁 Создание папок...${NC}"
mkdir -p targets results poses priors
echo "   ✅ папки готовы"

# 2. ПРОВЕРКА МОДУЛЕЙ (на серверах часто используется module load вместо conda)
echo -e "\n${BLUE}🔍 Проверка conda...${NC}"
if ! command -v conda &> /dev/null; then
    echo -e "${RED}❌ Conda не найдена. Проверьте module load conda${NC}"
    echo "   Попробуйте: module load conda && source /usr/local/conda/etc/profile.d/conda.sh"
    exit 1
fi
CONDA_BASE=$(conda info --base)
echo "   ✅ Conda: $CONDA_BASE"

# 3. УДАЛЕНИЕ СТАРЫХ ОКРУЖЕНИЙ
echo -e "\n${BLUE}🧹 Очистка...${NC}"
for env in reinvent4 DockStream; do
    if conda env list | grep -q $env; then
        echo "   Удаление $env..."
        conda remove -n $env --all -y
    fi
done

# 4. СОЗДАНИЕ НОВЫХ ОКРУЖЕНИЙ
echo -e "\n${BLUE}🏗️ Создание окружений...${NC}"
conda create -n reinvent4 python=3.10 -y
conda create -n DockStream python=3.10 -y
echo "   ✅ окружения созданы"

# 5. УСТАНОВКА ИНСТРУМЕНТОВ ДОКИНГА
echo -e "\n${BLUE}🔬 Установка openbabel, vina, meeko...${NC}"
source $CONDA_BASE/etc/profile.d/conda.sh
conda activate DockStream

# Добавляем conda-forge и устанавливаем
conda config --env --add channels conda-forge
conda config --env --set channel_priority strict
conda install -y openbabel vina meeko rdkit numpy pandas
pip install prody gemmi

echo "   Проверка:"
which obabel || echo -e "${RED}   ❌ obabel не найден${NC}"
which vina || echo -e "${RED}   ❌ vina не найден${NC}"
conda deactivate

# 6. УСТАНОВКА REINVENT4
echo -e "\n${BLUE}🎯 Установка REINVENT4...${NC}"
conda activate reinvent4

if [ ! -d "$INSTALL_DIR/REINVENT4" ]; then
    echo "   Клонирование репозитория..."
    git clone --depth 1 https://github.com/MolecularAI/REINVENT4.git
    cd REINVENT4
else
    cd REINVENT4
    git pull
fi

# На сервере обычно CPU (если нет GPU, можно оставить cpu)
echo "   Установка зависимостей..."
python install.py cpu

# Если на сервере есть NVIDIA GPU, можно использовать:
# python install.py cu121  # для CUDA 12.1
# python install.py cu126  # для CUDA 12.6

pip install --no-deps .
cd $INSTALL_DIR

echo "   Проверка: $(which reinvent || echo 'не найден')"
conda deactivate

# 7. УСТАНОВКА DOCKSTREAM
echo -e "\n${BLUE}🐳 Установка DockStream...${NC}"
if [ ! -d "$INSTALL_DIR/DockStream" ]; then
    git clone https://github.com/MolecularAI/DockStream.git
    conda activate DockStream
    pip install -r DockStream/requirements.txt
    conda deactivate
    echo "   ✅ DockStream установлен"
else
    echo "   ⏭️ DockStream уже есть"
fi

# 8. ЗАГРУЗКА PRIOR ФАЙЛА
echo -e "\n${BLUE}📥 Загрузка prior-модели...${NC}"
cd $INSTALL_DIR
conda activate reinvent4

if [ ! -f "priors/reinvent.prior" ] && [ ! -f "reinvent.prior" ]; then
    echo "   Скачивание с Zenodo..."
    
    # Проверяем наличие wget, если нет - используем curl
    if command -v wget &> /dev/null; then
        wget -q --show-progress https://zenodo.org/api/records/15641297/files-archive -O priors.zip
    elif command -v curl &> /dev/null; then
        curl -L https://zenodo.org/api/records/15641297/files-archive -o priors.zip
    else
        echo -e "${RED}❌ Нет wget или curl${NC}"
        exit 1
    fi
    
    if [ -f "priors.zip" ] && [ -s "priors.zip" ]; then
        # Проверяем наличие unzip
        if command -v unzip &> /dev/null; then
            unzip -o priors.zip -d priors/
            rm priors.zip
        else
            echo -e "${RED}❌ Нет unzip${NC}"
            exit 1
        fi
        
        if [ -f "priors/reinvent.prior" ]; then
            ln -sf priors/reinvent.prior reinvent.prior
            echo "   ✅ Prior загружен (размер: $(du -h priors/reinvent.prior | cut -f1))"
        else
            echo -e "${RED}   ❌ Ошибка: prior не найден в архиве${NC}"
            ls -la priors/
        fi
    else
        echo -e "${RED}   ❌ Ошибка скачивания${NC}"
    fi
else
    echo "   ✅ Prior уже есть"
fi
conda deactivate

# 9. ФИНАЛЬНАЯ ПРОВЕРКА
echo -e "\n${BLUE}✅ Проверка установки...${NC}"

# reinvent
conda activate reinvent4 2>/dev/null || true
if command -v reinvent &> /dev/null; then
    echo "   ✅ reinvent: $(which reinvent)"
else
    echo -e "${RED}   ❌ reinvent не найден${NC}"
fi
conda deactivate 2>/dev/null || true

# dockstream инструменты
conda activate DockStream 2>/dev/null || true
for cmd in obabel vina mk_prepare_receptor.py; do
    if command -v $cmd &> /dev/null; then
        echo "   ✅ $cmd: $(which $cmd)"
    else
        echo -e "${RED}   ❌ $cmd не найден${NC}"
    fi
done
conda deactivate 2>/dev/null || true

# prior
if [ -f "$INSTALL_DIR/priors/reinvent.prior" ]; then
    echo "   ✅ prior: $(du -h $INSTALL_DIR/priors/reinvent.prior | cut -f1)"
else
    echo -e "${RED}   ❌ prior не найден${NC}"
fi

echo -e "\n${BLUE}✅ Установка завершена в $INSTALL_DIR${NC}"
echo "   Для запуска:"
echo "   cd $INSTALL_DIR"
echo "   conda activate reinvent4"
echo "   python selective_docking.py"
