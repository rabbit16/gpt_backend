# -*- coding: utf-8 -*-
"""对话与绘图计费。

用户扣费（人民币）=
    供应商美元价
    × USD_TO_CNY
    × PROFIT_RATE
    × 用户折扣 discount
    × 用户个人倍率 money_rate

调利润只改 PROFIT_RATE：
- 1.0 = 按成本卖（供应商价 × 汇率）
- 1.3 = 加价 30%
- 1.5 = 默认加价 50%
- 2.0 = 售价翻倍

图像模型与 claude_proxy / TeamRouter 对齐（非 OpenAI 官方价）：
- GPT Image：billing=per_image，按输出最长边 1k/2k/4k 按张计费
- Gemini Image：billing=token，按 text_input / output（美元 / 百万 tokens）
实际主路径扣费在 claude_proxy；本表供旧入口估价、模式列表与兼容扣费。
"""
import json

USD_TO_CNY = 8
PROFIT_RATE = 1.5
TOKENS_PER_MILLION = 1_000_000
DEFAULT_CHAT_MODE = "gpt-5.6-luna"
DEFAULT_IMAGE_MODEL = "gpt-image-2"

# 官方 API 价：美元 / 百万 tokens（短上下文档）
CHAT_USD_PER_MILLION = {
    "gpt-5.6-luna": {"input": 0.20, "output": 1.20, "cached": 0.02, "label": "GPT-5.6 Luna"},
    "gpt-5.6-terra": {"input": 2.00, "output": 12.00, "cached": 0.20, "label": "GPT-5.6 Terra"},
    "gpt-5.6-sol": {"input": 4.00, "output": 20.00, "cached": 0.40, "label": "GPT-5.6 Sol"},
    "gpt-6-astra": {"input": 10.00, "output": 50.00, "cached": 1.00, "label": "GPT-6 Astra"},
    "gpt-5.3-codex": {"input": 1.75, "output": 14.00, "cached": 0.175, "label": "GPT-5.3 Codex"},
    "gpt-5.5": {"input": 5.00, "output": 30.00, "cached": 0.50, "label": "GPT-5.5"},
    "gpt-5.5-pro": {"input": 30.00, "output": 180.00, "label": "GPT-5.5 Pro"},
    "gpt-5.4": {"input": 2.50, "output": 15.00, "cached": 0.25, "label": "GPT-5.4"},
    "gpt-5.4-mini": {"input": 0.75, "output": 4.50, "cached": 0.075, "label": "GPT-5.4 Mini"},
    "gpt-5.4-nano": {"input": 0.20, "output": 1.25, "cached": 0.02, "label": "GPT-5.4 Nano"},
    "gpt-5.4-pro": {"input": 30.00, "output": 180.00, "label": "GPT-5.4 Pro"},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60, "cached": 0.075, "label": "GPT-4o Mini"},
    "gpt-4o": {"input": 2.50, "output": 10.00, "cached": 1.25, "label": "GPT-4o"},
    "gpt-3.5-turbo-0125": {"input": 0.50, "output": 1.50, "label": "GPT-3.5 Turbo"},
    "gpt-3.5-turbo-16k-0613": {"input": 3.00, "output": 4.00, "label": "GPT-3.5 16k"},
}

CHAT_MODE_ORDER = [
    "gpt-5.6-luna",
    "gpt-5.6-terra",
    "gpt-5.6-sol",
    "gpt-6-astra",
    "gpt-5.3-codex",
    "gpt-5.4-mini",
    "gpt-5.4",
    "gpt-5.4-nano",
    "gpt-4o-mini",
]

