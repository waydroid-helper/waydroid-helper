import logging
import os
import sys
import multiprocessing
from multiprocessing import Queue
import threading
from typing import Any
import queue
import pickle

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib


class MultiprocessingQueueHandler(logging.Handler):
    """多进程安全的队列处理器"""
    
    def __init__(self, queue):
        super().__init__()
        self.queue = queue
        self._lock = threading.Lock()
    
    def emit(self, record):
        try:
            with self._lock:
                # 确保进程信息字段存在
                if not hasattr(record, 'process_id'):
                    record.process_id = multiprocessing.current_process().pid
                if not hasattr(record, 'process_name'):
                    record.process_name = multiprocessing.current_process().name
                
                # 检查记录是否可序列化
                try:
                    pickle.dumps(record)
                except (pickle.PicklingError, TypeError):
                    # 创建简化的可序列化记录
                    record = self._create_serializable_record(record)
                
                # 序列化记录并放入队列
                self.queue.put_nowait(record)
        except queue.Full:
            # 如果队列满了，回退到标准错误输出
            sys.stderr.write(f"Log queue full: {record.getMessage()}\n")
        except Exception as e:
            # 其他错误，回退到标准输出
            sys.stderr.write(f"Log queue error: {record.getMessage()}\n")
    
    def _create_serializable_record(self, original_record):
        """创建可序列化的日志记录"""
        try:
            simple_record = logging.LogRecord(
                name=original_record.name,
                level=original_record.levelno,
                pathname=original_record.pathname,
                lineno=original_record.lineno,
                msg=str(original_record.getMessage()),
                args=(),
                exc_info=None
            )
            simple_record.process_id = getattr(original_record, 'process_id', os.getpid())
            simple_record.process_name = getattr(original_record, 'process_name', 'Unknown')
            return simple_record
        except Exception:
            return original_record


class MultiprocessingFileHandler(logging.Handler):
    def __init__(self, filename, mode='a', encoding='utf-8'):
        super().__init__()
        self.filename = filename
        self.mode = mode
        self.encoding = encoding
        self._lock = threading.Lock()
        self._ensure_log_directory()
    
    def _ensure_log_directory(self):
        """确保日志目录存在"""
        try:
            log_dir = os.path.dirname(self.filename)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, mode=0o755, exist_ok=True)
        except OSError:
            pass  # 如果创建失败，继续执行，文件操作时会处理
    
    def emit(self, record):
        try:
            with self._lock:
                # 确保进程信息字段存在
                if not hasattr(record, 'process_id'):
                    record.process_id = multiprocessing.current_process().pid
                if not hasattr(record, 'process_name'):
                    record.process_name = multiprocessing.current_process().name
                
                # 格式化日志消息
                msg = self.format(record)
                with open(self.filename, self.mode, encoding=self.encoding) as f:
                    f.write(msg + '\n')
                    f.flush()
        except Exception:
            # 如果文件写入失败，回退到标准输出
            sys.stderr.write(f"Log file error: {record.getMessage()}\n")


class SafeFormatter(logging.Formatter):
    """安全的日志格式化器，处理缺失字段"""
    
    def format(self, record):
        # 确保进程信息字段存在
        if not hasattr(record, 'process_id'):
            record.process_id = multiprocessing.current_process().pid
        if not hasattr(record, 'process_name'):
            record.process_name = multiprocessing.current_process().name
        
        try:
            return super().format(record)
        except (KeyError, ValueError, AttributeError) as e:
            # 如果格式化失败，使用安全的回退格式
            return self._create_fallback_format(record)
    
    def _create_fallback_format(self, record):
        """创建回退格式"""
        try:
            process_name = getattr(record, 'process_name', 'Unknown')
            process_id = getattr(record, 'process_id', 0)
            level_name = getattr(record, 'levelname', 'INFO')
            filename = getattr(record, 'filename', 'unknown.py')
            lineno = getattr(record, 'lineno', 0)
            
            # 使用 record.created 时间戳创建时间字符串
            import time
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created))
            
            return f"[{level_name}][{timestamp}][{process_name}:{process_id}][{filename}:{lineno}] - {record.getMessage()}"
        except Exception:
            return f"[LOG_FORMAT_ERROR] - {record.getMessage()}"


def _reset_logger(log: logging.Logger):
    """重置日志器配置"""
    handlers_to_remove = log.handlers[:]  # 创建副本避免迭代时修改
    for handler in handlers_to_remove:
        try:
            handler.close()
        except Exception:
            pass
        try:
            log.removeHandler(handler)
        except Exception:
            pass
    log.handlers.clear()
    log.propagate = False


