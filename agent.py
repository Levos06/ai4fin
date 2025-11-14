#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Агент на базе LLM с шестью инструментами:
1. Запрос котировок акций (yfinance) - для американских и зарубежных акций
2. Запрос котировок российских акций (MOEX API) - для российских акций
3. Получение финансовых мультипликаторов (P/E, P/B, EV/EBITDA, ROE, ROA и т.д.)
4. Получение финансовой отчетности (баланс, отчет о прибылях, денежные потоки)
5. Поиск в векторной базе знаний (ChromaDB)
6. Поиск в интернете (Tavily)
"""
import json
import logging
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
    LOG_DIR, FINANCIAL_REPORTS_DIR
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
        # Парсим ticker, если он пришел как JSON строка
        if ticker.startswith('{') or ticker.startswith('['):
            try:
                parsed = json.loads(ticker)
                if isinstance(parsed, dict):
                    ticker = parsed.get('ticker', ticker)
                elif isinstance(parsed, str):
                    ticker = parsed
            except:
                pass
        
        logger.info(f"Запрос котировок для {ticker}")
        
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
            "source": "yfinance"
        }
        
        logger.info(f"Успешно получены котировки для {ticker}")
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
    board: Optional[str] = None
) -> str:
    """
    Получает котировки российских акций через API Московской биржи (MOEX).
    
    Args:
        ticker: Тикер акции на Мосбирже (например, 'SBER', 'GAZP', 'YNDX')
        board: Режим торгов (TQBR для акций, TQTF для ETF, TQTD для долларовых ETF, TQTE для евро ETF)
               По умолчанию определяется автоматически
    
    Returns:
        JSON строка с данными о котировках
    """
    try:
        # Парсим ticker, если он пришел как JSON строка
        if ticker.startswith('{') or ticker.startswith('['):
            try:
                parsed = json.loads(ticker)
                if isinstance(parsed, dict):
                    ticker = parsed.get('ticker', ticker)
                    board = parsed.get('board', board)
                elif isinstance(parsed, str):
                    ticker = parsed
            except:
                pass
        
        # Убираем .ME если есть (для совместимости)
        ticker = ticker.replace('.ME', '').upper()
        
        logger.info(f"Запрос котировок MOEX для {ticker}")
        
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
        for i, (doc, metadata, distance) in enumerate(zip(documents, metadatas, distances)):
            search_results.append({
                "rank": i + 1,
                "content": doc,
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
            "ВАЖНО: Для российских акций (GAZP.ME, SBER.ME и т.д.) yfinance часто не работает из-за ограничений. "
            "Если этот инструмент вернет ошибку для российских акций, обязательно используй search_web для поиска актуальной информации. "
            "Параметры: ticker (обязательно), period_days (опционально), start_date и end_date (опционально, формат YYYY-MM-DD)."
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
            "Параметры: ticker (обязательно - тикер на Мосбирже, например 'SBER', 'GAZP', 'YNDX'), "
            "board (опционально - режим торгов: TQBR для акций, TQTF для ETF, TQTD для долларовых ETF, TQTE для евро ETF, по умолчанию TQBR)."
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
    
    return [stock_quotes_tool, russian_stocks_tool, financial_metrics_tool, company_financials_tool, vector_db_search_tool, web_search_tool]


# ============================================================================
# ПРОМПТ ДЛЯ АГЕНТА
# ============================================================================

REACT_PROMPT = """Ты полезный AI-ассистент с доступом к шести инструментам:

1. get_stock_quotes - получение котировок акций (только для американских и других зарубежных акций)
2. get_russian_stock_quotes - получение котировок российских акций через MOEX (для всех российских акций)
3. get_financial_metrics - получение финансовых мультипликаторов (P/E, P/B, EV/EBITDA, ROE, ROA и т.д.)
4. get_company_financials - получение финансовой отчетности (баланс, отчет о прибылях, денежные потоки)
5. search_vector_db - поиск в базе знаний (теория, учебники, методики оценки)
6. search_web - поиск актуальной информации в интернете

Используй инструменты для ответа на вопросы пользователя. Всегда думай шаг за шагом.

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

Важные правила:
- Если инструмент вернул ошибку, попробуй использовать другой инструмент или объясни пользователю проблему
- Для российских акций (Сбер, Газпром, Яндекс, Лукойл и т.д.): ВСЕГДА используй get_russian_stock_quotes с тикером без .ME (например, 'SBER' для Сбера, 'GAZP' для Газпрома)
- Для американских и других зарубежных акций используй get_stock_quotes с тикером (например, 'AAPL' для Apple)
- Для финансового анализа: используй get_financial_metrics для получения мультипликаторов и get_company_financials для детальной отчетности
- Для обоснования выводов: комбинируй текущие данные (get_financial_metrics, get_company_financials) с теорией из search_vector_db и актуальной информацией из search_web
- При сравнении компаний: получай метрики для всех компаний через get_financial_metrics и сравнивай их
- Для сценариев "Что если": используй текущие данные и теорию из search_vector_db для моделирования изменений
- Если информации недостаточно, используй несколько инструментов
- Всегда давай структурированный ответ с источниками информации и обоснованием выводов

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
        
        # Создаем executor
        self.agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            memory=self.memory,
            verbose=AGENT_VERBOSE,
            max_iterations=AGENT_MAX_ITERATIONS,
            handle_parsing_errors=True,
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
                    sources.append({
                        "type": "knowledge_base",
                        "query": obs_data.get("query"),
                        "results_count": obs_data.get("results_count", 0),
                        "source": "vector_db"
                    })
                elif source_type == "tavily":
                    sources.append({
                        "type": "web_search",
                        "query": obs_data.get("query"),
                        "results_count": obs_data.get("results_count", 0),
                        "source": "tavily"
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

