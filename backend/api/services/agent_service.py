"""
Сервис для работы с финансовым агентом
"""
import json
import sys
import asyncio
import threading
import re
from pathlib import Path
from typing import AsyncGenerator, Dict, Any, Optional, List
from datetime import datetime

# Добавляем корневую директорию в путь для импорта agent.py
ROOT_DIR = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

try:
    from agent import FinancialAgent
    from config import AGENT_MAX_ITERATIONS
    from langchain_core.callbacks import BaseCallbackHandler
except ImportError as e:
    print(f"Warning: Could not import agent: {e}")
    FinancialAgent = None
    BaseCallbackHandler = None


# Упрощенный подход - отправляем шаги сразу после получения из результата
class ThoughtCallbackHandler(BaseCallbackHandler):
    """Callback handler для перехвата размышлений агента в реальном времени"""
    
    def __init__(self, thought_callback=None, step_callback=None):
        super().__init__()
        self.thought_callback = thought_callback
        self.step_callback = step_callback
        self.current_thought = ""
        self.thoughts: List[str] = []
        self.last_thought = None
        self.step_counter = 0
    
    def on_llm_end(self, response, **kwargs):
        """Вызывается когда LLM завершает генерацию - здесь мы можем извлечь Thought"""
        try:
            content = None
            # Пытаемся получить content из разных мест response
            if hasattr(response, 'generations') and response.generations:
                for generation_list in response.generations:
                    for generation in generation_list:
                        if hasattr(generation, 'text'):
                            content = generation.text
                            break
                        elif hasattr(generation, 'message'):
                            if hasattr(generation.message, 'content'):
                                content = generation.message.content
                                break
                            elif hasattr(generation.message, 'text'):
                                content = generation.message.text
                                break
                    if content:
                        break
            
            # Если не нашли в generations, пробуем другие атрибуты
            if not content:
                if hasattr(response, 'content'):
                    content = response.content
                elif hasattr(response, 'text'):
                    content = response.text
                elif hasattr(response, 'llm_output'):
                    # Пытаемся извлечь из llm_output
                    llm_output = response.llm_output
                    if isinstance(llm_output, dict) and 'text' in llm_output:
                        content = llm_output['text']
            
            # Логируем для отладки
            print(f"[DEBUG] on_llm_end called, content type: {type(content)}, has callback: {self.thought_callback is not None}")
            if content:
                print(f"[DEBUG] Content length: {len(str(content))}, first 200 chars: {str(content)[:200]}")
            
            # Извлекаем Thought из content
            if content:
                content_str = str(content)
                
                # Сначала ищем явные "Thought:" паттерны
                thought_matches = re.finditer(r'Thought:?\s*(.+?)(?=\s*Action:|\s*Final Answer:|\s*Thought:|$)', 
                                             content_str, re.DOTALL | re.IGNORECASE)
                found_thought = False
                for match in thought_matches:
                    thought_text = match.group(1).strip()
                    # Очищаем от лишних символов и переносов строк
                    thought_text = re.sub(r'\n+', ' ', thought_text)
                    thought_text = re.sub(r'\s+', ' ', thought_text)
                    thought_text = thought_text.strip()
                    
                    if thought_text and len(thought_text) > 10:
                        # НЕ обрезаем мысли на бэкенде - они должны передаваться полностью
                        # Обрезка будет на фронтенде для визуального отображения
                        
                        # Проверяем, не был ли уже отправлен этот thought
                        if thought_text not in self.thoughts and thought_text != self.last_thought:
                            print(f"[DEBUG] Found thought (with Thought:): {thought_text[:100]}...")
                            self.thoughts.append(thought_text)
                            self.last_thought = thought_text
                            found_thought = True
                            if self.thought_callback:
                                print(f"[DEBUG] Calling thought_callback with: {thought_text[:50]}...")
                                try:
                                    self.thought_callback(thought_text, is_final=False)
                                    print(f"[DEBUG] thought_callback executed successfully")
                                except Exception as e:
                                    print(f"[ERROR] Error in thought_callback: {e}")
                                    import traceback
                                    print(traceback.format_exc())
                        else:
                            print(f"[DEBUG] Thought already sent, skipping: {thought_text[:50]}...")
                
                # Если не нашли явный "Thought:", но есть текст перед "Action:"
                # Это может быть размышление без метки
                if not found_thought:
                    # Ищем текст от начала до первого "Action:" или "Final Answer:"
                    # Более гибкий паттерн - ищем любой текст перед Action или Final Answer
                    pre_action_match = re.search(r'^(.+?)(?=\s*Action:|\s*Final Answer:)', content_str, re.DOTALL | re.IGNORECASE)
                    if pre_action_match:
                        potential_thought = pre_action_match.group(1).strip()
                        # Убираем "Question:" если есть
                        potential_thought = re.sub(r'^Question:?\s*', '', potential_thought, flags=re.IGNORECASE)
                        # Убираем лишние пробелы и переносы
                        potential_thought = re.sub(r'\n+', ' ', potential_thought)
                        potential_thought = re.sub(r'\s+', ' ', potential_thought)
                        potential_thought = potential_thought.strip()
                        
                        # Проверяем, что это похоже на размышление
                        # Уменьшаем минимальную длину до 15 символов для более раннего вывода
                        if (potential_thought and len(potential_thought) > 15 and 
                            re.search(r'[а-яА-Яa-zA-Z]', potential_thought)):  # Есть буквы
                            # НЕ обрезаем мысли на бэкенде - они должны передаваться полностью
                            # Обрезка будет на фронтенде для визуального отображения
                            
                            # Проверяем, не был ли уже отправлен
                            if potential_thought not in self.thoughts and potential_thought != self.last_thought:
                                print(f"[DEBUG] Found potential thought (before Action:): {potential_thought[:100]}...")
                                self.thoughts.append(potential_thought)
                                self.last_thought = potential_thought
                                if self.thought_callback:
                                    print(f"[DEBUG] Calling thought_callback with: {potential_thought[:50]}...")
                                    try:
                                        self.thought_callback(potential_thought, is_final=False)
                                        print(f"[DEBUG] thought_callback executed successfully")
                                    except Exception as e:
                                        print(f"[ERROR] Error in thought_callback: {e}")
                                        import traceback
                                        print(traceback.format_exc())
                            else:
                                print(f"[DEBUG] Potential thought already sent, skipping: {potential_thought[:50]}...")
                    else:
                        # Если не нашли паттерн, но content не пустой и не содержит Action/Final Answer
                        # Это может быть размышление без явных маркеров
                        if content_str and not re.search(r'Action:|Final Answer:', content_str, re.IGNORECASE):
                            # Проверяем, что это не слишком короткое и содержит буквы
                            clean_content = content_str.strip()
                            clean_content = re.sub(r'^Question:?\s*', '', clean_content, flags=re.IGNORECASE)
                            clean_content = re.sub(r'\n+', ' ', clean_content)
                            clean_content = re.sub(r'\s+', ' ', clean_content)
                            clean_content = clean_content.strip()
                            
                            if (clean_content and len(clean_content) > 15 and 
                                re.search(r'[а-яА-Яa-zA-Z]', clean_content)):
                                # Проверяем, не был ли уже отправлен
                                if clean_content not in self.thoughts and clean_content != self.last_thought:
                                    print(f"[DEBUG] Found thought (no markers): {clean_content[:100]}...")
                                    self.thoughts.append(clean_content)
                                    self.last_thought = clean_content
                                    if self.thought_callback:
                                        print(f"[DEBUG] Calling thought_callback with: {clean_content[:50]}...")
                                        try:
                                            self.thought_callback(clean_content, is_final=False)
                                            print(f"[DEBUG] thought_callback executed successfully")
                                        except Exception as e:
                                            print(f"[ERROR] Error in thought_callback: {e}")
                                            import traceback
                                            print(traceback.format_exc())
                                else:
                                    print(f"[DEBUG] Thought (no markers) already sent, skipping: {clean_content[:50]}...")
        except KeyboardInterrupt:
            # Пробрасываем прерывание дальше
            raise
        except Exception as e:
            # Логируем ошибку для отладки
            import traceback
            print(f"[ERROR] Error in on_llm_end: {e}")
            print(traceback.format_exc())
    
    def on_agent_action(self, action, **kwargs):
        """Вызывается когда агент выполняет действие - отправляем уведомление о вызове инструмента"""
        try:
            # Получаем название инструмента
            tool_name = None
            if hasattr(action, 'tool'):
                tool_name = action.tool
            elif isinstance(action, dict):
                tool_name = action.get('tool', 'unknown')
            else:
                tool_name = str(action)
            
            # Получаем входные параметры
            tool_input = None
            if hasattr(action, 'tool_input'):
                tool_input = action.tool_input
            elif isinstance(action, dict):
                tool_input = action.get('tool_input', {})
            
            # Сохраняем информацию о действии для последующего использования в on_tool_end
            self.current_action = {
                'tool_name': tool_name,
                'tool_input': tool_input
            }
            
            # Формируем текст уведомления
            if tool_name:
                # Переводим названия инструментов на русский для лучшего понимания
                tool_names_ru = {
                    'get_stock_quotes': 'Получение котировок акций',
                    'get_russian_stock_quotes': 'Получение котировок российских акций',
                    'get_financial_metrics': 'Получение финансовых метрик',
                    'get_company_financials': 'Получение финансовой отчетности',
                    'search_vector_db': 'Поиск в базе знаний',
                    'search_web': 'Поиск в интернете',
                    'create_visualization': 'Создание визуализации'
                }
                tool_display_name = tool_names_ru.get(tool_name, tool_name)
                
                # Формируем сообщение в формате "Вызываю <tool_name>. Входные данные: <данные>"
                # Используем оригинальное название инструмента для точности
                tool_name_display = tool_name
                
                # Формируем строку с входными данными
                input_data_str = ""
                if tool_input:
                    if isinstance(tool_input, dict):
                        # Форматируем JSON красиво
                        try:
                            input_data_str = json.dumps(tool_input, ensure_ascii=False, indent=0)
                            # Убираем переносы строк для компактности
                            input_data_str = input_data_str.replace('\n', ' ')
                        except:
                            input_data_str = str(tool_input)
                    else:
                        input_data_str = str(tool_input)
                
                if input_data_str:
                    notification_text = f"Вызываю {tool_name_display}. Входные данные: {input_data_str}"
                else:
                    notification_text = f"Вызываю {tool_name_display}"
                
                # НЕ обрезаем уведомления на бэкенде - они должны передаваться полностью
                # Обрезка будет на фронтенде для визуального отображения
                
                # Отправляем уведомление через callback
                if self.thought_callback:
                    self.thought_callback(notification_text, is_final=False)
        except Exception as e:
            print(f"[ERROR] Error in on_agent_action: {e}")
            import traceback
            print(traceback.format_exc())
        
        # Очищаем последний thought
        self.last_thought = None
    
    def on_tool_end(self, output, **kwargs):
        """Вызывается когда инструмент завершает работу - отправляем шаг"""
        try:
            if hasattr(self, 'current_action') and self.current_action and self.step_callback:
                self.step_counter += 1
                tool_name = self.current_action.get('tool_name')
                tool_input = self.current_action.get('tool_input')
                
                # Парсим output
                if isinstance(output, str):
                    try:
                        obs_data = json.loads(output)
                    except:
                        obs_data = {"observation": output}
                elif isinstance(output, dict):
                    obs_data = output
                else:
                    obs_data = {"observation": str(output)}
                
                step_data = {
                    "step_number": self.step_counter,
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "tool_result": obs_data,
                    "timestamp": datetime.now().isoformat()
                }
                
                # Отправляем шаг через callback
                self.step_callback(step_data)
                
                # Очищаем текущее действие
                self.current_action = None
        except KeyboardInterrupt:
            # Пробрасываем прерывание дальше
            raise
        except Exception as e:
            print(f"[ERROR] Error in on_tool_end: {e}")
            import traceback
            print(traceback.format_exc())


