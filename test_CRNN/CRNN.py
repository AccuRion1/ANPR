import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


class CRNN(nn.Module):
    def __init__(self, num_classes, hidden_size=256, num_layers=2):
        super(CRNN, self).__init__()

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
        output = self.fc(rnn_out)
        return output


def load_char_set(char_set_path):
    with open(char_set_path, 'r', encoding='utf-8') as f:
        char_to_idx = json.load(f)
    idx_to_char = {int(idx): char for char, idx in char_to_idx.items()}
    return char_to_idx, idx_to_char


def preprocess_plate_image(image, img_width=200, img_height=64):
    if image is None:
        raise ValueError('Image not loaded')

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (img_width, img_height), interpolation=cv2.INTER_CUBIC)
    normalized = resized.astype(np.float32) / 255.0
    tensor = torch.from_numpy(normalized).unsqueeze(0).unsqueeze(0)
    return tensor


def ctc_decode(logits, idx_to_char, blank_index=0):
    probs = F.softmax(logits, dim=-1)
    max_probs, preds = probs.max(dim=-1)
    preds = preds.squeeze(0).tolist()
    max_probs = max_probs.squeeze(0).tolist()
    result = []
    previous = blank_index

    for idx in preds:
        if idx != blank_index and idx != previous:
            result.append(idx_to_char.get(idx, ''))
        previous = idx

    text = ''.join(result)
    confidence = float(np.mean(max_probs)) if max_probs else 0.0
    return text, confidence


def load_model(model_path, num_classes, device):
    model = CRNN(num_classes=num_classes, hidden_size=256, num_layers=2)
    checkpoint = torch.load(model_path, map_location=device)
    model.load_state_dict(checkpoint['model_state_dict'])
    model.to(device)
    model.eval()
    return model


def recognize_plate(image_input, model, idx_to_char, device):
    if isinstance(image_input, str) or isinstance(image_input, Path):
        image = cv2.imread(str(image_input))
    else:
        image = image_input

    if image is None:
        raise FileNotFoundError(f'Unable to load image input: {image_input}')

    tensor = preprocess_plate_image(image).to(device)
    with torch.no_grad():
        logits = model(tensor)

    text, confidence = ctc_decode(logits, idx_to_char)
    return text, confidence


def main():
    parser = argparse.ArgumentParser(description='CRNN license plate recognition test script')
    parser.add_argument('--image', required=True, help='Path to a license plate image')
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent.parent
    model_path = base_dir / 'models' / 'recognition' / 'crnn_plate.pth'
    char_set_path = base_dir / 'models' / 'recognition' / 'char_set.json'

    if not model_path.exists():
        raise FileNotFoundError(f'CRNN model not found: {model_path}')
    if not char_set_path.exists():
        raise FileNotFoundError(f'Character set file not found: {char_set_path}')

    _, idx_to_char = load_char_set(char_set_path)
    num_classes = len(idx_to_char) - 1

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f'Using device: {device}')

    model = load_model(model_path, num_classes, device)
    plate_text, score = recognize_plate(args.image, model, idx_to_char, device)

    print(f'Recognized plate: {plate_text}')
    print(f'Confidence score: {score:.4f}')


if __name__ == '__main__':
    main()
