import os

# Force Hugging Face to use a local cache directory instead of ~/.cache/

os.environ["HF_HOME"] = "./hf_cache"


from huggingface_hub import snapshot_download 

base_dir="/work/imvia/in156281/projet_pui"

model_id = "Qwen/Qwen3-30B-A3B-Instruct-2507" 
local_dir = os.path.join(base_dir, "Qwen3-30B-A3B-Instruct-2507") 

snapshot_download(
    repo_id=model_id,
    local_dir=local_dir,
    local_dir_use_symlinks=False,
    resume_download=True )

print(f"Model files downloaded to: {local_dir}")
