#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Агент на базе LLM с семью инструментами:
1. Запрос котировок акций (yfinance) - для американских и зарубежных акций
2. Запрос котировок российских акций (MOEX API) - для российских акций
3. Получение финансовых мультипликаторов (P/E, P/B, EV/EBITDA, ROE, ROA и т.д.)
4. Получение финансовой отчетности (баланс, отчет о прибылях, денежные потоки)
5. Поиск в векторной базе знаний (ChromaDB)
6. Поиск в интернете (Tavily)
7. Создание интерактивных визуализаций (Plotly) - графики, диаграммы, визуализации
"""
import json
import logging
import re
import hashlib
import base64
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List
import sys

import yfinance as yf
import chromadb
from chromadb.config import Settings
from tavily import TavilyClient
import requests
import xml.etree.ElementTree as ET
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.offline import plot
from langchain_classic.agents import AgentExecutor
from langchain_classic.agents.react.agent import create_react_agent
from langchain_core.tools import StructuredTool
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from langchain_classic.memory import ConversationBufferMemory

from config import (
    VECTOR_DB_DIR, OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_BASE_URL,
    AGENT_LLM_MODEL, AGENT_MAX_ITERATIONS, AGENT_VERBOSE,
    TAVILY_API_KEY, TAVILY_SEARCH_DEPTH, TAVILY_MAX_RESULTS,
    STOCK_QUOTES_DEFAULT_PERIOD_DAYS, VECTOR_DB_DEFAULT_RESULTS,
    LOG_DIR, FINANCIAL_REPORTS_DIR, CHARTS_CACHE_DIR
)
from openrouter_embeddings import OpenRouterEmbeddings


# Настройка логирования
def setup_logging():
    """Настройка логирования действий агента"""
    log_file = LOG_DIR / f"agent_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    return logging.getLogger(__name__)


logger = setup_logging()


# ============================================================================
# ИНСТРУМЕНТЫ
# ============================================================================

def get_stock_quotes(
    ticker: str,
    period_days: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> str:
    """
    Получает котировки акций через yfinance.
    
    Args:
        ticker: Тикер акции (например, 'AAPL', 'GAZP.ME' для российских)
        period_days: Количество дней назад (по умолчанию из config)
        start_date: Начальная дата в формате 'YYYY-MM-DD' (опционально)
        end_date: Конечная дата в формате 'YYYY-MM-DD' (опционально)
    
    Returns:
        Словарь с данными о котировках
    """
    try:
        # Парсим параметры, если они пришли как JSON строка
        if ticker.startswith('{') or ticker.startswith('['):
            try:
                parsed = json.loads(ticker)
                if isinstance(parsed, dict):
                    # Извлекаем все параметры из JSON
                    ticker = parsed.get('ticker', ticker)
                    if 'period_days' in parsed and period_days is None:
                        period_days = parsed.get('period_days')
                    if 'start_date' in parsed and start_date is None:
                        start_date = parsed.get('start_date')
                    if 'end_date' in parsed and end_date is None:
                        end_date = parsed.get('end_date')
                elif isinstance(parsed, str):
                    ticker = parsed
            except:
                pass
        
        # Конвертируем period_days в int, если он строка
        if period_days is not None:
            try:
                period_days = int(period_days)
            except (ValueError, TypeError):
                period_days = None
        
        logger.info(f"Запрос котировок для {ticker}, period_days={period_days}, start_date={start_date}, end_date={end_date}")
        
        # Определяем период
        if start_date and end_date:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
        elif period_days:
            end = datetime.now()
            start = end - timedelta(days=period_days)
        else:
            end = datetime.now()
            start = end - timedelta(days=STOCK_QUOTES_DEFAULT_PERIOD_DAYS)
        
        logger.info(f"Период запроса: {start.strftime('%Y-%m-%d')} - {end.strftime('%Y-%m-%d')} ({period_days or STOCK_QUOTES_DEFAULT_PERIOD_DAYS} дней)")
        
        # Загружаем данные
        stock = yf.Ticker(ticker)
        hist = stock.history(start=start, end=end)
        
        if hist.empty:
            # Для российских акций (.ME) yfinance часто не работает из-за санкций
            # Возвращаем специальную ошибку, чтобы агент мог использовать веб-поиск
            is_russian = ticker.endswith('.ME')
            error_msg = (
                f"Не удалось получить данные для {ticker}. "
                f"{'Для российских акций yfinance может не работать - рекомендуется использовать веб-поиск.' if is_russian else ''}"
            )
            error_result = {
                "success": False,
                "error": error_msg,
                "ticker": ticker,
                "is_russian": is_russian,
                "suggestion": "use_web_search" if is_russian else None
            }
            return json.dumps(error_result, ensure_ascii=False)
        
        # Получаем текущую информацию
        try:
            info = stock.info
        except:
            info = {}
        
        # Формируем исторические данные для графиков
        historical_data = None
        if not hist.empty:
            # Преобразуем DataFrame в список словарей с датами и ценами
            historical_data = {
                "dates": [date.strftime('%Y-%m-%d') for date in hist.index],
                "open": [float(x) for x in hist['Open'].tolist()],
                "high": [float(x) for x in hist['High'].tolist()],
                "low": [float(x) for x in hist['Low'].tolist()],
                "close": [float(x) for x in hist['Close'].tolist()],
                "volume": [int(x) for x in hist['Volume'].tolist()]
            }
        
        # Формируем результат
        result = {
            "success": True,
            "ticker": ticker,
            "company_name": info.get('longName', ticker),
            "currency": info.get('currency', 'USD'),
            "period": {
                "start": start.strftime('%Y-%m-%d'),
                "end": end.strftime('%Y-%m-%d')
            },
            "current_price": float(hist['Close'].iloc[-1]) if not hist.empty else None,
            "price_change": float(hist['Close'].iloc[-1] - hist['Close'].iloc[0]) if len(hist) > 1 else None,
            "price_change_percent": float((hist['Close'].iloc[-1] / hist['Close'].iloc[0] - 1) * 100) if len(hist) > 1 else None,
            "high": float(hist['High'].max()) if not hist.empty else None,
            "low": float(hist['Low'].min()) if not hist.empty else None,
            "volume": int(hist['Volume'].sum()) if not hist.empty else None,
            "data_points": len(hist),
            "latest_date": hist.index[-1].strftime('%Y-%m-%d') if not hist.empty else None,
            "historical_data": historical_data,  # Добавляем исторические данные для графиков
            "source": "yfinance"
        }
        
        logger.info(f"Успешно получены котировки для {ticker} ({len(hist)} точек данных)")
        return json.dumps(result, ensure_ascii=False)
        
    except Exception as e:
        error_msg = f"Ошибка при получении котировок для {ticker}: {str(e)}"
        logger.error(error_msg)
        is_russian = ticker.endswith('.ME')
        error_result = {
            "success": False,
            "error": error_msg,
            "ticker": ticker,
            "is_russian": is_russian,
            "suggestion": "use_web_search" if is_russian else None
        }
        return json.dumps(error_result, ensure_ascii=False)


def get_russian_stock_quotes(
    ticker: str,
    board: Optional[str] = None,
    period_days: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> str:
    """
    Получает котировки российских акций через API Московской биржи (MOEX).
    
    Args:
        ticker: Тикер акции на Мосбирже (например, 'SBER', 'GAZP', 'YNDX')
        board: Режим торгов (TQBR для акций, TQTF для ETF, TQTD для долларовых ETF, TQTE для евро ETF)
               По умолчанию определяется автоматически
        period_days: Количество дней назад для получения исторических данных (опционально)
        start_date: Начальная дата в формате 'YYYY-MM-DD' (опционально)
        end_date: Конечная дата в формате 'YYYY-MM-DD' (опционально)
    
    Returns:
        JSON строка с данными о котировках
    """
    try:
        # Парсим параметры, если они пришли как JSON строка
        if ticker.startswith('{') or ticker.startswith('['):
            try:
                parsed = json.loads(ticker)
                if isinstance(parsed, dict):
                    # Извлекаем все параметры из JSON
                    ticker = parsed.get('ticker', ticker)
                    if 'board' in parsed and board is None:
                        board = parsed.get('board')
                    if 'period_days' in parsed and period_days is None:
                        period_days = parsed.get('period_days')
                    if 'start_date' in parsed and start_date is None:
                        start_date = parsed.get('start_date')
                    if 'end_date' in parsed and end_date is None:
                        end_date = parsed.get('end_date')
                elif isinstance(parsed, str):
                    ticker = parsed
            except:
                pass
        
        # Конвертируем period_days в int, если он строка
        if period_days is not None:
            try:
                period_days = int(period_days)
            except (ValueError, TypeError):
                period_days = None
        
        # Убираем .ME если есть (для совместимости)
        ticker = ticker.replace('.ME', '').upper()
        
        logger.info(f"Запрос котировок MOEX для {ticker}, period_days={period_days}, start_date={start_date}, end_date={end_date}")
        
        # Определяем режим торгов, если не указан
        if board is None:
            board = "TQBR"  # По умолчанию для акций
        
        # URL для получения котировок
        url = f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/{board}/securities.xml"
        params = {
            "iss.meta": "off",
            "iss.only": "marketdata",
            "marketdata.columns": "SECID,LAST,OPEN,HIGH,LOW,VOLUME,VALTODAY"
        }
        
        # Получаем данные
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        # Парсим XML
        root = ET.fromstring(response.content)
        
        # Ищем нужный тикер
        last_price = None
        open_price = None
        high_price = None
        low_price = None
        volume = None
        value_today = None
        
        for row in root.findall(".//row[@SECID='{}']".format(ticker)):
            last_price = row.get('LAST')
            open_price = row.get('OPEN')
            high_price = row.get('HIGH')
            low_price = row.get('LOW')
            volume = row.get('VOLUME')
            value_today = row.get('VALTODAY')
            break
        
        if last_price is None:
            # Пробуем получить название компании для проверки
            url_name = f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/{board}/securities.xml"
            params_name = {
                "iss.meta": "off",
                "iss.only": "securities",
                "securities.columns": "SECID,SECNAME"
            }
            
            response_name = requests.get(url_name, params=params_name, timeout=10)
            root_name = ET.fromstring(response_name.content)
            
            company_name = None
            for row in root_name.findall(".//row[@SECID='{}']".format(ticker)):
                company_name = row.get('SECNAME')
                break
            
            error_result = {
                "success": False,
                "error": f"Тикер {ticker} не найден на Мосбирже в режиме {board}",
                "ticker": ticker,
                "board": board,
                "suggestion": "Проверьте правильность тикера или попробуйте другой режим торгов (TQBR, TQTF, TQTD, TQTE)"
            }
            return json.dumps(error_result, ensure_ascii=False)
        
        # Получаем название компании
        url_name = f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/{board}/securities.xml"
        params_name = {
            "iss.meta": "off",
            "iss.only": "securities",
            "securities.columns": "SECID,SECNAME"
        }
        
        company_name = ticker
        try:
            response_name = requests.get(url_name, params=params_name, timeout=10)
            root_name = ET.fromstring(response_name.content)
            for row in root_name.findall(".//row[@SECID='{}']".format(ticker)):
                company_name = row.get('SECNAME', ticker)
                break
        except:
            pass
        
        # Получаем исторические данные
        # ВАЖНО: Для графиков всегда получаем исторические данные, даже если period_days не указан
        # Используем период по умолчанию, если не указан
        historical_data = None
        try:
            # Определяем период для исторических данных
            if start_date and end_date:
                start = datetime.strptime(start_date, '%Y-%m-%d')
                end = datetime.strptime(end_date, '%Y-%m-%d')
            elif period_days:
                end = datetime.now()
                start = end - timedelta(days=period_days)
            else:
                # Если period_days не указан, используем период по умолчанию для получения исторических данных
                end = datetime.now()
                start = end - timedelta(days=30)
                logger.info(f"period_days не указан, используем период по умолчанию: 30 дней")
            
            logger.info(f"Период запроса исторических данных MOEX: {start.strftime('%Y-%m-%d')} - {end.strftime('%Y-%m-%d')} ({period_days or 30} дней)")
            
            # MOEX ISS API для исторических данных
            history_url = f"https://iss.moex.com/iss/history/engines/stock/markets/shares/boards/{board}/securities/{ticker}.xml"
            history_params = {
                "iss.meta": "off",
                "from": start.strftime('%Y-%m-%d'),
                "till": end.strftime('%Y-%m-%d'),
                "history.columns": "TRADEDATE,OPEN,HIGH,LOW,CLOSE,VOLUME"
            }
            
            logger.info(f"Запрос исторических данных MOEX: {history_url} с параметрами {history_params}")
            history_response = requests.get(history_url, params=history_params, timeout=15)
            
            if history_response.status_code == 200:
                history_root = ET.fromstring(history_response.content)
                history_rows = history_root.findall(".//row")
                
                logger.info(f"Получено {len(history_rows)} строк исторических данных от MOEX")
                
                if history_rows:
                    dates = []
                    opens = []
                    highs = []
                    lows = []
                    closes = []
                    volumes = []
                    
                    for row in history_rows:
                        trade_date = row.get('TRADEDATE')
                        if trade_date:
                            dates.append(trade_date)
                            opens.append(float(row.get('OPEN', 0)) if row.get('OPEN') else 0)
                            highs.append(float(row.get('HIGH', 0)) if row.get('HIGH') else 0)
                            lows.append(float(row.get('LOW', 0)) if row.get('LOW') else 0)
                            closes.append(float(row.get('CLOSE', 0)) if row.get('CLOSE') else 0)
                            volumes.append(int(float(row.get('VOLUME', 0))) if row.get('VOLUME') else 0)
                    
                    if dates:
                        historical_data = {
                            "dates": dates,
                            "open": opens,
                            "high": highs,
                            "low": lows,
                            "close": closes,
                            "volume": volumes
                        }
                        logger.info(f"Получено {len(dates)} исторических точек данных для {ticker}")
                    else:
                        logger.warning(f"Не удалось извлечь даты из исторических данных для {ticker}")
                else:
                    logger.warning(f"MOEX вернул пустой ответ для исторических данных {ticker}")
            else:
                logger.warning(f"MOEX вернул статус {history_response.status_code} для исторических данных {ticker}: {history_response.text[:200]}")
        except Exception as e:
            logger.error(f"Ошибка при получении исторических данных для {ticker}: {e}", exc_info=True)
        
        # Формируем результат
        result = {
            "success": True,
            "ticker": ticker,
            "company_name": company_name,
            "currency": "RUB",
            "board": board,
            "current_price": float(last_price) if last_price else None,
            "open_price": float(open_price) if open_price else None,
            "high_price": float(high_price) if high_price else None,
            "low_price": float(low_price) if low_price else None,
            "volume": int(float(volume)) if volume else None,
            "value_today": float(value_today) if value_today else None,
            "historical_data": historical_data,  # Добавляем исторические данные для графиков
            "source": "moex"
        }
        
        logger.info(f"Успешно получены котировки MOEX для {ticker}: {last_price} RUB")
        return json.dumps(result, ensure_ascii=False)
        
    except requests.exceptions.RequestException as e:
        error_msg = f"Ошибка при запросе к MOEX API для {ticker}: {str(e)}"
        logger.error(error_msg)
        error_result = {
            "success": False,
            "error": error_msg,
            "ticker": ticker,
            "board": board
        }
        return json.dumps(error_result, ensure_ascii=False)
    except Exception as e:
        error_msg = f"Ошибка при получении котировок MOEX для {ticker}: {str(e)}"
        logger.error(error_msg)
        error_result = {
            "success": False,
            "error": error_msg,
            "ticker": ticker,
            "board": board
        }
        return json.dumps(error_result, ensure_ascii=False)


def get_financial_metrics(
    ticker: str,
    market: str = "auto"
) -> str:
    """
    Получает финансовые мультипликаторы и метрики компании.
    
    Args:
        ticker: Тикер акции (например, 'AAPL', 'SBER', 'GAZP')
        market: Рынок ('us' для американских, 'ru' для российских, 'auto' для автоматического определения)
    
    Returns:
        JSON строка с финансовыми метриками
    """
    try:
        # Парсим ticker, если он пришел как JSON строка
        if ticker.startswith('{') or ticker.startswith('['):
            try:
                parsed = json.loads(ticker)
                if isinstance(parsed, dict):
                    ticker = parsed.get('ticker', ticker)
                    market = parsed.get('market', market)
                elif isinstance(parsed, str):
                    ticker = parsed
            except:
                pass
        
        # Определяем рынок автоматически
        if market == "auto":
            if ticker.endswith('.ME') or ticker.upper() in ['SBER', 'GAZP', 'YNDX', 'LKOH', 'GMKN', 'NVTK', 'TATN', 'ALRS', 'POLY', 'CHMF']:
                market = "ru"
            else:
                market = "us"
        
        logger.info(f"Запрос финансовых метрик для {ticker} (рынок: {market})")
        
        if market == "ru":
            # Для российских акций используем MOEX API и веб-поиск
            ticker_clean = ticker.replace('.ME', '').upper()
            
            # Получаем базовые данные с MOEX
            url = f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities/{ticker_clean}.xml"
            params = {
                "iss.meta": "off",
                "iss.only": "securities,marketdata"
            }
            
            try:
                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()
                root = ET.fromstring(response.content)
                
                # Извлекаем данные
                marketdata = root.find(".//data[@id='marketdata']")
                securities = root.find(".//data[@id='securities']")
                
                current_price = None
                if marketdata is not None:
                    row = marketdata.find(".//row")
                    if row is not None:
                        current_price = row.get('LAST')
                
                company_name = ticker_clean
                if securities is not None:
                    row = securities.find(".//row")
                    if row is not None:
                        company_name = row.get('SECNAME', ticker_clean)
                
                result = {
                    "success": True,
                    "ticker": ticker_clean,
                    "company_name": company_name,
                    "market": "ru",
                    "currency": "RUB",
                    "current_price": float(current_price) if current_price else None,
                    "source": "moex",
                    "note": "Для полных мультипликаторов используйте веб-поиск или проверьте отчеты компании"
                }
                
                logger.info(f"Успешно получены базовые метрики MOEX для {ticker_clean}")
                return json.dumps(result, ensure_ascii=False)
                
            except Exception as e:
                logger.warning(f"Не удалось получить данные MOEX для {ticker_clean}: {e}")
                # Fallback на веб-поиск
                result = {
                    "success": False,
                    "error": f"Не удалось получить данные MOEX. Рекомендуется использовать веб-поиск для получения мультипликаторов.",
                    "ticker": ticker_clean,
                    "market": "ru",
                    "suggestion": "use_web_search"
                }
                return json.dumps(result, ensure_ascii=False)
        
        else:
            # Для американских и других зарубежных акций используем yfinance
            stock = yf.Ticker(ticker)
            
            try:
                info = stock.info
            except Exception as e:
                logger.error(f"Ошибка при получении info для {ticker}: {e}")
                info = {}
            
            # Извлекаем ключевые мультипликаторы
            metrics = {
                "success": True,
                "ticker": ticker,
                "company_name": info.get('longName', ticker),
                "market": "us",
                "currency": info.get('currency', 'USD'),
                
                # Ценовые мультипликаторы
                "current_price": info.get('currentPrice'),
                "market_cap": info.get('marketCap'),
                "enterprise_value": info.get('enterpriseValue'),
                "pe_ratio": info.get('trailingPE'),
                "forward_pe": info.get('forwardPE'),
                "peg_ratio": info.get('pegRatio'),
                "price_to_book": info.get('priceToBook'),
                "price_to_sales": info.get('priceToSalesTrailing12Months'),
                "ev_to_ebitda": info.get('enterpriseToEbitda'),
                "ev_to_revenue": info.get('enterpriseToRevenue'),
                
                # Прибыльность
                "profit_margin": info.get('profitMargins'),
                "operating_margin": info.get('operatingMargins'),
                "gross_margin": info.get('grossMargins'),
                "ebitda_margin": info.get('ebitdaMargins'),
                
                # Рентабельность
                "roe": info.get('returnOnEquity'),
                "roa": info.get('returnOnAssets'),
                "roic": info.get('returnOnInvestedCapital'),
                
                # Финансовая устойчивость
                "debt_to_equity": info.get('debtToEquity'),
                "current_ratio": info.get('currentRatio'),
                "quick_ratio": info.get('quickRatio'),
                "cash_per_share": info.get('totalCashPerShare'),
                
                # Дивиденды
                "dividend_yield": info.get('dividendYield'),
                "payout_ratio": info.get('payoutRatio'),
                
                # Рост
                "revenue_growth": info.get('revenueGrowth'),
                "earnings_growth": info.get('earningsGrowth'),
                "earnings_quarterly_growth": info.get('earningsQuarterlyGrowth'),
                
                # Прочие
                "beta": info.get('beta'),
                "52_week_high": info.get('fiftyTwoWeekHigh'),
                "52_week_low": info.get('fiftyTwoWeekLow'),
                "shares_outstanding": info.get('sharesOutstanding'),
                "float_shares": info.get('floatShares'),
                
                "source": "yfinance"
            }
            
            logger.info(f"Успешно получены финансовые метрики для {ticker}")
            return json.dumps(metrics, ensure_ascii=False)
            
    except Exception as e:
        error_msg = f"Ошибка при получении финансовых метрик для {ticker}: {str(e)}"
        logger.error(error_msg)
        error_result = {
            "success": False,
            "error": error_msg,
            "ticker": ticker,
            "market": market
        }
        return json.dumps(error_result, ensure_ascii=False)


def _extract_key_metrics(df, metric_names):
    """Извлекает ключевые метрики из DataFrame"""
    if df is None or df.empty:
        return {}
    
    result = {}
    for col in df.columns:
        # Конвертируем Timestamp в строку
        if hasattr(col, 'strftime'):
            col_str = col.strftime('%Y-%m-%d')
        else:
            col_str = str(col)
        
        result[col_str] = {}
        for metric_name in metric_names:
            # Ищем метрику в индексе DataFrame (нечувствительно к регистру и пробелам)
            found = False
            for idx in df.index:
                idx_str = str(idx).strip().lower()
                metric_lower = metric_name.lower().strip()
                if metric_lower in idx_str or idx_str in metric_lower:
                    value = df.loc[idx, col]
                    if pd.notna(value):
                        result[col_str][metric_name] = float(value)
                    found = True
                    break
            if not found:
                result[col_str][metric_name] = None
    
    return result


def get_company_financials(
    ticker: str,
    report_type: str = "annual",
    market: str = "auto"
) -> str:
    """
    Получает финансовую отчетность компании (возвращает только ключевые показатели).
    Полный отчет автоматически сохраняется в файл.
    
    Args:
        ticker: Тикер акции (например, 'AAPL', 'SBER', 'GAZP')
        report_type: Тип отчета ('annual' для годового, 'quarterly' для квартального)
        market: Рынок ('us' для американских, 'ru' для российских, 'auto' для автоматического определения)
    
    Returns:
        JSON строка с ключевыми финансовыми показателями (summary)
    """
    try:
        # Парсим ticker, если он пришел как JSON строка
        if ticker.startswith('{') or ticker.startswith('['):
            try:
                parsed = json.loads(ticker)
                if isinstance(parsed, dict):
                    ticker = parsed.get('ticker', ticker)
                    report_type = parsed.get('report_type', report_type)
                    market = parsed.get('market', market)
                elif isinstance(parsed, str):
                    ticker = parsed
            except:
                pass
        
        # Определяем рынок автоматически
        if market == "auto":
            if ticker.endswith('.ME') or ticker.upper() in ['SBER', 'GAZP', 'YNDX', 'LKOH', 'GMKN', 'NVTK', 'TATN', 'ALRS', 'POLY', 'CHMF']:
                market = "ru"
            else:
                market = "us"
        
        logger.info(f"Запрос финансовой отчетности для {ticker} (тип: {report_type}, рынок: {market})")
        
        if market == "ru":
            # Для российских акций используем веб-поиск для поиска отчетов
            # MOEX API не предоставляет полную финансовую отчетность
            result = {
                "success": False,
                "error": "Прямой доступ к финансовой отчетности российских компаний через API ограничен",
                "ticker": ticker.replace('.ME', '').upper(),
                "market": "ru",
                "report_type": report_type,
                "suggestion": "Используйте веб-поиск для поиска отчетов на сайте компании или MOEX, или используйте search_vector_db для поиска в базе знаний"
            }
            return json.dumps(result, ensure_ascii=False)
        
        else:
            # Для американских акций используем yfinance
            stock = yf.Ticker(ticker)
            
            try:
                # Получаем финансовые данные
                if report_type == "annual":
                    financials = stock.financials  # Годовая отчетность
                    balance_sheet = stock.balance_sheet
                    cashflow = stock.cashflow
                else:
                    financials = stock.quarterly_financials
                    balance_sheet = stock.quarterly_balance_sheet
                    cashflow = stock.quarterly_cashflow
                
                # Функция для преобразования DataFrame в словарь (для полного отчета)
                def df_to_dict(df):
                    if df is None or df.empty:
                        return {}
                    result_dict = {}
                    for col in df.columns:
                        if hasattr(col, 'strftime'):
                            col_str = col.strftime('%Y-%m-%d')
                        else:
                            col_str = str(col)
                        result_dict[col_str] = {}
                        for idx, row in df.iterrows():
                            idx_str = str(idx) if not hasattr(idx, 'strftime') else idx.strftime('%Y-%m-%d')
                            result_dict[col_str][idx_str] = float(row[col]) if pd.notna(row[col]) else None
                    return result_dict
                
                # Получаем последний доступный период
                latest_period = None
                if financials is not None and not financials.empty:
                    latest_period = financials.columns[0].strftime('%Y-%m-%d') if hasattr(financials.columns[0], 'strftime') else str(financials.columns[0])
                
                company_name = stock.info.get('longName', ticker) if hasattr(stock, 'info') else ticker
                currency = stock.info.get('currency', 'USD') if hasattr(stock, 'info') else 'USD'
                
                # Извлекаем ключевые показатели для summary
                income_key_metrics = [
                    "Total Revenue", "Revenue", "Gross Profit", "Operating Income", 
                    "Net Income", "Earnings Per Share", "EBITDA"
                ]
                balance_key_metrics = [
                    "Total Assets", "Total Current Assets", "Total Liabilities",
                    "Total Current Liabilities", "Total Stockholder Equity", 
                    "Cash And Cash Equivalents", "Total Debt"
                ]
                cashflow_key_metrics = [
                    "Operating Cash Flow", "Free Cash Flow", "Capital Expenditure",
                    "Cash Flow From Continuing Operating Activities"
                ]
                
                # Создаем summary с ключевыми показателями
                summary = {
                    "success": True,
                    "ticker": ticker,
                    "company_name": company_name,
                    "market": "us",
                    "report_type": report_type,
                    "latest_period": latest_period,
                    "currency": currency,
                    "summary": True,  # Флаг, что это summary
                    
                    # Ключевые показатели из отчета о прибылях
                    "income_statement_summary": _extract_key_metrics(financials, income_key_metrics),
                    
                    # Ключевые показатели из баланса
                    "balance_sheet_summary": _extract_key_metrics(balance_sheet, balance_key_metrics),
                    
                    # Ключевые показатели из отчета о движении денежных средств
                    "cash_flow_summary": _extract_key_metrics(cashflow, cashflow_key_metrics),
                    
                    "source": "yfinance"
                }
                
                # Сохраняем полный отчет в файл
                full_report = {
                    "success": True,
                    "ticker": ticker,
                    "company_name": company_name,
                    "market": "us",
                    "report_type": report_type,
                    "latest_period": latest_period,
                    "currency": currency,
                    "income_statement": df_to_dict(financials) if financials is not None else {},
                    "balance_sheet": df_to_dict(balance_sheet) if balance_sheet is not None else {},
                    "cash_flow": df_to_dict(cashflow) if cashflow is not None else {},
                    "source": "yfinance",
                    "generated_at": datetime.now().isoformat()
                }
                
                # Сохраняем полный отчет в файл
                report_filename = f"{ticker}_{report_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                report_filepath = FINANCIAL_REPORTS_DIR / report_filename
                
                try:
                    with open(report_filepath, 'w', encoding='utf-8') as f:
                        json.dump(full_report, f, ensure_ascii=False, indent=2, default=str)
                    
                    summary["full_report_file"] = str(report_filepath)
                    summary["note"] = f"Полный отчет сохранен в файл: {report_filepath}"
                    logger.info(f"Полный отчет сохранен в {report_filepath}")
                except Exception as e:
                    logger.error(f"Ошибка при сохранении полного отчета: {e}")
                    summary["note"] = "Не удалось сохранить полный отчет в файл"
                
                logger.info(f"Успешно получена финансовая отчетность (summary) для {ticker}")
                return json.dumps(summary, ensure_ascii=False, default=str)
                
            except Exception as e:
                error_msg = f"Ошибка при получении финансовой отчетности для {ticker}: {str(e)}"
                logger.error(error_msg)
                error_result = {
                    "success": False,
                    "error": error_msg,
                    "ticker": ticker,
                    "market": market,
                    "report_type": report_type,
                    "suggestion": "Попробуйте использовать веб-поиск для поиска отчетов на сайте компании или SEC EDGAR"
                }
                return json.dumps(error_result, ensure_ascii=False)
            
    except Exception as e:
        error_msg = f"Ошибка при получении финансовой отчетности для {ticker}: {str(e)}"
        logger.error(error_msg)
        error_result = {
            "success": False,
            "error": error_msg,
            "ticker": ticker,
            "market": market,
            "report_type": report_type
        }
        return json.dumps(error_result, ensure_ascii=False)


def search_vector_db(
    query: str,
    n_results: Optional[int] = None
) -> str:
    """
    Поиск в векторной базе знаний.
    
    Args:
        query: Поисковый запрос
        n_results: Количество результатов (по умолчанию из config)
    
    Returns:
        Словарь с результатами поиска
    """
    try:
        # Парсим query, если он пришел как JSON строка
        if query.startswith('{') or query.startswith('['):
            try:
                parsed = json.loads(query)
                if isinstance(parsed, dict):
                    query = parsed.get('query', query)
                elif isinstance(parsed, str):
                    query = parsed
            except:
                pass
        
        logger.info(f"Поиск в векторной БД: {query}")
        
        if n_results is None:
            n_results = VECTOR_DB_DEFAULT_RESULTS
        
        # Подключаемся к БД
        client = chromadb.PersistentClient(
            path=str(VECTOR_DB_DIR),
            settings=Settings(anonymized_telemetry=False)
        )
        
        collection = client.get_collection("documents")
        
        # Инициализируем эмбеддинги
        embeddings = OpenRouterEmbeddings(
            api_key=OPENROUTER_API_KEY,
            model=OPENROUTER_MODEL,
            base_url=OPENROUTER_BASE_URL
        )
        
        # Создаем эмбеддинг для запроса
        query_embedding = embeddings.embed_query(query)
        
        # Ищем похожие документы
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results
        )
        
        # Формируем результат
        documents = results.get('documents', [])[0] if results.get('documents') else []
        metadatas = results.get('metadatas', [])[0] if results.get('metadatas') else []
        distances = results.get('distances', [])[0] if results.get('distances') else []
        
        search_results = []
        MAX_CONTENT_LENGTH = 10000  # Максимальная длина содержимого чанка
        for i, (doc, metadata, distance) in enumerate(zip(documents, metadatas, distances)):
            # Обрезаем содержимое до 10000 символов
            content = doc[:MAX_CONTENT_LENGTH] if doc else ""
            if doc and len(doc) > MAX_CONTENT_LENGTH:
                content += "..."  # Добавляем многоточие, если текст обрезан
            
            search_results.append({
                "rank": i + 1,
                "content": content,
                "metadata": metadata,
                "similarity_score": 1 - distance if distance else None,
                "source": "vector_db"
            })
        
        result = {
            "success": True,
            "query": query,
            "results_count": len(search_results),
            "results": search_results,
            "source": "vector_db"
        }
        
        logger.info(f"Найдено {len(search_results)} результатов в векторной БД")
        return json.dumps(result, ensure_ascii=False)
        
    except Exception as e:
        error_msg = f"Ошибка при поиске в векторной БД: {str(e)}"
        logger.error(error_msg)
        error_result = {
            "success": False,
            "error": error_msg,
            "query": query,
            "results": []
        }
        return json.dumps(error_result, ensure_ascii=False)


def search_web(
    query: str,
    max_results: Optional[int] = None,
    search_depth: Optional[str] = None
) -> str:
    """
    Поиск в интернете через Tavily API.
    
    Args:
        query: Поисковый запрос
        max_results: Максимальное количество результатов (по умолчанию из config)
        search_depth: Глубина поиска 'basic' или 'advanced' (по умолчанию из config)
    
    Returns:
        Словарь с результатами поиска
    """
    try:
        # Парсим query, если он пришел как JSON строка
        if query.startswith('{') or query.startswith('['):
            try:
                parsed = json.loads(query)
                if isinstance(parsed, dict):
                    query = parsed.get('query', query)
                elif isinstance(parsed, str):
                    query = parsed
            except:
                pass
        
        logger.info(f"Поиск в интернете: {query}")
        
        if max_results is None:
            max_results = TAVILY_MAX_RESULTS
        if search_depth is None:
            search_depth = TAVILY_SEARCH_DEPTH
        
        # Инициализируем клиент Tavily
        tavily = TavilyClient(api_key=TAVILY_API_KEY)
        
        # Выполняем поиск
        response = tavily.search(
            query=query,
            search_depth=search_depth,
            max_results=max_results
        )
        
        # Формируем результат
        search_results = []
        for i, result in enumerate(response.get('results', [])):
            search_results.append({
                "rank": i + 1,
                "title": result.get('title', ''),
                "url": result.get('url', ''),
                "content": result.get('content', ''),
                "score": result.get('score', None),
                "source": "tavily"
            })
        
        result = {
            "success": True,
            "query": query,
            "results_count": len(search_results),
            "results": search_results,
            "source": "tavily"
        }
        
        logger.info(f"Найдено {len(search_results)} результатов в интернете")
        return json.dumps(result, ensure_ascii=False)
        
    except Exception as e:
        error_msg = f"Ошибка при поиске в интернете: {str(e)}"
        logger.error(error_msg)
        error_result = {
            "success": False,
            "error": error_msg,
            "query": query,
            "results": []
        }
        return json.dumps(error_result, ensure_ascii=False)


def create_visualization(
    chart_type: str,
    data: str = None,
    title: Optional[str] = None,
    x_label: Optional[str] = None,
    y_label: Optional[str] = None,
    config: Optional[str] = None
) -> str:
    """
    Создает интерактивную визуализацию с использованием Plotly.
    
    Args:
        chart_type: Тип графика - 'line', 'candlestick', 'bar', 'pie', 'scatter', 'area', 'heatmap'
                   ИЛИ JSON строка со всеми параметрами
        data: Данные в формате JSON строка. Структура зависит от типа графика:
            - line/bar/area: [{{"x": [...], "y": [...], "name": "..."}}, ...]
            - candlestick: {{"open": [...], "high": [...], "low": [...], "close": [...], "dates": [...]}}
            - pie: {{"labels": [...], "values": [...]}}
            - scatter: [{{"x": [...], "y": [...], "text": [...], "name": "..."}}, ...]
            - heatmap: {{"z": [[...]], "x": [...], "y": [...]}}
        title: Заголовок графика (опционально)
        x_label: Подпись оси X (опционально)
        y_label: Подпись оси Y (опционально)
        config: Дополнительные настройки в формате JSON (опционально)
    
    Returns:
        JSON строка с результатом создания графика
    """
    try:
        # Парсим chart_type, если он пришел как JSON строка со всеми параметрами
        if chart_type.startswith('{') or chart_type.startswith('['):
            try:
                parsed = json.loads(chart_type)
                if isinstance(parsed, dict):
                    # Извлекаем параметры из JSON
                    actual_chart_type = parsed.get('chart_type', chart_type)
                    data = parsed.get('data', data)
                    title = parsed.get('title', title)
                    x_label = parsed.get('x_label', x_label)
                    y_label = parsed.get('y_label', y_label)
                    config = parsed.get('config', config)
                    chart_type = actual_chart_type
            except:
                pass  # Если не удалось распарсить, используем как есть
        
        # Проверяем, что data не пустой
        if not data:
            raise ValueError("Параметр 'data' обязателен для создания графика")
        
        # Парсим входные данные
        if isinstance(data, str):
            try:
                # Пытаемся распарсить как JSON
                parsed = json.loads(data)
                data_dict = parsed
            except json.JSONDecodeError:
                # Если не удалось распарсить, возможно это невалидный JSON
                # Пытаемся извлечь список из начала строки (для случаев, когда агент передает список + другие поля)
                logger.warning(f"Failed to parse data as JSON, attempting to extract list from string")
                # Ищем первый валидный JSON массив в строке, используя подсчет скобок
                data_stripped = data.strip()
                if data_stripped.startswith('['):
                    # Находим конец списка, считая скобки
                    bracket_count = 0
                    end_pos = -1
                    for i, char in enumerate(data_stripped):
                        if char == '[':
                            bracket_count += 1
                        elif char == ']':
                            bracket_count -= 1
                            if bracket_count == 0:
                                end_pos = i + 1
                                break
                    
                    if end_pos > 0:
                        try:
                            list_str = data_stripped[:end_pos]
                            data_dict = json.loads(list_str)
                            logger.info(f"Successfully extracted list from malformed JSON string (length: {len(list_str)})")
                        except Exception as e:
                            logger.error(f"Failed to parse extracted list: {e}")
                            data_dict = {"data": data}
                    else:
                        logger.error("Could not find end of list in malformed JSON")
                        data_dict = {"data": data}
                else:
                    data_dict = {"data": data}
            except Exception as e:
                logger.error(f"Error parsing data: {e}")
                data_dict = {"data": data}
        else:
            data_dict = data
        
        # Логируем данные для отладки
        logger.info(f"Creating {chart_type} chart with data type: {type(data_dict)}")
        if isinstance(data_dict, list):
            logger.info(f"  Data is a list with {len(data_dict)} items")
            if len(data_dict) > 0 and isinstance(data_dict[0], dict):
                logger.info(f"  First item keys: {list(data_dict[0].keys())}")
        elif isinstance(data_dict, dict):
            logger.info(f"  Data keys: {list(data_dict.keys())}")
            for key in data_dict.keys():
                if isinstance(data_dict[key], list):
                    logger.info(f"  {key}: list with {len(data_dict[key])} items")
                else:
                    logger.info(f"  {key}: {type(data_dict[key])}")
        
        if isinstance(config, str):
            try:
                config_dict = json.loads(config) if config else {}
            except:
                config_dict = {}
        else:
            config_dict = config or {}
        
        # Создаем хэш для кэширования
        cache_key = hashlib.md5(
            json.dumps({
                "chart_type": chart_type,
                "data": data_dict,
                "title": title,
                "x_label": x_label,
                "y_label": y_label,
                "config": config_dict
            }, sort_keys=True).encode('utf-8')
        ).hexdigest()
        
        cache_file = CHARTS_CACHE_DIR / f"{cache_key}.html"
        
        # Проверяем кэш
        if cache_file.exists():
            logger.info(f"Используется кэшированный график: {cache_key}")
            with open(cache_file, 'r', encoding='utf-8') as f:
                chart_html = f.read()
            
            result = {
                "success": True,
                "chart_html": chart_html,
                "chart_type": chart_type,
                "title": title or f"График {chart_type}",
                "cached": True,
                "cache_key": cache_key,
                "source": "plotly"
            }
            return json.dumps(result, ensure_ascii=False)
        
        # Создаем график в зависимости от типа
        fig = None
        
        if chart_type == "line":
            # Линейный график
            fig = go.Figure()
            if isinstance(data_dict, list):
                # Список серий данных
                for series in data_dict:
                    fig.add_trace(go.Scatter(
                        x=series.get("x", []),
                        y=series.get("y", []),
                        mode='lines+markers',
                        name=series.get("name", "Series"),
                        line=dict(width=2)
                    ))
            else:
                # Один ряд данных
                fig.add_trace(go.Scatter(
                    x=data_dict.get("x", []),
                    y=data_dict.get("y", []),
                    mode='lines+markers',
                    name=data_dict.get("name", "Data"),
                    line=dict(width=2)
                ))
        
        elif chart_type == "candlestick":
            # Свечной график
            fig = go.Figure(data=go.Candlestick(
                x=data_dict.get("dates", []),
                open=data_dict.get("open", []),
                high=data_dict.get("high", []),
                low=data_dict.get("low", []),
                close=data_dict.get("close", [])
            ))
        
        elif chart_type == "bar":
            # Столбчатый график
            fig = go.Figure()
            if isinstance(data_dict, list):
                # Список серий данных
                for series in data_dict:
                    fig.add_trace(go.Bar(
                        x=series.get("x", []),
                        y=series.get("y", []),
                        name=series.get("name", "Series")
                    ))
            else:
                # Один ряд данных
                fig.add_trace(go.Bar(
                    x=data_dict.get("x", []),
                    y=data_dict.get("y", []),
                    name=data_dict.get("name", "Data")
                ))
        
        elif chart_type == "pie":
            # Круговая диаграмма
            fig = go.Figure(data=[go.Pie(
                labels=data_dict.get("labels", []),
                values=data_dict.get("values", []),
                hole=config_dict.get("hole", 0)  # Для donut chart
            )])
        
        elif chart_type == "scatter":
            # Точечный график
            fig = go.Figure()
            
            # Улучшенная обработка данных для scatter
            if isinstance(data_dict, list):
                # Список серий данных
                if len(data_dict) == 0:
                    raise ValueError("Пустой список данных для scatter графика")
                for i, series in enumerate(data_dict):
                    if not isinstance(series, dict):
                        logger.warning(f"Series {i} is not a dict, skipping")
                        continue
                    x_data = series.get("x", [])
                    y_data = series.get("y", [])
                    # Валидация данных
                    if not x_data or not y_data:
                        raise ValueError(f"Пустые данные для scatter графика (серия {i}): x={len(x_data) if x_data else 0} точек, y={len(y_data) if y_data else 0} точек")
                    if len(x_data) != len(y_data):
                        raise ValueError(f"Несовпадение размеров данных (серия {i}): x имеет {len(x_data)} точек, y имеет {len(y_data)} точек")
                    logger.info(f"Adding scatter trace {i}: {len(x_data)} points")
                    fig.add_trace(go.Scatter(
                        x=x_data,
                        y=y_data,
                        mode='markers',
                        text=series.get("text", []),
                        name=series.get("name", f"Series {i+1}"),
                        marker=dict(size=8)
                    ))
            elif isinstance(data_dict, dict):
                # Один ряд данных
                x_data = data_dict.get("x", [])
                y_data = data_dict.get("y", [])
                # Валидация данных
                if not x_data or not y_data:
                    logger.error(f"Empty data: x_data type={type(x_data)}, len={len(x_data) if x_data else 0}, y_data type={type(y_data)}, len={len(y_data) if y_data else 0}")
                    logger.error(f"Data dict keys: {list(data_dict.keys())}")
                    raise ValueError(f"Пустые данные для scatter графика: x={len(x_data) if x_data else 0} точек, y={len(y_data) if y_data else 0} точек. Доступные ключи: {list(data_dict.keys())}")
                if len(x_data) != len(y_data):
                    raise ValueError(f"Несовпадение размеров данных: x имеет {len(x_data)} точек, y имеет {len(y_data)} точек")
                logger.info(f"Adding scatter trace: {len(x_data)} points")
                fig.add_trace(go.Scatter(
                    x=x_data,
                    y=y_data,
                    mode='markers',
                    text=data_dict.get("text", []),
                    name=data_dict.get("name", "Data"),
                    marker=dict(size=8)
                ))
            else:
                raise ValueError(f"Неподдерживаемый тип данных для scatter графика: {type(data_dict)}. Ожидается list или dict.")
        
        elif chart_type == "area":
            # Площадной график
            fig = go.Figure()
            if isinstance(data_dict, list):
                # Список серий данных
                for series in data_dict:
                    fig.add_trace(go.Scatter(
                        x=series.get("x", []),
                        y=series.get("y", []),
                        mode='lines',
                        name=series.get("name", "Series"),
                        fill='tonexty' if len(fig.data) > 0 else 'tozeroy',
                        stackgroup='one'
                    ))
            else:
                # Один ряд данных
                fig.add_trace(go.Scatter(
                    x=data_dict.get("x", []),
                    y=data_dict.get("y", []),
                    mode='lines',
                    name=data_dict.get("name", "Data"),
                    fill='tozeroy'
                ))
        
        elif chart_type == "heatmap":
            # Тепловая карта
            fig = go.Figure(data=go.Heatmap(
                z=data_dict.get("z", []),
                x=data_dict.get("x", []),
                y=data_dict.get("y", []),
                colorscale=config_dict.get("colorscale", "Viridis")
            ))
        
        else:
            raise ValueError(f"Неподдерживаемый тип графика: {chart_type}")
        
        # Настраиваем график
        # Устанавливаем autosize для автоматической подстройки под контейнер
        fig.update_layout(autosize=True)
        
        # Title не устанавливаем - не показываем название на графике
        # if title:
        #     fig.update_layout(title=title)
        if x_label:
            fig.update_xaxes(title_text=x_label)
        if y_label:
            fig.update_yaxes(title_text=y_label)
        
        # Применяем дополнительные настройки из config
        if config_dict:
            fig.update_layout(**config_dict)
        
        # Генерируем HTML
        chart_html = fig.to_html(include_plotlyjs='cdn', div_id=f"chart_{cache_key}")
        
        # Сохраняем в кэш
        with open(cache_file, 'w', encoding='utf-8') as f:
            f.write(chart_html)
        
        logger.info(f"Создан график {chart_type}, сохранен в кэш: {cache_key}")
        
        # Возвращаем результат с сообщением вместо полного HTML
        # HTML будет доступен через sources для фронтенда
        # В observation возвращаем только краткое сообщение, чтобы агент не включал HTML в ответ
        result = {
            "success": True,
            "chart_html": chart_html,  # HTML сохраняется для sources
            "chart_type": chart_type,
            "title": title or f"График {chart_type}",
            "cached": False,
            "cache_key": cache_key,
            "source": "plotly",
            "message": f"График '{title or chart_type}' успешно создан. График будет отображен в интерфейсе."
        }
        
        # Для observation возвращаем только краткую информацию, без HTML
        observation_result = {
            "success": True,
            "chart_type": chart_type,
            "title": title or f"График {chart_type}",
            "cached": False,
            "cache_key": cache_key,
            "source": "plotly",
            "message": result["message"],
            "chart_html_length": len(chart_html)  # Только длина для информации
        }
        
        return json.dumps(observation_result, ensure_ascii=False)
        
    except Exception as e:
        error_msg = f"Ошибка при создании визуализации: {str(e)}"
        logger.error(f"Ошибка при создании графика {chart_type}: {error_msg}")
        logger.error(f"Данные, которые вызвали ошибку: data type={type(data)}, data length={len(str(data)) if data else 0}")
        if isinstance(data, str) and len(data) > 0:
            logger.error(f"Первые 500 символов данных: {data[:500]}")
        import traceback
        logger.error(traceback.format_exc())
        error_result = {
            "success": False,
            "error": error_msg,
            "chart_type": chart_type
        }
        return json.dumps(error_result, ensure_ascii=False)


# ============================================================================
# СОЗДАНИЕ ИНСТРУМЕНТОВ ДЛЯ LANGCHAIN
# ============================================================================

def create_tools():
    """Создает инструменты для агента"""
    
    stock_quotes_tool = StructuredTool.from_function(
        func=get_stock_quotes,
        name="get_stock_quotes",
        description=(
            "Получает котировки акций через yfinance. "
            "Используй для получения текущих и исторических цен акций. "
            "ВАЖНО: Этот инструмент возвращает исторические данные в поле 'historical_data' с массивами dates, open, high, low, close, volume. "
            "Эти данные можно использовать для создания графиков через create_visualization. "
            "Для построения графика используй historical_data.dates как x и historical_data.close как y. "
            "КРИТИЧЕСКИ ВАЖНО: Когда пользователь просит график за определенный период (например, 'за 10 дней', 'за месяц', 'за 30 дней'), "
            "ОБЯЗАТЕЛЬНО передавай параметр period_days с соответствующим числом дней. Например: для 'за 10 дней' передай period_days=10, для 'за месяц' передай period_days=30. "
            "Без period_days инструмент вернет данные за период по умолчанию (30 дней), что может быть не тем, что хочет пользователь. "
            "Для российских акций (GAZP.ME, SBER.ME и т.д.) yfinance часто не работает из-за ограничений. "
            "Если этот инструмент вернет ошибку для российских акций, обязательно используй search_web для поиска актуальной информации. "
            "Параметры: ticker (обязательно), period_days (ОБЯЗАТЕЛЬНО передавай при запросе графика за определенный период), start_date и end_date (опционально, формат YYYY-MM-DD)."
        )
    )
    
    vector_db_search_tool = StructuredTool.from_function(
        func=search_vector_db,
        name="search_vector_db",
        description=(
            "Ищет информацию в базе знаний (векторной БД). "
            "Используй для поиска информации из документов, которые были загружены в базу знаний. "
            "Параметры: query (обязательно - поисковый запрос), n_results (опционально, по умолчанию 5)."
        )
    )
    
    web_search_tool = StructuredTool.from_function(
        func=search_web,
        name="search_web",
        description=(
            "Ищет актуальную информацию в интернете. "
            "Используй для получения свежих новостей, актуальных данных и информации, которой может не быть в базе знаний. "
            "Параметры: query (обязательно - поисковый запрос), max_results (опционально, по умолчанию 5), search_depth (опционально, 'basic' или 'advanced')."
        )
    )
    
    russian_stocks_tool = StructuredTool.from_function(
        func=get_russian_stock_quotes,
        name="get_russian_stock_quotes",
        description=(
            "Получает котировки российских акций через API Московской биржи (MOEX). "
            "Используй ЭТОТ инструмент для всех российских акций (Сбер, Газпром, Яндекс, Лукойл и т.д.). "
            "ВАЖНО: Этот инструмент возвращает исторические данные в поле 'historical_data' с массивами dates, open, high, low, close, volume. "
            "Эти данные можно использовать для создания графиков через create_visualization. "
            "Для построения графика используй historical_data.dates как x и historical_data.close как y. "
            "Параметры: ticker (обязательно - тикер на Мосбирже, например 'SBER', 'GAZP', 'YNDX'), "
            "board (опционально - режим торгов: TQBR для акций, TQTF для ETF, TQTD для долларовых ETF, TQTE для евро ETF, по умолчанию TQBR), "
            "period_days (опционально - количество дней назад для исторических данных), "
            "start_date и end_date (опционально - формат YYYY-MM-DD для исторических данных)."
        )
    )
    
    financial_metrics_tool = StructuredTool.from_function(
        func=get_financial_metrics,
        name="get_financial_metrics",
        description=(
            "Получает финансовые мультипликаторы и метрики компании (P/E, P/B, EV/EBITDA, ROE, ROA и т.д.). "
            "Используй для анализа инвестиционной привлекательности, сравнения компаний и оценки справедливой стоимости. "
            "Параметры: ticker (обязательно - тикер акции), market (опционально - 'us' для американских, 'ru' для российских, 'auto' для автоматического определения). "
            "Для российских акций данные могут быть ограничены - используй веб-поиск для получения полных мультипликаторов."
        )
    )
    
    company_financials_tool = StructuredTool.from_function(
        func=get_company_financials,
        name="get_company_financials",
        description=(
            "Получает финансовую отчетность компании (баланс, отчет о прибылях и убытках, отчет о движении денежных средств). "
            "ВАЖНО: Возвращает только ключевые показатели (summary) для экономии токенов. Полный отчет автоматически сохраняется в файл. "
            "Используй для детального финансового анализа, оценки финансового состояния и поиска конкретных показателей в отчетах. "
            "Параметры: ticker (обязательно - тикер акции), report_type (опционально - 'annual' для годового, 'quarterly' для квартального, по умолчанию 'annual'), "
            "market (опционально - 'us' для американских, 'ru' для российских, 'auto' для автоматического определения). "
            "Для российских акций рекомендуется использовать веб-поиск для поиска отчетов на сайте компании или MOEX."
        )
    )
    
    visualization_tool = StructuredTool.from_function(
        func=create_visualization,
        name="create_visualization",
        description=(
            "Создает интерактивную визуализацию (график) с использованием Plotly. "
            "Используй этот инструмент, когда пользователь просит показать график, визуализацию, диаграмму или сравнение данных. "
            "Параметры: "
            "chart_type (обязательно) - тип графика: 'line' (линейный для котировок, временных рядов), "
            "'candlestick' (свечной для акций), 'bar' (столбчатый для сравнения), 'pie' (круговая диаграмма), "
            "'scatter' (точечный для корреляций), 'area' (площадной), 'heatmap' (тепловая карта). "
            "data (обязательно) - данные в формате JSON строка. Структура зависит от типа: "
            "для line/bar/area: [{{\"x\": [...], \"y\": [...], \"name\": \"...\"}}, ...], "
            "для candlestick: {{\"open\": [...], \"high\": [...], \"low\": [...], \"close\": [...], \"dates\": [...]}}, "
            "для pie: {{\"labels\": [...], \"values\": [...]}}, "
            "для scatter: [{{\"x\": [...], \"y\": [...], \"text\": [...], \"name\": \"...\"}}, ...], "
            "для heatmap: {{\"z\": [[...]], \"x\": [...], \"y\": [...]}}. "
            "title (опционально) - заголовок графика. "
            "x_label (опционально) - подпись оси X. "
            "y_label (опционально) - подпись оси Y. "
            "config (опционально) - дополнительные настройки в формате JSON. "
            "ВАЖНО: Для создания графиков котировок: "
            "1. Сначала получи данные через get_stock_quotes (он возвращает historical_data с dates, close, open, high, low, volume). "
            "2. Используй historical_data.dates как x и historical_data.close как y для линейного графика. "
            "3. Для свечного графика используй historical_data.dates, open, high, low, close. "
            "4. Передай данные в create_visualization в формате JSON. "
            "Пример для линейного графика: data = json.dumps([{{\"x\": historical_data.dates, \"y\": historical_data.close, \"name\": ticker}}]). "
            "Пример для свечного: data = json.dumps({{\"dates\": historical_data.dates, \"open\": historical_data.open, \"high\": historical_data.high, \"low\": historical_data.low, \"close\": historical_data.close}})."
        )
    )
    
    return [stock_quotes_tool, russian_stocks_tool, financial_metrics_tool, company_financials_tool, vector_db_search_tool, web_search_tool, visualization_tool]


# ============================================================================
# ПРОМПТ ДЛЯ АГЕНТА
# ============================================================================

REACT_PROMPT = """Ты полезный AI-ассистент с доступом к семи инструментам:

