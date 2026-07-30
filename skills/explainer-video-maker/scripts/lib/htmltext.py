"""
HTML-to-text extraction utility for search results.
"""

from __future__ import annotations

import re


def strip_html(html: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    # Remove script and style blocks
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # Remove tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode common entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def truncate(text: str, max_chars: int = 5000) -> str:
    """Truncate text to max_chars, preserving sentence boundaries."""
    if len(text) <= max_chars:
        return text
    # Try to cut at a sentence boundary
    cut = text[:max_chars]
    last_period = max(cut.rfind("。"), cut.rfind(". "), cut.rfind("\n"))
    if last_period > max_chars * 0.5:
        return cut[: last_period + 1]
    return cut + "..."


# ── Text cleaning patterns ───────────────────────────────────────────
# Lines that match any of these are pure noise and should be removed.

_NOISE_LINE_PATTERNS = [
    # Cookie / privacy consent (multi-language)
    r"^.*(?:cookie|Cookie|COOKIE).*(?:政策|声明|通知|同意|设置|接受|policy|notice|consent|accept|setting).*$",
    r"^(?:我们|我們|本(?:网)?站)(?:使用|采用|会|將).*(?:cookie|Cookie|COOKIE).*$",
    r"^.*(?:GDPR|CCPA|隐私|隐私权|个资|个人信息).*(?:政策|保护|声明|条款).*$",
    # Navigation / UI boilerplate (match start of line, may contain more)
    r"^(?:登录|登錄|注册|註冊|立即登录|立即註冊|免费注册|免费註冊|加入|登入|开通|立即开通)\b.*$",
    r"^(?:Log\s*in|Sign\s*up|Sign\s*in|Register|Login|Join|Get\s*started|Create\s*account)\b.*$",
    r"^(?:下载|下載|下载APP|下載APP|扫码下载|扫码|扫一扫|手机版|客户端|移动版|APP下载).*$",
    r"^(?:Download|Get the app|Mobile app|Install)\b.*$",
    r"^(?:返回顶部|回到顶部|返回首頁|回到首頁|回顶部|顶部|TOP|Back to top).*$",
    r"^(?:首页|首頁|主页|主頁|Home|HOME)\b.*$",
    r"^(?:上一页|下一页|上一篇|下一篇|更多|查看更多|阅读更多|展开全文|收起).*$",
    r"^(?:Prev|Next|Previous|Read more|Show more|View more|More|Less)\b.*$",
    r"^(?:导航|導航|菜单|菜單|目录|目錄|Navigation|Menu|Sitemap).*$",
    # Social / sharing
    r"^(?:分享(?:到|至)?|转发|收藏|点赞|评论|举报|投诉|反馈|打赏|赞赏).*$",
    r"^(?:Share|Tweet|Pin|Like|Comment|Subscribe|Follow|Repost).*$",
    # Ads / promotions
    r"^(?:广告|推广|赞助|AD|Advertisement|Sponsored|Promoted|ADVERTISING).*$",
    r"^.*(?:广告|推广|赞助商).*$",
    # Copyright / legal
    r"^(?:Copyright|©)\s*\d{4}.*$",
    r"^(?:版权|版權|版权所有|版權所有).*$",
    r"^.*(?:All rights reserved|保留(?:所有)?(?:权利|權利)).*$",
    r"^(?:免责声明|免責聲明|用户协议|用户条款|服务条款|使用条款|隐私政策|社区(?:规范|公约)).*$",
    r"^(?:Terms of (?:Service|Use)|Privacy Policy|Legal|Disclaimer).*$",
    # Newsletter / subscription
    r"^(?:订阅|訂閱|关注我们|關注我們|邮件订阅|邮件訂閱|电子报).*$",
    r"^(?:Subscribe|Newsletter|Mailing list|Email updates).*$",
    # Contact / about boilerplate
    r"^(?:联系我们|聯絡我們|关于我们|關於我們|商务合作|广告合作|合作联系).*$",
    r"^(?:Contact us|About us|Advertise|Work with us|Careers|Press).*$",
    # Comment / interaction prompts
    r"^(?:评论|評論|写评论|发表评论|抢沙发|来说两句|说点什么).*$",
    r"^(?:Comments|Leave a comment|Write a comment|What do you think).*$",
    # Breadcrumb / navigation fragments
    r"^首页\s*[>＞»]\s*.*$",
    r"^Home\s*[>＞»]\s*.*$",
    # Purely decorative / empty
    r"^[\s\|·•·\-\*\.＿]+$",
    r"^[|｜·•·\-—\*]{3,}$",
    # Timestamp-only lines
    r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}\s*\d{1,2}:\d{2}(?::\d{2})?$",
    # View count / stats
    r"^(?:阅读\s*\d+|浏览\s*\d+|点击\s*\d+|查看\s*\d+).*$",
    r"^(?:\d+\s*(?:views?|reads?|次阅读|次浏览|人阅读|人浏览)).*$",
]

_NOISE_RE = re.compile("|".join(_NOISE_LINE_PATTERNS), re.IGNORECASE)

# Minimum meaningful line length (characters). Shorter lines are usually
# nav items, button labels, or other UI fragments.
_MIN_LINE_LENGTH = 8


def clean_text(text: str, min_line_length: int = _MIN_LINE_LENGTH) -> str:
    """Remove boilerplate / noise lines from extracted page text.

    Filters out navigation, cookie notices, ads, social-share prompts,
    copyright lines, and other common web page noise. Deduplicates
    repeated lines and collapses excessive whitespace.
    """
    lines = text.splitlines()
    kept: list[str] = []
    seen: set[str] = set()

    for line in lines:
        stripped = line.strip()

        # Skip empty
        if not stripped:
            continue

        # Skip short lines (nav items, button labels, etc.)
        # CJK chars carry more meaning per character; count them as 2 towards
        # the effective length to avoid filtering short-but-meaningful lines.
        has_cjk = any("\u4e00" <= c <= "\u9fff" for c in stripped)
        if has_cjk:
            effective_len = sum(2 if "\u4e00" <= c <= "\u9fff" else 1 for c in stripped)
            if effective_len < 6:  # 3 CJK chars or ~2 CJK + 2 ASCII
                continue
        elif len(stripped) < min_line_length:
            continue

        # Skip noise patterns
        if _NOISE_RE.match(stripped):
            continue

        # Skip pure-numeric or mostly symbolic
        alpha = sum(1 for c in stripped if c.isalpha() or "\u4e00" <= c <= "\u9fff")
        if alpha < len(stripped) * 0.3 and len(stripped) > 5:
            continue

        # Deduplicate identical lines (common in web page boilerplate)
        key = stripped[:80]
        if key in seen:
            continue
        seen.add(key)

        kept.append(stripped)

    # Collapse consecutive blank lines
    result = "\n".join(kept)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()
