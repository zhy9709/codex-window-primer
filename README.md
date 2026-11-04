# codex-window-primer

让闲置的 Codex 五小时滚动额度窗口提前开始，等你真正要用时少等一会儿。

[English](README.en.md)

## 它解决什么问题

如果一个新额度窗口一直没有使用，它会等到你第一次发起请求时才开始计时。这个小工具定时检查本机 Codex 的主额度窗口：只有在用量仍为 0% 时，才发送一次极小请求把窗口启动起来。请求结束后还会重新读取官方额度状态；只有主窗口用量确实高于 0%，才算点火成功。

它**不会增加额度、绕过套餐限制或让请求免费**，只是把正常窗口提前启动。工具使用 Codex 的实验性 app-server 接口，未来 Codex 升级后可能需要同步适配。

## 安装

需要 Python 3.10+、已安装 Codex CLI，并完成 `codex login`。

```bash
git clone https://github.com/zhy9709/codex-window-primer.git
cd codex-window-primer
python3 -m venv .venv
.venv/bin/pip install .
.venv/bin/codex-window-primer status
```

安装推荐的每小时检查任务：

```bash
.venv/bin/codex-window-primer install-timer --interval 1h
```

默认 `1h` 比较均衡：新窗口出现后最多晚 59 分钟启动，每天只做 24 次轻量查询。也可以改成 `30m` 或 `15m`，最低允许 5 分钟。

想在服务端报告的重置时间后更快点火，可开启精准补跑（固定轮询仍作为兜底）：

```bash
codex-window-primer install-timer --interval 1h --reset-follow-up --reset-delay 30
```

它会根据每次查询得到的 `resetsAt`，幂等更新一个单次 systemd 定时器，在重置后 30 秒补跑。过期、超过未来 7 天或缺失的时间不会预约。

## 常用命令

```bash
# 查看当前额度状态
codex-window-primer status

# 只演练，不真正发送点火请求
codex-window-primer check --dry-run

# 立即检查一次
codex-window-primer check

# 指定点火模型；不指定时沿用 Codex CLI 当前默认模型
codex-window-primer check --model gpt-5.1-codex-mini

# 改成每 30 分钟检查
codex-window-primer install-timer --interval 30m
```

如果不用 systemd，也可以加入 cron：

```cron
17 * * * * /path/to/codex-window-primer/.venv/bin/codex-window-primer check
```

## 安全说明

- OAuth 凭据仍保存在 Codex 自己的认证文件中，本工具不会复制或记录它。
- 状态默认保存在 `~/.local/state/codex-window-primer/state.json`。
- 点火后会有限次重查额度；如果用量一直为 0% 或查询持续失败，命令会以非零状态退出且不更新状态，下一次定时任务仍可重试。
- `check` 的 JSON 会保留 `before`、验证后的 `after`、`resetsAt` 和 `modelRequested`，方便直接判断是否真点着；演练和未点火不会伪造 `after`。
- 只有验证成功后才记录点火状态；之后四小时内禁止重复请求，避免服务端重置时间轻微漂移造成重复点火。
- 目前适合 Linux、服务器和树莓派；Android Termux 只能算实验用法，iPhone 不适合长期后台运行。

## 开发测试

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## License

MIT
