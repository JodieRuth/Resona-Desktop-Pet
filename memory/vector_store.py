import numpy as np
from pathlib import Path
from typing import List, Optional, Tuple
import json
import logging

logger = logging.getLogger("Memory")


class VectorStore:
    REQUIRED_FILES = [
        "config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "sentencepiece.bpe.model",
        "special_tokens_map.json",
    ]

    def __init__(self, model_path: Path, model_file: str = "model.onnx"):
        self.model_path = model_path
        self.model_file = model_file
        self.model = None
        self.tokenizer = None
        self._load_model()

    def _load_model(self):
        try:
            try:
                from optimum.onnxruntime import ORTModelForFeatureExtraction
                from transformers import AutoTokenizer

                model_file_path = self.model_path / self.model_file

                if not model_file_path.exists():
                    return

                self.tokenizer = AutoTokenizer.from_pretrained(str(self.model_path))
                self.model = ORTModelForFeatureExtraction.from_pretrained(
                    str(self.model_path),
                    file_name=self.model_file
                )
                logger.info(f"[VectorStore] Loaded ONNX model via optimum: {self.model_file}")

            except ImportError:
                import onnxruntime as ort
                from transformers import AutoTokenizer

                model_file_path = self.model_path / self.model_file

                if not model_file_path.exists():
                    return

                self.tokenizer = AutoTokenizer.from_pretrained(str(self.model_path))

                self.session = ort.InferenceSession(str(model_file_path))
                self.model = self  

                logger.info(f"[VectorStore] Loaded ONNX model via onnxruntime: {self.model_file}")

        except Exception as e:
            logger.info(f"[VectorStore] Failed to load model: {e}")

    def is_loaded(self) -> bool:
        return self.model is not None and self.tokenizer is not None

    def encode(self, texts: List[str]) -> List[np.ndarray]:
        if not self.is_loaded():
            raise RuntimeError("Model not loaded")

        inputs = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="np"
        )

        if hasattr(self, 'session'):
            input_names = [inp.name for inp in self.session.get_inputs()]
            input_feed = {}

            for name in input_names:
                if name in inputs:
                    tensor = inputs[name]
                    if tensor.dtype == np.int32:
                        tensor = tensor.astype(np.int64)
                    input_feed[name] = tensor

            outputs = self.session.run(None, input_feed)
            embeddings = outputs[0].mean(axis=1)  
        else:
            import torch
            inputs_pt = {k: torch.from_numpy(v) for k, v in inputs.items()}
            outputs = self.model(**inputs_pt)
            embeddings = outputs.last_hidden_state.mean(dim=1)
            embeddings = embeddings.detach().numpy()

        return [embeddings[i] for i in range(len(texts))]

    def encode_single(self, text: str) -> np.ndarray:
        return self.encode([text])[0]

    def to_bytes(self, vector: np.ndarray) -> bytes:
        return vector.astype(np.float32).tobytes()

    def from_bytes(self, data: bytes) -> np.ndarray:
        return np.frombuffer(data, dtype=np.float32)

    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    def search_similar(
        self,
        query: str,
        candidates: List[Tuple[str, bytes]],
        top_k: int = 5
    ) -> List[Tuple[str, float]]:
        if not self.is_loaded():
            return []

        query_vec = self.encode_single(query)

        similarities = []
        for content, vec_bytes in candidates:
            candidate_vec = self.from_bytes(vec_bytes)
            sim = self.cosine_similarity(query_vec, candidate_vec)
            similarities.append((content, sim))

        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:top_k]
