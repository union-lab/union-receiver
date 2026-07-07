from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from fastapi import BackgroundTasks

from .config import TaskSettings, load_settings

logger = logging.getLogger("union-davinci-task")


def _setup_logging() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def _load_env_file(path: Path, *, override: bool = False) -> None:
    if not path.exists():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(path, override=override)
        return
    except Exception:
        pass

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if override or key not in os.environ:
            os.environ[key] = value


def _database_url_with_name(dsn: str, database_name: str) -> str:
    if not database_name:
        return dsn
    parsed = urlsplit(dsn)
    if not parsed.scheme or not parsed.netloc:
        return dsn
    return urlunsplit((parsed.scheme, parsed.netloc, f"/{database_name}", parsed.query, parsed.fragment))


def _force_database_name(database_name: str) -> None:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn or not database_name:
        return
    updated = _database_url_with_name(dsn, database_name)
    if updated != dsn:
        os.environ["DATABASE_URL"] = updated
        logger.info("达芬奇工单 worker 数据库已切换到：%s", database_name)


def bootstrap_agent(settings: TaskSettings):
    """导入 union-agent，让 worker 直接复用原达芬奇做图逻辑。"""
    if not settings.agent_path.exists():
        raise RuntimeError(f"union-agent 路径不存在：{settings.agent_path}")
    if str(settings.agent_path) not in sys.path:
        sys.path.insert(0, str(settings.agent_path))

    os.environ.setdefault("UNION_AGENT_ENV_FILE", settings.agent_env_file)
    os.environ.setdefault("UNION_KNOWLEDGEBASE_PATH", str(settings.knowledgebase_path))
    vendored_core_path = settings.agent_path / "davinci_core_vendored"
    knowledgebase_core_path = (
        settings.knowledgebase_path
        / "重点项目"
        / "AI部门"
        / "AI美工师·达芬奇"
        / "davinci_core"
    )
    if (vendored_core_path / "lib").exists():
        os.environ.setdefault("DAVINCI_CORE_PATH", str(vendored_core_path))
    elif knowledgebase_core_path.exists():
        os.environ.setdefault("DAVINCI_CORE_PATH", str(knowledgebase_core_path))
    _load_env_file(settings.agent_path / settings.agent_env_file)
    _load_env_file(settings.agent_path / ".env", override=False)
    _force_database_name(settings.database_name)

    from app.api.routes import davinci
    from app.db.davinci_pool import close_davinci_pool, get_davinci_pool

    return davinci, get_davinci_pool, close_davinci_pool


def _json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip() or default


def _extract_platform(config: dict[str, Any]) -> str:
    platform = _as_dict(config.get("platform"))
    return _text(platform.get("id") or platform.get("value") or config.get("platform"), "tmall")


def _extract_image_type(config: dict[str, Any]) -> str:
    image_type = _as_dict(config.get("image_type"))
    return _text(
        image_type.get("runtime_image_type") or image_type.get("id") or config.get("image_type"),
        "main",
    )


def _extract_recipe(config: dict[str, Any]) -> str:
    recipe = _as_dict(config.get("recipe"))
    return _text(recipe.get("code") or recipe.get("id") or config.get("recipe"), "R02")


def _extract_business_tier(config: dict[str, Any]) -> str:
    tier = _as_dict(config.get("business_tier"))
    return _text(tier.get("runtime_tier") or tier.get("id") or config.get("business_tier"), "marketing")


def _extract_pipeline(config: dict[str, Any]) -> str | None:
    tier = _as_dict(config.get("business_tier"))
    pipeline = tier.get("runtime_pipeline") or config.get("runtime_pipeline") or config.get("pipeline")
    return _text(pipeline) or None


def _extract_subject_focus(config: dict[str, Any]) -> str | None:
    subject = config.get("subject_focus") or config.get("subject")
    return _text(subject) or None


def _extract_store(config: dict[str, Any]) -> dict[str, Any]:
    return _as_dict(config.get("store"))


def _extract_product(config: dict[str, Any]) -> dict[str, Any]:
    return _as_dict(config.get("product"))


def _kingdee_code(config: dict[str, Any]) -> str:
    product = _extract_product(config)
    return _text(
        product.get("kingdee_code")
        or product.get("code")
        or product.get("sku")
        or config.get("kingdee_code")
    )


def _selling_points(config: dict[str, Any]) -> list[str]:
    raw_text = _text(config.get("selling_text"))
    if raw_text:
        lines = [line.strip(" -\t") for line in raw_text.splitlines()]
        points = [line for line in lines if line]
        if points:
            return points

    upgrade = _as_dict(config.get("selling_upgrade"))
    layered = _as_dict(upgrade.get("layered_copy"))
    headline = _text(layered.get("headline"))
    chips = [_text(item) for item in _as_list(layered.get("chips"))]
    points = [item for item in [headline, *chips] if item]
    return points or ["按已配置卖点出图"]


