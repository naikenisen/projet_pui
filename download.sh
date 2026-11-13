#!/bin/ksh 
#$ -q gpu 
#$ -o train.out 
#$ -j y 
#$ -N train

set -e

# Modify these variables to adapt the sh script to your ccub accout and workgroup
USER_NAME=in156281 
GROUP_NAME=imvia
# modify theses variables according to your project directory name and virtual environment directory name
PROJECT_NAME=projet_pui
VENV_SUBFOLDER=projet_pui
# this part should not be modified
BASE_BEEGFS=/beegfs/data/work/$GROUP_NAME/$USER_NAME 
BASE_WORK=/work/$GROUP_NAME/$USER_NAME 
PROJECT_DIR=$BASE_BEEGFS/$PROJECT_NAME
VENV_DIR=$BASE_BEEGFS/$VENV_SUBFOLDER/venv 

cd "$WORKDIR" 
cd "$PROJECT_DIR" 

source "$VENV_DIR/bin/activate"
module load python
export PYTHONPATH="$VENV_DIR/lib/python3.9/site-packages:$PYTHONPATH" 

python download.py
