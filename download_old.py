import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

model_id = "Qwen/Qwen3-30B-A3B-Instruct-2507"

save_directory = "Qwen3-30B-A3B-Instruct-2507" 

print(f"Downloading tokenizer for {model_id}...") 

tokenizer = AutoTokenizer.from_pretrained(
    model_id,
    trust_remote_code=True )

print(f"Downloading model weights and loading with PyTorch...")

# device_map="auto" distributes the 30B MoE layers across available GPUs/CPU torch_dtype=torch.bfloat16 keeps memory usage minimal without loss of precision

model = AutoModelForCausalLM.from_pretrained(
    model_id,
    torch_dtype=torch.bfloat16,
    device_map="auto",
    trust_remote_code=True )

# Optional: Save a local copy to disk for offline access

print(f"Saving model and tokenizer locally to {save_directory}...") 

model.save_pretrained(save_directory) 

tokenizer.save_pretrained(save_directory)

print("Download and local save complete!\n")