class AgentService:
    """Сервис для работы с агентом с поддержкой стриминга"""
    
    def __init__(self):
        self.agents: Dict[str, FinancialAgent] = {}
        self.active_threads: Dict[str, threading.Thread] = {}  # Активные потоки агента по session_id
        self.agent_results: Dict[str, Any] = {}  # Результаты выполнения агента
        self.logger = None
        if FinancialAgent is None:
            raise ImportError("Не удалось импортировать FinancialAgent. Убедитесь, что agent.py доступен.")
    
    def get_agent(self, session_id: str, use_memory: bool = True, clear_memory: bool = False) -> FinancialAgent:
        """
        Получить или создать агента для сессии
        
        Args:
            session_id: ID сессии
            use_memory: Использовать ли память диалога
            clear_memory: Очистить память перед использованием (для нового диалога)
        """
        # Если нужно очистить память - удаляем старого агента и создаем нового
        if clear_memory:
            if session_id in self.agents:
                del self.agents[session_id]
            # Создаем нового агента с чистой памятью
            self.agents[session_id] = FinancialAgent(use_memory=use_memory)
        elif session_id not in self.agents:
            # Создаем нового агента если его еще нет
            self.agents[session_id] = FinancialAgent(use_memory=use_memory)
        
        return self.agents[session_id]
    
    def clear_agent_memory(self, session_id: str):
        """Очистить память агента для указанной сессии"""
        if session_id in self.agents:
            agent = self.agents[session_id]
            if agent.memory:
                agent.memory.clear()
    
    async def stream_agent_response(
        self, 
        query: str, 
        session_id: str, 
        use_memory: bool = True
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Стриминг ответа агента с промежуточными шагами в реальном времени
        
        Yields:
            Словари с данными для стриминга
        """
        
        agent = self.get_agent(session_id, use_memory)
        
        try:
            # Отправляем начальное сообщение
            yield {
                "type": "start",
                "data": {
                    "query": query,
                    "session_id": session_id,
                    "timestamp": datetime.now().isoformat()
                }
            }
            
            # Проверяем, является ли вопрос простым приветствием
            simple_greetings = ["привет", "здравствуй", "здравствуйте", "hi", "hello", "hey", "как дела", "как поживаешь"]
            query_lower = query.lower().strip()
            
            # Если это простое приветствие - отвечаем сразу
            if any(greeting in query_lower for greeting in simple_greetings) and len(query.split()) <= 3:
                simple_response = "Привет! Чем могу помочь? Я могу помочь с анализом акций, получением котировок, финансовых метрик и другой финансовой информацией."
                yield {
                    "type": "final",
                    "data": {
                        "answer": simple_response,
                        "sources": [],
                        "steps": [],
                        "timestamp": datetime.now().isoformat()
                    }
                }
                return
            
            # Список для хранения текущих thoughts
            current_thoughts = []
            thought_queue = asyncio.Queue()
            step_queue = asyncio.Queue()
            
            # Callback для обработки thoughts
            def on_thought(thought_text: str, is_final: bool = False):
                """Callback для обработки thought"""
                try:
                    print(f"[DEBUG] on_thought callback called with: {thought_text[:100]}...")
                    print(f"[DEBUG] Queue size before adding: {thought_queue.qsize()}")
                    thought_queue.put_nowait({
                        "text": thought_text,
                        "is_final": is_final
                    })
                    print(f"[DEBUG] Thought added to queue successfully, queue size: {thought_queue.qsize()}")
                except Exception as e:
                    print(f"[ERROR] Error in on_thought callback: {e}")
                    import traceback
                    print(traceback.format_exc())
            
            # Callback для обработки шагов
            def on_step(step_data: Dict[str, Any]):
                """Callback для обработки шага"""
                try:
                    print(f"[DEBUG] on_step called with step {step_data.get('step_number')}")
                    step_queue.put_nowait(step_data)
                    print(f"[DEBUG] Step added to queue, queue size: {step_queue.qsize()}")
                except Exception as e:
                    print(f"[ERROR] Error in on_step: {e}")
                    import traceback
                    print(traceback.format_exc())
            
            # Создаем callback handler
            thought_handler = ThoughtCallbackHandler(
                thought_callback=on_thought,
                step_callback=on_step
            ) if BaseCallbackHandler else None
            
            # Запускаем агента в отдельном потоке для неблокирующего выполнения
            agent_result = {"done": False, "result": None, "exception": None}
            
            def run_agent():
                try:
                    # Если есть callback handler, используем его
                    if thought_handler:
                        result = agent.agent_executor.invoke(
                            {"input": query},
                            config={"callbacks": [thought_handler]}
                        )
                    else:
                        result = agent.agent_executor.invoke({"input": query})
                    agent_result["result"] = result
                    agent_result["done"] = True
                except Exception as e:
                    agent_result["result"] = {"error": str(e), "error_type": type(e).__name__}
                    agent_result["done"] = True
                    agent_result["exception"] = e
            
            # Сохраняем результат ДО создания потока, чтобы stop_agent мог его найти
            self.agent_results[session_id] = agent_result
            
            # Запускаем агента в отдельном потоке
            agent_thread = threading.Thread(target=run_agent, daemon=True)
            
            # Сохраняем поток ДО старта, чтобы stop_agent мог его найти
            self.active_threads[session_id] = agent_thread
            
            # Теперь запускаем поток
            agent_thread.start()
            
            # Обрабатываем thoughts и шаги параллельно с выполнением агента
            while not agent_result["done"] and agent_thread.is_alive():
                
                try:
                    # Сначала проверяем thoughts (с очень коротким таймаутом для быстрой реакции на stop)
                    try:
                        thought_data = await asyncio.wait_for(thought_queue.get(), timeout=0.01)
                        print(f"[DEBUG] Got thought from queue: {thought_data['text'][:100]}...")
                        print(f"[DEBUG] Current thoughts list: {[t[:50] for t in current_thoughts]}")
                        if thought_data["text"] not in current_thoughts:
                            current_thoughts.append(thought_data["text"])
                            print(f"[DEBUG] Yielding thought chunk to WebSocket")
                            yield {
                                "type": "thought",
                                "data": {
                                    "text": thought_data["text"],
                                    "is_final": thought_data["is_final"],
                                    "timestamp": datetime.now().isoformat()
                                }
                            }
                            print(f"[DEBUG] Thought chunk yielded successfully")
                        else:
                            print(f"[DEBUG] Thought already in current_thoughts, skipping")
                        continue
                    except asyncio.TimeoutError:
                        pass
                    
                    # Затем проверяем шаги (с очень коротким таймаутом для быстрой реакции на stop)
                    try:
                        step_data = await asyncio.wait_for(step_queue.get(), timeout=0.01)
                        print(f"[DEBUG] Got step from queue: step {step_data.get('step_number')}")
                        # НЕ удаляем thought перед отправкой шага - мысли должны оставаться
                        # Отправляем шаг (но не показываем его в ToolStepViewer)
                        yield {
                            "type": "step",
                            "data": step_data
                        }
                        continue
                    except asyncio.TimeoutError:
                        pass
                    
                    # Если ничего не получили, небольшая задержка
                    await asyncio.sleep(0.01)
                except Exception as e:
                    print(f"[ERROR] Error processing thoughts/steps: {e}")
                    import traceback
                    print(traceback.format_exc())
                    break
            
            # Ждем завершения потока
            agent_thread.join(timeout=300)  # Максимум 5 минут
            
            # Получаем результат агента
            result = agent_result.get("result")
            
            if not result:
                # Если результат не получен, возможно произошла ошибка
                if agent_result.get("exception"):
                    result = {"error": str(agent_result["exception"]), "error_type": type(agent_result["exception"]).__name__}
                else:
                    return
                
            if "error" in result:
                yield {
                    "type": "error",
                    "data": {
                        "error": result["error"],
                        "error_type": result.get("error_type", "UnknownError"),
                        "timestamp": datetime.now().isoformat()
                    }
                }
                return
            
            # Удаляем все thoughts перед отправкой шагов
            if current_thoughts:
                yield {
                    "type": "thought_remove",
                    "data": {
                        "timestamp": datetime.now().isoformat()
                    }
                }
            
            # Обрабатываем оставшиеся thoughts и шаги из очереди
            # (на случай, если что-то осталось после завершения агента)
            while not thought_queue.empty() or not step_queue.empty():
                try:
                    # Сначала thoughts
                    if not thought_queue.empty():
                        try:
                            thought_data = thought_queue.get_nowait()
                            if thought_data["text"] not in current_thoughts:
                                current_thoughts.append(thought_data["text"])
                                yield {
                                    "type": "thought",
                                    "data": {
                                        "text": thought_data["text"],
                                        "is_final": thought_data["is_final"],
                                        "timestamp": datetime.now().isoformat()
                                    }
                                }
                        except:
                            pass
                    
                    # Затем шаги
                    if not step_queue.empty():
                        try:
                            step_data = step_queue.get_nowait()
                            # НЕ удаляем thought - мысли должны оставаться
                            yield {
                                "type": "step",
                                "data": step_data
                            }
                        except:
                            pass
                    
                    await asyncio.sleep(0.01)
                except:
                    break
            
            # Собираем все шаги для финального ответа (для источников и т.д.)
            steps = []
            if "intermediate_steps" in result:
                for i, (action, observation) in enumerate(result["intermediate_steps"]):
                    # Извлекаем информацию о действии
                    tool_name = action.tool if hasattr(action, 'tool') else str(action)
                    tool_input = action.tool_input if hasattr(action, 'tool_input') else str(action)
                    
                    # Парсим observation
                    if isinstance(observation, str):
                        try:
                            obs_data = json.loads(observation)
                        except:
                            obs_data = {"observation": observation}
                    elif isinstance(observation, dict):
                        obs_data = observation
                    else:
                        obs_data = {"observation": str(observation)}
                    
                    step_data = {
                        "step_number": i + 1,
                        "tool_name": tool_name,
                        "tool_input": tool_input,
                        "tool_result": obs_data,
                        "timestamp": datetime.now().isoformat()
                    }
                    steps.append(step_data)
            
            # Получаем финальный ответ
            final_answer = result.get("output", "Нет ответа")
            
            # Извлекаем источники
            sources = agent._extract_sources(result) if hasattr(agent, '_extract_sources') else []
            
            # Отправляем финальный ответ сразу (без стриминга по словам)
            yield {
                "type": "final",
                "data": {
                    "answer": final_answer,
                    "sources": sources,
                    "steps": steps,
                    "timestamp": datetime.now().isoformat()
                }
            }
            
        except Exception as e:
            error_msg = str(e)
            yield {
                "type": "error",
                "data": {
                    "error": error_msg,
                    "error_type": type(e).__name__,
                    "timestamp": datetime.now().isoformat()
                }
            }
        finally:
            # Очищаем поток и результат
            if session_id in self.active_threads:
                del self.active_threads[session_id]
            if session_id in self.agent_results:
                del self.agent_results[session_id]


# Глобальный экземпляр сервиса
agent_service = AgentService()

