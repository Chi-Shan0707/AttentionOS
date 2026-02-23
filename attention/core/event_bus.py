"""
EventBus - Attention OS 统一事件系统

所有模块通过事件总线进行松耦合通信。
插件系统基于此事件总线实现扩展。

事件命名规范：
  - monitor.cycle_complete   监控周期完成（携带 FusedState）
  - monitor.screenshot       截图完成
  - monitor.analysis         分析完成
  - nudge.triggered          提醒触发
  - nudge.dismissed          提醒被用户忽略
  - pomodoro.started         番茄钟开始
  - pomodoro.completed       番茄钟完成
  - pomodoro.break_started   休息开始
  - goal.added               目标添加
  - goal.completed           目标完成
  - briefing.completed       Briefing 完成
  - review.generated         一日回顾生成
  - plugin.loaded            插件加载
  - plugin.error             插件错误

使用方法：
  from attention.core.event_bus import get_event_bus

  bus = get_event_bus()
  bus.on("monitor.cycle_complete", my_handler)
  bus.emit("monitor.cycle_complete", {"fused_state": fused})
"""
import logging
import threading
import traceback
from collections import defaultdict
from typing import Callable, Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class EventBus:
    """
    线程安全的同步事件总线。

    支持：
    - 事件注册/注销
    - 带优先级的监听器（priority 越小越先执行）
    - 通配符监听（"*" 可监听所有事件）
    - 一次性监听器（once）
    """

    def __init__(self):
        self._handlers: Dict[str, List[dict]] = defaultdict(list)
        self._lock = threading.Lock()
        self._event_history: List[dict] = []  # 最近事件（用于调试）
        self._history_limit = 100

    def on(
        self,
        event: str,
        handler: Callable,
        *,
        priority: int = 100,
        once: bool = False,
        source: str = "",
    ) -> str:
        """
        注册事件监听器。

        Args:
            event:    事件名称（如 "monitor.cycle_complete"）
            handler:  回调函数，签名为 handler(event_name: str, data: dict)
            priority: 优先级，数值越小越先执行（默认 100）
            once:     是否只触发一次后自动移除
            source:   注册来源标识（用于调试和插件管理）

        Returns:
            监听器 ID（可用于 off() 注销）
        """
        listener_id = f"{event}:{id(handler)}:{source}"
        entry = {
            "id": listener_id,
            "handler": handler,
            "priority": priority,
            "once": once,
            "source": source,
        }
        with self._lock:
            self._handlers[event].append(entry)
            self._handlers[event].sort(key=lambda h: h["priority"])
        logger.debug(f"EventBus: 注册监听器 [{event}] source={source} priority={priority}")
        return listener_id

    def off(self, event: str, handler: Optional[Callable] = None, source: Optional[str] = None):
        """
        注销事件监听器。

        Args:
            event:   事件名称
            handler: 要移除的处理函数（不传则按 source 移除）
            source:  按来源标识移除
        """
        with self._lock:
            if event not in self._handlers:
                return
            before = len(self._handlers[event])
            if handler is not None:
                self._handlers[event] = [
                    h for h in self._handlers[event] if h["handler"] is not handler
                ]
            elif source is not None:
                self._handlers[event] = [
                    h for h in self._handlers[event] if h["source"] != source
                ]
            else:
                self._handlers[event] = []
            removed = before - len(self._handlers[event])
            if removed:
                logger.debug(f"EventBus: 移除 {removed} 个监听器 [{event}]")

    def off_all(self, source: str):
        """移除指定来源的所有监听器（用于插件卸载）。"""
        with self._lock:
            total_removed = 0
            for event in list(self._handlers.keys()):
                before = len(self._handlers[event])
                self._handlers[event] = [
                    h for h in self._handlers[event] if h["source"] != source
                ]
                total_removed += before - len(self._handlers[event])
            if total_removed:
                logger.info(f"EventBus: 移除来源 [{source}] 的 {total_removed} 个监听器")

    def emit(self, event: str, data: Optional[Dict[str, Any]] = None):
        """
        触发事件，按优先级依次调用所有监听器。

        Args:
            event: 事件名称
            data:  事件数据（dict）
        """
        if data is None:
            data = {}

        # 记录事件历史
        self._record_history(event, data)

        # 收集要调用的监听器（精确匹配 + 通配符）
        with self._lock:
            exact = list(self._handlers.get(event, []))
            wildcard = list(self._handlers.get("*", []))
            all_handlers = sorted(exact + wildcard, key=lambda h: h["priority"])

        # 在锁外执行回调
        once_ids = []
        for entry in all_handlers:
            try:
                entry["handler"](event, data)
            except Exception as e:
                source = entry.get("source", "unknown")
                logger.error(
                    f"EventBus: 监听器错误 [{event}] source={source}: {e}\n"
                    f"{traceback.format_exc()}"
                )
            if entry["once"]:
                once_ids.append(entry["id"])

        # 清理一次性监听器
        if once_ids:
            with self._lock:
                for evt_key in [event, "*"]:
                    if evt_key in self._handlers:
                        self._handlers[evt_key] = [
                            h for h in self._handlers[evt_key] if h["id"] not in once_ids
                        ]

    def _record_history(self, event: str, data: dict):
        """记录事件到历史（供调试用）。"""
        from datetime import datetime

        record = {
            "event": event,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "data_keys": list(data.keys()) if data else [],
        }
        self._event_history.append(record)
        if len(self._event_history) > self._history_limit:
            self._event_history = self._event_history[-self._history_limit:]

    def get_history(self, limit: int = 20) -> List[dict]:
        """获取最近的事件历史。"""
        return self._event_history[-limit:]

    def get_listeners(self, event: Optional[str] = None) -> List[dict]:
        """获取注册的监听器信息（供调试/插件管理 UI 使用）。"""
        with self._lock:
            if event:
                return [
                    {"id": h["id"], "source": h["source"], "priority": h["priority"], "event": event}
                    for h in self._handlers.get(event, [])
                ]
            result = []
            for evt, handlers in self._handlers.items():
                for h in handlers:
                    result.append({
                        "id": h["id"],
                        "source": h["source"],
                        "priority": h["priority"],
                        "event": evt,
                    })
            return result


# ============================================================
# 单例
# ============================================================

_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """获取全局 EventBus 单例。"""
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
