"""Shared registration workflow used by both GUI and CLI adapters."""
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Tuple


@dataclass
class RegistrationCallbacks:
    log: Callable[[str], None]
    cancelled: Callable[[], bool]


@dataclass
class RegistrationOperations:
    start_browser: Callable[[], None]
    restart_browser: Callable[[], None]
    browser_missing: Callable[[], bool]
    open_signup_page: Callable[[], None]
    fill_email_and_submit: Callable[[], Tuple[str, str]]
    save_mail_credential: Callable[[str, str], bool]
    fill_code_and_submit: Callable[[str, str], str]
    fill_profile_and_submit: Callable[[], Dict[str, Any]]
    wait_for_sso_cookie: Callable[[], str]
    enable_nsfw: Callable[[str], Tuple[bool, str]]
    persist_account_line: Callable[[str, str, str], None]
    queue_unsaved_result: Callable[[Dict[str, Any], str], bool]
    add_tokens: Callable[[str, str], Dict[str, Dict[str, Any]]]
    export_cpa: Callable[[str, str, str], Dict[str, Any]]
    cleanup: Callable[[str], None]
    sleep: Callable[[float], None]
    cancelled_exception: type
    retry_exception: type


@dataclass
class RegistrationResult:
    ok: bool
    email: str = ""
    password: str = ""
    sso: str = ""
    profile: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    retryable: bool = False


@dataclass
class OutputResult:
    registered: bool
    saved: bool
    pending_saved: bool = False
    save_error: str = ""
    pools: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    cpa: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BatchResult:
    success_count: int = 0
    fail_count: int = 0
    processed_count: int = 0
    cancelled: bool = False
    results: list = field(default_factory=list)


def register_one_account(callbacks, ops, enable_nsfw=True, max_mail_retry=3):
    email = ""
    dev_token = ""
    code = ""
    mail_ok = False
    for mail_try in range(1, max_mail_retry + 1):
        if callbacks.cancelled():
            raise ops.cancelled_exception()
        callbacks.log(f"[*] 1. 打开注册页 (尝试 {mail_try}/{max_mail_retry})")
        ops.open_signup_page()
        callbacks.log("[*] 2. 创建邮箱并提交")
        email, dev_token = ops.fill_email_and_submit()
        callbacks.log(f"[*] 邮箱: {email}")
        callbacks.log(f"[Debug] 邮箱credential(jwt): {dev_token}")
        if not ops.save_mail_credential(email, dev_token):
            callbacks.log("[!] 邮箱凭据保存失败，注册继续，但已明确记录该异常")
        callbacks.log("[*] 3. 拉取验证码")
        try:
            code = ops.fill_code_and_submit(email, dev_token)
            mail_ok = True
            break
        except Exception as exc:
            message = str(exc)
            if ("未收到验证码" in message or "验证码" in message) and mail_try < max_mail_retry:
                callbacks.log(f"[!] 本邮箱未取到验证码，自动更换新邮箱重试: {message}")
                ops.restart_browser()
                ops.sleep(1)
                continue
            raise
    if not mail_ok:
        raise RuntimeError("验证码阶段失败，已达到最大重试次数")
    callbacks.log(f"[*] 验证码: {code}")
    callbacks.log("[*] 4. 填写资料")
    profile = ops.fill_profile_and_submit()
    callbacks.log(f"[*] 资料已填: {profile.get('given_name')} {profile.get('family_name')}")
    callbacks.log("[*] 5. 等待 sso cookie")
    sso = ops.wait_for_sso_cookie()
    if enable_nsfw:
        callbacks.log("[*] 6. 开启 NSFW")
        nsfw_ok, nsfw_msg = ops.enable_nsfw(sso)
        if nsfw_ok:
            callbacks.log(f"[+] NSFW 开启成功: {nsfw_msg}")
        else:
            callbacks.log(f"[!] NSFW 未开启，继续保存账号: {nsfw_msg}")
    return RegistrationResult(
        ok=True,
        email=email,
        password=str(profile.get("password") or ""),
        sso=sso,
        profile=profile,
    )


def persist_account_result(result, callbacks, ops):
    try:
        ops.persist_account_line(result.email, result.password, result.sso)
        saved = True
        save_error = ""
        pending_saved = False
    except Exception as exc:
        saved = False
        save_error = str(exc)
        pending_saved = ops.queue_unsaved_result(
            {
                "email": result.email,
                "password": result.password,
                "sso": result.sso,
                "profile": result.profile,
            },
            save_error,
        )
        callbacks.log(f"[!] 账号已注册但主结果文件保存失败: {save_error}")
        if pending_saved:
            callbacks.log("[!] 未保存账号已写入 pending 队列，等待人工重试")
        else:
            callbacks.log("[!] pending 队列也写入失败，请立即复制当前账号信息")
    pools = ops.add_tokens(result.sso, result.email)
    for name, state in pools.items():
        if state.get("enabled") and not state.get("ok"):
            callbacks.log(f"[!] grok2api {name} 入池失败: {state.get('error')}")
    cpa = ops.export_cpa(result.email, result.password, result.sso)
    return OutputResult(
        registered=True,
        saved=saved,
        pending_saved=pending_saved,
        save_error=save_error,
        pools=pools,
        cpa=cpa,
    )


def run_batch(count, callbacks, observer, ops, enable_nsfw=True, cleanup_interval=5,
              max_slot_retry=3, max_mail_retry=3):
    result = BatchResult()
    retry_count_for_slot = 0
    ops.start_browser()
    callbacks.log("[*] 浏览器已启动")
    try:
        while result.processed_count < count:
            if callbacks.cancelled():
                result.cancelled = True
                break
            callbacks.log(f"--- 开始第 {result.processed_count + 1}/{count} 个账号 ---")
            account = None
            output = None
            try:
                account = register_one_account(
                    callbacks, ops, enable_nsfw=enable_nsfw,
                    max_mail_retry=max_mail_retry,
                )
                output = persist_account_result(account, callbacks, ops)
                result.results.append({"registration": account, "output": output})
                retry_count_for_slot = 0
                result.processed_count += 1
                if output.saved:
                    result.success_count += 1
                    callbacks.log(f"[+] 注册并保存成功: {account.email}")
                else:
                    result.fail_count += 1
                    callbacks.log(f"[-] 注册成功但持久化未完成: {account.email}")
                if result.success_count > 0 and result.success_count % cleanup_interval == 0 and result.processed_count < count:
                    ops.cleanup(f"已成功 {result.success_count} 个账号，执行定期清理")
            except ops.cancelled_exception:
                result.cancelled = True
                callbacks.log("[!] 注册被停止")
                break
            except ops.retry_exception as exc:
                retry_count_for_slot += 1
                if retry_count_for_slot <= max_slot_retry:
                    callbacks.log(f"[!] 当前账号流程卡住，重试第 {retry_count_for_slot}/{max_slot_retry} 次: {exc}")
                else:
                    result.fail_count += 1
                    result.processed_count += 1
                    retry_count_for_slot = 0
                    callbacks.log(f"[-] 当前账号已达到最大重试次数，跳过: {exc}")
            except Exception as exc:
                result.fail_count += 1
                result.processed_count += 1
                retry_count_for_slot = 0
                callbacks.log(f"[-] 注册失败: {exc}")
            finally:
                observer(result, account, output)
                if callbacks.cancelled():
                    result.cancelled = True
                    break
                if ops.browser_missing():
                    ops.start_browser()
                else:
                    ops.restart_browser()
                ops.sleep(1)
    finally:
        ops.cleanup("任务结束")
    return result