1. get_stock_quotes - получение котировок акций (только для американских и других зарубежных акций)
2. get_russian_stock_quotes - получение котировок российских акций через MOEX (для всех российских акций)
3. get_financial_metrics - получение финансовых мультипликаторов (P/E, P/B, EV/EBITDA, ROE, ROA и т.д.)
4. get_company_financials - получение финансовой отчетности (баланс, отчет о прибылях, денежные потоки)
5. search_vector_db - поиск в базе знаний (теория, учебники, методики оценки)
6. search_web - поиск актуальной информации в интернете
7. create_visualization - создание интерактивных графиков и визуализаций (линейные, свечные, столбчатые, круговые и т.д.)

ВАЖНО: 
- Для простых приветствий (Привет, Здравствуй, Как дела и т.д.) - отвечай сразу через Final Answer БЕЗ использования инструментов

Доступные инструменты:
{tools}

Доступные имена инструментов: {tool_names}

История диалога:
{chat_history}

Используй следующий формат:

Question: вопрос пользователя
Thought: твои рассуждения о том, что нужно сделать
Action: название инструмента
Action Input: входные параметры для инструмента (в формате JSON, если нужно несколько параметров)
Observation: результат выполнения инструмента
... (этот Thought/Action/Action Input/Observation может повторяться N раз)
Thought: теперь у меня есть вся необходимая информация
Final Answer: финальный ответ пользователю на русском языке

