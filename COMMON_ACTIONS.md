# 常见操作速查

给 `profile_*.json` 里的按键/转轮分支用的现成片段，直接抄。

- 跑起来：`python3 main.py`
- 改配置（可视化界面）：`python3 main.py --config`
- 重新映射手柄硬件：`python3 main.py --map`

动作写在 `layers.<层名>.<输入名>.action`；转轮分支则是 `...Y.action.segments[]` 里的每一项 `{label, action}`。

---

## 一、转轮分支的「单行写法」

配置界面里编辑转轮时，「瞄准」选好摇杆/十字键，下面每瓣一行（标签 / 分支写法 / 占比），其中「分支写法」由 `config_gui.py` 的 `wheel_spec_to_action()` 解析，占比和十字键瞄准见下面的「功能转轮」一节：

| 写法 | 含义 |
| --- | --- |
| `cmd+w` | 键盘按键。`+` 分段，只认 `cmd`/`alt`/`ctrl`/`shift` 四段是修饰键，最后一段是键名 |
| `enter` | 单个按键 |
| `run:open -a "Google Chrome"` | 执行 shell 命令，`run:` 后面的内容原样当命令（里面的 `+` 不会被拆） |
| `click:right` | 鼠标点击，可选 `left`/`right`/`middle` |
| `none` 或留空 | 什么也不做 |

Option 键要写 `alt`（写 `opt` 会被当成键名，见后面「坑」）。

---

## 二、网页 / 浏览器（Chrome、Safari、Edge、Arc 通用）

单行写法直接贴进转轮分支：

| 想要的效果 | 单行写法 |
| --- | --- |
| **网页后退** | `cmd+left` |
| 网页前进 | `cmd+right` |
| 刷新 | `cmd+r` |
| 强制刷新（忽略缓存） | `cmd+shift+r` |
| 新标签页 | `cmd+t` |
| 关闭标签页 | `cmd+w` |
| 恢复刚关掉的标签页 | `cmd+shift+t` |
| 下一个 / 上一个标签页 | `ctrl+tab` / `ctrl+shift+tab` |
| 跳到地址栏 | `cmd+l` |
| 页内查找 | `cmd+f` |
| 整页全屏 | `cmd+ctrl+f` |
| 窗口最小化 | `cmd+m` |
| 向上 / 向下翻屏 | `page_up` / `page_down` |
| 跳到页首 / 页尾 | `home` / `end` |
| 复制 / 粘贴 / 剪切 | `cmd+c` / `cmd+v` / `cmd+x` |
| 撤销 / 重做 | `cmd+z` / `cmd+shift+z` |
| 保存页面 | `cmd+s` |
| 打开 Chrome | `run:open -a "Google Chrome"` |
| 打开一个网址（每次新标签） | `run:open -a "Google Chrome" https://example.com` |
| 打开 `localhost:3000` 并**复用**已有标签页 | 见下面的长命令 |

复用标签页那条（已实测：Chrome 里已有该标签页时切过去，没有才新建，Chrome 没开则启动）：

```
run:osascript -e 'tell application "Google Chrome"' -e 'if (count of windows) = 0 then make new window' -e 'set u to "http://localhost:3000/"' -e 'tell front window' -e 'set k to 0' -e 'repeat with i from 1 to (count of tabs)' -e 'if URL of tab i starts with u then' -e 'set k to i' -e 'exit repeat' -e 'end if' -e 'end repeat' -e 'if k = 0 then make new tab with properties {URL:u}' -e 'if k = 0 then set k to count of tabs' -e 'set active tab index to k' -e 'set index to 1' -e 'end tell' -e 'activate' -e 'end tell'
```

把两处 `http://localhost:3000/` 换成别的网址就是通用版本；只在**最前面那个 Chrome 窗口**里找目标标签页。

---

## 三、系统 / 媒体

| 想要的效果 | 单行写法 |
| --- | --- |
| 静音开关（切换） | `run:osascript -e 'set volume output muted not (output muted of (get volume settings))'` |
| 音量加 / 减 | `media_volume_up` / `media_volume_down` |
| 播放暂停 | `media_play_pause` |
| 上一首 / 下一首 | `media_previous` / `media_next` |
| 锁屏 | `run:osascript -e 'tell application "System Events" to keystroke "q" using {control down, command down}'` |
| 息屏（只关显示器） | `run:pmset displaysleepnow` |
| 睡眠 | `run:pmset sleepnow` |
| 截图：框选并存入剪贴板 | `run:screencapture -i -c` |
| 截图：全屏存到桌面（带时间戳） | `run:screencapture -x ~/Desktop/shot-$(date +%Y%m%d-%H%M%S).png` |
| 退出当前应用 | `cmd+q` |
| 强制退出面板 | `cmd+alt+esc` |
| 任务控制（所有窗口） | `ctrl+up` |
| 启动台 | `run:open -a Launchpad` |
| 打开访达 | `run:open ~` |
| 打开终端 | `run:open -a Terminal` |
| 打开某个应用 | `run:open -a "应用名"` |