def _get_logger(log_level: str|None = None, log_queue=None):
    """获取日志器实例
    
    Args:
        log_level: 日志级别
        log_queue: 日志队列（所有进程都使用队列，只有监听器进程不用）
    """
    log = logging.getLogger("log")
    
    # 检查是否已经配置过
    if log.handlers:
        return log
    
    _reset_logger(log)
    
    # 获取当前进程信息
    current_process = multiprocessing.current_process()
    
    if log_queue and current_process.name != "LogListener":
        # 所有非监听器进程：只使用队列处理器
        queue_handler = MultiprocessingQueueHandler(log_queue)
        queue_handler.setFormatter(
            SafeFormatter(
                "[%(levelname)s][%(asctime)s][%(process_name)s:%(process_id)d][%(filename)s:%(lineno)d] - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        
        log.addHandler(queue_handler)
    else:
        # 监听器进程：使用文件处理器和控制台处理器
        formatter = SafeFormatter(
            "[%(levelname)s][%(asctime)s][%(process_name)s:%(process_id)d][%(filename)s:%(lineno)d] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        
        console_handle = logging.StreamHandler(sys.stdout)
        console_handle.setFormatter(formatter)
        
        try:
            log_file = os.path.join(
                os.getenv("XDG_CACHE_HOME", GLib.get_user_cache_dir()),
                "waydroid-helper",
                "waydroid-helper.log",
            )
            file_handle = MultiprocessingFileHandler(log_file, encoding="utf-8")
            file_handle.setFormatter(formatter)
            log.addHandler(file_handle)
        except Exception as e:
            # 如果文件处理器创建失败，只使用控制台处理器
            sys.stderr.write(f"Failed to create file handler: {e}\n")
        
        log.addHandler(console_handle)
    
    # 设置日志级别
    if log_level is not None:
        log_level_str = log_level.upper()
        level: int = getattr(logging, log_level_str, logging.INFO)
        log.setLevel(level)
    else:
        log.setLevel(logging.INFO)
    
    return log


def setup_main_process_logging(log_level: str|None = None):
    """设置主进程的日志系统
    
    Args:
        log_level: 日志级别
        
    Returns:
        tuple: (logger, log_queue, listener_process)
    """
    # 创建日志队列，设置合理的最大大小
    log_queue = Queue(maxsize=1000)
    
    # 启动日志监听器进程
    listener_process = multiprocessing.Process(
        target=_log_listener_process,
        args=(log_queue, log_level),
        name="LogListener"
    )
    listener_process.start()
    
    # 获取主进程日志器 - 使用队列处理器
    logger = _get_logger(log_level, log_queue=log_queue)
    
    return logger, log_queue, listener_process


def get_subprocess_logger(log_level: str|None = None, log_queue=None):
    """为子进程获取日志器
    
    Args:
        log_level: 日志级别
        log_queue: 主进程传入的日志队列
    """
    return _get_logger(log_level, log_queue=log_queue)


def _log_listener_process(log_queue, log_level: str|None = None):
    """日志监听器进程，负责将队列中的日志写入文件和控制台"""
    try:
        # 设置进程名称
        multiprocessing.current_process().name = "LogListener"
        
        # 清空日志文件（应用启动时）
        try:
            log_file = os.path.join(
                os.getenv("XDG_CACHE_HOME", GLib.get_user_cache_dir()),
                "waydroid-helper",
                "waydroid-helper.log",
            )
            # 确保日志目录存在
            log_dir = os.path.dirname(log_file)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, mode=0o755, exist_ok=True)
            # 清空日志文件
            with open(log_file, 'w', encoding='utf-8') as f:
                pass
        except Exception as e:
            sys.stderr.write(f"Failed to clear log file: {e}\n")
        
        # 获取日志器 - 监听器进程使用文件处理器和控制台处理器，不使用队列
        logger = _get_logger(log_level, log_queue=None)
        
        # 监听队列中的日志记录
        while True:
            try:
                # 使用超时避免无限阻塞
                record = log_queue.get(timeout=1.0)
                if record is None:  # 退出信号
                    break
                logger.handle(record)
            except queue.Empty:
                continue  # 超时继续等待
            except Exception as e:
                # 如果处理日志记录失败，写入标准错误
                sys.stderr.write(f"Log listener error: {e}\n")
    except KeyboardInterrupt:
        # 处理中断信号
        pass
    except Exception as e:
        sys.stderr.write(f"Log listener process failed: {e}\n")
    finally:
        # 处理队列中剩余的日志
        try:
            while True:
                try:
                    record = log_queue.get_nowait()
                    if record is not None:
                        logger.handle(record)
                except queue.Empty:
                    break
        except Exception:
            pass


def cleanup_logging():
    """清理日志资源 - 应在PyGObject应用程序的do_shutdown中调用"""
    global _log_queue, _log_listener
    
    try:
        if _log_queue is not None:
            # 发送退出信号
            _log_queue.put(None, timeout=1.0)
    except Exception:
        pass
    
    if _log_listener is not None and _log_listener.is_alive():
        try:
            _log_listener.join(timeout=2.0)  # 等待最多2秒
            if _log_listener.is_alive():
                _log_listener.terminate()  # 强制终止
        except Exception:
            pass


# 全局变量，用于清理
_log_queue = None
_log_listener = None


# PyGObject应用程序不使用atexit，而是在应用程序的do_shutdown中清理资源


# 检查是否在主进程中
_is_main_process = multiprocessing.current_process().name == "MainProcess"

if _is_main_process:
    # 主进程：使用队列处理器，通过监听器进程写入文件
    logger, _log_queue, _log_listener = setup_main_process_logging(
        os.environ.get('LOG_LEVEL', '')
    )
else:
    # 子进程：也使用队列处理器，需要从父进程传入log_queue
    # 注意：子进程需要通过某种方式获得log_queue的引用
    # 这里暂时使用直接文件处理器作为回退，但理想情况下应该使用队列
    logger = _get_logger(os.environ.get('LOG_LEVEL', ''), log_queue=None)