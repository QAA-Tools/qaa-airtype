# Shift+Insert 组合键在子线程中失效问题

**日期**: 2025-12-2
**问题类型**: 键盘输入 / Windows API
**影响范围**: Windows 系统，特别是终端应用（CMD/PowerShell）

---

## 问题描述

在 Flask 子线程中使用 `pyautogui.hotkey('shift', 'insert')` 执行 Shift+Insert 粘贴操作时，只触发了 Insert 键，Shift 键未生效。

### 症状
- 昨天代码正常工作，今天突然失效
- 手动按 Shift+Insert 可以正常粘贴
- 脚本执行时只触发 Insert 键，Shift 键被忽略
- 主要在终端应用（CMD/PowerShell）中测试

### 环境
- 操作系统: Windows
- Python 库: pyautogui, Flask
- 执行环境: Flask daemon 线程

---

## 问题根因分析

### 1. 线程问题
Flask 应用运行在 daemon 线程中（`src/remote_server.py:464`）：
```python
t = threading.Thread(target=self.run_flask, args=(listen_host, port), daemon=True)
```

`type_text()` 函数在 Flask 的请求处理线程中执行，这是一个子线程。

### 2. pyautogui 的局限性
- **pyautogui 在 Windows 子线程中对修饰键（Shift、Ctrl 等）的支持很差**
- 修饰键的释放事件无法被正确捕获
- 系统认为 Shift 键一直处于按下状态或从未按下

### 3. 终端应用的特殊性
终端应用（CMD/PowerShell）对键盘输入的处理更底层：
- 需要使用**扫描码**而不是虚拟键码
- Insert 键是**扩展键**，需要 `KEYEVENTF_EXTENDEDKEY` 标志
- 虚拟键码方式在终端中不可靠

---

## 解决方案

### 方案演进

#### ❌ 方案1: 手动控制 pyautogui 按键顺序
```python
pyautogui.keyDown('shift')
time.sleep(0.05)
pyautogui.press('insert')
time.sleep(0.05)
pyautogui.keyUp('shift')
```
**结果**: 失败，子线程问题依然存在

#### ❌ 方案2: 使用 Windows API keybd_event（虚拟键码）
```python
user32.keybd_event(VK_SHIFT, 0, 0, 0)
user32.keybd_event(VK_INSERT, 0, 0, 0)
user32.keybd_event(VK_INSERT, 0, KEYEVENTF_KEYUP, 0)
user32.keybd_event(VK_SHIFT, 0, KEYEVENTF_KEYUP, 0)
```
**结果**: 失败，终端应用不识别虚拟键码

#### ✅ 方案3: 使用 Windows API keybd_event（扫描码 + 扩展键标志）
```python
user32 = ctypes.windll.user32

# 获取扫描码
shift_scan = user32.MapVirtualKeyW(VK_SHIFT, MAPVK_VK_TO_VSC)
insert_scan = user32.MapVirtualKeyW(VK_INSERT, MAPVK_VK_TO_VSC)

# 按下 Shift（使用扫描码）
user32.keybd_event(VK_SHIFT, shift_scan, KEYEVENTF_SCANCODE, 0)
time.sleep(0.05)

# 按下 Insert（使用扫描码 + 扩展键标志）
user32.keybd_event(VK_INSERT, insert_scan, KEYEVENTF_SCANCODE | KEYEVENTF_EXTENDEDKEY, 0)
time.sleep(0.02)

# 释放 Insert
user32.keybd_event(VK_INSERT, insert_scan, KEYEVENTF_SCANCODE | KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)
time.sleep(0.02)

# 释放 Shift
user32.keybd_event(VK_SHIFT, shift_scan, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0)
```
**结果**: ✅ 成功！在终端和其他应用中都能正常工作

---

## 最终实现

### 代码位置
`src/remote_server.py:223-253`