截图第一次用会弹「屏幕录制」权限申请，允许一次即可。

---

## 四、JSON 片段（粘进 profile 的 action 里）

### 键盘组合键

```json
{
    "kind": "key",
    "key": "left",
    "modifiers": ["cmd"]
}
```

### 执行 shell 命令

```json
{
    "kind": "command",
    "command": "open -a \"Google Chrome\""
}
```

命令走 `/bin/sh`（`subprocess.Popen(..., shell=True)`），所以 `~`、`$(date ...)`、管道、`&&` 都能用；进程后台跑，不等待，也不回收输出。

### 鼠标点击（按住 = 按下，松开 = 抬起）

```json
{
    "kind": "mouse_click",
    "button": "left"
}
```

### 鼠标滚轮（按住连续滚）

```json
{
    "kind": "scroll",
    "direction": 1,
    "speed": 15,
    "initial_delay": 0.4,
    "repeat_rate": 0.1
}
```

沿用现有 profile 的方向约定：上一个（UP）用 `direction: -1`，下一个（DOWN）用 `1`。

### 扳机模拟滚轮

```json
{
    "kind": "analog_scroll",
    "axis": "rt",
    "threshold": 0.01,
    "direction": 1,
    "speed": 15,
    "initial_delay": 0.3,
    "repeat_rate": 0.05
}
```

### 摇杆控鼠标

```json
{
    "kind": "mouse_move",
    "x_axis": "lx",
    "y_axis": "ly",
    "sensitivity": 24.0,
    "deadzone": 0.15
}
```

### 切层（按住 X 进入 layer_X）

```json
{
    "kind": "modifier",
    "target_layer": "layer_X"
}
```

### 功能转轮（整块）

```json
{
    "kind": "wheel",
    "pointer_x": "lx",
    "pointer_y": "ly",
    "deadzone": 0.45,
    "segments": [
        {
            "label": "关闭页面",
            "width": 0.5,
            "action": {
                "kind": "key",
                "key": "w",
                "modifiers": ["cmd"]
            }
        },
        {
            "label": "网页后退",
            "action": {
                "kind": "key",
                "key": "left",
                "modifiers": ["cmd"]
            }
        },
        {
            "label": "截图",
            "action": {
                "kind": "command",
                "command": "screencapture -i -c"
            }
        }
    ]
}
```

用法：按住绑定的键打开转轮 → 用 `pointer_x`/`pointer_y` 指定的摇杆拨向某一瓣 → **摇杆回中**执行。

`width` 是这一瓣在转盘上占的角度份额，**默认 1，可以不写**：

| 取值 | 效果 |
| --- | --- |
| `1` | 默认，平均分（6 瓣时每瓣 60°） |
| `2` | 别人两倍宽 |
| `0.5` | 别人一半宽。上例里是 `0.5 / 5.5 × 360° ≈ 32.7°`，其余每瓣约 65.5° |
| `0` | 几乎选不中，等于临时停用这一瓣 |

份额只按相对比例算，总角度永远 360°，所以收窄一瓣会把多出来的角度分给其他瓣。把「关闭页面」这类会丢东西的操作收窄，是降低误触的常见用法。

配置界面里每瓣一行就是「标签 / 分支写法 / 占比」三列，占比填在这里即可；存盘时等于 1 的份额会被省略，文件里不会多出一堆 `"width": 1`。

### 用十字键瞄准（4 格）

`pointer_x`/`pointer_y` 决定拿哪个输入瞄准，不写就是左摇杆：

| 瞄准来源 | `pointer_x` / `pointer_y` | 建议瓣数 |
| --- | --- | --- |
| 左摇杆 | `lx` / `ly` | 任意 |
| 右摇杆 | `rx` / `ry` | 任意 |
| 十字键 | `dx` / `dy` | 4（一瓣正好管一个方向） |

十字键瞄准时 4 瓣各管一个方向，不用记角度：

| 十字键推到 | 选中的瓣 |
| --- | --- |
| 上 | 第 1 瓣 |
| 右 | 第 2 瓣 |
| 下 | 第 3 瓣 |
| 左 | 第 4 瓣 |

