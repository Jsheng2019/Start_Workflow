# -*- coding: utf-8 -*-
"""状态卡片风 HTML 邮件发送（notify-email composite action 的实现）。

全部输入来自环境变量（由 action.yml 注入）：
  INPUT_STATUS       job 结论：success / failure / cancelled（必填）
  INPUT_MAIL_TO      收件人，逗号分隔（必填）
  INPUT_MAIL_FROM    发件邮箱（必填）
  INPUT_SMTP_PASSWORD SMTP 授权码（必填）
  INPUT_SMTP_HOST / INPUT_SMTP_PORT / INPUT_SMTP_USER  可选
  INPUT_SUBJECT_PREFIX 主题前缀，缺省仓库名
  CTX_*              运行上下文：REPO / WORKFLOW / SHA / BRANCH / ACTOR /
                     EVENT / RUN_NUMBER / RUN_ID / RUN_URL / COMMIT_TIME

邮件为 multipart/alternative：纯文本 + 状态卡片风 HTML（text 客户端降级可读）。
退出码：0 成功或跳过；1 发送失败。
"""
import html
import os
import re
import smtplib
import ssl
import sys
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
from email.utils import formataddr, formatdate

DEFAULT_HOST = "smtp.163.com"
DEFAULT_PORT = "465"
BJ = timezone(timedelta(hours=8))

# 结论 → (emoji, 中文文案, 状态条底色, 徽章底色)
STATUS_MAP = {
    "success":   ("✅", "执行成功", "#1a7f37", "#dafbe1"),
    "failure":   ("❌", "执行失败", "#cf222e", "#ffebe9"),
    "cancelled": ("⛔", "已取消",   "#57606a", "#eaeef2"),
}
STATUS_FALLBACK = ("ℹ️", "状态未知", "#57606a", "#eaeef2")


def env(name, default=""):
    return (os.environ.get(name) or default).strip()


def split_addrs(raw):
    out = []
    for part in raw.replace(";", ",").replace(" ", ",").split(","):
        part = part.strip()
        if part and part not in out:
            out.append(part)
    return out


def esc(value):
    return html.escape(value or "", quote=True)


def conclusion_display(status):
    return STATUS_MAP.get(status, STATUS_FALLBACK)


def short_sha(sha):
    return sha[:8] if sha else ""


def text_body(data):
    emoji, text, _, _ = conclusion_display(data["status"])
    lines = [
        f"GitHub Actions 执行通知（{emoji} {text}）",
        "",
        f"Workflow : {data['workflow']}",
        f"结果     : {text}",
        f"仓库     : {data['repo']}",
        f"分支     : {data['branch'] or '/'}",
        f"Commit   : {short_sha(data['sha']) or '/'}",
        f"执行人   : {data['actor'] or '/'}",
        f"触发方式 : {data['event'] or '/'}",
        f"Run 编号 : #{data['run_number']}",
        "",
        f"详情链接 : {data['run_url']}",
        "",
        "（本邮件由 GitHub Actions 自动发送）",
    ]
    return "\n".join(lines)


def html_body(data):
    emoji, text, bar, pill_bg = conclusion_display(data["status"])
    row = 'cellpadding="0" cellspacing="0" style="font-size:14px;color:#24292f;"'
    field = 'style="padding:7px 0;color:#57606a;width:110px;vertical-align:top;"'
    value = 'style="padding:7px 0;font-weight:600;"'
    code = ('style="font-family:ui-monospace,SFMono-Regular,Consolas,monospace;'
            'background-color:#eff2f5;border-radius:6px;padding:2px 6px;font-weight:400;"')
    commit_time = ""
    if data["commit_time"]:
        commit_time = (f'<tr><td {field}>提交时间</td>'
                       f'<td {value}>{esc(data["commit_time"][:19].replace("T", " "))} UTC</td></tr>')
    return f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background-color:#f6f8fa;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f6f8fa;padding:24px 0;">
