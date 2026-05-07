# coding=utf-8
"""
平台标题格式化模块

提供多平台标题格式化功能
"""

from typing import Dict

from trendradar.report.helpers import clean_title, html_escape, format_rank_display


def _build_score_badge(platform: str, title_data: Dict) -> str:
    """构造 final_score 徽标（行尾追加），仅当 title_data 含 final_score 时返回内容

    Phase 1+2+4 把 tier × decay × ai_relevance 算成 final_score 写入 title_data。
    展示时让分数显示在标题行末，方便用户一眼判断这条新闻的综合"含金量"。

    样式（按平台特性）：
      [T1 0.85]  ← 高分（≥0.7）红色 / [T1 0.62] ← 中等（0.5-0.7）橙色 / [T2 0.42] ← 低分灰色

    没有 final_score 字段 → 返回空串（向后兼容，旧调用不受影响）
    """
    if "final_score" not in title_data:
        return ""

    try:
        score = float(title_data.get("final_score") or 0.0)
    except (ValueError, TypeError):
        return ""

    tier = str(title_data.get("tier") or "").strip()
    label = f"{tier} {score:.2f}" if tier else f"{score:.2f}"

    if platform == "feishu":
        if score >= 0.7:
            color = "red"
        elif score >= 0.5:
            color = "orange"
        else:
            color = "grey"
        return f" <font color='{color}'>📊 {label}</font>"

    if platform == "html":
        css_class = "score-high" if score >= 0.7 else "score-mid" if score >= 0.5 else "score-low"
        return f" <span class='score-badge {css_class}'>📊 {label}</span>"

    if platform == "telegram":
        return f" <code>📊 {label}</code>"

    if platform == "slack":
        return f" `📊 {label}`"

    # dingtalk / wework / bark / ntfy / fallback
    return f" `📊 {label}`"