Примеры:
- Вопрос "Привет!" → Thought: Это простое приветствие, не требует инструментов → Final Answer: Привет! Чем могу помочь?
- Вопрос "Сколько стоит акция Apple?" → Thought: Нужно получить котировки → Action: get_stock_quotes → Action Input: {{"ticker": "AAPL"}} → Observation: ... → Final Answer: ...
- Вопрос "Покажи график котировок Apple за месяц" → Thought: Нужно получить исторические данные → Action: get_stock_quotes → Action Input: {{"ticker": "AAPL", "period_days": 30}} → Observation: {{"success": true, "historical_data": {{"dates": [...], "close": [...]}}, ...}} → Thought: Теперь создам график → Action: create_visualization → Action Input: {{"chart_type": "line", "data": "[{{\"x\": historical_data.dates, \"y\": historical_data.close, \"name\": \"AAPL\"}}]", "title": "Котировки Apple за месяц"}} → Observation: ... → Final Answer: Вот график котировок Apple за последний месяц.

Важные правила:
- Если пользователь задал НЕСКОЛЬКО вопросов - обрабатывай их ПОСЛЕДОВАТЕЛЬНО, один за другим. НЕ пытайся ответить на все сразу через один Final Answer
- Для простых приветствий, общих вопросов или когда вопрос не требует данных - отвечай сразу через Final Answer БЕЗ использования инструментов, но если вопрос хоть как-то затрагивает финансы - лучше выбрать инструмент, чем ответить самостоятельно
- Если инструмент вернул ошибку, попробуй использовать другой инструмент или объясни пользователю проблему
- НИКОГДА не смешивай Final Answer и Action в одном ответе. Либо используй инструмент (Action), либо дай финальный ответ (Final Answer)
- Для российских акций (Сбер, Газпром, Яндекс, Лукойл и т.д.): ВСЕГДА используй get_russian_stock_quotes с тикером без .ME (например, 'SBER' для Сбера, 'GAZP' для Газпрома)
- Для американских и других зарубежных акций используй get_stock_quotes с тикером (например, 'AAPL' для Apple)
- Для финансового анализа: используй get_financial_metrics для получения мультипликаторов и get_company_financials для детальной отчетности
- Для обоснования выводов: комбинируй текущие данные (get_financial_metrics, get_company_financials) с теорией из search_vector_db и актуальной информацией из search_web
- При сравнении компаний: получай метрики для всех компаний через get_financial_metrics и сравнивай их
- Для сценариев "Что если": используй текущие данные и теорию из search_vector_db для моделирования изменений
- Для визуализаций: когда пользователь просит показать график котировок, используй get_stock_quotes (для американских акций) или get_russian_stock_quotes (для российских акций) для получения исторических данных (поле historical_data), затем create_visualization для создания графика. Оба инструмента возвращают historical_data с массивами dates, close, open, high, low, volume - используй их для построения графика. КРИТИЧЕСКИ ВАЖНО: Когда пользователь указывает период (например, "за 10 дней", "за месяц", "за 30 дней"), ОБЯЗАТЕЛЬНО передавай параметр period_days с соответствующим числом. Например: "за 10 дней" → period_days=10, "за месяц" → period_days=30, "за неделю" → period_days=7. Без period_days инструмент вернет данные за период по умолчанию (30 дней), что будет неправильно. ВАЖНО: Когда create_visualization возвращает результат, НЕ включай HTML в финальный ответ. Просто скажи, что график создан и будет отображен ниже. Например: "Вот график котировок..." или "График создан и отображается ниже."
- Если информации недостаточно, используй несколько инструментов
- Всегда давай структурированный ответ с источниками информации и обоснованием выводов
- НИКОГДА не включай HTML код в финальный ответ. Если инструмент вернул HTML (например, от create_visualization), просто упомяни, что график/визуализация создана
- КРИТИЧЕСКИ ВАЖНО: ВСЕГДА используй историю диалога ({chat_history}) для понимания контекста. 
  Если запрос пользователя непонятен, неполон или содержит короткие вопросы (например, "Какое?", "Что это?", "Почему?", "Как?", "Когда?"), 
  это означает, что он ссылается на информацию из предыдущих сообщений. 
  ВСЕГДА анализируй историю диалога, чтобы понять, о чем идет речь, и ответь на основе этого контекста. 
  НЕ проси уточнить вопрос, если ответ можно найти в истории диалога или в предыдущих ответах. 
  Используй контекст из истории для восстановления полного смысла вопроса. Если после рассмотрения контекста сообщение пользователя непонятно, можешь задать уточняющий вопрос. 
