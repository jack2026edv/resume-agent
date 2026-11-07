# 应届生简历制作 Agent

一个用 Streamlit（Python）做的网页应用：AI 通过多轮对话帮你收集经历、
主动追问细节（做了什么 / 怎么做的 / 有什么数据结果），
再根据目标岗位的 JD 生成一份"动作+方法+数据"风格的针对性简历，
支持多轮修改，最终可导出 PDF。

---

## 一、项目文件结构

```
resume-agent/
├── app.py              ← 主程序：网页界面 + 对话流程（唯一需要"运行"的文件）
├── prompts.py          ← 所有 AI 提示词集中管理（想改 AI 行为只动这里）
├── llm_client.py       ← 负责调用大模型 API 的小模块
├── pdf_export.py       ← 把 Markdown 简历导出成 PDF
├── requirements.txt    ← 依赖清单（项目需要安装哪些第三方库）
├── .env.example        ← 环境变量模板（告诉你需要配置哪些密钥）
├── .streamlit/         ← Streamlit 配置和云端 Secrets 示例
├── session_store.py    ← 每个浏览器独立的会话存档
├── resume_render.py    ← 把 JSON 简历转为 Markdown 预览
├── .gitignore          ← 告诉 Git 哪些文件不要上传（保护密钥）
└── README.md           ← 本说明书
```

每个文件是干什么的：

| 文件 | 通俗解释 |
|---|---|
| `app.py` | 整个应用的"前台+后台"，网页长什么样、对话怎么进行，都在这里 |
| `prompts.py` | 发给 AI 的"工作说明书"：怎么追问、怎么写简历，全在这里，方便随时调整 |
| `llm_client.py` | "电话机"：负责把消息发给大模型、把回复拿回来 |
| `pdf_export.py` | "打印机"：把简历变成 PDF 文件 |
| `requirements.txt` | "购物清单"：列出项目需要的所有第三方库，一键安装 |
| `.env` | "保险柜"：存你的 API 密钥（由 .env.example 复制而来，不上传网络） |

---

## 二、环境搭建（Windows 傻瓜教程）

### 第 1 步：安装 Python（如果已经装过，跳到第 2 步）

1. 打开 https://www.python.org/downloads/ ，点黄色大按钮下载 Windows 安装包
   （官网下载慢的话，可以用华为镜像：https://mirrors.huaweicloud.com/python/ ）
2. 双击安装包。**第一个界面最下方有一个勾选项 `Add python.exe to PATH`，
   一定要勾上！** 这是新手最常踩的坑，不勾的话后面命令会找不到 Python。
3. 一路 Next 装完。
4. 验证是否成功：按 `Win + R`，输入 `powershell` 回车，在黑窗口里输入：

   ```powershell
   python --version
   ```

   显示 `Python 3.x.x` 就成功了。如果提示"不是内部或外部命令"，
   说明刚才没勾 PATH，卸载重装一遍并记得勾选。

### 第 2 步：安装 VS Code（可选但推荐）

看代码、改提示词会比记事本舒服很多。
打开 https://code.visualstudio.com/ 下载安装即可，装完可以在
扩展商店里搜 "Python" 装一个官方扩展（不装也能用）。

### 第 3 步：打开终端，进入项目文件夹

在文件资源管理器里打开项目文件夹，然后在地址栏输入 `powershell` 回车，
就会弹出一个已经"站"在这个文件夹里的终端。

### 第 4 步：创建虚拟环境

什么是虚拟环境：给这个项目单独准备一间"工具房"，里面装的库不影响
电脑上的其他 Python 项目，反之亦然。每个项目做一次就行。

在终端里依次输入：

```powershell
python -m venv .venv
```

（等几秒，文件夹里会多出一个 `.venv` 文件夹，这就是那间工具房）

```powershell
.\.venv\Scripts\Activate.ps1
```

这一行是"走进工具房"。**如果报红字说"禁止运行脚本"**，
先运行下面这句（只需设一次），再重新执行上面的激活命令：

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

激活成功的标志：每行命令最左边出现 `(.venv)` 字样。
以后每次打开终端要运行项目，都要先执行一次激活命令。

### 第 5 步：安装依赖