斜按（比如上+左）会落到最近的那一瓣。

配置界面里就是「瞄准」那个下拉。用的时候注意：

- **十字键只负责选，转轮要用另一个键打开**：按住触发键 → 拨一下方向 → 松手就执行。如果每个按钮都被占了，可以腾一个重复的绑定出来（比如 Y 和 HOME 都是回车，拿一个当转轮触发键）。
- **打开期间十字键自己的绑定会自动静音**，所以拨方向不会顺带滚屏/翻页；不按触发键时，十字键还是原来的滚屏/方向键。
- `dx`/`dy` 是从 UP/DOWN/LEFT/RIGHT 推出来的，跟底层怎么映射十字键无关，**不需要改 `hardware` 段**。

### 什么都不做

```json
{
    "kind": "none"
}
```

### 输入名（`layers.default` 下的可用键）

`A` `B` `X` `Y` `LB` `RB` `LT` `RT` `UP` `DOWN` `LEFT` `RIGHT` `LEFT_STICK` `RIGHT_STICK` `RS` `HOME` `MENU`

切到别的层（`modifier` 的 `target_layer`）时，**只**执行那一层里定义过的输入，没定义的直接什么都不做，不会回落到 `default` 层。所以 `layer_X` 里要先把 `RIGHT`/`LEFT`/`UP`/`DOWN` 这些写好。

---

## 五、键名与修饰键

修饰键只认这四个：`cmd` `alt` `ctrl` `shift`。

键名按 pynput 的 `Key` 成员解析（实测 python3.12 + pynput，macOS 上可用的是这些）：

```
alt  alt_r  backspace  caps_lock  cmd  cmd_r  ctrl  ctrl_r
delete  down  end  enter  esc  home  left  right  space  tab  up
f1 ... f20
media_eject  media_next  media_play_pause  media_previous
media_volume_down  media_volume_mute  media_volume_up
page_down  page_up
```

不在这个表里的字符串会按「字面字符」处理，所以 `3`、`[`、`/`、`a` 这类也能直接写：

```json
{
    "kind": "key",
    "key": "[",
    "modifiers": ["cmd"]
}
```

注意 macOS 的 pynput 没有 `print_screen`、`insert`、`num_lock`、`pause` 这些名字，也没有 `*_l` 后缀（`cmd_l`/`shift_l`/`ctrl_l`/`alt_l` 不存在，只有 `ctrl_r`、`alt_r`、`cmd_r`、`shift_r`）。

---

## 六、几个坑

- **键盘类动作只在「按下」那一瞬间触发一次**，长按不连发。想连发就在 `command` 里自己写循环，或改按键的按下沿处理。
- **`mouse_click` 放在普通按键上是「按住=按下、松开=抬起」**（可以按住 A 拖拽），但放在转轮分支里是 `trigger_once`，也就是单击一下。
- **单行写法里 `+` 是分隔符**，所以「按加号键」在单行写法里表达不了（`cmd++` 会被解析成只有修饰键）。这种键用 JSON 的 `"key": "+"` 形式。
- **单行写法里 Option 必须写 `alt`**：`cmd+opt+esc` 会把 `opt` 当键名丢掉，正确是 `cmd+alt+esc`。
- **命令里的双引号**：写进 JSON 时是 `\"`。用配置界面填的话它会自己转义，不用管。
- **转轮取消**：先松开绑定的键就是取消；取消后摇杆要回中，鼠标才会恢复移动（防止光标乱飞）。
- **改 JSON 只影响动作**。换了手柄型号要先 `python3 main.py --map` 重新映射硬件段。

---

## 七、改完自检

```bash
# 1. JSON 语法
python3 -c "import json; json.load(open('profile_Xbox_Series_X_Controller.json')); print('OK')"

# 2. 能被程序正确解析成 Profile
python3 -c "from profile_manager import load_profile; p = load_profile('Xbox_Series_X_Controller', '.'); print(p.name, list(p.layers))"

# 3. 只想确认某个动作解析出来的样子
python3 -c "
import json
d = json.load(open('profile_Xbox_Series_X_Controller.json'))
for s in d['layers']['default']['Y']['segments']:
    print(s['label'], '->', s['action'])
"
```

这三步只用到标准库和 `profile_manager`，随便哪个 `python3` 都行。真正跑 `main.py` 需要 pygame / pynput（本机装在 `python3.12` 那套环境里，实测 pygame 2.6.1）。