def format_title_for_platform(
    platform: str, title_data: Dict, show_source: bool = True, show_keyword: bool = False
) -> str:
    """统一的标题格式化方法

    为不同平台生成对应格式的标题字符串。

    Args:
        platform: 目标平台，支持:
            - "feishu": 飞书
            - "dingtalk": 钉钉
            - "wework": 企业微信
            - "bark": Bark
            - "telegram": Telegram
            - "ntfy": ntfy
            - "slack": Slack
            - "html": HTML 报告
        title_data: 标题数据字典，包含以下字段:
            - title: 标题文本
            - source_name: 来源名称
            - time_display: 时间显示
            - count: 出现次数
            - ranks: 排名列表
            - rank_threshold: 高亮阈值
            - url: PC端链接
            - mobile_url: 移动端链接（优先使用）
            - is_new: 是否为新增标题（可选）
            - matched_keyword: 匹配的关键词（可选，platform 模式使用）
        show_source: 是否显示来源名称（keyword 模式使用）
        show_keyword: 是否显示关键词标签（platform 模式使用）

    Returns:
        格式化后的标题字符串
    """
    rank_display = format_rank_display(
        title_data["ranks"], title_data["rank_threshold"], platform
    )

    link_url = title_data["mobile_url"] or title_data["url"]
    cleaned_title = clean_title(title_data["title"])

    # 获取关键词标签（platform 模式使用）
    keyword = title_data.get("matched_keyword", "") if show_keyword else ""

    if platform == "feishu":
        if link_url:
            formatted_title = f"[{cleaned_title}]({link_url})"
        else:
            formatted_title = cleaned_title

        title_prefix = "🆕 " if title_data.get("is_new") else ""

        if show_source:
            result = f"<font color='grey'>[{title_data['source_name']}]</font> {title_prefix}{formatted_title}"
        elif show_keyword and keyword:
            result = f"<font color='blue'>[{keyword}]</font> {title_prefix}{formatted_title}"
        else:
            result = f"{title_prefix}{formatted_title}"

        if rank_display:
            result += f" {rank_display}"
        if title_data["time_display"]:
            result += f" <font color='grey'>- {title_data['time_display']}</font>"
        if title_data["count"] > 1:
            result += f" <font color='green'>({title_data['count']}次)</font>"

        result += _build_score_badge("feishu", title_data)
        return result

    elif platform == "dingtalk":
        if link_url:
            formatted_title = f"[{cleaned_title}]({link_url})"
        else:
            formatted_title = cleaned_title

        title_prefix = "🆕 " if title_data.get("is_new") else ""

        if show_source:
            result = f"[{title_data['source_name']}] {title_prefix}{formatted_title}"
        elif show_keyword and keyword:
            result = f"[{keyword}] {title_prefix}{formatted_title}"
        else:
            result = f"{title_prefix}{formatted_title}"

        if rank_display:
            result += f" {rank_display}"
        if title_data["time_display"]:
            result += f" - {title_data['time_display']}"
        if title_data["count"] > 1:
            result += f" ({title_data['count']}次)"

        result += _build_score_badge("dingtalk", title_data)
        return result

    elif platform in ("wework", "bark"):
        # WeWork 和 Bark 使用 markdown 格式
        if link_url:
            formatted_title = f"[{cleaned_title}]({link_url})"
        else:
            formatted_title = cleaned_title

        title_prefix = "🆕 " if title_data.get("is_new") else ""

        if show_source:
            result = f"[{title_data['source_name']}] {title_prefix}{formatted_title}"
        elif show_keyword and keyword:
            result = f"[{keyword}] {title_prefix}{formatted_title}"
        else:
            result = f"{title_prefix}{formatted_title}"

        if rank_display:
            result += f" {rank_display}"
        if title_data["time_display"]:
            result += f" - {title_data['time_display']}"
        if title_data["count"] > 1:
            result += f" ({title_data['count']}次)"

        result += _build_score_badge(platform, title_data)
        return result

    elif platform == "telegram":
        if link_url:
            formatted_title = f'<a href="{link_url}">{html_escape(cleaned_title)}</a>'
        else:
            formatted_title = cleaned_title

        title_prefix = "🆕 " if title_data.get("is_new") else ""

        if show_source:
            result = f"[{title_data['source_name']}] {title_prefix}{formatted_title}"
        elif show_keyword and keyword:
            result = f"<b>[{html_escape(keyword)}]</b> {title_prefix}{formatted_title}"
        else:
            result = f"{title_prefix}{formatted_title}"

        if rank_display:
            result += f" {rank_display}"
        if title_data["time_display"]:
            result += f" <code>- {title_data['time_display']}</code>"
        if title_data["count"] > 1:
            result += f" <code>({title_data['count']}次)</code>"

        result += _build_score_badge("telegram", title_data)
        return result

    elif platform == "ntfy":
        if link_url:
            formatted_title = f"[{cleaned_title}]({link_url})"
        else:
            formatted_title = cleaned_title

        title_prefix = "🆕 " if title_data.get("is_new") else ""

        if show_source:
            result = f"[{title_data['source_name']}] {title_prefix}{formatted_title}"
        elif show_keyword and keyword:
            result = f"[{keyword}] {title_prefix}{formatted_title}"
        else:
            result = f"{title_prefix}{formatted_title}"

        if rank_display:
            result += f" {rank_display}"
        if title_data["time_display"]:
            result += f" `- {title_data['time_display']}`"
        if title_data["count"] > 1:
            result += f" `({title_data['count']}次)`"

        result += _build_score_badge("ntfy", title_data)
        return result

    elif platform == "slack":
        # Slack 使用 mrkdwn 格式
        if link_url:
            # Slack 链接格式: <url|text>
            formatted_title = f"<{link_url}|{cleaned_title}>"
        else:
            formatted_title = cleaned_title

        title_prefix = "🆕 " if title_data.get("is_new") else ""

        if show_source:
            result = f"[{title_data['source_name']}] {title_prefix}{formatted_title}"
        elif show_keyword and keyword:
            result = f"*[{keyword}]* {title_prefix}{formatted_title}"
        else:
            result = f"{title_prefix}{formatted_title}"

        # 排名（使用 * 加粗）
        rank_display = format_rank_display(
            title_data["ranks"], title_data["rank_threshold"], "slack"
        )
        if rank_display:
            result += f" {rank_display}"
        if title_data["time_display"]:
            result += f" `- {title_data['time_display']}`"
        if title_data["count"] > 1:
            result += f" `({title_data['count']}次)`"

        result += _build_score_badge("slack", title_data)
        return result

    elif platform == "html":
        rank_display = format_rank_display(
            title_data["ranks"], title_data["rank_threshold"], "html"
        )

        link_url = title_data["mobile_url"] or title_data["url"]

        escaped_title = html_escape(cleaned_title)
        escaped_source_name = html_escape(title_data["source_name"])

        # 构建前缀（来源或关键词）
        if show_source:
            prefix = f'<span class="source-tag">[{escaped_source_name}]</span> '
        elif show_keyword and keyword:
            escaped_keyword = html_escape(keyword)
            prefix = f'<span class="keyword-tag">[{escaped_keyword}]</span> '
        else:
            prefix = ""

        if link_url:
            escaped_url = html_escape(link_url)
            formatted_title = f'{prefix}<a href="{escaped_url}" target="_blank" class="news-link">{escaped_title}</a>'
        else:
            formatted_title = f'{prefix}<span class="no-link">{escaped_title}</span>'

        if rank_display:
            formatted_title += f" {rank_display}"
        if title_data["time_display"]:
            escaped_time = html_escape(title_data["time_display"])
            formatted_title += f" <font color='grey'>- {escaped_time}</font>"
        if title_data["count"] > 1:
            formatted_title += f" <font color='green'>({title_data['count']}次)</font>"

        formatted_title += _build_score_badge("html", title_data)

        if title_data.get("is_new"):
            formatted_title = f"<div class='new-title'>🆕 {formatted_title}</div>"

        return formatted_title

    else:
        return cleaned_title