# TeamRouter / Teamo 图像成本价（对齐 claude_proxy.settings.macro.TEAMO_IMAGE_MODEL_MONEY_DICT）
# GPT Image：per_image_tiers 为 USD / 张；token 字段仅作展示/回退。
# Gemini Image：按 USD / 百万 tokens。
IMAGE_USD_PER_MILLION = {
    "gpt-image-2.5-sunburst": {
        "billing": "per_image",
        "per_image_tiers": {"1k": 0.006, "2k": 0.02, "4k": 0.025},
        "text_input": 0.5,
        "image_input": 0.8,
        "output": 3.0,
        "label": "GPT Image 2.5 Sunburst",
    },
    "gpt-image-2.5-flare": {
        "billing": "per_image",
        "per_image_tiers": {"1k": 0.006, "2k": 0.02, "4k": 0.025},
        "text_input": 0.5,
        "image_input": 0.8,
        "output": 3.0,
        "label": "GPT Image 2.5 Flare",
    },
    "gpt-image-2": {
        "billing": "per_image",
        "per_image_tiers": {"1k": 0.006, "2k": 0.02, "4k": 0.025},
        "text_input": 0.5,
        "image_input": 0.8,
        "output": 3.0,
        "label": "GPT Image 2",
    },
    "gemini-3.1-flash-image": {
        "billing": "token",
        "text_input": 0.3,
        "image_input": 0.0,
        "output": 36.0,
        "label": "Gemini 3.1 Flash Image",
    },
}

IMAGE_MODE_ORDER = [
    "gpt-image-2.5-sunburst",
    "gpt-image-2.5-flare",
    "gpt-image-2",
    "gemini-3.1-flash-image",
]

# 旧入口按次参考成本（人民币，未乘利润）。quality=low/medium/high 映射 1k/2k/4k。
# USD_TO_CNY：1k=0.006*8≈0.05，2k=0.02*8=0.16，4k=0.025*8=0.20
IMAGE_COST_CNY = {
    "gpt-image-2.5-sunburst": {"low": 0.05, "medium": 0.16, "high": 0.20},
    "gpt-image-2.5-flare": {"low": 0.05, "medium": 0.16, "high": 0.20},
    "gpt-image-2": {"low": 0.05, "medium": 0.16, "high": 0.20},
    "gemini-3.1-flash-image": {"low": 0.1, "medium": 0.3, "high": 0.6},
}

# quality 档位 → Teamo 尺寸档位
_QUALITY_TO_TIER = {"low": "1k", "medium": "2k", "high": "4k", "auto": "1k"}


def sell_cny_per_million(usd_per_million):
    return float(usd_per_million) * USD_TO_CNY * PROFIT_RATE


def sell_cny_per_image(usd_per_image):
    return float(usd_per_image) * USD_TO_CNY * PROFIT_RATE


def resolve_chat_mode(mode):
    if mode and mode in CHAT_USD_PER_MILLION:
        return mode
    return DEFAULT_CHAT_MODE


def resolve_image_model(model):
    raw = (model or "").strip().lower()
    if raw in IMAGE_USD_PER_MILLION:
        return raw
    if raw in IMAGE_COST_CNY:
        return raw
    if raw:
        for key in sorted(IMAGE_USD_PER_MILLION, key=len, reverse=True):
            if raw == key or raw.startswith(key + "-") or raw.startswith(key + "."):
                return key
    return DEFAULT_IMAGE_MODEL


def resolve_image_size_tier(size=None, quality=None):
    """Teamo：<=1024→1k，<=2048→2k，其余→4k；也可直接传 1k/2k/4k。"""
    raw = (size or "").strip().lower()
    if raw in {"1k", "2k", "4k"}:
        return raw
    if "x" in raw:
        parts = raw.split("x", 1)
        try:
            longest = max(int(parts[0]), int(parts[1]))
        except (TypeError, ValueError, IndexError):
            longest = 0
        if longest > 0:
            if longest <= 1024:
                return "1k"
            if longest <= 2048:
                return "2k"
            return "4k"
    q = (quality or "").strip().lower()
    if q in _QUALITY_TO_TIER:
        return _QUALITY_TO_TIER[q]
    return "1k"


