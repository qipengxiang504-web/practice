"""A small RSS digest agent; Python standard library only."""

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import html
import json
from pathlib import Path
import re
import sys
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


BASE_DIR = Path(__file__).resolve().parent
BEIJING = timezone(timedelta(hours=8))
ATOM = "{http://www.w3.org/2005/Atom}"


@dataclass(frozen=True)
class Article:
    title: str
    url: str
    source: str
    summary: str
    published_at: datetime | None


def plain_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    return " ".join(html.unescape(value).split())


def parse_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        result = parsedate_to_datetime(value)
    except (ValueError, TypeError, OverflowError):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    # An undated timezone must not silently be treated as local time.
    if result.tzinfo is None:
        return None
    return result.astimezone(timezone.utc)


def canonical_url(value: str) -> str:
    parts = urlsplit(value.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith("utm_")]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path,
                       urlencode(query), ""))


def parse_feed(data: bytes, source: str) -> list[Article]:
    root = ET.fromstring(data)
    if root.tag == "rss":
        nodes = root.findall("./channel/item")
        is_atom = False
    elif root.tag == ATOM + "feed":
        nodes = root.findall(ATOM + "entry")
        is_atom = True
    else:
        raise ValueError("Expected an RSS 2.0 or Atom feed")
    articles = []
    for node in nodes:
        if is_atom:
            title = node.findtext(ATOM + "title", "")
            url = next((link.get("href", "") for link in node.findall(ATOM + "link")
                        if link.get("rel", "alternate") == "alternate"), "")
            summary = node.findtext(ATOM + "summary", "") or node.findtext(ATOM + "content", "")
            date = node.findtext(ATOM + "published", "") or node.findtext(ATOM + "updated", "")
        else:
            title = node.findtext("title", "")
            url = node.findtext("link", "")
            summary = node.findtext("description", "")
            date = node.findtext("pubDate", "")
        if not title.strip() or urlsplit(url).scheme.lower() not in {"http", "https"}:
            continue
        articles.append(Article(plain_text(title), canonical_url(url), source,
                                plain_text(summary), parse_date(date)))
    return articles


def select_articles(articles: list[Article], keywords: list[str], now: datetime,
                    lookback_hours: float | None, max_items: int) -> list[Article]:
    selected = []
    seen = set()
    cutoff = now - timedelta(hours=lookback_hours) if lookback_hours is not None else None
    for article in sorted(articles, key=lambda a: a.published_at or
                          datetime.min.replace(tzinfo=timezone.utc), reverse=True):
        if cutoff is not None and (article.published_at is None or
                                   not cutoff <= article.published_at <= now):
            continue
        content = (article.title + " " + article.summary).casefold()
        if not any(keyword.casefold() in content for keyword in keywords):
            continue
        if article.url in seen:
            continue
        seen.add(article.url)
        selected.append(article)
    return selected[:max_items]


def markdown_text(value: str) -> str:
    # Keep feed-provided text as text, including in the GitHub run summary.
    value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"([\\`*_{}\[\]()#!|])", r"\\\1", value)


def render_digest(articles: list[Article], now: datetime, warnings: list[str],
                  demo: bool = False) -> str:
    local_time = now.astimezone(BEIJING)
    lines = [f"# 一级市场资讯简报 · {local_time:%Y-%m-%d}", "",
             f"生成时间：{local_time:%Y-%m-%d %H:%M}（北京时间）", ""]
    if demo:
        lines.extend(["> 离线演示：以下新闻全部为虚构示例，忽略时间窗口。", ""])
    if warnings:
        lines.extend(["## 来源状态", ""])
        lines.extend(f"- {markdown_text(warning)}" for warning in warnings)
        lines.append("")
    lines.extend([f"## 匹配资讯（{len(articles)} 条）", ""])
    if not articles:
        lines.extend(["在当前时间窗口和关键词条件下，没有匹配到资讯。", ""])
    for index, article in enumerate(articles, 1):
        date = (article.published_at.astimezone(BEIJING).strftime("%Y-%m-%d %H:%M")
                if article.published_at else "时间未知")
        # Encode characters that could break a Markdown link target.
        target = article.url.replace("<", "%3C").replace(">", "%3E")
        lines.extend([f"### {index}. [{markdown_text(article.title)}](<{target}>)", "",
                      f"来源：{markdown_text(article.source)} | 发布时间：{date}（北京时间）", "",
                      markdown_text(article.summary[:240]) or "原资讯未提供摘要。", ""])
    lines.extend(["---", "说明：按关键词筛选，摘要为来源摘录；请打开原文核对。", ""])
    return "\n".join(lines)


def load_config(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config.get("sources"), list) or not config["sources"]:
        raise ValueError("sources must be a non-empty list")
    for source in config["sources"]:
        if (not isinstance(source, dict) or not isinstance(source.get("name"), str)
                or not isinstance(source.get("url"), str)
                or urlsplit(source["url"]).scheme not in {"http", "https"}):
            raise ValueError("each source needs a name and an HTTP(S) url")
    keywords = config.get("keywords")
    if (not isinstance(keywords, list) or not keywords or
            any(not isinstance(k, str) or not k.strip() for k in keywords)):
        raise ValueError("keywords must be a non-empty list of non-empty strings")
    if type(config.get("max_items")) is not int or config["max_items"] <= 0:
        raise ValueError("max_items must be a positive integer")
    hours = config.get("lookback_hours")
    if type(hours) not in {int, float} or not 0 < hours < float("inf"):
        raise ValueError("lookback_hours must be a positive finite number")
    return config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a primary-market RSS digest")
    parser.add_argument("--demo", action="store_true", help="Use fictional offline examples")
    parser.add_argument("--config", type=Path, default=BASE_DIR / "config.json")
    parser.add_argument("--output", type=Path, help="Override the Markdown output path")
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    try:
        config = load_config(args.config)
        warnings = []
        articles = []
        succeeded = 0
        if args.demo:
            articles = parse_feed((BASE_DIR / "examples" / "sample.xml").read_bytes(), "虚构示例")
        else:
            for source in config["sources"]:
                try:
                    request = Request(source["url"], headers={"User-Agent": "primary-market-digest/0.1"})
                    with urlopen(request, timeout=20) as response:
                        articles.extend(parse_feed(response.read(), source["name"]))
                    succeeded += 1
                except (OSError, ValueError, ET.ParseError) as exc:
                    # Report only the error class; URLs may contain access credentials.
                    warnings.append(f"{source['name']} 读取失败（{type(exc).__name__}）")
            if succeeded == 0:
                for warning in warnings:
                    print(warning, file=sys.stderr)
                print("所有资讯源读取失败，未生成新的简报。", file=sys.stderr)
                return 1
            unknown_dates = sum(article.published_at is None for article in articles)
            if unknown_dates:
                warnings.append(f"已跳过 {unknown_dates} 条无法确认发布时间的资讯。")
        selected = select_articles(articles, config["keywords"], now,
                                   None if args.demo else config["lookback_hours"],
                                   config["max_items"])
        filename = "demo.md" if args.demo else f"digest-{now.astimezone(BEIJING):%Y-%m-%d}.md"
        output = args.output or BASE_DIR / "output" / filename
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render_digest(selected, now, warnings, args.demo), encoding="utf-8")
        print(f"已生成：{output}（{len(selected)} 条）")
        return 0
    except (OSError, ValueError, ET.ParseError) as exc:
        print(f"运行失败（{type(exc).__name__}）：请检查配置及本地文件。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