def _compile_request_payload(config: dict[str, Any]) -> dict[str, Any]:
    kingdee_code = _kingdee_code(config)
    if not kingdee_code:
        raise ValueError("工单配置缺少商品 kingdee_code")
    selling_upgrade = _as_dict(config.get("selling_upgrade"))
    if not selling_upgrade:
        raise ValueError("工单配置缺少 selling_upgrade，无法复用 L3 编译链路")

    store = _extract_store(config)
    return {
        "kingdee_code": kingdee_code,
        "business_tier": _extract_business_tier(config),
        "recipe": _extract_recipe(config),
        "pipeline": _extract_pipeline(config),
        "platform": _extract_platform(config),
        "image_type": _extract_image_type(config),
        "store_id": _text(store.get("id") or store.get("store_id") or store.get("shop_no")) or None,
        "shop_no": _text(store.get("shop_no")) or None,
        "shop_name": _text(store.get("shop_name") or store.get("name")) or None,
        "biz_unit": _text(store.get("biz_unit")) or None,
        "subject_focus": _extract_subject_focus(config),
        "combo_generation_mode": _text(config.get("combo_generation_mode"), "suite"),
        "combo_member_codes": _as_list(config.get("combo_member_codes")),
        "reference_manifest": _as_list(config.get("reference_manifest")),
        "product_evidence_refs": _as_list(config.get("product_evidence_refs")),
        "selling_upgrade": selling_upgrade,
    }


def _gate_passed(resp: Any) -> bool:
    gates = getattr(resp, "gates", None) or {}
    if isinstance(gates, dict) and gates.get("all_passed") is True:
        return True
    snapshot = getattr(resp, "gate_snapshot", None) or {}
    return isinstance(snapshot, dict) and snapshot.get("all_passed") is True


def _blocking_reasons(resp: Any) -> list[str]:
    gates = getattr(resp, "gates", None) or {}
    reasons = []
    if isinstance(gates, dict):
        reasons = _as_list(gates.get("blocking_reasons"))
    if not reasons:
        ratio = getattr(resp, "ratio_check", None)
        reasons = _as_list(getattr(ratio, "fail_reasons", None))
    return [_text(item) for item in reasons if _text(item)]


def _only_ratio_blocked(reasons: list[str]) -> bool:
    return bool(reasons) and all(
        item.startswith("zone2_") or item.startswith("zone3_plus_zone4_")
        for item in reasons
    )


async def _compile_with_existing_logic(davinci: Any, config: dict[str, Any]) -> Any:
    payload = _compile_request_payload(config)
    resp = await davinci.compile_plan(davinci.CompilePlanRequest(**payload))
    if _gate_passed(resp):
        return resp

    reflow_payload = dict(payload)
    reflow_payload["reflow_action"] = "auto"
    resp = await davinci.compile_plan_reflow(davinci.CompilePlanReflowRequest(**reflow_payload))
    if _gate_passed(resp):
        return resp

    reasons = _blocking_reasons(resp)
    if _only_ratio_blocked(reasons):
        override_payload = dict(payload)
        override_payload.update(
            {
                "override_by": "union-davinci-task",
                "override_reason": "工单队列自动放行字数占比 Gate，保留原失败原因用于追溯",
                "original_fail_reasons": reasons,
            }
        )
        return await davinci.compile_plan_override(
            davinci.CompilePlanOverrideRequest(**override_payload)
        )

    raise RuntimeError(f"编译 Gate 未通过：{'；'.join(reasons) or '未知原因'}")


async def _run_background_tasks(background_tasks: BackgroundTasks) -> None:
    for task in background_tasks.tasks:
        result = task()
        if inspect.isawaitable(result):
            await result


def _build_generate_request(davinci: Any, config: dict[str, Any], compile_resp: Any) -> Any:
    store = _extract_store(config)
    product_evidence_refs = _as_list(config.get("product_evidence_refs"))
    reference_manifest = list(getattr(compile_resp, "reference_manifest", None) or [])
    if not reference_manifest:
        reference_manifest = _as_list(config.get("reference_manifest"))
    evidence_policy = _text(config.get("evidence_policy"), "collector_or_upload")
    preflight = _as_dict(config.get("preflight"))
    primary_product = _as_dict(preflight.get("primary_product"))
    has_system_product_evidence = bool(
        primary_product.get("has_image")
        and (primary_product.get("evidence_source") or primary_product.get("evidence_url"))
    )
    if evidence_policy == "upload_only" and not product_evidence_refs and has_system_product_evidence:
        evidence_policy = "default"
    return davinci.GenerateRequest(
        kingdee_code=_kingdee_code(config),
        recipe_code=_extract_recipe(config),
        platform=_extract_platform(config),
        image_type=_extract_image_type(config),
        business_tier=_extract_business_tier(config),
        provider="gemini",
        selling_points=_selling_points(config),
        compile_id=compile_resp.compile_id,
        config_hash=compile_resp.config_hash,
        gate_snapshot=compile_resp.gate_snapshot,
        model_call_spec=compile_resp.model_call_spec,
        reference_manifest=reference_manifest,
        product_evidence_refs=product_evidence_refs,
        evidence_policy=evidence_policy,
        store_id=_text(store.get("id") or store.get("store_id") or store.get("shop_no")) or None,
        shop_no=_text(store.get("shop_no")) or None,
        shop_name=_text(store.get("shop_name") or store.get("name")) or None,
        biz_unit=_text(store.get("biz_unit")) or None,
        combo_member_codes=_as_list(config.get("combo_member_codes")),
        combo_generation_mode=_text(config.get("combo_generation_mode"), "suite"),
        subject_focus=_extract_subject_focus(config),
        task_level="L3",
    )


