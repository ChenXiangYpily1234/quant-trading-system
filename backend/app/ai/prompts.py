SYSTEM = "你是基金数据解释器。只解释已提供的数据，不给出买卖、仓位或收益承诺。只输出JSON。"


def explanation_prompt(name, signal, risk, news_titles):
    return (f"基金：{name}\n信号：{signal}\n风险：{risk}\n新闻标题：{news_titles[:5]}\n"
            '输出 {"headline":"", "summary":"", "key_points":[], "risk_note":""}')
