#!/bin/bash
set -e  # остановка при ошибке

# Цвета: синий для заголовков, красный для ошибок
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'


# 1. ПАПКИ
echo -e "${BLUE}📁 Создание папок...${NC}"
mkdir -p targets results poses
echo "   ✅ targets/ results/ poses/"


# 2. ПРОВЕРКА CONDA
echo -e "\n${BLUE}🔍 Проверка Conda...${NC}"
if ! command -v conda &> /dev/null; then
    echo -e "${RED}❌ Conda не найдена. Установите Miniconda${NC}"
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
echo "   ✅ reinvent4, DockStream"


# 5. УСТАНОВКА ИНСТРУМЕНТОВ ДОКИНГА
echo -e "\n${BLUE}🔬 Установка openbabel, vina, meeko...${NC}"
source $CONDA_BASE/etc/profile.d/conda.sh
conda activate DockStream
conda install -c conda-forge openbabel vina meeko rdkit numpy pandas -y
pip install prody gemmi
echo "   Проверка: $(which obabel) $(which vina)"
conda deactivate


# 6. УСТАНОВКА REINVENT4
echo -e "\n${BLUE}🎯 Установка REINVENT4...${NC}"
conda activate reinvent4

if [ ! -d "REINVENT4" ]; then
    echo "   Клонирование репозитория..."
    git clone --depth 1 https://github.com/MolecularAI/REINVENT4.git
    cd REINVENT4
else
    cd REINVENT4
    git pull
fi

echo "   Установка зависимостей (CPU)..."
python install.py cpu
pip install --no-deps .
cd ..
echo "   ✅ reinvent: $(which reinvent)"
conda deactivate


# 7. УСТАНОВКА DOCKSTREAM
echo -e "\n${BLUE}🐳 Установка DockStream...${NC}"
if [ ! -d "DockStream" ]; then
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
mkdir -p priors
conda activate reinvent4

if [ ! -f "priors/reinvent.prior" ] && [ ! -f "reinvent.prior" ]; then
    echo "   Скачивание с Zenodo..."
    
    if ! command -v unzip &> /dev/null; then
        sudo apt update && sudo apt install unzip -y
    fi
    
    wget https://zenodo.org/api/records/15641297/files-archive -O priors.zip
    
    if [ -f "priors.zip" ] && [ -s "priors.zip" ]; then
        unzip -o priors.zip -d priors/
        rm priors.zip
        
        if [ -f "priors/reinvent.prior" ]; then
            ln -sf priors/reinvent.prior reinvent.prior
            echo "   ✅ Prior загружен (размер: $(du -h priors/reinvent.prior | cut -f1))"
        else
            echo -e "${RED}   ❌ Ошибка: prior не найден в архиве${NC}"
        fi
    else
        echo -e "${RED}   ❌ Ошибка скачивания${NC}"
    fi
else
    echo "   ✅ Prior уже есть"
fi
conda deactivate


# 9. ФИНАЛЬНАЯ ПРОВЕРКА
echo -e "\n${BLUE}✅ Проверка...${NC}"

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
if [ -f "priors/reinvent.prior" ]; then
    echo "   ✅ prior: $(du -h priors/reinvent.prior | cut -f1)"
else
    echo -e "${RED}   ❌ prior не найден${NC}"
fi

echo -e "\n${BLUE}✅ Установка завершена${NC}"
echo "   Для запуска: conda activate reinvent4 && python selective_docking.py"