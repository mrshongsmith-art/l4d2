from __future__ import annotations

import mimetypes
from collections.abc import Callable
from pathlib import Path
from typing import Any

import aiohttp


class WebManagerError(Exception):
    """Raised when the L4D2 web manager returns an error."""


class L4D2WebManager:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: int = 60,
        upload_chunk_size: int = 5 * 1024 * 1024,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.upload_chunk_size = upload_chunk_size

    def enabled(self) -> bool:
        return bool(self.base_url and self.token)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    async def _request(
        self,
        path: str,
        *,
        data: Any | None = None,
        json: dict[str, Any] | None = None,
        timeout: int | None = None,
    ) -> Any:
        if not self.enabled():
            raise WebManagerError("Web 管理器未配置。")

        url = f"{self.base_url}{path}"
        client_timeout = aiohttp.ClientTimeout(total=timeout or self.timeout)
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            async with session.post(
                url, headers=self._headers(), data=data, json=json
            ) as response:
                text = await response.text()
                if response.status >= 400:
                    raise WebManagerError(
                        f"Web 管理器请求失败: HTTP {response.status} {text[:200]}"
                    )

                content_type = response.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    return await response.json()
                return text

    async def list_maps(self) -> list[dict[str, str]]:
        text = await self._request("/list")
        maps: list[dict[str, str]] = []
        for line in str(text).splitlines():
            line = line.strip()
            if not line:
                continue
            name, _, size = line.partition("$$")
            maps.append({"name": name.strip(), "size": size.strip()})
        return maps

    async def clear_maps(self) -> Any:
        return await self._request("/clear")

    async def remove_map(self, map_name: str) -> Any:
        form = aiohttp.FormData()
        form.add_field("map", map_name)
        return await self._request("/remove", data=form)

    async def rename_map(self, old_name: str, new_name: str) -> Any:
        form = aiohttp.FormData()
        form.add_field("oldName", old_name)
        form.add_field("newName", new_name)
        return await self._request("/rename", data=form)

    async def list_download_tasks(self) -> list[dict[str, Any]]:
        data = await self._request("/download/list")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("tasks", "data", "items"):
                value = data.get(key)
                if isinstance(value, list):
                    return value
        return []

    async def add_download_task(
        self, url: str, filename: str = "", referer: str = ""
    ) -> Any:
        form = aiohttp.FormData()
        form.add_field("url", url)
        if filename:
            form.add_field("filename", filename)
        if referer:
            form.add_field("referer", referer)
        return await self._request("/download/add", data=form)

    async def upload_map(
        self,
        file_path: Path,
        *,
        filename: str | None = None,
        progress: Callable[[int, int], None] | None = None,
    ) -> Any:
        file_path = file_path.resolve()
        if not file_path.is_file():
            raise WebManagerError(f"文件不存在: {file_path}")

        upload_name = filename or file_path.name
        file_size = file_path.stat().st_size
        total_chunks = max(
            1, (file_size + self.upload_chunk_size - 1) // self.upload_chunk_size
        )

        init_form = aiohttp.FormData()
        init_form.add_field("filename", upload_name)
        init_form.add_field("fileSize", str(file_size))
        init_form.add_field("totalChunks", str(total_chunks))
        init_data = await self._request("/upload/init", data=init_form)

        upload_id = ""
        if isinstance(init_data, dict):
            upload_id = str(init_data.get("uploadId") or init_data.get("id") or "")
        if not upload_id:
            raise WebManagerError(f"无法初始化上传: {init_data}")

        mime_type = mimetypes.guess_type(upload_name)[0] or "application/octet-stream"
        with file_path.open("rb") as file_obj:
            for chunk_index in range(total_chunks):
                chunk = file_obj.read(self.upload_chunk_size)
                form = aiohttp.FormData()
                form.add_field("uploadId", upload_id)
                form.add_field("chunkIndex", str(chunk_index))
                form.add_field(
                    "chunk",
                    chunk,
                    filename="chunk",
                    content_type=mime_type,
                )
                await self._request(
                    "/upload/chunk",
                    data=form,
                    timeout=max(self.timeout, 180),
                )
                if progress:
                    progress(chunk_index + 1, total_chunks)

        merge_form = aiohttp.FormData()
        merge_form.add_field("uploadId", upload_id)
        merge_form.add_field("filename", upload_name)
        return await self._request(
            "/upload/merge", data=merge_form, timeout=max(self.timeout, 180)
        )

    async def list_rcon_maps(self) -> dict[str, list[Any]]:
        data = await self._request("/rcon/maplist")
        if isinstance(data, dict):
            official = data.get("official") or data.get("officialMaps") or []
            custom = (
                data.get("custom") or data.get("thirdParty") or data.get("maps") or []
            )
            return {
                "official": [str(item) for item in official],
                "custom": self._normalize_campaign_maps(custom),
            }
        if isinstance(data, list):
            custom_maps = []
            for campaign in data:
                if not isinstance(campaign, dict):
                    custom_maps.append(
                        {
                            "title": str(campaign),
                            "chapters": [
                                {"code": str(campaign), "title": str(campaign)}
                            ],
                        }
                    )
                    continue
                campaign_title = str(
                    campaign.get("Title") or campaign.get("VpkName") or ""
                )
                chapters = []
                for chapter in campaign.get("Chapters") or []:
                    if not isinstance(chapter, dict):
                        continue
                    code = str(chapter.get("Code") or "")
                    title = str(chapter.get("Title") or code)
                    if code:
                        chapters.append({"code": code, "title": title})
                if chapters:
                    custom_maps.append({"title": campaign_title, "chapters": chapters})
            return {"official": [], "custom": custom_maps}
        return {"official": [], "custom": []}

    def _normalize_campaign_maps(self, maps: list[Any]) -> list[dict[str, Any]]:
        custom_maps = []
        for item in maps:
            if isinstance(item, dict):
                title = str(
                    item.get("title")
                    or item.get("Title")
                    or item.get("name")
                    or item.get("VpkName")
                    or ""
                )
                raw_chapters = (
                    item.get("chapters")
                    or item.get("Chapters")
                    or item.get("maps")
                    or item.get("Maps")
                    or []
                )
                chapters = []
                for chapter in raw_chapters:
                    if isinstance(chapter, dict):
                        code = str(chapter.get("code") or chapter.get("Code") or "")
                        chapter_title = str(
                            chapter.get("title") or chapter.get("Title") or code
                        )
                    else:
                        code = str(chapter)
                        chapter_title = code
                    if code:
                        chapters.append({"code": code, "title": chapter_title})
                if chapters:
                    custom_maps.append({"title": title, "chapters": chapters})
                continue

            text = str(item)
            code, _, title = text.partition("|")
            custom_maps.append(
                {
                    "title": title.strip() or code.strip(),
                    "chapters": [
                        {"code": code.strip(), "title": title.strip() or code.strip()}
                    ],
                }
            )
        return custom_maps

    async def change_map(self, map_name: str) -> Any:
        form = aiohttp.FormData()
        form.add_field("mapName", map_name)
        return await self._request("/rcon/changemap", data=form)
