import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from streamlink import Streamlink
from streamlink.exceptions import NoPluginError, PluginError
from streamlink.stream.hls import HLSStream
from streamlink.stream.http import HTTPStream


class UnsupportedLiveUrlError(ValueError):
    pass


class LiveSourceOfflineError(RuntimeError):
    pass


class LiveSourceAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class LiveSourceProbe:
    status: str
    message: str
    qualities: list[str]
    room_id: str | None = None
    title: str | None = None
    author: str | None = None


@dataclass(frozen=True)
class ResolvedLiveSource:
    stream: Any
    stream_url: str
    quality: str
    room_id: str | None = None
    title: str | None = None
    author: str | None = None


def _load_douyin_streams(url: str):
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or hostname != "live.douyin.com":
        raise UnsupportedLiveUrlError("抖音直连仅支持 https://live.douyin.com/房间号 格式")

    client = Streamlink()
    client.set_option("http-timeout", 15)

    try:
        _, plugin_class, resolved_url = client.resolve_url(url)
        plugin = plugin_class(client, resolved_url)
        streams = plugin.streams()
    except NoPluginError as exc:
        raise UnsupportedLiveUrlError("该链接暂不受直连解析器支持") from exc
    return plugin, streams


def _autoengine_room_id(url: str) -> str:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if (
        parsed.scheme not in {"http", "https"}
        or hostname not in {"autoengine.com", "www.autoengine.com"}
        or parsed.path != "/jdc/industry/live/screen"
    ):
        raise UnsupportedLiveUrlError(
            "懂车云店直连仅支持 autoengine.com/jdc/industry/live/screen 页面链接"
        )
    room_id = parse_qs(parsed.query).get("room_id", [""])[0].strip()
    if not room_id.isdigit():
        raise UnsupportedLiveUrlError("懂车云店链接缺少有效的 room_id")
    return room_id


