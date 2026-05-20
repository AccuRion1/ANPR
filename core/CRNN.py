import json
import re
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from core.helper import fix_plate


ALLOWED_CHARS = "ABCEHKMOPTXY0123456789"
PLATE_PATTERN = re.compile(r"^[ABCEHKMOPTXY][0-9]{3}[ABCEHKMOPTXY]{2}[0-9]{2,3}$")
_MODEL = None
_DEVICE = None
_IDX_TO_CHAR = None


class CRNNModel(nn.Module):
    def __init__(self, num_classes, hidden_size=256, num_layers=2):
        super().__init__()
        self.cnn = nn.Sequential(
            nn.Conv2d(1, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2, 2),
            nn.Conv2d(64, 128, kernel_size=3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2, 2),
            nn.Conv2d(128, 256, kernel_size=3, padding=1),
            nn.BatchNorm2d(256),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2, 2),
            nn.Conv2d(256, 512, kernel_size=3, padding=1),
            nn.BatchNorm2d(512),
            nn.ReLU(inplace=True),
            nn.AdaptiveAvgPool2d((1, 25)),
        )
        self.rnn = nn.LSTM(
            input_size=512,
            hidden_size=hidden_size,
            num_layers=num_layers,
            bidirectional=True,
            batch_first=True,
            dropout=0.2,
        )
        self.fc = nn.Linear(hidden_size * 2, num_classes + 1)

    def forward(self, x):
        conv = self.cnn(x)
        conv = conv.squeeze(2)
        conv = conv.permute(0, 2, 1)
        rnn_out, _ = self.rnn(conv)
        return self.fc(rnn_out)


def _model_paths():
    base_dir = Path(__file__).resolve().parent.parent
    model_path = base_dir / "models" / "recognition" / "crnn_plate.pth"
    char_set_path = base_dir / "models" / "recognition" / "char_set.json"
    return model_path, char_set_path


def _load_char_set(char_set_path):
    with open(char_set_path, "r", encoding="utf-8") as file:
        char_to_idx = json.load(file)
    idx_to_char = {int(idx): char for char, idx in char_to_idx.items()}
    return idx_to_char


def _get_model():
    global _MODEL, _DEVICE, _IDX_TO_CHAR

    if _MODEL is not None:
        return _MODEL, _IDX_TO_CHAR, _DEVICE

    model_path, char_set_path = _model_paths()
    if not model_path.exists():
        raise FileNotFoundError(f"CRNN model not found: {model_path}")
    if not char_set_path.exists():
        raise FileNotFoundError(f"CRNN char set not found: {char_set_path}")

    _IDX_TO_CHAR = _load_char_set(char_set_path)
    num_classes = len(_IDX_TO_CHAR) - 1
    _DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    _MODEL = CRNNModel(num_classes=num_classes, hidden_size=256, num_layers=2)

    checkpoint = torch.load(model_path, map_location=_DEVICE)
    state_dict = checkpoint["model_state_dict"] if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint else checkpoint
    _MODEL.load_state_dict(state_dict)
    _MODEL.to(_DEVICE)
    _MODEL.eval()
    return _MODEL, _IDX_TO_CHAR, _DEVICE


def _normalize_candidate(text):
    candidate = re.sub(r"[^A-Za-z0-9]", "", text).upper()
    candidate = fix_plate(candidate)
    candidate = "".join(char for char in candidate if char in ALLOWED_CHARS)
    return candidate


def _extract_rf_plate(candidate):
    if not candidate:
        return ""

    if PLATE_PATTERN.fullmatch(candidate):
        return candidate

    for length in (9, 8):
        for start in range(0, max(0, len(candidate) - length + 1)):
            fragment = candidate[start:start + length]
            if PLATE_PATTERN.fullmatch(fragment):
                return fragment

    return ""


def _candidate_score(candidate, confidence):
    if not candidate:
        return -1.0

    score = float(confidence) * 10.0
    if 6 <= len(candidate) <= 9:
        score += 2.0
    if PLATE_PATTERN.fullmatch(candidate):
        score += 20.0
    score -= abs(8 - len(candidate)) * 0.7
    return score


def _prepare_variants(plate_img, fast_mode=False):
    gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gray)
    sharpened = cv2.addWeighted(clahe, 1.5, cv2.GaussianBlur(clahe, (0, 0), 1.2), -0.5, 0)
    otsu = cv2.threshold(sharpened, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

    variants = [
        ("gray", gray),
        ("clahe", clahe),
        ("sharpened", sharpened),
        ("otsu", otsu),
    ]

    if fast_mode:
        return variants[:2]
    return variants


def _preprocess_variant(gray_variant, img_width=200, img_height=64):
    resized = cv2.resize(gray_variant, (img_width, img_height), interpolation=cv2.INTER_CUBIC)
    normalized = resized.astype(np.float32) / 255.0
    tensor = torch.from_numpy(normalized).unsqueeze(0).unsqueeze(0)
    return tensor, resized


def _ctc_decode(logits, idx_to_char, blank_index=0):
    probabilities = F.softmax(logits, dim=-1)
    max_probs, preds = probabilities.max(dim=-1)
    preds = preds.squeeze(0).tolist()
    max_probs = max_probs.squeeze(0).tolist()

    result = []
    previous = blank_index
    for idx in preds:
        if idx != blank_index and idx != previous:
            result.append(idx_to_char.get(idx, ""))
        previous = idx

    text = "".join(result)
    confidence = float(np.mean(max_probs)) if max_probs else 0.0
    return text, confidence


def recognize_plate_crnn(plate_img, fast_mode=False):
    if plate_img is None or plate_img.size == 0:
        return "", None

    model, idx_to_char, device = _get_model()
    best_text = ""
    best_score = -1.0
    best_preview = None

    for _, variant in _prepare_variants(plate_img, fast_mode=fast_mode):
        tensor, preview = _preprocess_variant(variant)
        tensor = tensor.to(device)

        with torch.no_grad():
            logits = model(tensor)

        text, confidence = _ctc_decode(logits, idx_to_char)
        normalized = _normalize_candidate(text)
        rf_candidate = _extract_rf_plate(normalized)
        score = _candidate_score(rf_candidate or normalized, confidence)

        if score > best_score:
            best_text = rf_candidate or normalized
            best_score = score
            best_preview = preview

    if not best_text:
        return "", best_preview

    # Отсекаем совсем слабые и шумные предсказания, чтобы не спамить журнал случайными строками.
    if best_score < 8.0 or not PLATE_PATTERN.fullmatch(best_text):
        return "", best_preview

    return best_text, best_preview