### 完整实现
```python
import ctypes

# Windows API 常量
if IS_WINDOWS:
    VK_SHIFT = 0x10
    VK_INSERT = 0x2D
    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_SCANCODE = 0x0008
    MAPVK_VK_TO_VSC = 0

def send_shift_insert_windows():
    """使用 Windows API 发送 Shift+Insert 组合键（使用扫描码，兼容终端）"""
    if not IS_WINDOWS:
        return False

    try:
        user32 = ctypes.windll.user32

        # 获取扫描码（对于终端应用如 CMD/PowerShell 必须使用扫描码）
        shift_scan = user32.MapVirtualKeyW(VK_SHIFT, MAPVK_VK_TO_VSC)
        insert_scan = user32.MapVirtualKeyW(VK_INSERT, MAPVK_VK_TO_VSC)

        # 按下 Shift（使用扫描码）
        user32.keybd_event(VK_SHIFT, shift_scan, KEYEVENTF_SCANCODE, 0)
        time.sleep(0.05)

        # 按下 Insert（使用扫描码 + 扩展键标志）
        user32.keybd_event(VK_INSERT, insert_scan, KEYEVENTF_SCANCODE | KEYEVENTF_EXTENDEDKEY, 0)
        time.sleep(0.02)

        # 释放 Insert（使用扫描码 + 扩展键标志）
        user32.keybd_event(VK_INSERT, insert_scan, KEYEVENTF_SCANCODE | KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)
        time.sleep(0.02)

        # 释放 Shift（使用扫描码）
        user32.keybd_event(VK_SHIFT, shift_scan, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0)

        return True
    except Exception as e:
        print(f"Windows API error: {e}")
        return False

@app.route('/type', methods=['POST'])
def type_text():
    try:
        data = request.get_json()
        text = data.get('text', '')
        if text:
            pyperclip.copy(text)
            time.sleep(0.1)

            # 使用 Shift+Insert 粘贴（兼容所有应用，包括终端）
            if IS_WINDOWS:
                # Windows: 使用 Windows API 直接发送键盘事件（解决子线程问题）
                success = send_shift_insert_windows()
                if not success:
                    # 如果 Windows API 失败，回退到 pyautogui
                    pyautogui.hotkey('shift', 'insert')
            else:
                # Mac/Linux: 使用 pyautogui
                pyautogui.hotkey('shift', 'insert')

            return {'success': True}
    except Exception as e:
        print(f"Error in type_text: {e}")
        pass
    return {'success': False}
```

---

## 关键技术点

### 1. 扫描码 vs 虚拟键码
- **虚拟键码 (Virtual Key Code)**: 逻辑键码，与物理键盘布局无关
- **扫描码 (Scan Code)**: 物理键码，直接对应键盘硬件
- 终端应用需要扫描码才能正确识别按键

### 2. 扩展键标志
Insert、Home、End、Page Up/Down 等键是扩展键，需要 `KEYEVENTF_EXTENDEDKEY` 标志：
```python
KEYEVENTF_EXTENDEDKEY = 0x0001
```

### 3. MapVirtualKeyW 函数
将虚拟键码转换为扫描码：
```python
scan_code = user32.MapVirtualKeyW(virtual_key, MAPVK_VK_TO_VSC)
```

### 4. 按键事件标志组合
```python
# 按下扩展键
KEYEVENTF_SCANCODE | KEYEVENTF_EXTENDEDKEY

# 释放扩展键
KEYEVENTF_SCANCODE | KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP
```

---

## 诊断工具

创建了 `test_shift.py` 诊断脚本，测试 3 种不同的实现方法：
1. keybd_event（虚拟键码）
2. SendInput（现代 API）
3. keybd_event（扫描码）✅

通过诊断工具确认方案3在终端环境中有效。

---

## 经验总结

1. **pyautogui 在 Windows 子线程中不可靠**，特别是处理修饰键时
2. **终端应用需要使用扫描码**，虚拟键码不够底层
3. **扩展键必须添加 KEYEVENTF_EXTENDEDKEY 标志**
4. **先诊断再实施**：创建测试脚本验证不同方案的有效性
5. **Windows API 比第三方库更可靠**：直接调用系统 API 可以绕过很多限制

---

## 参考资料

- [Windows keybd_event 文档](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-keybd_event)
- [Virtual-Key Codes](https://learn.microsoft.com/en-us/windows/win32/inputdev/virtual-key-codes)
- [Keyboard Input](https://learn.microsoft.com/en-us/windows/win32/inputdev/keyboard-input)

---

## 相关文件

- `src/remote_server.py:223-253` - 核心实现
- `src/remote_server.py:263-271` - 调用逻辑
- `test_shift.py` - 诊断工具
