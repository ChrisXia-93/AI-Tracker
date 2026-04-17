"""
AI 人才流动追踪 - MVP 版本
每周抓取 3 个信源，用 DeepSeek 抽取人才流动信息
"""
import feedparser
import json
import os
from datetime import datetime, timezone
from openai import OpenAI

# ========== 配置 ==========
RSS_FEEDS = [
    {"name": "TechCrunch AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/", "lang": "en"},
    {"name": "机器之心", "url": "https://www.jiqizhixin.com/rss", "lang": "zh"},
    {"name": "36氪 AI", "url": "https://36kr.com/feed-newsflash", "lang": "zh"},
]

# DeepSeek 客户端（兼容 OpenAI SDK）
client = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com"
)

EXTRACT_PROMPT = """你是一个 AI 行业信息分析助手。请判断下面这篇新闻是否描述了"AI 行业知名人物的工作变动"（跳槽、加入、离职、创业等）。

只有当满足以下全部条件时，才视为有效的人才流动事件：
1. 明确提到具体人名
2. 此人是 AI 行业的知名研究员、公司高管或核心开发者（例如 OpenAI / Anthropic / DeepMind / Meta AI / xAI / DeepSeek / Moonshot / 智谱 / 百川 / 阶跃 / 字节 Seed / MiniMax 等公司的研究员、VP、创始人等）
3. 涉及实际的公司变动

请严格按照以下 JSON 格式返回（不要有任何额外文字）：
{
  "is_talent_move": true 或 false,
  "person_name": "姓名（中文或英文原文）",
  "from_company": "原公司（不清楚则填 unknown）",
  "to_company": "新公司（不清楚则填 unknown）",
  "role": "新职位（不清楚则填 unknown）",
  "seniority": "研究员/高管/创始人/核心开发者/其他",
  "summary": "一句话总结（不超过 50 字）",
  "confidence": 0.0 到 1.0 之间的浮点数
}

如果不是人才流动新闻，返回：{"is_talent_move": false}

新闻标题：{title}
新闻内容：{content}
"""

def extract_from_article(title, content):
    """用 DeepSeek 从一篇文章里抽取人才流动信息"""
    # 截断过长的内容，省 token
    content = content[:2000] if content else ""
    prompt = EXTRACT_PROMPT.replace("{title}", title).replace("{content}", content)
    
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        print(f"  ⚠️ 抽取失败: {e}")
        return {"is_talent_move": False}

def load_existing():
    """读取已有数据，用于去重"""
    if os.path.exists("data.json"):
        with open("data.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {"items": [], "last_updated": None}

def main():
    print("🚀 开始抓取 AI 人才流动...")
    existing = load_existing()
    seen_urls = {item["source_url"] for item in existing["items"]}
    new_items = []

    for feed in RSS_FEEDS:
        print(f"\n📡 抓取 {feed['name']} ...")
        try:
            parsed = feedparser.parse(feed["url"])
            entries = parsed.entries[:20]  # 每个源最多看 20 篇最新的
            print(f"  找到 {len(entries)} 篇文章")
            
            for entry in entries:
                url = entry.get("link", "")
                if url in seen_urls:
                    continue
                
                title = entry.get("title", "")
                content = entry.get("summary", "") or entry.get("description", "")
                
                # 先用关键词粗筛，省 API 调用
                keywords = ["join", "hire", "leave", "depart", "poach", "CEO", "CTO",
                           "加入", "跳槽", "离职", "出走", "挖", "就任", "离开", "创业"]
                text = (title + content).lower()
                if not any(kw.lower() in text for kw in keywords):
                    continue
                
                print(f"  🔍 分析: {title[:60]}...")
                result = extract_from_article(title, content)
                
                if result.get("is_talent_move") and result.get("confidence", 0) >= 0.7:
                    result["source_url"] = url
                    result["source_name"] = feed["name"]
                    result["scraped_at"] = datetime.now(timezone.utc).isoformat()
                    new_items.append(result)
                    print(f"  ✅ 命中: {result.get('person_name')} ({result.get('from_company')} → {result.get('to_company')})")
        except Exception as e:
            print(f"  ❌ 源抓取失败: {e}")

    # 合并新旧数据，按时间倒序
    all_items = new_items + existing["items"]
    # 按 scraped_at 倒序，最多保留 500 条
    all_items.sort(key=lambda x: x.get("scraped_at", ""), reverse=True)
    all_items = all_items[:500]

    output = {
        "items": all_items,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "total_count": len(all_items),
    }
    
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n✨ 完成！本次新增 {len(new_items)} 条，总计 {len(all_items)} 条")

if __name__ == "__main__":
    main()
