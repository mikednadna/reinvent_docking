#!/bin/bash
#SBATCH -p aichem
#SBATCH --cpus-per-task=16
#SBATCH --time=48:00:00
#SBATCH --gres=gpu:1

set -e  # остановка при ошибке

# Цвета
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

# Устанавливаем путь установки (ТУТ СВОЕ ИМЯ НА КЛАСТЕРЕ)
export INSTALL_DIR="/mnt/tank/scratch/username"    # ТУТ МЕНЯЕМ ИМЯ НА СВОЕ
cd $INSTALL_DIR

echo -e "${BLUE}📁 Установка в: $INSTALL_DIR${NC}"

# 1. ПАПКИ
echo -e "\n${BLUE}📁 Создание папок...${NC}"
mkdir -p targets results poses priors
echo "   ✅ папки готовы"

# 2. ПРОВЕРКА И УСТАНОВКА CONDA (НОВЫЙ ПУНКТ!)
echo -e "\n${BLUE}🔍 Проверка conda...${NC}"

# Функция для установки Miniconda
install_miniconda() {
    echo "   Установка Miniconda в $INSTALL_DIR/miniconda3..."
    
    # Скачиваем Miniconda
    wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O miniconda.sh
    
    # Устанавливаем
    bash miniconda.sh -b -p $INSTALL_DIR/miniconda3
    rm miniconda.sh
    
    # Инициализируем conda
    source $INSTALL_DIR/miniconda3/etc/profile.d/conda.sh
    $INSTALL_DIR/miniconda3/bin/conda init bash
    
    # Добавляем в PATH для текущей сессии
    export PATH="$INSTALL_DIR/miniconda3/bin:$PATH"
    
    echo "   ✅ Miniconda установлена"
}

# Проверяем, доступна ли conda как модуль
if command -v conda &> /dev/null; then
    echo "   ✅ Conda уже доступна: $(which conda)"
    CONDA_BASE=$(conda info --base)
else
    echo -e "${BLUE}   ⚠️ Conda не найдена в системе${NC}"
    
    # Пробуем загрузить модуль conda (названия могут отличаться)
    if module load anaconda3 2>/dev/null || module load miniconda3 2>/dev/null || module load python/conda 2>/dev/null; then
        echo "   ✅ Conda модуль загружен"
        source $CONDA_BASE/etc/profile.d/conda.sh 2>/dev/null || true
    else
        echo "   ⚠️ Модуль conda не найден, устанавливаем свою копию"
        install_miniconda
    fi
    
    # Проверяем еще раз
    if ! command -v conda &> /dev/null; then
        echo -e "${RED}   ❌ Не удалось установить conda${NC}"
        exit 1
    fi
    CONDA_BASE=$(conda info --base)
fi

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

# На сервере с GPU (по #SBATCH --gres=gpu:1)
echo "   Установка зависимостей с поддержкой GPU..."
python install.py cu121  # или cu126, смотря какая версия CUDA на кластере

pip install --no-deps .
cd $INSTALL_DIR

echo "   Проверка: $(which reinvent || echo 'не найден')"
conda deactivate

# 7. УСТАНОВКА DOCKSTREAM
echo -e "\n${BLUE}🐳 Установка DockStream...${NC}"

cd $INSTALL_DIR

# Удаляем старую папку, если она есть
if [ -d "DockStream" ]; then
    echo "   🗑️ Удаление старой версии DockStream..."
    rm -rf DockStream
fi

# Клонируем свежий репозиторий
echo "   Клонирование репозитория DockStream..."
git clone https://github.com/MolecularAI/DockStream.git
cd DockStream

# Активируем окружение DockStream
conda activate DockStream

# Устанавливаем как Python-пакет
echo "   Установка DockStream через pip install -e ."
pip install -e .

# Возвращаемся назад
cd $INSTALL_DIR

# Проверяем, что установка прошла успешно
echo "   Проверка импорта DockStream..."
conda run -n DockStream python -c "
try:
    import dockstream
    print('   ✅ DockStream успешно импортирован')
except ImportError as e:
    print('   ❌ Ошибка импорта:', e)
    exit(1)
"

conda deactivate
echo "   ✅ DockStream готов к работе"

# 8. ЗАГРУЗКА PRIOR ФАЙЛА
echo -e "\n${BLUE}📥 Загрузка prior-модели...${NC}"
cd $INSTALL_DIR
conda activate reinvent4

if [ ! -f "priors/reinvent.prior" ] && [ ! -f "reinvent.prior" ]; then
    echo "   Скачивание с Zenodo..."
    
    if command -v wget &> /dev/null; then
        wget -q --show-progress https://zenodo.org/api/records/15641297/files-archive -O priors.zip
    elif command -v curl &> /dev/null; then
        curl -L https://zenodo.org/api/records/15641297/files-archive -o priors.zip
    else
        echo -e "${RED}❌ Нет wget или curl${NC}"
        exit 1
    fi
    
    if [ -f "priors.zip" ] && [ -s "priors.zip" ]; then
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
