#!/usr/bin/env python3
"""
Обучение CRNN модели для распознавания российских номерных знаков
Использует PyTorch для высокой производительности на GPU
"""

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import cv2
import numpy as np
import json
import os
from tqdm import tqdm
import matplotlib.pyplot as plt


import os
import json
import cv2
import numpy as np
from tqdm import tqdm

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader


class Config:
    # Пути к данным
    DATA_ROOT = "models/CRNN/plates"
    TRAIN_PATH = os.path.join(DATA_ROOT, "train")
    VAL_PATH = os.path.join(DATA_ROOT, "val")
    TEST_PATH = os.path.join(DATA_ROOT, "test")

    # Сохранение модели
    MODEL_SAVE_DIR = "models/recognition"
    MODEL_PATH = os.path.join(MODEL_SAVE_DIR, "crnn_plate2.pth")
    CHAR_SET_PATH = os.path.join(MODEL_SAVE_DIR, "char_set2.json")

    # Размер изображения
    IMG_WIDTH = 160
    IMG_HEIGHT = 48

    # Параметры обучения
    BATCH_SIZE = 32
    EPOCHS = 30
    LEARNING_RATE = 0.001

    # Символы российских номеров
    CHARS = "ABCEHKMOPTXY0123456789"

    # Устройство
    DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


os.makedirs(Config.MODEL_SAVE_DIR, exist_ok=True)


# ==========================================
# Кодировка символов
# ==========================================

char_to_idx = {char: idx + 1 for idx, char in enumerate(Config.CHARS)}
idx_to_char = {idx + 1: char for idx, char in enumerate(Config.CHARS)}

# blank token для CTC
idx_to_char[0] = ""

with open(Config.CHAR_SET_PATH, "w", encoding="utf-8") as file:
    json.dump({
        "char_to_idx": char_to_idx,
        "idx_to_char": idx_to_char,
    }, file, ensure_ascii=False, indent=4)


# ==========================================
# Dataset
# ==========================================

