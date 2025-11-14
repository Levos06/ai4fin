#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для объединения всех документов в одну таблицу и копирования файлов
"""

import csv
import os
import shutil
from pathlib import Path

# Путь к корневой директории
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "all_documents"
OUTPUT_CSV = BASE_DIR / "all_documents.csv"

def remove_suffix(filename):
    """Удаляет суффиксы _article и _cleaned из имени файла"""
    # Удаляем расширение
    name_without_ext = filename.rsplit('.', 1)[0]
    ext = filename.rsplit('.', 1)[1] if '.' in filename else ''
    
    # Удаляем суффиксы
    if name_without_ext.endswith('_article'):
        name_without_ext = name_without_ext[:-8]
    elif name_without_ext.endswith('_cleaned'):
        name_without_ext = name_without_ext[:-8]
    
    return f"{name_without_ext}.{ext}" if ext else name_without_ext

def find_file_with_variants(base_path, base_name):
    """Ищет файл с различными вариантами суффиксов"""
    # Создаем список вариантов для поиска
    variants = []
    
    # Если имя уже содержит _cleaned, ищем его как есть
    if '_cleaned' in base_name:
        variants.append(base_name)
    else:
        # Пробуем разные варианты
        if base_name.endswith('.txt'):
            name_without_ext = base_name[:-4]
            variants.extend([
                base_name,  # Оригинальное имя
                f"{name_without_ext}_cleaned.txt",  # С _cleaned
                f"{name_without_ext}_article.txt",  # С _article
            ])
        elif base_name.endswith('.html'):
            name_without_ext = base_name[:-5]
            variants.extend([
                f"{name_without_ext}_cleaned.txt",
                f"{name_without_ext}_article.txt",
                f"{name_without_ext}.txt",
            ])
        else:
            variants.append(base_name)
    
    # Убираем дубликаты, сохраняя порядок
    seen = set()
    unique_variants = []
    for v in variants:
        if v not in seen:
            seen.add(v)
            unique_variants.append(v)
    
    # Ищем файл
    for variant in unique_variants:
        full_path = base_path / variant
        if full_path.exists():
            return variant, full_path
    
    # Если не нашли, возвращаем первый вариант
    return base_name, base_path / base_name

def process_alph():
    """Обрабатывает данные из alph.csv"""
    data = []
    csv_path = BASE_DIR / "alph.csv"
    
    if not csv_path.exists():
        return data
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = row.get('URL', '')
            name = row.get('Название', '')
            filename = row.get('Имя файла', '')
            
            # Преобразуем .html в .txt
            if filename.endswith('.html'):
                filename = filename.replace('.html', '.txt')
            
            # Ищем файл с различными вариантами
            actual_filename, source_path = find_file_with_variants(BASE_DIR / 'alph', filename)
            
            data.append({
                'URL': url,
                'Название': name,
                'Имя файла': actual_filename,
                'Тип': 'статья',
                'Источник': 'alph',
                'Исходный путь': source_path
            })
    
    return data

def process_fin():
    """Обрабатывает данные из fin.csv"""
    data = []
    csv_path = BASE_DIR / "fin.csv"
    
    if not csv_path.exists():
        return data
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = row.get('URL', '')
            name = row.get('Название', '')
            filename = row.get('Имя файла', '')
            
            data.append({
                'URL': url if url != '-' else '',
                'Название': name,
                'Имя файла': filename,
                'Тип': 'документ',
                'Источник': 'fin',
                'Исходный путь': BASE_DIR / 'fin' / filename
            })
    
    return data

def extract_title_from_url(url):
    """Извлекает название из URL"""
    if not url:
        return ''
    # Берем последнюю часть URL после последнего слеша
    parts = url.rstrip('/').split('/')
    if parts:
        title = parts[-1]
        # Убираем расширения и декодируем
        title = title.replace('.html', '').replace('-', ' ').replace('_', ' ')
        return title
    return ''

def process_fincult():
    """Обрабатывает данные из fincult.csv"""
    data = []
    csv_path = BASE_DIR / "fincult.csv"
    
    if not csv_path.exists():
        return data
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = row.get('URL', '')
            filename = row.get('Имя файла', '')
            
            # Преобразуем .html в _cleaned.txt
            if filename.endswith('.html'):
                filename = filename.replace('.html', '_cleaned.txt')
            
            # Ищем файл
            actual_filename, source_path = find_file_with_variants(BASE_DIR / 'fincult', filename)
            
            # Извлекаем название из URL
            name = extract_title_from_url(url)
            if not name:
                # Если не получилось из URL, берем из имени файла
                name = actual_filename.replace('_cleaned.txt', '').replace('-', ' ').replace('_', ' ')
            
            data.append({
                'URL': url,
                'Название': name,
                'Имя файла': actual_filename,
                'Тип': 'статья',
                'Источник': 'fincult',
                'Исходный путь': source_path
            })
    
    return data

def process_gazprom():
    """Обрабатывает данные из gazprom.csv"""
    data = []
    csv_path = BASE_DIR / "gazprom.csv"
    
    if not csv_path.exists():
        return data
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = row.get('URL', '')
            filename = row.get('Имя файла', '')
            
            # Преобразуем .html в _cleaned.txt
            if filename.endswith('.html'):
                filename = filename.replace('.html', '_cleaned.txt')
            
            # Ищем файл
            actual_filename, source_path = find_file_with_variants(BASE_DIR / 'gazprom', filename)
            
            # Извлекаем название из URL
            name = extract_title_from_url(url)
            if not name:
                # Если не получилось из URL, берем из имени файла
                name = actual_filename.replace('_cleaned.txt', '').replace('-', ' ').replace('_', ' ')
            
            data.append({
                'URL': url,
                'Название': name,
                'Имя файла': actual_filename,
                'Тип': 'статья',
                'Источник': 'gazprom',
                'Исходный путь': source_path
            })
    
    return data

def process_moex():
    """Обрабатывает данные из moex.csv"""
    data = []
    csv_path = BASE_DIR / "moex.csv"
    
    if not csv_path.exists():
        return data
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = row.get('URL', '')
            name = row.get('Название', '')
            filename = row.get('Имя файла', '')
            
            # Преобразуем .html в _cleaned.txt
            if filename.endswith('.html'):
                filename = filename.replace('.html', '_cleaned.txt')
            
            # Ищем файл
            actual_filename, source_path = find_file_with_variants(BASE_DIR / 'moex', filename)
            
            data.append({
                'URL': url,
                'Название': name,
                'Имя файла': actual_filename,
                'Тип': 'статья',
                'Источник': 'moex',
                'Исходный путь': source_path
            })
    
    return data

def process_books():
    """Обрабатывает данные из files_data.csv (books)"""
    data = []
    csv_path = BASE_DIR / "files_data.csv"
    
    if not csv_path.exists():
        return data
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = row.get('URL', '')
            name = row.get('Название', '')
            filename = row.get('file_name', '')
            
            data.append({
                'URL': url,
                'Название': name,
                'Имя файла': filename,
                'Тип': 'документ',
                'Источник': 'books',
                'Исходный путь': BASE_DIR / 'books' / filename
            })
    
    return data

def main():
    print("Начинаю обработку данных...")
    
    # Собираем все данные
    all_data = []
    all_data.extend(process_alph())
    all_data.extend(process_fin())
    all_data.extend(process_fincult())
    all_data.extend(process_gazprom())
    all_data.extend(process_moex())
    all_data.extend(process_books())
    
    print(f"Найдено {len(all_data)} записей")
    
    # Создаем выходную директорию
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    # Создаем общую таблицу и копируем файлы
    with open(OUTPUT_CSV, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['URL', 'Название', 'Тип', 'Источник', 'Имя файла'])
        writer.writeheader()
        
        for item in all_data:
            source_path = item['Исходный путь']
            original_filename = item['Имя файла']
            new_filename = remove_suffix(original_filename)
            
            # Копируем файл с новым именем
            if source_path.exists():
                dest_path = OUTPUT_DIR / new_filename
                
                # Если файл с таким именем уже существует, добавляем суффикс источника
                if dest_path.exists():
                    name_part = new_filename.rsplit('.', 1)[0]
                    ext = new_filename.rsplit('.', 1)[1] if '.' in new_filename else 'txt'
                    new_filename = f"{name_part}_{item['Источник']}.{ext}"
                    dest_path = OUTPUT_DIR / new_filename
                
                try:
                    shutil.copy2(source_path, dest_path)
                    print(f"Скопирован: {original_filename} -> {new_filename}")
                except Exception as e:
                    print(f"Ошибка при копировании {source_path}: {e}")
            else:
                print(f"Файл не найден: {source_path}")
            
            # Записываем в CSV с новым именем файла
            writer.writerow({
                'URL': item['URL'],
                'Название': item['Название'],
                'Тип': item['Тип'],
                'Источник': item['Источник'],
                'Имя файла': new_filename
            })
    
    print(f"\nГотово! Создана таблица: {OUTPUT_CSV}")
    print(f"Файлы скопированы в: {OUTPUT_DIR}")
    print(f"Всего обработано: {len(all_data)} документов")

if __name__ == "__main__":
    main()