- КРИТИЧЕСКИ ВАЖНО: Ты специализированный финансовый ассистент. ВСЕГДА оставайся в рамках финансовой тематики. 
  Если пользователь пытается увести разговор в сторону от финансов, акций, инвестиций, экономики или связанных тем, 
  вежливо напомни о своей специализации и предложи вернуться к финансовым вопросам. 
  НЕ отвечай на вопросы, не связанные с финансами, экономикой, инвестициями, акциями, облигациями и другими финансовыми инструментами.

Question: {input}
Thought:{agent_scratchpad}
"""


# ============================================================================
# КЛАСС АГЕНТА
# ============================================================================

class FinancialAgent:
    """Агент для работы с финансовой информацией"""
    
    def __init__(self, use_memory: bool = False):
        """
        Инициализация агента
        
        Args:
            use_memory: Использовать ли память диалога
        """
        self.use_memory = use_memory
        self.logger = logger
        
        # Инициализируем LLM через OpenRouter
        self.llm = ChatOpenAI(
            model=AGENT_LLM_MODEL,
            openai_api_key=OPENROUTER_API_KEY,
            openai_api_base=OPENROUTER_BASE_URL,
            temperature=0.7,
            streaming=False
        )
        
        # Создаем инструменты
        self.tools = create_tools()
        
        # Создаем память (если нужно)
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True,
            input_key="input",
            output_key="output"
        ) if use_memory else None
        
        # Создаем промпт
        base_prompt = PromptTemplate.from_template(REACT_PROMPT)
        if self.memory:
            prompt = base_prompt
        else:
            prompt = base_prompt.partial(chat_history="")
        
        # Создаем агента
        agent = create_react_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=prompt
        )
        
        # Функция для обработки ошибок парсинга
        def handle_parsing_error(error: Exception) -> str:
            """Обработка ошибок парсинга - пытаемся извлечь Action из ответа"""
            error_str = str(error)
            
            # Если ошибка связана с тем, что есть и Final Answer и Action одновременно
            if "both a final answer and a parse-able action" in error_str.lower():
                # Пытаемся извлечь Action из текста ошибки
                # Ищем Action: в тексте ошибки
                action_match = re.search(r'Action:\s*(\w+)', error_str, re.IGNORECASE)
                action_input_match = re.search(r'Action Input:\s*(\{.*?\})', error_str, re.DOTALL)
                
                if action_match:
                    # Если нашли Action, возвращаем его для повторной попытки
                    # LangChain автоматически попробует использовать этот Action
                    action_name = action_match.group(1)
                    if action_input_match:
                        action_input = action_input_match.group(1)
                        # Возвращаем строку, которую LangChain может распарсить
                        return f"Action: {action_name}\nAction Input: {action_input}"
                    else:
                        return f"Action: {action_name}\nAction Input: {{}}"
            
            if "Missing 'Action:'" in error_str or "Could not parse" in error_str:
                # Если агент не может распарсить ответ, возвращаем финальный ответ напрямую
                return "Я понял ваш вопрос, но возникла техническая проблема. Пожалуйста, переформулируйте вопрос или попробуйте еще раз."
            
            return f"Ошибка: {error_str}"
        
        # Создаем executor
        self.agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            memory=self.memory,
            verbose=AGENT_VERBOSE,
            max_iterations=AGENT_MAX_ITERATIONS,
            handle_parsing_errors=handle_parsing_error,
            return_intermediate_steps=True
        )
        
        self.logger.info(f"Агент инициализирован (memory={'включена' if use_memory else 'выключена'})")
    
    def _print_step(self, step_type: str, data: Dict[str, Any]):
        """Выводит информацию о шаге в реальном времени"""
        output = {
            "timestamp": datetime.now().isoformat(),
            "type": step_type,
            "data": data
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        sys.stdout.flush()
    
    def run(self, query: str) -> Dict[str, Any]:
        """
        Выполняет запрос пользователя
        
        Args:
            query: Запрос пользователя
        
        Returns:
            Результат работы агента
        """
        self.logger.info(f"Запрос пользователя: {query}")
        self._print_step("user_query", {"query": query})
        
        try:
            # Проверяем, является ли вопрос простым приветствием или общим вопросом
            # Если да, отвечаем сразу без использования инструментов
            simple_greetings = ["привет", "здравствуй", "здравствуйте", "hi", "hello", "hey", "как дела", "как поживаешь"]
            query_lower = query.lower().strip()
            
            # Если это простое приветствие - отвечаем сразу
            if any(greeting in query_lower for greeting in simple_greetings) and len(query.split()) <= 3:
                simple_response = "Привет! Чем могу помочь? Я могу помочь с анализом акций, получением котировок, финансовых метрик и другой финансовой информацией."
                self._print_step("final_answer", {
                    "answer": simple_response,
                    "sources": []
                })
                return {
                    "success": True,
                    "query": query,
                    "answer": simple_response,
                    "sources": [],
                    "steps": 0
                }
            
            # Запускаем агента
            result = self.agent_executor.invoke({"input": query})
            
            # Выводим промежуточные шаги
            if "intermediate_steps" in result:
                for i, (action, observation) in enumerate(result["intermediate_steps"]):
                    # Извлекаем информацию о действии
                    tool_name = action.tool if hasattr(action, 'tool') else str(action)
                    tool_input = action.tool_input if hasattr(action, 'tool_input') else str(action)
                    
                    self._print_step("agent_action", {
                        "step": i + 1,
                        "tool": tool_name,
                        "tool_input": tool_input
                    })
                    
                    # Форматируем observation
                    # Инструменты возвращают JSON строки, парсим их
                    if isinstance(observation, str):
                        try:
                            obs_data = json.loads(observation)
                        except:
                            obs_data = {"observation": observation}
                    elif isinstance(observation, dict):
                        obs_data = observation
                    else:
                        obs_data = {"observation": str(observation)}
                    
                    # Для финансовой отчетности выводим только summary, если он есть
                    if isinstance(obs_data, dict) and obs_data.get("summary") and obs_data.get("full_report_file"):
                        # Создаем сокращенную версию для вывода
                        display_data = {
                            "success": obs_data.get("success"),
                            "ticker": obs_data.get("ticker"),
                            "company_name": obs_data.get("company_name"),
                            "report_type": obs_data.get("report_type"),
                            "latest_period": obs_data.get("latest_period"),
                            "summary": True,
                            "income_statement_summary": obs_data.get("income_statement_summary"),
                            "balance_sheet_summary": obs_data.get("balance_sheet_summary"),
                            "cash_flow_summary": obs_data.get("cash_flow_summary"),
                            "full_report_file": obs_data.get("full_report_file"),
                            "note": obs_data.get("note")
                        }
                        self._print_step("tool_result", {
                            "step": i + 1,
                            "result": display_data
                        })
                        
                        # Интерактивный вопрос о сохранении полного отчета
                        full_report_path = obs_data.get("full_report_file")
                        if full_report_path:
                            try:
                                report_path = Path(full_report_path)
                                if report_path.exists():
                                    # Файл уже сохранен инструментом, спрашиваем, нужно ли его оставить
                                    print("\n" + "="*80)
                                    print(f"Полный отчет временно сохранен в файл: {full_report_path}")
                                    response = input("Сохранить полный отчет? (y/n): ").strip().lower()
                                    print("="*80 + "\n")
                                    
                                    if response != 'y':
                                        # Удаляем файл, если пользователь не хочет его сохранять
                                        try:
                                            report_path.unlink()
                                            print("Полный отчет не сохранен (файл удален)")
                                        except Exception as e:
                                            self.logger.error(f"Ошибка при удалении файла: {e}")
                                    else:
                                        print(f"Полный отчет сохранен: {full_report_path}")
                            except Exception as e:
                                self.logger.error(f"Ошибка при обработке вопроса о сохранении отчета: {e}")
                    else:
                        self._print_step("tool_result", {
                            "step": i + 1,
                            "result": obs_data
                        })
            
            # Выводим финальный ответ
            final_answer = result.get("output", "Нет ответа")
            self._print_step("final_answer", {
                "answer": final_answer,
                "sources": self._extract_sources(result)
            })
            
            return {
                "success": True,
                "query": query,
                "answer": final_answer,
                "sources": self._extract_sources(result),
                "steps": len(result.get("intermediate_steps", []))
            }
            
        except Exception as e:
            error_msg = f"Ошибка при выполнении запроса: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self._print_step("error", {
                "error": error_msg,
                "error_type": type(e).__name__
            })
            
            return {
                "success": False,
                "query": query,
                "error": error_msg,
                "answer": f"Произошла ошибка: {error_msg}"
            }
    
    def _extract_sources(self, result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Извлекает источники из результатов работы агента"""
        sources = []
        
        if "intermediate_steps" in result:
            for action, observation in result["intermediate_steps"]:
                # Парсим observation (может быть строкой JSON или dict)
                if isinstance(observation, str):
                    try:
                        obs_data = json.loads(observation)
                    except:
                        continue
                elif isinstance(observation, dict):
                    obs_data = observation
                else:
                    continue
                
                source_type = obs_data.get("source", "unknown")
                
                # Определяем тип данных по содержимому
                if source_type == "yfinance":
                    # Проверяем, что это за данные
                    if obs_data.get("pe_ratio") is not None or obs_data.get("roe") is not None:
                        # Это финансовые метрики
                        sources.append({
                            "type": "financial_metrics",
                            "ticker": obs_data.get("ticker"),
                            "source": "yfinance"
                        })
                    elif obs_data.get("income_statement") is not None or obs_data.get("balance_sheet") is not None or obs_data.get("summary"):
                        # Это финансовая отчетность (полная или summary)
                        sources.append({
                            "type": "company_financials",
                            "ticker": obs_data.get("ticker"),
                            "report_type": obs_data.get("report_type"),
                            "source": "yfinance",
                            "full_report_file": obs_data.get("full_report_file") if obs_data.get("summary") else None
                        })
                    elif obs_data.get("current_price") is not None and obs_data.get("period") is not None:
                        # Это котировки
                        sources.append({
                            "type": "stock_quotes",
                            "ticker": obs_data.get("ticker"),
                            "source": "yfinance"
                        })
                    else:
                        # По умолчанию котировки
                        sources.append({
                            "type": "stock_quotes",
                            "ticker": obs_data.get("ticker"),
                            "source": "yfinance"
                        })
                elif source_type == "moex":
                    sources.append({
                        "type": "russian_stock_quotes",
                        "ticker": obs_data.get("ticker"),
                        "board": obs_data.get("board"),
                        "source": "moex"
                    })
                elif source_type == "vector_db":
                    # Извлекаем информацию о документах из результатов поиска
                    results = obs_data.get("results", [])
                    documents = []
                    seen_docs = set()  # Для отслеживания уникальных документов
                    
                    for result in results:
                        if isinstance(result, dict):
                            metadata = result.get("metadata", {})
                            title = metadata.get("title", "")
                            url = metadata.get("url", "")
                            filename = metadata.get("filename", "")
                            
                            # Создаем уникальный ключ для документа (по filename или title)
                            doc_key = filename or title
                            if doc_key and doc_key not in seen_docs:
                                seen_docs.add(doc_key)
                                documents.append({
                                    "title": title or filename or "Документ",
                                    "url": url,
                                    "filename": filename
                                })
                    
                    sources.append({
                        "type": "knowledge_base",
                        "query": obs_data.get("query"),
                        "results_count": obs_data.get("results_count", 0),
                        "documents": documents,  # Добавляем массив документов
                        "source": "vector_db"
                    })
                elif source_type == "tavily":
                    # Извлекаем URL-ы из результатов веб-поиска
                    results = obs_data.get("results", [])
                    urls = []
                    for result in results:
                        if isinstance(result, dict) and result.get("url"):
                            urls.append({
                                "url": result.get("url"),
                                "title": result.get("title", "")
                            })
                    
                    sources.append({
                        "type": "web_search",
                        "query": obs_data.get("query"),
                        "results_count": obs_data.get("results_count", 0),
                        "urls": urls,  # Добавляем массив URL-ов
                        "source": "tavily"
                    })
                elif source_type == "plotly":
                    # Обрабатываем графики
                    cache_key = obs_data.get("cache_key")
                    chart_html = obs_data.get("chart_html")
                    
                    # Если HTML не в observation, загружаем из кэша
                    if not chart_html and cache_key:
                        cache_file = CHARTS_CACHE_DIR / f"{cache_key}.html"
                        if cache_file.exists():
                            try:
                                with open(cache_file, 'r', encoding='utf-8') as f:
                                    chart_html = f.read()
                            except Exception as e:
                                logger.error(f"Ошибка при загрузке графика из кэша: {e}")
                    
                    sources.append({
                        "type": "visualization",
                        "chart_type": obs_data.get("chart_type"),
                        "title": obs_data.get("title"),
                        "cache_key": cache_key,
                        "chart_html": chart_html,  # HTML для отображения
                        "source": "plotly"
                    })
        
        return sources


