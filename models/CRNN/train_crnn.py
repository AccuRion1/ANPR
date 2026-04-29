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


class Config:
    # Пути к данным
    DATA_ROOT = "models/CRNN/plates"
    TRAIN_PATH = os.path.join(DATA_ROOT, "train")
    VAL_PATH = os.path.join(DATA_ROOT, "val")
    TEST_PATH = os.path.join(DATA_ROOT, "test")

    # Сохранение модели
    MODEL_SAVE_DIR = "models/recognition"
    MODEL_PATH = os.path.join(MODEL_SAVE_DIR, "crnn_plate.pth")
    CHAR_SET_PATH = os.path.join(MODEL_SAVE_DIR, "char_set.json")

    # Параметры модели
    IMG_HEIGHT = 64
    IMG_WIDTH = 200
    BATCH_SIZE = 32
    EPOCHS = 100
    LEARNING_RATE = 0.001
    WEIGHT_DECAY = 1e-4

    # Параметры CRNN
    HIDDEN_SIZE = 256
    NUM_LAYERS = 2
    DROPOUT = 0.2

    # Максимальная длина номера
    MAX_PLATE_LENGTH = 12

    # Допустимые символы для российских номеров
    ALLOWED_CHARS = "ABCEHKMOPTXY0123456789"


class PlateDataset(Dataset):
    def __init__(self, data_path, char_to_idx, transform=None):
        self.data_path = data_path
        self.char_to_idx = char_to_idx
        self.transform = transform
        self.samples = []

        self._load_data()

    def _load_data(self):
        img_dir = os.path.join(self.data_path, "img")
        ann_dir = os.path.join(self.data_path, "ann")

        json_files = [f for f in os.listdir(ann_dir) if f.endswith(".json")]

        for json_file in json_files:
            json_path = os.path.join(ann_dir, json_file)

            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                plate_text = data.get("description", "").strip().upper()

                if not plate_text:
                    continue

                # Фильтруем только допустимые символы
                plate_text = ''.join(c for c in plate_text if c in self.char_to_idx)

                if len(plate_text) < 6 or len(plate_text) > Config.MAX_PLATE_LENGTH:
                    continue

                # Ищем изображение
                img_name = data.get("name", json_file.replace(".json", ""))
                img_path = None
                for ext in ['.jpg', '.png', '.jpeg']:
                    candidate = os.path.join(img_dir, img_name + ext)
                    if os.path.exists(candidate):
                        img_path = candidate
                        break

                if img_path is None:
                    continue

                self.samples.append((img_path, plate_text))

            except Exception as e:
                print(f"Ошибка загрузки {json_file}: {e}")

        print(f"Загружено {len(self.samples)} образцов из {self.data_path}")

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        img_path, text = self.samples[idx]

        # Загружаем изображение
        img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            # Возвращаем пустое изображение если не удалось загрузить
            img = np.zeros((Config.IMG_HEIGHT, Config.IMG_WIDTH), dtype=np.uint8)

        # Преобразуем
        img = cv2.resize(img, (Config.IMG_WIDTH, Config.IMG_HEIGHT))
        img = img.astype(np.float32) / 255.0

        if self.transform:
            img = self.transform(img)

        # Кодируем текст
        encoded_text = [self.char_to_idx[c] for c in text]
        text_length = len(encoded_text)

        return {
            'image': torch.tensor(img, dtype=torch.float32).unsqueeze(0),  # (1, H, W)
            'text': torch.tensor(encoded_text, dtype=torch.long),
            'text_length': torch.tensor(text_length, dtype=torch.long),
            'raw_text': text
        }


def ctc_collate_fn(batch):
    return {
        'image': torch.stack([item['image'] for item in batch], dim=0),
        'text': torch.cat([item['text'] for item in batch], dim=0),
        'text_length': torch.stack([item['text_length'] for item in batch], dim=0),
        'raw_text': [item['raw_text'] for item in batch],
    }


