"""텔레그램 공식 통계(stats.*) 그래프 파싱 공용 헬퍼.

collect.py / backfill.py 가 함께 쓴다. StatsGraphAsync 는 토큰으로 한 번 더
로드해야 실제 데이터(JSON)가 나온다.
"""
import json
from datetime import datetime, timezone

from telethon.tl.functions.stats import LoadAsyncGraphRequest
from telethon.tl.types import StatsGraph, StatsGraphAsync, StatsGraphError


async def load_graph(client, graph):
    """동기/비동기 그래프를 실제 데이터(dict)로 변환. 실패 시 None."""
    if graph is None:
        return None
    if isinstance(graph, StatsGraphAsync):
        try:
            graph = await client(LoadAsyncGraphRequest(token=graph.token))
        except Exception:
            return None
    if isinstance(graph, StatsGraphError):
        return None
    if isinstance(graph, StatsGraph):
        try:
            return json.loads(graph.json.data)
        except Exception:
            return None
    return None


def parse_graph(data):
    """텔레그램 차트 JSON → {'days':[YYYY-MM-DD...], 'series':[(label,[vals...])...]}"""
    if not data:
        return None
    cols = data.get("columns", [])
    types = data.get("types", {})
    names = data.get("names", {})
    xvals, series = None, []
    for col in cols:
        key, vals = col[0], col[1:]
        if types.get(key) == "x" or key == "x":
            xvals = vals
        else:
            series.append((names.get(key, key), vals))
    if not xvals:
        return None
    days = [datetime.fromtimestamp(int(t) / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            for t in xvals]
    return {"days": days, "series": series}


def by_name(parsed, *subs):
    """series 라벨에 subs 중 하나가 포함된 첫 시리즈를 {date: value} 로."""
    if not parsed:
        return {}
    for label, vals in parsed["series"]:
        low = str(label).lower()
        if any(s in low for s in subs):
            return {d: v for d, v in zip(parsed["days"], vals) if v is not None}
    return {}


def first_series(parsed):
    if not parsed or not parsed["series"]:
        return {}
    _, vals = parsed["series"][0]
    return {d: v for d, v in zip(parsed["days"], vals) if v is not None}