class PlateDataset(Dataset):
    def __init__(self, folder_path):
        self.folder_path = folder_path
        self.image_dir = os.path.join(folder_path, "img")
        self.image_files = []

        if not os.path.exists(self.image_dir):
            print(f"Предупреждение: директория {self.image_dir} не найдена")
            return

        for file_name in os.listdir(self.image_dir):
            if file_name.lower().endswith((".jpg", ".jpeg", ".png")):
                self.image_files.append(file_name)

    def __len__(self):
        return len(self.image_files)

    def encode_label(self, text):
        encoded = []

        for char in text:
            if char in char_to_idx:
                encoded.append(char_to_idx[char])

        return encoded

    def preprocess_image(self, image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        resized = cv2.resize(
            gray,
            (Config.IMG_WIDTH, Config.IMG_HEIGHT)
        )

        normalized = resized.astype(np.float32) / 255.0

        normalized = np.expand_dims(normalized, axis=0)

        return normalized

    def __getitem__(self, index):
        file_name = self.image_files[index]

        image_path = os.path.join(self.image_dir, file_name)

        image = cv2.imread(image_path)

        if image is None:
            raise ValueError(f"Ошибка загрузки изображения: {image_path}")

        image = self.preprocess_image(image)

        label = os.path.splitext(file_name)[0].upper()
        label = ''.join([char for char in label if char in Config.CHARS])

        encoded_label = self.encode_label(label)

        return (
            torch.tensor(image, dtype=torch.float32),
            torch.tensor(encoded_label, dtype=torch.long),
            len(encoded_label)
        )


# ==========================================
# Collate function
# ==========================================

def collate_fn(batch):
    images = []
    labels = []
    label_lengths = []

    for image, label, label_length in batch:
        images.append(image)
        labels.extend(label.tolist())
        label_lengths.append(label_length)

    images = torch.stack(images)
    labels = torch.tensor(labels, dtype=torch.long)
    label_lengths = torch.tensor(label_lengths, dtype=torch.long)

    return images, labels, label_lengths


# ==========================================
# CRNN модель
# ==========================================

class CRNN(nn.Module):
    def __init__(self, num_classes):
        super(CRNN, self).__init__()

        self.cnn = nn.Sequential(
            nn.Conv2d(1, 64, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2, 2),

            nn.Conv2d(64, 128, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2, 2),

            nn.Conv2d(128, 256, kernel_size=3, padding=1),
            nn.BatchNorm2d(256),
            nn.ReLU(),

            nn.Conv2d(256, 256, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d((2, 1)),

            nn.Conv2d(256, 512, kernel_size=3, padding=1),
            nn.BatchNorm2d(512),
            nn.ReLU(),

            nn.Conv2d(512, 512, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d((2, 1)),

            nn.Conv2d(512, 512, kernel_size=2),
            nn.ReLU(),
        )

        self.rnn = nn.LSTM(
            input_size=512,
            hidden_size=256,
            num_layers=2,
            bidirectional=True,
            batch_first=True
        )

        self.fc = nn.Linear(512, num_classes)

    def forward(self, x):
        x = self.cnn(x)

        batch_size, channels, height, width = x.size()

        x = x.squeeze(2)
        x = x.permute(0, 2, 1)

        x, _ = self.rnn(x)

        x = self.fc(x)

        x = x.permute(1, 0, 2)

        return x


# ==========================================
# Декодирование результата
# ==========================================

def decode_prediction(prediction):
    prediction = prediction.argmax(2)
    prediction = prediction.permute(1, 0)

    texts = []

    for sequence in prediction:
        previous = -1
        text = ""

        for index in sequence:
            index = index.item()

            if index != previous and index != 0:
                text += idx_to_char.get(index, "")

            previous = index

        texts.append(text)

    return texts


# ==========================================
# Обучение
# ==========================================

def train_epoch(model, loader, criterion, optimizer):
    model.train()

    total_loss = 0

    progress_bar = tqdm(loader, desc="Обучение")

    for images, labels, label_lengths in progress_bar:
        images = images.to(Config.DEVICE)
        labels = labels.to(Config.DEVICE)
        label_lengths = label_lengths.to(Config.DEVICE)

        optimizer.zero_grad()

        outputs = model(images)

        input_lengths = torch.full(
            size=(images.size(0),),
            fill_value=outputs.size(0),
            dtype=torch.long
        ).to(Config.DEVICE)

        loss = criterion(
            outputs.log_softmax(2),
            labels,
            input_lengths,
            label_lengths
        )

        loss.backward()

        optimizer.step()

        total_loss += loss.item()

        progress_bar.set_postfix(loss=loss.item())

    return total_loss / len(loader)


# ==========================================
# Валидация
# ==========================================

def validate(model, loader, criterion):
    model.eval()

    total_loss = 0

    with torch.no_grad():
        for images, labels, label_lengths in loader:
            images = images.to(Config.DEVICE)
            labels = labels.to(Config.DEVICE)
            label_lengths = label_lengths.to(Config.DEVICE)

            outputs = model(images)

            input_lengths = torch.full(
                size=(images.size(0),),
                fill_value=outputs.size(0),
                dtype=torch.long
            ).to(Config.DEVICE)

            loss = criterion(
                outputs.log_softmax(2),
                labels,
                input_lengths,
                label_lengths
            )

            total_loss += loss.item()

    return total_loss / len(loader)


# ==========================================
# Главная функция
# ==========================================

def main():
    print(f"Устройство: {Config.DEVICE}")

    train_dataset = PlateDataset(Config.TRAIN_PATH)
    val_dataset = PlateDataset(Config.VAL_PATH)

    train_loader = DataLoader(
        train_dataset,
        batch_size=Config.BATCH_SIZE,
        shuffle=True,
        collate_fn=collate_fn
    )

    val_loader = DataLoader(
        val_dataset,
        batch_size=Config.BATCH_SIZE,
        shuffle=False,
        collate_fn=collate_fn
    )

    num_classes = len(Config.CHARS) + 1

    model = CRNN(num_classes).to(Config.DEVICE)

    criterion = nn.CTCLoss(blank=0, zero_infinity=True)

    optimizer = optim.Adam(
        model.parameters(),
        lr=Config.LEARNING_RATE
    )

    best_val_loss = float("inf")

    train_losses = []
    val_losses = []

    for epoch in range(Config.EPOCHS):
        print(f"\nЭпоха {epoch + 1}/{Config.EPOCHS}")

        train_loss = train_epoch(
            model,
            train_loader,
            criterion,
            optimizer
        )

        val_loss = validate(
            model,
            val_loader,
            criterion
        )

        train_losses.append(train_loss)
        val_losses.append(val_loss)

        print(f"Train Loss: {train_loss:.4f}")
        print(f"Val Loss: {val_loss:.4f}")

        if val_loss < best_val_loss:
            best_val_loss = val_loss

            torch.save({
                "model_state_dict": model.state_dict(),
                "char_to_idx": char_to_idx,
                "idx_to_char": idx_to_char,
            }, Config.MODEL_PATH)

            print("Модель сохранена")

    plt.figure(figsize=(10, 5))
    plt.plot(train_losses, label="Train Loss")
    plt.plot(val_losses, label="Val Loss")
    plt.xlabel("Epoch")
    plt.ylabel("Loss")
    plt.legend()
    plt.grid()
    plt.show()


if __name__ == "__main__":
    main()
