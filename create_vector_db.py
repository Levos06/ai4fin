#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для создания векторной базы данных из документов
с использованием семантического чанкования
"""
import csv
import re
from pathlib import Path
from typing import List, Dict, Any
from tqdm import tqdm
import tiktoken

try:
    from langchain_core.documents import Document
except ImportError:
    from langchain.schema import Document

from langchain_experimental.text_splitter import SemanticChunker
from langchain_text_splitters import RecursiveCharacterTextSplitter
import chromadb
from chromadb.config import Settings

from config import (
    DOCUMENTS_DIR, METADATA_CSV, VECTOR_DB_DIR,
    OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_BASE_URL,
    CHUNK_SIZE_TOKENS, CHUNK_OVERLAP_SENTENCES, BATCH_SIZE
)
from openrouter_embeddings import OpenRouterEmbeddings


def load_metadata() -> Dict[str, Dict[str, str]]:
    """
    Загружает метаданные из CSV файла
    
    Returns:
        Словарь {имя_файла: метаданные}
    """
    metadata_dict = {}
    
    with open(METADATA_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            filename = row['Имя файла']
            metadata_dict[filename] = {
                'url': row.get('URL', ''),
                'title': row.get('Название', ''),
                'type': row.get('Тип', ''),
                'source': row.get('Источник', ''),
                'filename': filename
            }
    
    return metadata_dict


def count_tokens(text: str, model: str = "gpt-4") -> int:
    """Подсчет токенов в тексте"""
    encoding = tiktoken.encoding_for_model(model)
    return len(encoding.encode(text))


def split_text_by_tokens(text: str, max_tokens: int = CHUNK_SIZE_TOKENS) -> List[str]:
    """
    Разбивает текст на части с учетом ограничения по токенам
    
    Args:
        text: Текст для разбиения
        max_tokens: Максимальное количество токенов в чанке
        
    Returns:
        Список текстовых чанков
    """
    encoding = tiktoken.encoding_for_model("gpt-4")
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    chunks = []
    current_chunk = []
    current_tokens = 0
    
    for sentence in sentences:
        sentence_tokens = len(encoding.encode(sentence))
        
        if current_tokens + sentence_tokens > max_tokens and current_chunk:
            # Сохраняем текущий чанк
            chunks.append(' '.join(current_chunk))
            current_chunk = [sentence]
            current_tokens = sentence_tokens
        else:
            current_chunk.append(sentence)
            current_tokens += sentence_tokens
    
    if current_chunk:
        chunks.append(' '.join(current_chunk))
    
    return chunks


def clean_text(text: str) -> str:
    """Очистка текста от лишних символов и форматирования"""
    # Удаляем множественные пробелы
    text = re.sub(r'\s+', ' ', text)
    # Удаляем множественные переносы строк
    text = re.sub(r'\n\s*\n', '\n\n', text)
    # Удаляем лишние пробелы в начале и конце
    text = text.strip()
    return text


def extract_section_title(text: str, position: int) -> str:
    """
    Извлекает заголовок раздела для чанка
    
    Args:
        text: Полный текст документа
        position: Позиция начала чанка в тексте
        
    Returns:
        Заголовок раздела или пустая строка
    """
    # Ищем заголовки в формате ВСЕ ЗАГЛАВНЫЕ БУКВЫ или с разделителями
    before_text = text[:position]
    lines = before_text.split('\n')
    
    # Ищем последний заголовок (строки в верхнем регистре или с разделителями)
    for line in reversed(lines[-10:]):  # Проверяем последние 10 строк
        line = line.strip()
        if not line:
            continue
        # Проверяем, является ли строка заголовком
        if (line.isupper() and len(line) > 3) or '---' in line or '===' in line:
            # Очищаем от разделителей
            title = re.sub(r'[-=]+', '', line).strip()
            if title and len(title) > 3:
                return title
    
    return ""


def process_document(
    filepath: Path,
    metadata: Dict[str, str],
    embeddings: OpenRouterEmbeddings,
    semantic_chunker: SemanticChunker
) -> List[Dict[str, Any]]:
    """
    Обрабатывает один документ: загружает, чанкует и создает эмбеддинги
    
    Args:
        filepath: Путь к файлу
        metadata: Метаданные документа
        embeddings: Объект для генерации эмбеддингов
        semantic_chunker: Семантический чанкер
        
    Returns:
        Список словарей с чанками и метаданными
    """
    # Загружаем текст
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            text = f.read()
    except Exception as e:
        print(f"Ошибка при чтении файла {filepath}: {e}")
        return []
    
    # Очищаем текст
    text = clean_text(text)
    
    if not text or len(text.strip()) < 50:
        return []
    
    # Создаем Document для langchain
    doc = Document(
        page_content=text,
        metadata=metadata
    )
    
    # Применяем семантическое чанкование
    try:
        chunks = semantic_chunker.split_documents([doc])
    except Exception as e:
        print(f"Ошибка при чанковании {filepath}: {e}")
        # Fallback на обычное разбиение
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE_TOKENS * 4,  # Примерно 4 символа на токен
            chunk_overlap=CHUNK_OVERLAP_SENTENCES * 50,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        chunks = text_splitter.split_documents([doc])
    
    # Обрабатываем чанки с ограничением по токенам
    processed_chunks = []
    char_position = 0
    
    for chunk_idx, chunk in enumerate(chunks):
        chunk_text = chunk.page_content.strip()
        
        if not chunk_text or len(chunk_text) < 20:
            continue
        
        # Проверяем размер в токенах
        token_count = count_tokens(chunk_text)
        
        if token_count > CHUNK_SIZE_TOKENS:
            # Разбиваем на более мелкие части по предложениям
            sub_chunks = split_text_by_tokens(chunk_text, CHUNK_SIZE_TOKENS)
        else:
            sub_chunks = [chunk_text]
        
        # Обрабатываем каждый подчанк
        for sub_idx, sub_chunk in enumerate(sub_chunks):
            sub_chunk = clean_text(sub_chunk)
            if not sub_chunk or len(sub_chunk.strip()) < 20:
                continue
            
            # Проверяем размер еще раз после очистки
            final_token_count = count_tokens(sub_chunk)
            if final_token_count > CHUNK_SIZE_TOKENS:
                # Если все еще слишком большой, разбиваем еще раз
                smaller_chunks = split_text_by_tokens(sub_chunk, CHUNK_SIZE_TOKENS)
                for small_idx, small_chunk in enumerate(smaller_chunks):
                    small_chunk = clean_text(small_chunk)
                    if not small_chunk or len(small_chunk.strip()) < 20:
                        continue
                    
                    # Находим позицию в исходном тексте
                    chunk_start = text.find(small_chunk[:50], char_position)
                    if chunk_start == -1:
                        chunk_start = char_position
                    
                    # Извлекаем заголовок раздела
                    section_title = extract_section_title(text, chunk_start)
                    
                    # Создаем метаданные для чанка
                    chunk_metadata = {
                        **metadata,
                        'chunk_index': chunk_idx,
                        'sub_chunk_index': f"{sub_idx}_{small_idx}",
                        'total_chunks': len(chunks),
                        'section_title': section_title,
                        'char_start': chunk_start,
                        'char_end': chunk_start + len(small_chunk),
                        'token_count': count_tokens(small_chunk)
                    }
                    
                    processed_chunks.append({
                        'text': small_chunk,
                        'metadata': chunk_metadata
                    })
                    
                    char_position = chunk_start + len(small_chunk)
            else:
                # Находим позицию в исходном тексте
                chunk_start = text.find(sub_chunk[:50], char_position)
                if chunk_start == -1:
                    chunk_start = char_position
                
                # Извлекаем заголовок раздела
                section_title = extract_section_title(text, chunk_start)
                
                # Создаем метаданные для чанка
                chunk_metadata = {
                    **metadata,
                    'chunk_index': chunk_idx,
                    'sub_chunk_index': sub_idx,
                    'total_chunks': len(chunks),
                    'section_title': section_title,
                    'char_start': chunk_start,
                    'char_end': chunk_start + len(sub_chunk),
                    'token_count': final_token_count
                }
                
                processed_chunks.append({
                    'text': sub_chunk,
                    'metadata': chunk_metadata
                })
                
                char_position = chunk_start + len(sub_chunk)
    
    return processed_chunks


def create_vector_database():
    """Создает векторную базу данных из всех документов"""
    
    print("Инициализация компонентов...")
    
    # Инициализируем эмбеддинги
    embeddings = OpenRouterEmbeddings(
        api_key=OPENROUTER_API_KEY,
        model=OPENROUTER_MODEL,
        base_url=OPENROUTER_BASE_URL,
        batch_size=BATCH_SIZE
    )
    
    # Инициализируем семантический чанкер
    semantic_chunker = SemanticChunker(
        embeddings=embeddings,
        buffer_size=CHUNK_OVERLAP_SENTENCES,
        breakpoint_threshold_type="percentile"
    )
    
    # Загружаем метаданные
    print("Загрузка метаданных...")
    metadata_dict = load_metadata()
    
    # Инициализируем Chroma
    print("Инициализация Chroma DB...")
    client = chromadb.PersistentClient(
        path=str(VECTOR_DB_DIR),
        settings=Settings(anonymized_telemetry=False)
    )
    
    # Создаем или получаем коллекцию
    collection = client.get_or_create_collection(
        name="documents",
        metadata={"description": "Knowledge base documents"}
    )
    
    # Получаем список всех txt файлов
    txt_files = list(DOCUMENTS_DIR.glob("*.txt"))
    print(f"Найдено {len(txt_files)} документов для обработки")
    
    # Обрабатываем документы
    all_chunks = []
    failed_files = []
    
    for filepath in tqdm(txt_files, desc="Обработка документов"):
        filename = filepath.name
        
        # Получаем метаданные
        doc_metadata = metadata_dict.get(filename, {
            'url': '',
            'title': filename.replace('.txt', ''),
            'type': 'статья',
            'source': 'unknown',
            'filename': filename
        })
        
        # Обрабатываем документ
        try:
            chunks = process_document(
                filepath,
                doc_metadata,
                embeddings,
                semantic_chunker
            )
            all_chunks.extend(chunks)
        except Exception as e:
            print(f"\nОшибка при обработке {filename}: {e}")
            failed_files.append(filename)
    
    print(f"\nОбработано чанков: {len(all_chunks)}")
    if failed_files:
        print(f"Не удалось обработать файлов: {len(failed_files)}")
        print(f"Список: {failed_files}")
    
    # Генерируем эмбеддинги батчами
    print("\nГенерация эмбеддингов...")
    texts = [chunk['text'] for chunk in all_chunks]
    
    # Генерируем эмбеддинги батчами
    all_embeddings = []
    for i in tqdm(range(0, len(texts), BATCH_SIZE), desc="Генерация эмбеддингов"):
        batch_texts = texts[i:i + BATCH_SIZE]
        batch_embeddings = embeddings.embed_documents(batch_texts)
        all_embeddings.extend(batch_embeddings)
    
    # Подготавливаем данные для Chroma
    print("\nСохранение в векторную БД...")
    ids = [f"chunk_{i}" for i in range(len(all_chunks))]
    documents = [chunk['text'] for chunk in all_chunks]
    metadatas = [chunk['metadata'] for chunk in all_chunks]
    
    # Добавляем в коллекцию батчами
    batch_size = 100
    for i in tqdm(range(0, len(ids), batch_size), desc="Сохранение в Chroma"):
        batch_ids = ids[i:i + batch_size]
        batch_docs = documents[i:i + batch_size]
        batch_embeddings = all_embeddings[i:i + batch_size]
        batch_metadatas = metadatas[i:i + batch_size]
        
        collection.add(
            ids=batch_ids,
            documents=batch_docs,
            embeddings=batch_embeddings,
            metadatas=batch_metadatas
        )
    
    print(f"\n✅ Векторная база данных создана!")
    print(f"📊 Статистика:")
    print(f"   - Документов обработано: {len(txt_files)}")
    print(f"   - Чанков создано: {len(all_chunks)}")
    print(f"   - Векторная БД сохранена в: {VECTOR_DB_DIR}")
    print(f"   - Коллекция: documents")
    
    # Выводим статистику по источникам
    source_stats = {}
    for chunk in all_chunks:
        source = chunk['metadata'].get('source', 'unknown')
        source_stats[source] = source_stats.get(source, 0) + 1
    
    print(f"\n📈 Статистика по источникам:")
    for source, count in sorted(source_stats.items(), key=lambda x: x[1], reverse=True):
        print(f"   - {source}: {count} чанков")


if __name__ == "__main__":
    create_vector_database()

