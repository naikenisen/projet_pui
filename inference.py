import os
import argparse
from functools import lru_cache

from openai import OpenAI, NOT_GIVEN
from openai.types.chat import ChatCompletionMessageParam

from dotenv import load_dotenv

import torch
from transformers import AutoConfig, AutoModelForCausalLM, AutoModelForImageTextToText, AutoTokenizer
from sentence_transformers import SentenceTransformer

MODEL = "qwen/qwen3.6-35b-a3b"
EMBEDDING_MODEL = "qwen/qwen3-embedding-8b"

@lru_cache(maxsize=1)
def get_openrouter_client() -> OpenAI:
    load_dotenv()
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is required for remote inference.")
    return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)

@lru_cache(maxsize=1)
def load_local_generator(model_id: str):
    config = AutoConfig.from_pretrained(model_id)
    model_class = AutoModelForImageTextToText if hasattr(config, "vision_config") else AutoModelForCausalLM
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    model = model_class.from_pretrained(
        model_id, config=config, dtype="auto" if torch.cuda.is_available() else torch.float32, device_map="auto"
    )
    model.eval()
    return tokenizer, model


@lru_cache(maxsize=1)
def load_local_embedder(model_id: str):
    return SentenceTransformer(model_id, device="cuda" if torch.cuda.is_available() else "cpu")


class InferenceBackend:
    def __init__(self, local: bool = False):
        self.local = local
        self.model = MODEL
        self.embedding_model = EMBEDDING_MODEL

    def generate(self, system_prompt: str, message: str, *, max_tokens: int,
                 reasoning: bool = False, json_mode: bool = False) -> str:
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ]
        if self.local:
            import torch

            tokenizer, model = load_local_generator(self.model)
            prompt = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True, enable_thinking=reasoning
            )
            inputs = tokenizer(prompt, return_tensors="pt", add_special_tokens=False).to(model.device)
            input_length = inputs["input_ids"].shape[1]
            context_length = model.config.get_text_config().max_position_embeddings
            if input_length + max_tokens > context_length:
                raise ValueError(
                    f"Input ({input_length} tokens) and requested output ({max_tokens} tokens) exceed "
                    f"the context window of {self.model} ({context_length} tokens)."
                )
            with torch.inference_mode():
                output = model.generate(
                    **inputs, max_new_tokens=max_tokens, do_sample=False,
                    pad_token_id=tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.eos_token_id,
                )
            generated_ids = output[0, input_length:].tolist()
            # Separate reasoning before decoding, as thinking markers may be special tokens.
            end_thinking = tokenizer.convert_tokens_to_ids("</think>")
            if end_thinking is not None and end_thinking != tokenizer.unk_token_id:
                if end_thinking in generated_ids:
                    last_end = len(generated_ids) - 1 - generated_ids[::-1].index(end_thinking)
                    generated_ids = generated_ids[last_end + 1:]
                elif reasoning:
                    raise ValueError(f"The model {self.model} did not finish its reasoning before answering.")
            text = tokenizer.decode(generated_ids, skip_special_tokens=True)
        else:
            completion = get_openrouter_client().chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0,
                response_format={"type": "json_object"} if json_mode else NOT_GIVEN,
                extra_body={"reasoning": {"enabled": reasoning}},
            )
            text = completion.choices[0].message.content
        if not text or not text.strip():
            raise ValueError(f"The model {self.model} returned an empty response.")
        return text

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self.local:
            model = load_local_embedder(self.embedding_model)
            return model.encode(
                texts, batch_size=4, prompt="", normalize_embeddings=True,
                convert_to_numpy=True, show_progress_bar=False,
            ).tolist()
        response = get_openrouter_client().embeddings.create(model=self.embedding_model, input=texts)
        return [element.embedding for element in response.data]


def add_inference_arguments(parser: argparse.ArgumentParser):
    parser.add_argument("--local", action="store_true", help="run inference locally with Hugging Face models")


def backend_from_args(args: argparse.Namespace) -> InferenceBackend:
    return InferenceBackend(local=args.local)