<tr><td align="center">
<table role="presentation" width="640" cellpadding="0" cellspacing="0"
       style="background-color:#ffffff;border-radius:12px;overflow:hidden;
              border:1px solid #d0d7de;font-family:-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;">
  <tr><td style="background-color:{bar};padding:18px 24px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
      <td style="color:#ffffff;font-size:19px;font-weight:600;">{emoji} {text}</td>
      <td align="right" style="color:rgba(255,255,255,0.85);font-size:13px;">
        {esc(data['workflow'])} · #{esc(data['run_number'])}</td>
    </tr></table>
  </td></tr>
  <tr><td style="padding:20px 24px 8px 24px;">
    <table role="presentation" width="100%" {row}>
      <tr><td {field}>仓库</td><td {value}>{esc(data['repo'])}</td></tr>
      <tr><td {field}>Workflow</td><td {value}>{esc(data['workflow'])}</td></tr>
      <tr><td {field}>分支</td><td {value}>
        <span style="background-color:{pill_bg};border-radius:10px;padding:2px 10px;font-size:12px;">{esc(data['branch'] or '/')}</span>
      </td></tr>
      <tr><td {field}>Commit</td><td {value}><code {code}>{esc(short_sha(data['sha'])) or '/'}</code></td></tr>
      <tr><td {field}>执行人</td><td {value}>{esc(data['actor'] or '/')}</td></tr>
      <tr><td {field}>触发方式</td><td {value}>{esc(data['event'] or '/')}</td></tr>
      <tr><td {field}>Run 编号</td><td {value}>#{esc(data['run_number'])}</td></tr>
      {commit_time}
    </table>
    <table role="presentation" cellpadding="0" cellspacing="0" style="margin-top:18px;"><tr>
      <td align="center" bgcolor="#0969da" style="border-radius:6px;">
        <a href="{esc(data['run_url'])}"
           style="display:inline-block;padding:10px 22px;color:#ffffff;text-decoration:none;
                  font-size:14px;font-weight:600;">查看运行详情</a>
      </td>
    </tr></table>
  </td></tr>
  <tr><td style="background-color:#f6f8fa;padding:12px 24px;color:#8b949e;font-size:12px;">
    本邮件由 GitHub Actions 自动发送 · {esc(datetime.now(BJ).strftime("%Y-%m-%d %H:%M:%S"))} 北京时间
  </td></tr>
</table>
</td></tr></table>
</body></html>"""


def main():
    mail_to = split_addrs(env("INPUT_MAIL_TO"))
    mail_from = env("INPUT_MAIL_FROM")
    password = env("INPUT_SMTP_PASSWORD")
    host = env("INPUT_SMTP_HOST", DEFAULT_HOST)
    port = env("INPUT_SMTP_PORT", DEFAULT_PORT)
    user = env("INPUT_SMTP_USER") or mail_from
    cc = split_addrs(env("INPUT_MAIL_CC", ""))

    missing = [n for n, v in (("INPUT_MAIL_FROM", mail_from),
                              ("INPUT_MAIL_TO", mail_to),
                              ("INPUT_SMTP_PASSWORD", password)) if not v]
    if missing:
        print("MAIL-SKIP: 未传入 %s，本次不发送" % ", ".join(missing))
        return 0

    data = {
        "status": env("INPUT_STATUS"),
        "repo": env("CTX_REPO"),
        "workflow": env("CTX_WORKFLOW"),
        "sha": env("CTX_SHA"),
        "branch": env("CTX_BRANCH"),
        "actor": env("CTX_ACTOR"),
        "event": env("CTX_EVENT"),
        "run_number": env("CTX_RUN_NUMBER"),
        "run_id": env("CTX_RUN_ID"),
        "run_url": env("CTX_RUN_URL"),
        "commit_time": env("CTX_COMMIT_TIME"),
    }
    emoji, text = conclusion_display(data["status"])
    prefix = env("INPUT_SUBJECT_PREFIX") or data["repo"]
    subject = f"[{prefix}] {emoji} {text} {data['workflow']} #{data['run_number']}"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((env("INPUT_MAIL_FROM_NAME", "GitHub Actions 通知"), mail_from))
    msg["To"] = ", ".join(mail_to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(text_body(data))
    msg.add_alternative(html_body(data), subtype="html")

    rcpts = mail_to + cc
    port_num = int(port)
    try:
        context = ssl.create_default_context()
        if port_num == 465:
            server = smtplib.SMTP_SSL(host, port_num, timeout=60, context=context)
        else:
            server = smtplib.SMTP(host, port_num, timeout=60)
        with server:
            if port_num != 465:
                server.starttls(context=context)
            server.login(user, password)
            server.send_message(msg, from_addr=mail_from, to_addrs=rcpts)
    except Exception as exc:
        print("MAIL-FAILED: %s: %s" % (type(exc).__name__, exc))
        return 1

    print("MAIL-OK: %s%s %s #%s，收件人 %d 个"
          % (emoji, text, data["workflow"], data["run_number"], len(rcpts)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
