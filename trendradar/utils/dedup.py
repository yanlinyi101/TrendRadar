# coding=utf-8
"""
事件聚类（去重）工具

借鉴 AIHOT 的事件聚类思路：用标题文本相似度把同一事件的多条报道聚到一个簇里，
簇内只保留 representative（最有价值的那条），其余折叠成 "另有 N 条相关报道"。

简化方案：64-bit SimHash + 汉明距离阈值
- 不引入 jieba / simhash 第三方依赖（标准库 + hashlib）
- token 用 character 3-gram，对中英文混合标题都适用
- 汉明距离 ≤ threshold（默认 6）视为同事件，对应 ~90% 相似度

更精确的 embedding 聚类留作 Phase 5。
"""

import hashlib
from typing import Iterable, List, Set


def _normalize_text(text: str) -> str:
    """归一化：去标点空白、转小写。保留中英文字符与数字。"""
    if not text:
        return ""
    out: List[str] = []
    for ch in text:
        if ch.isalnum() or "一" <= ch <= "鿿":
            out.append(ch.lower())
    return "".join(out)


def _char_ngrams(text: str, n: int = 3) -> Iterable[str]:
    """字符 n-gram tokenizer。文本短于 n 时退化为整个文本。"""
    text = _normalize_text(text)
    if len(text) < n:
        if text:
            yield text
        return
    for i in range(len(text) - n + 1):
        yield text[i : i + n]


def simhash64(text: str, n: int = 3) -> int:
    """
    计算 64-bit SimHash。

    Args:
        text: 输入文本
        n: char n-gram 大小

    Returns:
        64-bit 整数指纹。空文本返回 0。
    """
    accumulator = [0] * 64
    has_token = False
    for token in _char_ngrams(text, n=n):
        has_token = True
        # md5 取前 8 字节作为 64-bit hash
        h = int.from_bytes(hashlib.md5(token.encode("utf-8")).digest()[:8], "big")
        for i in range(64):
            if h & (1 << i):
                accumulator[i] += 1
            else:
                accumulator[i] -= 1
    if not has_token:
        return 0
    fingerprint = 0
    for i in range(64):
        if accumulator[i] > 0:
            fingerprint |= 1 << i
    return fingerprint


def hamming_distance(a: int, b: int) -> int:
    """两个整数的汉明距离（不同 bit 的数量）。"""
    # Python 3.10+ 有 int.bit_count()，老版本 fallback
    x = a ^ b
    return bin(x).count("1")


def cluster_by_simhash(
    items: List[dict],
    *,
    text_key: str = "title",
    threshold: int = 6,
    score_key: str = "final_score",
) -> List[dict]:
    """
    在排好序的 items 列表上做贪心事件聚类。

    输入：按价值降序排好的 items 列表（每个 item 是 dict）
    输出：每个 representative 加上：
        - "cluster_count": 簇大小（包含自己）
        - "cluster_titles": 被折叠的标题列表（不含自己，按原顺序）

    保留前面的（更高分的）作为 representative，是为了让 final_score 更高、
    tier 更靠前的内容自然成为主条。

    Args:
        items: 已按 score_key 降序排好的 dict 列表
        text_key: 用于计算 SimHash 的字段名
        threshold: 汉明距离阈值（≤ 视为同簇）
        score_key: 得分字段名（仅用于日志，不参与聚类决策）

    Returns:
        representative items（保留 cluster_count / cluster_titles 元数据）
    """
    if not items:
        return []

    representatives: List[dict] = []
    rep_hashes: List[int] = []

    for item in items:
        text = str(item.get(text_key, ""))
        h = simhash64(text)

        merged_into: int = -1
        if h != 0 and rep_hashes:
            for idx, rep_h in enumerate(rep_hashes):
                if rep_h != 0 and hamming_distance(h, rep_h) <= threshold:
                    merged_into = idx
                    break

        if merged_into >= 0:
            rep = representatives[merged_into]
            rep.setdefault("cluster_count", 1)
            rep["cluster_count"] += 1
            rep.setdefault("cluster_titles", []).append(text)
        else:
            item.setdefault("cluster_count", 1)
            item.setdefault("cluster_titles", [])
            representatives.append(item)
            rep_hashes.append(h)

    return representatives
