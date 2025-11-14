#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для анализа и визуализации статистики векторной базы данных
"""
import json
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime
import statistics

import chromadb
from chromadb.config import Settings
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np

from config import VECTOR_DB_DIR

# Настройка стиля для графиков
try:
    plt.style.use('seaborn-v0_8-darkgrid')
except OSError:
    try:
        plt.style.use('seaborn-darkgrid')
    except OSError:
        plt.style.use('ggplot')
sns.set_palette("husl")

# Создаем директорию для статистики
STATS_DIR = VECTOR_DB_DIR.parent / "statistics"
STATS_DIR.mkdir(parents=True, exist_ok=True)


def load_vector_db():
    """Загружает данные из векторной БД"""
    print("Подключение к векторной БД...")
    client = chromadb.PersistentClient(
        path=str(VECTOR_DB_DIR),
        settings=Settings(anonymized_telemetry=False)
    )
    
    collection = client.get_collection("documents")
    
    # Получаем все данные
    print("Загрузка данных из БД...")
    results = collection.get(include=['documents', 'metadatas'])
    
    return results


def calculate_statistics(results):
    """Вычисляет статистику по векторной БД"""
    print("Вычисление статистики...")
    
    documents = results['documents']
    metadatas = results['metadatas']
    
    # Общая статистика
    total_chunks = len(documents)
    
    # Статистика по токенам и символам
    token_counts = []
    char_counts = []
    sources = []
    types = []
    filenames = []
    section_titles = []
    chunks_per_doc = defaultdict(int)
    tokens_per_doc = defaultdict(int)
    
    for i, metadata in enumerate(metadatas):
        token_count = metadata.get('token_count', 0)
        if isinstance(token_count, str):
            try:
                token_count = int(token_count)
            except:
                token_count = 0
        
        char_count = metadata.get('char_end', 0) - metadata.get('char_start', 0)
        if isinstance(char_count, str):
            try:
                char_count = int(char_count)
            except:
                char_count = len(documents[i])
        
        token_counts.append(token_count)
        char_counts.append(char_count)
        
        source = metadata.get('source', 'unknown')
        sources.append(source)
        
        doc_type = metadata.get('type', 'unknown')
        types.append(doc_type)
        
        filename = metadata.get('filename', 'unknown')
        filenames.append(filename)
        chunks_per_doc[filename] += 1
        tokens_per_doc[filename] += token_count
        
        section_title = metadata.get('section_title', '')
        section_titles.append(section_title if section_title else None)
    
    # Уникальные документы
    unique_documents = len(set(filenames))
    
    # Статистика по источникам
    source_stats = Counter(sources)
    source_token_avg = defaultdict(list)
    for i, source in enumerate(sources):
        source_token_avg[source].append(token_counts[i])
    
    # Статистика по типам
    type_stats = Counter(types)
    type_token_avg = defaultdict(list)
    for i, doc_type in enumerate(types):
        type_token_avg[doc_type].append(token_counts[i])
    
    # Статистика по заголовкам
    chunks_with_titles = sum(1 for title in section_titles if title)
    chunks_without_titles = total_chunks - chunks_with_titles
    top_titles = Counter([t for t in section_titles if t]).most_common(20)
    
    # Распределение по размерам
    size_ranges = {
        '0-100': 0,
        '100-200': 0,
        '200-300': 0,
        '300-400': 0,
        '400-512': 0,
        '>512': 0
    }
    
    for tokens in token_counts:
        if tokens <= 100:
            size_ranges['0-100'] += 1
        elif tokens <= 200:
            size_ranges['100-200'] += 1
        elif tokens <= 300:
            size_ranges['200-300'] += 1
        elif tokens <= 400:
            size_ranges['300-400'] += 1
        elif tokens <= 512:
            size_ranges['400-512'] += 1
        else:
            size_ranges['>512'] += 1
    
    # Топ документы
    top_docs_by_chunks = sorted(chunks_per_doc.items(), key=lambda x: x[1], reverse=True)[:10]
    top_docs_by_tokens = sorted(tokens_per_doc.items(), key=lambda x: x[1], reverse=True)[:10]
    
    stats = {
        'total_chunks': total_chunks,
        'unique_documents': unique_documents,
        'total_tokens': sum(token_counts),
        'total_chars': sum(char_counts),
        'token_stats': {
            'mean': statistics.mean(token_counts) if token_counts else 0,
            'median': statistics.median(token_counts) if token_counts else 0,
            'min': min(token_counts) if token_counts else 0,
            'max': max(token_counts) if token_counts else 0,
            'std': statistics.stdev(token_counts) if len(token_counts) > 1 else 0
        },
        'char_stats': {
            'mean': statistics.mean(char_counts) if char_counts else 0,
            'median': statistics.median(char_counts) if char_counts else 0,
            'min': min(char_counts) if char_counts else 0,
            'max': max(char_counts) if char_counts else 0
        },
        'source_stats': dict(source_stats),
        'source_token_avg': {k: statistics.mean(v) for k, v in source_token_avg.items()},
        'type_stats': dict(type_stats),
        'type_token_avg': {k: statistics.mean(v) for k, v in type_token_avg.items()},
        'size_distribution': size_ranges,
        'chunks_with_titles': chunks_with_titles,
        'chunks_without_titles': chunks_without_titles,
        'top_titles': top_titles,
        'avg_chunks_per_doc': statistics.mean(list(chunks_per_doc.values())) if chunks_per_doc else 0,
        'median_chunks_per_doc': statistics.median(list(chunks_per_doc.values())) if chunks_per_doc else 0,
        'top_docs_by_chunks': top_docs_by_chunks,
        'top_docs_by_tokens': top_docs_by_tokens,
        'embedding_dimension': 3072  # text-embedding-3-large
    }
    
    return stats, token_counts, sources, types, filenames, chunks_per_doc


def save_text_report(stats, output_file):
    """Сохраняет текстовый отчет"""
    print(f"Сохранение текстового отчета в {output_file}...")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("СТАТИСТИКА ВЕКТОРНОЙ БАЗЫ ДАННЫХ\n")
        f.write("=" * 80 + "\n")
        f.write(f"Дата создания отчета: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        # Общая статистика
        f.write("ОБЩАЯ СТАТИСТИКА\n")
        f.write("-" * 80 + "\n")
        f.write(f"Общее количество чанков: {stats['total_chunks']:,}\n")
        f.write(f"Уникальных документов: {stats['unique_documents']:,}\n")
        f.write(f"Общее количество токенов: {stats['total_tokens']:,}\n")
        f.write(f"Общее количество символов: {stats['total_chars']:,}\n")
        f.write(f"Размерность эмбеддингов: {stats['embedding_dimension']}\n")
        f.write(f"\n")
        
        # Статистика по токенам
        f.write("СТАТИСТИКА ПО РАЗМЕРАМ ЧАНКОВ (ТОКЕНЫ)\n")
        f.write("-" * 80 + "\n")
        f.write(f"Средний размер: {stats['token_stats']['mean']:.2f} токенов\n")
        f.write(f"Медианный размер: {stats['token_stats']['median']:.2f} токенов\n")
        f.write(f"Минимальный размер: {stats['token_stats']['min']} токенов\n")
        f.write(f"Максимальный размер: {stats['token_stats']['max']} токенов\n")
        f.write(f"Стандартное отклонение: {stats['token_stats']['std']:.2f}\n")
        f.write(f"\n")
        
        # Статистика по символам
        f.write("СТАТИСТИКА ПО РАЗМЕРАМ ЧАНКОВ (СИМВОЛЫ)\n")
        f.write("-" * 80 + "\n")
        f.write(f"Средний размер: {stats['char_stats']['mean']:.2f} символов\n")
        f.write(f"Медианный размер: {stats['char_stats']['median']:.2f} символов\n")
        f.write(f"Минимальный размер: {stats['char_stats']['min']} символов\n")
        f.write(f"Максимальный размер: {stats['char_stats']['max']} символов\n")
        f.write(f"\n")
        
        # Статистика по источникам
        f.write("СТАТИСТИКА ПО ИСТОЧНИКАМ\n")
        f.write("-" * 80 + "\n")
        total = sum(stats['source_stats'].values())
        for source, count in sorted(stats['source_stats'].items(), key=lambda x: x[1], reverse=True):
            percentage = (count / total * 100) if total > 0 else 0
            avg_tokens = stats['source_token_avg'].get(source, 0)
            f.write(f"{source:15} | Чанков: {count:6,} ({percentage:5.2f}%) | "
                   f"Средний размер: {avg_tokens:.2f} токенов\n")
        f.write(f"\n")
        
        # Статистика по типам
        f.write("СТАТИСТИКА ПО ТИПАМ ДОКУМЕНТОВ\n")
        f.write("-" * 80 + "\n")
        total = sum(stats['type_stats'].values())
        for doc_type, count in sorted(stats['type_stats'].items(), key=lambda x: x[1], reverse=True):
            percentage = (count / total * 100) if total > 0 else 0
            avg_tokens = stats['type_token_avg'].get(doc_type, 0)
            f.write(f"{doc_type:15} | Чанков: {count:6,} ({percentage:5.2f}%) | "
                   f"Средний размер: {avg_tokens:.2f} токенов\n")
        f.write(f"\n")
        
        # Распределение по размерам
        f.write("РАСПРЕДЕЛЕНИЕ ПО РАЗМЕРАМ ЧАНКОВ\n")
        f.write("-" * 80 + "\n")
        total = sum(stats['size_distribution'].values())
        for size_range, count in stats['size_distribution'].items():
            percentage = (count / total * 100) if total > 0 else 0
            f.write(f"{size_range:10} токенов: {count:6,} чанков ({percentage:5.2f}%)\n")
        f.write(f"\n")
        
        # Статистика по документам
        f.write("СТАТИСТИКА ПО ДОКУМЕНТАМ\n")
        f.write("-" * 80 + "\n")
        f.write(f"Среднее количество чанков на документ: {stats['avg_chunks_per_doc']:.2f}\n")
        f.write(f"Медианное количество чанков на документ: {stats['median_chunks_per_doc']:.2f}\n")
        f.write(f"\n")
        
        # Топ документы по чанкам
        f.write("ТОП-10 ДОКУМЕНТОВ ПО КОЛИЧЕСТВУ ЧАНКОВ\n")
        f.write("-" * 80 + "\n")
        for i, (filename, count) in enumerate(stats['top_docs_by_chunks'], 1):
            f.write(f"{i:2}. {filename[:60]:60} | {count:4} чанков\n")
        f.write(f"\n")
        
        # Топ документы по токенам
        f.write("ТОП-10 ДОКУМЕНТОВ ПО КОЛИЧЕСТВУ ТОКЕНОВ\n")
        f.write("-" * 80 + "\n")
        for i, (filename, tokens) in enumerate(stats['top_docs_by_tokens'], 1):
            f.write(f"{i:2}. {filename[:60]:60} | {tokens:8,} токенов\n")
        f.write(f"\n")
        
        # Статистика по заголовкам
        f.write("СТАТИСТИКА ПО ЗАГОЛОВКАМ РАЗДЕЛОВ\n")
        f.write("-" * 80 + "\n")
        f.write(f"Чанков с заголовками: {stats['chunks_with_titles']:,} "
               f"({stats['chunks_with_titles']/stats['total_chunks']*100:.2f}%)\n")
        f.write(f"Чанков без заголовков: {stats['chunks_without_titles']:,} "
               f"({stats['chunks_without_titles']/stats['total_chunks']*100:.2f}%)\n")
        f.write(f"\n")
        f.write("ТОП-20 НАИБОЛЕЕ ЧАСТЫХ ЗАГОЛОВКОВ\n")
        f.write("-" * 80 + "\n")
        for i, (title, count) in enumerate(stats['top_titles'], 1):
            f.write(f"{i:2}. {title[:70]:70} | {count:4} раз\n")
        f.write(f"\n")
        
        f.write("=" * 80 + "\n")
        f.write("Конец отчета\n")
        f.write("=" * 80 + "\n")


def create_visualizations(stats, token_counts, sources, types, filenames, chunks_per_doc):
    """Создает визуализации"""
    print("Создание визуализаций...")
    
    # 1. Распределение по источникам (круговая диаграмма)
    fig, ax = plt.subplots(figsize=(10, 8))
    source_counts = list(stats['source_stats'].values())
    source_labels = list(stats['source_stats'].keys())
    colors = sns.color_palette("husl", len(source_labels))
    ax.pie(source_counts, labels=source_labels, autopct='%1.1f%%', startangle=90, colors=colors)
    ax.set_title('Распределение чанков по источникам', fontsize=16, fontweight='bold')
    plt.tight_layout()
    plt.savefig(STATS_DIR / 'distribution_by_source_pie.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    # 2. Количество чанков по источникам (столбчатая диаграмма)
    fig, ax = plt.subplots(figsize=(12, 6))
    source_data = sorted(stats['source_stats'].items(), key=lambda x: x[1], reverse=True)
    sources_list = [s[0] for s in source_data]
    counts_list = [s[1] for s in source_data]
    bars = ax.bar(sources_list, counts_list, color=sns.color_palette("husl", len(sources_list)))
    ax.set_xlabel('Источник', fontsize=12)
    ax.set_ylabel('Количество чанков', fontsize=12)
    ax.set_title('Количество чанков по источникам', fontsize=16, fontweight='bold')
    ax.tick_params(axis='x', rotation=45)
    # Добавляем значения на столбцы
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{int(height):,}',
                ha='center', va='bottom', fontsize=9)
    plt.tight_layout()
    plt.savefig(STATS_DIR / 'chunks_by_source_bar.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    # 3. Распределение размеров чанков (гистограмма)
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.hist(token_counts, bins=50, color='skyblue', edgecolor='black', alpha=0.7)
    ax.axvline(stats['token_stats']['mean'], color='red', linestyle='--', linewidth=2, label=f'Среднее: {stats["token_stats"]["mean"]:.1f}')
    ax.axvline(stats['token_stats']['median'], color='green', linestyle='--', linewidth=2, label=f'Медиана: {stats["token_stats"]["median"]:.1f}')
    ax.set_xlabel('Количество токенов', fontsize=12)
    ax.set_ylabel('Количество чанков', fontsize=12)
    ax.set_title('Распределение размеров чанков (в токенах)', fontsize=16, fontweight='bold')
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(STATS_DIR / 'chunk_size_distribution.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    # 4. Распределение по диапазонам размеров
    fig, ax = plt.subplots(figsize=(12, 6))
    size_ranges = list(stats['size_distribution'].keys())
    size_counts = list(stats['size_distribution'].values())
    bars = ax.bar(size_ranges, size_counts, color=sns.color_palette("viridis", len(size_ranges)))
    ax.set_xlabel('Диапазон токенов', fontsize=12)
    ax.set_ylabel('Количество чанков', fontsize=12)
    ax.set_title('Распределение чанков по диапазонам размеров', fontsize=16, fontweight='bold')
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{int(height):,}',
                ha='center', va='bottom', fontsize=9)
    plt.tight_layout()
    plt.savefig(STATS_DIR / 'size_ranges_distribution.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    # 5. Топ-10 документов по количеству чанков
    fig, ax = plt.subplots(figsize=(14, 8))
    top_docs = stats['top_docs_by_chunks'][:10]
    doc_names = [d[0][:50] + '...' if len(d[0]) > 50 else d[0] for d in top_docs]
    doc_counts = [d[1] for d in top_docs]
    bars = ax.barh(doc_names, doc_counts, color=sns.color_palette("coolwarm", len(doc_names)))
    ax.set_xlabel('Количество чанков', fontsize=12)
    ax.set_ylabel('Документ', fontsize=12)
    ax.set_title('Топ-10 документов по количеству чанков', fontsize=16, fontweight='bold')
    for i, (bar, count) in enumerate(zip(bars, doc_counts)):
        ax.text(count, bar.get_y() + bar.get_height()/2,
                f' {count}',
                ha='left', va='center', fontsize=9)
    plt.tight_layout()
    plt.savefig(STATS_DIR / 'top_docs_by_chunks.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    # 6. Box plot: распределение размеров по источникам
    fig, ax = plt.subplots(figsize=(14, 8))
    source_token_data = defaultdict(list)
    for i, source in enumerate(sources):
        source_token_data[source].append(token_counts[i])
    
    data_for_box = [source_token_data[source] for source in sorted(source_token_data.keys())]
    labels = sorted(source_token_data.keys())
    
    bp = ax.boxplot(data_for_box, labels=labels, patch_artist=True)
    colors = sns.color_palette("Set2", len(labels))
    for patch, color in zip(bp['boxes'], colors):
        patch.set_facecolor(color)
    
    ax.set_xlabel('Источник', fontsize=12)
    ax.set_ylabel('Количество токенов', fontsize=12)
    ax.set_title('Распределение размеров чанков по источникам', fontsize=16, fontweight='bold')
    ax.tick_params(axis='x', rotation=45)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(STATS_DIR / 'chunk_size_by_source_boxplot.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    # 7. Статистика по типам документов
    fig, ax = plt.subplots(figsize=(10, 6))
    type_data = sorted(stats['type_stats'].items(), key=lambda x: x[1], reverse=True)
    types_list = [t[0] for t in type_data]
    counts_list = [t[1] for t in type_data]
    bars = ax.bar(types_list, counts_list, color=sns.color_palette("pastel", len(types_list)))
    ax.set_xlabel('Тип документа', fontsize=12)
    ax.set_ylabel('Количество чанков', fontsize=12)
    ax.set_title('Распределение чанков по типам документов', fontsize=16, fontweight='bold')
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{int(height):,}',
                ha='center', va='bottom', fontsize=10)
    plt.tight_layout()
    plt.savefig(STATS_DIR / 'chunks_by_type.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"Визуализации сохранены в {STATS_DIR}")


def main():
    """Основная функция"""
    print("=" * 80)
    print("АНАЛИЗ ВЕКТОРНОЙ БАЗЫ ДАННЫХ")
    print("=" * 80)
    print()
    
    # Загружаем данные
    results = load_vector_db()
    
    # Вычисляем статистику
    stats, token_counts, sources, types, filenames, chunks_per_doc = calculate_statistics(results)
    
    # Сохраняем текстовый отчет
    output_file = STATS_DIR / "vector_db_statistics.txt"
    save_text_report(stats, output_file)
    print(f"✅ Текстовый отчет сохранен: {output_file}")
    
    # Создаем визуализации
    create_visualizations(stats, token_counts, sources, types, filenames, chunks_per_doc)
    print(f"✅ Визуализации сохранены в: {STATS_DIR}")
    
    print()
    print("=" * 80)
    print("АНАЛИЗ ЗАВЕРШЕН")
    print("=" * 80)
    print(f"\nКраткая статистика:")
    print(f"  - Всего чанков: {stats['total_chunks']:,}")
    print(f"  - Уникальных документов: {stats['unique_documents']:,}")
    print(f"  - Всего токенов: {stats['total_tokens']:,}")
    print(f"  - Средний размер чанка: {stats['token_stats']['mean']:.2f} токенов")
    print(f"\nФайлы сохранены в: {STATS_DIR}")


if __name__ == "__main__":
    main()