```powershell
pip install -r requirements.txt
```

国内网络慢/卡住的话，换清华镜像源：

```powershell
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

看到一堆 `Successfully installed ...` 就完成了。

### 第 6 步：申请大模型 API 密钥（需要你亲自操作）

程序本身没有"脑子"，需要调用云端的大模型。推荐使用 **DeepSeek**：
国内可直接访问、价格便宜（开发测试几块钱能用很久）、接口和 OpenAI 兼容
（以后想换 Kimi、智谱等其他国产模型，改配置即可，代码不用动）。

1. 打开 https://platform.deepseek.com ，注册并登录
2. 按提示完成实名认证，充值少量余额
3. 进入左侧 "API keys" 页面，点"创建 API key"，起个名字
4. **立刻复制保存这串 key**——它只显示一次，关了就再也看不到了

拿到 key 后配置到项目里：

1. 把项目里的 `.env.example` 文件复制一份，改名为 `.env`
2. 用记事本/VS Code 打开 `.env`，把 `API_KEY=` 后面的内容换成你的 key
3. 保存

> 为什么密钥不写进代码？因为代码以后可能要上传到 GitHub 公开仓库，
> 密钥一旦泄露，别人就能盗用你的账户余额。`.env` 已被 `.gitignore`
> 排除，永远不会被上传。

### 第 7 步：运行！

```powershell
streamlit run app.py
```

浏览器会自动打开 http://localhost:8501 ，就能看到你的应用了。
想停止程序：回到终端按 `Ctrl + C`。

---

## 三、常见问题

- **`python` 命令找不到**：装 Python 时没勾 Add to PATH，重装并勾选。
- **激活虚拟环境报红字**：先运行
  `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`。
- **API 报 401 / Authentication Error**：`.env` 里的 key 没填对，
  或者文件没改名叫 `.env`（注意开头有个点，且不能是 `.env.example`）。
- **API 报余额不足**：去 DeepSeek 平台充值。
- **端口被占用**：运行 `streamlit run app.py --server.port 8502` 换个端口。

---

## 四、让所有设备通过公网使用（推荐）

前面在电脑上运行得到的是 `localhost` 地址，只适合本机预览。
要让手机、平板、其他电脑都能打开，应该把项目部署到
**Streamlit Community Cloud**。部署成功后，你会得到一个类似
`https://你的名字-resume-agent.streamlit.app` 的网址，任何设备打开它即可使用。

### 1. 注册 GitHub

1. 打开 https://github.com 注册账号。
2. 新建一个仓库（New repository），名字可以叫 `resume-agent`。
3. 把本项目 `resume-agent` 文件夹里的代码上传到仓库。
   不要上传 `.venv`、`data` 和 `.env`；`.gitignore` 已经帮你排除了它们。
4. 确认仓库里能看到 `app.py`、`requirements.txt` 和 `.streamlit/config.toml`。

### 2. 在 Streamlit Cloud 创建网站

1. 打开 https://share.streamlit.io ，用 GitHub 账号登录并授权。
2. 点击 **New app**。
3. 选择刚才的仓库，主文件填 `app.py`，分支选 `main`。
4. 在 **Advanced settings → Python version** 选择 `3.12`。
5. 在 **Advanced settings → Secrets** 填入：

   ```toml
   API_KEY = "你的 DeepSeek API 密钥"
   BASE_URL = "https://api.deepseek.com"
   MODEL_NAME = "deepseek-chat"
   ```

6. 点击 **Deploy**，等几分钟完成部署。
7. 部署完成后，Streamlit 会给你一个 `https://...streamlit.app` 的网址。
   把这个网址发给别人，手机或电脑打开就能使用。

### 3. 重要说明

- 不要把真实 API 密钥写进 `app.py`，也不要把 `.env` 上传到 GitHub。
  云端使用的是 Streamlit Secrets，密钥不会出现在网页前端。
- 免费版 Streamlit Cloud 在长时间没人访问时会休眠，下一次打开会重新启动，
  稍等几十秒即可。
- 当前每个浏览器会得到一个独立的会话编号，保存在网址的 `session_id` 参数里；
  不同设备之间不会互相看到聊天记录或简历。