class CRNN(nn.Module):
    def __init__(self, num_classes, hidden_size=256, num_layers=2):
        super(CRNN, self).__init__()

        # CNN часть
        self.cnn = nn.Sequential(
            nn.Conv2d(1, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(),
            nn.MaxPool2d(2, 2),  # 64x200 -> 32x100

            nn.Conv2d(64, 128, kernel_size=3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(),
            nn.MaxPool2d(2, 2),  # 32x100 -> 16x50

            nn.Conv2d(128, 256, kernel_size=3, padding=1),
            nn.BatchNorm2d(256),
            nn.ReLU(),
            nn.MaxPool2d(2, 2),  # 16x50 -> 8x25

            nn.Conv2d(256, 512, kernel_size=3, padding=1),
            nn.BatchNorm2d(512),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d((1, 25))
        )

        # RNN часть
        self.rnn = nn.LSTM(
            input_size=512,  # 512 каналов после CNN
            hidden_size=hidden_size,
            num_layers=num_layers,
            bidirectional=True,
            dropout=0.2,
            batch_first=True
        )

        # Выходной слой
        self.fc = nn.Linear(hidden_size * 2, num_classes + 1)  # +1 для CTC blank

    def forward(self, x):
        # x: (batch, 1, H, W)

        # CNN
        conv = self.cnn(x)  # (batch, 512, 1, 25)

        # Подготавливаем для RNN: (batch, time_steps, features)
        # time_steps = 8 (высота), features = 512 * 25 / 8? Нет
        # Нужно reshape: (batch, 512, 8, 25) -> (batch, 25, 512*8)
        conv = conv.squeeze(2)  # (batch, 512, 25)
        conv = conv.permute(0, 2, 1)  # (batch, 25, 512)

        # RNN
        rnn_out, _ = self.rnn(conv)  # (batch, 25, hidden_size*2)

        # Выходной слой
        output = self.fc(rnn_out)  # (batch, 25, num_classes+1)

        # Для CTC: (batch, time_steps, num_classes+1)
        return output


def build_char_set(data_paths):
    """Создает словарь символов из всех данных"""
    chars = set(Config.ALLOWED_CHARS)

    char_to_idx = {char: idx + 1 for idx, char in enumerate(sorted(chars))}
    char_to_idx['[BLANK]'] = 0

    idx_to_char = {idx: char for char, idx in char_to_idx.items()}

    return char_to_idx, idx_to_char, len(chars)


def ctc_decode(preds, idx_to_char, blank_idx=0):
    """Декодирует предсказания CTC"""
    preds = preds.argmax(dim=-1)  # (batch, time_steps)

    decoded = []
    for pred in preds:
        text = []
        prev_char = blank_idx
        for char_idx in pred:
            char_idx = char_idx.item()
            if char_idx != blank_idx and char_idx != prev_char:
                text.append(idx_to_char.get(char_idx, ''))
            prev_char = char_idx
        decoded.append(''.join(text))

    return decoded


def train_epoch(model, dataloader, criterion, optimizer, device):
    model.train()
    total_loss = 0

    for batch in tqdm(dataloader, desc="Training"):
        images = batch['image'].to(device)
        texts = batch['text'].to(device)
        text_lengths = batch['text_length'].to(device)

        optimizer.zero_grad()

        # Forward pass
        outputs = model(images)  # (batch, time_steps, num_classes+1)
        outputs = outputs.log_softmax(2)
        outputs = outputs.permute(1, 0, 2)  # (time_steps, batch, num_classes+1) для CTC

        # CTC loss
        input_lengths = torch.full((images.size(0),), outputs.size(0), dtype=torch.long).to(device)

        loss = criterion(outputs, texts, input_lengths, text_lengths)
        loss.backward()
        optimizer.step()

        total_loss += loss.item()

    return total_loss / len(dataloader)


def validate(model, dataloader, criterion, device, idx_to_char):
    model.eval()
    total_loss = 0
    correct = 0
    total = 0

    with torch.no_grad():
        for batch in tqdm(dataloader, desc="Validation"):
            images = batch['image'].to(device)
            texts = batch['text'].to(device)
            text_lengths = batch['text_length'].to(device)
            raw_texts = batch['raw_text']

            outputs = model(images)
            preds_for_decode = outputs
            outputs = outputs.log_softmax(2).permute(1, 0, 2)

            input_lengths = torch.full((images.size(0),), outputs.size(0), dtype=torch.long).to(device)
            loss = criterion(outputs, texts, input_lengths, text_lengths)
            total_loss += loss.item()

            # Декодируем предсказания
            preds = ctc_decode(preds_for_decode, idx_to_char)

            for pred, true in zip(preds, raw_texts):
                if pred.strip() == true.strip():
                    correct += 1
                total += 1

    accuracy = correct / total if total > 0 else 0
    return total_loss / len(dataloader), accuracy


def main():
    # Создаем директорию для модели
    os.makedirs(Config.MODEL_SAVE_DIR, exist_ok=True)

    # Определяем устройство
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Используем устройство: {device}")

    # Создаем словарь символов
    char_to_idx, idx_to_char, num_classes = build_char_set([
        Config.TRAIN_PATH, Config.VAL_PATH, Config.TEST_PATH
    ])

    print(f"Словарь символов: {num_classes} классов")
    print(f"Символы: {list(char_to_idx.keys())}")

    # Сохраняем словарь
    with open(Config.CHAR_SET_PATH, 'w', encoding='utf-8') as f:
        json.dump(char_to_idx, f, ensure_ascii=False, indent=2)

    # Создаем датасеты
    print("Загрузка датасета train...")
    train_dataset = PlateDataset(Config.TRAIN_PATH, char_to_idx)
    print("Загрузка датасета val...")
    val_dataset = PlateDataset(Config.VAL_PATH, char_to_idx)
    print("Загрузка датасета test...")
    test_dataset = PlateDataset(Config.TEST_PATH, char_to_idx)

    num_workers = 0
    pin_memory = torch.cuda.is_available()

    train_loader = DataLoader(
        train_dataset,
        batch_size=Config.BATCH_SIZE,
        shuffle=True,
        num_workers=num_workers,
        pin_memory=pin_memory,
        collate_fn=ctc_collate_fn,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=Config.BATCH_SIZE,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=pin_memory,
        collate_fn=ctc_collate_fn,
    )
    test_loader = DataLoader(
        test_dataset,
        batch_size=Config.BATCH_SIZE,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=pin_memory,
        collate_fn=ctc_collate_fn,
    )

    print(f"Train: {len(train_dataset)}, Val: {len(val_dataset)}, Test: {len(test_dataset)}")
    print("Создание модели и запуск обучения...")

    # Создаем модель
    model = CRNN(num_classes=num_classes, hidden_size=Config.HIDDEN_SIZE, num_layers=Config.NUM_LAYERS)
    model.to(device)

    # Оптимизатор и loss
    optimizer = optim.Adam(model.parameters(), lr=Config.LEARNING_RATE, weight_decay=Config.WEIGHT_DECAY)
    criterion = nn.CTCLoss(blank=0, reduction='mean', zero_infinity=True)

    # Scheduler для learning rate
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='min', factor=0.5, patience=5)

    # Обучение
    best_accuracy = 0
    train_losses = []
    val_losses = []
    val_accuracies = []

    for epoch in range(Config.EPOCHS):
        print(f"\nEpoch {epoch+1}/{Config.EPOCHS}")

        train_loss = train_epoch(model, train_loader, criterion, optimizer, device)
        val_loss, val_accuracy = validate(model, val_loader, criterion, device, idx_to_char)

        train_losses.append(train_loss)
        val_losses.append(val_loss)
        val_accuracies.append(val_accuracy)

        print(f"Train Loss: {train_loss:.4f} | Val Loss: {val_loss:.4f} | Val Accuracy: {val_accuracy:.4f}")

        scheduler.step(val_loss)

        # Сохраняем лучшую модель
        if val_accuracy > best_accuracy:
            best_accuracy = val_accuracy
            torch.save({
                'epoch': epoch,
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'accuracy': val_accuracy,
                'char_to_idx': char_to_idx,
                'idx_to_char': idx_to_char
            }, Config.MODEL_PATH)
            print(f"Модель сохранена с точностью {val_accuracy:.4f}")

        # Раннее остановка
        if val_accuracy > 0.95:  # 95% точность
            print("Достигнута высокая точность, останавливаем обучение")
            break

    # Финальное тестирование
    print("\nФинальное тестирование:")
    if os.path.exists(Config.MODEL_PATH):
        checkpoint = torch.load(Config.MODEL_PATH, map_location=device)
        model.load_state_dict(checkpoint['model_state_dict'])
    test_loss, test_accuracy = validate(model, test_loader, criterion, device, idx_to_char)
    print(f"Test Loss: {test_loss:.4f} | Test Accuracy: {test_accuracy:.4f}")

    # Графики
    plt.figure(figsize=(12, 4))

    plt.subplot(1, 3, 1)
    plt.plot(train_losses, label='Train Loss')
    plt.plot(val_losses, label='Val Loss')
    plt.legend()
    plt.title('Loss')

    plt.subplot(1, 3, 2)
    plt.plot(val_accuracies, label='Val Accuracy')
    plt.legend()
    plt.title('Accuracy')

    plt.tight_layout()
    plt.savefig(os.path.join(Config.MODEL_SAVE_DIR, 'training_history.png'))
    plt.close()

    print(f"\nОбучение завершено. Лучшая точность: {best_accuracy:.4f}")
    print(f"Модель сохранена в {Config.MODEL_PATH}")


if __name__ == "__main__":
    main()