# ============================================================================
# CLI ИНТЕРФЕЙС
# ============================================================================

def main():
    """Главная функция CLI"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Финансовый AI-агент с доступом к котировкам, базе знаний и интернету"
    )
    parser.add_argument(
        "--memory",
        action="store_true",
        help="Включить память диалога (для прода)"
    )
    parser.add_argument(
        "--no-memory",
        action="store_true",
        help="Выключить память диалога (для тестирования)"
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="Запрос к агенту"
    )
    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Интерактивный режим"
    )
    
    args = parser.parse_args()
    
    # Определяем использование памяти
    use_memory = args.memory if not args.no_memory else False
    
    # Создаем агента
    agent = FinancialAgent(use_memory=use_memory)
    
    if args.interactive or not args.query:
        # Интерактивный режим
        print("=" * 60)
        print("Финансовый AI-агент")
        print(f"Память диалога: {'включена' if use_memory else 'выключена'}")
        print("Введите 'exit' или 'quit' для выхода")
        print("=" * 60)
        
        while True:
            try:
                query = input("\n> ")
                if query.lower() in ['exit', 'quit', 'q']:
                    break
                
                if not query.strip():
                    continue
                
                agent.run(query)
                
            except KeyboardInterrupt:
                print("\n\nВыход...")
                break
            except Exception as e:
                print(f"\nОшибка: {e}")
    else:
        # Одноразовый запрос
        result = agent.run(args.query)
        if not result.get("success"):
            sys.exit(1)


if __name__ == "__main__":
    main()

