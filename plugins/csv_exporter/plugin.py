"""
CSV Exporter Plugin - CSV 数据导出插件

每个监控周期结束后将 FusedState 追加写入 CSV 文件，
方便用户在 Excel / Google Sheets 中进行自定义分析。
"""
import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

from attention.config import Config
from attention.core.plugin_interface import ExporterPlugin, PluginMeta

logger = logging.getLogger(__name__)


class CSVExporterPlugin(ExporterPlugin):
    """将每次监控数据追加导出到 CSV 文件。"""

    # CSV 表头
    CSV_HEADERS = [
        "timestamp",
        "attention_level",
        "user_engagement",
        "app_category",
        "is_productive",
        "is_distracted",
        "activity_ratio",
        "keyboard_events",
        "mouse_events",
        "window_switches",
        "active_window_app",
        "confidence",
    ]

    def _get_meta(self) -> PluginMeta:
        return PluginMeta(
            name="csv-exporter",
            display_name="CSV Exporter",
            description="将监控数据实时导出到 CSV 文件，可在 Excel 中分析",
            version="1.0.0",
            author="AttentionOS",
            tags=["exporter", "csv", "data", "built-in"],
        )

    def get_default_config(self) -> Dict[str, Any]:
        return {
            "output_dir": str(Config.DATA_DIR / "exports"),
            "file_per_day": True,  # 每天一个文件 vs 一个大文件
        }

    def get_config_schema(self) -> List[Dict[str, Any]]:
        return [
            {
                "key": "output_dir",
                "label": "Output Directory",
                "type": "text",
                "required": True,
            },
            {
                "key": "file_per_day",
                "label": "File Per Day",
                "type": "boolean",
                "required": False,
            },
        ]

    def export(self, event: str, data: dict):
        """将 FusedState 写入 CSV。"""
        fused = data.get("fused_state", {})
        if not fused:
            return

        try:
            output_dir = Path(self.config.get("output_dir", str(Config.DATA_DIR / "exports")))
            output_dir.mkdir(parents=True, exist_ok=True)

            if self.config.get("file_per_day", True):
                date_str = datetime.now().strftime("%Y-%m-%d")
                csv_path = output_dir / f"attention_{date_str}.csv"
            else:
                csv_path = output_dir / "attention_log.csv"

            file_exists = csv_path.exists()

            with open(csv_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.CSV_HEADERS)
                if not file_exists:
                    writer.writeheader()

                row = {}
                for header in self.CSV_HEADERS:
                    if header == "timestamp":
                        row[header] = data.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    else:
                        row[header] = fused.get(header, "")
                writer.writerow(row)

        except Exception as e:
            logger.warning(f"[csv-exporter] 导出失败: {e}")

    def activate(self):
        self.event_bus.on(
            "monitor.cycle_complete",
            self.export,
            source=self.get_meta().name,
        )
        logger.info("[csv-exporter] CSV 导出插件已激活")

    def deactivate(self):
        logger.info("[csv-exporter] CSV 导出插件已停用")
