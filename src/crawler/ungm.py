"""
UNGM（联合国全球市场）标讯爬虫

站点：https://www.ungm.org/Public/Notice
搜索：POST https://www.ungm.org/Public/Notice/Search（返回 HTML 片段，非 JSON）

实测要点：
- 返回的是 HTML 行片段，需要按 CSS 选择器解析，不是 JSON。
- 每页固定返回 15 条，用 PageIndex 翻页（0 起）。
- `Description` 字段做服务端关键词过滤有效；标题用 `.ungm-title`。
- 行结构（tableRow.dataRow）：
    标题   .tableCell.resultTitle .ungm-title
    链接   .tableCell.resultTitle a[href^="/Public/Notice/"]
    截止   .tableCell.deadline span（第 1 个）
    发布   .tableCell.deadline 之后的下一个 .tableCell span —— 形如 15-Sep-2026
    机构   .tableCell.resultAgency span
    类型   .tableCell label（如 Request for quotation）
    国家   最后一个 .tableCell span
- 日期是 DD-Mon-YYYY，需转成 YYYY-MM-DD 入库。
"""
import re
import time
import random
from datetime import datetime
from typing import List, Dict, Any, Optional

from bs4 import BeautifulSoup

from .base import BaseCrawler, BidInfo

_MONTHS = {m: i for i, m in enumerate(
    ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
     'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], start=1)}


class UNGMCrawler(BaseCrawler):
    """联合国全球市场（UNGM）爬虫"""

    name = "ungm"
    base_url = "https://www.ungm.org"
    search_path = "/Public/Notice/Search"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        kws = [k for k in (config.get('search_keywords') or []) if k and k.strip()]
        # UNGM 是英文库：去掉中文词
        kws = [k for k in kws if not any('\u4e00' <= ch <= '\u9fff' for ch in k)]
        self.search_keywords = kws or ['water']
        self.max_pages = int(config.get('ungm_max_pages', 2))

    def get_list_urls(self) -> List[str]:
        return [self.base_url + self.search_path]

    def parse(self, html: str) -> List[BidInfo]:
        return self._parse_rows(html, '')

    # ------------------------------------------------------------------ 抓取
    def _search(self, keyword: str, page: int) -> Optional[str]:
        body = {
            'PageIndex': page,
            'PageSize': 100,
            'Title': '',
            'Description': keyword,
            'Reference': '',
            'PublishedFrom': '',
            'PublishedTo': '',
            'DeadlineFrom': '',
            'DeadlineTo': '',
            'Agencies': [],
            'Countries': [],
            'NoticeTypes': [],
            'SortField': 'DatePublished',
            'SortAscending': False,
        }
        headers = self._get_headers()
        headers.update({
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': f'{self.base_url}/Public/Notice',
        })
        try:
            resp = self.session.post(self.base_url + self.search_path,
                                     json=body, headers=headers,
                                     timeout=self.timeout)
            if resp.status_code != 200:
                self.logger.warning(f'[ungm] HTTP {resp.status_code}')
                return None
            return resp.text
        except Exception as e:
            self.logger.warning(f'[ungm] 请求异常: {e}')
            return None

    def crawl(self, stop_event=None) -> Optional[List[BidInfo]]:
        all_bids: List[BidInfo] = []
        seen = set()
        attempted = 0
        succeeded = 0

        for keyword in self.search_keywords:
            for page in range(0, self.max_pages):
                if stop_event and stop_event.is_set():
                    return all_bids

                attempted += 1
                html = self._search(keyword, page)
                if html is None:
                    break
                succeeded += 1

                bids = self._parse_rows(html, keyword)
                new_in_page = 0
                for b in bids:
                    if b.url in seen:
                        continue
                    seen.add(b.url)
                    all_bids.append(b)
                    new_in_page += 1

                self.logger.info(
                    f'[ungm] 关键词「{keyword}」第 {page + 1} 页: '
                    f'{len(bids)} 条, 新增 {new_in_page}'
                )

                if len(bids) < 15 or new_in_page == 0:
                    break
                time.sleep(self.request_delay + random.uniform(0.5, 1.5))

            time.sleep(self.request_delay + random.uniform(0.5, 1.5))

        self.logger.info(
            f'[ungm] 抓取完成: {len(all_bids)} 条候选, '
            f'请求 {attempted} 次、成功 {succeeded} 次'
        )
        if succeeded == 0:
            return None
        return all_bids

    # ------------------------------------------------------------------ 解析
    @staticmethod
    def _to_iso(text: str) -> str:
        """15-Sep-2026 -> 2026-09-15"""
        m = re.search(r'(\d{1,2})-([A-Za-z]{3})-(\d{4})', text or '')
        if not m:
            return ''
        day, mon, year = m.group(1), m.group(2).title(), m.group(3)
        mm = _MONTHS.get(mon)
        if not mm:
            return ''
        return f'{year}-{mm:02d}-{int(day):02d}'

    def _parse_rows(self, html: str, keyword: str) -> List[BidInfo]:
        soup = BeautifulSoup(html, 'lxml')
        out: List[BidInfo] = []

        for row in soup.select('.tableRow.dataRow, tr.dataRow, .notice-table'):
            title_el = row.select_one('.ungm-title')
            link_el = row.select_one('a[href^="/Public/Notice/"]')
            if not title_el or not link_el:
                continue
            title = title_el.get_text(' ', strip=True)
            href = link_el.get('href', '')
            if not title or not href:
                continue
            url = href if href.startswith('http') else self.base_url + href

            cells = row.select('.tableCell')
            deadline = ''
            publish = ''
            agency = ''
            ntype = ''
            country = ''
            # 按语义 class 取，避免依赖列顺序
            dl_el = row.select_one('.tableCell.deadline span')
            if dl_el:
                deadline = dl_el.get_text(strip=True)
            ag_el = row.select_one('.tableCell.resultAgency span')
            if ag_el:
                agency = ag_el.get_text(strip=True)
            lab_el = row.select_one('.tableCell label')
            if lab_el:
                ntype = lab_el.get_text(strip=True)
            # 发布日期：deadline 单元格之后的第一个单元格里的日期
            for idx, c in enumerate(cells):
                if 'deadline' in (c.get('class') or []):
                    for nxt in cells[idx + 1:]:
                        iso = self._to_iso(nxt.get_text(' ', strip=True))
                        if iso:
                            publish = iso
                            break
                    break
            if not publish:
                # 兜底：整行里找第一个 DD-Mon-YYYY
                publish = self._to_iso(row.get_text(' ', strip=True))
            # 国家：行内最后一个非空 span 文本
            spans = [s.get_text(strip=True) for s in row.select('.tableCell span')]
            spans = [s for s in spans if s and not s.replace('.', '').isdigit()]
            if spans:
                country = spans[-1]

            parts = []
            if publish:
                parts.append(f'发布日期: {publish}')
            if deadline:
                parts.append(f'截止: {deadline}')
            if agency:
                parts.append(f'机构: {agency}')
            if ntype:
                parts.append(f'类型: {ntype}')
            if country:
                parts.append(f'国家: {country}')
            if keyword:
                parts.append(f'命中词: {keyword}')

            out.append(BidInfo(
                title=title,
                url=url,
                publish_date=publish,
                source='UNGM 联合国采购',
                content=' | '.join(parts),
            ))
        return out
