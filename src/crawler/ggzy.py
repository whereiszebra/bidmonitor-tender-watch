"""
全国公共资源交易平台爬虫（真实可用版）

网站：https://www.ggzy.gov.cn/
接口：POST /information/pubTradingInfo/getTradList

为什么重写：
- 列表页 dealList.html 是 Vue 前端，数据由上述 AJAX 接口以 JSON 返回，
  原实现的 dealList_find.jsp（DEAL_* 版）实测已 502/失效，解析 HTML 也拿不到数据。
- 接口必须带 DEAL_TIME（时间范围代码），否则直接报错：
    01/02/03/06 实测返回 0 条；04、05 返回真实数据。默认用 04。
- FINDTXT 是站内关键词。注意：关键词无命中时该站会「回退返回全量列表」
  （实测「管式膜」返回 total=1000 且首条与无关键词列举相同），
  所以本地由 KeywordMatcher 对标题再做一次精确过滤，杜绝假命中。
- 接口有风控：code=829 需验证码、800 过于频繁、804 需细化条件。
  命中即停止翻页，不硬刚。
"""
import json
import random
import time
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin

from .base import BaseCrawler, BidInfo


class GGZYCrawler(BaseCrawler):
    """全国公共资源交易平台爬虫（基于官方 AJAX 接口）"""

    name = "ggzy"
    base_url = "https://www.ggzy.gov.cn"
    api_path = "/information/pubTradingInfo/getTradList"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        kws = [k for k in (config.get('search_keywords') or []) if k and k.strip()]
        # 只取中文关键词：GGZY 是国内站，英文词没意义
        kws = [k for k in kws if any('\u4e00' <= ch <= '\u9fff' for ch in k)]
        # 兜底：上游若没传中文关键词，用一个宽口径中文词拉回候选，
        # 再由 KeywordMatcher 精确过滤，避免"没关键词就啥都不抓"。
        self.search_keywords = kws or ['水务']
        self.deal_time = str(config.get('ggzy_deal_time', '04'))
        self.max_pages = int(config.get('ggzy_max_pages', 6))

    # 基类抽象方法：本爬虫走 POST 接口，此处仅作占位
    def get_list_urls(self) -> List[str]:
        return [self.base_url + self.api_path]

    def parse(self, html: str) -> List[BidInfo]:
        """兼容基类接口：把 JSON 文本当输入解析"""
        try:
            payload = json.loads(html)
        except Exception:
            return []
        return self._parse_payload(payload)

    # ------------------------------------------------------------------ 抓取
    def _post(self, data: Dict[str, str]) -> Optional[Dict[str, Any]]:
        url = self.base_url + self.api_path
        headers = self._get_headers()
        headers.update({
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': f'{self.base_url}/deal/dealList.html',
            'Origin': self.base_url,
            'X-Requested-With': 'XMLHttpRequest',
        })
        try:
            resp = self.session.post(url, data=data, headers=headers,
                                     timeout=self.timeout)
            if resp.status_code != 200:
                self.logger.warning(f'[ggzy] HTTP {resp.status_code}')
                return None
            return resp.json()
        except Exception as e:
            self.logger.warning(f'[ggzy] 请求异常: {e}')
            return None

    def crawl(self, stop_event=None) -> Optional[List[BidInfo]]:
        """按关键词查询接口并翻页，返回候选列表（上层再做精确匹配）"""
        keywords = [k for k in self.search_keywords if k and k.strip()]
        if not keywords:
            self.logger.warning('[ggzy] 没有关键词，跳过')
            return []

        all_bids: List[BidInfo] = []
        seen_urls = set()
        attempted = 0
        succeeded = 0

        for keyword in keywords:
            for page in range(1, self.max_pages + 1):
                if stop_event and stop_event.is_set():
                    self.logger.info('[ggzy] 收到停止信号')
                    return all_bids

                data = {
                    'FINDTXT': keyword,
                    'DEAL_TIME': self.deal_time,
                    'PAGENUMBER': str(page),
                }
                attempted += 1
                payload = self._post(data)
                if payload is None:
                    break

                code = payload.get('code')
                if code == 829:
                    self.logger.warning('[ggzy] 触发验证码(829)，停止本次抓取')
                    break
                if code == 800:
                    self.logger.warning('[ggzy] 操作过于频繁(800)，停止本次抓取')
                    break
                if code == 804:
                    self.logger.warning('[ggzy] 需细化查询条件(804)')
                    break
                if code != 200:
                    self.logger.warning(
                        f"[ggzy] 接口 code={code} msg={payload.get('message')}")
                    break

                succeeded += 1
                body = payload.get('data') or {}
                records = body.get('records') or []
                total = body.get('total') or 0
                pages = body.get('pages') or 0

                new_in_page = 0
                for rec in records:
                    bid = self._to_bid(rec)
                    if bid is None or bid.url in seen_urls:
                        continue
                    seen_urls.add(bid.url)
                    all_bids.append(bid)
                    new_in_page += 1

                self.logger.info(
                    f"[ggzy] 关键词「{keyword}」第 {page} 页: {len(records)} 条"
                    f"(总 {total}, 共 {pages} 页), 新增 {new_in_page}"
                )

                if page >= pages or not records or new_in_page == 0:
                    break

                time.sleep(self.request_delay + random.uniform(0.5, 1.5))

            time.sleep(self.request_delay + random.uniform(0.5, 1.5))

        self.logger.info(
            f'[ggzy] 抓取完成: {len(all_bids)} 条候选, '
            f'请求 {attempted} 次、成功 {succeeded} 次'
        )

        if succeeded == 0:
            return None
        return all_bids

    # ------------------------------------------------------------------ 解析
    def _parse_payload(self, payload: Dict[str, Any]) -> List[BidInfo]:
        body = payload.get('data') or {}
        bids = []
        for rec in body.get('records') or []:
            bid = self._to_bid(rec)
            if bid is not None:
                bids.append(bid)
        return bids

    def _to_bid(self, rec: Dict[str, Any]) -> Optional[BidInfo]:
        title = (rec.get('title') or '').strip()
        if not title:
            return None

        path = rec.get('url') or ''
        if path and not path.startswith('http'):
            url = urljoin(self.base_url, path)
        else:
            url = path or f"{self.base_url}/#id={rec.get('id', '')}"

        meta = []
        if rec.get('publishTime'):
            meta.append(f"发布日期: {rec['publishTime']}")
        if rec.get('provinceText'):
            region = rec['provinceText']
            if rec.get('cityText'):
                region += rec['cityText']
            meta.append(f"地区: {region}")
        if rec.get('businessTypeText'):
            meta.append(f"业务类型: {rec['businessTypeText']}")
        if rec.get('informationTypeText'):
            meta.append(f"信息类型: {rec['informationTypeText']}")
        if rec.get('transactionSourcesPlatformText'):
            meta.append(f"交易平台: {rec['transactionSourcesPlatformText']}")

        return BidInfo(
            title=title,
            url=url,
            publish_date=rec.get('publishTime') or '',
            source='全国公共资源交易平台',
            content=' | '.join(meta),
        )