def count_tokens(text, model=""):
    if not text:
        return 0
    try:
        import tiktoken
        try:
            encoding = tiktoken.encoding_for_model(model)
        except Exception:
            encoding = tiktoken.get_encoding("o200k_base")
        return len(encoding.encode(text))
    except Exception:
        return max(1, len(text) // 4)


def billed_input_text(prompt, context_list, without_context):
    prompt = prompt or ""
    if without_context and context_list and getattr(context_list, "context", None):
        try:
            return prompt + json.dumps(json.loads(context_list.context), ensure_ascii=False)
        except Exception:
            return prompt
    return prompt


def parse_usage_tokens(usage):
    if not usage:
        return 0, 0
    input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
    output_tokens = usage.get("completion_tokens") or usage.get("output_tokens") or 0
    return int(input_tokens or 0), int(output_tokens or 0)


def chat_cost_cny(mode, input_tokens, output_tokens, discount=1.0, money_rate=1.0):
    spec = CHAT_USD_PER_MILLION[resolve_chat_mode(mode)]
    usd = (
        int(input_tokens or 0) * spec["input"]
        + int(output_tokens or 0) * spec["output"]
    ) / TOKENS_PER_MILLION
    cost = usd * USD_TO_CNY * PROFIT_RATE * float(discount or 1) * float(money_rate or 1)
    return round(cost, 6)


def image_list_cny(model, quality):
    model = resolve_image_model(model)
    spec = IMAGE_USD_PER_MILLION.get(model) or {}
    tiers = spec.get("per_image_tiers") if isinstance(spec.get("per_image_tiers"), dict) else None
    if tiers:
        tier = resolve_image_size_tier(quality=quality)
        usd = float(tiers.get(tier) or tiers.get("1k") or 0)
        return round(usd * USD_TO_CNY * PROFIT_RATE, 4)
    qualities = IMAGE_COST_CNY.get(model) or IMAGE_COST_CNY[DEFAULT_IMAGE_MODEL]
    if quality not in qualities:
        quality = "medium" if "medium" in qualities else next(iter(qualities))
    return round(qualities[quality] * PROFIT_RATE, 2)


def charge_image_cny(model, quality, discount=1.0, money_rate=1.0, size=None):
    """兼容旧按次入口；GPT Image 走供应商按张档位。"""
    model = resolve_image_model(model)
    spec = IMAGE_USD_PER_MILLION.get(model) or {}
    tiers = spec.get("per_image_tiers") if isinstance(spec.get("per_image_tiers"), dict) else None
    if tiers:
        tier = resolve_image_size_tier(size=size, quality=quality)
        usd = float(tiers.get(tier) or tiers.get("1k") or 0)
        return round(
            usd * USD_TO_CNY * PROFIT_RATE * float(discount or 1) * float(money_rate or 1),
            4,
        )
    qualities = IMAGE_COST_CNY.get(model) or IMAGE_COST_CNY[DEFAULT_IMAGE_MODEL]
    if quality not in qualities:
        quality = "medium" if "medium" in qualities else next(iter(qualities))
    return round(
        qualities[quality] * PROFIT_RATE * float(discount or 1) * float(money_rate or 1),
        4,
    )


def charge_image_tokens_cny(
    model,
    text_tokens=0,
    image_input_tokens=0,
    output_tokens=0,
    discount=1.0,
    money_rate=1.0,
    n=1,
    size=None,
    quality=None,
):
    """图像计费：优先供应商 per_image 档位，否则按 tokens。"""
    model = resolve_image_model(model)
    spec = IMAGE_USD_PER_MILLION.get(model) or IMAGE_USD_PER_MILLION[DEFAULT_IMAGE_MODEL]
    tiers = spec.get("per_image_tiers") if isinstance(spec.get("per_image_tiers"), dict) else None
    if (spec.get("billing") == "per_image" or tiers) and tiers:
        tier = resolve_image_size_tier(size=size, quality=quality)
        usd = float(tiers.get(tier) or tiers.get("1k") or 0) * max(1, int(n or 1))
        cost = usd * USD_TO_CNY * PROFIT_RATE * float(discount or 1) * float(money_rate or 1)
        return round(cost, 6)
    usd = (
        int(text_tokens or 0) * float(spec.get("text_input") or 0)
        + int(image_input_tokens or 0) * float(spec.get("image_input") or 0)
        + int(output_tokens or 0) * float(spec.get("output") or 0)
    ) / TOKENS_PER_MILLION
    cost = usd * USD_TO_CNY * PROFIT_RATE * float(discount or 1) * float(money_rate or 1)
    return round(cost, 6)


def parse_image_mode(mode):
    """兼容旧格式：`{price}元gpt-可绘图:{model}`{quality}`；也支持直接 `model` / `model:quality`。"""
    raw = (mode or "").strip()
    if not raw:
        return DEFAULT_IMAGE_MODEL, "medium"
    if ":" in raw and "`" in raw:
        model, quality = raw.split(":")[-1].split("`")
        return resolve_image_model(model), (quality or "medium")
    if ":" in raw:
        model, quality = raw.split(":", 1)
        return resolve_image_model(model), (quality or "medium")
    if "`" in raw:
        model, quality = raw.split("`", 1)
        return resolve_image_model(model), (quality or "medium")
    return resolve_image_model(raw), "medium"


def parse_pending_mode(redis_key, user_id, kind):
    prefix = f"{user_id}_{kind}_"
    if redis_key.startswith(prefix):
        return redis_key[len(prefix):]
    return DEFAULT_CHAT_MODE


def build_gpt_mode_list():
    modes = []
    for mode in CHAT_MODE_ORDER:
        spec = CHAT_USD_PER_MILLION[mode]
        modes.append({
            "mode": mode,
            "label": spec["label"],
            "type": "chat",
            "input_cny_per_1m": round(sell_cny_per_million(spec["input"]), 4),
            "output_cny_per_1m": round(sell_cny_per_million(spec["output"]), 4),
        })
    for model in IMAGE_MODE_ORDER:
        usd = IMAGE_USD_PER_MILLION[model]
        tiers = usd.get("per_image_tiers") if isinstance(usd.get("per_image_tiers"), dict) else None
        if tiers:
            for quality, tier in (("low", "1k"), ("medium", "2k"), ("high", "4k")):
                price = image_list_cny(model, quality)
                modes.append({
                    "mode": f"{price}元gpt-可绘图:{model}`{quality}",
                    "label": f"{price}元 {usd['label']} {tier.upper()}",
                    "type": "image",
                    "billing": "per_image",
                    "model": model,
                    "quality": quality,
                    "size_tier": tier,
                    "usd_per_image": float(tiers.get(tier) or 0),
                    "per_image_tiers": dict(tiers),
                })
            continue
        qualities = IMAGE_COST_CNY.get(model) or {"medium": 1.0}
        for quality in qualities:
            price = image_list_cny(model, quality)
            modes.append({
                "mode": f"{price}元gpt-可绘图:{model}`{quality}",
                "label": f"{price}元 {usd['label']} {quality}",
                "type": "image",
                "billing": "token",
                "model": model,
                "quality": quality,
                "text_input_usd_per_1m": usd.get("text_input"),
                "image_input_usd_per_1m": usd.get("image_input"),
                "output_usd_per_1m": usd.get("output"),
            })
    return modes


def billing_public_config():
    return {
        "usdToCny": USD_TO_CNY,
        "profitRate": PROFIT_RATE,
        "unit": "cny",
        "tokenUnit": "per_1m_tokens",
        "imageBilling": "vendor",
        "imageModels": IMAGE_MODE_ORDER,
        "imagePerImageTiers": {
            model: spec.get("per_image_tiers")
            for model, spec in IMAGE_USD_PER_MILLION.items()
            if isinstance(spec.get("per_image_tiers"), dict)
        },
    }


def format_billing_payload(input_tokens, output_tokens, cost, balance):
    return {
        "input_tokens": int(input_tokens or 0),
        "output_tokens": int(output_tokens or 0),
        "cost": round(float(cost or 0), 6),
        "balance": round(float(balance or 0), 6),
    }


def format_billing_stream_chunk(input_tokens, output_tokens, cost, balance):
    return {
        "id": "billing-notice",
        "object": "chat.completion.chunk",
        "choices": [{
            "index": 0,
            "delta": {"content": ""},
            "finish_reason": None,
            "logprobs": None,
        }],
        "billing": format_billing_payload(input_tokens, output_tokens, cost, balance),
    }


def _cny_per_1k(usd_per_million):
    return sell_cny_per_million(usd_per_million) / 1000


MODEL_MAP_MONEY_DICT = {
    mode: {
        "input": _cny_per_1k(spec["input"]),
        "output": _cny_per_1k(spec["output"]),
    }
    for mode, spec in CHAT_USD_PER_MILLION.items()
}
for _model, _qualities in IMAGE_COST_CNY.items():
    MODEL_MAP_MONEY_DICT[_model] = {
        quality: charge_image_cny(_model, quality, discount=1, money_rate=1)
        for quality in _qualities
    }

GPT_MODE_LIST = build_gpt_mode_list()
MONEY_RATE = PROFIT_RATE
