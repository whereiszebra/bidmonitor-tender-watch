"""
TED 欧盟官方标讯爬虫（Tenders Electronic Daily）

接口：POST https://api.ted.europa.eu/v3/notices/search
特点：官方、免密钥、结构化 JSON，覆盖全欧盟政府采购公告。

查询语法（TED v3 expert search，实测要点）：
- 全文检索      FT~"water treatment"
- 日期过滤      PD>=20260801（YYYYMMDD）
- 排序只能写在 query 里：SORT BY publication-date DESC
  （把 sortBy/orderBy/sort 当 JSON 字段传会直接 400，实测确认）
- scope=ALL 全量归档；ACTIVE 仅当前开放中的公告
- 多语言字段（notice-title / buyer-name）是 {语言: [值]} 字典，优先取 eng
- 公告页地址：https://ted.europa.eu/en/notice/-/detail/<publication-number>

注意：这是公共公益 API，别高频打；默认每个关键词只取 1 页。
"""
import time
import random
from typing import List, Dict, Any, Optional

from .base import BaseCrawler, BidInfo


class TEDCrawler(BaseCrawler):
    """TED（欧盟官方标讯）爬虫"""

    name = "ted"
    base_url = "https://api.ted.europa.eu"
    api_path = "/v3/notices/search"
    notice_url = "https://ted.europa.eu/en/notice/-/detail/"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        kws = [k for k in (config.get('search_keywords') or []) if k and k.strip()]
        # TED 是英文库：中文关键词搜不出东西，这里只保留非中文词
        kws = [k for k in kws if not any('\u4e00' <= ch <= '\u9fff' for ch in k)]
        # 英文兜底词
        self.search_keywords = kws or ['water treatment', 'membrane']
        # 只要发布日期在该日期之后的公告（YYYYMMDD）
        self.since = str(config.get('ted_since', '20260101'))
        self.max_pages = int(config.get('ted_max_pages', 1))
        self.page_limit = int(config.get('ted_limit', 50))
        self.scope = config.get('ted_scope', 'ALL')

    def get_list_urls(self) -> List[str]:
        return [self.base_url + self.api_path]

    def parse(self, html: str) -> List[BidInfo]:
        """兼容基类接口"""
        import json
        try:
            payload = json.loads(html)
        except Exception:
            return []
        return self._parse_payload(payload)

    # ------------------------------------------------------------------ 抓取
    def _search(self, query: str, page: int) -> Optional[Dict[str, Any]]:
        body = {
            'query': query,
            'fields': ['publication-number', 'notice-title', 'buyer-name',
                       'buyer-country', 'publication-date', 'deadline',
                       'classification-cpv', 'notice-type', 'contract-nature'],
            'limit': self.page_limit,
            'scope': self.scope,
            'paginationMode': 'ITERATION',
            'page': page,
        }
        headers = self._get_headers()
        headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        })
        try:
            resp = self.session.post(self.base_url + self.api_path,
                                     json=body, headers=headers,
                                     timeout=self.timeout)
            if resp.status_code == 429:
                self.logger.warning('[ted] 被限流(429)，停止本次抓取')
                return None
            if resp.status_code != 200:
                self.logger.warning(f'[ted] HTTP {resp.status_code}')
                return None
            return resp.json()
        except Exception as e:
            self.logger.warning(f'[ted] 请求异常: {e}')
            return None

    def crawl(self, stop_event=None) -> Optional[List[BidInfo]]:
        all_bids: List[BidInfo] = []
        seen = set()
        attempted = 0
        succeeded = 0

        for keyword in self.search_keywords:
            for page in range(1, self.max_pages + 1):
                if stop_event and stop_event.is_set():
                    return all_bids

                query = (f'FT~"{keyword}" AND PD>={self.since} '
                         f'SORT BY publication-date DESC')
                attempted += 1
                payload = self._search(query, page)
                if payload is None:
                    break
                succeeded += 1

                notices = payload.get('notices') or []
                total = payload.get('totalNoticeCount')
                new_in_page = 0
                for n in notices:
                    bid = self._to_bid(n)
                    if bid is None or bid.url in seen:
                        continue
                    seen.add(bid.url)
                    all_bids.append(bid)
                    new_in_page += 1

                self.logger.info(
                    f'[ted] 关键词「{keyword}」第 {page} 页: {len(notices)} 条'
                    f'(总 {total}), 新增 {new_in_page}'
                )

                if not notices or len(notices) < self.page_limit or new_in_page == 0:
                    break
                time.sleep(self.request_delay + random.uniform(0.5, 1.5))

            time.sleep(self.request_delay + random.uniform(0.5, 1.5))

        self.logger.info(
            f'[ted] 抓取完成: {len(all_bids)} 条候选, '
            f'请求 {attempted} 次、成功 {succeeded} 次'
        )
        if succeeded == 0:
            return None
        return all_bids

    # ------------------------------------------------------------------ 解析
    def _parse_payload(self, payload: Dict[str, Any]) -> List[BidInfo]:
        out = []
        for n in payload.get('notices') or []:
            bid = self._to_bid(n)
            if bid is not None:
                out.append(bid)
        return out

    @staticmethod
    def _pick(value: Any) -> str:
        """多语言字段取值：优先 eng，其次任意语言"""
        if value is None:
            return ''
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            v = value.get('eng')
            if isinstance(v, list):
                return v[0] if v else ''
            if v:
                return str(v)
            for v in value.values():
                if isinstance(v, list) and v:
                    return v[0]
                if v:
                    return str(v)
            return ''
        if isinstance(value, list):
            return str(value[0]) if value else ''
        return str(value)

    def _to_bid(self, n: Dict[str, Any]) -> Optional[BidInfo]:
        num = n.get('publication-number') or ''
        title = self._pick(n.get('notice-title')).strip()
        if not num and not title:
            return None
        if not title:
            title = f'TED notice {num}'

        url = self.notice_url + num if num else self.notice_url

        parts = []
        pub = str(n.get('publication-date') or '')
        if pub:
            parts.append(f"发布日期: {pub[:10]}")
        buyer = self._pick(n.get('buyer-name'))
        if buyer:
            parts.append(f"采购方: {buyer}")
        country = n.get('buyer-country')
        if isinstance(country, list):
            country = ','.join(str(c) for c in country)
        if country:
            parts.append(f"国家: {country}")
        cpv = n.get('classification-cpv')
        if isinstance(cpv, list):
            cpv = ','.join(str(c) for c in cpv)
        if cpv:
            parts.append(f"CPV: {cpv}")
        if n.get('notice-type'):
            parts.append(f"类型: {n['notice-type']}")
        if n.get('contract-nature'):
            parts.append(f"标的性质: {n['contract-nature']}")
        dl = str(n.get('deadline') or '')
        if dl:
            parts.append(f"截止: {dl[:10]}")

        return BidInfo(
            title=title,
            url=url,
            publish_date=pub[:10],
            source='TED 欧盟标讯',
            content=' | '.join(parts),
        )