def _request_autoengine_json(
    endpoint: str,
    room_id: str,
    cookie: str | None,
    *,
    need_hls: bool = False,
) -> dict[str, Any]:
    query: dict[str, str] = {
        "__method": "window.fetch",
        "room_id": room_id,
    }
    if need_hls:
        query["need_hls"] = "1"
    request = Request(
        f"https://www.autoengine.com{endpoint}?{urlencode(query)}",
        headers={
            "Accept": "application/json, text/plain, */*",
            "Referer": (
                "https://www.autoengine.com/jdc/industry/live/screen?"
                f"room_id={room_id}"
            ),
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/126 Safari/537.36"
            ),
            **({"Cookie": cookie} if cookie else {}),
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"懂车云店接口返回 HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError("服务器无法连接懂车云店接口") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("懂车云店接口未返回有效数据") from exc

    message = str(payload.get("prompts") or payload.get("message") or "")
    status = payload.get("status")
    if status == 10014 or "重新登录" in message or "授权过期" in message:
        raise LiveSourceAuthError(
            "懂车云店要求登录授权，请在服务器配置 AUTOENGINE_COOKIE 后重试"
        )
    return payload


def _find_value(payload: Any, keys: set[str]) -> Any:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in keys and value is not None and value != "":
                return value
        for value in payload.values():
            found = _find_value(value, keys)
            if found is not None and found != "":
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _find_value(value, keys)
            if found is not None and found != "":
                return found
    return None


def _autoengine_stream_url(payload: dict[str, Any]) -> str | None:
    value = _find_value(
        payload,
        {
            "stream_url",
            "hls_url",
            "hls_pull_url",
            "flv_url",
            "flv_pull_url",
            "flvPullUrl",
            "pull_url",
            "play_url",
        },
    )
    if not isinstance(value, str) or not value.startswith(("http://", "https://")):
        return None
    return value


def _autoengine_metadata(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    title = _find_value(payload, {"title", "room_title"})
    author = _find_value(payload, {"author", "anchor_name", "account_name", "nickname"})
    return (
        title if isinstance(title, str) else None,
        author if isinstance(author, str) else None,
    )


def _load_autoengine_room(
    url: str,
    cookie: str | None,
) -> tuple[str, dict[str, Any], str | None]:
    room_id = _autoengine_room_id(url)
    room_payload = _request_autoengine_json(
        "/motor/dealer/jdc_saas/live/room/info",
        room_id,
        cookie,
        need_hls=True,
    )
    return room_id, room_payload, _autoengine_stream_url(room_payload)


def _autoengine_replay_exists(room_id: str, cookie: str | None) -> bool:
    payload = _request_autoengine_json(
        "/motor/dealer/jdc_saas/live/data/screen/get_replay_url",
        room_id,
        cookie,
    )
    replay_url = _find_value(payload, {"replay_url"})
    return isinstance(replay_url, str) and replay_url.startswith(("http://", "https://"))


def probe_live_source(url: str, autoengine_cookie: str | None = None) -> LiveSourceProbe:
    hostname = (urlparse(url).hostname or "").lower()
    if hostname in {"autoengine.com", "www.autoengine.com"}:
        try:
            room_id, payload, stream_url = _load_autoengine_room(url, autoengine_cookie)
            title, author = _autoengine_metadata(payload)
            if stream_url:
                return LiveSourceProbe(
                    status="live",
                    message="已从懂车云店解析到实时直播流",
                    qualities=["auto"],
                    room_id=room_id,
                    title=title,
                    author=author,
                )
            if _autoengine_replay_exists(room_id, autoengine_cookie):
                return LiveSourceProbe(
                    status="offline",
                    message="该懂车云店场次已经结束，当前页面只有回放，不能实时监听",
                    qualities=[],
                    room_id=room_id,
                    title=title,
                    author=author,
                )
            return LiveSourceProbe(
                status="offline",
                message="链接可识别，但当前未解析到实时直播流；直播间可能尚未开播",
                qualities=[],
                room_id=room_id,
                title=title,
                author=author,
            )
        except (UnsupportedLiveUrlError, LiveSourceAuthError):
            raise
        except Exception as exc:
            return LiveSourceProbe(
                status="error",
                message=f"服务器未能解析懂车云店直播间：{type(exc).__name__}",
                qualities=[],
            )

    if hostname != "live.douyin.com":
        raise UnsupportedLiveUrlError("目前支持抖音直播页和懂车云店直播大屏链接")

    try:
        plugin, streams = _load_douyin_streams(url)
    except UnsupportedLiveUrlError:
        raise
    except PluginError as exc:
        return LiveSourceProbe(
            status="error",
            message=f"直播平台返回异常：{type(exc).__name__}",
            qualities=[],
        )
    except Exception as exc:
        return LiveSourceProbe(
            status="error",
            message=f"服务器未能解析该直播间：{type(exc).__name__}",
            qualities=[],
        )

    if not streams:
        return LiveSourceProbe(
            status="offline",
            message="链接可识别，但当前未解析到直播流；直播间可能尚未开播",
            qualities=[],
            room_id=getattr(plugin, "id", None),
            title=getattr(plugin, "title", None),
            author=getattr(plugin, "author", None),
        )

    qualities = sorted(quality for quality in streams if quality not in {"best", "worst"})
    return LiveSourceProbe(
        status="live",
        message="已从直播页面解析到可用直播流",
        qualities=qualities,
        room_id=getattr(plugin, "id", None),
        title=getattr(plugin, "title", None),
        author=getattr(plugin, "author", None),
    )


def _stream_from_direct_url(url: str) -> tuple[Any, str]:
    client = Streamlink()
    client.set_option("http-timeout", 15)
    path = urlparse(url).path.lower()
    if path.endswith(".m3u8"):
        streams = HLSStream.parse_variant_playlist(client, url)
        if streams:
            stream = streams.get("best") or next(iter(streams.values()))
            return stream, "best"
        return HLSStream(client, url), "hls"
    return HTTPStream(client, url), "source"


def resolve_live_source(
    url: str,
    preferred_quality: str = "best",
    autoengine_cookie: str | None = None,
) -> ResolvedLiveSource:
    hostname = (urlparse(url).hostname or "").lower()
    if hostname in {"autoengine.com", "www.autoengine.com"}:
        room_id, payload, stream_url = _load_autoengine_room(url, autoengine_cookie)
        title, author = _autoengine_metadata(payload)
        if not stream_url:
            if _autoengine_replay_exists(room_id, autoengine_cookie):
                raise LiveSourceOfflineError(
                    "该懂车云店场次已经结束，当前只有回放，无法作为实时直播监听"
                )
            raise LiveSourceOfflineError("懂车云店直播间尚未开播或未返回实时流")
        stream, quality = _stream_from_direct_url(stream_url)
        return ResolvedLiveSource(
            stream=stream,
            stream_url=stream_url,
            quality=quality,
            room_id=room_id,
            title=title,
            author=author,
        )

    if hostname != "live.douyin.com":
        raise UnsupportedLiveUrlError("目前支持抖音直播页和懂车云店直播大屏链接")

    try:
        plugin, streams = _load_douyin_streams(url)
    except (UnsupportedLiveUrlError, LiveSourceOfflineError):
        raise
    except Exception as exc:
        raise RuntimeError(f"直播流解析失败：{type(exc).__name__}") from exc

    if not streams:
        raise LiveSourceOfflineError("直播间当前未开播或未返回可用直播流")

    quality = preferred_quality if preferred_quality in streams else "best"
    stream = streams.get(quality)
    if stream is None:
        quality, stream = next(iter(streams.items()))

    stream_url = stream.to_url()
    if not stream_url:
        raise RuntimeError("直播平台未返回可读取的媒体地址")
    return ResolvedLiveSource(
        stream=stream,
        stream_url=stream_url,
        quality=quality,
        room_id=getattr(plugin, "id", None),
        title=getattr(plugin, "title", None),
        author=getattr(plugin, "author", None),
    )
