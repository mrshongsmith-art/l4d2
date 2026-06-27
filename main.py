import asyncio
import os
import re
import tempfile
from pathlib import Path

from astrbot.api.all import *
from astrbot.api.event import filter
from astrbot.core.message.components import File, Node, Nodes, Plain
from astrbot.core.utils.io import download_file

from .config_manager import ConfigManager
from .server_query import L4D2Server
from .web_manager import L4D2WebManager, WebManagerError
from .workshop_utils import WorkshopTools


@register("l4d2", "l4d2", "L4D2服务器管理插件", "1.0.0")
class L4D2Plugin(Star):
    OFFICIAL_MAPS = [
        "c1m1_hotel | 死亡中心 - 旅馆",
        "c1m2_streets | 死亡中心 - 街道",
        "c1m3_mall | 死亡中心 - 购物中心",
        "c1m4_atrium | 死亡中心 - 中厅",
        "c2m1_highway | 黑色狂欢节 - 高速公路",
        "c2m2_fairgrounds | 黑色狂欢节 - 游乐场",
        "c2m3_coaster | 黑色狂欢节 - 过山车",
        "c2m4_barns | 黑色狂欢节 - 谷仓",
        "c2m5_concert | 黑色狂欢节 - 音乐会",
        "c3m1_plankcountry | 沼泽激战 - 乡村",
        "c3m2_swamp | 沼泽激战 - 沼泽",
        "c3m3_shantytown | 沼泽激战 - 贫民窟",
        "c3m4_plantation | 沼泽激战 - 种植园",
        "c4m1_milltown_a | 暴风骤雨 - 小镇",
        "c4m2_sugarmill_a | 暴风骤雨 - 糖厂",
        "c4m3_sugarmill_b | 暴风骤雨 - 逃离糖厂",
        "c4m4_milltown_b | 暴风骤雨 - 重返小镇",
        "c4m5_milltown_escape | 暴风骤雨 - 逃离小镇",
        "c5m1_waterfront | 教区 - 码头",
        "c5m2_park | 教区 - 公园",
        "c5m3_cemetery | 教区 - 墓地",
        "c5m4_quarter | 教区 - 特区",
        "c5m5_bridge | 教区 - 大桥",
        "c6m1_riverbank | 消逝 - 河畔",
        "c6m2_bedlam | 消逝 - 地下通道",
        "c6m3_port | 消逝 - 港口",
        "c7m1_docks | 牺牲 - 码头",
        "c7m2_barge | 牺牲 - 驳船",
        "c7m3_port | 牺牲 - 港口",
        "c8m1_apartment | 毫不留情 - 公寓",
        "c8m2_subway | 毫不留情 - 地铁",
        "c8m3_sewers | 毫不留情 - 下水道",
        "c8m4_interior | 毫不留情 - 医院",
        "c8m5_rooftop | 毫不留情 - 屋顶",
        "c9m1_alleys | 坠机险途 - 小巷",
        "c9m2_lots | 坠机险途 - 卡车停车场",
        "c10m1_caves | 死亡丧钟 - 收费公路",
        "c10m2_drainage | 死亡丧钟 - 水沟",
        "c10m3_ranchhouse | 死亡丧钟 - 教堂",
        "c10m4_mainstreet | 死亡丧钟 - 小镇",
        "c10m5_houseboat | 死亡丧钟 - 码头",
        "c11m1_greenhouse | 静寂时分 - 温室",
        "c11m2_offices | 静寂时分 - 起重机",
        "c11m3_garage | 静寂时分 - 建筑工地",
        "c11m4_terminal | 静寂时分 - 航站楼",
        "c11m5_runway | 静寂时分 - 飞机跑道",
        "c12m1_hilltop | 血腥收获 - 森林",
        "c12m2_traintunnel | 血腥收获 - 隧道",
        "c12m3_bridge | 血腥收获 - 大桥",
        "c12m4_barn | 血腥收获 - 火车站",
        "c12m5_cornfield | 血腥收获 - 农舍",
        "c13m1_alpinecreek | 刺骨寒溪 - 高山小溪",
        "c13m2_southpinestream | 刺骨寒溪 - 南松溪",
        "c13m3_memorialbridge | 刺骨寒溪 - 纪念大桥",
        "c13m4_cutthroatcreek | 刺骨寒溪 - 割喉溪",
        "c14m1_junkyard | 背水一战 - 垃圾场",
        "c14m2_lighthouse | 背水一战 - 灯塔",
    ]

    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config_path = os.path.join(os.path.dirname(__file__), "config.json")
        self.cfg = ConfigManager(self.config_path, config)
        self.workshop = WorkshopTools()
        self.web_manager = L4D2WebManager(
            self.cfg.get_web_manager_base_url(), self.cfg.get_web_manager_token()
        )

    def _get_group_config(self, event: AstrMessageEvent):
        """获取当前群的配置"""
        try:
            current_group = event.get_group_id()
            if not current_group:
                message_obj = getattr(event, "message_obj", None)
                if isinstance(message_obj, dict):
                    current_group = message_obj.get("group_id")
                else:
                    current_group = getattr(message_obj, "group_id", None)
            if not current_group:
                return None
            return self.cfg.get_group_config(str(current_group))
        except Exception:
            return None
        return None

    def _get_server_config_by_name(self, servers: list, target_name: str):
        """按现有查询规则匹配服务器名（忽略空格）"""
        for server in servers:
            if server.get("name", "").replace(" ", "") == target_name:
                return server
        return None

    @filter.regex(r"^求生帮助$")
    async def help_card(self, event: AstrMessageEvent, *args, **kwargs):
        """发送插件功能卡片。"""
        group_conf = self._get_group_config(event)
        if not group_conf:
            return

        msg = (
            "=== 求生之路插件帮助 ===\n"
            "服务器:\n"
            "- 查询 / 查服 / 综合查询：查看服务器在线状态和连接指令\n"
            "- 切换官方图：查看官方图列表\n"
            "- 切换官方图2：切换到官方图编号 2\n"
            "- 切换地图 / 切换三方图：查看三方图列表\n"
            "- 切换地图1-2：切换到三方图编号 1 的第 2 小图\n"
            "\n地图管理:\n"
            "- 地图 / 地图列表：查看地图编号列表\n"
            "- 删除地图2：删除编号 2 的地图\n"
            "- 删除地图2-6：删除编号 2 到 6 的地图\n"
            "- 上传地图 文件名：从群文件添加地图下载任务，不用写后缀\n"
            "- 地图下载 <url>：添加地图下载任务\n"
            "- 下载任务：查看下载任务\n"
            "\n创意工坊:\n"
            "- 创意工坊 <链接> / 创意工坊解析 <链接>：自动加入下载任务并上传群文件\n"
        )
        yield event.plain_result(msg)

    @filter.regex(r"^(查询|查服|综合查询)$")
    async def query_server(self, event: AstrMessageEvent, *args, **kwargs):
        """查询唯一 L4D2 服务器状态。"""
        group_conf = self._get_group_config(event)
        if not group_conf:
            return

        server_config = self.cfg.get_server_config()
        yield event.plain_result("正在查询服务器状态...")

        loop = asyncio.get_running_loop()
        server = L4D2Server(server_config["name"], server_config["address"])
        info = await loop.run_in_executor(None, server.query_info)

        if not info:
            yield event.plain_result(
                f"无法连接到服务器 {server_config['address']}，可能服务器离线或网络问题。"
            )
            return

        map_display_name = await self._get_map_display_name(str(info["map_name"]))
        players = await loop.run_in_executor(None, server.query_players)

        msg = "=== L4D2 服务器状态 ===\n"
        msg += f"服务器: {info['server_name']}\n"
        msg += f"地图: {map_display_name}\n"
        msg += f"人数: {info['player_count']}/{info['max_players']}\n"
        msg += f"延迟: {info['ping']}ms\n"

        if players:
            msg += "\n在线玩家:\n"
            for player in players:
                duration = int(player["duration"])
                minutes, seconds = divmod(duration, 60)
                hours, minutes = divmod(minutes, 60)
                days, hours = divmod(hours, 24)
                if days > 0:
                    time_str = f"{days}:{hours:02d}:{minutes:02d}:{seconds:02d}"
                elif hours > 0:
                    time_str = f"{hours}:{minutes:02d}:{seconds:02d}"
                else:
                    time_str = f"{minutes}:{seconds:02d}"
                msg += f"- {player['name']} ({time_str})\n"
        else:
            msg += "\n当前无玩家在线。\n"

        msg += f"\n连接指令: connect {server_config['address']}"

        yield event.plain_result(msg)

    def _check_permission(self, event: AstrMessageEvent, admin_list: list) -> bool:
        """检查发送者是否在管理员列表中"""
        try:
            user_id = None
            obj = event.message_obj

            # 尝试获取 sender
            sender = None
            if isinstance(obj, dict):
                sender = obj.get("sender")
            elif hasattr(obj, "sender"):
                sender = getattr(obj, "sender")

            if sender:
                if isinstance(sender, dict):
                    user_id = sender.get("user_id")
                elif hasattr(sender, "user_id"):
                    user_id = getattr(sender, "user_id")

            if user_id and str(user_id) in [str(uid) for uid in admin_list]:
                return True

            return False
        except Exception as e:
            print(f"[L4D2Plugin] Error checking permission: {e}")
            return False

    def _has_admin_permission(self, event: AstrMessageEvent, group_conf: dict) -> bool:
        """Only plugin-configured admins can run important operations."""
        return self._check_permission(event, group_conf.get("admin_users", []))

    def _format_map_list(self, maps: list[dict[str, str]]) -> str:
        if not maps:
            return "当前没有地图文件。"

        lines = [f"=== 地图列表（共 {len(maps)} 个）==="]
        for index, item in enumerate(maps, start=1):
            size = item.get("size") or "未知大小"
            lines.append(f"{index}. {item.get('name', '')} ({size})")
        lines.append("可用：删除地图2 或 删除地图2-6")
        return "\n".join(lines)

    def _build_map_list_lines(self, maps: list[dict[str, str]]) -> list[str]:
        if not maps:
            return ["当前没有地图文件。"]

        lines = [f"=== 地图列表（共 {len(maps)} 个）==="]
        for index, item in enumerate(maps, start=1):
            size = item.get("size") or "未知大小"
            lines.append(f"{index}. {item.get('name', '')} ({size})")
        lines.append("可用：删除地图2 或 删除地图2-6")
        return lines

    def _split_text_chunks(self, lines: list[str], max_chars: int = 900) -> list[str]:
        chunks = []
        current = ""
        for line in lines:
            candidate = f"{current}\n{line}" if current else line
            if len(candidate) > max_chars and current:
                chunks.append(current)
                current = line
            else:
                current = candidate
        if current:
            chunks.append(current)
        return chunks

    def _build_map_list_nodes(
        self, event: AstrMessageEvent, maps: list[dict[str, str]]
    ) -> Nodes:
        lines = self._build_map_list_lines(maps)
        midpoint = max(1, (len(lines) + 1) // 2)
        chunks = ["\n".join(lines[:midpoint]), "\n".join(lines[midpoint:])]
        chunks = [chunk for chunk in chunks if chunk.strip()]
        uin = event.get_self_id() or event.get_sender_id() or "0"
        nodes = [
            Node(uin=uin, name="AstrBot", content=[Plain(chunk)]) for chunk in chunks
        ]
        return Nodes(nodes)

    def _format_download_tasks(self, tasks: list[dict]) -> str:
        if not tasks:
            return "当前没有下载任务。"

        status_map = {0: "等待中", 1: "下载中", 2: "已完成", 3: "失败"}
        lines = [f"=== 地图下载任务（共 {len(tasks)} 个）==="]
        for index, task in enumerate(tasks[:20], start=1):
            filename = task.get("filename") or self._filename_from_url(
                task.get("url", "")
            )
            status = status_map.get(task.get("status"), str(task.get("status", "未知")))
            progress = task.get("progress", 0) or 0
            size = task.get("formattedSize") or task.get("size") or "未知大小"
            speed = task.get("formattedSpeed") or ""
            line = f"{index}. {filename} [{status}] {progress:.1f}% {size}"
            if speed and task.get("status") == 1:
                line += f" {speed}"
            if task.get("status") == 3 and task.get("message"):
                line += f"\n   失败原因: {task.get('message')}"
            lines.append(line)
        if len(tasks) > 20:
            lines.append(f"... 还有 {len(tasks) - 20} 个任务未显示")
        return "\n".join(lines)

    def _filename_from_url(self, url: str) -> str:
        try:
            path = url.split("?", 1)[0].rstrip("/")
            return path.rsplit("/", 1)[-1] or "downloaded_file"
        except Exception:
            return "downloaded_file"

    def _is_supported_map_file(self, filename: str) -> bool:
        return Path(filename).suffix.lower() in {".vpk", ".zip", ".rar", ".7z"}

    def _normalize_file_stem(self, filename: str) -> str:
        return Path(filename).stem.strip().lower().replace(" ", "")

    def _safe_temp_filename(self, filename: str) -> str:
        safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", filename).strip(" .")
        return safe_name or "workshop_file"

    def _parse_map_indexes(
        self, content: str, maps: list[dict[str, str]]
    ) -> tuple[list[dict[str, str]], str | None]:
        indexes: set[int] = set()
        for token in re.split(r"[,，\s]+", content.strip()):
            if not token:
                continue
            match = re.fullmatch(r"(\d+)(?:-(\d+))?", token)
            if not match:
                return [], None
            start = int(match.group(1))
            end = int(match.group(2) or start)
            if start > end:
                start, end = end, start
            indexes.update(range(start, end + 1))

        if not indexes:
            return [], "请输入要删除的地图编号，例如：删除地图2 或 删除地图2-6"

        invalid = [idx for idx in sorted(indexes) if idx < 1 or idx > len(maps)]
        if invalid:
            return [], f"地图编号超出范围: {', '.join(str(i) for i in invalid)}"

        return [maps[idx - 1] for idx in sorted(indexes)], None

    def _extract_first_file(self, event: AstrMessageEvent) -> File | None:
        for comp in event.get_messages():
            if isinstance(comp, File):
                return comp
        return None

    def _format_change_map_list(self, title: str, maps: list[str]) -> str:
        if not maps:
            return f"{title}列表为空。"
        lines = [f"=== {title}（共 {len(maps)} 张）==="]
        for index, map_name in enumerate(maps, start=1):
            lines.append(f"{index}. {map_name}")
        lines.append(f"可用：切换{title}{1 if maps else ''}")
        return "\n".join(lines)

    def _format_campaign_chapter_range(self, chapters: list[dict[str, str]]) -> str:
        if not chapters:
            return ""
        if len(chapters) == 1:
            return "1"
        return f"1-{len(chapters)}"

    def _format_campaign_map_list(self, maps: list[dict]) -> str:
        if not maps:
            return "三方图列表为空。"
        lines = [f"=== 三方图（共 {len(maps)} 个战役）==="]
        for index, campaign in enumerate(maps, start=1):
            title = campaign.get("title") or "未知地图"
            chapters = campaign.get("chapters") or []
            chapter_range = self._format_campaign_chapter_range(chapters)
            suffix = chapter_range
            lines.append(f"{index}. {title}{suffix}")
        lines.append("可用：切换地图1 或 切换地图1-2")
        return "\n".join(lines)

    def _format_chapter_number(self, index: int) -> str:
        chinese_numbers = {
            1: "一",
            2: "二",
            3: "三",
            4: "四",
            5: "五",
            6: "六",
            7: "七",
            8: "八",
            9: "九",
            10: "十",
        }
        number = chinese_numbers.get(index, str(index))
        return f"第{number}关"

    def _display_from_map_entry(self, map_entry: str) -> tuple[str, str]:
        code, _, display = map_entry.partition("|")
        code = code.strip()
        display = display.strip() or code
        return code, display

    async def _get_map_display_name(self, map_code: str) -> str:
        normalized_code = map_code.strip().lower()
        for map_entry in self.OFFICIAL_MAPS:
            code, display = self._display_from_map_entry(map_entry)
            if code.lower() == normalized_code:
                return display

        result = await self._run_web_manager_call(self.web_manager.list_rcon_maps())
        if isinstance(result, str):
            return map_code

        for campaign in result.get("custom", []):
            campaign_title = str(campaign.get("title") or "")
            for chapter_index, chapter in enumerate(
                campaign.get("chapters") or [], start=1
            ):
                code = str(chapter.get("code") or "")
                if code.lower() != normalized_code:
                    continue
                chapter_title = str(chapter.get("title") or code)
                return (
                    f"{campaign_title} - {chapter_title}"
                    f"{self._format_chapter_number(chapter_index)}"
                )
        return map_code

    def _resolve_map_choice(
        self, content: str, maps: list[str]
    ) -> tuple[str, str, str | None]:
        value = content.strip()
        if not value:
            return "", "", "请提供地图编号或地图名。"
        if value.isdigit():
            index = int(value)
            if index < 1 or index > len(maps):
                return "", "", f"地图编号超出范围: {index}"
            selected = maps[index - 1]
            code, display = self._display_from_map_entry(selected)
            return code, display, None
        for map_name in maps:
            code, display = self._display_from_map_entry(map_name)
            if code.lower() == value.lower() or map_name.lower() == value.lower():
                return code, display, None
        return value, value, None

    def _resolve_campaign_map_choice(
        self, content: str, maps: list[dict]
    ) -> tuple[str, str, str | None]:
        value = content.strip()
        if not value:
            return "", "", "请提供地图编号或地图名。"

        index_match = re.fullmatch(r"(\d+)(?:-(\d+))?", value)
        if index_match:
            campaign_index = int(index_match.group(1))
            chapter_index = int(index_match.group(2) or 1)
            if campaign_index < 1 or campaign_index > len(maps):
                return "", "", f"地图编号超出范围: {campaign_index}"
            campaign = maps[campaign_index - 1]
            chapters = campaign.get("chapters") or []
            if chapter_index < 1 or chapter_index > len(chapters):
                return "", "", f"小图编号超出范围: {campaign_index}-{chapter_index}"
            chapter = chapters[chapter_index - 1]
            code = str(chapter.get("code") or "")
            campaign_title = str(campaign.get("title") or "未知地图")
            chapter_title = str(chapter.get("title") or code)
            display = (
                f"{campaign_title} - {chapter_title}"
                f"{self._format_chapter_number(chapter_index)}"
            )
            return code, display, None

        value_lower = value.lower()
        for campaign in maps:
            title = str(campaign.get("title") or "")
            for chapter_index, chapter in enumerate(
                campaign.get("chapters") or [], start=1
            ):
                code = str(chapter.get("code") or "")
                chapter_title = str(chapter.get("title") or "")
                full_title = f"{title} - {chapter_title}"
                if value_lower in {
                    code.lower(),
                    chapter_title.lower(),
                    full_title.lower(),
                }:
                    display = (
                        f"{title} - {chapter_title}"
                        f"{self._format_chapter_number(chapter_index)}"
                    )
                    return code, display, None
        return value, value, None

    async def _call_onebot_action(self, event: AstrMessageEvent, action: str, **params):
        bot = getattr(event, "bot", None)
        if bot is None:
            raise RuntimeError("当前平台不支持群文件 API。")
        if hasattr(bot, "call_action"):
            return await bot.call_action(action, **params)
        api = getattr(bot, "api", None)
        if api and hasattr(api, "call_action"):
            return await api.call_action(action, **params)
        raise RuntimeError("当前平台不支持群文件 API。")

    async def _upload_group_file(
        self, event: AstrMessageEvent, file_path: Path, filename: str
    ) -> str | None:
        group_id = event.get_group_id()
        if not group_id:
            return "该命令需要在群聊中使用。"
        try:
            await self._call_onebot_action(
                event,
                "upload_group_file",
                group_id=int(group_id),
                file=str(file_path),
                name=filename,
            )
            return None
        except Exception as e:
            return f"上传群文件失败: {type(e).__name__} - {e}"

    async def _list_group_files_in_folder(
        self, event: AstrMessageEvent, group_id: int, folder_id: str | None = None
    ) -> list[dict]:
        if folder_id:
            data = await self._call_onebot_action(
                event,
                "get_group_files_by_folder",
                group_id=group_id,
                folder_id=folder_id,
            )
        else:
            data = await self._call_onebot_action(
                event, "get_group_root_files", group_id=group_id
            )

        files = list(data.get("files") or [])
        folders = data.get("folders") or []
        for folder in folders:
            child_id = (
                folder.get("folder_id") or folder.get("folderId") or folder.get("id")
            )
            if not child_id:
                continue
            try:
                files.extend(
                    await self._list_group_files_in_folder(
                        event, group_id, str(child_id)
                    )
                )
            except Exception as e:
                print(f"[L4D2Plugin] Failed to list group folder {child_id}: {e}")
        return files

    async def _find_group_map_file(
        self, event: AstrMessageEvent, name_without_ext: str
    ) -> tuple[dict | None, str | None]:
        group_id = event.get_group_id()
        if not group_id:
            return None, "该命令需要在群聊中使用。"

        try:
            group_id_int = int(group_id)
            files = await self._list_group_files_in_folder(event, group_id_int)
        except Exception as e:
            return None, f"读取群文件失败: {type(e).__name__} - {e}"

        target = name_without_ext.strip()
        normalized_target = target.lower().replace(" ", "")
        candidates = [
            file
            for file in files
            if self._is_supported_map_file(
                str(file.get("file_name") or file.get("name") or "")
            )
            and self._normalize_file_stem(
                str(file.get("file_name") or file.get("name") or "")
            )
            == normalized_target
        ]

        if not candidates:
            return None, f"群文件中未找到地图文件: {target}"
        if len(candidates) > 1:
            names = [
                str(file.get("file_name") or file.get("name") or "未知文件")
                for file in candidates[:5]
            ]
            return None, "找到多个同名地图文件，请改用更准确的名称:\n" + "\n".join(
                names
            )
        return candidates[0], None

    async def _get_group_file_url(
        self, event: AstrMessageEvent, file_info: dict
    ) -> tuple[str, str | None]:
        group_id = event.get_group_id()
        file_id = (
            file_info.get("file_id")
            or file_info.get("fileId")
            or file_info.get("id")
            or file_info.get("file_uuid")
            or file_info.get("fileUuid")
        )
        if not group_id or not file_id:
            return "", "群文件缺少 file_id，无法获取下载链接。"

        try:
            data = await self._call_onebot_action(
                event,
                "get_group_file_url",
                group_id=int(group_id),
                file_id=str(file_id),
            )
        except Exception as e:
            return "", f"获取群文件下载链接失败: {type(e).__name__} - {e}"

        url = ""
        if isinstance(data, dict):
            url = str(data.get("url") or data.get("data", {}).get("url") or "")
        if not url:
            return "", "获取群文件下载链接失败：接口未返回 URL。"
        return url, None

    async def _run_web_manager_call(self, coro):
        try:
            return await coro
        except WebManagerError as e:
            return f"操作失败: {self._format_web_manager_error(str(e))}"
        except Exception as e:
            return f"操作失败: {type(e).__name__} - {e}"

    def _silent_stop(self, event: AstrMessageEvent) -> None:
        try:
            event.stop_event()
        except Exception:
            pass

    def _format_web_manager_error(self, error: str) -> str:
        if "HTTP 507" in error or "磁盘空间不足" in error:
            return "Web 管理器磁盘空间不足，当前使用率超过 90%，请先清理服务器地图或磁盘空间。"
        return error.removeprefix("Web 管理器请求失败: ").strip()

    @filter.regex(r"^(删除地图|重命名地图|地图下载|下载地图)$")
    async def silent_incomplete_command(self, event: AstrMessageEvent, *args, **kwargs):
        """Silently consume incomplete commands that require arguments."""
        if not self._get_group_config(event):
            return
        self._silent_stop(event)

    @filter.regex(r"^切换(官方图|三方图|地图)\s*(.*)$")
    async def change_server_map(self, event: AstrMessageEvent, *args, **kwargs):
        """切换官方图或三方图。"""
        group_conf = self._get_group_config(event)
        if not group_conf:
            return
        if not self._has_admin_permission(event, group_conf):
            yield event.plain_result("权限不足：您不在管理员列表中。")
            return

        match = re.match(r"^切换(官方图|三方图|地图)\s*(.*)$", event.message_str)
        if not match:
            return
        map_type, content = match.groups()
        if map_type == "官方图":
            maps = self.OFFICIAL_MAPS
        else:
            result = await self._run_web_manager_call(self.web_manager.list_rcon_maps())
            if isinstance(result, str):
                yield event.plain_result(result)
                return
            maps = result["custom"]
            if not content.strip():
                yield event.plain_result(self._format_campaign_map_list(maps))
                return
            map_name, display_name, error = self._resolve_campaign_map_choice(
                content, maps
            )
            if error:
                yield event.plain_result(error)
                return
            change_result = await self._run_web_manager_call(
                self.web_manager.change_map(map_name)
            )
            if isinstance(change_result, str) and change_result.startswith("操作失败"):
                yield event.plain_result(change_result)
                return
            yield event.plain_result(f"已发送切换地图指令: {display_name}")
            return

        if not content.strip():
            yield event.plain_result(self._format_change_map_list(map_type, maps))
            return

        map_name, display_name, error = self._resolve_map_choice(content, maps)
        if error:
            yield event.plain_result(error)
            return

        change_result = await self._run_web_manager_call(
            self.web_manager.change_map(map_name)
        )
        if isinstance(change_result, str) and change_result.startswith("操作失败"):
            yield event.plain_result(change_result)
            return
        yield event.plain_result(f"已发送切换地图指令: {display_name}")

    @filter.regex(r"^(地图列表|地图)$")
    async def list_maps(self, event: AstrMessageEvent, *args, **kwargs):
        """列出 Web 管理器中的地图文件。"""
        group_conf = self._get_group_config(event)
        if not group_conf:
            return
        result = await self._run_web_manager_call(self.web_manager.list_maps())
        if isinstance(result, str):
            yield event.plain_result(result)
            return
        yield event.chain_result([self._build_map_list_nodes(event, result)])

    @filter.regex(r"^删除地图\s*(.+)$")
    async def delete_map(self, event: AstrMessageEvent, *args, **kwargs):
        """按地图列表编号删除地图。用法：删除地图2 或 删除地图2-6"""
        group_conf = self._get_group_config(event)
        if not group_conf:
            return
        if not self._has_admin_permission(event, group_conf):
            yield event.plain_result("权限不足：您不在管理员列表中。")
            return

        map_name = event.message_str.replace("删除地图", "", 1).strip()
        maps = await self._run_web_manager_call(self.web_manager.list_maps())
        if isinstance(maps, str):
            yield event.plain_result(maps)
            return

        targets, error = self._parse_map_indexes(map_name, maps)
        if error:
            yield event.plain_result(error)
            return
        if not targets:
            yield event.plain_result("没有找到要删除的地图。")
            return

        yield event.plain_result(
            "正在删除地图:\n"
            + "\n".join(f"- {item.get('name', '')}" for item in targets)
        )

        success = []
        failures = []
        for item in targets:
            target_name = item.get("name", "")
            result = await self._run_web_manager_call(
                self.web_manager.remove_map(target_name)
            )
            if isinstance(result, str) and result.startswith("操作失败"):
                failures.append(f"{target_name}: {result}")
            else:
                success.append(target_name)

        msg = f"已删除 {len(success)} 个地图。"
        if failures:
            msg += "\n失败:\n" + "\n".join(failures[:10])
        yield event.plain_result(msg)

    @filter.regex(r"^重命名地图\s+(.+)$")
    async def rename_map(self, event: AstrMessageEvent, *args, **kwargs):
        """重命名地图。用法：重命名地图 旧名称.vpk 新名称.vpk"""
        group_conf = self._get_group_config(event)
        if not group_conf:
            return
        if not self._has_admin_permission(event, group_conf):
            yield event.plain_result("权限不足：您不在管理员列表中。")
            return

        content = event.message_str.replace("重命名地图", "", 1).strip()
        parts = content.split(maxsplit=1)
        if len(parts) != 2:
            self._silent_stop(event)
            return

        old_name, new_name = parts
        result = await self._run_web_manager_call(
            self.web_manager.rename_map(old_name, new_name)
        )
        if isinstance(result, str) and result.startswith("操作失败"):
            yield event.plain_result(result)
            return
        if isinstance(result, dict) and result.get("name"):
            new_name = result["name"]
        yield event.plain_result(f"已重命名地图: {old_name} -> {new_name}")

    @filter.regex(r"^清空地图$")
    async def clear_maps(self, event: AstrMessageEvent, *args, **kwargs):
        """清空 Web 管理器中的第三方地图。"""
        group_conf = self._get_group_config(event)
        if not group_conf:
            return
        if not self._has_admin_permission(event, group_conf):
            yield event.plain_result("权限不足：您不在管理员列表中。")
            return

        result = await self._run_web_manager_call(self.web_manager.clear_maps())
        if isinstance(result, str) and result.startswith("操作失败"):
            yield event.plain_result(result)
            return
        yield event.plain_result("已清空地图。")

    @filter.regex(r"^(地图下载|下载地图)\s+(.+)$")
    async def add_map_download(self, event: AstrMessageEvent, *args, **kwargs):
        """添加地图下载任务。用法：地图下载 <url> [文件名]"""
        group_conf = self._get_group_config(event)
        if not group_conf:
            return
        if not self._has_admin_permission(event, group_conf):
            yield event.plain_result("权限不足：您不在管理员列表中。")
            return

        content = re.sub(
            r"^(地图下载|下载地图)\s+", "", event.message_str, count=1
        ).strip()
        urls = re.findall(r"https?://\S+", content)
        if not urls:
            self._silent_stop(event)
            return

        yield event.plain_result(f"正在添加 {len(urls)} 个地图下载任务...")
        success = 0
        failures = []
        for url in urls:
            result = await self._run_web_manager_call(
                self.web_manager.add_download_task(url)
            )
            if isinstance(result, str) and result.startswith("操作失败"):
                failures.append(f"{url}: {result}")
            else:
                success += 1

        msg = f"已添加 {success} 个下载任务。"
        if failures:
            msg += "\n失败:\n" + "\n".join(failures[:5])
        yield event.plain_result(msg)

    @filter.regex(r"^下载任务$")
    async def list_map_download_tasks(self, event: AstrMessageEvent, *args, **kwargs):
        """列出地图下载任务。"""
        group_conf = self._get_group_config(event)
        if not group_conf:
            return
        result = await self._run_web_manager_call(
            self.web_manager.list_download_tasks()
        )
        if isinstance(result, str):
            yield event.plain_result(result)
            return
        yield event.plain_result(self._format_download_tasks(result))

    @filter.regex(r"^上传地图(?:\s+.*)?$")
    async def upload_map(self, event: AstrMessageEvent, *args, **kwargs):
        """上传地图。用法：上传地图 群文件名（不含后缀）"""
        group_conf = self._get_group_config(event)
        if not group_conf:
            return
        if not self._has_admin_permission(event, group_conf):
            yield event.plain_result("权限不足：您不在管理员列表中。")
            return

        content = event.message_str.replace("上传地图", "", 1).strip()
        if content.startswith(("http://", "https://")):
            result = await self._run_web_manager_call(
                self.web_manager.add_download_task(content)
            )
            if isinstance(result, str) and result.startswith("操作失败"):
                yield event.plain_result(result)
                return
            yield event.plain_result("已添加地图下载任务。")
            return

        if content:
            yield event.plain_result(f"正在查找群文件地图: {content}")
            file_info, error = await self._find_group_map_file(event, content)
            if error:
                yield event.plain_result(error)
                return

            filename = str(
                file_info.get("file_name") or file_info.get("name") or "map_file"
            )
            url, error = await self._get_group_file_url(event, file_info)
            if error:
                yield event.plain_result(error)
                return

            if not self._is_supported_map_file(filename):
                yield event.plain_result("仅支持 .vpk、.zip、.rar、.7z 地图文件。")
                return

            safe_filename = self._safe_temp_filename(filename)
            temp_path = Path(tempfile.gettempdir()) / f"l4d2_group_{safe_filename}"
            yield event.plain_result(f"已找到群文件: {filename}")
            yield event.plain_result("正在下载群文件到本地...")
            try:
                await download_file(url, str(temp_path))
                if not temp_path.is_file() or temp_path.stat().st_size <= 0:
                    yield event.plain_result("群文件下载失败：本地临时文件为空。")
                    return
                size_mb = temp_path.stat().st_size / 1024 / 1024
                yield event.plain_result(
                    f"群文件下载完成: {filename} ({size_mb:.2f}MB)"
                )
                yield event.plain_result("正在上传到 Web 管理器...")
                result = await self._run_web_manager_call(
                    self.web_manager.upload_map(temp_path, filename=filename)
                )
            except Exception as e:
                stage = "上传到 Web 管理器" if temp_path.exists() else "群文件下载"
                yield event.plain_result(f"{stage}失败: {type(e).__name__} - {e}")
                return
            finally:
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    pass

            if isinstance(result, str) and result.startswith("操作失败"):
                yield event.plain_result(
                    f"本地下载已完成，上传到 Web 管理器失败：{result}"
                )
                return
            yield event.plain_result(f"地图上传完成: {filename}")
            return

        file_comp = self._extract_first_file(event)
        if not file_comp:
            self._silent_stop(event)
            return

        filename = file_comp.name or "map_file"
        if not self._is_supported_map_file(filename):
            yield event.plain_result("仅支持 .vpk、.zip、.rar、.7z 地图文件。")
            return

        yield event.plain_result(f"正在上传地图文件 {filename}，请稍候...")
        file_path = await file_comp.get_file()
        if not file_path:
            self._silent_stop(event)
            return

        last_reported = -1

        def progress(done: int, total: int) -> None:
            nonlocal last_reported
            percent = int(done * 100 / total)
            if percent // 25 > last_reported // 25:
                last_reported = percent
                print(f"[L4D2Plugin] Uploading {filename}: {percent}%")

        result = await self._run_web_manager_call(
            self.web_manager.upload_map(
                Path(file_path), filename=filename, progress=progress
            )
        )
        if isinstance(result, str) and result.startswith("操作失败"):
            yield event.plain_result(result)
            return
        yield event.plain_result(f"地图上传完成: {filename}")

    @filter.regex(
        r"^(?:创意工坊(?:解析)?(?:\s+.*)?|.*https?://steamcommunity\.com/(?:sharedfiles|workshop)/filedetails/\?id=\d+.*)$"
    )
    async def parse_workshop_link(self, event: AstrMessageEvent, *args, **kwargs):
        """解析创意工坊链接。"""
        group_conf = self._get_group_config(event)
        if not group_conf:
            return
        if not self._has_admin_permission(event, group_conf):
            yield event.plain_result("权限不足：您不在管理员列表中。")
            return

        match = re.search(
            r"https?://steamcommunity\.com/(?:sharedfiles|workshop)/filedetails/\?id=(\d+)",
            event.message_str,
        )
        if not match:
            if re.fullmatch(r"创意工坊(?:解析)?", event.message_str.strip()):
                self._silent_stop(event)
            return

        url = match.group(0)
        yield event.plain_result("正在解析创意工坊链接，请稍候...")

        results, type_str = await self.workshop.process_url(url)

        if not results:
            yield event.plain_result(f"解析失败: {type_str}")
            return

        max_items = 5
        items = results[:max_items]
        yield event.plain_result(
            f"解析到 {len(results)} 个文件，开始添加下载任务并上传群文件..."
        )

        lines = [f"=== 创意工坊{type_str}处理结果 ==="]
        for item in items:
            title = item.get("title", "未知标题")
            # 清理标题中的换行符
            if title:
                title = title.replace("\n", " ").replace("\r", "").strip()

            file_url = item.get("file_url", "")
            filename = item.get("filename", "")
            size = item.get("file_size", "未知大小")

            # 简单的文件名清理
            if filename:
                filename = filename.replace("\\", "/").split("/")[-1]

            if not file_url:
                lines.append(f"{title}: 无可用下载链接")
                continue

            download_result = await self._run_web_manager_call(
                self.web_manager.add_download_task(file_url, filename)
            )
            download_ok = not (
                isinstance(download_result, str)
                and download_result.startswith("操作失败")
            )

            upload_error = None
            if filename:
                safe_filename = self._safe_temp_filename(filename)
                temp_path = (
                    Path(tempfile.gettempdir()) / f"l4d2_workshop_{safe_filename}"
                )
                try:
                    await download_file(file_url, str(temp_path))
                    upload_error = await self._upload_group_file(
                        event, temp_path, filename
                    )
                except Exception as e:
                    upload_error = f"下载/上传群文件失败: {type(e).__name__} - {e}"
                finally:
                    try:
                        temp_path.unlink(missing_ok=True)
                    except Exception:
                        pass
            else:
                upload_error = "缺少文件名，未上传群文件。"

            status = []
            status.append("下载任务已添加" if download_ok else str(download_result))
            status.append("群文件已上传" if not upload_error else upload_error)
            lines.append(f"{title}\n文件: {filename} ({size})\n" + "\n".join(status))

        if len(results) > max_items:
            lines.append(
                f"还有 {len(results) - max_items} 个文件未自动处理，请分批发送。"
            )

        yield event.plain_result("\n---\n".join(lines))