def _collect_urls(status: dict[str, Any]) -> list[str]:
    output = _as_dict(status.get("output"))
    urls: list[str] = []

    def add(value: Any) -> None:
        text = _text(value)
        if not text:
            return
        if text.startswith("http://") or text.startswith("https://") or text.startswith("/api/"):
            if text not in urls:
                urls.append(text)

    for key in ("image_url", "thumb_url", "url"):
        add(output.get(key))

    output_id = _text(output.get("id") or output.get("output_id"))
    if output_id and not urls:
        add(f"/api/davinci/outputs/{output_id}/image")
    return urls


async def _generate_with_existing_logic(davinci: Any, config: dict[str, Any], compile_resp: Any) -> list[str]:
    req = _build_generate_request(davinci, config, compile_resp)
    background_tasks = BackgroundTasks()
    created = await davinci.generate(req, background_tasks)
    task_id = created["task_id"]

    await _run_background_tasks(background_tasks)
    status = await davinci.task_status(task_id)
    if status.get("status") != "completed":
        raise RuntimeError(status.get("error") or f"出图任务未完成：{status.get('status')}")

    urls = _collect_urls(status)
    if not urls:
        raise RuntimeError("出图已完成，但任务状态中没有可写回的图片 URL")
    return urls


def _has_cn_image_provider(settings: Any) -> bool:
    return bool(
        getattr(settings, "volcengine_ark_api_key", None)
        or getattr(settings, "aliyun_bailian_api_key", None)
        or getattr(settings, "zhipu_api_key", None)
    )


def _should_try_cn_fallback(error: Exception) -> bool:
    message = str(error)
    # 只兜底模型供应商链路错误；配置/素材/编译类错误不应该换模型重试。
    blocked_markers = (
        "编译 Gate",
        "商品不存在",
        "缺少有效 compile_id",
        "config_hash",
        "产品证据图",
        "product_image_missing",
        "business_compliance",
    )
    if any(marker in message for marker in blocked_markers):
        return False
    provider_markers = (
        "AI 出图失败",
        "wolfai",
        "请求异常",
        "ConnectError",
        "Timeout",
        "超时",
        "429",
        "未配置 wolfai",
        "HTTP 5",
    )
    return any(marker in message for marker in provider_markers)


async def _generate_with_foreign_then_cn_fallback(
    davinci: Any,
    config: dict[str, Any],
    compile_resp: Any,
) -> list[str]:
    """默认走国外模型；国外供应商失败时，临时切国内网关兜底一次。"""
    from app.config import settings as agent_settings

    original_cn_enabled = bool(getattr(agent_settings, "davinci_cn_image_enabled", False))
    try:
        return await _generate_with_existing_logic(davinci, config, compile_resp)
    except Exception as foreign_error:
        if original_cn_enabled:
            raise
        if not _should_try_cn_fallback(foreign_error):
            raise
        if not _has_cn_image_provider(agent_settings):
            logger.warning("国外模型失败，但国产生图 key 未配置，无法兜底: %s", foreign_error)
            raise

        logger.warning("国外模型失败，自动切换国产生图网关重试一次: %s", foreign_error)
        agent_settings.davinci_cn_image_enabled = True
        try:
            return await _generate_with_existing_logic(davinci, config, compile_resp)
        except Exception as cn_error:
            raise RuntimeError(
                f"国外模型失败且国内兜底也失败；国外错误：{foreign_error}；国内错误：{cn_error}"
            ) from cn_error
        finally:
            agent_settings.davinci_cn_image_enabled = original_cn_enabled


