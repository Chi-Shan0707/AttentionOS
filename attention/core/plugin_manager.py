"""
PluginManager - Attention OS 插件管理器

职责：
  - 自动发现 plugins/ 目录下的插件
  - 加载、激活、停用插件
  - 管理插件配置持久化
  - 提供插件列表 API（供 Web UI 使用）

目录结构约定：
  plugins/
    my_plugin/
      plugin.py        # 必须包含一个 BasePlugin 子类
      README.md        # 可选：插件说明
    another_plugin/
      plugin.py

插件配置持久化在 data/plugin_configs.json
"""
import importlib
import importlib.util
import json
import logging
import sys
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Any

from attention.config import Config
from attention.core.event_bus import get_event_bus
from attention.core.plugin_interface import BasePlugin

logger = logging.getLogger(__name__)

PLUGIN_CONFIG_FILE = Config.DATA_DIR / "plugin_configs.json"


class PluginManager:
    """插件管理器。"""

    def __init__(self):
        self._plugins: Dict[str, dict] = {}  # name → {"instance": BasePlugin, "active": bool, ...}
        self._event_bus = get_event_bus()
        self._configs = self._load_configs()

    # ================================================================== #
    #  插件发现与加载
    # ================================================================== #

    def discover_plugins(self, plugin_dirs: Optional[List[str]] = None):
        """
        扫描插件目录，发现并注册所有可用插件。

        Args:
            plugin_dirs: 插件目录列表。默认为 [项目根目录/plugins]
        """
        if plugin_dirs is None:
            plugin_dirs = [str(Config.BASE_DIR / "plugins")]

        for dir_path in plugin_dirs:
            plugin_dir = Path(dir_path)
            if not plugin_dir.exists():
                logger.debug(f"插件目录不存在，跳过: {plugin_dir}")
                continue

            for candidate in sorted(plugin_dir.iterdir()):
                if not candidate.is_dir():
                    continue
                if candidate.name.startswith("_") or candidate.name.startswith("."):
                    continue

                plugin_file = candidate / "plugin.py"
                if not plugin_file.exists():
                    continue

                try:
                    self._load_plugin(candidate.name, plugin_file)
                except Exception as e:
                    logger.error(f"加载插件 [{candidate.name}] 失败: {e}\n{traceback.format_exc()}")

    def _load_plugin(self, dir_name: str, plugin_file: Path):
        """加载单个插件模块，找到 BasePlugin 子类并注册。"""
        module_name = f"plugins.{dir_name}.plugin"

        spec = importlib.util.spec_from_file_location(module_name, str(plugin_file))
        if spec is None or spec.loader is None:
            raise ImportError(f"无法加载模块: {plugin_file}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # 查找 BasePlugin 子类
        plugin_class = None
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BasePlugin)
                and attr is not BasePlugin
                and not attr.__name__.startswith("_")
                # 跳过接口基类本身
                and attr.__module__ == module_name
            ):
                plugin_class = attr
                break

        if plugin_class is None:
            raise ImportError(f"未找到 BasePlugin 子类: {plugin_file}")

        # 实例化
        instance = plugin_class()
        meta = instance.get_meta()
        name = meta.name

        if name in self._plugins:
            logger.warning(f"插件名称冲突，跳过: {name}")
            return

        # 注入 event_bus
        instance.event_bus = self._event_bus

        # 注入配置
        default_config = instance.get_default_config()
        saved_config = self._configs.get(name, {}).get("config", {})
        merged = {**default_config, **saved_config}
        instance.config = merged

        # 注册
        self._plugins[name] = {
            "instance": instance,
            "meta": meta,
            "active": False,
            "error": None,
            "dir": str(plugin_file.parent),
        }

        logger.info(f"插件已注册: {meta.display_name} v{meta.version} [{name}]")

        # 如果之前是启用状态，自动激活
        if self._configs.get(name, {}).get("enabled", False):
            self.activate_plugin(name)

        # 触发事件
        self._event_bus.emit("plugin.loaded", {"name": name, "meta": meta.to_dict()})

    # ================================================================== #
    #  插件激活/停用
    # ================================================================== #

    def activate_plugin(self, name: str) -> bool:
        """激活指定插件。"""
        entry = self._plugins.get(name)
        if not entry:
            logger.warning(f"插件不存在: {name}")
            return False

        if entry["active"]:
            logger.debug(f"插件已经是激活状态: {name}")
            return True

        try:
            entry["instance"].activate()
            entry["active"] = True
            entry["error"] = None

            # 持久化启用状态
            self._update_config(name, enabled=True)

            logger.info(f"插件已激活: {name}")
            self._event_bus.emit("plugin.activated", {"name": name})
            return True

        except Exception as e:
            entry["error"] = str(e)
            logger.error(f"插件激活失败 [{name}]: {e}\n{traceback.format_exc()}")
            self._event_bus.emit("plugin.error", {"name": name, "error": str(e)})
            return False

    def deactivate_plugin(self, name: str) -> bool:
        """停用指定插件。"""
        entry = self._plugins.get(name)
        if not entry:
            return False

        if not entry["active"]:
            return True

        try:
            entry["instance"].deactivate()
        except Exception as e:
            logger.warning(f"插件停用回调出错 [{name}]: {e}")

        # 清理该插件注册的所有事件监听
        self._event_bus.off_all(source=name)

        entry["active"] = False
        entry["error"] = None

        # 持久化
        self._update_config(name, enabled=False)

        logger.info(f"插件已停用: {name}")
        self._event_bus.emit("plugin.deactivated", {"name": name})
        return True

    def deactivate_all(self):
        """停用所有插件（用于关闭时清理）。"""
        for name in list(self._plugins.keys()):
            if self._plugins[name]["active"]:
                self.deactivate_plugin(name)

    # ================================================================== #
    #  插件查询
    # ================================================================== #

    def list_plugins(self) -> List[dict]:
        """获取所有已注册插件的信息列表。"""
        result = []
        for name, entry in self._plugins.items():
            meta = entry["meta"]
            result.append({
                **meta.to_dict(),
                "active": entry["active"],
                "error": entry["error"],
                "config": entry["instance"].config,
                "config_schema": entry["instance"].get_config_schema(),
                "dir": entry["dir"],
            })
        return result

    def get_plugin(self, name: str) -> Optional[BasePlugin]:
        """获取插件实例。"""
        entry = self._plugins.get(name)
        return entry["instance"] if entry else None

    def is_active(self, name: str) -> bool:
        """检查插件是否已激活。"""
        entry = self._plugins.get(name)
        return entry["active"] if entry else False

    # ================================================================== #
    #  插件配置
    # ================================================================== #

    def update_plugin_config(self, name: str, new_config: Dict[str, Any]) -> bool:
        """更新插件配置。"""
        entry = self._plugins.get(name)
        if not entry:
            return False

        instance = entry["instance"]
        merged = {**instance.config, **new_config}
        instance.config = merged

        # 通知插件配置变更
        try:
            instance.on_config_changed(merged)
        except Exception as e:
            logger.warning(f"插件配置变更回调出错 [{name}]: {e}")

        # 持久化
        self._update_config(name, config=merged)
        return True

    def _update_config(self, name: str, **updates):
        """更新并持久化插件配置。"""
        if name not in self._configs:
            self._configs[name] = {}
        self._configs[name].update(updates)
        self._save_configs()

    def _load_configs(self) -> Dict[str, dict]:
        """从磁盘加载插件配置。"""
        try:
            if PLUGIN_CONFIG_FILE.exists():
                with open(PLUGIN_CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"加载插件配置失败: {e}")
        return {}

    def _save_configs(self):
        """持久化插件配置到磁盘。"""
        Config.ensure_dirs()
        try:
            with open(PLUGIN_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self._configs, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error(f"保存插件配置失败: {e}")


# ============================================================
# 单例
# ============================================================

_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    """获取 PluginManager 单例。"""
    global _manager
    if _manager is None:
        _manager = PluginManager()
    return _manager