async def claim_orders(davinci: Any, get_pool: Any, limit: int) -> list[dict[str, Any]]:
    await davinci._ensure_task_table()
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            WITH picked AS (
                SELECT id
                FROM union_davinci_draworder
                WHERE status = '待做图'
                  AND COALESCE(config->>'cancelled', 'false') <> 'true'
                  AND (
                    CASE
                      WHEN COALESCE(config->>'attempt_count', '') ~ '^[0-9]+$'
                        THEN (config->>'attempt_count')::int
                      ELSE 0
                    END
                  ) < 3
                ORDER BY created_at ASC
                LIMIT $1
                FOR UPDATE SKIP LOCKED
            )
            UPDATE union_davinci_draworder d
            SET status = '做图中',
                started_at = COALESCE(d.started_at, now()),
                updated_at = now()
            FROM picked
            WHERE d.id = picked.id
            RETURNING d.id, d.draworder_id, d.operator_account_name, d.status,
                      d.config, d.output_urls, d.created_at
            """,
            limit,
        )
    return [dict(row) for row in rows]


async def mark_completed(get_pool: Any, order_id: int, urls: list[str]) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE union_davinci_draworder
            SET status = '已完成',
                output_urls = $2::jsonb,
                config = config - 'last_error' - 'last_failed_at',
                completed_at = now(),
                updated_at = now()
            WHERE id = $1
            """,
            order_id,
            _json_dumps(urls),
        )


async def mark_failed_for_retry(get_pool: Any, order: dict[str, Any], error: Exception) -> None:
    config = _as_dict(order.get("config")).copy()
    config["last_error"] = str(error)
    config["last_failed_at"] = datetime.now(timezone.utc).isoformat()
    config["attempt_count"] = int(config.get("attempt_count") or 0) + 1

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE union_davinci_draworder
            SET status = '待做图',
                config = $2::jsonb,
                updated_at = now()
            WHERE id = $1
            """,
            int(order["id"]),
            _json_dumps(config),
        )


async def process_order(davinci: Any, get_pool: Any, order: dict[str, Any]) -> None:
    order_id = int(order["id"])
    draworder_id = str(order["draworder_id"])
    logger.info("开始处理工单 id=%s draworder_id=%s", order_id, draworder_id)

    config = _as_dict(order.get("config"))
    try:
        compile_resp = await _compile_with_existing_logic(davinci, config)
        urls = await _generate_with_foreign_then_cn_fallback(davinci, config, compile_resp)
        await mark_completed(get_pool, order_id, urls)
        logger.info("工单完成 id=%s urls=%s", order_id, urls)
    except Exception as exc:
        logger.exception("工单失败，退回待做图 id=%s: %s", order_id, exc)
        await mark_failed_for_retry(get_pool, order, exc)


async def run_once(settings: TaskSettings) -> int:
    davinci, get_pool, close_pool = bootstrap_agent(settings)
    try:
        orders = await claim_orders(davinci, get_pool, settings.batch_size)
        if not orders:
            logger.info("本轮没有待做图工单")
            return 0
        for order in orders:
            await process_order(davinci, get_pool, order)
        return len(orders)
    finally:
        await close_pool()


async def run_forever(settings: TaskSettings) -> None:
    davinci, get_pool, close_pool = bootstrap_agent(settings)
    try:
        logger.info(
            "达芬奇工单 worker 已启动 interval=%ss batch=%s",
            settings.interval_seconds,
            settings.batch_size,
        )
        while True:
            try:
                orders = await claim_orders(davinci, get_pool, settings.batch_size)
                if not orders:
                    logger.info("本轮没有待做图工单")
                for order in orders:
                    await process_order(davinci, get_pool, order)
            except Exception:
                logger.exception("工单轮询异常，等待下一轮")
            await asyncio.sleep(settings.interval_seconds)
    finally:
        await close_pool()


async def async_main(args: argparse.Namespace) -> None:
    settings = load_settings()
    if args.interval:
        settings = TaskSettings(
            agent_path=settings.agent_path,
            knowledgebase_path=settings.knowledgebase_path,
            interval_seconds=max(10, args.interval),
            batch_size=settings.batch_size,
            agent_env_file=settings.agent_env_file,
            database_name=settings.database_name,
        )
    if args.batch_size:
        settings = TaskSettings(
            agent_path=settings.agent_path,
            knowledgebase_path=settings.knowledgebase_path,
            interval_seconds=settings.interval_seconds,
            batch_size=max(1, args.batch_size),
            agent_env_file=settings.agent_env_file,
            database_name=settings.database_name,
        )

    if args.once:
        await run_once(settings)
    else:
        await run_forever(settings)


def main() -> None:
    _setup_logging()
    parser = argparse.ArgumentParser(description="达芬奇做图工单队列 worker")
    parser.add_argument("--once", action="store_true", help="只执行一轮，不进入常驻轮询")
    parser.add_argument("--interval", type=int, default=None, help="轮询间隔秒数，默认读取环境变量")
    parser.add_argument("--batch-size", type=int, default=None, help="每轮最多认领工单数")
    args = parser.parse_args()
    asyncio.run(async_main(args))
